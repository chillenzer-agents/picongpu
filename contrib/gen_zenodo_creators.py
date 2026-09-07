#!/usr/bin/env python3
"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
License: GPLv3+

Identity-aware Zenodo creators/contributors derivation (release automation L2
exploration, TT-21).

Given a git release range ``<prev>..<cand>`` the tool derives the proposed
``.zenodo.json`` ``creators`` (deduplicated people who committed within the
range) and ``contributors`` (every body else in the repository history,
``"type": "Other"``), taking badly configured git identities into account:

* ``git log --use-mailmap`` applies ``.mailmap`` if one exists;
* a checked-in alias/skip table (default ``contrib/aliases.json``) merges the
  same person's multiple emails/names (multi-machine commits, GitHub noreply
  addresses, HPC login-node accounts) and drops bot/CI identities.

The output is a unified diff of the proposed ``.zenodo.json`` against the one
currently in the repository plus a human-readable resolution table. ORCIDs and
affiliations are NEVER invented: they are carried over from the existing
``.zenodo.json`` for matching names and otherwise left to a human-verified
sidecar.

The tool only proposes; it never writes ``.zenodo.json`` itself.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import subprocess
import sys
from collections import Counter, OrderedDict
from pathlib import Path

DEFAULT_ALIASES = "contrib/aliases.json"
DEFAULT_ZENODO = ".zenodo.json"

# Generic bot / maintenance identities that must never show up as people.
DEFAULT_SKIP_PATTERNS = [
    r"(?i)\[bot\]",
    r"(?i)dependabot",
    r"(?i)renovate",
    r"(?i)github-actions",
    r"(?i)gitlab(?:.*ci|ci-runner)",
    r"root@",
    # Official GitHub notification address (not `users.noreply` which real
    # humans use for private email).
    r"noreply@github\.com",
]


class ZenodoCreatorError(RuntimeError):
    """Raised when the derivation cannot be completed (e.g. git failure)."""


