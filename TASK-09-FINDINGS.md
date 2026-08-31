# TASK-09 Findings: Partial Workflow Execution in PICMI (draft)

Branch: `task-09-partial-workflow` (base: `task-05-cwl-cache-ref-purge` @ `33d89313f`)

Status: **draft implementation + design note** (exploratory task convention:
iterate on, not PR-perfect).

## 1. What was delivered

- `pypicongpu/runner.py`: a stable `Stage` vocabulary, a stage->CWL-step
  adapter (`StagePlan` + `DEFAULT_STAGE_PLAN`), a stage-keyed persisted
  workflow state (`run_dir/.workflow_state.json`), and `Runner.run_range()`
  which executes a range of stages.
- `picmi/simulation.py`: `Simulation.picongpu_run(up_to=..., from_=...,
  force=...)`; `step()` keeps its (full-run) semantics and now documents why.
- Exports: `picongpu.picmi.Stage`, `picongpu.pypicongpu.{Stage,
  DEFAULT_STAGE_PLAN, WorkflowPrerequisiteError, WorkflowStageError}`.
- Tests: `lib/python/test/picongpu/quick/picmi/test_partial_workflow.py`
  (8 tests, tiny echo CWL steps).
- Docs: `docs/source/usage/picmi/partial_workflow.rst` (+ toctree entry,
  cross-reference in `picmi/intro.rst`).
- CHANGELOG entry (draft feature note).

## 2. The stable stage vocabulary (primary design point)

**Decision: the public API speaks in coarse-grained *stages* (milestones),
never in CWL step names.** The number/names of `workflow.cwl` steps may
change (e.g. remote-execution upload/download steps get added); stages
absorb that change.

Current stages, in execution (topological) order:

| stage     | meaning                                    | current CWL step(s)            |
|-----------|--------------------------------------------|--------------------------------|
| `build`   | compile the executable (pic-build)         | `build_step`                   |
| `prepare` | prepare the submission (tbg)               | `prepare_submission_step`      |
| `submit`  | launch the job on the batch system         | `submit_step`                  |
| `collect` | organize the results into the run directory| `organize_output_step`         |

Dependencies: `submit` needs `build` + `prepare`; `collect` needs `build` +
`submit`. Today each stage maps 1:1 onto a CWL step; the adapter supports
N steps per stage (see the stability test, section 12), so a future
`submit` = [upload-to-cluster, submit, download] is a mapping change only.

Names chosen per the task proposal (`prepare`, `build`, `submit`,
`collect`). Rationale: they describe *what is achieved* (a milestone), not
*how* (a tool invocation). `prepare` is intentionally not
`prepare_submission` — the stage survives tbg being replaced by a different
submission-preparation mechanism.

## 3. Public API — chosen shape

```python
sim.picongpu_run()                              # full pipeline (unchanged default)
sim.picongpu_run(up_to=Stage.build)             # everything up to and incl. build
sim.picongpu_run(from_=Stage.submit)            # submit + collect; earlier stages
                                                # must already be completed
sim.picongpu_run(from_=Stage.submit, up_to=Stage.submit)  # exactly one stage
sim.picongpu_run(force=True)                    # re-run everything
sim.picongpu_run(force=Stage.build)             # re-run build + dependents
```

- `up_to`/`from_` accept `Stage` or the bare string (`"build"`).
- Default (no args) = full pipeline, backward compatible (section 9).

**Alternatives considered:**

- `run(stages=[...])` (explicit set): more general, but (a) silently accepts
  sets that are not "downward closed" (e.g. `[submit]` without `build`)
  forcing an implicit prerequisite policy anyway, (b) is awkward for the two
  dominant use cases ("build only", "everything up to submit"), (c) is less
  readable for resume (`stages=[submit, collect]`). Rejected for the draft.
- Milestone-only `run("submit")` = "everything up to and including submit":
  covers "build only" and "run up to X", but not "start at X" (resume from
  a known-good point) and not "exactly one stage" without also re-running
  prerequisites. `from_`/`up_to` generalize it: `up_to=Stage.submit` *is*
  the milestone call. Rejected in favour of `up_to`/`from_`.
