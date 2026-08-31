# TASK-10 - Audit of `lib/python/test/{testsuite,setups}`: what are they testing, what is their quality?

Branch: `task-10-testsuite-audit` (base `dev` @ b4e4ca5b2) - Date: 2026-08-29

This document answers the two audit questions -- *what are they testing?* and
*what is their quality?* -- with verified defects (reproducible commands),
summarises the cleanup and modernisation commits on this branch, and gives a
costed recommendation for CI integration.

---

## 1. What are they?

### 1.1 `lib/python/test/testsuite/` -- a standalone post-simulation validation framework

Not a pytest suite. It is a self-contained **post-simulation validation
framework** (origin 2022-12-09, last functional commit
`0e3f64f3f` 2024-02-28 "fix growth rate and charge conservation test tools";
bachelor-thesis work per file headers). 21 Python files, ~3000 lines, ~75 KB
(plus 4 files in `setups/`).

Pipeline: `setups/<case>/main.py` (argparse CLI) ->
`testsuite._manager.run_testsuite()` ->
`Reader` (crude parsers for `.param` preprocessor-style files, `.json`,
`.dat` columns, `cmakeFlags`) -> `config.theory(**parameter)` vs
`config.simData(**parameter)` (the case's analytic theory and the simulated
quantity) -> `Math._manager._calculate` (deviation checks) ->
`Output` (`testresult.log` + matplotlib PNG) -> `sys.exit(0/1/42)`.

### 1.2 `lib/python/test/setups/` -- the two concrete cases

| Case | Title | Theory (units of omega_pe) | Simulated quantity | Acceptance |
|---|---|---|---|---|
| `ESKHI/` | KHI Growthrate (2D ESKHI) | `1/(sqrt(8)*gamma)` | growth rate of the `Bx` column of `fields_energy.dat` | 20 % |
| `MI/` | KHI Growthrate (2D MI) | `v/(c*sqrt(gamma))` with `v=sqrt(1-1/gamma^2)*c` | growth rate of `Bx`, trimmed at the first local minimum | 20 % |

Both measure the Kelvin-Helmholtz instability growth rate of the dominant
magnetic field in a sub-relativistic shear-flow simulation
([Alves12], [Grismayer13], [Bussmann13]; see
`share/picongpu/tests/KHI_growthRate/README.rst`) and pass if the simulated
growth rate is within 20 % of the analytic value.

### 1.3 What they are NOT (and are not part of)

- **Not pytest**: no `test_*.py`/`*_test.py` files, no `assert`s.
  `cd lib/python && python -m pytest test/testsuite test/setups --collect-only -q`
  -> **`no tests collected`** (0 items).
- **Not imported by the `picongpu` package** (zero cross-imports; the package
  is installed from `lib/python/picongpu`, the framework lives in
  `lib/python/test/`).
- **Not run by CI** (see section 2).
- **Not duplicated** by the new `test/picongpu/` suite (2025 rewrite with
  `quick/`/`compiling/`/`end_to_end/`): different purpose -- physics
  post-processing of real simulation output vs. package unit/integration
  tests.

## 2. Are they tested in CI? -- No

CI is GitLab-based (`.gitlab-ci.yml` + `share/ci/`). Verified facts:

1. The Python package jobs run only the new suite:
   `share/ci/install/pypicongpu.sh:61-65` --
   `pip3 install -e lib/python[test]` then
   `cd lib/python/test/picongpu && python3 -m pytest quick/`;
   line 97: `python3 -m pytest compiling/ -v` (compile job only).
2. `share/picongpu/tests/*` jobs (`share/ci/run_picongpu_tests.sh`) only
   **compile** each test case and run a `picongpu --help` smoke test --
   **no simulation is ever executed in CI**.
3. No CI script references KHI:
   `grep -rn KHI .gitlab-ci.yml share/ci/` -> no matches.
