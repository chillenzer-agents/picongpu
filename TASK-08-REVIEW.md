# Review — Task 08: Tighten the ruff rule set

- **Branch:** `task-08-ruff-all` (tip `0b1ba15d0`, base `dev` `b4e4ca5b2`)
- **Reviewed:** 2026-08-31 · **Scope:** 32 commits (31 code + 1 artifact), 241 files, +2422/−2066
- **Verdict:** APPROVE
  (All definition-of-done items are met and re-verified green; the incremental structure is real; the only issues are a factually wrong config justification, a few inaccurate artifact claims, and small unexplained edge-case shifts from auto-fixes.)

## 1. Summary

The branch introduces a repo-root `ruff.toml` (single source of truth, pre-commit args removed) and tightens the effective rule set from ruff defaults (E4/E7/E9/F) to `select = ["ALL"]` in 31 rule-batch commits, each leaving the tree green. Re-verified: `ruff check` 0 violations and `ruff format --check` 0 diffs (291 files) at the tip with ruff 0.12.10 (matches the pinned pre-commit rev); the quick suite is **174 passed, 2 xfailed, 1 xpassed** — identical to baseline; all pre-commit hooks pass on a clean copy of the tip. Spot-checked 5 intermediate commits green for the ruff gates and 2 (the S and PLW batches) green for the quick suite, so the "each commit green" claim holds where sampled. Both claimed real bugs are genuine and correctly fixed (unraised `NotImplementedError` in `particle_functor.py`; S110 in `species_requirements.py`). Most important issues, one line each: (1) the `PLC0414` per-file-ignore justification in `ruff.toml` is factually wrong (removing `X as X` from a from-import does not drop the name); (2) the PR proposal's scope numbers are off (30 vs 31 commits; "~86 files" isort vs ~175; D/ANN magnitudes overstated 10–25%); (3) a handful of auto-fixes change edge-case behavior without call-out (`[...][0]` → `next()` flips IndexError→StopIteration; public protocol param renamed `grid` → `_grid`).

## 2. Findings

### 2.1 Critical

None found.

### 2.2 Major

None found.

### 2.3 Minor

- **m1 — `ruff.toml:223-228`** — The `PLC0414` per-file-ignores for `picmi/diagnostics/radiation.py` and `picmi/interaction/collision.py` justify keeping `import X as X` with "removing the alias (PLC0414) would drop the names from the namespace". That is false for from-imports: `from m import X as X` and `from m import X` bind `X` identically.
  - *Evidence:* throwaway repro (`/tmp/opencode/review-08/repro_alias.py`): after `exec("from m import X as X")` and `exec("from m import X")`, both namespaces contain `X` and it is the same class. Also, commit `61e3d320c` removed the same redundant alias in `lib/python/picongpu/picmi/diagnostics/macro_particle_count.py` (`from ..species import Species as Species` → `from ..species import Species`) — the identical case is treated inconsistently across the branch.
  - *Suggested fix:* keep the explicit re-export idiom (defensible — it marks intentional re-exports into the picmi public namespace), but rewrite the justification to say so, e.g. "kept as the explicit `X as X` re-export idiom into the picmi public namespace; PLC0414's fix is safe but would lose the re-export marker". Alternatively, remove the aliases in these two files too, for consistency with `macro_particle_count.py`.

- **m2 — `lib/python/picongpu/picmi/distribution/UniformDistribution.py:42`, `lib/python/picongpu/picmi/distribution/FoilDistribution.py:41`** — public protocol parameter renamed `grid` → `_grid` (ARG002 auto-fix). All in-repo call sites are positional (`runner.py:219` calls `get_as_pypicongpu()` bare; the distribution methods are called positionally), so nothing breaks internally, but an external keyword caller `dist.get_as_pypicongpu(grid=g)` would now fail — a small public-API signature change made silently.
  - *Evidence:* `git diff dev...task-08-ruff-all` shows the two renames; `grep -rn "get_as_pypicongpu(grid=" lib/ share/ src/ docs/` → no in-repo keyword callers.
  - *Suggested fix:* use the branch's own other pattern for protocol parameters — `def get_as_pypicongpu(self, grid):  # noqa: ARG002 -- pypicongpu conversion-protocol signature` — as was done for `add_interaction` (`picmi/simulation.py:367`), instead of renaming.

