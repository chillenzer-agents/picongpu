# Task 09 - Rework Response

All findings were independently re-verified before integration (reviewer's
probes re-run, plus extra probes against the real step templates where the
probes used dummies). No findings rejected; three suggested fixes were
corrected for correctness (noted below).

## Findings

- **M1 - accepted** (`9a63ad1c9`). Rewrote the resume section of
  `partial_workflow.rst` with a range-based failure/resume example and an
  explicit statement that a failed *default* run leaves no stage state and
  resumes only at job granularity via the cwltool cache (byte-identical
  inputs). Softened the CHANGELOG sentence and the `picongpu_run` docstring
  (the same claim was also there). Reviewer's probe I re-run: no state file
  after a failed default run, confirmed.
- **M2 - accepted, suggested fix corrected** (`3488ef7c2`). Per-stage
  `inputs_digest` (sha256 of the consumed workflow inputs) recorded in
  `_run_stage`/`_record_full_run`, re-checked in `run_range`. Correction 1:
  the sketch downgrades only stages whose *own* digest changed - insufficient,
  because downstream stages whose inputs are artifacts of the stale stage
  would still be skipped; stale stages are invalidated together with their
  transitive dependents (same mechanism as `force`). Correction 2 (bug found
  while testing): per-step re-runs consulted the shared cwltool job cache,
  whose key does not cover `Directory` contents, so an invalidated dependent
  received a *stale* cached output (verified: even pre-existing
  `force=Stage.build` produced the new binary but a cached submit tbg still
  embedding the old one). Per-step invocations now run with `cachedir=None`;
  the legacy single-invocation path keeps the shared `.cwl_cache` (task-05
  behavior unchanged). New test
  `test_input_change_invalidates_completed_stages` proves the new input is
  visible in the final artifacts (not silently skipped).
- **m1 - accepted, with an environment note** (`470dcfce2`). ASCII-normalized
  `TASK-09-FINDINGS.md` (all em dashes to hyphens, same treatment as
  `TASK-05-PR-PROPOSAL.md`) and corrected section 12 (12 tests, final
  numbers, hook claim phrased as what is actually true). Note: the "pre-commit
  is failing" claim was true at the reviewed code tip `7e6e67bd8` (no
  `TASK-*.md` exclusion existed there), but the review commit `fd539988e`
  itself added the `^TASK-.*\.md$` exclusion, so at the review tip
  `pre-commit run --all-files` already exits 0. The normalization was applied
  anyway, so the claim holds under either hook config.
- **m2 - accepted** (`304da40b6`). New
  `test_default_plan_matches_workflow_template` loads the real
  `templates/workflow/workflow.cwl` (YAML) and asserts all invariants from the
  review: step files, input names/sources (workflow inputs, stage artifacts,
  in-stage step outputs), and output coverage, plus the reverse direction.
  Verified to fail against a drifted template (renamed workflow input).
  `test_stability_future_workflow` re-framed to mutate a scratch
  `workflow.cwl` (renamed step id + inserted step) with a correspondingly
  updated plan, exercising plan/workflow drift instead of plan self-consistency.
- **m3 - accepted** (`15fe49513`). The `WorkflowFactory(...).make(...)(**inputs)`
  call now wraps any load/validation exception (e.g. a renamed step file) in
  `WorkflowStageError`; the specific `WorkflowStatus` message is kept. New test
  `test_step_file_renamed_raises_workflow_stage_error`.
- **n1 - accepted, check implemented** (`6c29b4489`).
  `_load_workflow_state` now ignores state files with `version != 1` (logged
  warning, treated as empty, re-recorded on the next run) - chosen over
  dropping the field so the version is a real migration hook. New test
  `test_unknown_state_version_is_ignored`.
- **n2 - accepted** (`38b430a45`). The legacy full-run path now returns the
  recorded artifacts of the final stage instead of the raw workflow outputs
  dict, matching the documented "artifacts of the last executed stage, or
  None" contract; `picongpu_run` discards the return value (unchanged).
  Pinned in tests: the default run returns the collect artifacts, an up-to-date
  re-run returns `None`.
- **FYI (bash preset staging) - accepted, claim corrected** (`26b1540d9`,
  FINDINGS note in `470dcfce2`). Caveat added to `partial_workflow.rst`
  (Semantics) and FINDINGS section 5. Correction: the review's "deterministically
  cannot find its binary" is an artifact of the dummy echo steps in its probe;
  with the real `submit.cwl` the task-05 pre-staging places `input/bin` and
  `input/etc` into the run dir even for a per-step submit (verified by probe),
  so the local job finds its binary but runs against a *partial* input
  directory (metadata, `.build`, `ro-crate.json` appear only after `collect`).
  Staging order itself unchanged, per the rework scope.

## Gates

- `cd lib/python/test/picongpu && python -m pytest quick/ -q` ->
  **190 passed, 2 xfailed, 1 xpassed** (3499 subtests), exit 0. Baseline at
  the review tip in this environment: 186 passed, 2 xfailed, 1 xpassed
  (the review reported 185; one test differs between environments). +4 new
  tests, no regressions.
- `pre-commit run --all-files` (worktree root, venv pre-commit) -> exit 0,
  all 21 hooks passed (run after all rework commits; this file is ASCII).