4. The sole consumer of the framework is
   `share/picongpu/tests/KHI_growthRate/bin/validate.sh:65-66`:
   `python $PICSRC/lib/python/test/setups/ESKHI/main.py -p ... -r ... -s ...`,
   which is invoked only by the **manual** `KHI_growthRate/bin/ci.sh`
   (`pic-create` + `pic-build` +
   `mpiexec -n 1 picongpu ... -s 3000 --fields_energy.period 10`), i.e. a
   local/manual workflow, never by CI.

## 3. Quality: verified defects (with evidence)

All reproductions run in a clean shell; `PY` = task venv python,
`T = lib/python/test` (relative to the worktree root).

### 3.1 Computational bugs (fixed on this branch)

**B1 - `Math/math.py::growthRate` returned half the growth rate.**
The docstring formula `log(f(t_(k+1))/f(t_(k-1)))/(t_(k+1)-t_(k-1))` is a
two-step centred difference that already yields Gamma per unit time; the
code multiplied by `0.5`, double-correcting the two-step span.

```
$ PY -c "import sys; sys.path.insert(0,'lib/python/test'); import numpy as np, testsuite.Math.math as m;
         t=np.arange(50.0); g=m.growthRate(2.0**t, t); print(np.mean(g), np.log(2))"
0.346574 0.693147   # returned Gamma/2 (ratio 0.5000 in both branches)
```
Skewed the verdict of *both* setups (sim rate measured at half value; a
simulation matching theory would appear at ~-50 % deviation).

**B2 - `Math/deviation.py::getMinDifference` crashed on scalars, ambiguous on 2-D.**
`np.abs(min(theory - simulation))` uses the built-in `min()` -- although this
function is part of the main pipeline (`Math/_manager.py:20 _calculate`).

```
getMinDifference(0.5, 0.5)            # TypeError: 'float' object is not iterable
getMinDifference(ones((2,3)), ...)    # ValueError: truth value of array ambiguous
```

**B3 - `Math/deviation.py::getDifferenceInPercentage` docstring/code mismatch.**
Docstring: `(theory - max(simulation)) / simulation * 100`; code:
`(theory - max(simulation)) / theory * 100`. The code's semantics (relative
to theory) are the ones `getTestResult` and the acceptance range
(`theory*(1+/-acceptance)`) rely on, so the docstring was corrected; also
`max(simulation)` raised `TypeError` for scalar simulation values
(`np.max` now).

```
getDifferenceInPercentage(2.0, [1.0, 1.5])  # code: 25.0, docstring formula: 33.33
```

**B4 - `Reader/readFiles.py::setDirection` -- `AttributeError`.**
Referenced `self.directiontype`; the attribute is `self._directiontype`.

```
ReadFiles(".dat", direction="/tmp").setDirection("/tmp")
# AttributeError: 'ReadFiles' object has no attribute 'directiontype'
```

**B5 (additional, found & fixed) -- unclosed file handles.**
`ParamReader.paramInLine` (paramReader.py:193) and
`CMAKEFlagReader.getAllSetups` (cmakeFlagReader.py:98) opened files without
closing them. Under the repo's pytest regime (`filterwarnings = ["error"]`
in `lib/python/pyproject.toml:88`) the resulting `ResourceWarning` fails any
test exercising the parsers -- one of the reasons the framework has zero
tests (the global config state, L3, and the missing fixtures are at least
equally plausible). Both file-handle fixes have regression tests:
`TestParamReader` for the paramReader side, `TestCMAKEFlagReader` for the
cmakeFlagReader side (added in the rework, review m2).

**B6 (additional, found & fixed) -- `DataReader.getValue` could not read the
file format its own `allParamsinFile` defines.** `allParamsinFile` treats
the first `.dat` line as the column-name header; `getValue` then read the
same file with `np.loadtxt` (no `skiprows`), which dies on the header:

