# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "picongpu @ git+https://github.com/ComputationalRadiationPhysics/picongpu@dev#subdirectory=lib/python"
# ]
# ///
"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+

``picongpu`` -- a single general entry point for the Python-layer tools.

Dispatches to the individual tools as subcommands, so everything can be invoked
through one name (both as a console script and via ``python -m picongpu``):

- ``picongpu rc build``       interactive ``.picongpurc.toml`` builder
- ``picongpu rc print``       print the full resolved ``rc_params`` content
- ``picongpu dependencies install``  best-effort dependency auto-installation
- ``picongpu dependencies check``    verify the preset's dependency directories
- ``picongpu shell [--from <setup_dir_or_run_dir>]``
                              interactive shell with a generated/sourced profile
- ``picongpu shell [--from <...>] run <command>``
                              run ``<command>`` inside that shell environment

The subcommand implementations live in ``picrc_builder`` and ``pic_deps``; this
module only routes to them.
"""

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path

import tomli_w

from picongpu._rc_params import rc_params as _rc_params_default
from picongpu.pic_deps import main as deps_main
from picongpu.picrc_builder import main as rc_build
from picongpu.pypicongpu.runner import generate_bare_profile

__all__ = ["main"]

_DESC = (
    "picongpu -- general entry point for the PIConGPU Python-layer tools\n"
    "\n"
    "Subcommands:\n"
    "  rc build                 interactive .picongpurc.toml configuration builder\n"
    "  rc print                 print the full resolved rc_params content\n"
    "  dependencies install     run the preset's dependencies_autoinstall.sh (best-effort)\n"
    "  dependencies check       verify each dependency directory the script owns\n"
    "  shell [--from PATH]      interactive shell with the generated/sourced profile\n"
    "  shell [--from PATH] run <command>\n"
    "                           run <command> inside the corresponding shell environment\n"
)

PROFILE_NAME = "picongpu.profile"


def find_profile(from_path: Path | None, tmpdir: Path | None = None) -> Path:
    """Return the profile to source for ``shell --from *from_path*``.

    ``from_path`` may point at a ``picongpu.profile`` directly, or at a
    ``setup_dir``/``run_dir`` that contains one (in ``workflow/scripts/`` for a
    setup dir, or at its root for an organized run dir). With ``None`` a bare
    profile is generated from the discovered ``rc_params`` into *tmpdir* (or a
    fresh temporary directory) -- the default ``picongpu.profile``.
    """
    if from_path is None:
        import tempfile

        directory = Path(tempfile.mkdtemp(prefix="picongpu-shell-")) if tmpdir is None else Path(tmpdir)
        return generate_bare_profile(path=directory / PROFILE_NAME)

    from_path = Path(from_path)
    if from_path.is_file():
        return from_path
    if not from_path.is_dir():
        raise SystemExit(f"error: --from path does not exist: {from_path}")

    candidates = (
        from_path / PROFILE_NAME,
        from_path / "workflow" / "scripts" / PROFILE_NAME,
        from_path / "input" / "workflow" / "scripts" / PROFILE_NAME,
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise SystemExit(
        f"error: no {PROFILE_NAME} found in {from_path} (looked in ./, workflow/scripts/, input/workflow/scripts/)."
    )


def shell(from_path: Path | None, command: list[str] | None) -> int:
    """Drop into an interactive shell (or run *command*) with the profile sourced.

    Everything transient (a generated default profile, the bash rcfile) lives in
    one temporary directory that is removed when this function returns. For the
    interactive case that is after the shell exits; the profile has been sourced
    into the running shell by then.
    """
    import tempfile

    with tempfile.TemporaryDirectory(prefix="picongpu-shell-") as tmp:
        tmpdir = Path(tmp)
        profile = find_profile(from_path, tmpdir)

        rcfile = tmpdir / "picongpu.shell.rc"
        rcfile.write_text(f"if [ -f ~/.bashrc ]; then . ~/.bashrc; fi\n. {shlex.quote(str(profile))}\n")

        env = dict(os.environ)
        env["PIC_PROFILE"] = str(profile)

        if command:
            # Non-interactive: source the profile, then exec the command.
            # Keep the profile's stderr (real diagnostics) visible; drop stdout
            # and the interactive banner.
            snippet = f". {shlex.quote(str(rcfile))} >/dev/null\nexec {shlex.join(command)}"
            return subprocess.run(["bash", "-lc", snippet], env=env).returncode

        return subprocess.run(["bash", "--rcfile", str(rcfile), "-i"], env=env).returncode


def _print_rc(rcp) -> int:
    """Print the full resolved ``rc_params`` content as TOML."""
    print(tomli_w.dumps(rcp.model_dump()), end="")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="picongpu",
        description=_DESC,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    rc = sub.add_parser("rc", help="rc_params related tools")
    rc_sub = rc.add_subparsers(dest="rc_command", required=True)
    rc_build_parser = rc_sub.add_parser("build", help="interactive .picongpurc.toml configuration builder")
    rc_build_parser.add_argument(
        "config",
        nargs="?",
        default=None,
        type=Path,
        help="Path to a .picongpurc.toml to load and complete. If the path does "
        "not exist (or is a directory), a new configuration is created there.",
    )
    rc_sub.add_parser("print", help="print the full resolved rc_params content")

    deps = sub.add_parser("dependencies", help="preset dependency tools")
    deps_sub = deps.add_subparsers(dest="dependencies_command", required=True)
    deps_sub.add_parser("install", help="run the preset's dependencies_autoinstall.sh (best-effort)")
    deps_sub.add_parser("check", help="verify each dependency directory the script owns")

    shell_parser = sub.add_parser("shell", help="interactive shell with a sourced picongpu.profile")
    shell_parser.add_argument(
        "--from",
        dest="from_path",
        default=None,
        type=Path,
        help="setup_dir or run_dir whose picongpu.profile to source "
        "(default: a freshly generated profile from the discovered rc_params).",
    )
    # No `required=True` here: a bare `picongpu shell` must drop into the
    # interactive shell, `shell run <cmd>` runs a command instead.
    shell_sub = shell_parser.add_subparsers(dest="shell_command")
    # add_help=False so `shell run <cmd> -h` passes `-h` through to <cmd>
    # instead of argparse intercepting it as its own help request.
    shell_run = shell_sub.add_parser(
        "run",
        add_help=False,
        help="run a command in the corresponding shell environment",
    )
    shell_run.add_argument("run_command", nargs=argparse.REMAINDER)

    args = parser.parse_args(argv)

    if args.command == "rc":
        if args.rc_command == "build":
            return rc_build([str(args.config)] if args.config is not None else [])
        return _print_rc(_rc_params_default)

    if args.command == "dependencies":
        return deps_main([args.dependencies_command])

    if args.command == "shell":
        command = None
        if args.shell_command == "run":
            # argparse.REMAINDER keeps a leading "--" separator; drop it.
            command = list(args.run_command)
            if command and command[0] == "--":
                command = command[1:]
            if not command:
                parser.error("shell run: no command given")
        return shell(args.from_path, command)

    return 0


if __name__ == "__main__":
    sys.exit(main())
