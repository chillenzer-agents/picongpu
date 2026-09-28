# Review — Task 10: Audit `lib/python/test/{testsuite,setups}` (cleanup + openPMD modernisation draft)

- **Branch:** `task-10-testsuite-audit` (tip `ce5a79568`, base `dev` @ `b4e4ca5b2`)
- **Reviewed:** 2026-08-31 · **Scope:** 11 commits, 15 files, +903/−47
- **Verdict:** APPROVE
  (audit is accurate on every spot-checked claim; cleanup is safe and verified; the modernisation draft works within its honestly-documented scope; only minor issues remain.)

## 1. Summary

The branch audits the standalone KHI post-simulation validation framework (`testsuite/` + `setups/`), fixes six real defects in it (4 pre-named + 2 found during the audit) plus three stale docs, adds 27 pytest unit tests under `quick/testsuite/`, drafts an openPMD-based re-expression of the ESKHI validation (`end_to_end/khi_growthrate.py` + `test_khi_growthrate.py`), and gives a costed manual/weekly CI proposal. I re-ran the gate (`201 passed, 2 xfailed, 1 xpassed`, baseline `174 passed, 2 xfailed, 1 xpassed` — both reproduced exactly in this container) and independently reproduced every bug/defect claim (B1–B6, L1–L7) against the dev code, including the openpmd-api 3.14 read-path breakage (on-disk file verified correct via h5py, `load_chunk` returns swapped data). The audit is unusually well-evidenced and I found no materially wrong statement — only line-number drift, a sign error, one over-claimed "with regression tests" sentence, and one undocumented residual edge case of the `DataReader` fix. The modernisation reuses the corrected `testsuite.Math` as the reference (verified: synthetic pipeline recovers the analytic rate to ~1e-16 relative error, verdict `True`), self-skips in broken openpmd environments, and deletes nothing, as the task required. The CI recommendation (manual/weekly, not per-MR) is well argued; its proposed job script should state explicitly that `ci.sh` must first be fixed (it still carries the dead `--fields_energy.period 10` flag).

Most important issues, one line each:

1. **m1** — the B6 `skiprows=1` fix does not cover `.dat` files whose header's *last* column is the sought parameter (trailing-newline quirk in `allParamsinFile`), and the findings doc presents B6 as fully fixed without listing this residual limitation.
2. **m3** — the proposed CI job invokes `ci.sh`, which contains the dead `--fields_energy.period 10` flag and calls the dead legacy `validate.sh`; "fix ci.sh/validate.sh" is missing from the §6.2 pre-conditions, so the job as written would fail.
3. **m2** — "all fixed on this branch with regression tests" is overclaimed: the `cmakeFlagReader` file-handle fix (B5) has no test at all.

## 2. Findings

### 2.1 Critical

None found.

### 2.2 Major

None found.

### 2.3 Minor

- **m1** — `lib/python/test/testsuite/Reader/dataReader.py:102` (`allParamsinFile`) — the B6 fix (commit `528666828`, `skiprows=1` at lines 212/214/218/228) is incomplete for one real input shape: `allParamsinFile` splits the header line with `split(" ")`, so the **last** column name keeps its trailing newline (`"Bx\n"` ≠ `"Bx"`); when the sought parameter is the last header column, `getDatwithParam` finds nothing and `getValue` raises `ValueError: The given Parameter could not be found` — even on this branch. The author's own unit test works around it (`quick/testsuite/test_reader.py:78-79`: "Bx must not be the last header column"), but TASK-10-FINDINGS.md §3.1 (B6) presents the pipeline as "fixed with `skiprows=1`" and the residual limitation appears in neither B6 nor the L1–L7 latent-defect list. For the ESKHI flow this is material: whether `Bx` is the last column of a real `fields_energy.dat` header decides whether the "fixed" legacy path works at all.
  - *Evidence:* repro in `/tmp/opencode/review-10/verify_b6.py`: branch code, 3-column header `step Bx By` → `Bx = [1. 2. 4. 8.]` OK; 2-column header `step Bx` → `ValueError: The given Parameter could not be found` (dev fails both).
  - *Suggested fix:* one-liner — in `allParamsinFile`, `line = fi.readlines()[0].split()` (whitespace split, strips the newline) — and add a regression test with a 2-column header (`"step Bx\n"`). Also add the limitation (or the fix) to the findings doc.

