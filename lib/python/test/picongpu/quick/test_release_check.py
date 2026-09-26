"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
License: GPLv3+
"""

import os
from pathlib import Path
from subprocess import run
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[5]
RELEASE_CHECK = REPO_ROOT / "share" / "ci" / "release_check.sh"

MAIN_REPO_PIN = "picongpu @ git+https://github.com/ComputationalRadiationPhysics/picongpu@dev#subdirectory=lib/python"

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

CHANGELOG = """\
Changelog
=========

0.0.0
-----

**Date:** 2026-09-07
Key highlights for this release.
"""

ZENODO = """\
{
  "creators": [
    { "affiliation": "HZDR", "name": "Debus, Alexander" }
  ],
  "contributors": []
}
"""

EXAMPLES = (
    """\
# /// script
#   requires-python = ">=3.11"
#   dependencies = [
#     """
    + MAIN_REPO_PIN
    + """,
#   ]
# ///
import picongpu
"""
)


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


def make_release_repo(repo: Path):
    repo.mkdir(parents=True)
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Release Tester")
    git(repo, "config", "user.email", "release@example.com")

    for rel, content in {
        "include/picongpu/version.hpp": VERSION_HPP,
        "docs/source/conf.py": CONF_PY,
        "lib/python/pyproject.toml": PYPROJECT,
        "CHANGELOG.md": CHANGELOG,
        ".zenodo.json": ZENODO,
        "lib/python/examples/tutorial/01_minimal.py": EXAMPLES,
        "lib/python/picongpu/picrc_builder.py": EXAMPLES,
    }.items():
        file = repo / rel
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content)

    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "baseline")
    git(repo, "tag", "0.0.0-rc1")
    git(repo, "checkout", "-qb", "release-0.0.0")
    git(repo, "commit", "-q", "--allow-empty", "-m", "release: final tweaks")


def run_release_check(repo: Path):
    return run(
        [str(RELEASE_CHECK), "--repo", str(repo)],
        capture_output=True,
        text=True,
    )


def test_release_check_passes_on_clean_release_branch():
    with TemporaryDirectory() as d:
        repo = Path(d) / "repo"
        make_release_repo(repo)

        result = run_release_check(repo)

        assert result.returncode == 0, result.stdout + result.stderr
        assert "RELEASE CHECKLIST RESULT: OK" in result.stdout
        assert "gh release create 0.0.0" in result.stdout
        assert "--target release-0.0.0" in result.stdout


def test_release_check_works_in_a_git_worktree():
    with TemporaryDirectory() as d:
        root = Path(d) / "root"
        make_release_repo(root)
        git(root, "checkout", "-qb", "some-other-branch")
        worktree = Path(d) / "worktree"
        git(root, "worktree", "add", "-q", str(worktree), "release-0.0.0")
        assert (worktree / ".git").is_file()

        result = run_release_check(worktree)

        assert result.returncode == 0, result.stdout + result.stderr
        assert "RELEASE CHECKLIST RESULT: OK" in result.stdout


def test_release_check_bad_previous_tag_still_reports_a_verdict():
    with TemporaryDirectory() as d:
        repo = Path(d) / "repo"
        make_release_repo(repo)

        result = run(
            [str(RELEASE_CHECK), "--repo", str(repo), "--previous-tag", "no_such_tag_xyz"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stdout + result.stderr
        assert "RELEASE CHECKLIST RESULT: OK" in result.stdout


def test_release_check_creators_match_with_normalized_ordering():
    with TemporaryDirectory() as d:
        repo = Path(d) / "repo"
        make_release_repo(repo)
        zenodo = repo / ".zenodo.json"
        zenodo.write_text('{ "creators": [ { "name": "Tester, Release" } ], "contributors": [] }\n')
        git(repo, "add", ".zenodo.json")
        git(repo, "commit", "-qm", "align zenodo creators")

        result = run_release_check(repo)

        assert result.returncode == 0, result.stdout + result.stderr
        assert "ok:  creators match the committers of the release range" in result.stdout


def test_release_check_fails_when_conf_py_release_mismatches():
    with TemporaryDirectory() as d:
        repo = Path(d) / "repo"
        make_release_repo(repo)
        conf_py = repo / "docs" / "source" / "conf.py"
        conf_py.write_text(conf_py.read_text().replace('release = "0.0.0"', 'release = "0.0.9"'))

        result = run_release_check(repo)

        assert result.returncode != 0
        assert "conf.py release '0.0.9' != version.hpp '0.0.0'" in result.stderr
        assert "RELEASE CHECKLIST RESULT: FAILED" in result.stdout + result.stderr


def test_release_check_fails_when_pyproject_version_mismatches():
    with TemporaryDirectory() as d:
        repo = Path(d) / "repo"
        make_release_repo(repo)
        pyproject = repo / "lib" / "python" / "pyproject.toml"
        pyproject.write_text(pyproject.read_text().replace('version = "0.0.0"', 'version = "0.0.9"'))

        result = run_release_check(repo)

        assert result.returncode != 0
        assert "pyproject.toml version '0.0.9' != version.hpp '0.0.0'" in result.stderr
        assert "RELEASE CHECKLIST RESULT: FAILED" in result.stdout + result.stderr


def test_release_check_fails_when_working_tree_is_dirty():
    with TemporaryDirectory() as d:
        repo = Path(d) / "repo"
        make_release_repo(repo)
        version_hpp = repo / "include" / "picongpu" / "version.hpp"
        version_hpp.write_text(version_hpp.read_text() + "\n")

        result = run_release_check(repo)

        assert result.returncode != 0
        assert "working tree is not clean" in result.stderr
        assert "RELEASE CHECKLIST RESULT: FAILED" in result.stdout + result.stderr


def test_release_check_fails_when_not_on_release_branch():
    with TemporaryDirectory() as d:
        repo = Path(d) / "repo"
        make_release_repo(repo)
        git(repo, "checkout", "-qb", "feature/foo")

        result = run_release_check(repo)

        assert result.returncode != 0
        assert "not on a release-*.*.* branch" in result.stderr
        assert "RELEASE CHECKLIST RESULT: FAILED" in result.stdout + result.stderr


def test_release_check_fails_when_dev_label_remains():
    with TemporaryDirectory() as d:
        repo = Path(d) / "repo"
        make_release_repo(repo)
        version_hpp = repo / "include" / "picongpu" / "version.hpp"
        version_hpp.write_text(version_hpp.read_text().replace('LABEL ""', 'LABEL "dev"'))

        result = run_release_check(repo)

        assert result.returncode != 0
        assert "release label 'dev'" in result.stderr
        assert "RELEASE CHECKLIST RESULT: FAILED" in result.stdout + result.stderr


def test_release_check_fails_when_picmi_pin_points_at_fork():
    with TemporaryDirectory() as d:
        repo = Path(d) / "repo"
        make_release_repo(repo)
        example = repo / "lib" / "python" / "examples" / "tutorial" / "01_minimal.py"
        example.write_text(example.read_text().replace("ComputationalRadiationPhysics", "some-fork"))

        result = run_release_check(repo)

        assert result.returncode != 0
        assert "pins a fork" in result.stdout
        assert "RELEASE CHECKLIST RESULT: FAILED" in result.stdout + result.stderr