- A `Runner.run_stage(...)`-level API: kept available at the runner level
  (`Runner.run_range`) for tests/advanced use; the PICMI level is the public
  surface (Python API only, per the requester).

Open question for the requester: confirm the argument names `up_to`/`from_`
(`from` is a Python keyword, hence the trailing underscore — an alternative
would be `since=`/`until=`).

## 4. Stage -> step adapter (implementation)

The adapter is a pure-data pydantic model, the single place that knows the
current `workflow.cwl` layout:

- `StagePlan`: `order` (topological stage order) + `stages` (name -> spec).
- `StageSpec`: `depends_on` + `steps` (ordered list of step specs).
- `StageStepSpec`: `step` (CWL step name, for diagnostics), `run` (CWL file
  relative to the workflow dir), `inputs` (step input -> source), `outputs`
  (stage artifact name -> step output name).
- Input sources: a bare string = workflow input (from `input.yaml`);
  `StageArtifactRef(stage, artifact)` = artifact recorded by a completed
  stage; `StepOutputRef(step, output)` = output of a preceding step of the
  same stage (needed so a stage can grow steps over time, e.g. upload ->
  submit chaining).
- `Runner.stage_plan` is a (reassignable) pydantic field defaulting to
  `DEFAULT_STAGE_PLAN`; the tests inject a modified plan to simulate a
  "future" workflow.

The default plan mirrors the `in:`/`out:` bindings of `workflow.cwl`
(steps, lines 112-155) exactly, including the task-05 `destination_path`
input.

## 5. Execution mechanisms — comparison and recommendation

**Option 1 (chosen): per-step cwltool invocations.** Each stage's steps are
run as standalone `steps/*.cwl` tools through `cwltool.factory.Factory`, in
dependency order; outputs of earlier stages are re-staged as File/Directory
inputs from the state file; a cwltool `cachedir` is shared with the full
run.

- Pros: the CWL steps are already self-contained tools; no CWL generation;
  input wiring is a small, testable Python dict; the cwltool job cache keeps
  working per step; failures are localized to one stage.
- Cons: re-implements the step->step wiring in Python (mitigated: it is
  declarative data in the plan, verified by the stability test); per-step
  outdirs must be managed (private `.stage_outputs/<stage>/step-N` dirs).

**Option 2: sub-workflow generation.** Emit narrowed copies of
`workflow.cwl` (pruned steps, missing inputs replaced by File/Directory
inputs pointing at on-disk artifacts) and hand them to cwltool.

- Pros: cwltool does the intra-sub-workflow wiring; DAG validated by cwltool.
- Cons: requires programmatic CWL *serialization* (cwltool/salad has no
  clean writer; we would hand-generate YAML), which is fragile, hard to
  keep in sync with the templates, and duplicates the same state-file wiring
  for the pruned inputs. More code, more failure modes, for no user-visible
  benefit at this granularity.

**Option 3: cwltool flags only.** Rejected: cwltool cannot select individual
workflow steps (`--do-work` etc. only control staging/debugging).

**Recommendation: Option 1**, for the reasons above. It also keeps the
*default* path byte-for-byte identical (section 9), which option 2 could not
do as cleanly (the default would also become a generated sub-workflow).

