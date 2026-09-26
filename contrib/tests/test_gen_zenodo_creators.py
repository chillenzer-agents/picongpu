"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
License: GPLv3+

Cheap tests for the identity-aware Zenodo creators derivation
(``contrib/gen_zenodo_creators.py``). A synthetic git repository with
deliberately inconsistent author identities (same person committing from
several machines, bot/CI accounts) asserts that:

* the same person's multiple identities are deduplicated,
* bot/CI/maintenance identities are excluded,
* unknown identities are surfaced for human attribution (not auto-merged),
* the wrong-branch guard catches a candidate that is not on a ``release-*``
  branch.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gen_zenodo_creators as gzc

ALIASES = {
    "skip": {
        "emails": ["tools@example.com"],
        "patterns": [
            "(?i)dependabot",
            "(?i)renovate",
            "(?i)github-actions",
            "(?i)gitlab-ci",
            "root@",
        ],
    },
    "people": {
        "alice-miller": {
            "name": "Miller, Alice",
            "email": "alice@example.com",
            "aliases": ["alice@corp.example.com", "alice", "alice-m", "alice.miller.work@example.com"],
        },
        "bob-smith": {
            "name": "Smith, Bob",
            "email": "bob@example.com",
            "aliases": ["bob@example.com"],
        },
    },
}


@pytest.fixture
def synthetic_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "dev")
    git(repo, "config", "commit.gpgsign", "false")
    git(repo, "config", "tag.gpgsign", "false")
    return repo


def git(repo: Path, *args: str, **env: str) -> str:
    full_env = {
        **os.environ,
        "GIT_AUTHOR_NAME": env.get("author_name", "Initial"),
        "GIT_AUTHOR_EMAIL": env.get("author_email", "initial@example.com"),
        "GIT_COMMITTER_NAME": env.get("author_name", "Initial"),
        "GIT_COMMITTER_EMAIL": env.get("author_email", "initial@example.com"),
    }
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env=full_env,
    ).stdout


def commit_as(repo: Path, name: str, email: str, message: str) -> None:
    # GIT_AUTHOR_* / GIT_COMMITTER_* take precedence over `-c user.*`, so the
    # identity has to be injected via the environment to emulate commits made
    # from different machines with different git identities.
    git(repo, "commit", "--allow-empty", "-m", message, author_name=name, author_email=email)


def write_aliases(repo: Path, content: dict) -> Path:
    alias_file = repo / "aliases-test.json"
    alias_file.write_text(json.dumps(content, ensure_ascii=False, indent=2))
    return alias_file


def build_scenario(repo: Path) -> tuple[Path, str, str]:
    """Bootstrap a 0.0.1..HEAD history with messy identities."""
    git(repo, "commit", "--allow-empty", "-m", "base commit")
    git(repo, "tag", "0.0.1")

    # Same human, second machine, different name+email:
    commit_as(repo, "alice", "alice@corp.example.com", "alice work machine")
    # And a third, with a corporate relay address:
    commit_as(repo, "alice-m", "alice.miller.work@example.com", "more alice")
    # A human contributor:
    commit_as(repo, "Bob Smith", "bob@example.com", "bob feature")
    # Bots / maintenance identities that must be dropped:
    commit_as(repo, "dependabot[bot]", "dependabot[bot]@users.noreply.github.com", "bump dep")
    commit_as(repo, "Renovate Bot", "renovate@whitesourcesoftware.com", "update lockfile")
    # Generic shared build account:
    commit_as(repo, "nobody", "root@buildhost.internal", "system update")
    # Alice's canonical machine (in range, to exercise all three identities):
    commit_as(repo, "Alice Miller", "alice@example.com", "alice home machine")
    return repo, "0.0.1", "HEAD"


def derive(repo: Path, alias_file: Path, rev_range: str):
    data = gzc.load_aliases(alias_file)
    identities = gzc.collect_identities(repo, rev_range, use_mailmap=True)
    return gzc.derive_people(identities, data)


def test_multi_identity_dedup_and_bot_exclusion(synthetic_repo, tmp_path):
    repo, base, head = build_scenario(synthetic_repo)
    alias_file = write_aliases(repo, ALIASES)
    summary = derive(repo, alias_file, f"{base}..{head}")

    creators = {p["key"]: p for p in summary["people"].values()}
    alice = creators["alice-miller"]
    # Three distinct raw identities collapse into a single person:
    assert len(alice["raw_names"]) == 3
    assert alice["count"] == 3
    assert "Smith, Bob" == creators["bob-smith"]["name"]
    # Only the two humans remain as creators:
    assert set(creators) == {"alice-miller", "bob-smith"}

    # Bot and root identities were skipped, all of them:
    skipped = set(summary["skipped"])
    assert ("dependabot[bot]", "dependabot[bot]@users.noreply.github.com") in skipped
    assert ("Renovate Bot", "renovate@whitesourcesoftware.com") in skipped
    assert ("nobody", "root@buildhost.internal") in skipped
    assert len(skipped) == 3


def test_unknown_identity_is_surfaced_not_merged(synthetic_repo, tmp_path):
    repo, base, head = build_scenario(synthetic_repo)
    # Without an alias table the dedup can only group by email; an extra
    # identity with a distinct email must NOT be silently merged away.
    commit_as(repo, "Alice Miller", "alice.elsewhere@example.com", "mystery commit")
    alias_file = write_aliases(repo, ALIASES)
    summary = derive(repo, alias_file, f"{base}..{head}")

    keys = set(summary["people"])
    assert "alice-miller" in keys
    unknown = [k for k in keys if k.startswith("email:")]
    # Exactly one surfaced unknown (the mystery address), flagged for humans.
    assert len(unknown) == 1
    assert not summary["people"][unknown[0]]["known"]


