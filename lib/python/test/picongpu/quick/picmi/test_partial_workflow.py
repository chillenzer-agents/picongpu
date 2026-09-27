"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: opencode
License: GPLv3+
"""

import json
import shutil
from pathlib import Path

import yaml
from picongpu.picmi import Cartesian3DGrid, ElectromagneticSolver, Stage, Simulation
from picongpu.pypicongpu.runner import (
    DEFAULT_STAGE_PLAN,
    StageArtifactRef,
    StageStepSpec,
    StepOutputRef,
    WorkflowPrerequisiteError,
    WorkflowStageError,
)
from picongpu.templates import path as tpath
from pytest import fixture, raises


# Tiny echo replacements for the real CWL steps. They keep the same input
# names/types as the production steps (see templates/workflow/steps/*.cwl) so
# that the default stage plan can drive them, but only do file bookkeeping.
# The build step echoes the (optional) cmake argument into the "binary", so a
# changed build input visibly changes the artifact content.
ECHO_BUILD_CWL = """
cwlVersion: v1.2
class: CommandLineTool
label: "Build PIConGPU (test echo)"
requirements:
  InitialWorkDirRequirement:
    listing:
      - entryname: include
        entry: $(inputs.include_directory)
      - entryname: build.sh
        entry: $(inputs.script)
# note: with `bash -c`, the first argument after the command string is $0,
# so CWL input position 4 (cmake) arrives as $3 here
baseCommand: ["bash", "-c", "mkdir -p bin && echo built-${3:-default} > bin/picongpu"]
inputs:
  include_directory:
    type: Directory
    inputBinding:
      position: 1
  script:
    type: File
    inputBinding:
      position: 2
  jobs:
    type: int?
    inputBinding:
      position: 3
  cmake:
    type: string?
    inputBinding:
      position: 4
  preset:
    type: int?
    inputBinding:
      position: 5
  force:
    type: boolean
    inputBinding:
      position: 6
  cmake_build_system:
    type: string?
    inputBinding:
      position: 7
outputs:
  bin_directory:
    type: Directory
    outputBinding:
      glob: "bin"
"""

ECHO_PREPARE_SUBMISSION_CWL = """
cwlVersion: v1.2
class: CommandLineTool
label: "Prepare submission (test echo)"
requirements:
  InitialWorkDirRequirement:
    listing:
      - entryname: etc
        entry: $(inputs.etc_directory)
      - entryname: prepare_submission.sh
        entry: $(inputs.script)
baseCommand: ["bash", "-c", "mkdir -p run_dir/tbg && echo prepared > run_dir/tbg/marker.txt"]
inputs:
  etc_directory:
    type: Directory
  script:
    type: File
  template_file:
    type: string?
  cfg_file:
    type: string
  overwrite_vars:
    type: string?
  force:
    type: boolean
outputs:
  tbg_directory:
    type: Directory
    outputBinding:
      glob: "run_dir/tbg"
"""

ECHO_SUBMIT_CWL = """
cwlVersion: v1.2
class: CommandLineTool
label: "Submit (test echo)"
requirements:
  InitialWorkDirRequirement:
    listing:
      - entryname: submit.sh
        entry: $(inputs.script)
      - entryname: bin
        entry: $(inputs.bin_directory)
      - entryname: tbg_link
        entry: $(inputs.tbg_link)
      - entryname: etc
        entry: $(inputs.etc_directory)
baseCommand: ["bash", "-c", "cp -rL tbg_link tbg && cp -rL bin/picongpu tbg/bin_from_build && \
echo fake-job-42 > submission_information.txt && \
echo 'ln -s /stable/simOutput $1' > link_results.sh && chmod +x link_results.sh"]
inputs:
  script:
    type: File
  bin_directory:
    type: Directory
  tbg_link:
    type: Directory
  etc_directory:
    type: Directory
  submit_system:
    type: string?
outputs:
  submission_information:
    type: File
    outputBinding:
      glob: "submission_information.txt"
  link_results_script:
    type: File
    outputBinding:
      glob: "link_results.sh"
  tbg_directory:
    type: Directory
    outputBinding:
      glob: "tbg"
"""

ECHO_ORGANIZE_OUTPUT_CWL = """
cwlVersion: v1.2
class: CommandLineTool
label: "Organize output (test echo)"
requirements:
  InitialWorkDirRequirement:
    listing:
      - entryname: organize_output.sh
        entry: $(inputs.script)
      - entryname: project_path
        entry: $(inputs.project_path)
      - entryname: bin
        entry: $(inputs.bin_directory)
      - entryname: tbg
        entry: $(inputs.tbg_directory)
      - entryname: submission_information
        entry: $(inputs.submission_information)
      - entryname: link_results
        entry: $(inputs.link_results_script)