```
headered  file -> getValue('Bx'): ValueError: could not convert string 'step' to float64 at row 0
headerless file -> getValue('Bx'): ValueError: The given Parameter could not be found
```
i.e. the "simulation data" leg of the whole pipeline was dead for both
possible on-disk formats. Fixed with `skiprows=1` (only reachable via
headered files, since the sought parameter name is non-numeric, so no data
row can ever be dropped). The review (m1) found one residual edge case of
that fix: `allParamsinFile` split the header line on single spaces, so the
*last* column name kept its trailing newline (`"Bx\n" != "Bx"`) and a
sought parameter that is the last header column was never found (a 2-column
`step Bx` file made `getValue('Bx')` raise "could not be found" even on the
fixed branch). Also fixed: the header is now split on whitespace
(`split()`), with a 2-column-header regression test
(`TestDataReaderTrailingColumn`).

### 3.2 Latent defects (documented, NOT fixed -- see scope note)

- **L1 - `Math/_searchData.py::searchParameter(directiontype="openpmd")`**
  validates `"openpmd"` as a legal direction type but implements no branch
  for it -> `UnboundLocalError: cannot access local variable 'result'`. The
  framework's advertised openPMD support was never written (no
  `openPMDReader` exists). The modernisation (section 5) supplies a real
  openPMD path instead.
- **L2 - `setups/ESKHI/main.py` and `setups/MI/main.py` parse `-o
  <openPMD dir>` but never pass it to `run_testsuite`** (dead option).
- **L3 - `_checkData.py` uses `eval("config."+name)` / `exec(...)`** to read
  and *write* the global `config` module (e.g. `checkDirection` persists
  resolved directories into it). Stateful, fragile, and the reason any test
  of the framework must reset global config between tests.
- **L4 - `Output/Viewer.py::plot_2D` is an empty stub**;
  `_manager.py` blanket-catches `Exception` -> `sys.exit(42)` (real errors
  surface only as `error.log` + exit code 42).
- **L5 - the KHI flow's data source is gone.** `ci.sh` passes
  `--fields_energy.period 10`, but no `fields_energy`/`fieldsEnergy`
  plugin/option exists anywhere in this checkout (only a stale reference in
  `src/tools/bin/plotNumericalHeating` docs and the same flag in
  `tests/FieldAbsorber`). If it is also gone upstream, the KHI flow has been
  dead since the diagnostic was removed -- the "load-bearing status
  uncertain" flag is therefore well placed.
- **L6 - the KHI input set has no openPMD diagnostics.**
  `share/picongpu/tests/KHI_growthRate/` contains no
  `etc/picongpu/picongpu.cfg`, so the current test does not write openPMD
  fields at all. The modernised openPMD check (section 5) cannot run on it
  until a `picongpu.cfg` with a field dump for `B` is added (follow-up,
  section 7).
- **L7 - environment: openpmd-api's read path is broken for Python 3.14 in
  this container.** Write works (files verified correct byte-for-byte via
  h5py: correct groups, `time`/`dt` attributes, dataset contents), but
  `load_chunk()` returns swapped/corrupted data -- e.g. a 2-iteration scalar
  series reads back `[2.0, 1.0]` instead of `[1.0, 2.0]`, identical for
  openpmd-api 0.16.1 and 0.17.1.post4, h5 and BP backends, all read
  patterns. The project targets Python `>=3.11,<3.14`
  (`lib/python/pyproject.toml`) and CI runs 3.11/3.12/3.13
  (`share/ci/pypicongpu_generator.py:316`); the 3.14 wheel here is outside
  the supported range. The new tests therefore self-check the read path and
  skip with a clear message when it is broken (this container); they run on
  CI's Python versions.

### 3.3 Stale documentation (fixed on this branch)

- `docs/source/testing/structure.rst` referenced `Template/Data.py` and
  `Template/main.py` (neither exists; the template is `Template/config.py`)
  and omitted `Reader/readFiles.py`/`cmakeFlagReader.py`.
- `docs/source/testing/testbuilding.rst` described the obsolete "Data.py"
  workflow, had a typo'd path (`.lib/python/...`), and its MI example did
  not match `setups/MI/config.py` (`Bz` vs `Bx`, `*args` vs `**kwargs`,
  `calculateV_O()` vs `calculateV_O(gamma)`).