def test_wrong_branch_guard(synthetic_repo):
    repo, _base, _head = build_scenario(synthetic_repo)
    git(repo, "checkout", "-q", "-b", "release-0.0.2")
    git(repo, "tag", "0.0.2")

    # Candidate on the release branch -> guard passes, not blocked.
    ok, blocked = gzc.check_release_branch_guard(repo, "0.0.2")
    assert any("guard OK" in w for w in ok)
    assert not blocked

    # Remote-tracking release branches are found too (fresh clone / CI case).
    git(repo, "update-ref", "refs/remotes/origin/release-0.0.2", "0.0.2")
    ok_remote, blocked_remote = gzc.check_release_branch_guard(repo, "0.0.2")
    assert any(b.endswith("release-0.0.2") for b in ok_remote) or any("guard OK" in w for w in ok_remote)

    # A candidate not reachable from the release branch -> guard fails + blocks.
    git(repo, "checkout", "-q", "dev")
    commit_as(repo, "Alice Miller", "alice@example.com", "dev-only commit")
    git(repo, "tag", "0.0.3")
    bad, blocked = gzc.check_release_branch_guard(repo, "0.0.3")
    assert any("guard FAILED" in w for w in bad)
    assert blocked


def test_wrong_branch_guard_exit_code(synthetic_repo, tmp_path, capsys):
    """The guard must actually fail hard (non-zero exit) on a wrong branch."""
    repo, base, head = build_scenario(synthetic_repo)
    alias_file = write_aliases(repo, ALIASES)
    git(repo, "checkout", "-q", "-b", "release-0.0.2")
    git(repo, "tag", "0.0.2")

    common = ["--repo", str(repo), "--range", f"{base}..{head}", "--aliases", str(alias_file), "--no-diff"]

    # Candidate reachable from the release branch -> exit 0.
    rc = gzc.main([*common, "--check-release-branch", "0.0.2"])
    assert rc == 0

    # Dev-only candidate, not on any release branch -> hard non-zero exit.
    git(repo, "checkout", "-q", "dev")
    commit_as(repo, "Alice Miller", "alice@example.com", "dev-only commit 2")
    git(repo, "tag", "0.0.3")
    rc = gzc.main([*common, "--check-release-branch", "0.0.3"])
    assert rc != 0
    out = capsys.readouterr().out
    assert "REFUSED" in out
    assert "Proposed .zenodo.json diff" not in out

    # ... unless --ignore-release-branch is given.
    rc = gzc.main([*common, "--check-release-branch", "0.0.3", "--ignore-release-branch"])
    assert rc == 0


def test_mailmap_used_only_when_present(synthetic_repo):
    repo, _base, _head = build_scenario(synthetic_repo)
    # No .mailmap in the repo -> the flag must NOT be passed.
    assert gzc.mailmap_enabled(repo, no_mailmap=False) is False
    # Once a .mailmap exists -> enable it; --no-mailmap still disables it.
    (repo / ".mailmap").write_text("Alice Miller <alice@example.com>\n")
    assert gzc.mailmap_enabled(repo, no_mailmap=False) is True
    assert gzc.mailmap_enabled(repo, no_mailmap=True) is False


def test_contributors_dedup_no_creator_leak(synthetic_repo, tmp_path, capsys):
    """
    Contributors must be deduplicated by canonical person and must not leak
    creator identities back in (emitted .zenodo.json would otherwise be
    corrupted with duplicates and wrong rows).
    """
    repo = synthetic_repo
    # History BEFORE the release tag -> contributors, not creators.
    commit_as(repo, "Zoe Zoe", "zoe@corp.example.com", "zoe pre a")
    commit_as(repo, "Zoe Zoe", "zoe@home.example.com", "zoe pre b")  # same person
    commit_as(repo, "Alice Miller", "alice@prerange.example.com", "alice pre-range")
    git(repo, "tag", "0.0.1")
    # Release-range committers -> creators.
    commit_as(repo, "Alice Miller", "alice@example.com", "alice range a")
    commit_as(repo, "Bob Smith", "bob@example.com", "bob range")
    alias_file = write_aliases(repo, ALIASES)

    rc = gzc.main(
        [
            "--repo",
            str(repo),
            "--range",
            "0.0.1..HEAD",
            "--aliases",
            str(alias_file),
            "--no-diff",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    contributors_section = out.split("=== Contributors")[1].split("=== Skipped")[0]
    # Same canonical person from two unknown emails collapses to one row.
    assert contributors_section.count("Zoe, Zoe") == 1
    # A creator identity must NOT leak back into contributors.
    assert "Miller, Alice" not in contributors_section
    # Unrelated contributor stays.
    assert "Zoe, Zoe" in contributors_section


def test_main_renders_proposal_and_diff(synthetic_repo, tmp_path, capsys):
    repo, base, head = build_scenario(synthetic_repo)
    alias_file = write_aliases(repo, ALIASES)
    (repo / ".zenodo.json").write_text(
        json.dumps(
            {
                "access_right": "open",
                "creators": [{"name": "Miller, Alice", "orcid": "0000-0000-0000-0001"}],
                "contributors": [],
                "license": {"id": "GPL-3.0"},
            },
            indent=2,
        )
    )
    rc = gzc.main(
        [
            "--repo",
            str(repo),
            "--range",
            f"{base}..{head}",
            "--aliases",
            str(alias_file),
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "Miller, Alice" in out
    assert "Smith, Bob" in out
    # Bots appear only in the skipped section, never among creators:
    creators_section = out.split("=== Skipped")[0]
    assert "dependabot" not in creators_section.lower()
    assert "=== Proposed .zenodo.json diff ===" in out
    # ORCID is carried over from the existing file for matching names.
    assert "0000-0000-0000-0001" in out