baseCommand: ["bash", "-c", "cp -rL project_path input && cp -rL bin input/bin && \
mv submission_information submission_information.txt && mv link_results link_results.sh"]
inputs:
  script:
    type: File
  project_path:
    type: Directory
  bin_directory:
    type: Directory
  tbg_directory:
    type: Directory
  submission_information:
    type: File
  link_results_script:
    type: File
outputs:
  input_directory:
    type: Directory
    outputBinding:
      glob: "input"
  tbg_directory:
    type: Directory
    outputBinding:
      glob: "tbg"
  submission_information:
    type: File
    outputBinding:
      glob: "submission_information.txt"
  link_results_script:
    type: File
    outputBinding:
      glob: "link_results.sh"
"""

# An extra CWL step that a "future" workflow might insert inside the submit
# stage (e.g. uploading files to a cluster before submitting).
ECHO_UPLOAD_CWL = """
cwlVersion: v1.2
class: CommandLineTool
label: "Upload (test echo, future step)"
requirements:
  InitialWorkDirRequirement:
    listing:
      - entryname: tbg_link
        entry: $(inputs.tbg_link)
baseCommand: ["bash", "-c", "cp -rL tbg_link uploaded && echo uploaded > uploaded/upload.log"]
inputs:
  tbg_link:
    type: Directory
outputs:
  uploaded:
    type: Directory
    outputBinding:
      glob: "uploaded"
