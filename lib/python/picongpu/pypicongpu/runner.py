"""
This file is part of PIConGPU.
Copyright 2021-2024 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre, Richard Pausch
License: GPLv3+
"""

import datetime
import json
import logging
import re
import tempfile
from importlib.util import module_from_spec, spec_from_file_location
from os import chmod
from pathlib import Path
from shutil import copy2, copytree
from typing import Annotated, Sequence

from cwltool.context import RuntimeContext
from cwltool.factory import Factory as WorkflowFactory
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


# --- Stepwise (chunked) execution helpers ---------------------------------
#
# `step()` runs the simulation in chunks [start, end). Each chunk re-uses the
# already-compiled binary and the already-rendered base setup; only an
# *additive* chunk config is written and a single chunk is executed. The C++
# loop runs steps [start, end) when started with `-s <end>` (TBG_steps) plus a
# restart block. See `run_chunk` / `render_chunk_config` below.


def chunk_config_filename(start: int, end: int) -> str:
    """Name of the additive chunk config for the step range [start, end)."""
    return f"N-step-{int(start)}-{int(end)}.cfg"


def _flag_present(text: str, flag: str) -> bool:
    """True if ``flag`` appears as a whole command-line token (not a prefix)."""
    return re.search(r"(^|\s)" + re.escape(flag) + r"(\s|$)", text) is not None


def _flag_value(text: str, flag: str) -> str | None:
    """The value following ``flag`` (first occurrence), or None."""
    m = re.search(r"(^|\s)" + re.escape(flag) + r"\s+(\S+)", text)
    return m.group(2) if m else None


def _merge_checkpoint_period(text: str, spec: str) -> str:
    """
    Add ``spec`` to an existing ``--checkpoint.period`` spec list.

    The PIConGPU CLI rejects a repeated ``--checkpoint.period`` (boost
    ``multiple_values``), so the chunk's checkpoint step must be *merged* into
    the user's period rather than appended as a second flag. Returns the text
    unchanged if the spec is already present.
    """
    m = re.search(r"(--checkpoint\.period\s+)[\d:,]+", text)
    if not m:
        return text
    existing = m.group(0).split(None, 1)[1]
    if spec in existing.split(","):
        return text
    return text[: m.start()] + m.group(1) + existing + "," + spec + text[m.end() :]


def chunk_config_text(
    base_cfg_text: str,
    end: int,
    *,
    checkpoint_directory: str = "checkpoints",
    checkpoint_file: str = "checkpoint",
    restart_step: int | None = None,
    auto_checkpoint: int | None = None,
) -> str:
    """
    Render an additive chunk config from the rendered base ``N.cfg`` text.

    The base text is left as-is except that:

    1. ``TBG_steps`` is overwritten to the chunk's *absolute* stop step
       ``end`` (``-s <end>`` makes the C++ loop run exactly steps ``[start,
       end)`` once ``--checkpoint.restart.step <start>`` is applied).
    2. When ``auto_checkpoint`` is given, a checkpoint is scheduled at that
       step (the chunk's final step) so the next chunk can resume. This is
       *merged* into an existing user ``--checkpoint.period`` (never a second
       flag, which the CLI rejects) or added as a new one. When ``auto_checkpoint``
       is ``None`` the user's period (covering ``end``) is left untouched --
       no forced double-write.
    3. A restart block is appended (``--checkpoint.tryRestart`` [+
       ``--checkpoint.restart.step <start>``] + the shared checkpoint
       directory). ``tryRestart`` makes a fresh start (no prior checkpoint)
       degrade cleanly to a fresh run (C++ ``TRY`` state, ``checkRestart``).

    This never modifies the base file; it returns the chunk config text.
    """
    text = re.sub(r'^(\s*TBG_steps\s*=\s*)".*?"', rf'\g<1>"{int(end)}"', base_cfg_text, count=1, flags=re.M)

    # 2. Auto-checkpoint at the chunk's final step (merged, not duplicated).
    if auto_checkpoint is not None:
        spec = f"{int(auto_checkpoint)}:{int(auto_checkpoint)}:1"
        if _flag_present(text, "--checkpoint.period"):
            text = _merge_checkpoint_period(text, spec)
        else:
            text = text.replace('--versionOnce"', f'--checkpoint.period {spec} --versionOnce"', 1)

    # 3. Restart / checkpoint-directory block (only flags not already present).
    flags = []
    if not _flag_present(text, "--checkpoint.tryRestart"):
        flags.append("--checkpoint.tryRestart")
    if restart_step is not None and not _flag_present(text, "--checkpoint.restart.step"):
        flags.append(f"--checkpoint.restart.step {int(restart_step)}")
    # Reuse the user's checkpoint directory/file if given, else the defaults.
    directory = _flag_value(text, "--checkpoint.directory") or checkpoint_directory
    file = _flag_value(text, "--checkpoint.file") or checkpoint_file
    if not _flag_present(text, "--checkpoint.directory"):
        flags.append(f"--checkpoint.directory {directory}")
    if not _flag_present(text, "--checkpoint.file"):
        flags.append(f"--checkpoint.file {file}")
    if not _flag_present(text, "--checkpoint.restart.directory"):
        flags.append(f"--checkpoint.restart.directory {directory}")
    if not _flag_present(text, "--checkpoint.restart.file"):
        flags.append(f"--checkpoint.restart.file {file}")

    if flags:
        anchor = '--versionOnce"'
        assert anchor in text, "cannot locate program-parameter anchor in rendered N.cfg"
        text = text.replace(anchor, " ".join(flags) + " " + anchor, 1)
    return text



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
