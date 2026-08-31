# Review — Task 09: Partial Workflow Execution (Stable Stage Interface)

- **Branch:** `task-09-partial-workflow` (tip `7e6e67bd8`, base `task-05-cwl-cache-ref-purge` @ `33d89313f`)
- **Reviewed:** 2026-08-31 · **Scope:** 7 commits, 11 files, +1572/−19
- **Verdict:** REQUEST CHANGES
  (Sound design and a working draft, but the artifact contains two false claims — a failed "pre-commit green" and a doc example that misdescribes the flagship resume behavior — plus a silent-no-op hazard on changed inputs.)

## 1. Summary

The branch adds a `Stage` vocabulary (`build`/`prepare`/`submit`/`collect`), a
data-driven stage→CWL-step adapter (`StagePlan`/`DEFAULT_STAGE_PLAN`), a
stage-keyed persisted state file (`run_dir/.workflow_state.json`), and
`Runner.run_range(up_to/from_/force)` exposed as
`Simulation.picongpu_run(up_to=..., from_=..., force=...)`. Scope is
correctly Python-only (no C++/template/CWL changes in the diff). I verified the
test gate (185 passed = 177 baseline + 8 new), re-implemented the author's
scenarios in scratch scripts, and attacked the core promise: renaming CWL step
ids in `workflow.cwl` is transparent to the stage API (the per-step path
bypasses `workflow.cwl` entirely and the plan references step *files*, not ids),
and the state/on-disk layout is genuinely step-name-free. The main problems:
(1) a failed *default* (no-arg) run records no stage state at all, so the
documented "resume after a failed run" example is false for the most common
entry point; (2) the state has no link to the inputs that produced the
artifacts — after any completed run, editing `input.yaml` and calling
`picongpu_run()` silently does nothing and reuses stale artifacts; (3) the
"pre-commit green" claim is false (the author's own `TASK-09-FINDINGS.md`
fails `require-ascii`).

## 2. Findings

### 2.1 Critical

None found.

### 2.2 Major

**M1** — **`docs/source/usage/picmi/partial_workflow.rst:66-82`** (and the
same wording in `CHANGELOG.md:12`) — the flagship "resume after a failed run"
story does not hold for the default (no-arg) call, and the doc example asserts
it does.
- The example shows `sim.picongpu_run()` failing inside `submit`, then a
  second `sim.picongpu_run()` where "only 'submit' and 'collect' are re-run".
  That is false: the legacy full-run path records state **only after
  success** — `run_range` calls `self._record_full_run(state, outputs)`
  (runner.py:967-968) only after `self.run()` returns. A failed default run
  leaves **no state file at all**, so the second call sees an empty state,
  takes the legacy path again, and re-runs the whole `workflow.cwl`.
  `build`/`prepare` are skipped only if cwltool's job cache hits — i.e. only
  when the "fix" did not change any input, which is usually not the case.
  - *Evidence:* scratch repro (`/tmp/opencode/review-09/probe_i.py`): failing
    `submit` dummy, `sim.picongpu_run()` → raises `WorkflowStatus`; afterwards
    `run_dir/.workflow_state.json` **does not exist** (only `.cwl_cache` with
    6 job entries). Stage-level resume *does* work for range-started runs
    (verified: `up_to=submit` fails → no-arg resume re-ran only submit+collect,
    build/prepare untouched), so the feature exists but the documented
    default-call example is wrong.
  - *Suggested fix:* (a) Rewrite the doc section: state that stage-level resume
    applies to runs started with an explicit range (`up_to`/`from_`), while a
    failed *default* run resumes at job granularity via the cwltool cache only
    when inputs are byte-identical; show the range-based example instead.
    (b) Soften the CHANGELOG sentence "so failed or stopped runs can be
    resumed without redoing the successful stages" to match.
  - *Alternative:* if stage-level resume after a failed default run is wanted,
    the default path would need per-step progress during the single cwltool
    invocation (e.g. always drive stages individually, or poll the job cache)
    — both change the "default = single invocation" invariant, so for a draft
    the honest documentation is the right call.

