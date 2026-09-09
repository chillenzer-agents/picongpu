"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
License: GPLv3+
"""

import os
import shutil
from pathlib import Path
from subprocess import run
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[5]
NEW_VERSION = REPO_ROOT / "src" / "tools" / "bin" / "newVersion.sh"

VERSION_HPP = """\
#pragma once

#define PICONGPU_VERSION_MAJOR 0
#define PICONGPU_VERSION_MINOR 0
#define PICONGPU_VERSION_PATCH 0
#define PICONGPU_VERSION_LABEL ""
"""

CONF_PY = """\
version = "0.0.0"
release = "0.0.0"
"""

PYPROJECT = """\
[project]
name = "picongpu"
version = "0.0.0"
"""


def git(repo: Path, *args: str, check: bool = True):
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Release Tester",
        "GIT_AUTHOR_EMAIL": "release@example.com",
        "GIT_COMMITTER_NAME": "Release Tester",
        "GIT_COMMITTER_EMAIL": "release@example.com",
    }
    result = run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        env=env,
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr}")
    return result


def make_version_repo(repo: Path) -> Path:
    repo.mkdir(parents=True)
    script = repo / "src" / "tools" / "bin" / "newVersion.sh"
    script.parent.mkdir(parents=True)
    shutil.copy(NEW_VERSION, script)

    for rel, content in {
        "include/picongpu/version.hpp": VERSION_HPP,
        "docs/source/conf.py": CONF_PY,
        "lib/python/pyproject.toml": PYPROJECT,
    }.items():
        file = repo / rel
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content)

    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Release Tester")
    git(repo, "config", "user.email", "release@example.com")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "baseline")
    return script


def run_new_version(script: Path, *values: str):
    stdin = "\n".join(("y", *values, "y")) + "\n"
    return run(
        ["bash", str(script)],
        input=stdin,
        capture_output=True,
        text=True,
    )


def assert_version(repo: Path, version: str, label: str, release: str, pyproject_version: str):
    version_hpp = (repo / "include" / "picongpu" / "version.hpp").read_text()
    assert f"PICONGPU_VERSION_MAJOR {version.split('.')[0]}" in version_hpp
    assert f"PICONGPU_VERSION_MINOR {version.split('.')[1]}" in version_hpp
    assert f"PICONGPU_VERSION_PATCH {version.split('.')[2]}" in version_hpp
    assert f'PICONGPU_VERSION_LABEL "{label}"' in version_hpp

    conf_py = (repo / "docs" / "source" / "conf.py").read_text()
    assert f'version = "{version}"' in conf_py
    assert f'release = "{release}"' in conf_py

    pyproject = (repo / "lib" / "python" / "pyproject.toml").read_text()
    assert f'version = "{pyproject_version}"' in pyproject


def test_new_version_round_trip_dev_and_plain_suffix():
    with TemporaryDirectory() as d:
        repo = Path(d) / "repo"
        script = make_version_repo(repo)

        result = run_new_version(script, "0", "1", "0", "dev")
        assert result.returncode == 0, result.stdout + result.stderr
        assert_version(repo, "0.1.0", "dev", "0.1.0-dev", "0.1.0.dev")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "bump to 0.1.0-dev")

        result = run_new_version(script, "0", "1", "0", "")
        assert result.returncode == 0, result.stdout + result.stderr
        assert_version(repo, "0.1.0", "", "0.1.0", "0.1.0")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "strip -dev for release")

        assert git(repo, "diff", "--quiet", check=False).returncode == 0


def test_new_version_rejects_bad_suffix_before_mutation():
    with TemporaryDirectory() as d:
        repo = Path(d) / "repo"
        script = make_version_repo(repo)

        result = run_new_version(script, "0", "1", "0", "rc/2")

        assert result.returncode != 0
        assert "error: SUFFIX" in result.stderr
        assert_version(repo, "0.0.0", "", "0.0.0", "0.0.0")
        assert git(repo, "diff", "--quiet", check=False).returncode == 0
