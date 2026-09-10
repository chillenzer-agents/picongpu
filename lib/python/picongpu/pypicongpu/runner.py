"""
This file is part of PIConGPU.
Copyright 2021-2024 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre, Richard Pausch
License: GPLv3+
"""

import datetime
import json
import logging
import tempfile
from importlib.util import module_from_spec, spec_from_file_location
from os import chmod, environ
from pathlib import Path
from shutil import copy2, copytree
from typing import Annotated, Sequence, cast

from cwltool.context import LoadingContext, RuntimeContext
from cwltool.cwlprov.ro import ResearchObject
from cwltool.cwlprov.writablebagfile import close_ro, create_job, open_log_file_for_activity, packed_workflow
from cwltool.factory import Factory as WorkflowFactory
from cwltool.load_tool import fetch_document, resolve_and_validate_document
from cwltool.loghandler import _logger as cwltool_logger
from cwltool.main import ProvLogFormatter, print_pack, prov_deps, resolve_tool_uri
from cwltool.stdfsaccess import StdFsAccess
from cwltool.workflow import default_make_tool
from pydantic import (
    AfterValidator,
    AliasChoices,
    BaseModel,
    BeforeValidator,
    Field,
    field_serializer,
)
from rocrate.rocrate import ROCrate

from picongpu import core, rc_params
from picongpu.templates import path as tpath

from .rendering import Renderer
from .simulation import Simulation
from .util import alt


def script_content_with(commands, rc_params=rc_params):
    if not isinstance(commands, str):
        commands = "\n".join(commands)
    return f"""{rc_params.shebang}

# preamble
{rc_params.preamble}

# profile content
{rc_params.profile_content}

# commands
{commands}
"""


def generate_bare_profile(path=None, rc_params=rc_params):
    if path is None:
        return generate_bare_profile(
            path=Path(tempfile.NamedTemporaryFile("w", delete=False, delete_on_close=False).name), rc_params=rc_params
        )
    if not isinstance(path, Path):
        return generate_bare_profile(path=Path(path), rc_params=rc_params)

    with rc_params.set_temporarily(preamble="", override_existing=False):
        with path.open("w") as file:
            file.write(script_content_with("", rc_params=rc_params))

    return path


def generate_bare_profile_as_in(script_path, path=None):
    if not isinstance(script_path, Path):
        return generate_bare_profile_as_in(Path(script_path).absolute(), path=path)
    if not script_path.is_absolute():
        return generate_bare_profile_as_in(script_path.absolute(), path=path)

    module_spec = spec_from_file_location("script", script_path)
    module = module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return generate_bare_profile(path=path, rc_params=module.rc_params)


def get_tmpdir_with_name(name, parent: Path | None = None):
    """
    returns a not existing temporary directory path,
    which contains the given name
    :param name: part of the newly created directory name
    :param parent: if given: create the tmpdir there
    :return: not existing path to directory
    """
    with tempfile.TemporaryDirectory(
        prefix=f"pypicongpu-{datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}-{name}-", dir=parent
    ) as tmpdir:
        return Path(tmpdir).absolute()


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


class PicBuildFlags(BaseModel):
    # We explicitly disallow the some shorthands like `-c`, `-t`, ...
    # because they overlap with tbg flags and could thus lead to confusion.
    jobs: int | None = Field(
        default=4,
        description="allow N jobs at once; infinite jobs if set to None",
        validation_alias=AliasChoices("jobs", "j"),
    )

    cmake: str | None = Field(
        default=None,
        description=(
            'Extra arguments that are passed straight to CMake, e.g. "-DPIC_VERBOSE=21 -DCMAKE_BUILD_TYPE=Debug".'
        ),
        validation_alias=AliasChoices("cmake"),
    )

    preset: int | None = Field(
        default=None,
        description="Configure this preset number from CMake flags.",
        ge=0,
        validation_alias=AliasChoices("preset"),
    )

    force: bool = Field(
        default=False,
        description=("When set, clears the CMake file cache and forces a scan for new .param files."),
        validation_alias=AliasChoices("force", "f"),
    )

    cmake_build_system: str | None = Field(
        default=None,
        description=("Select the build system used by CMake (e.g. ``Ninja``)."),
        validation_alias=AliasChoices("G"),
    )