- **m3 — `TASK-08-PR-PROPOSAL.md`** — several checkable claims are inaccurate:
  - *Evidence:*
    - "30 commits on dev" — the branch has 31 code commits + the artifact commit (`git log --oneline dev..task-08-ruff-all | wc -l` = 32); the proposal's own table lists 31 steps (0–30).
    - "I (isort): 181 import-block fixes across ~86 files" — `git show cb95ff2c9 --numstat` shows ~175 Python files changed (scope understated ~2×).
    - "D (pydocstyle, ~4.8k)" / config comment "normalising ~4,600 docstrings" — measured 4064 violations (`ruff check --isolated --select D`).
    - "ANN (~3.5k)" — measured 2639 (`ruff check --isolated --select ANN`).
    - S110 described as "restructured to catch the specific exception" — the actual fix in `species_requirements.py` (commit `89d26a20a`) is `try: return lhs == rhs / except Exception: return False` (no specific exception).
    - "36 `assert`s converted ... in library code" — of the 36, 2 are in `docs/source/pypicongpu/doc_example.py` and 15 in the standalone `extra/input/` scripts; strictly not all "library code".
  - *Suggested fix:* correct the numbers (31 code commits; ~175 isort files; measured D/ANN counts; S110 wording; "library code" → "library, docs-example, and script code") before merge so the PR description is review-accurate.

- **m4 — `lib/python/picongpu/extra/plugins/plot_mpl/phase_space_visualizer.py:202`, `energy_waterfall_visualizer.py:202`, `slice_emittance_waterfall_visualizer.py:210`, `lib/python/picongpu/extra/plugins/data/png.py:104`** — `[x for ...][0]` → `next(x for ...)` changes the exception on an empty sequence from `IndexError` to `StopIteration` (unexplained error-type change; inside a generator it would even surface as `RuntimeError` via PEP 479).
  - *Evidence:* diff hunks in commits `d55e15750`/`aff3090ed`; e.g. `idx = next(i for i, cbar in enumerate(self.colorbars) if cbar is not None)` raises `StopIteration` when all colorbars are `None`, where the old code raised `IndexError`.
  - *Suggested fix:* these are invalid-usage paths (a visualizer with no colorbars at all; a dir with no `.png`), so leaving it is defensible; if the error type matters, keep the list comprehension with `[0]`, or wrap: `try: idx = next(...) except StopIteration: raise IndexError("no colorbar found")`.

### 2.4 Nits

- **n1 — `lib/python/picongpu/pypicongpu/laser.py:109` (commit `9651430cb`, G batch)** — `f"All {values=} ... {wrong=}"` → lazy `%s` loses the `repr` of string values in the log message (`wrong='foo'` becomes `wrong=foo`). Current call sites pass lists/numbers (repr == str), so today's output is byte-identical; only a future string value would differ. If exact message preservation matters, keep that one f-string with a documented `# noqa: G004`.
- **n2 — commit `c59316215` (E batch)** — the manual wraps of over-long docstrings insert a hard newline mid-sentence into `__doc__` (e.g. `docs/propose_changelog.py` module docstring: "...milestone and labelled\nby the label..."). Cosmetic, and the commit message does say "Wraps over-long docstrings"; prefer wrapping at a sentence boundary.
- **n3 — RUF022 (`aff3090ed`)** — `__all__` lists were alphabetized (e.g. `picmi/__init__.py`), which changes member order in Sphinx-rendered docs. Cosmetic.
- **n4 — `ruff.toml:29-33`** — `E721` is a *global* ignore for 3 repo-wide violations, one of which is the documented `renderer.py` case. A per-file-ignore on `lib/python/picongpu/pypicongpu/rendering/renderer.py` would be more precise; the global form was inherited from the old pre-commit flag, so this is a tightening opportunity, not a defect.

## 3. Requirement traceability