- **m2** — `TASK-10-FINDINGS.md:210-211` (§3.4 "all fixed on this branch with regression tests") and §4 table — overclaim. The B5 fix (commit `7e5501907`) touched two files: `paramReader.py:193` (exercised incidentally by `TestParamReader::test_get_value` → `getValue` → `paramInLine`) and `cmakeFlagReader.py:98` (`getAllSetups`) — the latter has **no** test; there is no `CMAKEFlagReader` test in `quick/testsuite/`. The paramReader side is also only covered *incidentally*: a reverted unclosed `open()` would surface as a GC-time `ResourceWarning`, which under `filterwarnings=error` is not a deterministic per-test failure. Related: §3.1 (B5) "this is why the framework has zero tests" is causal over-attribution — the global `config` state (L3) and missing fixtures are at least equally plausible; fine as a hypothesis, not as a stated cause.
  - *Evidence:* `grep -rn "cmakeFlag" lib/python/test/picongpu/quick/` → no matches; `git show 7e5501907 --stat` → both files.
  - *Suggested fix:* add a small `TestCMAKEFlagReader` (fixture `cmakeFlags` file, assert `getAllSetups()` returns the flags, and that it runs clean under the existing `filterwarnings=error` regime); soften §3.4 to "five of six with direct regression tests; the cmakeFlagReader fix is covered by [X]" or add the test.

