"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
License: GPLv3+
"""

from picongpu.picmi import Cartesian3DGrid, ElectromagneticSolver, Simulation
from picongpu.pypicongpu.runner import Runner, STAGE_OUTPUTS, Stage
from pytest import fixture, raises

# Partial execution is delegated to cwltool, invoked in-process via its
# WorkflowFactory: the runner only *generates* the correct in-process
# invocation (`Runner.run_invocation()`), which asks cwltool for the top-level
# outputs of the requested stage (cwltool's `--target`). cwltool then executes
# exactly the steps contributing to those outputs (pruning the downstream
# stages); the persistent job store (the `--cachedir`) is what makes a later
# invocation skip the already completed steps. These tests pin the generated
# invocation, i.e. the public API of the new behavior. They deliberately do
# not run CWL (nor render/generate a setup): the cwltool side is verified
# separately.


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
    # No generate(): generating an invocation does not need a rendered setup.
    return Runner(sim=sim, setup_dir=tmp_path / "setup", run_dir=tmp_path / "run")


def targets(invocation):
    """The set of requested top-level output names of a cwltool invocation."""
    return set(invocation.target_outputs)


def test_default_run_asks_for_the_full_pipeline_outputs(runner):
    invocation = runner.run_invocation()
    # The default run is the full workflow: it asks cwltool for the collect
    # stage's outputs. Asking for them walks the whole DAG, so the default
    # behavior is unchanged (and the per-stage aliases stay out of the
    # run directory).
    assert targets(invocation) == set(STAGE_OUTPUTS[Stage.collect])
    assert len(invocation.target_outputs) == len(STAGE_OUTPUTS[Stage.collect])


def test_default_run_invokes_cwltool_in_process(runner):
    invocation = runner.run_invocation()
    # The invocation is executed in-process via the WorkflowFactory: it
    # targets the run directory as output directory and the persistent job
    # store as cache directory, and is bound to the workflow + job order file.
    assert invocation.workflow_path == runner.workflow_definition_path
    assert invocation.input_path == runner.workflow_input_path
    assert invocation.outdir == runner.run_dir
    assert invocation.cachedir == runner.cwl_cachedir


def test_up_to_build_requests_only_the_build_outputs(runner):
    assert targets(runner.run_invocation(up_to=Stage.build)) == set(STAGE_OUTPUTS[Stage.build])


def test_up_to_prepare_requests_only_the_prepare_outputs(runner):
    assert targets(runner.run_invocation(up_to="prepare")) == set(STAGE_OUTPUTS[Stage.prepare])


def test_up_to_submit_requests_all_submit_outputs(runner):
    assert targets(runner.run_invocation(up_to=Stage.submit)) == set(STAGE_OUTPUTS[Stage.submit])


def test_from_resumes_via_the_job_store(runner):
    # "resume from a stage" runs the full workflow against the persistent job
    # store: cwltool serves the already completed steps from the store and
    # recomputes the requested stage and everything after it.
    resume = runner.run_invocation(from_=Stage.submit)
    default = runner.run_invocation()
    assert (resume.workflow_path, resume.input_path, resume.outdir, resume.cachedir, resume.targets) == (
        default.workflow_path,
        default.input_path,
        default.outdir,
        default.cachedir,
        default.targets,
    )


def test_combining_up_to_and_from_is_rejected(runner):
    with raises(ValueError, match="cannot combine up_to and from_"):
        runner.run_invocation(up_to=Stage.build, from_=Stage.submit)


def test_unknown_stage_is_rejected(runner):
    with raises(ValueError):
        runner.run_invocation(up_to="not-a-stage")