class TBGFlags(BaseModel):
    # We explicitly disallow the some shorthands like `-c`, `-t`, ...
    # because they overlap with pic-build flags and could thus lead to confusion.
    cfg_file: str = Field(
        default="etc/picongpu/N.cfg",
        description="Configuration file to set up batch file.",
        validation_alias=AliasChoices("cfg"),
    )

    submit_system: str | None = Field(
        default_factory=lambda: rc_params.get("tbg_submit", "bash"),
        description="Submit command (qsub, 'qsub -h', sbatch, ...).",
        validation_alias=AliasChoices("submit", "s"),
    )

    template_file: str | None = Field(
        default_factory=lambda: rc_params.get("tbg_tpl_file", None), validation_alias=AliasChoices("tpl")
    )

    overwrite_vars: list[str] | None = Field(
        default=None,
        description="Overwrite any template variable.",
        validation_alias=AliasChoices("o"),
    )

    force: bool = Field(
        default=False,
        description="Override if 'destinationPath' exists.",
        validation_alias=AliasChoices("force", "f"),
    )

    project_path: Path = Field(description="Simulation setup directory to run.")

    @field_serializer("project_path")
    def _serialize_project_path(self, value) -> dict[str, str]:
        return {"class": "Directory", "location": str(value)}


class Runner(BaseModel):
    """
    Accepts a PyPIConGPU Simulation and runs it

    Manages 2 basic parts:

    - *where* which data is stored (various ``..._dir`` options)
    - *what* is done (generate, build, run)

    Where:

    - run_dir: directory where data for an execution is stored
    - setup_dir: directory where data is generated to and the simulation
      executable is built

    These dirs are either copied from params or guessed.
    See __init__() for a detailed description.

    The initialization of the dirs happens only once (!) inside __init__().
    Any changes performed after that will be accepted and might lead to broken
    builds.

    What:

    - generate(): create a setup (directory) which represents the parameters
      given
    - build(): run pic-build
    - run(): run tbg

    Typically these can only be performed in that order, and each once.
    Whether a step can be started is determined by some sanity checks:
    Are the inputs (e.g. the setup dir, the ``.build`` dir) ready,
    and is the output location empty (e.g. the run dir).
    **If those sanity checks pass, the respective process is launched.**
    If this launched program (e.g. pic-build) fails,
    the process output (stdout & stderr) is printed.
    While a process is running, all output is silenced
    (and collected into an internal buffer).
    """

    template_dir: Annotated[Sequence[Path], AfterValidator(lambda t: tuple(p.absolute() for p in t))] = (tpath(),)
    setup_dir: Annotated[Path, AfterValidator(Path.absolute)] = Field(
        default_factory=lambda: Path(get_tmpdir_with_name("setup")).absolute()
    )
    run_dir: Annotated[Path, AfterValidator(Path.absolute)] = Field(
        default_factory=lambda: Path(get_tmpdir_with_name("run")).absolute()
    )
    sim: Annotated[Simulation, BeforeValidator(lambda s: alt(lambda: s.get_as_pypicongpu(), s))]

    def _log_dirs(self):
        """print human-readble list of paths to log"""
        logging.info(" template dir: {}".format(self.template_dir))
        logging.info("    setup dir: {}".format(self.setup_dir))
        logging.info("      run dir: {}".format(self.run_dir))

    def _render_templates(self):
        """
        render the templates in the setup dir into a picongpu input

        Delegates work to Renderer(), see there for details.
        """
        logging.info("rendering templates...")
        # This is kind of a dirty hack:
        self.sim.spread_directory_information(self.setup_dir)
        # check 1 (implicit): according to schema?
        context = self.sim.get_rendering_context()
        # check 2: structure suitable for renderer?
        Renderer.check_rendering_context(context)
        # dump checked context
        self.store_metadata(context, filename="pypicongpu_rendering_context.json")
        # preprocess (floats to str, add _special properties, ...)
        Renderer.render_directory(Renderer.get_context_preprocessed(context), str(self.setup_dir))

    @property
    def metadata_path(self):
        return self.setup_dir / "metadata"

    @property
    def workflow_dir_path(self):
        return self.setup_dir / "workflow"

    @property
    def workflow_scripts_path(self):
        return self.workflow_dir_path / "scripts"

    @property
    def profile_path(self):
        return self.workflow_scripts_path / "picongpu.profile"

    @property
    def build_script_path(self):
        return self.workflow_scripts_path / "build.sh"

    @property
    def prepare_submission_script_path(self):
        return self.workflow_scripts_path / "prepare_submission.sh"

    @property
    def submission_script_path(self):
        return self.workflow_scripts_path / "submit.sh"

    @property
    def gather_results_script_path(self):
        return self.workflow_scripts_path / "gather_results.sh"

    @property
    def workflow_definition_path(self):
        return self.workflow_dir_path / "workflow.cwl"

    @property
    def workflow_input_path(self):
        return self.workflow_dir_path / "input.yaml"

    @property
    def workflow_path(self):
        return self.workflow_dir_path / "workflow.cwl"

    @property
    def build_step_path(self):
        return self.workflow_dir_path / "steps" / "build.cwl"

    @property
    def run_step_path(self):
        return self.workflow_dir_path / "steps" / "run.cwl"

    @property
    def cwl_cachedir(self):
        return self.run_dir / ".cwl_cache"

    @property
    def provenance_path(self):
        return self.run_dir / "provenance"

    def generate_profile(self):
        self.profile_path.parent.mkdir(parents=True, exist_ok=True)
        generate_bare_profile(self.profile_path)

    def generate_build_command(self, rc_params=rc_params):
        self.build_script_path.parent.mkdir(parents=True, exist_ok=True)
        with self.build_script_path.open("w") as script:
            script.write(script_content_with("pic-build $@", rc_params=rc_params))
            script.flush()
        chmod(self.build_script_path, 0o755)

    def generate_prepare_submission_command(self, rc_params=rc_params):
        self.prepare_submission_script_path.parent.mkdir(parents=True, exist_ok=True)
        with self.prepare_submission_script_path.open("w") as script:
            script.write(
                script_content_with(
                    [
                        f'export PIC_PROFILE="{self.profile_path}"',
                        "tbg $@ . run_dir",
                    ],
                    rc_params=rc_params,
                )
            )
            script.flush()
        chmod(self.prepare_submission_script_path, 0o755)

    def generate_submission_command(self, rc_params=rc_params):
        self.submission_script_path.parent.mkdir(parents=True, exist_ok=True)
        with self.submission_script_path.open("w") as script:
            script.write(
                script_content_with(
                    [
                        "cp -r tbg_link tbg",
                        'submission_script="./tbg/submit.start"',
                        'submission_cmd="$1"',
                        'sed -i "s|TBG_dstPath=.*|TBG_dstPath=$(pwd -P)|" "$submission_script"',
                        'sed -i "s|--chdir=.*|--chdir=$(pwd -P)|" "$submission_script"',
                        r"""
                        if [[ "$submission_cmd" =~ \s*bash.* ]] || [[ "$submission_cmd" =~ \s*zsh.* ]]; then
                            $submission_cmd $submission_script &
                            echo $! > "submission_information.txt";
                        else
                            $submission_cmd $submission_script > "submission_information.txt";
                        fi
                        """,
                        r"""echo "#!/bin/bash
                        ln -s $(pwd -P)/simOutput \$1" > link_results.sh
                        """,
                        "chmod +x link_results.sh",
                    ],
                    rc_params=rc_params,
                )
            )
            script.flush()
        chmod(self.submission_script_path, 0o755)

    def generate_workflow_input(self, build_flags: PicBuildFlags, run_flags: TBGFlags):
        with (self.workflow_input_path).open("w") as file:
            # Technically, we are writing json into a yaml file here,
            # but yaml is a superset of json, so that's fine.
            json.dump(
                # We follow the comvention of prefixing with `build_` (resp. `run_`)
                # because this makes it easy to filter and parse the arguments
                # in cases when one wants to run the steps individually.
                {
                    "build_include_directory": {
                        "class": "Directory",
                        "location": str(self.setup_dir / "include"),
                    },
                    "build_script": {
                        "class": "File",
                        "location": str(self.build_script_path),
                    },
                    **{f"build_{key}": value for key, value in build_flags.model_dump(mode="json").items()},
                    "run_etc_directory": {
                        "class": "Directory",
                        "location": str(self.setup_dir / "etc"),
                    },
                    "submission_script": {
                        "class": "File",
                        "location": str(self.submission_script_path),
                    },
                    "prepare_submission_script": {
                        "class": "File",
                        "location": str(self.prepare_submission_script_path),
                    },
                    "organize_output_script": {
                        "class": "File",
                        "location": str(self.workflow_scripts_path / "organize_output.sh"),
                    },
                    **{f"run_{key}": value for key, value in run_flags.model_dump(mode="json").items()},
                },
                file,
                indent=4,
            )

    def store_metadata(self, metadata, filename):
        self.metadata_path.mkdir(parents=True, exist_ok=True)
        with (self.metadata_path / filename).open("w") as file:
            json.dump(metadata, file, indent=4)

    def generate(self, printDirToConsole=False, exist_ok=False, **flags):
        """
        generate the picongpu-compatible input files
        """

        if printDirToConsole:
            print(" [" + str(self.setup_dir) + "]")

        if not exist_ok:
            assert not self.setup_dir.is_dir(), (
                "setup directory must not exist before generation -- did you call generate() already?"
            )
        preset = rc_params.preset_dir
        copytree(core.path("etc") / f"picongpu/{preset}", self.setup_dir / f"etc/picongpu/{preset}")
        for path in (core.path("etc") / "picongpu").iterdir():
            if path.is_file():
                copy2(path, self.setup_dir / f"etc/picongpu/{path.name}")

        for t in self.template_dir:
            for src, dst in map(
                lambda f: (t / f, self.setup_dir / f),
                ("etc/picongpu", "bin", "include/picongpu", "lib", "validation", "workflow"),
            ):
                if src.is_dir():
                    dst.mkdir(parents=True, exist_ok=True)
                    copytree(src, dst, dirs_exist_ok=True)

        self.generate_profile()
        self.generate_build_command()
        self.generate_prepare_submission_command()
        self.generate_submission_command()

        self._render_templates()

        self.generate_workflow_input(
            build_flags=PicBuildFlags(**flags),
            run_flags=TBGFlags(project_path=self.setup_dir, **flags),
        )
        self.cwl_cachedir.mkdir(parents=True)

        self.store_metadata(self.model_dump(mode="json"), filename="pypicongpu_runner.json")
        self.store_metadata(rc_params.model_dump(mode="json"), filename="rc_params.json")

        self._write_rocrate()

    def _write_rocrate(self):
        rc_params.rocrate_info.add_metadata_to(ROCrate(self.setup_dir, version="1.2", init=True)).metadata.write(
            self.setup_dir
        )

    def run(self):
        """
        run compiled picongpu simulation
        """
        # cwltool provenance (a Research Object) is tracked in-process and written to
        # `run_dir/provenance/`. It is on by default and configured via the `[provenance]`
        # table of rc_params (see `.picongpurc.toml`); set `enabled = false` to opt out.
        raw_provenance = rc_params.get("provenance", {}) or {}
        if not isinstance(raw_provenance, dict):
            logging.warning(
                "[provenance] the rc_params 'provenance' table must be a dict; got %s; using defaults",
                type(raw_provenance).__name__,
            )
            raw_provenance = {}
        if not _coerce_flag(raw_provenance.get("enabled"), default=True):
            return self._run_bare()
        return self._run_with_provenance(raw_provenance)

    def _run_bare(self):
        """Run the workflow without any cwltool provenance tracking."""
        with self.workflow_input_path.open("r") as file:
            return WorkflowFactory(
                runtime_context=RuntimeContext(
                    kwargs={
                        "outdir": str(self.run_dir),
                        "rm_tmpdir": False,
                        "move_outputs": "copy",
                        "cachedir": str(self.cwl_cachedir),
                        "preserve_entire_environment": True,
                    }
                )
            ).make(str(self.workflow_definition_path))(**json.load(file))

    def _run_with_provenance(self, provenance_config: dict):
        """
        Run the workflow through the in-process ``WorkflowFactory`` while mirroring the
        cwltool CLI provenance wiring (``cwltool.main``), so a complete Research Object
        (packed workflow, primary job/output, snapshot, per-activity log, bagit
        manifests, prov profiles) is produced under ``provenance_path``.

        A failure in the provenance machinery is logged as a WARNING and never fails the
        run itself: the simulation result is always returned.
        """
        rt = RuntimeContext(
            kwargs={
                "outdir": str(self.run_dir),
                "rm_tmpdir": False,
                "move_outputs": "copy",
                "cachedir": str(self.cwl_cachedir),
                "preserve_entire_environment": True,
            }
        )

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
            with self.workflow_input_path.open("r") as file:
                out = WorkflowFactory(loading_context=lc, runtime_context=rt).make(str(self.workflow_definition_path))(
                    **json.load(file)
                )

            # Produce the remaining RO artifacts. A failure here degrades to a WARNING
            # but the (already successful) result is still returned.
            try:
                create_job(ro, out, True)
                # Re-resolve the document (Factory.make() leaves lc.loader == None) so the
                # packed workflow and snapshot can be produced, mirroring cwltool.main.
                uri, _ = resolve_tool_uri(str(self.workflow_definition_path))
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
                provenance_path = self.provenance_path
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