def run_git(repo: Path, args: list[str]) -> str:
    """Run a git subcommand in ``repo`` and return its stdout."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip()
        raise ZenodoCreatorError(f"git {' '.join(args)} failed" + (f": {stderr}" if stderr else "")) from exc
    return proc.stdout


def load_aliases(alias_file: Path) -> dict:
    """Load and validate the alias/skip table."""
    data = json.loads(alias_file.read_text(encoding="utf-8"))
    if not isinstance(data.get("people"), dict):
        raise ZenodoCreatorError(f'{alias_file}: expected a top-level "people" object')
    if not isinstance(data.get("skip", {}).get("emails", []), list):
        raise ZenodoCreatorError(f'{alias_file}: "skip.emails" must be a list')
    if not isinstance(data.get("skip", {}).get("patterns", []), list):
        raise ZenodoCreatorError(f'{alias_file}: "skip.patterns" must be a list')
    return data


def _compile_skip_patterns(patterns: list[str]) -> list[re.Pattern]:
    compiled = []
    for pattern in [*DEFAULT_SKIP_PATTERNS, *patterns]:
        try:
            compiled.append(re.compile(pattern))
        except re.error as exc:
            raise ZenodoCreatorError(f"invalid skip pattern {pattern!r}: {exc}")
    return compiled


def parse_identity_line(line: str) -> tuple[str, str]:
    """Split a ``git log --format=%an|%ae`` line into (name, email)."""
    name, sep, email = line.partition("|")
    if not sep:
        raise ZenodoCreatorError(f"malformed identity line: {line!r}")
    return name.strip(), email.strip()


def is_skipped(name: str, email: str, data: dict) -> bool:
    """True if this raw identity is a bot/CI/maintenance identity."""
    lower_email = email.lower()
    if lower_email in data.get("skip", {}).get("emails", []):
        return True
    patterns = _compile_skip_patterns(data.get("skip", {}).get("patterns", []))
    haystack = f"{name}|{lower_email}"
    return any(pattern.search(haystack) for pattern in patterns)


def resolve_person_key(name: str, email: str, data: dict) -> str:
    """Map a raw (name, email) to a canonical person key."""
    lower_email = email.lower()
    for key, person in data.get("people", {}).items():
        aliases = [a.lower() for a in person.get("aliases", [])]
        if lower_email in aliases or name in person.get("aliases", []):
            return key
        if person.get("email") and lower_email == person["email"].lower():
            return key
    # Nothing known: fall back to an email-derived key so different names on
    # the same machine still collapse, and the identity is surfaced as
    # unknown for human review.
    return f"email:{lower_email}"


def titlecase_last_first(name: str) -> str:
    """Convert ``Given Names Last`` to ``Last, Given Names`` best-effort."""
    parts = name.split()
    if len(parts) <= 1:
        return name
    return f"{parts[-1]}, {' '.join(parts[:-1])}"


def display_name(key: str, raw_names: list[str], data: dict) -> str:
    """Canonical zenodo name for a person key."""
    person = data.get("people", {}).get(key)
    if person and person.get("name"):
        return person["name"]
    if key.startswith("email:"):
        if raw_names:
            return titlecase_last_first(raw_names[0])
        return key  # pragma: no cover - unreachable, kept defensive
    return key


def collect_identities(repo: Path, rev_range: str | None, use_mailmap: bool) -> list:
    """Run ``git log`` and return [(name, email, sha)] in log order."""
    args = ["log", "--format=%H%x00%an|%ae"]
    if use_mailmap:
        args.insert(1, "--use-mailmap")
    if rev_range:
        args.append(rev_range)
    lines = [ln for ln in run_git(repo, args).splitlines() if ln.strip()]
    identities = []
    for line in lines:
        sha, _, ident = line.partition("\x00")
        name, email = parse_identity_line(ident)
        identities.append((name, email, sha))
    return identities


def derive_people(identities: list, data: dict) -> dict:
    """
    Reduce raw identities to a ``{person_key: {...}}`` summary.

    The summary holds the person key, display name, raw names, canonical
    email, total commit count and whether the key came from the alias table
    (``known``) or was auto-derived and needs human attribution.
    """
    skipped = Counter()
    people: dict[str, dict] = OrderedDict()

    def bump(key: str, name: str, email: str) -> None:
        person = people.setdefault(
            key,
            {
                "key": key,
                "name": "",
                "raw_names": [],
                "email": "",
                "count": 0,
                "known": key in data.get("people", {}),
            },
        )
        if name not in person["raw_names"]:
            person["raw_names"].append(name)
        # Prefer the domain-ish address of the most frequent identity.
        if not person["email"]:
            person["email"] = email
        person["count"] += 1

    for name, email, _sha in identities:
        if is_skipped(name, email, data):
            skipped[(name, email)] += 1
            continue
        key = resolve_person_key(name, email, data)
        bump(key, name, email)

    for person in people.values():
        person["name"] = display_name(person["key"], person["raw_names"], data)
        known = data.get("people", {}).get(person["key"])
        if known and known.get("email"):
            # Prefer the canonical address from the alias table for display.
            person["email"] = known["email"]

    return {"people": people, "skipped": dict(skipped)}


def carry_meta_from_existing(names: list[str], existing: dict | None) -> list[dict]:
    """Build zenodo entries, carrying ORCID/affiliation for known names."""
    entries = []
    existing_creators = {c.get("name"): c for c in (existing or {}).get("creators", [])}
    existing_contributors = {c.get("name"): c for c in (existing or {}).get("contributors", [])}
    for name in names:
        entry = {"name": name}
        extra = existing_creators.get(name) or existing_contributors.get(name)
        if extra:
            if extra.get("orcid"):
                entry["orcid"] = extra["orcid"]
            if extra.get("affiliation"):
                entry["affiliation"] = extra["affiliation"]
        entries.append(entry)
    return entries


def proposed_zenodo(
    creators: list[str],
    contributors: list[str],
    existing_path: Path,
) -> dict:
    """Proposed ``.zenodo.json`` = existing file with creators/contributors swapped."""
    if existing_path.exists():
        proposed = json.loads(existing_path.read_text(encoding="utf-8"))
    else:
        proposed = {
            "creators": [],
            "contributors": [],
            "access_right": "open",
            "license": {"id": "GPL-3.0"},
            "language": "eng",
        }
    proposed["creators"] = carry_meta_from_existing(creators, proposed)
    proposed["contributors"] = [
        {**entry, "type": "Other"} for entry in carry_meta_from_existing(contributors, proposed)
    ]
    return proposed


def zenodo_diff(repo: Path, proposed: dict) -> str:
    """Unified diff of the proposed ``.zenodo.json`` against the current one."""
    existing_path = repo / DEFAULT_ZENODO
    old = existing_path.read_text(encoding="utf-8") if existing_path.exists() else ""
    new = json.dumps(proposed, indent=2, ensure_ascii=False) + "\n"
    if not old:
        old_marker = f"--- /dev/null\n+++ {DEFAULT_ZENODO}\n"
        return old_marker + "\n".join(f"+{ln}" for ln in new.splitlines())
    diff = list(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=DEFAULT_ZENODO,
            tofile=DEFAULT_ZENODO,
        )
    )
    return "".join(diff)


def check_release_branch_guard(repo: Path, cand_ref: str) -> list[str]:
    """
    Wrong-branch guard (Level 2): warn/demand that the candidate release commit
    is reachable from a local ``release-*`` branch, i.e. the zenodo update must
    target the release branch, not ``dev`` (historical #5235/#5239 failure).
    """
    warnings = []
    branches = [
        b.strip()
        for b in (run_git(repo, ["branch", "--format=%(refname:short)"]).splitlines())
        if b.strip().startswith("release-")
    ]
    if not branches:
        warnings.append(
            "guard: no local `release-*` branch found; cannot verify the "
            "candidate is merged back yet (run from the release branch)."
        )
        return warnings
    reachable = []
    for branch in branches:
        rc = subprocess.run(
            ["git", "-C", str(repo), "merge-base", "--is-ancestor", cand_ref, branch],
            capture_output=True,
            check=False,
        )
        if rc.returncode == 0:
            reachable.append(branch)
    if reachable:
        warnings.append(f"guard OK: {cand_ref} is reachable from release branch `{reachable[0]}`.")
    else:
        warnings.append(
            f"guard FAILED: {cand_ref} is NOT reachable from any `release-*` "
            "branch. Refusing to proceed: the .zenodo.json update must land on "
            f"the release branch, not `dev`. release branches: {branches}"
        )
    return warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=("Identity-aware Zenodo creators/contributors derivation (L2 PoC)."))
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="git repo root")
    parser.add_argument(
        "--range",
        help="release range, e.g. '0.7.0..0.8.0' (default: repo root only)",
    )
    parser.add_argument(
        "--aliases",
        type=Path,
        default=None,
        help=f"alias/skip table (default: <repo>/{DEFAULT_ALIASES})",
    )
    parser.add_argument(
        "--no-mailmap",
        action="store_true",
        help="do not apply .mailmap (default: --use-mailmap)",
    )
    parser.add_argument(
        "--no-diff",
        action="store_true",
        help="suppress the .zenodo.json unified diff from the output",
    )
    parser.add_argument(
        "--check-release-branch",
        metavar="CAND_REF",
        help="wrong-branch guard: require CAND_REF reachable from a release-* branch",
    )
    args = parser.parse_args(argv)

    repo: Path = args.repo.resolve()
    if not (repo / ".git").exists() and not repo.joinpath(".git").is_dir():
        raise ZenodoCreatorError(f"{repo} is not a git repository")

    aliases_path = args.aliases or (repo / DEFAULT_ALIASES)
    data = load_aliases(aliases_path)

    candidates = collect_identities(repo, args.range, not args.no_mailmap)
    summary = derive_people(candidates, data)
    people = sorted(summary["people"].values(), key=lambda p: p["name"].casefold())

    full_hist = collect_identities(repo, None, not args.no_mailmap)
    full_summary = derive_people(full_hist, data)
    creator_keys = set(summary["people"])
    contributor_keys = [key for key in full_summary["people"] if key not in creator_keys]

    creators = [p["name"] for p in people]
    contributors_sorted = sorted(
        (full_summary["people"][k] for k in contributor_keys),
        key=lambda p: p["name"].casefold(),
    )
    contributors = [p["name"] for p in contributors_sorted]

    existing_path = repo / DEFAULT_ZENODO
    proposed = proposed_zenodo(creators, contributors, existing_path)

    report = []
    report.append("=== Creators (release-range committers, deduplicated) ===")
    report.append(f"count: {len(creators)}")
    for p in people:
        known = "known" if p["known"] else "NEEDS-HUMAN-ATTRIBUTION"
        report.append(f"  {p['name']:<34} {p['count']:>4} commits  email={p['email']:<45} {known}")
    report.append("")
    report.append("=== Contributors (rest of history, type=Other) ===")
    report.append(f"count: {len(contributors)}")
    for name in contributors:
        report.append(f"  {name}")
    report.append("")
    report.append("=== Skipped identities (bots/CI/maintenance) ===")
    for (name, email), count in sorted(summary["skipped"].items()):
        report.append(f"  {name:<20} {email:<45} x{count}")

    if args.check_release_branch:
        warnings = check_release_branch_guard(repo, args.check_release_branch)
        report.append("")
        report.append("=== Wrong-branch guard ===")
        report.extend(f"  {w}" for w in warnings)

    if not args.no_diff:
        report.append("")
        report.append("=== Proposed .zenodo.json diff ===")
        report.append(zenodo_diff(repo, proposed))

    print("\n".join(report))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ZenodoCreatorError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
