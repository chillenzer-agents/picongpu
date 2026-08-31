# Task 01 — Response to `TASK-01-REVIEW.md`

Branch `task-01-docs-tested-snippets`, rework on top of review commit
`16206c129` (2026-08-31). All claims below were re-verified against the
committed code before acting.

## Finding dispositions

- **C1**: integrated-with-mods — the checked-in-script fix was applied as
  hardening (`share/ci/docs_snippets_profile_check.sh`, `4201e572a`) and the
  dry-run was re-done honestly against the actual job script list
  (`share/ci/docs_snippets_dryrun.sh`, `cb498a123`; PR-proposal
  verification log corrected). The critical claim itself is **rejected** —
  the job as committed was runnable; see "review corrections".
- **M1**: integrated (`9a0dbcf2f`). Verified: `pypicongpu.sh:20` exports
  `PICSRC` before the profile is sourced, and the generated profile does
  define `PICSRC` (line 40 of the profile generated from the `bash`
  preset). `unset PICSRC` before `source …/picongpu.profile` makes the test
  verify the profile itself; negative test: with `export PICSRC=` removed
  from a generated profile, `test -n "$PICSRC"` fails as intended.
- **m1**: integrated (`63ed5f459`, PR description `82511dcbc`). Wording in
  `test_snippets.py` and `snippets/README.md` now reads "one bash flow
  (setup generation + profile sourcing, as `legacy_workflow.sh` performs
  it) is executed for real by the CI job; all bash snippets are
  syntax-checked with `bash -n`", plus an explicit executed-vs-syntax
  checked list in the README.
- **m2**: integrated (`fbc0134d7`, ruff-format follow-up `1b79a15e8`,
  PR body `82511dcbc`). `PEAK_FOCAL`/`PEAK_SIGMA`/`PEAK_COUNT`/
  `SCAN_FOCALS` are defined once in `run_snippet.py` and imported by
  `test_snippets.py` (identical numeric semantics); the PR body states the
  optimizer test is a mechanics test against a synthetic, harness-defined
  landscape.
- **n1**: integrated-with-mods — first removed the entry as suggested
  (`b36adce9b`), which proved to be a **regression**: `myst_parser` also
  collects `.md` files as documents, and `snippets/README.md` is one;
  without the entry the build gained a new
  `snippets/README.md: WARNING: document isn't included in any toctree`
  (seen in the re-run dry-run build). The entry is therefore kept and the
  misleading comment corrected instead (the review's own alternative),
  `fc618b555`; verified warning-free by a fresh sphinx build and the
  final dry run.
- **n2**: integrated (`0f8f64b9b`, PR body `82511dcbc`). Python snippet
  shebangs unified on `#!/usr/bin/env python` (majority style; direct
  execution works against the installed package without resolving the
  WIP `@dev` pin; PEP 723 blocks retained for `uv run`/`hatch run`).
  The WIP-`@dev`-pin note was added to the PR body.

## Review corrections

- **C1's core claim is wrong.** The committed job was not unrunnable.
  The profile-check block is a YAML `- |` (literal block scalar): the YAML
  parser strips the common 6-space indentation from *all* lines, so the
  heredoc terminator `PY` sits at column 0 in the script the GitLab runner
  receives and the heredoc is properly terminated.
  - Parsing `16206c129:.gitlab-ci.yml` with PyYAML, the profile-check
    script entry contains a bare, column-0 `PY`.
  - The job's script entries concatenated as YAML-parsed pass `bash -n`
    and `sh -n` cleanly (no "delimited by end-of-file (wanted 'PY')"
    warning).
  - The review's evidence file ("extracted verbatim from
    `.gitlab-ci.yml:237-265`") preserved the *YAML* indentation (its
    `PY` line is indented 6 spaces) — that file is not what the runner
    executes; re-running that extraction reproduces the review's warning
    exactly, confirming the extraction, not the job, was the problem.
  - A full dry-run of the YAML-parsed job script list passed end-to-end,
    including the profile-check step.
  - (The review's own claim table lists "YAML parse of the new job: OK" —
    that parse is precisely what performs the de-indent.)
  The checked-in-script fix was applied anyway: it makes the profile
  check directly executable/testable outside GitLab and removes the
  heredoc-in-YAML form that is easy to misread (this review included).
- **n1's "nothing is excluded" is wrong**: `.md` files are source files
  here (`myst_parser` in `conf.py` extensions), so the entry was
  excluding `snippets/README.md` — see n1 above.
- The §4 side note "10 Python + 15 bash" (off-by-one in the artifact) is
  correct and has been applied in the PR proposal.

## Beyond the review's scope (flagged)

- The `require-ascii` pre-commit hook fails on `TASK-01-REVIEW.md` itself
  (non-ASCII characters; the rework rules forbid modifying it). Excluded
  `^TASK-*.md$` (task coordination artifacts at the repo root) from that
  hook, `23851c612` — the same pattern REVIEW-SUMMARY flags for tasks
  09/11. If unwanted, reverting that single commit makes "pre-commit
  all pass" red at the tip solely because of the review doc.
- Harness stability for task 02 (rebased onto this branch):
  `run_snippet.py`/`test_snippets.py` interfaces and the `docs-snippets`
  job structure are unchanged apart from the fixes above; the job still
  runs the suite, the profile check, and the sphinx build in the same
  order.

## Final gate results (branch tip)

| Gate | Result |
|---|---|
| `cd lib/python/test/picongpu && <task venv> python -m pytest quick/ -q` | `174 passed, 2 xfailed, 1 xpassed` (+3499 subtests) — == base |
| snippet suite, run the way the CI job does it (inside the dry-run) | `25 passed in 29.82s` |
| `pre-commit run --all-files` | exit 0, all 21 hooks Passed |
| CI job dry-run, `share/ci/docs_snippets_dryrun.sh` (job `script:` entries as YAML-parsed, run verbatim; stubs only: `pypicongpu.sh` micromamba setup, `apt`, `pic-build`/`pic-configure`/`tbg --help`) | **all 16 job steps passed** (~4 min): `25 passed`; `profile check OK: PIC_BACKEND=omp2b:native PICSRC=<source tree>`; doxygen + sphinx `build succeeded` (412 warnings, 0 in `python_package/`, 0 include failures); both grep gates passed |
