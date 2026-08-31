# TASK-10 - Rework response to review (TASK-10-REVIEW.md)

Branch: `task-10-testsuite-audit` (review tip `1a996c8be`) - 2026-08-31
Verdict addressed: APPROVE (0 critical / 0 major / 3 minor / 6 nits).

Every claim below was re-verified against the branch code in this container
before acting. All changes are new commits on top of the review commit;
nothing is deleted; `TASK-10-REVIEW.md` is untouched.

## Disposition per finding

| ID | Disposition | Commit |
|----|-------------|--------|
| m1 | fixed | `762c41b9b` |
| m2 | fixed | `2ea8e370d` |
| m3 | fixed | `77ceb3a79` |
| n1 | fixed | `624156fd4` |
| n2 | fixed | `624156fd4` |
| n3 | fixed | `624156fd4` |
| n4 | fixed | `77ceb3a79` |
| n5 | fixed | `a52ce40db` |
| n6 | fixed | `5707a3576` |
| -  | gate fix (inherited red pre-commit) | `2b33e490f` |

## Detail and evidence

- **m1 (fixed)** - `allParamsinFile` now splits the header line on
  whitespace (`split()`), so the last column no longer keeps its trailing
  newline. Reproduced first: on the review tip a 2-column `step Bx` file
  gave `getDatwithParam('Bx') == []` and `getValue('Bx')` raised "could not
  be found"; a 3-column `step Bx By` file worked. Added
  `TestDataReaderTrailingColumn` (2-column header): the three tests fail on
  the pre-fix code and pass after. B6 in the findings doc now records the
  residual edge case and its fix.

- **m2 (fixed)** - added `TestCMAKEFlagReader` (getAllSetups / usedSetup /
  getValue on a fixture file) so the B5 fix in `cmakeFlagReader.py` has a
  direct regression test; `gc.collect()` after `getAllSetups()` forces an
  unclosed handle to raise its ResourceWarning under `filterwarnings=error`.
  Verified: reverting the B5 `with open` makes `test_get_all_setups` and
  `test_get_value` fail with a ResourceWarning. The B5 finding and the
  quality summary are reworded: the "this is why the framework has zero
  tests" causal claim is softened, and all six fixes now have a direct
  regression test.

- **m3 (fixed)** - the proposed job no longer invokes `ci.sh` (dead
  `--fields_energy.period 10` at ci.sh:120, dead `validate.sh` call at
  ci.sh:124). It now inlines the runnable steps (pic-create + pic-build +
  `mpiexec ... -s 3000` without the dead flag) and validates with the
  openPMD pytest step from this branch. Added the ci.sh/validate.sh fix as
  an explicit pre-condition (now #3). Both line numbers and the dead flag
  were re-confirmed by reading the current `ci.sh`.

- **n1 (fixed)** - `validate.sh` main.py call is at :67 (not 65-66);
  `filterwarnings = ["error"]` is at `lib/python/pyproject.toml:92` (not
  :88). Both confirmed by reading the files.

- **n2 (fixed)** - sign corrected: `getDifferenceInPercentage(Gamma,
  Gamma/2)` = +50, not -50. Verified: the function returns 50.0 for
  (1.0, 0.5). The B1 narrative now reads "~+50 % deviation ... -> fail".

- **n3 (fixed)** - the 21 `testsuite/*.py` files are 2630 lines (not
  ~3000); the ~75 KB figure (74 504 bytes) was already accurate and is kept.
  Counted with `find ... | xargs wc -l`.

- **n4 (fixed)** - one 15-40 min job per week is < 1 h/week, not < 5 h/week.
  Cost bullet corrected to "(weekly = < 1 h/week of one CPU runner)".

- **n5 (fixed)** - `times_omega_pe` now reads `time * time_unit_SI`.
  Verified: openpmd-api 0.17.1 exposes `time_unit_SI` and reports the
  standard default 1.0 when the attribute is absent (so PIConGPU output and
  the synthetic tests are unchanged); an explicit `timeUnitSI=2.0` scales
  the result as expected.

- **n6 (fixed)** - added `test_validation_fails_below_theory`: a series
  growing at half the analytic rate must fail the 20 % acceptance. Verified
  the logic standalone (openpmd read path is self-skipping in this
  container, as the positive tests are): 50 %-of-theory series -> 50.0 %
  deviation -> `result False`. The test collects cleanly (5 tests in the
  file, was 4).

## Gate fix (inherited, not a review finding)

`pre-commit run --all-files` was already failing at the review commit
`1a996c8be`: the review team's `TASK-10-REVIEW.md` contains non-ASCII math
notation (274 non-ASCII bytes), which trips `require-ascii`. The rework
rules forbid modifying that file, so instead of editing it I added it to
the hook's documented `exclude` (the same mechanism the config already uses
for CHANGELOG.md etc.) in `2b33e490f`. No other file needed an exclusion.

## Deliberately not done (with rationale)

- **Wiring the synthetic test into the `pypicongpu` CI job** (review
  section 6, item 4, "one-line pypicongpu.sh change"): not applied. The
  task is an exploratory investigation with an explicit "propose, don't
  wire" scope, and whether/where KHI validation runs in CI is the open
  question left to the requester. Changing `share/ci/install/pypicongpu.sh`
  would alter CI behaviour for every MR, beyond the light-rework mandate.
  Instead the findings doc now states the exact one-line change, why the
  auto-applied `slow`/`end_to_end` markers do not block it (no `-m` filter
  is active there), and that the real-run test self-skips without
  `PIC_KHI_OPENPMD`, so it is trivial for the requester to adopt.

## Final gate results (at final tip)

- `cd lib/python/test/picongpu && python -m pytest quick/ -q`
  -> `207 passed, 2 xfailed, 1 xpassed, 3499 subtests passed`
  (baseline `201 passed, 2 xfailed, 1 xpassed` + 6 new quick tests:
  3 trailing-column + 3 CMAKEFlagReader).
- `pre-commit run --all-files` -> all hooks passed (21 Passed, 0 Failed).
- compiling/ and end_to_end/ marker tests were not executed (per task
  constraint); the two new end_to_end-related changes were verified by
  standalone logic checks and collection only.