**Composition with the cwltool job cache:** the legacy single-invocation
full run (`Runner.run()`) keeps the shared `.cwl_cache` as before (job-level
resume safety net). Per-step invocations deliberately do not use the job
cache (`cachedir=None`): the stage state file is the skip mechanism of the
per-step path, and invoked steps always execute freshly. This is required
for correctness, not just an optimization: cwltool's cache key does not
cover the *contents* of `Directory` inputs, so a re-run stage that
regenerates an artifact directory in place (same `.stage_outputs` path)
would otherwise let its dependents hit a stale cache entry (verified before
the fix: `force=Stage.build` after changing `build_cmake` produced the new
binary, but the submit step's *cached* tbg still contained the old one).

**Composition with task 05:** the per-step `submit` run passes the same
stable `destination_path` workflow input (the run dir) into `submit.cwl`, so
`tbg/submit.start`/`link_results.sh` are stable for partial runs exactly as
for the full run; the `organize_output` sed-based rewrite remains a safety
net for per-step runs too (a per-step submit also runs inside a
`.cwl_cache` job dir).

## 6. State file format

`run_dir/.workflow_state.json` (written atomically via tmp+rename):

```json
{
  "version": 1,
  "updated_at": "2026-08-29T02:57:45.619884",
  "stages": {
    "build": {
      "status": "completed",
      "updated_at": "2026-08-29T02:57:45.608147",
      "inputs_digest": "9f86d081884c7d65...",
      "artifacts": {
        "bin_directory": {"class": "Directory", "location": "/.../run_dir/.stage_outputs/build/step-1/bin"}
      }
    },
    "submit": {
      "status": "completed",
      "updated_at": "...",
      "inputs_digest": "3a7bd1e02c9f48ab...",
      "artifacts": {
        "tbg_directory": {"class": "Directory", "location": "/.../run_dir/.stage_outputs/submit/step-1/tbg"},
        "submission_information": {"class": "File", "location": "/.../run_dir/.stage_outputs/submit/step-1/submission_information.txt"},
        "link_results_script": {"class": "File", "location": "/.../run_dir/.stage_outputs/submit/step-1/link_results.sh"}
      }
    }
  }
}
```

Rules:

- **Keyed by stage names only** (never CWL step names); per-step outdirs are
  numbered (`step-1`, `step-2`, ...) for the same reason, so the on-disk
  layout also survives step reorganisation.
- Artifacts are reduced CWL file objects (`class` + `location`, plain
  absolute paths) so they can be re-staged verbatim as inputs of later
  steps.
- Statuses: `running` (crash marker), `completed`, `failed`, `invalidated`
  (a dependent of a forced stage). Only `completed` counts as done.
- `inputs_digest`: sha256 of the workflow inputs (from `workflow/input.yaml`)
  the stage consumed, recorded when it runs. On a re-run, a completed stage
  whose digest no longer matches (or has none, e.g. a state file from before
  digest recording) is treated as stale: it and its transitive dependents are
  invalidated and re-run. This is how an edit of `input.yaml` after a
  completed run is detected (without it, the run would silently skip every
  stage and reuse stale artifacts).
- Unreadable/foreign state files are logged and treated as empty. A state
  file whose `version` is not 1 (the only version this runner writes and
  reads) is likewise logged and ignored: it is treated as empty, so the next
  run re-records it (the check makes the `version` field a migration hook for
  future format changes instead of a dead field).
- The file is safe to delete (fresh start); `Runner.reset_workflow_state()`
  does it programmatically.

**Full-workflow runs are recorded too.** After a legacy single-invocation
full run, all four stages are marked `completed`; the artifacts are recorded
at their stable organized locations in the run dir (`input/`, `tbg/`,
`submission_information.txt`, `link_results.sh`), and `build.bin_directory`
at `run_dir/input/bin` (organize_output.sh copies the binaries there). This
makes "resume after a full run" consistent with "resume after partial
runs".

## 7. Resume and failure semantics

- Re-run with no args: stages recorded `completed` are skipped (only if the
  workflow inputs they consumed are unchanged, see section 6); the first
  incomplete stage runs (and everything after it).
- Changed workflow inputs invalidate the affected stages and their
  dependents (logged), so an edited `input.yaml` is never silently ignored.
- A stage marked `running`/`failed`/`invalidated` is re-run.
- While a stage runs, the state is updated `running` -> (on success)
  `completed` with artifacts; on failure the stage is marked `failed` and
  the exception propagates (wrapped in `WorkflowStageError` for cwltool
  load and execution failures).
- `force=True`: re-run every stage of the range. `force=Stage`/list: re-run
  those stages; **all transitive dependents are invalidated** (marked
  `invalidated` in the state, persisted) and re-run if they are in the
  range. Rationale: downstream artifacts are stale once an input stage is
  redone (new binaries -> old job results).
- Crash during a run: the interrupted stage stays `running`; the next run
  re-runs it (and its dependents, which were never completed).

## 8. Missing prerequisites: decision

**Error, not auto-run.** Requesting a stage whose prerequisites are not
completed (and not in the requested range) raises
`WorkflowPrerequisiteError` naming the missing stages. Rationale: implicit
prerequisite execution would silently start long/irreversible work (a full
recompile, a cluster submission) that the user did not ask for; the error
message points at the exact call that would satisfy it. (Auto-run is an
easy policy swap later if desired.)

## 9. Backward compatibility

- `Runner.run()` is **unchanged** (single cwltool invocation of
  `workflow.cwl`).
- `picongpu_run()` with no stage args and no recorded state takes exactly
  the legacy path: `generate()` + `run()`, i.e. byte-for-byte the full
  workflow as today (a new `.workflow_state.json` is written afterwards,
  which is additive).
- Previously, a *second* `picongpu_run()` on the same setup crashed in
  `generate()`'s "setup directory must not exist" assert; it now resumes
  (skips completed stages) — strictly less surprising.
- New: `picongpu_run(flags=...)` after generation raises a clear `ValueError`
  instead of the same confusing assert (changing workflow flags would
  invalidate the recorded state; the existing `generate(exist_ok=True)`
  path is not re-entrant anyway — the renderer refuses to overwrite
  rendered files, a pre-existing limitation left untouched).
- `step()` is unchanged in behaviour (full run only) and now documents that
  time-stepping and workflow stages are orthogonal.

## 10. Interactions with sibling tasks

- **Task 05** (base): built on top; per-step runs reuse `destination_path`
  and the organize_output rewrite (section 5). Nothing resurrected.
- **Task 11** (pre-existing bug): `TBGFlags.overwrite_vars` is a `list`
  while the CWL input `run_overwrite_vars` is `string?`, so
  `picongpu_run(o=[...])` is rejected by cwltool. This draft does **not**
  touch that path (the plan passes the `run_overwrite_vars` workflow input
  through verbatim, same as the full workflow); fixing it is task 11's.
  Note for task 11: after a fix, the value will flow into the per-step
  `prepare` run through the same `input.yaml` value, so no extra work there.

## 11. What the draft implements vs defers

Implemented:

- stage vocabulary + adapter, state file, range API, resume, force with
  dependent invalidation, prerequisite errors, full-run state recording,
  PICMI exposure, tests (incl. stability), docs, changelog.

Deliberately deferred (open for the next iteration):

- CLI surface (requester: Python API only for now).
- Artifact-existence validation: the state is authoritative; if the user
  deleted artifacts manually, a re-run of a *later* stage would re-stage
  missing files and cwltool would error. A `verify`/`--check` mode could be
  added.
- Concurrency: `build` and `prepare` are independent but run sequentially
  (cwltool's SingleJobExecutor; parallelism could come later without API
  change).
- `stages=[...]` set syntax and milestone shorthand (`run("submit")`) —
  see open questions.
- Stale-artifact GC of `.stage_outputs/<stage>/step-N` after plan changes.
- Pre-existing stale hooks `run_step_path`/`gather_results_script_path`
  (point to non-existent files, unused) — left untouched.

## 12. Tests and results

`lib/python/test/picongpu/quick/picmi/test_partial_workflow.py` (8 tests)
uses tiny echo CWL steps (same input names/types as the production steps)
installed into the generated setup dir:

1. `test_full_run_default_and_state` — default run places final artifacts in
   the run dir like today; state file is stage-keyed, all stages completed,
   artifacts are `class`+`location` objects; no step names in the file.
2. `test_second_run_skips_completed` — a second no-arg run does not redo or
   even rewrite completed stages (state file byte-identical).
3. `test_range_build_only` — `up_to=Stage.build` completes exactly `build`;
   artifact lands in `.stage_outputs/build/step-1/bin`.
4. `test_incremental_stage_scenario` — the task's manual scenario:
   build-only, then prepare-only, then submit-only
   (`from_=up_to=submit`), then collect-only (`from_=collect`); state grows
   stage by stage and final artifacts match a full run (the built-binary
   marker flows build -> submit -> collect).
5. `test_missing_prerequisite_is_an_error` — `from_=Stage.submit` on a fresh
   run raises `WorkflowPrerequisiteError` (naming `build, prepare`), and
   nothing is executed; `from_` after `up_to` raises `ValueError`.
6. `test_force_stage_invalidates_dependents` — full run, then
   `run_range(up_to=Stage.submit, force=Stage.build)` with a changed build
   input: build re-runs with new content, submit re-runs (invalidated),
   prepare is skipped (state entry untouched), collect is marked
   `invalidated` (stale, outside the range).
7. `test_flags_after_generation_are_rejected` — flags after generation raise
   a clear `ValueError`; the state is left intact.
8. **Stability test** `test_stability_future_workflow` — a fake "future"
   workflow where the `submit` stage gains an extra `upload` step chained
   into `submit` via `StepOutputRef`: the public API (stage names, ranges,
   state file) works unchanged; the in-stage wiring is verified (the upload
   output reaches the final `tbg`); the state file contains no step names.
   **Result: passed** — the adapter absorbs a step inserted inside an
   existing stage without any API change.

Results (venv `task-09`):

- `python -m pytest quick/ -q`: **185 passed, 2 xfailed, 1 xpassed**
  (baseline on the branch: 177 passed, 2 xfailed, 1 xpassed; +8 new tests,
  no regressions; includes task 05's 3 workflow tests).
- `pre-commit run --all-files`: **all hooks passed** (after replacing two
  non-ASCII characters in the inherited `TASK-05-PR-PROPOSAL.md` task
  artifact, which made the base branch fail the `require-ascii` hook).

## 13. Documentation

- New self-contained page: `docs/source/usage/picmi/partial_workflow.rst`,
  added to the usage/PICMI toctree (`docs/source/usage/picmi/index.rst`)
  and cross-referenced from `picmi/intro.rst`.
- **Post-PR-5731 note:** the `docs/source/python_package/` pages from PR
  5731 do not exist on this lineage (per the task brief, no
  `docs/source/python_package/` files were created). Once PR 5731 lands,
  the content of `usage/picmi/partial_workflow.rst` should be moved or
  linked into the `python_package` running-simulation page (the PR proposal
  must carry this note).

## 14. Open questions for the requester

1. **Stage names**: confirm `prepare`, `build`, `submit`, `collect` and the
   execution order `build -> prepare -> submit -> collect` (ranges are
   defined on this order; `up_to=Stage.prepare` means "build + prepare").
2. **Range syntax**: `up_to`/`from_` (chosen) vs `stages=[...]` vs milestone
   shorthand `run("submit")`. Can any of the alternatives replace or
   complement the draft's signature? (`from_` vs `since=`/`until=` naming.)
3. **force semantics**: dependent invalidation (chosen) vs "re-run only the
   forced stage and leave dependents recorded-complete".
4. **Missing prerequisites**: error (chosen, safer) vs auto-run of missing
   prerequisites.
5. **Final-stage placement**: the last stage's outputs land in the run dir
   root (like the full workflow); other stages' outputs in
   `run_dir/.stage_outputs/...`. Acceptable?
6. **State on flag change**: flags after generation are rejected (chosen;
   regeneration is not re-entrant yet — pre-existing renderer limitation).
   Alternative: auto-regenerate + state reset (needs the renderer fix).
7. Should `Runner` expose a `verify()` that re-checks recorded artifacts
   on disk (deferred)?

## 15. Risks / known limitations

- The stage vocabulary is a **new public commitment**; renaming a stage
  later breaks the state file (mitigation: the state `version` field is
  checked on load -- unknown versions are ignored, cf. section 6 -- plus the
  "membership may grow, meaning is stable" contract documented in the
  `Stage` docstring).
- Per-step outdirs named `step-N`: if a stage's steps are renumbered, stale
  directories linger until the next run of that stage (harmless; they are
  wiped before use).
- State authority: manually deleted artifacts are not detected (section 11).
- The draft records full-workflow artifacts at the *organized* locations;
  if `organize_output.sh` ever stops copying `bin` into `input/`, the
  recorded `build.bin_directory` location would need updating (single place:
  `Runner._record_full_run`).
- `picongpu_run` now skips `generate()` when the workflow input exists; any
  code that relied on the old (crashing) double-generate behaviour would
  notice — none exists in the repo/tests.
