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

    # Directory (relative to ``simOutput``) where checkpoints are written/read.
    # Shared across all stepwise chunks so a later chunk can restart from an
    # earlier chunk's checkpoint. Mirrors the C++ default ("checkpoints").
    checkpoint_directory: str = "checkpoints"
    # openPMD checkpoint file prefix (mirrors the C++ default "checkpoint").
    checkpoint_file: str = "checkpoint"

    # Whether the setup has been generated (base N.cfg rendered). Stepwise
    # ``run_chunk`` calls must not re-render the base setup; the base ``N.cfg``
    # stays as-is and each chunk only writes an additive chunk config.
    _generated: bool = False
    # Whether the PIConGPU binary has been built once for this runner. Build
    # happens at most once; every stepwise chunk reuses it.
    _built: bool = False

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
    def run_chunk_step_path(self):
        return self.workflow_dir_path / "steps" / "run_chunk.cwl"

    @property
    def run_chunk_script_path(self):
        return self.workflow_scripts_path / "run_chunk.sh"

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

    def generate_run_chunk_command(self, rc_params=rc_params):
        """Generate the per-chunk foreground execution script used by ``run_chunk``.

        The script re-uses the once-built binary and the additive chunk config
        and runs a single chunk in the foreground, reusing the shared
        ``simOutput``. Positional arguments (see ``run_chunk.cwl``):

          1. submit_system (default ``bash``)
          2. cfg_file        (the additive chunk config, e.g. ``etc/picongpu/N-step-0-2.cfg``)
          3. project_path    (setup dir containing ``etc/`` and the chunk config)
          4. bin_directory   (the once-built binaries)
          5. dst_path        (shared run dir; ``simOutput`` accumulates here)
          6. template_file   (the preset TBG template, e.g. ``etc/picongpu/<preset>/mpiexec.tpl``)

        A stepwise chunk runs into the *shared* ``simOutput`` (results and
        checkpoints accumulate across chunks) and re-uses the once-built
        binary. The script therefore: stages the binary under
        ``<dst_path>/input`` (the path the preset template expects), generates
        ``submit.start`` via ``tbg`` into the shared ``dst_path`` (``-f``
        overwrites the previous chunk's ``submit.start``), and runs
        ``submit.start`` in the foreground. The preset template's
        ``mkdir simOutput 2> /dev/null`` is idempotent, so the shared directory
        is reused rather than wiped.
        """
        self.run_chunk_script_path.parent.mkdir(parents=True, exist_ok=True)
        with self.run_chunk_script_path.open("w") as script:
            script.write(
                script_content_with(
                    [
                        'export PIC_PROFILE="${PIC_PROFILE:-./picongpu.profile}"',
                        # run_chunk.sh: $1 submit_system, $2 cfg_file, $3 project_path,
                        #               $4 bin_directory, $5 dst_path, $6 template_file
                        'SUBMIT_SYSTEM="$1"',
                        'CFG_FILE="$2"',
                        'PROJECT_PATH="$3"',
                        'BIN_DIRECTORY="$4"',
                        'DST_PATH="$5"',
                        'TEMPLATE_FILE="$6"',
                        'mkdir -p "$DST_PATH"',
                        # Stage the once-built binary where the preset template
                        # expects it ($TBG_dstPath/input/bin). BIN_DIRECTORY is
                        # the build.cwl output (<run_dir>/bin).
                        'if [ -d "$BIN_DIRECTORY" ]; then',
                        '  mkdir -p "$DST_PATH/input"',
                        '  rm -rf "$DST_PATH/input/bin"',
                        '  cp -r "$BIN_DIRECTORY" "$DST_PATH/input/bin"',
                        "fi",
                        # Generate the chunk submission into the shared dst_path.
                        # NOTE: tbg is called WITHOUT -s so it only *generates*
                        # submit.start and does NOT auto-submit it; the explicit
                        # foreground run below is the single execution of the
                        # chunk (passing -s would make tbg submit a second time).
                        # -f is required: every chunk reuses the same dst_path,
                        # so a later chunk must overwrite the previous submit.start.
                        'if [ -n "$TEMPLATE_FILE" ] && [ -f "$TEMPLATE_FILE" ]; then',
                        '  tbg -c "$CFG_FILE" -t "$TEMPLATE_FILE" -f "$PROJECT_PATH" "$DST_PATH"',
                        "else",
                        '  tbg -c "$CFG_FILE" -f "$PROJECT_PATH" "$DST_PATH"',
                        "fi",
                        # Run the generated submission in the foreground (local
                        # execution; batched submission is a follow-up). This is
                        # the single execution of the chunk.
                        'bash "$DST_PATH/tbg/submit.start" > "$DST_PATH/output.chunk" 2>&1',
                    ],
                    rc_params=rc_params,
                )
            )
            script.flush()
        chmod(self.run_chunk_script_path, 0o755)

    def _preset_run_template(self):
        """Return the (preset) TBG template that submits via ``bash``/mpi, or None.

        A stepwise chunk reuses this template verbatim: the preset template's
        ``mkdir simOutput 2> /dev/null`` is idempotent, so a later chunk runs
        into the *shared* ``simOutput`` (results/checkpoints accumulate) instead
        of wiping it. An empty ``preset_dir`` is the foreground default, which
        uses the ``bash/`` submission templates.
        """
        preset = rc_params.preset_dir or "bash"
        preset_dir = self.setup_dir / "etc" / "picongpu" / preset
        if not preset_dir.is_dir():
            return None
        for name in ("mpiexec.tpl", "mpirun.tpl", "bash_mpiexec.tpl", "bash_mpirun.tpl"):
            candidate = preset_dir / name
            if candidate.is_file():
                return candidate
        for candidate in sorted(preset_dir.glob("*.tpl")):
            if "mpi" in candidate.read_text(errors="ignore"):
                return candidate
        return None

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
        self.generate_run_chunk_command()

        self._render_templates(exist_ok=exist_ok)

        self.generate_workflow_input(
            build_flags=PicBuildFlags(**flags),
            run_flags=TBGFlags(project_path=self.setup_dir, **flags),
        )
        self.cwl_cachedir.mkdir(parents=True, exist_ok=True)

        self.store_metadata(self.model_dump(mode="json"), filename="pypicongpu_runner.json")
        self.store_metadata(rc_params.model_dump(mode="json"), filename="rc_params.json")

        self._write_rocrate()
        self._generated = True

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

    # ------------------------------------------------------------------ #
    # Stepwise (chunked) execution                                         #
    # ------------------------------------------------------------------ #

    def chunk_config_path(self, start: int, end: int) -> Path:
        """Location of the additive chunk config for [start, end)."""
        return self.setup_dir / "etc" / "picongpu" / chunk_config_filename(start, end)

    def write_chunk_config(self, start: int, end: int, *, need_checkpoint: bool = True) -> Path:
        """
        Render and write the additive chunk config for [start, end).

        Reads the *rendered* base ``N.cfg`` (never the ``.mustache`` template)
        and produces ``N-step-<start>-<end>.cfg`` = base + ``TBG_steps = <end>``
        + (when ``need_checkpoint``) a checkpoint at ``end`` + the restart
        block. The base ``N.cfg`` is left as-is.
        """
        base_cfg = self.setup_dir / "etc" / "picongpu" / "N.cfg"
        base_text = base_cfg.read_text()
        restart_step = int(start) if start > 0 else None
        text = chunk_config_text(
            base_text,
            end,
            checkpoint_directory=self.checkpoint_directory,
            checkpoint_file=self.checkpoint_file,
            restart_step=restart_step,
            auto_checkpoint=int(end) if need_checkpoint else None,
        )
        out = self.chunk_config_path(start, end)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text)
        return out

    def _resolve_checkpoint_directory(self) -> str:
        """Checkpoint directory the chunks actually read/write.

        A user ``Checkpoint(directory=...)`` is what ``chunk_config_text`` reuses
        for the chunk's restart block and what the base ``N.cfg`` renders as
        ``--checkpoint.directory <dir>``; restart discovery must look in the same
        directory. It is resolved from the checkpoint output plugin on
        ``self.sim`` (available before the base ``N.cfg`` is rendered), then from
        the rendered base ``N.cfg``, then the C++ default.
        """
        from picongpu.pypicongpu.output.checkpoint import Checkpoint as CheckpointPlugin

        for plugin in self.sim.output or []:
            if isinstance(plugin, CheckpointPlugin) and plugin.directory is not None:
                return str(plugin.directory)
        base_cfg = self.setup_dir / "etc" / "picongpu" / "N.cfg"
        if base_cfg.is_file():
            directory = _flag_value(base_cfg.read_text(), "--checkpoint.directory")
            if directory:
                return directory
        return self.checkpoint_directory

    def detect_latest_checkpoint(self) -> int | None:
        """Latest checkpoint step recorded under the shared ``simOutput`` dir.

        Reads the C++ checkpoint master file (``checkpoints.txt``) from the
        run's shared ``simOutput/<checkpoint_directory>`` and returns the last
        step, or ``None`` when no checkpoint exists yet (fresh start). The
        directory honors a user ``Checkpoint(directory=...)`` (see
        ``_resolve_checkpoint_directory``).
        """
        master = self.run_dir / "simOutput" / self._resolve_checkpoint_directory() / "checkpoints.txt"
        if not master.is_file():
            return None
        steps = []
        for line in master.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    steps.append(int(line))
                except ValueError:
                    continue
        return max(steps) if steps else None

    def build_once(self, **flags) -> None:
        """
        Build the PIConGPU binary exactly once for this runner (chunks re-use it).

        Runs the ``build.cwl`` step a single time and stages the compiled
        binaries under ``<run_dir>/bin`` (the location the TBG submission
        expects, ``$TBG_dstPath/input/bin`` with ``TBG_dstPath=<run_dir>``).
        Subsequent stepwise chunks skip the build entirely: ``TBG_steps`` is a
        *runtime* TBG variable (``-s !TBG_steps``), not a compile-time
        ``.param``, so stepping across chunks never rebuilds.
        """
        if self._built:
            return
        if not self._generated:
            self.generate(**flags)
        build_input = {
            k: v for k, v in json.loads(self.workflow_input_path.read_text()).items() if k.startswith("build_")
        }
        WorkflowFactory(
            runtime_context=RuntimeContext(
                kwargs={
                    "outdir": str(self.run_dir),
                    "rm_tmpdir": False,
                    "move_outputs": "copy",
                    "cachedir": str(self.cwl_cachedir),
                    "preserve_entire_environment": True,
                }
            )
        ).make(str(self.build_step_path))(**build_input)
        self._built = True

    @property
    def _bin_dir(self) -> Path:
        """Shared per-run dir where the once-built binary is staged (``<run_dir>/bin``)."""
        return self.run_dir / "bin"

    def run_chunk(self, start: int, end: int, *, need_checkpoint: bool = True) -> None:
        """
        Execute a single stepwise chunk [start, end) into the shared run_dir.

        1. Writes the additive chunk config (base ``N.cfg`` + ``TBG_steps = end``
           + checkpoint/restart block). When ``need_checkpoint`` is set, a
           checkpoint is also scheduled at ``end`` so the next chunk can resume.
        2. Builds the binary once (``build.cwl``) if not already built.
        3. Runs the dedicated, reusable ``run_chunk`` CWL step once for this
           chunk.

        The top-level ``workflow.cwl`` is *not* re-invoked per chunk (that would
        re-run ``build`` and the single-shot submission). Every chunk shares the
        same ``run_dir`` / ``simOutput`` (constant ``TBG_dstPath``) so results
        accumulate next to each other with no per-chunk post-merge.
        """
        chunk_config = self.write_chunk_config(start, end, need_checkpoint=need_checkpoint)
        self.build_once()

        if not need_checkpoint:
            logging.info(
                "step() chunk [%s, %s): no checkpoint scheduled (add_checkpoint=False or "
                "covered by a user Checkpoint). The next chunk must provide its own "
                "restart point.",
                start,
                end,
            )

        with self.workflow_input_path.open("r") as file:
            workflow_input = json.load(file)
        preset_template = self._preset_run_template()
        # The chunk step writes into the *real* shared run directory in place,
        # so all directory inputs are passed as absolute string paths (not
        # staged Directories). See run_chunk.cwl for the rationale.
        chunk_input = {
            "start_step": int(start),
            "end_step": int(end),
            "cfg_file": str(chunk_config),
            "project_path": str(self.setup_dir),
            "bin_directory": str(self._bin_dir),
            "dst_path": str(self.run_dir),
            "submit_system": workflow_input.get("run_submit_system") or "bash",
            "template_file": str(preset_template) if preset_template is not None else "",
            "script": {"class": "File", "location": str(self.run_chunk_script_path)},
        }
        WorkflowFactory(
            runtime_context=RuntimeContext(
                kwargs={
                    "outdir": str(self.run_dir),
                    "rm_tmpdir": False,
                    "move_outputs": "copy",
                    "cachedir": str(self.cwl_cachedir),
                    "preserve_entire_environment": True,
                }
            )
        ).make(str(self.run_chunk_step_path))(**chunk_input)
