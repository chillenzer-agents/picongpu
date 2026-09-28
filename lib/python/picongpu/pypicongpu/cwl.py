"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

import json
import logging
from os import environ
from pathlib import Path
from typing import cast

from cwltool.context import LoadingContext, RuntimeContext
from cwltool.cwlprov.ro import ResearchObject
from cwltool.cwlprov.writablebagfile import close_ro, create_job, open_log_file_for_activity, packed_workflow
from cwltool.factory import Factory as WorkflowFactory
from cwltool.load_tool import fetch_document, resolve_and_validate_document
from cwltool.loghandler import _logger as cwltool_logger
from cwltool.main import ProvLogFormatter, print_pack, prov_deps, resolve_tool_uri
from cwltool.stdfsaccess import StdFsAccess
from cwltool.workflow import default_make_tool


def _coerce_flag(value, default: bool) -> bool:
    """Coerce an rc_params flag to a bool so string values like ``"false"`` opt out.

    ``rc_params`` tables are free-form (a plain dict), so a flag may arrive as a string
    (e.g. from a TOML comment or a typo). A bare ``bool("false")`` is ``True`` and a
    bare ``not "false"`` is ``False`` -- both would silently defeat an opt-out. This maps
    the common textual forms ("false"/"0"/"no"/"off"/"none" and their negations) to the
    intended boolean and leaves real booleans/ints intact.
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() not in {"", "false", "0", "no", "off", "none"}
    return bool(value)


class CWLWorkflow:
    """
    Runs a CWL workflow in-process via cwltool's ``WorkflowFactory`` and, optionally,
    mirrors the cwltool CLI provenance wiring so a complete Research Object (packed
    workflow, primary job/output, snapshot, per-activity log, bagit manifests, prov
    profiles) is produced under ``provenance_path``.

    This class is the seam between :class:`picongpu.pypicongpu.runner.Runner` and
    cwltool: the runner supplies the workflow locations and where results/provenance
    go, while this class owns the cwltool specifics (tool loading, job creation,
    Research Object management). The interface is intentionally platform-agnostic so
    other submission backends can program against it too.

    Provenance is on by default (driven by the ``enabled`` entry of
    ``provenance_config``). A failure in the provenance machinery is logged as a
    WARNING and never fails the run itself: the simulation result is always returned.
    """

    def __init__(
        self,
        *,
        workflow_definition: Path,
        workflow_input: Path,
        run_dir: Path,
        cwl_cachedir: Path,
        provenance_path: Path,
        provenance_config: dict,
    ):
        self._workflow_definition = workflow_definition
        self._workflow_input = workflow_input
        self._run_dir = run_dir
        self._cwl_cachedir = cwl_cachedir
        self._provenance_path = provenance_path
        self._provenance_config = provenance_config

    def _runtime_context(self) -> RuntimeContext:
        return RuntimeContext(
            kwargs={
                "outdir": str(self._run_dir),
                "rm_tmpdir": False,
                "move_outputs": "copy",
                "cachedir": str(self._cwl_cachedir),
                "preserve_entire_environment": True,
            }
        )

    def run(self):
        """Run the workflow and return its result.

        Provenance is on by default; it is switched off when ``enabled`` in the
        ``provenance_config`` (the validated rc_params ``[provenance]`` table) is false.
        A provenance failure degrades to a WARNING but the result is always returned.
        """
        if not _coerce_flag(self._provenance_config.get("enabled"), default=True):
            return self._run_bare()
        return self._run_with_provenance(self._provenance_config)

    def _run_bare(self):
        """Run the workflow without any cwltool provenance tracking."""
        with self._workflow_input.open("r") as file:
            return WorkflowFactory(runtime_context=self._runtime_context()).make(str(self._workflow_definition))(
                **json.load(file)
            )

    def _run_with_provenance(self, provenance_config: dict):
        """
        Run the workflow through the in-process ``WorkflowFactory`` while mirroring the
        cwltool CLI provenance wiring (``cwltool.main``), so a complete Research Object
        (packed workflow, primary job/output, snapshot, per-activity log, bagit
        manifests, prov profiles) is produced under ``provenance_path``.

        A failure in the provenance machinery is logged as a WARNING and never fails the
        run itself: the simulation result is always returned.
        """
        rt = self._runtime_context()

        full_name = provenance_config.get("full_name", "") or environ.get("CWL_FULL_NAME", "") or ""
        orcid = provenance_config.get("orcid", "") or environ.get("ORCID", "") or ""
        host_provenance = _coerce_flag(provenance_config.get("host"), default=True)
        user_provenance = _coerce_flag(provenance_config.get("user"), default=False)

        ro = None
        prov_log_handler = None
        prov_log_stream = None
        log_stopped = False
        closed = False

        def stop_prov_log():
            nonlocal log_stopped
            if log_stopped:
                return
            log_stopped = True
            # Stop logging so we don't half-log adding ourself to the RO; the stream's
            # close() finalizes the tagfile into the (still open) RO.
            if prov_log_handler is not None:
                cwltool_logger.removeHandler(prov_log_handler)
                prov_log_handler.flush()
                if prov_log_stream is not None:
                    prov_log_stream.close()
                prov_log_handler.close()

        try:
            # Set up the Research Object and its contexts. If this fails, fall back to a
            # plain run rather than failing the simulation over provenance.
            try:
                ro = ResearchObject(
                    StdFsAccess(""),
                    temp_prefix_ro=rt.tmpdir_prefix,
                    orcid=orcid,
                    full_name=full_name,
                )
                rt.research_obj = ro

                prov_log_stream = open_log_file_for_activity(ro, ro.engine_uuid)
                prov_log_handler = logging.StreamHandler(prov_log_stream)
                prov_log_handler.setFormatter(ProvLogFormatter())
                cwltool_logger.addHandler(prov_log_handler)

                lc = LoadingContext()
                lc.construct_tool_object = default_make_tool
                lc.research_obj = ro
                lc.orcid = orcid
                lc.cwl_full_name = full_name
                lc.host_provenance = host_provenance
                lc.user_provenance = user_provenance
                # Forward to the runtime context the way cwltool.main does.
                rt.prov_host = host_provenance
                rt.prov_user = user_provenance
            except Exception:
                logging.exception("[provenance] Could not set up provenance; running the workflow without it")
                return self._run_bare()

            # Run the workflow; a failure here is a real run failure and propagates.
            with self._workflow_input.open("r") as file:
                out = WorkflowFactory(loading_context=lc, runtime_context=rt).make(str(self._workflow_definition))(
                    **json.load(file)
                )

            # Produce the remaining RO artifacts. A failure here degrades to a WARNING
            # but the (already successful) result is still returned.
            try:
                create_job(ro, out, True)
                # Re-resolve the document (Factory.make() leaves lc.loader == None) so the
                # packed workflow and snapshot can be produced, mirroring cwltool.main.
                uri, _ = resolve_tool_uri(str(self._workflow_definition))
                lc, workflowobj, uri = fetch_document(uri, lc)
                lc, uri = resolve_and_validate_document(lc, workflowobj, uri)
                if lc.loader is not None:
                    processobj, _ = lc.loader.resolve_ref(uri)
                    packed_workflow(ro, print_pack(lc, uri))
                    ro.generate_snapshot(prov_deps(cast(dict, processobj), lc.loader, uri))
            except Exception:
                logging.exception(
                    "[provenance] Failed to finalize the provenance artifacts; the simulation result is returned"
                    " without full provenance"
                )

            # Finalize: stop the log (adds the log tagfile to the manifest) while the RO is
            # still open, then move the RO into place. A failure here (e.g. temp disk full in
            # _finalize, or an IO/permission error on the move) must not discard the
            # (already successful) result: log it and return the result anyway. On failure the
            # temp Research Object is still cleaned up by the ``finally`` below (best effort).
            try:
                stop_prov_log()
                provenance_path = self._provenance_path
                if provenance_path.is_dir() and any(provenance_path.iterdir()):
                    logging.warning(
                        "[provenance] %s already exists and is non-empty; it will be overwritten",
                        provenance_path,
                    )
                close_ro(ro, str(provenance_path))
                closed = True
            except Exception:
                logging.exception(
                    "[provenance] Failed to move the Research Object into place; the simulation "
                    "result is returned without a finalized provenance Research Object"
                )
            return out
        finally:
            # On any path that didn't move the RO into place, stop the log (best effort) and
            # clean up the temp Research Object.
            stop_prov_log()
            if ro is not None and not closed:
                close_ro(ro, None)