- **m3** — `TASK-10-FINDINGS.md:310-329` (§6.3 proposed job) — the proposed `khi-growthrate-validation` job runs `KHI_growthRate/bin/ci.sh`, which (a) passes the dead flag `--fields_energy.period 10` (`ci.sh:120`; no such plugin/option exists in this checkout — the audit's own L5) and (b) ends with `validate.sh` running the legacy `.dat`/ESKHI path, which is not functional for the reasons in B6/L5. §6.2's pre-conditions list the `picongpu.cfg` field dump and the load-bearing decision, but not "fix `ci.sh`/`validate.sh` (drop the dead flag; replace the `validate.sh` call with the new openPMD pytest step)". As written, the proposed job would fail at the simulation step regardless of the pre-conditions.
  - *Evidence:* `share/picongpu/tests/KHI_growthRate/bin/ci.sh:120` (`--fields_energy.period 10`), `:124` (calls `validate.sh`); grep for `fields_energy` in `src/` finds only stale doc references.
  - *Suggested fix:* add item 4 to §6.2: "replace `ci.sh`'s `--fields_energy.period 10` and its `validate.sh` invocation (dead, see L5/B6) with the openPMD run + `pytest end_to_end/test_khi_growthrate.py` step"; optionally show the corrected 5-line script.

### 2.4 Nits

- **n1** — `TASK-10-FINDINGS.md:73,131` — line-number drift: the `main.py` call in `validate.sh` is at **:67**, not 65-66 (the task file's "65" was copied through); `filterwarnings = ["error"]` is at `lib/python/pyproject.toml:92`, not :88.
  - *Suggested fix:* correct the two references (or drop the line numbers).

- **n2** — `TASK-10-FINDINGS.md:97` (B1 narrative) — "a simulation matching theory would appear at ~-50 % deviation" has the wrong sign: with the 0.5 bug, `getDifferenceInPercentage(theory, Γ/2) = (Γ − Γ/2)/Γ·100 = +50`.
  - *Evidence:* `getDifferenceInPercentage(1.0, 0.5)` → `50.0`.
  - *Suggested fix:* write "~+50 % (i.e. |deviation| 50 % > 20 % acceptance → fail)".

- **n3** — `TASK-10-FINDINGS.md:19` — "~3000 lines" is ~14 % high: the 21 `.py` files total 2630 lines (the ~75 KB figure is accurate: 74 504 bytes).
  - *Suggested fix:* "~2600 lines".

- **n4** — `TASK-10-FINDINGS.md:332` — "(weekly = < 5 h/week)" is inconsistent with one 15-40 min job per week (≤ ~0.7 h/week); 5 h/week would imply ~8 runs/week.
  - *Suggested fix:* "weekly = < 1 h/week of one CPU runner".

- **n5** — `lib/python/test/picongpu/end_to_end/khi_growthrate.py:56` — `times_omega_pe` uses the raw openPMD `time` attribute without applying `timeUnitSI`. PIConGPU currently writes `timeUnitSI = 1.0` (verified in an on-disk dump), so this works today, but the unit-robust form is `time * iteration.time_unit_SI`.
  - *Suggested fix:* `t_si = float(it.time) * float(it.time_unit_SI)` (or document the assumption next to the call).

- **n6** — `lib/python/test/picongpu/end_to_end/test_khi_growthrate.py:85-123` — the synthetic suite only asserts the positive verdict. A one-line negative case (write a series growing at e.g. 50 % of the analytic rate and assert `result["result"] is False`) would guard the verdict/acceptance wiring, not just the rate recovery.
  - *Evidence:* logic check in `/tmp/opencode/review-10` (50 %-of-theory series → diff 50.0 % → `result False`), so this is a coverage suggestion, not a logic bug.

## 3. Requirement traceability

| # | Requirement (from task file) | Status | Where / note |
|---|---|---|---|
| 1 | Report answering "what do they test" + "quality", with concrete defects | met | TASK-10-FINDINGS.md §1-§3. ~15 specific claims spot-checked against dev (B1–B6 repros, L1–L7, CI scripts, docs, git history, .param values) — all accurate apart from nits n1-n4 |
| 2 | Cleanup: fix `growthRate` factor-2 | met | dev returns ln2/2 (0.346574) for 2^t; branch returns 0.693147; regression test `test_exponential_no_half_factor` |
| 3 | Cleanup: fix `getMinDifference` | met | dev: `TypeError` on scalars; branch: `0.0`; 1-D behaviour unchanged; regression test present |
| 4 | Cleanup: fix `getDifferenceInPercentage` | met | docstring aligned to the code's theory-relative semantics (the ones `getTestResult`/acceptance rely on — verified against `deviation.py:196-239`); `np.max` fixes scalar `simulation`; test present |
| 5 | Cleanup: fix `setDirection` | met | dev: `AttributeError: ... directiontype`; branch: works; regression test present |
| 6 | Cleanup: fix the three stale docs | met | all three claims verified against dev docs and the real files; the new `usage.rst` `--delete` statement is accurate (it is a flag of `ci.sh:42,60-62,127-129`, not `main.py`) |
| 7 | Cleanup: minimal unit tests for `Math/` + `Reader/` into `quick/` | met | 27 tests (12 math + 15 reader), green under the repo's `filterwarnings = ["error"]` regime; `conftest.py` resets the global template-config state (L3) between tests |
| 8 | Do not delete anything (KHI flow fate uncertain) | met | diff contains no deletions; legacy `.dat`/`.param` path retained as fallback |
| 9 | Modernisation draft: pytest checks consuming openPMD via openpmd-api, `Math` kept as reference | met (draft) | `end_to_end/khi_growthrate.py` reuses corrected `testsuite.Math` (verified); access pattern matches `compare_particles.py::read_fields`; ESKHI-only scope is documented and justified (ESKHI is the only setup the KHI flow's `validate.sh` actually runs); self-skip on broken openpmd read path; `openpmd-api` is a main package dep, so no new dep needed |
| 10 | Modernisation verification: "reproduces the (corrected) analytic comparison on an available KHI run" | partial | no real KHI run exists in this container and the KHI input set writes no openPMD fields (L5/L6 — coordinator-confirmed prerequisites). Verified instead on a synthetic series with an h5py-backed read: theory 0.22097086912079605 vs simulation rel. diff ~1e-16, verdict True (matches the doc's numbers); independently reproduced. The "only unexecuted part is the literal `load_chunk()`" statement is accurate |
| 11 | CI integration investigation: costed proposal or documented reason | met | §6: cost table (1.18 M cells = 192·512·12, correct), pre-conditions, manual/weekly recommendation with argued reasons, cheaper alternative (synthetic test in the existing `pypicongpu` job) identified and proposed. Gap: m3 |
| 12 | Semantically coherent commits | met | 11 focused commits, one concern each (bug fix / doc / tests / modernisation / findings / pre-commit) |
| 13 | No C++ changes | met | diff touches only `lib/python/test/**` and `docs/source/testing/**` |

## 4. Claim verification (author artifact)

| Claim (from TASK-10-FINDINGS.md / author report) | Re-verified? | Result / delta |
|---|---|---|
| Test gate: "201 passed, 2 xfailed, 1 xpassed" (baseline "174 passed, 2 xfailed, 1 xpassed") | yes | **Exact match.** Branch: `201 passed, 2 xfailed, 1 xpassed, 3499 subtests passed`; baseline (dev tree extracted to scratch, same venv): `174 passed, 2 xfailed, 1 xpassed`. Δ = the 27 new tests, nothing else changed. (Note: the xpass is `test_validate_rocrate` and is a pre-existing environment quirk — see FYI — identical in dev.) |
| B1 growthRate returned Γ/2, docstring has no 0.5, "0.346574 vs 0.693147" | yes | Reproduced on dev (0.346574); branch returns 0.693147. 0.5 present since the first commit `840a48dba` alongside the docstring |
| B2 `getMinDifference` `TypeError` on scalars, used in `Math/_manager.py:20` | yes | Reproduced; `_manager.py:20` is exactly `dv.getMinDifference(...)` |
| B3 docstring/code mismatch (`/ simulation` vs `/ theory`) | yes | dev docstring `deviation.py:149` vs code `:173`; code semantics are the ones `getTestResult` relies on, so fixing the docstring was the right choice |
| B4 `setDirection` → `AttributeError` on `self.directiontype` | yes | Reproduced on dev (`readFiles.py:94` vs attribute `_directiontype` at `:69`) |
| B5 unclosed handles at `paramReader.py:193`, `cmakeFlagReader.py:98`; "this is why the framework has zero tests" | yes (lines + warning) / partial (causal claim) | Both line numbers exact; `ResourceWarning: unclosed file` reproduced on dev under warnings-as-errors. Causal "why zero tests" is over-attribution (m2) |
| B6 `getValue` dead for headered ("could not convert string 'step'") and headerless ("could not be found") files; fixed with `skiprows=1` | yes / with residual edge case | Both dev repros match exactly; fix verified for 3-column headers; **not** fixed for last-column headers (m1) |
| L1 `searchParameter(directiontype="openpmd")` → `UnboundLocalError`; no openPMDReader exists | yes | `_searchData.py:47` accepts "openpmd", no branch implements it, `result` unbound at `:86`; Reader/ contains no openPMD reader |
| L2 `-o` parsed but never passed in both `main.py`s | yes | ESKHI `main.py:56-64` vs `:79-84`; MI `main.py:69` vs `:100-105` |
| L3 `eval`/`exec` in `_checkData.py` (exec at :115), persists dirs into global config | yes | `eval` at :94/:148/:190, `exec` at :115 — line exact |
| L4 `plot_2D` empty stub; blanket `except` → `sys.exit(42)` | yes | `Viewer.py:144-146` (`pass`); `_manager.py:115-117` |
| L5 no `fields_energy` plugin in this checkout; only stale refs (plotNumericalHeating docs, FieldAbsorber) | yes (scoped) | grep of `src/` confirms only `src/tools/bin/plotNumericalHeating:27,133` and `tests/FieldAbsorber` cfgs. (This checkout has no C++ sources at all — see FYI; the doc correctly says "in this checkout") |
| L6 KHI input set has no `picongpu.cfg` / no openPMD fields | yes | `share/picongpu/tests/KHI_growthRate/` contains only `bin/`, `cmakeFlags`, `include/`, `README.rst` |
| L7 openpmd-api 3.14 read path broken here (write OK, on-disk correct, read returns `[2.0, 1.0]`) | yes | Independently reproduced with openpmd-api 0.17.1 on Python 3.14.5: read-back `[2.0, 1.0]`; h5py dump of the same file shows correct per-iteration data and `time`/`dt`/`timeUnitSI` attrs |
| end_to_end tests auto-marked `slow`+`end_to_end` by `conftest.py` | yes | `test/picongpu/conftest.py:27-28`; all 4 tests collect and skip here (3 via the round-trip self-check, 1 via missing `PIC_KHI_OPENPMD`) |
| Pipeline "verified end-to-end ... theory 0.22097086912079605 vs simulation 0.22097086912079608, verdict True" via h5py-backed read | yes | Independently reproduced (h5py read of the same synthetic series, same `testsuite.Math` calls): rel. diff ~6e-16, `getTestResult` True |
| CI facts: `pypicongpu.sh:61-65`/`:97`; no KHI in `.gitlab-ci.yml`/`share/ci/`; PIC jobs compile-only + `--help` smoke; sole consumer `validate.sh` (line "65-66"); collect-only → 0 items; no `testpaths` | yes (one line-number drift) | All verified; the `main.py` call is at `validate.sh:67` (n1); `pytest test/testsuite test/setups --collect-only` → "no tests collected" |
| "21 Python files, ~3000 lines, ~75 KB"; origin 2022-12-09; last functional commit `0e3f64f3f` 2024-02-28 | yes (line count loose) | 21 files ✓; 74 504 bytes ✓; 2630 lines (n3); `840a48dba` 2022-12-09 ✓; post-`0e3f64f3f` commits are copyright/requirements/pre-commit only ✓ |
| KHI defaults gamma=1.021, n=1e25 (new real-run test) | yes | `particle.param:38` `PARAM_GAMMA 1.021`; `simulation.param:74` `BASE_DENSITY_SI = 1.e25` |
| CHANGELOG is release-based (latest 0.8.0), no unreleased section → no entry added | yes | `CHANGELOG.md` starts at `0.8.0` with per-PR refs; no Unreleased bucket |
| pre-commit / ruff pass (final commits), findings doc ASCII-only | yes | ruff 0.12.10 (pinned rev): `ruff check --ignore E721` and `ruff format --line-length 120 --check` clean on all 11 touched/new Python files; findings doc passes an ASCII scan |

## 5. Design discussion

- **Reuse of `testsuite.Math` as the reference in the modernised check is the right call.** One computation path (corrected `growthRate` + deviation helpers) shared by legacy and new code means the two cannot silently diverge, and the B1-B3 fixes are what make the new check meaningful. The cost is that importing the pure math pulls in `_checkData`'s `eval`/`exec` global-config machinery (L3) transitively; since `acceptance` is always passed explicitly, no global state is actually read on the happy path — but a stray top-level `config.py` on `sys.path` *would* be picked up by `_checkData` and could override explicit parameters ("the value from config.py is always taken first"). Acceptable for a draft; a long-term fix is to make the math module import-free of `_checkData` (move `checkVariables` out of `deviation.py`) — good follow-up, not a blocker.
- **The self-skip round-trip fixture is the correct pattern for a known-broken dependency wheel.** It converts "tests silently fail on a corrupted read" into "tests skip with a precise message", and it would have caught exactly the L7 iteration-order swap (the synthetic rate-recovery test is also order-sensitive, since `growthRate` pairs adjacent entries). The trade-off — the suite goes quiet in precisely the environments where openpmd is broken — is documented in the docstring and the findings (L7). The one untestable link (literal `load_chunk()` on a healthy 3.11-3.13 wheel) is acknowledged; that is a property of the container, not of the branch.
- **ESKHI-only modernisation scope is defensible.** The only consumer of the framework (`KHI_growthRate/bin/ci.sh` → `validate.sh`) runs ESKHI; MI is not wired into any flow. If the requester decides the flow is load-bearing, porting MI (its `argrelextrema` trim adds one step) is the natural next commit.
- **CI: manual/weekly is the right default.** The arguments hold up: it would be the first simulation ever run in CI (CI is compile + `--help` smoke + quick/pytest today), it has unmet pre-conditions (L5/L6 + the fate decision), and 15-40 min of a CPU runner per MR is hard to justify before the flow's value is confirmed. The cheaper safety net that was *not* dismissed but only proposed is actually the one worth doing first: the synthetic `test_khi_growthrate.py` is < 2 s and would run in the existing `pypicongpu` job with a one-line change to `share/ci/install/pypicongpu.sh` (add an `end_to_end/test_khi_growthrate.py` invocation or un-mark just that file) — it guards the openPMD plumbing and the L7 class of regressions on every MR at zero extra runner cost. The per-MR *simulation* variant (e.g. a 300-step reduced run) is the reasonable middle ground to revisit once the fate decision lands; the doc's open question to the requester is the right framing.
- **Alternative considered for the unit tests:** a `pyproject`/`sys.path` fixture would not have been enough — the framework's state lives in the *imported* `config` module (L3), so the snapshot/restore autouse fixture in `quick/testsuite/conftest.py` is the minimal correct workaround given "no deletions, no refactor" constraints.

## 6. Prioritized next steps

1. **m1:** fix `allParamsinFile` header splitting (`split()` instead of `split(" ")`) in `dataReader.py:102`, add the 2-column-header regression test, and record the pre-existing limitation (or the fix) in the findings doc.
2. **m3:** add "fix `ci.sh`/`validate.sh` (dead `--fields_energy.period 10` at `ci.sh:120`; dead legacy validation)" to §6.2 pre-conditions (or show the corrected script) so the proposed job is honest as written.
3. **m2:** add a `TestCMAKEFlagReader` regression test (or restate §3.4 accurately: which fixes have direct regression tests).
4. **n6 + CI safety net:** add the negative verdict test; wire the synthetic `test_khi_growthrate.py` into the existing `pypicongpu` quick job (one-line `pypicongpu.sh` change) as the cheap per-MR guard.
5. **nits:** fix the two line numbers (n1), the deviation sign (n2), the line count (n3), and the weekly-hours arithmetic (n4); consider `timeUnitSI` in `times_omega_pe` (n5).
6. Then the documented follow-ups: requester decision on the KHI flow's fate, `picongpu.cfg` openPMD field dump for the KHI input set, upstream report of the openpmd-api 3.14 read-path bug (L7, reproduced here), and the L1-L4 latent-defect fixes.

## FYI (inherited from base, not scored here)

- **`test_validate_rocrate` xpass quirk:** under the default gate invocation (warnings plugin on, `filterwarnings = ["error"]`) the rocrate-validator's SHACL checks crash ("error during check ... SHACLCheck" in the log), the validator swallows the error and reports no issues, so the xfail-marked test **xpasses**; with `-p no:warnings` the checks run and find issues, and it xfails. Identical on dev — pre-existing, unrelated to this task; worth flagging to the picmi/rocrate owners (it also means the "1 xpassed" in the gate numbers is environment- and filter-dependent).
- **Trimmed checkout:** this repository copy contains no C++ sources under `src/` (only `src/tools`). The audit's L5 claim is correctly scoped to "this checkout"; against full upstream the `fields_energy` plugin question would need re-checking before declaring the KHI flow dead upstream.
- **Latent defects L1-L7** (openpmd branch of `searchParameter`, dead `-o` option, `eval`/`exec` + global config, `plot_2D` stub / `sys.exit(42)` swallowing, dead `--fields_energy` flag, no openPMD diagnostics in the KHI input set, broken openpmd-api 3.14 wheel) are all documented in the findings with evidence; fixing them is explicitly deferred, which matches the task's "do not delete / de-risk, don't re-architect" mandate.
- **`growthRate`'s interval branch** (`math.py:60-65`) has the same "2-step difference" shape as the non-interval branch and is covered by `test_interval_returns_bounds`; no issue.
- **`bx_amplitude_per_iteration`** loads the full mesh chunk per iteration (fine at 192·512·12); for much larger 3D fields a binned/reduced read would be the optimization to keep in mind.