**M2** — **`lib/python/picongpu/pypicongpu/runner.py:998-1002`** (skip loop) +
`picongpu_run` (simulation.py:527-535) — the persisted state carries no
fingerprint of the inputs that produced the recorded artifacts, so a run whose
inputs changed is silently skipped, reusing stale artifacts.
- After a completed run, `completed` stages are unconditionally skipped
  (runner.py:999). The state is authoritative about *nothing* regarding
  inputs. The public API correctly rejects flag changes after generation
  (simulation.py:530-534), but `workflow/input.yaml` is a plain file the user
  may edit (the `build_`/`run_` prefix convention exists precisely "in cases
  when one wants to run the steps individually", runner.py:606-608) — and
  editing it invalidates the state with zero detection.
  - *Evidence:* scratch repro (`/tmp/opencode/review-09/probe_a.py`, probe B):
    full run → edit `build_cmake` in `input.yaml` to `"v2"` →
    `sim.picongpu_run()` returns `None`, state file byte-identical, and the
    final `input/bin/picongpu` still contains `built-default` — the user gets
    no indication that their input change was ignored and the simulation was
    *not* re-run.
  - *Suggested fix:* store an input fingerprint per stage (or globally) in the
    state, e.g. in `StageState` add
    `inputs_digest: str | None = None` and set it to
    `hashlib.sha256(json.dumps(consumed_workflow_inputs, sort_keys=True).encode()).hexdigest()`
    in `_run_stage` / `_record_full_run` (the consumed inputs are exactly the
    string-sourced entries of the step specs, resolvable in
    `_resolve_step_inputs`). In `run_range`, after loading state, recompute the
    digest from `workflow_input_path` and downgrade `completed` →
    `invalidated` (with a logged message) for stages whose digest no longer
    matches. Coarse variant: one digest of the whole `input.yaml`; any change
    invalidates all stages — simpler, still eliminates the silent no-op.
  - *Alternative:* for the no-arg all-completed case, fall back to the legacy
    `self.run()` path and let the cwltool cache decide what to skip —
    restores "call again → it re-runs (cheaply) when inputs changed" without
    fingerprinting, but loses stage granularity and changes the observed
    behavior of an up-to-date re-run from no-op to cache-checked re-run.

### 2.3 Minor

**m1** — **`TASK-09-FINDINGS.md` (19 occurrences, e.g. :48, :363, :384)** — the
claim "`pre-commit run --all-files`: all hooks passed" (§12) is false; the
task's "Verification: Pre-commit green" is not met.
- *Evidence:* `/tmp/opencode/venvs/task-09/bin/pre-commit run --files <all 11
  changed files>` → `require-ascii` **Failed, exit 1** on
  `TASK-09-FINDINGS.md` (19 em-dashes `—`). All other hooks pass (ruff,
  ruff-format, trailing-whitespace, end-of-file-fixer, …). Ironic detail: the
  branch *did* fix the inherited `TASK-05-PR-PROPOSAL.md` em-dashes to make the
  hook pass, but left the new artifact doc non-ASCII — so `--all-files`
  fails on the file this very branch added.
  - *Suggested fix:* ASCII-ify `TASK-09-FINDINGS.md` (same `—`→`-`
    normalization as in `TASK-05-PR-PROPOSAL.md`) and actually run
    `pre-commit run --all-files` before claiming it in §12.

**m2** — **`lib/python/picongpu/pypicongpu/runner.py:261-351`**
(`DEFAULT_STAGE_PLAN`) + `lib/python/test/picongpu/quick/picmi/test_partial_workflow.py:442-466` —
nothing verifies the plan against the real `workflow.cwl`, and the "stability
test" is tautological.
- The adapter is by design "the single place that knows the current CWL
  steps", but it is plain data with no sync check. If `workflow.cwl` drifts
  (a step file renamed, an input renamed, a step added), full runs and
  partial runs silently diverge: the full run follows `workflow.cwl`, the
  per-step path follows the plan.
  - *Evidence:* scratch probes (`/tmp/opencode/review-09/probe_def.py`):
    (a) current plan *is* in sync (all plan step files exist in the template;
    all plan workflow-input names are defined in `workflow.cwl`; step-output
    refs map to the right producing stages — verified by parsing
    `templates/workflow/workflow.cwl`), so no live bug; (b) inserting a 5th
    `validate_step` into a scratch `workflow.cwl` runs it in the full run but
    the per-step resume never runs it again — silent divergence; (c) the
    shipped stability test only reassigns `runner.stage_plan` with a synthetic
    plan, i.e. it proves "the code accepts a different plan", not that the
    default plan survives a workflow change. (Renaming CWL step *ids* is in
    fact transparent — verified in scratch — because per-step execution
    bypasses `workflow.cwl`.)
  - *Suggested fix:* add a test that loads the *real*
    `templates/workflow/workflow.cwl` (yaml) and asserts, for every plan step
    spec: its `run` file exists in the template; every string input source is
    a workflow input; every `StageArtifactRef` points at an artifact recorded
    by the stage that implements the referenced workflow step; every step
    output in the workflow's `out:` list is covered. Re-frame
    `test_stability_future_workflow` to mutate a scratch `workflow.cwl`
    (rename/insert a step) plus a correspondingly updated plan, so the test
    exercises the actual failure mode (plan/workflow drift) instead of
    self-consistency.

**m3** — **`lib/python/picongpu/pypicongpu/runner.py:839-855`** (`_run_cwl_step`) —
only `WorkflowStatus` is caught, so cwltool *load/validation* failures surface
as raw `cwltool` exceptions instead of the documented `WorkflowStageError`.
- *Evidence:* scratch probe: rename `steps/build.cwl` → `compile.cwl` in a
  scratch setup (plan unchanged) → `run_range(up_to=Stage.build)` raises
  `cwltool...ValidationException`, not `WorkflowStageError`; the failure is
  loud (good), but the error contract stated in the docstrings ("wrapped in
  `WorkflowStageError` for cwltool failures") does not hold for the most
  likely drift scenario.
  - *Suggested fix:* wrap the whole
    `WorkflowFactory(...).make(str(step_path))(**inputs)` expression in
    `except Exception as error: raise WorkflowStageError(...) from error`
    (keep the specific `WorkflowStatus` message), so stage execution has one
    error type.

### 2.4 Nits

**n1** — **`lib/python/picongpu/pypicongpu/runner.py:386`** — the state
`version` field is never consulted (probe: a state file with `version: 99`
loads without comment). It is a placeholder for migration logic that does not
exist; either implement a check (reject/`reset` on unknown version) or drop
the field until it means something.

**n2** — **`lib/python/picongpu/pypicongpu/runner.py:965-969` vs `:997-1003`** —
`run_range`'s return value is shape-inconsistent: the legacy path returns the
full-workflow outputs dict, the per-step path returns the last executed
stage's artifacts or `None`. Inconsequential through `picongpu_run` (which
discards it), but the Runner-level contract ("Returns the artifacts of the
last executed stage, or None") is violated by the legacy branch.

## 3. Requirement traceability

| # | Requirement (from task file) | Status | Where / note |
|---|---|---|---|
| 1 | PICMI-level interface to execute subsets of the CWL workflow | met | `picongpu_run(up_to/from_/force)` (simulation.py:506-535) → `Runner.run_range` (runner.py:930-1003) |
| 2 | Resume after a failed/partial run without redoing successful steps | partial | Works for range-started runs (verified); a failed *default* run records no state, and the doc example claiming otherwise is false → M1 |
| 3 | Run `build` without `submit` / `submit` after out-of-band build / `organize_output` after manual intervention | met (API level) | `up_to=Stage.build`, `from_=Stage.submit`, `force=Stage.collect`; real-`bash`-preset staging caveat → FYI |
| 4 | Implemented in the Python package, with tests, and documented | met | 8 tests (`test_partial_workflow.py`), `partial_workflow.rst` + toctree + cross-ref |
| 5 | Public interface must NOT address CWL steps by name (stable across step number/name changes) | met | State keyed by stage, outdirs `step-N` numbered; step-id renames verified transparent (scratch probe F1); plan is the single internal change point, but unvalidated → m2 |
| 6 | Python API only (no CLI) | met | diff touches only `lib/python` + docs/CHANGELOG/task md; no CLI, no C++/templates |
| 7 | Explore solution space → best option → draft implementation | met | FINDINGS §5 compares per-step vs sub-workflow vs flags-only, recommends per-step with trade-offs |
| 8 | Stage→step adapter as the single place knowing the current steps | met (partial) | `StagePlan`/`DEFAULT_STAGE_PLAN` (runner.py:233-351); currently in sync with the template (verified) but no sync test → m2 |
| 9 | State file in `run_dir/.workflow_state.json`, stage-keyed; `force` re-runs | met | atomic tmp+rename writes; `force` invalidates transitive dependents (verified, incl. out-of-range `collect` marked `invalidated`) |
| 10 | Missing prerequisites → error (safer default) | met | `WorkflowPrerequisiteError` naming the missing stages; verified; nothing executed before the error |
| 11 | `step()` semantics kept or documented | met | docstring now explains time-stepping vs workflow stages (simulation.py:366-375) |
| 12 | Tests: range runs, state records, second run skips, prerequisite error, full unchanged, stability test | met (stability test weak) | all 8 present and green; stability test is plan-swapping, not workflow-varying → m2 |
| 13 | Docs: workflow/running-simulation documentation updated | partial | page added, but the resume-after-failure example is inaccurate → M1 |
| 14 | Verification: `pytest quick/` green | met | re-ran: 185 passed, 2 xfailed, 1 xpassed (+3499 subtests) = 177 baseline + 8 new |
| 15 | Verification: manual scenario (build; submit; collect; final artifacts identical to full run) | met | `test_incremental_stage_scenario` + independent scratch repro (probe A: final artifacts identical, marker flows build→submit→collect) |
| 16 | Verification: Pre-commit green | missed | `require-ascii` fails on the branch's own `TASK-09-FINDINGS.md` → m1 |

## 4. Claim verification (author artifact)

| Claim (from TASK-09-FINDINGS.md / docs) | Re-verified? | Result / delta |
|---|---|---|
| `pytest quick/ -q`: 185 passed, 2 xfailed, 1 xpassed (baseline 177; +8 new tests) | yes | **Confirmed exactly** (185 passed, 2 xfailed, 1 xpassed, 3499 subtests; new file has 8 tests) |
| `pre-commit run --all-files`: all hooks passed | yes | **FALSE** — `require-ascii` fails (exit 1) on `TASK-09-FINDINGS.md` itself, 19 em-dashes; all other hooks pass → m1 |
| "The default plan mirrors the `in:`/`out:` bindings of `workflow.cwl` (steps, lines 112-155) exactly, incl. `destination_path`" | yes | **Confirmed** by parsing the real template and comparing every binding (scratch probe E) |
| "Second no-arg run must not redo (or even rewrite) completed stages (state file byte-identical)" | yes | **Confirmed** — no state write happens on the all-completed path; file untouched |
| "Stability test passed — adapter absorbs a step inserted inside an existing stage without any API change" | yes | Passes, but the test varies the *plan*, not the workflow (tautological) → m2; the real workflow-change modes were probed in scratch (step-id rename transparent; step-file rename fails loudly; extra workflow step → silent full/partial divergence) |
| Doc: "first attempt failed inside 'submit' … after fixing the problem: only 'submit' and 'collect' are re-run" (`partial_workflow.rst:74-82`) | yes | **FALSE for the default call** — a failed default run leaves no state file; second call re-runs the full workflow, job-cache permitting → M1 |
| "Previously a second `picongpu_run()` crashed in `generate()`'s assert; it now resumes" | yes | **Confirmed** — second call no longer crashes; it skips completed stages |
| "Flags after generation raise a clear `ValueError`; the state is left intact" | yes | **Confirmed** (scratch probe + test 7) |
| §9 "default (no args) = full pipeline, backward compatible" / "single cwltool invocation … byte-for-byte the full workflow as today" | yes | **Confirmed for fresh runs** (legacy path = single `workflow.cwl` invocation; only additive: the state file written afterwards) |
| §13 "the `docs/source/python_package/` pages from PR 5731 do not exist on this lineage" | yes | **Confirmed** — directory absent |
| §14 open questions still genuinely open | yes | All 7 are honestly deferred, not silently decided in code (each has a chosen default implemented + listed alternative) |
| §5 "per-step submit … stable for partial runs exactly as for the full run" | yes (partially) | Path stability: **confirmed** (same `destination_path` flows into per-step submit). But see FYI: for the default `bash` preset this wording understates the submit→collect staging-ordering hazard, which partial execution turns from a race into a deterministic failure |

## 5. Design discussion

**Option choice (per-step cwltool vs sub-workflow generation).** Per-step
invocation through the existing `cwltool.factory` is the right call for this
codebase: the steps are already self-contained tools, the default path stays
byte-for-byte the historical single invocation, and the wiring becomes small
declarative data (`StageStepSpec.inputs`) that is inspectable and testable.
Sub-workflow generation (option 2) would require hand-writing CWL serialization
and would change the default path too. The cost of option 1 — re-implementing
step→step wiring in Python — is real but bounded; the missing complement is a
**plan↔workflow sync test** (m2), which would turn "keep the adapter in sync"
from a tribal obligation into a CI-enforced invariant. A maintainer weighing
this should also note that per-step execution deliberately bypasses
`workflow.cwl` validation: a workflow.cwl change that breaks only the full-run
path (or only the per-step path) is possible today.

**Stability mechanism.** The core promise is genuinely achieved at the levels
that matter: the API, the state file, and the on-disk layout (`step-N`
numbered outdirs) contain no CWL step names, so step *id* renames and step
*reordering/insertion within a stage* are transparent (verified in scratch:
renamed step ids → both full and partial runs unaffected; author's in-stage
insertion → works). The stable boundary is the `Stage` enum + plan data. What
the design does *not* guarantee — and should document — is that the plan
tracks the templates automatically; that is a maintainer update, currently
untested (m2). The "membership may grow, meaning is stable" contract in the
`Stage` docstring is the right statement.

**Resume semantics and the state file's blind spots.** Two asymmetries are
worth a maintainer's attention. First, the state is only populated by
per-step execution or by a *successful* single invocation (M1): a failed
default run is invisible to the state layer, and resume falls back to the
cwltool job cache, which is keyed by input bytes — so "the fix" (changed
inputs) defeats it. Second, the state is authoritative about *nothing*
regarding inputs (M2): there is no fingerprint tying recorded artifacts to the
`input.yaml` that produced them. Together these make "skip completed stages"
a pure status lookup. The cwltool cache had exactly the missing property
(input-keyed); the draft keeps it as a "safety net" for job reuse but the
stage layer bypasses it for skip decisions. Input fingerprinting (sketch in
M2) is the minimal fix that makes the state layer honest.

**Force/invalidation.** Transitive dependent invalidation is the correct
default (new binaries ⇒ stale job results), persisting `invalidated` status
keeps the state auditable, and out-of-range invalidated stages are marked but
not executed — all verified. The one question left for the requester (§14.3)
is legitimate; the implemented default is defensible.

**Interaction with task 05 (see FYI).** The per-step submit passes the same
stable `destination_path` (run dir) as the full run, so task-05's root-cause
fix carries over to partial runs — that part works. What does not carry over
cleanly is the *ordering* assumption: for the default `bash` preset the
submitted background job needs `$TBG_dstPath/input/bin`, which only
`collect`/`organize_output` stages into the run dir. The full workflow hides
this in a race; "submit now, collect later" — the task's own use case — makes
it deterministic. The draft neither acknowledges nor mitigates this; at a
minimum the docs/FINDINGS should, and a later iteration might move the
`input/` staging ahead of job launch (e.g. into the submit stage) for local
presets.

## 6. Prioritized next steps

1. Fix the false resume documentation (M1): rewrite
   `partial_workflow.rst:66-82` with a range-based failure/resume example,
   state explicitly that a failed *default* run resumes only via the cwltool
   job cache when inputs are unchanged, and align the CHANGELOG sentence.
2. Add input-change detection to the state (M2): per-stage (or global)
   `inputs_digest` in `.workflow_state.json`, invalidating `completed` stages
   whose inputs changed, with a logged warning — or, minimally, treat the
   no-arg all-completed case as "re-run the legacy full workflow" so changed
   inputs are never silently ignored.
3. Make pre-commit actually green (m1): ASCII-ify `TASK-09-FINDINGS.md` and
   run `pre-commit run --all-files` before re-claiming it in §12.
4. Add the plan↔workflow sync test and re-frame the stability test around a
   mutated scratch `workflow.cwl` (m2).
5. Wrap cwltool load/validation errors in `WorkflowStageError` (m3).
6. Nits: implement or drop the state `version` check (n1); make
   `run_range`'s return consistent across both paths (n2).
7. Before graduating from draft: resolve the §14 open questions with the
   requester, and add the task-05 `bash`-preset staging-ordering caveat to the
   docs (FYI below).

## FYI (inherited from base, not scored here)

- **Task-05 C1 impact (assessed as requested).** With the default `bash`
  submit system the generated `submit.start`
  (`etc/picongpu/bash/mpiexec.tpl:36,56`) does `cd $TBG_dstPath` and runs
  `$TBG_dstPath/input/bin/picongpu`; `$TBG_dstPath` is the run dir (task-05's
  `destination_path`), and `run_dir/input/` is created only by
  `organize_output` (collect). In the full workflow this is the race flagged
  in task 05's review (inherited, not re-scored). Task-09's stage interface
  *widen*s it: verified in scratch that after `run_range(up_to=Stage.submit)`
  (no collect) `run_dir/input` does not exist, so for the `bash` preset the
  background job deterministically cannot find its binary — the "submit after
  an out-of-band build" / "organize_output after manual intervention" use
  cases fail for local runs unless `collect` follows immediately or the user
  stages `input/` by hand. The draft's FINDINGS §5 claim that partial submit
  is "exactly as for the full run" is optimistic in this respect. HPC presets
  have the related (pre-existing) issue that `$TBG_dstPath` must already hold
  the input files on the cluster — one of the future "remote execution steps"
  the stage design anticipates.
- The branch's edits to the inherited `TASK-05-PR-PROPOSAL.md` (em-dash →
  hyphen normalization) are disclosed in FINDINGS §12 and harmless; they exist
  because the base branch itself fails `require-ascii`.
- Pre-existing stale hooks `run_step_path`/`gather_results_script_path` and
  the class docstring's phantom `build()` are correctly left untouched and
  listed as deferred (FINDINGS §11) — agreed.
