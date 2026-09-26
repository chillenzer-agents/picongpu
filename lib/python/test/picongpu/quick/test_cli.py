"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+

Tests for the general ``picongpu`` entry point (lib/python/picongpu/cli.py).
"""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from picongpu import cli


def _make_profile(path: Path, *, marker: str = "marker"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'export PROFILE_MARKER="{marker}"\n')
    return path


def test_find_profile_direct_file():
    with TemporaryDirectory() as d:
        profile = _make_profile(Path(d) / "picongpu.profile")
        assert cli.find_profile(profile) == profile


def test_find_profile_setup_dir_layout():
    with TemporaryDirectory() as d:
        profile = _make_profile(Path(d) / "workflow" / "scripts" / "picongpu.profile")
        assert cli.find_profile(Path(d)) == profile


def test_find_profile_run_dir_layout():
    with TemporaryDirectory() as d:
        profile = _make_profile(Path(d) / "picongpu.profile")
        assert cli.find_profile(Path(d)) == profile


def test_find_profile_none_generates_a_profile():
    profile = cli.find_profile(None)
    assert profile.is_file()
    assert profile.name == cli.PROFILE_NAME


def test_find_profile_missing_directory():
    with TemporaryDirectory() as d:
        missing = Path(d) / "nope"
        with pytest.raises(SystemExit, match="does not exist"):
            cli.find_profile(missing)


def test_find_profile_directory_without_profile():
    with TemporaryDirectory() as d:
        with pytest.raises(SystemExit, match="no picongpu.profile found"):
            cli.find_profile(Path(d))


def test_shell_run_reports_missing_from_path():
    with TemporaryDirectory() as d:
        with pytest.raises(SystemExit, match="does not exist"):
            cli.shell(Path(d) / "nope", ["true"])


def test_shell_run_reports_directory_without_profile():
    with TemporaryDirectory() as d:
        with pytest.raises(SystemExit, match="no picongpu.profile found"):
            cli.shell(Path(d), ["true"])


def test_shell_run_drops_leading_double_dash():
    with TemporaryDirectory() as d:
        _make_profile(Path(d) / "picongpu.profile")
        # `--` must be consumed, not passed on as the command name.
        assert cli.shell(Path(d), ["--", "true"]) == 0


def test_shell_run_passes_dash_arguments_through():
    with TemporaryDirectory() as d:
        _make_profile(Path(d) / "picongpu.profile")
        rc = cli.shell(Path(d), ["bash", "-c", 'test -n "$1"', "bash", "-x"])
        assert rc == 0


def test_shell_run_returns_command_status_and_sources_profile():
    with TemporaryDirectory() as d:
        _make_profile(Path(d) / "picongpu.profile", marker="from-cli-test")
        rc = cli.shell(Path(d), ["bash", "-c", 'test "$PROFILE_MARKER" = from-cli-test'])
        assert rc == 0


def test_shell_run_propagates_failure_status():
    with TemporaryDirectory() as d:
        _make_profile(Path(d) / "picongpu.profile")
        assert cli.shell(Path(d), ["false"]) == 1


def test_rc_print_returns_zero(capsys):
    assert cli.main(["rc", "print"]) == 0
    out = capsys.readouterr().out
    assert "preset" in out or "dirty_reset_policy" in out


def test_missing_subcommand_errors():
    with pytest.raises(SystemExit):
        cli.main([])


def test_unknown_subcommand_errors():
    with pytest.raises(SystemExit):
        cli.main(["deps"])


def test_shell_run_without_command_errors():
    with pytest.raises(SystemExit):
        cli.main(["shell", "run"])