- `docs/source/testing/usage.rst` pointed at the non-existent
  `testsuite/Template/main.py --help` and claimed the output folder is
  deleted by default (it is kept; `--delete` removes it).

### 3.4 Quality summary

- Zero automated tests, zero asserts; "pass" = one 20 % deviation check per
  case, reported via log file + exit code.
- 6 real defects on the core computation/reader path (4 pre-existing named
  + 2 found during this audit), all fixed on this branch, each with a
  direct regression test (B5: `TestParamReader` for the paramReader handle,
  `TestCMAKEFlagReader` for the cmakeFlagReader handle, the latter added in
  the rework per review m2); 7 documented latent/environmental defects.
- Untouched functionally since 2024-02 while the rest of the Python package
  was rewritten in 2025; the data source it parses (`fields_energy.dat`) is
  no longer produced by this checkout (L5), and the KHI input set produces
  no openPMD fields (L6) -- the flow is likely already non-functional end to
  end.

## 4. Quick cleanup (commits b4e4ca5b2..997037074)

| Commit | Change |
|---|---|
| `256384619` | `Math/math.py`: remove the spurious factor 1/2 in `growthRate` (B1) |
| `f8c9b0dd8` | `Math/deviation.py`: `getMinDifference` via `np.min` (B2); `getDifferenceInPercentage` docstring aligned to the (intended) theory-relative semantics + `np.max` (B3); `getMaxDifference` via `np.max` (same class as B2) |
| `24c26adad` | `Reader/readFiles.py`: `setDirection` uses `self._directiontype` (B4) |
| `7e5501907` | `Reader/paramReader.py`, `Reader/cmakeFlagReader.py`: close file handles (B5) |
| `528666828` | `Reader/dataReader.py`: `getValue` skips the header line (`skiprows=1`) (B6) |
| `a884ba3ba` | New unit tests `lib/python/test/picongpu/quick/testsuite/` (27 tests): `growthRate` (incl. the factor-1/2 regression), deviation helpers, physics helpers, `.param`/`.dat`/`.json` parsers, `ReadFiles` (incl. the `setDirection` regression). A `conftest.py` makes the standalone `testsuite` package importable and resets the global template-config state between tests (L3) |
| `997037074` | Fix the three stale docs (`structure`/`testbuilding`/`usage.rst`) |

Gate: `pytest quick/` went from `174 passed, 2 xfailed, 1 xpassed` to
`201 passed, 2 xfailed, 1 xpassed` (all new tests pass; nothing deleted).

## 5. Modernisation (commit b921eb8e2)

`lib/python/test/picongpu/end_to_end/khi_growthrate.py` re-expresses the
ESKHI validation as openPMD-consuming checks:

- `bx_amplitude_per_iteration(series)` -- f(t) = max|Bx| per iteration from
  the openPMD series (`meshes["B"]["x"]`, the same access pattern as
  `end_to_end/compare_particles.py::read_fields`); this replaces the
  `fields_energy.dat` `Bx` column.
- `times_omega_pe(series, density_si, gamma)` -- openPMD `time` (SI) times
  relativistic plasma frequency; replaces the `step` column times
  `DELTA_T_SI` from `.dat`/`.param`.
- `eskhi_growthrate_theory(gamma)` = `1/(sqrt(8)*gamma)` (same as
  `setups/ESKHI/config.py::theory`).
- `validate_eskhi_growthrate(path, gamma, density_si, acceptance=0.2)` --
  **reuses the corrected `testsuite.Math` (`growthRate`,
  `getMinDifference`, `getDifferenceInPercentage`, `getTestResult`) as the
  reference**, so the new path and the legacy path share one computation.

`lib/python/test/picongpu/end_to_end/test_khi_growthrate.py` (auto-marked
`slow`+`end_to_end` by `test/picongpu/conftest.py`):

