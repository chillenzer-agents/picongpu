"""
This file is part of PIConGPU.
Copyright 2021-2024 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre, Richard Pausch
License: GPLv3+
"""

import datetime
import enum
import hashlib
import json
import logging
import shutil
import tempfile
import urllib.parse
from importlib.util import module_from_spec, spec_from_file_location
from os import chmod
from pathlib import Path
from shutil import copy2, copytree
from typing import Annotated, Sequence

from cwltool.context import RuntimeContext
from cwltool.factory import Factory as WorkflowFactory
from cwltool.factory import WorkflowStatus
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


class PicBuildFlags(BaseModel):
    # We explicitly disallow the some shorthands like `-c`, `-t`, ...
    # because they overlap with tbg flags and could thus lead to confusion.
    jobs: int | None = Field(
        # NOTE: This flat `build_jobs` config key is not the same as the
        # nested `[dependencies] jobs` setting (compile parallelism for
        # dependency builds) -- config docs should keep the two distinct.
        default_factory=lambda: rc_params.get("build_jobs", 4),
        description="allow N jobs at once; infinite jobs if set to None",
        validation_alias=AliasChoices("jobs", "j"),
        # `default_factory` results are not validated by default; validate so a
        # mis-typed `build_jobs` in picongpurc.toml is caught like an explicit
        # `PicBuildFlags(jobs=...)` argument would be.
        validate_default=True,
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


class Stage(str, enum.Enum):
    """
    Stable, user-facing execution stages of the PIConGPU workflow.

    Stages are the milestones of a simulation run. They are deliberately
    coarse-grained and decoupled from the individual CWL steps of
    ``workflow.cwl`` (whose number and names may change over time, e.g. when
    remote-execution steps are added). A stage may be implemented by one or
    several CWL steps; the mapping lives in a :class:`StagePlan` inside the
    runner, and both the public API and the persisted workflow state speak
    only in stages, never in CWL step names.

    The stages in execution order are:

    - ``build``: compile the simulation executable (pic-build)
    - ``prepare``: prepare the submission (tbg)
    - ``submit``: launch the simulation job on the batch system
    - ``collect``: organize the results into the run directory
    """

    build = "build"
    prepare = "prepare"
    submit = "submit"
    collect = "collect"


class StageArtifactRef(BaseModel):
    """Reference to an artifact produced by an earlier, completed stage."""

    stage: Stage
    artifact: str


class StepOutputRef(BaseModel):
    """Reference to an output of a preceding step within the same stage."""

    step: str
    output: str


class StageStepSpec(BaseModel):
    """
    How to run one CWL step of the workflow as part of a stage.

    ``inputs`` maps the step's input parameters to their source: a bare
    string names a workflow input (from ``workflow/input.yaml``), a
    :class:`StageArtifactRef` takes the value from a completed stage's
    recorded artifact, and a :class:`StepOutputRef` wires an output of a
    preceding step of the same stage.

    ``outputs`` maps stage artifact names to the step's output parameters;
    the resulting artifact locations are recorded in the workflow state.
    """

    step: str
    run: str
    inputs: dict[str, str | StageArtifactRef | StepOutputRef]
    outputs: dict[str, str] = {}


class StageSpec(BaseModel):
    """A stage: the stages it depends on and the CWL steps that implement it."""

    name: Stage
    depends_on: tuple[Stage, ...] = ()
    steps: list[StageStepSpec]


class StagePlan(BaseModel):
    """
    The stage -> CWL step adapter.

    This is the single place in the code base that knows the current layout
    of ``workflow.cwl``. ``order`` is the execution (topological) order of
    the stages; ``stages`` maps each stage to its spec.
    """

    order: tuple[Stage, ...]
    stages: dict[Stage, StageSpec]

    def __getitem__(self, stage: Stage | str) -> StageSpec:
        return self.stages[Stage(stage)]


# The current mapping of the stable stages onto the CWL steps of
# workflow.cwl. If steps are added, removed, or reorganised, only this
# mapping (and the workflow templates) need to change, not the public API.
DEFAULT_STAGE_PLAN = StagePlan(
    order=(Stage.build, Stage.prepare, Stage.submit, Stage.collect),
    stages={
        Stage.build: StageSpec(
            name=Stage.build,
            steps=[
                StageStepSpec(
                    step="build_step",
                    run="steps/build.cwl",
                    inputs={
                        "include_directory": "build_include_directory",
                        "script": "build_script",
                        "jobs": "build_jobs",
                        "cmake": "build_cmake",
                        "preset": "build_preset",
                        "force": "build_force",
                        "cmake_build_system": "build_cmake_build_system",
                    },
                    outputs={"bin_directory": "bin_directory"},
                )
            ],
        ),
        Stage.prepare: StageSpec(
            name=Stage.prepare,
            steps=[
                StageStepSpec(
                    step="prepare_submission_step",
                    run="steps/prepare_submission.cwl",
                    inputs={
                        "etc_directory": "run_etc_directory",
                        "script": "prepare_submission_script",
                        "cfg_file": "run_cfg_file",
                        "overwrite_vars": "run_overwrite_vars",
                        "template_file": "run_template_file",
                        "force": "run_force",
                    },
                    outputs={"tbg_directory": "tbg_directory"},
                )
            ],
        ),
        Stage.submit: StageSpec(
            name=Stage.submit,
            depends_on=(Stage.build, Stage.prepare),
            steps=[
                StageStepSpec(
                    step="submit_step",
                    run="steps/submit.cwl",
                    inputs={
                        "script": "submission_script",
                        "bin_directory": StageArtifactRef(stage=Stage.build, artifact="bin_directory"),
                        "etc_directory": "run_etc_directory",
                        "tbg_link": StageArtifactRef(stage=Stage.prepare, artifact="tbg_directory"),
                        "submit_system": "run_submit_system",
                        "destination_path": "destination_path",
                    },
                    outputs={
                        "submission_information": "submission_information",
                        "link_results_script": "link_results_script",
                        "tbg_directory": "tbg_directory",
                    },
                )
            ],
        ),
        Stage.collect: StageSpec(
            name=Stage.collect,
            depends_on=(Stage.build, Stage.submit),
            steps=[
                StageStepSpec(
                    step="organize_output_step",
                    run="steps/organize_output.cwl",
                    inputs={
                        "script": "organize_output_script",
                        "project_path": "run_project_path",
                        "bin_directory": StageArtifactRef(stage=Stage.build, artifact="bin_directory"),
                        "tbg_directory": StageArtifactRef(stage=Stage.submit, artifact="tbg_directory"),
                        "submission_information": StageArtifactRef(
                            stage=Stage.submit, artifact="submission_information"
                        ),
                        "link_results_script": StageArtifactRef(stage=Stage.submit, artifact="link_results_script"),
                    },
                    outputs={
                        "input_directory": "input_directory",
                        "tbg_directory": "tbg_directory",
                        "submission_information": "submission_information",
                        "link_results_script": "link_results_script",
                    },
                )
            ],
        ),
    },
)


class WorkflowStageError(RuntimeError):
    """A stage failed to execute."""


class WorkflowPrerequisiteError(RuntimeError):
    """A stage was requested whose prerequisites are not completed."""


class StageStatus(str, enum.Enum):
    running = "running"
    completed = "completed"
    failed = "failed"
    invalidated = "invalidated"


class StageState(BaseModel):
    status: StageStatus
    updated_at: datetime.datetime | None = None
    artifacts: dict[str, dict[str, str]] = {}
    inputs_digest: str | None = None


class WorkflowState(BaseModel):
    """
    Persisted, stage-keyed state of the workflow, stored in
    ``run_dir/.workflow_state.json``.

    Only stage names ever appear in this file (never CWL step names), so
    reorganising the workflow steps does not invalidate the state.
    Artifacts are stored as reduced CWL file objects (``class`` +
    ``location``) so they can be re-staged as inputs of later steps.
    """

    version: int = 1
    updated_at: datetime.datetime | None = None
    stages: dict[Stage, StageState] = {}

    @property
    def completed(self) -> set[Stage]:
        return {stage for stage, entry in self.stages.items() if entry.status is StageStatus.completed}


def cwl_location_to_path(location: str) -> Path:
    """Convert a cwltool file location (file:// URI or plain path) to a local path."""
    if location.startswith("file://"):
        return Path(urllib.parse.unquote(urllib.parse.urlparse(location).path))
    return Path(location)


def reduce_cwl_file(file: dict) -> dict[str, str]:
    """Keep only what is needed to re-stage a cwltool File/Directory output as an input."""
    return {"class": file["class"], "location": str(cwl_location_to_path(file["location"]))}


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
    stage_plan: StagePlan = Field(default_factory=lambda: DEFAULT_STAGE_PLAN)

    def _log_dirs(self):
        """print human-readble list of paths to log"""
        logging.info(" template dir: {}".format(self.template_dir))
        logging.info("    setup dir: {}".format(self.setup_dir))
        logging.info("      run dir: {}".format(self.run_dir))

    def _render_templates(self, exist_ok=False):
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
        Renderer.render_directory(Renderer.get_context_preprocessed(context), str(self.setup_dir), exist_ok=exist_ok)

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
    def workflow_state_path(self):
        return self.run_dir / ".workflow_state.json"

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
                        # This step runs in isolation: its working directory is
                        # cwltool's per-step job cache dir, so resolve
                        # TBG_dstPath/--chdir to that directory (its own pwd).
                        # The step must not reach outside itself; the final run
                        # directory is made to look self-contained later, by the
                        # organize_output step stripping the cache reference.
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
        copytree(
            core.path("etc") / f"picongpu/{preset}",
            self.setup_dir / f"etc/picongpu/{preset}",
            dirs_exist_ok=exist_ok,
        )
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

        self._render_templates(exist_ok=exist_ok)

        self.generate_workflow_input(
            build_flags=PicBuildFlags(**flags),
            run_flags=TBGFlags(project_path=self.setup_dir, **flags),
        )
        self.cwl_cachedir.mkdir(parents=True, exist_ok=True)

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

    # ------------------------------------------------------------------
    # Partial execution: stages, state, and stage ranges
    # ------------------------------------------------------------------

    def _load_workflow_state(self) -> WorkflowState:
        if not self.workflow_state_path.is_file():
            return WorkflowState()
        try:
            with self.workflow_state_path.open("r") as file:
                state = WorkflowState.model_validate(json.load(file))
        except (OSError, ValueError) as error:
            logging.warning(
                "could not read workflow state %s: %s; starting with an empty state", self.workflow_state_path, error
            )
            return WorkflowState()
        if state.version != 1:
            # version 1 is the only format this runner writes and reads; an
            # unknown version is ignored (treated as empty) rather than
            # guessed at -- a future format change starts from a clean state
            logging.warning(
                "workflow state %s has version %s, but this runner only supports version 1; "
                "the recorded progress is ignored",
                self.workflow_state_path,
                state.version,
            )
            return WorkflowState()
        return state

    def _save_workflow_state(self, state: WorkflowState):
        state.updated_at = datetime.datetime.now()
        tmp_path = self.workflow_state_path.with_suffix(".json.tmp")
        with tmp_path.open("w") as file:
            json.dump(state.model_dump(mode="json"), file, indent=4)
        tmp_path.replace(self.workflow_state_path)

    def reset_workflow_state(self) -> None:
        """Forget all recorded stage progress (e.g. because the inputs changed)."""
        self.workflow_state_path.unlink(missing_ok=True)

    @staticmethod
    def _resolve_force(force, plan: StagePlan) -> set[Stage]:
        if not force:
            return set()
        if force is True:
            return set(plan.order)
        stages = [Stage(stage) for stage in force] if isinstance(force, (list, tuple)) else [Stage(force)]
        known = {stage.value for stage in plan.order}
        unknown = sorted({stage.value for stage in stages} - known)
        if unknown:
            raise ValueError(
                f"unknown stage(s) {unknown}; known stages in execution order: {[s.value for s in plan.order]}"
            )
        return set(stages)

    @staticmethod
    def _invalidated_dependents(forced: set[Stage], plan: StagePlan) -> set[Stage]:
        """A forced stage invalidates itself and everything that depends on it."""
        dependents: dict[Stage, set[Stage]] = {stage: set() for stage in plan.order}
        for stage in plan.order:
            for dependency in plan[stage].depends_on:
                dependents[dependency].add(stage)
        invalidated = set(forced)
        queue = list(forced)
        while queue:
            for dependent in dependents[queue.pop()]:
                if dependent not in invalidated:
                    invalidated.add(dependent)
                    queue.append(dependent)
        return invalidated

    def _stage_inputs_digest(self, stage: Stage) -> str:
        """
        SHA-256 digest of the workflow inputs consumed by a stage.

        ``workflow/input.yaml`` is a plain file the user may edit at any time
        (the ``build_``/``run_`` prefixed entries exist precisely to run the
        steps individually), and nothing else on disk reflects such an edit.
        Recording a digest per stage lets a re-run detect that the inputs of
        a completed stage changed, instead of silently skipping it and
        reusing stale artifacts.
        """
        spec = self.stage_plan[stage]
        with self.workflow_input_path.open("r") as file:
            workflow_inputs = json.load(file)
        consumed = {
            input_name: workflow_inputs[source]
            for step_spec in spec.steps
            for input_name, source in step_spec.inputs.items()
            if isinstance(source, str) and source in workflow_inputs
        }
        return hashlib.sha256(json.dumps(consumed, sort_keys=True).encode()).hexdigest()

    def _record_full_run(self, state: WorkflowState, outputs: dict) -> None:
        """
        Record the stages as completed after a full single-invocation workflow run.

        The workflow's final outputs are the stable, organized artifacts in the
        run directory. The intermediate stages' outputs are only reachable
        through them (e.g. the built binaries are part of the organized input
        directory, cf. organize_output.sh), so they are recorded with the
        stable locations they have there.
        """

        def reduced(parameter: str) -> dict[str, str] | None:
            value = outputs.get(parameter)
            if isinstance(value, dict) and "location" in value and value.get("class") in ("File", "Directory"):
                return reduce_cwl_file(value)
            return None

        input_directory = reduced("input_directory")
        tbg_directory = reduced("tbg_directory")
        submission_information = reduced("submission_information")
        link_results_script = reduced("link_results_script")

        artifacts = {
            Stage.collect: {
                "input_directory": input_directory,
                "tbg_directory": tbg_directory,
                "submission_information": submission_information,
                "link_results_script": link_results_script,
            },
            Stage.submit: {
                "tbg_directory": tbg_directory,
                "submission_information": submission_information,
                "link_results_script": link_results_script,
            },
            Stage.prepare: {"tbg_directory": tbg_directory},
            Stage.build: {"bin_directory": None},
        }
        if input_directory is not None:
            # organize_output.sh copies the built binaries into input/bin
            artifacts[Stage.build]["bin_directory"] = {
                "class": "Directory",
                "location": str(Path(input_directory["location"]) / "bin"),
            }

        now = datetime.datetime.now()
        for stage, stage_artifacts in artifacts.items():
            clean = {name: value for name, value in stage_artifacts.items() if value is not None}
            if clean:
                state.stages[stage] = StageState(
                    status=StageStatus.completed,
                    updated_at=now,
                    artifacts=clean,
                    inputs_digest=self._stage_inputs_digest(stage),
                )
        self._save_workflow_state(state)

    def _stage_outdir(self, stage: Stage, step_index: int) -> Path:
        # The final stage's last step writes its outputs directly into the run
        # directory, exactly where the full workflow places them. The other
        # steps write to private, numbered subdirectories (no CWL step names,
        # so the on-disk layout survives step reorganisation, like the state).
        spec = self.stage_plan[stage]
        if stage is self.stage_plan.order[-1] and step_index == len(spec.steps) - 1:
            return self.run_dir
        return self.run_dir / ".stage_outputs" / stage.value / f"step-{step_index + 1}"

    def _run_cwl_step(self, step_path: Path, inputs: dict, outdir: Path) -> dict:
        outdir.mkdir(parents=True, exist_ok=True)
        self.cwl_cachedir.mkdir(parents=True, exist_ok=True)
        try:
            return (
                WorkflowFactory(
                    runtime_context=RuntimeContext(
                        kwargs={
                            "outdir": str(outdir),
                            "rm_tmpdir": False,
                            "move_outputs": "copy",
                            # No job cache for per-step runs: the stage state (not the
                            # job cache) decides what runs, and the job cache key does
                            # not cover Directory contents -- a re-run stage that
                            # regenerates an artifact directory in place would otherwise
                            # serve its dependents stale cached outputs. The legacy
                            # single-invocation full run (run()) keeps the shared cache.
                            "cachedir": None,
                            "preserve_entire_environment": True,
                        }
                    )
                ).make(str(step_path))(**inputs)
                or {}
            )
        except WorkflowStatus as error:
            raise WorkflowStageError(f"running CWL step {step_path.name} failed: {error}") from error
        except Exception as error:
            # cwltool load/validation failures (e.g. a renamed or missing step
            # file) surface here; wrap them so stage execution has a single
            # documented error type
            raise WorkflowStageError(f"loading/running CWL step {step_path} failed: {error}") from error

    def _resolve_step_inputs(self, step_spec: StageStepSpec, state: WorkflowState, step_outputs: dict) -> dict:
        with self.workflow_input_path.open("r") as file:
            workflow_inputs = json.load(file)
        inputs = {}
        for input_name, source in step_spec.inputs.items():
            if isinstance(source, str):
                if source not in workflow_inputs:
                    raise WorkflowStageError(
                        f"workflow input '{source}' for step '{step_spec.step}' is missing from {self.workflow_input_path}"
                    )
                inputs[input_name] = workflow_inputs[source]
            elif isinstance(source, StageArtifactRef):
                stage_state = state.stages.get(source.stage)
                artifact = stage_state.artifacts.get(source.artifact) if stage_state is not None else None
                if artifact is None:
                    raise WorkflowStageError(
                        f"cannot run step '{step_spec.step}': artifact '{source.artifact}' of stage "
                        f"'{source.stage.value}' is not available; run that stage first (or reset "
                        f"{self.workflow_state_path})"
                    )
                inputs[input_name] = artifact
            elif isinstance(source, StepOutputRef):
                artifact = step_outputs.get(source.step, {}).get(source.output)
                if artifact is None:
                    raise WorkflowStageError(
                        f"step '{step_spec.step}' references output '{source.output}' of step '{source.step}', "
                        f"which is not part of the same stage"
                    )
                inputs[input_name] = artifact
        return inputs

    def _run_stage(self, stage: Stage, state: WorkflowState) -> dict:
        spec = self.stage_plan[stage]
        logging.info("running stage '%s' (steps: %s)", stage.value, [step.step for step in spec.steps])
        state.stages[stage] = StageState(status=StageStatus.running, updated_at=datetime.datetime.now())
        self._save_workflow_state(state)
        inputs_digest = self._stage_inputs_digest(stage)

        try:
            step_outputs: dict[str, dict[str, dict[str, str]]] = {}
            stage_artifacts: dict[str, dict[str, str]] = {}
            for step_index, step_spec in enumerate(spec.steps):
                outdir = self._stage_outdir(stage, step_index)
                # Private per-step output directory: start clean. Never touch
                # the run directory itself.
                if outdir != self.run_dir and outdir.exists():
                    shutil.rmtree(outdir)
                inputs = self._resolve_step_inputs(step_spec, state, step_outputs)
                outputs = self._run_cwl_step(self.workflow_dir_path / step_spec.run, inputs, outdir)
                for output_name, output in outputs.items():
                    if (
                        isinstance(output, dict)
                        and "location" in output
                        and output.get("class") in ("File", "Directory")
                    ):
                        step_outputs.setdefault(step_spec.step, {})[output_name] = reduce_cwl_file(output)
                for artifact_name, output_name in step_spec.outputs.items():
                    if output_name not in step_outputs.get(step_spec.step, {}):
                        raise WorkflowStageError(
                            f"step '{step_spec.step}' did not produce output '{output_name}' "
                            f"required for artifact '{artifact_name}'"
                        )
                    stage_artifacts[artifact_name] = step_outputs[step_spec.step][output_name]
        except Exception:
            state.stages[stage] = StageState(status=StageStatus.failed, updated_at=datetime.datetime.now())
            self._save_workflow_state(state)
            raise

        state.stages[stage] = StageState(
            status=StageStatus.completed,
            updated_at=datetime.datetime.now(),
            artifacts=stage_artifacts,
            inputs_digest=inputs_digest,
        )
        self._save_workflow_state(state)
        return stage_artifacts

    def run_range(self, up_to: Stage | str | None = None, from_: Stage | str | None = None, force=None):
        """
        Execute the stages in the range ``[from_, up_to]`` of the workflow.

        - no arguments: the full pipeline. If no stage is recorded as
          completed, the complete ``workflow.cwl`` is run in a single
          cwltool invocation (the historical behavior). If earlier partial
          runs completed some stages, the remaining stages are executed
          individually and the completed ones are skipped.
        - ``up_to``: run all stages up to and including this one.
        - ``from_``: start with this stage; earlier stages must already be
          completed, otherwise a :class:`WorkflowPrerequisiteError` is
          raised (running the missing prerequisites is not done implicitly).
        - ``force``: ``True`` re-runs every stage of the range; a stage or a
          list of stages re-runs those stages. Stages that depend on a forced
          stage are invalidated as well, so they are re-run too.

        Progress is persisted in ``run_dir/.workflow_state.json`` (keyed by
        stage, never by CWL step). A completed stage is skipped only if the
        workflow inputs it consumed have not changed since it ran (each
        stage records a digest of them); changed inputs invalidate the
        affected stages and the stages that depend on them. Returns the
        artifacts of the last executed stage (for the legacy single-invocation
        full run, the artifacts recorded for the final stage), or ``None`` if
        everything was already up to date.
        """
        plan = self.stage_plan
        up_to = Stage(up_to) if up_to is not None else None
        from_ = Stage(from_) if from_ is not None else None
        forced = self._resolve_force(force, plan)

        order = list(plan.order)
        if up_to is not None and from_ is not None and order.index(from_) > order.index(up_to):
            raise ValueError(
                f"from_ ({from_.value}) is after up_to ({up_to.value}) in the pipeline order "
                f"({', '.join(stage.value for stage in order)})"
            )

        state = self._load_workflow_state()

        # Detect changes to workflow/input.yaml since the stages were last
        # executed: a completed stage whose recorded input digest no longer
        # matches (or which has none at all, e.g. a state file from before
        # digest recording) is stale, and so are the stages that depend on it.
        stale = set()
        if self.workflow_input_path.is_file():
            for stage, entry in state.stages.items():
                if entry.status is not StageStatus.completed:
                    continue
                if entry.inputs_digest is None:
                    logging.warning(
                        "stage '%s' was recorded without an input digest; treating it as stale", stage.value
                    )
                    stale.add(stage)
                elif entry.inputs_digest != self._stage_inputs_digest(stage):
                    logging.warning(
                        "the workflow inputs of stage '%s' changed since it was last executed; "
                        "it and the stages that depend on it will be re-run",
                        stage.value,
                    )
                    stale.add(stage)

        if up_to is None and from_ is None and not forced and not state.completed:
            # Historical full-run path: single cwltool invocation of workflow.cwl
            outputs = self.run()
            self._record_full_run(state, outputs)
            # Same contract as the per-step path: the artifacts of the last
            # executed stage, here the final stage of the plan.
            last_stage = state.stages.get(plan.order[-1])
            return last_stage.artifacts if last_stage is not None else None

        low = order.index(from_) if from_ is not None else 0
        high = order.index(up_to) if up_to is not None else len(order) - 1
        range_stages = order[low : high + 1]

        invalidated = self._invalidated_dependents(forced, plan) | self._invalidated_dependents(stale, plan)
        for stage in invalidated:
            entry = state.stages.get(stage)
            if entry is not None and entry.status is StageStatus.completed:
                state.stages[stage] = StageState(
                    status=StageStatus.invalidated,
                    updated_at=datetime.datetime.now(),
                    artifacts=entry.artifacts,
                    inputs_digest=entry.inputs_digest,
                )
        if invalidated:
            self._save_workflow_state(state)

        completed = state.completed - invalidated
        for stage in range_stages:
            missing = [dep for dep in plan[stage].depends_on if dep not in range_stages and dep not in completed]
            if missing:
                raise WorkflowPrerequisiteError(
                    "cannot run stage '{}' without completed prerequisite(s) {}; run them first "
                    "(e.g. picongpu_run(up_to=...)) or invoke the full pipeline without a range".format(
                        stage.value, ", ".join(dep.value for dep in missing)
                    )
                )

        last_artifacts = None
        for stage in range_stages:
            if stage in completed:
                logging.info("stage '%s' already completed, skipping", stage.value)
                continue
            last_artifacts = self._run_stage(stage, state)
        return last_artifacts
