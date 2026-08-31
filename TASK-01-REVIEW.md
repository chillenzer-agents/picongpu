# Review — Task 01: PR 5731 — convert `python_package` doc snippets to tested code

- **Branch:** `task-01-docs-tested-snippets` (tip `6d9f158ab`, base `85365feb2` = tip of `origin/picmi-docs`)
- **Reviewed:** 2026-08-31 · **Scope:** 7 commits (6 code + 1 artifact), 38 files, +1395/−249
- **Verdict:** REQUEST CHANGES — the snippet system itself is sound and every local gate re-verifies, but C1 means the new `docs-snippets` CI job (the task's central deliverable) fails deterministically on its first real GitLab run and never reaches the docs build.

## 1. Summary

The branch converts every code block in `docs/source/python_package/` into real scripts under `docs/source/python_package/snippets/` (10 Python, 15 bash) rendered via `literalinclude`, executed by a pytest suite (`run_snippet.py` harness + `test_snippets.py`), and glued together by a new `docs-snippets` GitLab job that also builds Sphinx and fails on missing includes. The design faithfully follows the task's alpaka-inspired evaluation, the correctness fixes against the real package are substantial, and all local gates re-verified exactly (snippet suite 25 passed; quick gate 174/2/1 == base; sphinx build with 0 warnings in `python_package/`; pre-commit all-pass). The blocking problem is that the CI job's profile-check step uses a heredoc whose terminator is indented, so as committed the job cannot run at all (C1). Secondary: the profile check's `PICSRC` assertion is vacuous because the env script exports it first (M1); the "bash snippets are executed for real" wording overstates what actually happens (m1); the optimizer test is self-referential with constants duplicated between harness and test (m2).

## 2. Findings

### 2.1 Critical

**C1** — ``.gitlab-ci.yml:237-265`` (docs-snippets job, profile-check block): the heredoc terminator is indented, so the job's script never parses as intended and the job cannot succeed.
- The block runs `python3 - <<'PY'` at line 241 with the closing `PY` at line 261 indented 6 spaces (required, since inside a YAML `- |` block every line is indented). In bash, a quoted here-document terminator must begin at column 0; indented, it is *not* a terminator. The heredoc therefore runs to the end of the file, python3 receives the trailing lines (`source setup/workflow/scripts/picongpu.profile`, the two `test -n` lines, the `echo`) as part of its stdin script, and fails. Worse, GitLab concatenates all `script:` entries into a single shell script, so the unterminated heredoc also swallows **all subsequent job steps** — `doxygen` (line 268), `sphinx-build` (line 269), and both grep gates (lines 271-276). The job deterministically fails on its first real run and never builds the docs.
  - *Evidence:* the block was extracted verbatim to `/tmp/opencode/review-01/actual-block.sh` (identical to `.gitlab-ci.yml:237-265` plus `set -e`).
    - `bash -n actual-block.sh` → `warning: here-document at line 5 delimited by end-of-file (wanted 'PY')` (note: `bash -n` exits 0 — the warning is the only static signal, and a YAML parse of the job sees nothing wrong either).
    - Runtime (`PATH=<task venv>/bin:$PATH bash actual-block.sh`): exit 1, output is exactly
      ```
      File "<stdin>", line 1
          from pathlib import Path
      IndentationError: unexpected indent
      ```
      — `profile check OK` is never printed and no step after the heredoc executes.
    - Minimal repro `/tmp/opencode/review-01/heredoc-test.sh` (heredoc body, indented `PY`, `echo "step after"`): prints `step before`, then `IndentationError` (python's stdin includes the line `    PY`), `step after` is never executed, exit 1 — demonstrating the swallowing of subsequent script lines.
  - *Suggested fix:* move the whole profile check into a checked-in script, e.g. `share/ci/docs_snippets_profile_check.sh`:
    ```bash
    #!/bin/bash
    set -euo pipefail
    cd "$(mktemp -d)"
    printf 'preset = "bash"\n' > .picongpurc.toml
    PIC_RC=$PWD/.picongpurc.toml python3 - <<'PY'
    from pathlib import Path
    from picongpu import picmi
    sim = picmi.Simulation(max_steps=1, solver=picmi.ElectromagneticSolver(
        method="Yee", cfl=0.95, grid=picmi.Cartesian3DGrid(
            number_of_cells=[16, 16, 16],
            lower_bound=[0.0, 0.0, 0.0], upper_bound=[1e-5, 1e-5, 1e-5],
            lower_boundary_conditions=["periodic"] * 3,
            upper_boundary_conditions=["periodic"] * 3)))
    sim.write_input_file(Path("setup"))
    PY
    source setup/workflow/scripts/picongpu.profile
    test -n "$PIC_BACKEND"
    test -n "$PICSRC"
    echo "profile check OK: PIC_BACKEND=$PIC_BACKEND PICSRC=$PICSRC"
    ```
    (a column-0 `PY` is legal in a normal file), and replace the `- |` block in the job with `- $CI_PROJECT_DIR/share/ci/docs_snippets_profile_check.sh` (plus the `unset PICSRC` from M1 inside the script). Alternative without a new file: `python3 -c '...'` or `printf '%s\n' ... > gen.py && python3 gen.py`. Whichever is chosen, re-run a local dry-run of the **actual** job script list (extract the job's `script:` entries verbatim into a script and run it with the task venv + a stubbed `pic-build`) before handing to CI — the previous dry-run evidently used a hand-corrected variant.
  - *Alternative:* the checked-in-script approach also makes the profile check reusable for future docs-style jobs and directly testable outside GitLab.
  - *Note:* a YAML `- |` block cannot contain a column-0 line, so the fix is **not** simply de-indenting `PY` inside the job.
  - This also contradicts the artifact's verification-log claim "CI job dry-run: profile-check block executed locally … OK" — as committed, the block cannot run; the author evidently tested a corrected variant (see §4).

### 2.2 Major

**M1** — ``.gitlab-ci.yml:264`` (profile check): `test -n "$PICSRC"` is a weak assertion that cannot fail for the reason it appears to guard.
- `PICSRC` is already exported by `share/ci/install/pypicongpu.sh:20` (`export PICSRC=$CI_PROJECT_DIR`), which the job sources at `.gitlab-ci.yml:224`, *before* the profile is sourced at line 262. So the test passes even if the generated `picongpu.profile` does not (re-)define `PICSRC`. The `PIC_BACKEND` check (line 263) is meaningful — `pypicongpu.sh` only sets it in the compiling-test path (line 77), which this job does not take.
  - *Suggested fix:* `unset PICSRC` before `source setup/workflow/scripts/picongpu.profile` (keep the `PIC_BACKEND` check), or assert that the profile file itself contains the definition (e.g. `grep -q 'export PICSRC=' setup/workflow/scripts/picongpu.profile`).

### 2.3 Minor

**m1** — the "real execution" of bash snippets is narrower than the PR text suggests.
- The bash snippets get only `bash -n` in the pytest suite (`test_snippets.py:174-177`). The CI job's only "real execution" is the inline 16³ setup generation + profile sourcing (`.gitlab-ci.yml:237-265`), which *mirrors* `legacy_workflow.sh` without executing it. The `cwltool` invocations (`cwltool_workflow.sh`, `cwltool_step.sh`) and `pic-build`/`tbg` are never actually run — only `--help` smoke checks (`.gitlab-ci.yml:229-231`). This is consistent with the task decision "real execution where cheap, `bash -n` for the rest", but the wording "Cheap bash snippets are additionally executed for real by the `docs-snippets` CI job" (in `test_snippets.py:17-19`, `snippets/README.md`, and the PR description) overstates it.
  - *Suggested fix:* correct the wording to "one bash flow (setup generation + profile sourcing, as `legacy_workflow.sh` performs it) is executed for real; all bash snippets are syntax-checked with `bash -n`", and list exactly which snippets are executed vs syntax-checked.

**m2** — tautological optimizer test with constants duplicated between harness and test.
- `run_snippet.py:26-37` (`emulated_electron_count`) hardcodes a Gaussian peaking at 4.6e-5 (sigma 1e-6, peak 1000); the scan focal values 4.4/4.6/4.8e-5 appear in `test_snippets.py:88-91` (EXPECTED_FILES for `multiple_simulations.py`) and again in `_make_synthetic_scan` (`test_snippets.py:109`); `test_snippets.py:168-171` then asserts the optimizer converges to 4.6e-5 (±5e-7) with count ≥ 995. The optimizer snippet's test therefore verifies the snippet's *mechanics* (scan loop, `minimize` call, parse) against a result the harness itself defines — acceptable for a docs gate, but the PR should say so explicitly, and the constants (4.6e-5, 1e-6, 1000, and the scan focal list) are duplicated between `run_snippet.py` and `test_snippets.py`, so they can drift silently.
  - *Suggested fix:* define the constants once (e.g. `PEAK_FOCAL = 4.6e-5`, `PEAK_SIGMA = 1e-6`, `PEAK_COUNT = 1000`, `SCAN_FOCALS = (4.4e-5, 4.6e-5, 4.8e-5)` in `run_snippet.py`) and import them into `test_snippets.py`; add a sentence in the PR body that the optimizer test is a mechanics test against a synthetic, harness-defined landscape.

### 2.4 Nits

**n1** — `docs/source/conf.py:142-143`: the `exclude_patterns = ["python_package/snippets/*"]` entry is a no-op with a misleading comment.
- `exclude_patterns` only applies to files matching `source_suffix` (`.rst`); `.py`/`.sh` snippets were never Sphinx documents, so nothing is excluded. Either remove the entry or reword the comment (e.g. "kept in sync with the literalinclude paths; snippets are not collected as documents" is false as stated — Sphinx does not try to). Harmless as-is.

**n2** — snippet shebang/dependency inconsistency + WIP pin.
- `defining_simulation/lwfa_example.py:1` and `defining_simulation/minimal_example.py:1` use `#!/usr/bin/env -S uv run` while the other seven python snippets use `#!/usr/bin/env python`; all PEP 723 blocks pin `picongpu @ git+https://github.com/ComputationalRadiationPhysics/picongpu@dev#subdirectory=lib/python`, but the docs describe the post-PR-5639 interface, which is not on `dev` yet — `uv run` of the two pinned snippets will break until 5639 lands. This is inherent to the docs lineage (the PR targets `picmi-docs` and feeds 5731), but it should be flagged in the PR body as a conscious decision; consider unifying the shebangs on the same invocation style.

## 3. Requirement traceability

| # | Requirement (from task file) | Status | Where / note |
|---|---|---|---|
| 1 | All snippets checked for correctness against actual package/CLI behaviour | partial | 10 Python snippets executed & artifact-asserted in `test_snippets.py` (25 passed, re-verified); bash snippets only `bash -n` + profile sourcing for the legacy flow — `cwltool`/`pic-build`/`tbg` commands never executed (see m1) |
| 2 | Every snippet is a `literalinclude` of a real script executed in CI | met | 32 `literalinclude` across the 3 rewritten pages (configuring_environment 4, defining_simulation 13, running_simulation 15) resolving to the 25 snippet files; Python via pytest in CI, bash per the task's `bash -n` decision |
| 3 | All doc scripts pass in CI; Sphinx build succeeds | met locally, blocked in CI | 25 passed (re-run); sphinx build with 0 warnings in `python_package/` and no include failures (coordinator's fresh build) — but the CI job as committed cannot succeed: C1 |
| 4 | New `docs-snippets` GitLab job | present | `.gitlab-ci.yml:210-280`, stage `test`, pypicongpu container image — but see C1 |
| 5 | Sphinx build fails on errors / missing includes | present (unreachable due to C1) | grep gates at `.gitlab-ci.yml:271-276` (`Include file … not found` + `build succeeded`) |
| 6 | Fix snippets that do not work as documented | met | extensive rewrites verified against package source, e.g.: nonexistent `picrc-builder` tool → rewritten as "The `.picongpurc.toml` File" with the real search order; nonexistent `picongpu.get_available_presets()` → listing `etc/picongpu` of the installed package; unsupported `MultiSpecies` → two individual `Species` sharing a `GaussianDistribution`; plus `model_dump()` serialization section corrected, `picongpu_laser`→`picongpu_lasers`, `GaussianLaser` given required `centroid_position` |
| 7 | Branching workflow (feature branch based on `picmi-docs`, PR against `picmi-docs`) | met | branch based on `85365feb2` (tip of `origin/picmi-docs`); unpushed per requester |
| 8 | Robustness: no line numbers; whole-file includes by default; semantic markers only where one file feeds multiple sections | met | markers only in `lwfa_example.py` (7 semantic pairs) and `multiple_simulations.py` (2 pairs); no `:start-at:`/`:lineno:` anywhere in the `.rst`; no marker lines leak into rendered HTML (coordinator) |
| 9 | No remaining inline executable code blocks in `python_package/` | met | only non-executable TOML/pseudo excerpts remain, per the documented convention in `snippets/README.md` (coordinator) |

## 4. Claim verification (author artifact)

From `TASK-01-PR-PROPOSAL.md` (verification log, lines 119-129). Coordinator re-runs 2026-08-31 unless marked "this review".

| Claim | Re-verified? | Result / delta |
|---|---|---|
| Snippet suite: `25 passed` | yes — this review, re-run in worktree with task venv | `25 passed in 17.11s` — exact. Side note: the artifact's breakdown "9 python executions … + 16 bash `bash -n`" (line 96) and "9 Python snippets + 15 bash snippets" (line 28) are each off by one; the actual split is **10 Python + 15 bash** (25 total — the head count is what CI will run). |
| Quick gate: `174 passed, 2 xfailed, 1 xpassed` (== base `85365feb2`) | yes — this review, re-run (`cd lib/python/test/picongpu && python -m pytest quick/ -q`) | `174 passed, 2 xfailed, 1 xpassed, 3499 subtests passed in 5.59s` — exact match, == coordinator's baseline `b4e4ca5b2`. |
| Clean `sphinx-build -b html`, **0 warnings in `python_package/`**, no "Include file … not found" | yes — coordinator (scratch venv, `docs/requirements.txt`, existing gitignored `docs/xml`) | Build succeeded with 378 warnings in the coordinator's environment (artifact says 381 — the absolute count is environment-dependent, e.g. whether `picongpu`/`moosetash` imports resolve for autoapi); **0 warnings mention `python_package/`**, zero include failures. The verifiable claim holds. |
| No `BEGIN-`/`END-` marker lines rendered into `defining_simulation.html` | yes — coordinator | Confirmed on the rendered HTML. |
| `pre-commit run --all-files`: all hooks pass | yes — **this review**, `/tmp/opencode/review-01/pc/venv/bin/pre-commit run --all-files` in the worktree | All 20 hooks **Passed**, exit 0 (hook envs already installed; full log in `/tmp/opencode/review-01/precommit.log`). |
| CI job dry-run: profile-check block executed locally (16³ setup, source profile) → `PIC_BACKEND=omp2b:native`, `PICSRC=<source tree>` — OK | **no** | **INACCURATE as committed.** The committed block cannot run: its heredoc is unterminated (C1) — `bash -n` warns `here-document at line 5 delimited by end-of-file (wanted 'PY')` and the runtime run dies with `IndentationError` before any `test`/`echo` executes. The author evidently tested a hand-corrected variant; the verification log should say so or be re-done against the committed text. |
| `.gitlab-ci.yml`: YAML parse of the new job OK | yes | True — the job parses cleanly; note that YAML parsing (and `bash -n` of the extracted block, which only warns) does not catch the heredoc problem. |

## 5. Design discussion

The overall design is right and matches the task's evaluation of alpaka's approach: real scripts in the docs tree, `literalinclude` of exactly the tested code, pytest as the "each snippet = one test" layer, a GitLab job as CI glue, and the Sphinx build as the docs↔scripts sync check (with explicit grep gates for the warning-only "Include file not found" case). The `--no-run` emulation of the workflow run step (`run_snippet.py:63-84`) is a sensible way to keep CI compile-free, and the synthetic `EnergyHistogram` is deterministic and documented as test infrastructure.

Weaknesses a maintainer should weigh:

- **(a) CI coupling and first-run risk.** The `docs-snippets` job runs a full `doxygen` over the C++ tree in every pipeline (slow) and regenerates `docs/xml/`, which is gitignored and has **never** run in CI on this lineage — so both the doxygen step and the whole job have untested first-run behavior. C1 makes that first run a guaranteed failure; even after the fix, the doxygen/sphinx path is the part least likely to have been exercised. The checked-in-script fix for C1 also makes the profile check reusable and testable outside GitLab.
- **(b) Shared-script mutation.** `PYPICONGPU_SKIP_QUICK_TEST` (new) makes `share/ci/install/pypicongpu.sh` skip both the `/.picongpurc.toml` write (line 24-26) and the quick tests (line 68-71). Verified opt-in and documented; existing jobs are unaffected. A future maintainer extending the pypicongpu jobs should know the guard exists.
- **(c) The bash "tested" story is really "syntax-checked".** Fine per the task decision, but the docs/PR wording should not say the cheap ones are "executed for real" when only one inline re-implementation of the legacy flow is (m1).
- **(d) PEP 723 `@dev` pin drift.** The snippets pin `picongpu @ ...@dev`, while the docs describe the post-5639 interface that is not on `dev` yet (n2). Acceptable while the PR feeds 5731, but it is a moving target: re-pin or note it when 5639 lands.
- **(e) Self-referential optimizer test.** Acceptable for a docs gate (m2) — the alternative (a real compiled scan) would violate the compile-free CI decision — but it should be documented as a mechanics test with shared constants.

## 6. Prioritized next steps

1. **Fix C1**: move the profile check to a checked-in script (or otherwise terminate the heredoc), then re-dry-run the *actual* job script list locally — extract the job's `script:` entries verbatim into a script and run it with the task venv + a stubbed `pic-build`/`pic-configure`/`tbg` — and attach that run to the verification log.
2. **Strengthen the profile check (M1)**: `unset PICSRC` before `source …/picongpu.profile`; keep the `PIC_BACKEND` check.
3. **Correct the PR proposal wording (m1)**: bash execution is "one legacy-flow equivalent executed for real + `bash -n` on all"; list executed-vs-syntax-checked snippets; and fix the dry-run log entry to reflect the committed text.
4. **Deduplicate the emulation constants (m2)**: single source of truth in `run_snippet.py`, imported by `test_snippets.py`; state explicitly that the optimizer test is a mechanics test.
5. **Nits (n1/n2)**: remove or reword the `conf.py` exclude_patterns comment; unify snippet shebangs and add the WIP-`@dev`-pin note to the PR body.

## FYI (inherited from base, not scored here)

- The base (`origin/picmi-docs`) docs are WIP; the 378–381 pre-existing Sphinx warnings elsewhere in the docs (autoapi, program-output) are out of scope.
- `docs/xml/` (doxygen output) is gitignored — the CI doxygen step has never actually run in CI for this lineage; its duration/robustness is untested, which compounds C1's "first real run" risk.