- synthetic openPMD series whose Bx grows with the analytic esKHI rate ->
  asserts the pipeline recovers the analytic rate and the verdict is
  `passed` (exercises openPMD read -> growth rate -> analytic comparison);
- `test_real_khi_run_validation` -- validates a real KHI openPMD output
  provided via `PIC_KHI_OPENPMD` (defaults for `PIC_KHI_GAMMA`/
  `PIC_KHI_DENSITY_SI` taken from the KHI test's `.param` files: gamma=1.021,
  n=1e25).

Verification status: the full pipeline was verified end-to-end here by
running `validate_eskhi_growthrate` over the synthetic series with the
openpmd read layer substituted by an h5py-backed equivalent (files verified
correct on disk) -- theory `0.22097086912079605` vs simulation
`0.22097086912079608`, verdict `True`. The only part not executed in this
container is the literal `openpmd_api.load_chunk()` call, because of L7
(openpmd-api's 3.14 read path is broken here); the tests therefore
self-check the read path and skip with a clear message in broken
environments, running on CI's Python 3.11-3.13.

Nothing was deleted: the legacy `.dat`/`.param` path (`setups/`,
`Reader/dataReader`, `Reader/paramReader`) is untouched and remains the
fallback; it can be retired once the openPMD check is proven on a real run
and the flow's future is decided.

## 6. CI integration investigation

**Question:** should these validations run regularly as part of the test
suite / CI? They are physics post-processing of a *real* 3000-step
simulation -- `slow`/`end_to_end` class, not unit tests.

### 6.1 Cost of one run (CPU runner, single config)

| Step | Cost estimate | Notes |
|---|---|---|
| `pic-create` + `pic-build` (KHI only, 1 config) | ~10-20 min | as done by existing compile jobs; single case, `PIC_CI_COMPILE`-style flags |
| `mpiexec -n 1 picongpu -g 192 512 12 -s 3000` | ~5-20 min (unmeasured) | 1.18 M cells, 3000 steps, 1 rank on a cpuonly runner; **no in-repo benchmark exists -- CI never runs any simulation**; to be measured on a real runner |
| Validation (openPMD read + pytest) | < 1 min | 300 iterations x Bx(192x512x12) |
| **Total** | **~15-40 min per job** | one cpuonly runner slot |

### 6.2 Pre-conditions (not met today)

1. The KHI input set writes **no openPMD fields** (L6): a
   `etc/picongpu/picongpu.cfg` with a field dump of `B` (period ~10) must
   be added to `share/picongpu/tests/KHI_growthRate/` before the
   modernised check can consume anything.
2. The legacy `--fields_energy` flag no longer resolves to a plugin in this
   checkout (L5), so the old `validate.sh` path is not a working fallback.
3. `KHI_growthRate/bin/ci.sh` cannot be invoked as-is: it passes the dead
   `--fields_energy.period 10` flag (ci.sh:120, L5) and ends with the dead
   legacy `validate.sh` call (ci.sh:124, L5/B6). It must either be fixed
   (drop the dead flag, replace the `validate.sh` call with the openPMD
   pytest step) or bypassed, as in the corrected proposal below.
4. A decision is needed on whether the KHI growth-rate flow is still
   load-bearing (requester: uncertain).

### 6.3 Recommendation (proposal only -- not wired into CI)

Do **not** add this to the default MR pipeline: it would be the first
simulation run ever executed in CI, it needs pre-conditions 1-3 to be met
first, and its load-bearing status is unconfirmed. Instead:

**Proposed job** (to add once pre-conditions 1-3 are met and the requester
confirms), e.g. in a new `share/ci/run_khi_growthrate.sh` invoked by a
GitLab job tagged `cpuonly`, `x86_64`, triggered **manually and/or on a
scheduled (weekly) pipeline**, not per-MR. It mirrors
`KHI_growthRate/bin/ci.sh` but drops the dead `--fields_energy.period 10`
flag and the dead `validate.sh` call (pre-condition 3), and validates the
openPMD output with the modernised pytest check added on this branch:

```yaml
khi-growthrate-validation:
  stage: test
  image: <same alpaka-ci image as .base_pypicongpu_quick_test>
  tags: [cpuonly, x86_64]
  rules:
    - if: '$CI_PIPELINE_SOURCE == "schedule"'   # or: manual trigger on a branch
  script:
    - source $CI_PROJECT_DIR/share/ci/install/cmake.sh && source $CI_PROJECT_DIR/share/ci/install/gcc.sh
    - source $CI_PROJECT_DIR/share/ci/install/pypicongpu.sh   # python env + pytest
    - pic-create -f $CI_PROJECT_DIR/share/picongpu/tests/KHI_growthRate $CI_PROJECT_DIR/khi_run
    - cd $CI_PROJECT_DIR/khi_run && pic-build
    - mkdir -p simOutput && cd simOutput
    - mpiexec -n 1 ../bin/picongpu -d 1 1 1 -g 192 512 12 --periodic 1 1 1 -s 3000
    - cd $CI_PROJECT_DIR/lib/python/test/picongpu
    - PIC_KHI_OPENPMD=$CI_PROJECT_DIR/khi_run/simOutput/<filePrefix>/openpmd
        python3 -m pytest end_to_end/test_khi_growthrate.py -v
      # <filePrefix>: the openPMD file prefix of the picongpu.cfg added per
      # pre-condition 1 (the input set writes no openPMD output until then)
```

- Cost: ~15-40 min of one CPU runner per run (weekly = < 1 h/week of one
  CPU runner).
- Benefit: continuous physics regression signal for KHI + openPMD field
  output + the validation pipeline itself; failures surface as a normal CI
  job failure instead of an exit code in a manual log.
- Cheaper alternative for the *pipeline logic only*: run the synthetic
  `test_khi_growthrate.py` in the existing `pypicongpu` quick job -- it is
  fast (< 2 s) and would also guard against the L7 class of environment
  regressions. The change is one line in `share/ci/install/pypicongpu.sh`,
  after `python3 -m pytest quick/`:
  `python3 -m pytest end_to_end/test_khi_growthrate.py -q`. The
  auto-applied `slow`/`end_to_end` markers are metadata only (no `-m`
  filter is active there), and `test_real_khi_run_validation` self-skips
  without `PIC_KHI_OPENPMD`. Propose, don't wire: adopting it is the
  requester's call along with the open question below.

**Open question for the requester:** slow job on the main pipeline vs
manual/periodic trigger (recommendation above: manual/periodic until the
flow's load-bearing status is confirmed).

## 7. CHANGELOG

No `CHANGELOG.md` entry: the changelog is release-based (latest section
0.8.0) with per-PR references and has no "unreleased" section; this
exploratory branch has no PR number yet. Suggest adding an entry under the
next release's "tools" bucket, e.g. "fix and modernise KHI growth-rate
test tools (testsuite Math/Reader, openPMD-based validation)".

## 8. Follow-ups (out of scope here)

1. Add `etc/picongpu/picongpu.cfg` (openPMD field dump of `B`, period 10)
   to `share/picongpu/tests/KHI_growthRate/`; decide fate of the
   `--fields_energy` flag (L5/L6).
2. Decide whether the KHI flow is load-bearing; if yes, adopt the proposed
   CI job; if no, the legacy `setups/`+`Reader.dataReader/paramReader`
   `.dat`/`.param` path can be retired (deletion was explicitly out of
   scope for this task).
3. Fix or document L1 (`searchParameter` `openpmd` -> `UnboundLocalError`),
   L2 (dead `-o` option), L3 (`eval`/`exec` + global config state),
   L4 (`plot_2D` stub, `sys.exit(42)` swallowing).
4. Report the broken openpmd-api 3.14 read path (L7) upstream if it
   reproduces outside this container.
5. Measure the real 3000-step runtime on a CI runner to firm up the cost
   estimate in section 6.1.