"""


DUMMY_STEPS = {
    "build.cwl": ECHO_BUILD_CWL,
    "prepare_submission.cwl": ECHO_PREPARE_SUBMISSION_CWL,
    "submit.cwl": ECHO_SUBMIT_CWL,
    "organize_output.cwl": ECHO_ORGANIZE_OUTPUT_CWL,
}


def install_dummy_workflow(runner, extra_steps=None):
    """Replace the generated workflow steps with fast echo versions."""
    steps_dir = runner.workflow_dir_path / "steps"
    steps = dict(DUMMY_STEPS)
    if extra_steps:
        steps.update(extra_steps)
    for name, content in steps.items():
        (steps_dir / name).write_text(content)


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
def runner(sim):
    r = sim.picongpu_get_runner()
    r.generate()
    install_dummy_workflow(r)
    return r


def load_state(runner):
    if not runner.workflow_state_path.is_file():
        return {"stages": {}}
    with runner.workflow_state_path.open("r") as file:
        return json.load(file)


def completed_stages(runner):
    return set(load_state(runner)["stages"])


def set_workflow_input(runner, key, value):
    with runner.workflow_input_path.open("r") as file:
        workflow_input = json.load(file)
    workflow_input[key] = value
    with runner.workflow_input_path.open("w") as file:
        json.dump(workflow_input, file, indent=4)


def test_full_run_default_and_state(runner, sim):
    # Default (no arguments) runs the whole pipeline; progress is recorded
    # in the stage-keyed state file.
    artifacts = runner.run_range()

    # the default full run returns the recorded artifacts of the last stage
    # (the same shape as the per-step path), not the raw workflow outputs
    assert set(artifacts) == {
        "input_directory",
        "tbg_directory",
        "submission_information",
        "link_results_script",
    }
    for artifact in artifacts.values():
        assert set(artifact) == {"class", "location"}

    run_dir = runner.run_dir
    assert (run_dir / "input" / "bin" / "picongpu").read_text() == "built-default\n"
    assert (run_dir / "tbg" / "marker.txt").read_text() == "prepared\n"
    assert (run_dir / "tbg" / "bin_from_build").read_text() == "built-default\n"
    assert (run_dir / "submission_information.txt").read_text() == "fake-job-42\n"
    assert "ln -s /stable/simOutput $1" in (run_dir / "link_results.sh").read_text()

    state = load_state(runner)
    assert state["version"] == 1
    assert set(state["stages"]) == {stage.value for stage in Stage}
    for entry in state["stages"].values():
        assert entry["status"] == "completed"
        assert entry["artifacts"]
        for artifact in entry["artifacts"].values():
            assert set(artifact) == {"class", "location"}
            assert artifact["class"] in ("File", "Directory")
    # the state is keyed by stages, never by CWL step names
    assert "build_step" not in json.dumps(state)


def test_second_run_skips_completed(runner, sim):
    sim.picongpu_run()
    first = load_state(runner)

    # an up-to-date re-run executes no stage at all and returns None
    assert runner.run_range() is None

    second = load_state(runner)
    assert first == second, "a second run must not redo (or even rewrite) completed stages"


def test_range_build_only(runner):
    runner.run_range(up_to=Stage.build)

    state = load_state(runner)
    assert set(state["stages"]) == {Stage.build.value}
    bin_directory = state["stages"][Stage.build.value]["artifacts"]["bin_directory"]
    assert ".stage_outputs" in bin_directory["location"]
    assert (Path(bin_directory["location"]) / "picongpu").read_text() == "built-default\n"


def test_incremental_stage_scenario(runner):
    # build only, then prepare only, then submit only, then collect only;
    # each run skips the stages that are already completed.
    runner.run_range(up_to=Stage.build)
    assert completed_stages(runner) == {Stage.build.value}

    runner.run_range(up_to=Stage.prepare)
    assert completed_stages(runner) == {Stage.build.value, Stage.prepare.value}

    runner.run_range(from_=Stage.submit, up_to=Stage.submit)
    assert completed_stages(runner) == {Stage.build.value, Stage.prepare.value, Stage.submit.value}

    runner.run_range(from_=Stage.collect)
    assert completed_stages(runner) == {stage.value for stage in Stage}

    # the final artifacts end up in the same place as a full run, and the
    # artifacts of the earlier stages flowed through the stages
    run_dir = runner.run_dir
    assert (run_dir / "input" / "bin" / "picongpu").read_text() == "built-default\n"
    assert (run_dir / "tbg" / "marker.txt").read_text() == "prepared\n"
    assert (run_dir / "tbg" / "bin_from_build").read_text() == "built-default\n"
    assert (run_dir / "submission_information.txt").read_text() == "fake-job-42\n"


def test_missing_prerequisite_is_an_error(runner):
    # starting at a stage whose prerequisites never ran must fail, not
    # silently (re)run them
    with raises(WorkflowPrerequisiteError, match="build, prepare"):
        runner.run_range(from_=Stage.submit)
    assert completed_stages(runner) == set()

    with raises(ValueError, match="after up_to"):
        runner.run_range(from_=Stage.collect, up_to=Stage.build)


def test_step_file_renamed_raises_workflow_stage_error(runner):
    # a missing (renamed) step file is a cwltool load/validation failure; the
    # documented error contract is WorkflowStageError, not a raw cwltool exception
    steps_dir = runner.workflow_dir_path / "steps"
    shutil.move(str(steps_dir / "build.cwl"), str(steps_dir / "compile.cwl"))

    with raises(WorkflowStageError, match="loading/running CWL step"):
        runner.run_range(up_to=Stage.build)


def test_unknown_state_version_is_ignored(runner):
    # a state file with an unknown version must not be trusted: it is
    # treated as empty, the stage is re-run, and the state is re-recorded
    # with the supported version (had the foreign state been trusted, the
    # stage would have been skipped and the file would still say version 99)
    runner.run_range(up_to=Stage.build)
    state = json.loads(runner.workflow_state_path.read_text())
    state["version"] = 99
    runner.workflow_state_path.write_text(json.dumps(state))

    runner.run_range(up_to=Stage.build)

    state = json.loads(runner.workflow_state_path.read_text())
    assert state["version"] == 1
    assert state["stages"][Stage.build.value]["status"] == "completed"


def test_force_stage_invalidates_dependents(runner):
    runner.run_range()
    state = load_state(runner)
    prepare_updated_before = state["stages"][Stage.prepare.value]["updated_at"]

    # change the build input and force a rebuild: the build and everything
    # downstream of it (submit, collect) is re-run, prepare is skipped
    set_workflow_input(runner, "build_cmake", "v2")
    runner.run_range(up_to=Stage.submit, force=Stage.build)

    state = load_state(runner)
    bin_directory = state["stages"][Stage.build.value]["artifacts"]["bin_directory"]["location"]
    assert ".stage_outputs" in bin_directory
    assert (Path(bin_directory) / "picongpu").read_text() == "built-v2\n"
    assert state["stages"][Stage.prepare.value]["updated_at"] == prepare_updated_before
    assert state["stages"][Stage.prepare.value]["status"] == "completed"
    assert state["stages"][Stage.submit.value]["status"] == "completed"
    assert state["stages"][Stage.submit.value]["updated_at"] != state["stages"][Stage.build.value]["updated_at"]
    # collect is outside the range, but it is now stale
    assert state["stages"][Stage.collect.value]["status"] == "invalidated"


def test_flags_after_generation_are_rejected(runner, sim):
    runner.run_range()
    state_before = load_state(runner)

    # flags can only be set at generation time; after that they must not
    # silently change the inputs of already completed stages
    with raises(ValueError, match="already generated"):
        sim.picongpu_run(jobs=2)

    assert load_state(runner) == state_before


def test_input_change_invalidates_completed_stages(runner):
    # editing workflow/input.yaml after a completed run must not be a silent
    # no-op: the stage whose inputs changed (and the stages that depend on it)
    # is re-run, while stages with unchanged inputs are still skipped.
    runner.run_range()
    state = load_state(runner)
    build_digest = state["stages"][Stage.build.value]["inputs_digest"]
    assert build_digest
    prepare_updated_at = state["stages"][Stage.prepare.value]["updated_at"]

    # the user edits a workflow input that only the build stage consumes
    set_workflow_input(runner, "build_cmake", "v2")
    runner.run_range()

    state = load_state(runner)
    for stage in Stage:
        assert state["stages"][stage.value]["status"] == "completed"
    assert state["stages"][Stage.build.value]["inputs_digest"] != build_digest
    # prepare was not affected by the input change and was skipped
    assert state["stages"][Stage.prepare.value]["updated_at"] == prepare_updated_at
    # the stale build and its dependents (submit, collect) were re-run, so
    # the new input is visible in the final artifacts (not silently skipped)
    run_dir = runner.run_dir
    assert (run_dir / "input" / "bin" / "picongpu").read_text() == "built-v2\n"
    assert (run_dir / "tbg" / "bin_from_build").read_text() == "built-v2\n"


def test_default_plan_matches_workflow_template():
    # The stage plan is the single place that knows the current workflow.cwl
    # layout, but the per-step path never reads workflow.cwl -- so drift
    # (a renamed step file, a renamed input, an added step) would make full
    # and partial runs silently diverge. This test pins the default plan to
    # the real template.
    workflow = yaml.safe_load((tpath() / "workflow" / "workflow.cwl").read_text())
    workflow_steps = workflow["steps"]
    workflow_inputs = set(workflow["inputs"])
    all_plan_steps = [(stage, spec) for stage, s in DEFAULT_STAGE_PLAN.stages.items() for spec in s.steps]

    def plan_step_of(run_file: str):
        matches = [(stage, spec) for stage, spec in all_plan_steps if spec.run == run_file]
        assert len(matches) == 1, f"exactly one plan step must run {run_file!r}, found {len(matches)}"
        return matches[0]

    for step_id, step in workflow_steps.items():
        # every workflow step is covered by exactly one plan step (same file)
        stage, spec = plan_step_of(step["run"])

        # the plan step offers exactly the workflow step's inputs
        assert set(spec.inputs) == set(step["in"]), (
            f"plan step {spec.step!r} input names differ from workflow step {step_id!r}: "
            f"{sorted(set(spec.inputs) ^ set(step['in']))}"
        )
        for input_name, source in spec.inputs.items():
            workflow_source = step["in"][input_name]
            if "/" not in str(workflow_source):
                # sourced from a workflow input
                assert source == workflow_source, (
                    f"workflow step {step_id!r} input {input_name!r} comes from {workflow_source!r} "
                    f"in the workflow but from {source!r} in the plan"
                )
                assert source in workflow_inputs, f"workflow input {source!r} is not defined in workflow.cwl"
            else:
                producer_id, output = str(workflow_source).split("/", 1)
                producer_stage, producer_spec = plan_step_of(workflow_steps[producer_id]["run"])
                assert output in producer_spec.outputs.values(), (
                    f"workflow step {step_id!r} consumes {workflow_source!r}, but plan step "
                    f"{producer_spec.step!r} records no such output"
                )
                if isinstance(source, StageArtifactRef):
                    assert source.stage == producer_stage and source.artifact == output, (
                        f"plan step {spec.step!r} input {input_name!r} is {source!r}, but the workflow "
                        f"takes {workflow_source!r} (stage {producer_stage.value!r})"
                    )
                elif isinstance(source, StepOutputRef):
                    assert producer_stage == stage and source.step == producer_id and source.output == output, (
                        f"plan step {spec.step!r} input {input_name!r} is {source!r}, but the workflow "
                        f"takes {workflow_source!r}"
                    )
                else:
                    raise AssertionError(
                        f"plan step {spec.step!r} input {input_name!r} is {source!r}, expected a "
                        f"StageArtifactRef or StepOutputRef for the workflow source {workflow_source!r}"
                    )
        # every output of the workflow step is recorded by the plan step
        missing = set(step["out"]) - set(spec.outputs.values())
        assert not missing, (
            f"workflow step {step_id!r} outputs {sorted(missing)} are not recorded by plan step {spec.step!r}"
        )

    # and the plan does not reference step files that are not workflow steps
    assert {spec.run for _, spec in all_plan_steps} == {step["run"] for step in workflow_steps.values()}


def future_stage_plan():
    """A "future" plan where the submit stage gained an extra (upload) step."""
    plan = DEFAULT_STAGE_PLAN.model_copy(deep=True)
    plan.stages[Stage.submit].steps = [
        StageStepSpec(
            step="upload_step",
            run="steps/upload.cwl",
            inputs={"tbg_link": StageArtifactRef(stage=Stage.prepare, artifact="tbg_directory")},
            outputs={"uploaded": "uploaded"},
        ),
        StageStepSpec(
            step="submit_step",
            run="steps/submit.cwl",
            inputs={
                "script": "submission_script",
                "bin_directory": StageArtifactRef(stage=Stage.build, artifact="bin_directory"),
                "etc_directory": "run_etc_directory",
                "tbg_link": StepOutputRef(step="upload_step", output="uploaded"),
                "submit_system": "run_submit_system",
            },
            outputs={
                "submission_information": "submission_information",
                "link_results_script": "link_results_script",
                "tbg_directory": "tbg_directory",
            },
        ),
    ]
    return plan


def mutate_workflow_cwl(runner) -> str:
    """
    Simulate a "future" workflow.cwl in the generated setup: the build step
    id is renamed and a new upload step is inserted ahead of the submit step.

    The per-step path never reads workflow.cwl; the point is that the stage
    API keeps working while the workflow file drifts (the plan is updated
    accordingly, as a maintainer would do).
    """
    wf_path = runner.workflow_dir_path / "workflow.cwl"
    text = wf_path.read_text()
    text = text.replace("build_step", "compile_step")
    text = text.replace(
        "  submit_step:\n",
        (
            "  upload_step:\n"
            "    run: steps/upload.cwl\n"
            "    in:\n"
            "      tbg_link: prepare_submission_step/tbg_directory\n"
            "    out: [uploaded]\n"
            "  submit_step:\n"
        ),
    )
    wf_path.write_text(text)
    return text


def test_stability_future_workflow(runner):
    # A future workflow (a mutated scratch workflow.cwl: a renamed step id
    # and a step inserted inside the submit stage) with a correspondingly
    # updated plan must keep the public API (stage names, ranges, state
    # file) unchanged.
    install_dummy_workflow(runner, extra_steps={"upload.cwl": ECHO_UPLOAD_CWL})
    text = mutate_workflow_cwl(runner)
    assert "compile_step" in text and "upload_step" in text, "the scratch workflow.cwl must be mutated"
    runner.stage_plan = future_stage_plan()

    runner.run_range(up_to=Stage.prepare)
    assert completed_stages(runner) == {Stage.build.value, Stage.prepare.value}

    runner.run_range(up_to=Stage.submit)
    state = load_state(runner)
    assert set(state["stages"]) == {Stage.build.value, Stage.prepare.value, Stage.submit.value}
    tbg_directory = state["stages"][Stage.submit.value]["artifacts"]["tbg_directory"]["location"]
    # the submit step consumed the upload step's output (in-stage wiring)
    assert (Path(tbg_directory) / "upload.log").read_text() == "uploaded\n"
    assert (Path(tbg_directory) / "bin_from_build").read_text() == "built-default\n"
    assert (Path(tbg_directory) / "marker.txt").read_text() == "prepared\n"
    # the state is still keyed by stages, not by the steps inside them
    assert "upload_step" not in json.dumps(state)

    runner.run_range(from_=Stage.collect)
    assert completed_stages(runner) == {stage.value for stage in Stage}
    run_dir = runner.run_dir
    assert (run_dir / "tbg" / "upload.log").exists()
    assert (run_dir / "input" / "bin" / "picongpu").read_text() == "built-default\n"