| # | Requirement (from task file) | Status | Where / note |
|---|---|---|---|
| 1 | `select = ["ALL"]` | met | `ruff.toml:27`; 0 violations re-verified |
| 2 | As few justified exceptions as possible; every `ignore`/`per-file-ignores`/`noqa` carries a written justification | met | 22 global ignores + 38 per-file-ignores + 13 `noqa`, all with comments; one justification factually wrong (m1) |
| 3 | Committed config, single source of truth, applies repo-wide except `thirdParty` | met | root `ruff.toml`; `exclude = ["thirdParty", ...build dirs]`; covers `lib/`, `share/`, `docs/`, `src/` (all four trees were linted and fixed across batches) |
| 4 | `ruff check` + `ruff format --check` green at each step and at the end | met (spot-checked) | tip: 0/0, 291 files; 5 intermediate commits (`c59316215`, `50e4a6119`, `96a86e233`, `89d26a20a`, `40915ba40`) green for both gates via `git archive` copies; **per-commit greenness not verified for all 31 commits**, only the sampled ones |
| 5 | pre-commit keeps working; args reconciled, no double `--ignore E721` | met | `--ignore E721`/`--line-length 120` removed from `.pre-commit-config.yaml`; full `pre-commit run --all-files` passed on a clean scratch copy of the tip (pre-commit 4.3.0, cached hook envs) |
| 6 | Step 0: root `ruff.toml`, today's effective set, `line-length 120`, `py311`, isort `known-first-party = ["picongpu"]` | met | commit `c0f1f29f9`; plus one small code fix (backslash-in-f-string, broken on Python 3.11) transparently documented in the commit message |
| 7 | One rule batch per step/commit, each independently reviewable | met | 31 commits, each a single family; commit messages state rules added, fixes, and exceptions |
| 8 | `N` batch: targeted per-file-ignores, never a global disable | met | per-file entries for picmi/pypicongpu/extra/test trees; only 6 code changes in the batch |
| 9 | Final step: preview rule treatment decided and documented | met | preview stays off, documented in `ruff.toml:23-26` and the proposal |
| 10 | Exception-minimisation pass after `ALL` | met | verified in config history: `PT018` dropped, 4× N8xx dropped from the testsuite entry as covered by `lib/python/test/**`, `RUF100` activated and tree clean of unused noqa |
| 11 | Guard rail: config covers `share/ci/*.py` and docs-adjacent scripts | met | per-file entries + files in both trees changed across batches |
| 12 | Quick suite stays green; behaviour changes called out | met | 174/2/1 at tip (baseline per coordinator: 174/2/1); the S101 `python -O` behaviour change is explicitly disclosed in the proposal |
| 13 | Keep `types_or: [python, pyi, jupyter]` (notebooks stay linted) | met | both hooks unchanged; the two example `.ipynb` files were linted/fixed in-branch |
| 14 | Scope: Python package (no docs/C++ churn) | met | diff touches 235 `.py` + 2 `.ipynb` + `.pre-commit-config.yaml` + `ruff.toml` + the artifact only; no `.cpp/.hpp/.rst/CHANGELOG` |

## 4. Claim verification (author artifact)

