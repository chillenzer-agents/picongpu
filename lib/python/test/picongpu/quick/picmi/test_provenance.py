"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from picongpu import rc_params
from picongpu.picmi import Cartesian3DGrid, ElectromagneticSolver, Simulation
from pytest import fixture

# A tiny, self-contained workflow that stands in for the (heavy) PIConGPU build/run
# workflow: it echoes a string to stdout (a File output). Running it through the
# provenance path is fast and reliable, and it exercises the same in-process
# ``WorkflowFactory`` + Research Object wiring as the real workflow.
_ECHO_CWL = """\
cwlVersion: v1.2
class: CommandLineTool
label: "provenance probe"
inputs:
  text: string
baseCommand: [echo, "$(inputs.text)"]
outputs:
  output_file:
    type: stdout
"""


@fixture
def picmi_sim():
    return Simulation(
        time_step_size=17,
        max_steps=4,
        solver=ElectromagneticSolver(
            method="Yee",
            grid=Cartesian3DGrid(
                number_of_cells=[32, 32, 32],
                lower_bound=[0, 0, 0],
                upper_bound=[32, 32, 32],
                # required, otherwise won't spawn
                lower_boundary_conditions=["open", "open", "periodic"],
                upper_boundary_conditions=["open", "open", "periodic"],
            ),
        ),
    )


def _build_probe_runner(sim, base_dir: Path):
    """Generate a setup and swap the heavy workflow for the tiny echo probe."""
    setup_dir = base_dir / "setup"
    run_dir = base_dir / "run"
    runner = sim.picongpu_get_runner(setup_dir=setup_dir, run_dir=run_dir)
    runner.generate()

    runner.workflow_dir_path.mkdir(parents=True, exist_ok=True)
    runner.workflow_definition_path.write_text(_ECHO_CWL)
    runner.workflow_input_path.write_text(json.dumps({"text": "provenance probe input"}))
    return runner


def test_provenance_path_is_under_run_dir(picmi_sim):
    with _new_base() as base:
        runner = _build_probe_runner(picmi_sim, base)
        assert runner.provenance_path == runner.run_dir / "provenance"


def test_provenance_enabled_produces_research_object(picmi_sim):
    with _new_base() as base:
        runner = _build_probe_runner(picmi_sim, base)
        with rc_params.set_temporarily(provenance={"enabled": True, "full_name": "Jane Tester"}):
            out = runner.run()

        # Assert while the temp base dir is still on disk (it is cleaned up on exit).
        assert out is not None and isinstance(out, dict)
        prov = runner.provenance_path
        assert prov.is_dir()

        # Packed workflow + primary job/output + per-run snapshot.
        assert (prov / "workflow" / "packed.cwl").is_file()
        assert (prov / "workflow" / "primary-job.json").is_file()
        assert (prov / "workflow" / "primary-output.json").is_file()
        assert (prov / "snapshot" / "workflow.cwl").is_file()

        # BagIt research object structure (payload + tag manifests + bag metadata).
        assert (prov / "data").is_dir()
        assert (prov / "bag-info.txt").is_file()
        assert (prov / "bagit.txt").is_file()
        assert (prov / "manifest-sha1.txt").is_file()
        assert (prov / "tagmanifest-sha1.txt").is_file()
        assert (prov / "metadata" / "manifest.json").is_file()

        # The PROV profile of the run (in the formats cwltool emits).
        assert (prov / "metadata" / "provenance" / "primary.cwlprov.json").is_file()
        assert (prov / "metadata" / "provenance" / "primary.cwlprov.jsonld").is_file()

        # The engine's per-activity log.
        assert list((prov / "metadata" / "logs").glob("engine.*.txt"))


def test_provenance_disabled_produces_no_research_object(picmi_sim):
    with _new_base() as base:
        runner = _build_probe_runner(picmi_sim, base)
        with rc_params.set_temporarily(provenance={"enabled": False}):
            out = runner.run()

        assert out is not None and isinstance(out, dict)
        assert not runner.provenance_path.exists()


def test_provenance_enabled_by_default(picmi_sim):
    # No `[provenance]` table at all -> the default (enabled) path is taken.
    with _new_base() as base:
        runner = _build_probe_runner(picmi_sim, base)
        out = runner.run()

        assert out is not None and isinstance(out, dict)
        assert runner.provenance_path.is_dir()
        assert (runner.provenance_path / "workflow" / "packed.cwl").is_file()


def test_provenance_close_failure_does_not_discard_result(picmi_sim, monkeypatch):
    # A failure while moving the Research Object into place (e.g. disk full in _finalize,
    # or an IO/permission error on the move) must NOT discard the already-computed result.
    import picongpu.pypicongpu.runner as runner_mod

    def _raise(ro, save_to):
        # Only fail the "into place" call; let the finally-block cleanup (save_to=None)
        # remove the temp RO so it does not raise on the way out.
        if save_to is not None:
            raise OSError("simulated disk full while finalizing the Research Object")
        _orig_close_ro(ro, save_to)

    _orig_close_ro = runner_mod.close_ro
    monkeypatch.setattr(runner_mod, "close_ro", _raise)
    with _new_base() as base:
        runner = _build_probe_runner(picmi_sim, base)
        with rc_params.set_temporarily(provenance={"enabled": True}):
            out = runner.run()  # must not raise

        # The simulation result is returned even though the RO could not be moved into place.
        assert out is not None and isinstance(out, dict)
        # ...and the (not fully written) Research Object was not left in place.
        assert not runner.provenance_path.exists()


def test_provenance_string_false_disables(picmi_sim):
    # A string-typed flag must not silently defeat the opt-out (bool("false") is True).
    with _new_base() as base:
        runner = _build_probe_runner(picmi_sim, base)
        with rc_params.set_temporarily(provenance={"enabled": "false"}):
            out = runner.run()

        assert out is not None and isinstance(out, dict)
        assert not runner.provenance_path.exists()


def test_provenance_non_dict_table_does_not_raise(picmi_sim):
    # A non-dict value for the table must not raise inside run() (rc_params is free-form).
    with _new_base() as base:
        runner = _build_probe_runner(picmi_sim, base)
        with rc_params.set_temporarily(provenance="not-a-table"):
            out = runner.run()

        assert out is not None and isinstance(out, dict)
        # Falls back to the enabled default, so a Research Object is produced.
        assert runner.provenance_path.is_dir()


def _new_base():
    from contextlib import contextmanager

    @contextmanager
    def _ctx():
        with TemporaryDirectory() as d:
            yield Path(d)

    return _ctx()
