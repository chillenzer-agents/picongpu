"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
License: GPLv3+
"""

import sys

from picongpu.picmi import Cartesian3DGrid, ElectromagneticSolver, Simulation
from picongpu.pypicongpu.runner import Runner, STAGE_OUTPUTS, Stage
from pytest import fixture, raises

# Partial execution is delegated to cwltool: the runner only *generates* the
# correct cwltool invocation. ``--target <output>`` makes cwltool execute only
# the steps that contribute to that output (pruning the downstream stages);
# the persistent job store (``--cachedir``) is what makes a later invocation
# skip the already completed steps. These tests pin the generated invocation,
# i.e. the public API of the new behavior. They deliberately do not run CWL
# (nor render/generate a setup): the cwltool side is verified separately.


@fixture
def sim():
    number_of_cells = 32
    cell_size = 1
    return Simulation(
        time_step_size=17,
        max_steps=4,
        solver=ElectromagneticSolver(
            method="Yee",
            grid=Cartesian3DGrid(
                number_of_cells=[number_of_cells, number_of_cells, number_of_cells],
                lower_bound=[0, 0, 0],
                upper_bound=list(map(lambda x: number_of_cells * x, [cell_size, cell_size, cell_size])),
                # required, otherwise won't spawn
                lower_boundary_conditions=["open", "open", "periodic"],
                upper_boundary_conditions=["open", "open", "periodic"],
            ),
        ),
    )


@fixture
def runner(sim, tmp_path):
    # No generate(): generating a command line does not need a rendered setup.
    return Runner(sim=sim, setup_dir=tmp_path / "setup", run_dir=tmp_path / "run")


def targets(command):
    """The set of ``--target`` values in a cwltool command."""
    return {command[i + 1] for i, arg in enumerate(command) if arg == "--target"}


def test_default_run_asks_for_the_full_pipeline_outputs(runner):
    command = runner.run_command()
    # The default run is the full workflow: it asks cwltool for the collect
    # stage's outputs. Asking for them walks the whole DAG, so the default
    # behavior is unchanged (and the per-stage aliases stay out of the
    # run directory).
    assert targets(command) == set(STAGE_OUTPUTS[Stage.collect])
    assert command.count("--target") == len(STAGE_OUTPUTS[Stage.collect])


def test_default_run_invokes_cwltool_against_the_run_dir_and_job_store(runner):
    command = runner.run_command()
    assert command[:3] == [sys.executable, "-m", "cwltool"]
    assert "--outdir" in command
    assert command[command.index("--outdir") + 1] == str(runner.run_dir)
    assert "--cachedir" in command
    assert command[command.index("--cachedir") + 1] == str(runner.cwl_cachedir)
    assert command[-2:] == [str(runner.workflow_definition_path), str(runner.workflow_input_path)]


def test_up_to_build_requests_only_the_build_outputs(runner):
    assert targets(runner.run_command(up_to=Stage.build)) == set(STAGE_OUTPUTS[Stage.build])


def test_up_to_prepare_requests_only_the_prepare_outputs(runner):
    assert targets(runner.run_command(up_to="prepare")) == set(STAGE_OUTPUTS[Stage.prepare])


def test_up_to_submit_requests_all_submit_outputs(runner):
    assert targets(runner.run_command(up_to=Stage.submit)) == set(STAGE_OUTPUTS[Stage.submit])


def test_from_resumes_via_the_job_store(runner):
    # "resume from a stage" runs the full workflow against the persistent job
    # store: cwltool serves the already completed steps from the store and
    # recomputes the requested stage and everything after it.
    assert runner.run_command(from_=Stage.submit) == runner.run_command()


def test_combining_up_to_and_from_is_rejected(runner):
    with raises(ValueError, match="cannot combine up_to and from_"):
        runner.run_command(up_to=Stage.build, from_=Stage.submit)


def test_unknown_stage_is_rejected(runner):
    with raises(ValueError):
        runner.run_command(up_to="not-a-stage")