| Claim (from TASK-08-PR-PROPOSAL.md) | Re-verified? | Result / delta |
|---|---|---|
| `ruff check .` → 0 violations (ruff 0.12.10) | yes | "All checks passed!" with the venv's ruff 0.12.10 (matches pinned rev) |
| `ruff format --check .` → 0 diffs (291 files) | yes | "291 files already formatted" |
| `pre-commit run --all-files` → all hooks passed | yes (scratch copy) | all hooks pass after removing review-side caches (`.ruff_cache`) from the copy; the first failure was an artifact of my own ruff run, not the branch |
| quick suite 174 passed / 2 xfailed / 1 xpassed, identical to baseline | yes | exactly 174/2/1 (+3499 subtests) at the tip and at intermediate commits `89d26a20a` and `d1e122e59` |
| incremental: one rule batch per commit, each green | spot-checked | all 31 commits are single-family (commit log); 5 commits re-verified green for the ruff gates, 2 for the quick suite (see §3 #4); not all 31 re-run |
| real bug: unraised `NotImplementedError()` in `particle_functor.py` (PLW0133) | yes | `dev` has bare `NotImplementedError()` in `Particle.get`; now `raise NotImplementedError("abstract base class only")` (commit `d1e122e59`) — genuine fix, verified |
| S110 restructured to catch the specific exception | partial | fix is correct and equivalent (`try: return lhs == rhs / except Exception: return False`, commit `89d26a20a`), but no specific exception is caught — wording inaccurate (m3) |
| 36 `assert`s → `raise AssertionError`, intentional `python -O` change, disclosed | yes | exactly 36 conversions; conditions and messages preserved (checked all multi-line messages incl. the backslash-continued one in `gaussian_laser.py`); behaviour change is disclosed |
| exception-minimisation pass dropped PT018 + 4× N8xx | yes | verified via `ruff.toml` history (`5dcb10860` → `40915ba40`) |
| "30 commits", "240 files, +2280/−2066" | no | 32 commits total (31 + artifact); 241 files, +2422/−2066 at tip — the file/line delta is the artifact itself, but the commit count is wrong even excluding it (m3) |
| "D ~4.8k / ANN ~3.5k / PTH ~110" | partial | measured 4064 / 2639 / 248 — right order of magnitude, D/ANN overstated ~10–25%, PTH understated ~2× (justifications unaffected) |
| "isort across ~86 files" | no | ~175 files (m3) |

## 5. Design discussion

- **`ALL` + 8 family ignores vs. fixing everything.** The final state is really "ALL minus D, ANN, TRY, EM, PTH, FBT, TID252, TD, FIX, BLE001, C901, ...". Measured violation counts (D 4064, ANN 2639, TRY 308, EM 304, PTH 248, FBT 75, TID252 78, C901 28, BLE001 16, TD 27, FIX 13) make the D/ANN ignores the only defensible ones at scale — each is a multi-PR documentation/typing project, and the task grants the implementer this judgment with written justification. The more questionable one is **PTH (248)**: a pathlib migration is mechanical, low-risk, and would have fit the incremental format as its own green batch; "separate modernisation" is an acceptable reason, but it is the ignore a maintainer would most likely challenge. FBT/TID252 (API-shape changes) are clearly out of scope. Suggestion for a follow-up (not a blocker): file the D, ANN, and PTH families as separate tasks so `ruff.toml` can shed ignores over time.
- **Preview rules off.** Correct call: with the pre-commit rev pinned, `preview = true` would shift lint outcomes on every ruff bump without code changes. Revisit deliberately at the next version bump.
- **Global vs. per-file `E721`.** Inherited from the old `--ignore E721` flag; 3 sites repo-wide. Per-file on `renderer.py` would be the tightening-consistent choice (n4).
- **S101 → `raise AssertionError` in library code.** Right direction for a physics library: invariant checks must not vanish under `python -O`. Properly flagged as a behaviour change; the quick suite (run unoptimized) is unaffected, as re-verified.
- **`X as X` re-export idiom (PLC0414).** Keeping the idiom is defensible (it marks intentional re-exports and plays well with `__all__`/tooling), but the branch must pick one treatment: the wrong justification plus the inconsistent removal in `macro_particle_count.py` is the kind of thing that erodes trust in the "every exception justified" guarantee (m1).
- **Integration-sweep readiness.** The proposal correctly states "must merge last" and the 03 → 08 order for `.pre-commit-config.yaml`, and no sweep-ready hacks exist (no global ignore exists merely to make a future sweep trivial). Missing: an explicit sentence that a final `ruff --fix` + `ruff format` sweep will run on the *integrated* tree before merge — the coordinator's plan assumes it; put it in the PR description so it isn't forgotten.

## 6. Prioritized next steps

1. Fix the `PLC0414` justification in `ruff.toml` (m1): reword to the true reason (explicit re-export idiom) or remove the aliases in the two hub files for consistency with `macro_particle_count.py`.
2. Correct the PR proposal's numbers and wording (m3): 31 code commits; ~175 isort files; measured D/ANN/PTH counts; S110 description; "library code" scope; add the post-integration sweep sentence (see §5).
3. Decide on `get_as_pypicongpu(_grid)` (m2): `# noqa: ARG002` with justification (matching `add_interaction`) rather than a public signature rename.
4. Optionally restore `IndexError` semantics at the `next()` sites (m4) or leave with a comment.
5. Optional tightenings: per-file `E721` (n4); keep the `laser.py` `=`-spec f-string if log-message fidelity matters (n1).

## FYI (inherited from base, not scored here)

- The `I = UnitDimension(I=1)  # noqa: E741` directive already exists on `dev` (pre-existing noqa, kept because it is used).
- The exact-type-check case in `renderer.py` (the documented E721 origin) predates this branch.
- The legacy testsuite framework's `eval("config.<name>")` (S307) and broad-try/except dispatcher are inherited; this branch only added documented per-file ignores around them.
- `share/ci/pypicongpu_generator.py` contained a backslash in an f-string expression part — a syntax error on Python ≤ 3.11 (the declared minimum); the branch fixed it in step 0 with a transparent commit message. Good catch by the new `target-version = "py311"`.
