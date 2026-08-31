# PR proposal — task 08: tighten the ruff rule set to `select = ["ALL"]`

Branch: `task-08-ruff-all` (31 code commits, steps 0–30, on `dev` =
b4e4ca5b2, plus this artifact; the review-response rework commits are
listed in TASK-08-RESPONSE.md)
Footprint: 240 files, +2280 / −2066 (code only; this artifact adds one
file) — 239 files are auto-fixes + small manual fixes; the substantive
decisions are all in `ruff.toml`.

## What this PR does

PIConGPU previously had **no ruff configuration at all**: pre-commit ran
`ruff` with `--fix --ignore E721` and `ruff-format --line-length 120`, i.e.
only the default rule set (E4/E7/E9/F). This PR introduces a repo-root
`ruff.toml` as the single source of truth and tightens the rule set in
31 incremental commits (steps 0–30: config foundation, then one commit
per rule batch, each independently green) up to `select = ["ALL"]` —
the complete stable ruff rule set.

Every exception (global `ignore`, `per-file-ignores`, `# noqa`) carries a
written justification in `ruff.toml`. The final step includes an
exception-minimisation pass: every `ignore` entry and every per-file rule
was audited by re-running ruff with the entry removed, and entries that
suppressed nothing were dropped (PT018; four N8xx rules on
`lib/python/test/testsuite/**` that the broader `lib/python/test/**` entry
already covers).

## Suggested PR structure

The 31 commits (steps 0–30) map 1:1 to the spec's incremental steps and
can be merged as one PR or squashed per batch. Suggested PR description
per batch is in each commit message; the full exception list lives in
`ruff.toml` comments.

## Rule batches (in landing order)

| step | commit | batch | highlights |
|---|---|---|---|
| 0 | c0f1f29f9 | config foundation | `ruff.toml` created with today's effective set; `--ignore E721` / `--line-length` args moved out of `.pre-commit-config.yaml` |
| 1 | c59316215 | E | 68 long lines wrapped |
| 2 | 81cdd40f9 | W | zero violations |
| 3 | cb95ff2c9 | I (isort) | 181 import-block fixes across 172 Python files (plus 2 example notebooks, `ruff.toml`, and one script) |
| 4 | 50e4a6119 | N (pep8-naming) | per-file-ignores for intentional C++-mirrored / physics notation |
| 5 | 96a86e233 | B (bugbear) | manual fixes |
| 6 | 661807b90 | UP (pyupgrade) | 253 fixes |
| 7 | 875daec19 | C4 (comprehensions) | 87 fixes |
| 8 | 7388b0e9e | SIM | 55 auto + 19 manual |
| 9 | 9f592ea8c | A (builtins) | targeted exceptions for domain terms (range, type, format, input, copyright) |
| 10 | 607545dd0 | RET | 84 fixes |
| 11 | e7d4732e2 | PLR | complexity thresholds ignored with justification (physics functions) |
| 12 | 9651430cb | G | lazy %-format logging |
| 13 | d55e15750 | FURB (refurb) | |
| 14 | 3a9343761 | PERF | |
| 15 | e54e8cc5d | ISC | |
| 16 | 282d9218d | PIE | |
| 17 | a875d350f | PT (pytest-style) | TestCase-based tests: PT009/011/012/027 ignored with justification |
| 18 | aff3090ed | RUF | 89 auto + 11 manual |
| 19 | 89d26a20a | S (bandit) | 36 S101 `assert`→`AssertionError` (18 library, 16 extra scripts, 2 docs-example); S110 try-except-pass restructure; per-file-ignores for test/example/tool trees |
| 20 | 000e3e8b3 | T20 (print) | 4 debug prints → `logging.debug`; console-output tools per-file-ignored |
| 21 | 32b4ea31d | ARG | 60 unused args renamed to `_`-prefixed; 5 API-contract params noqa'd |
| 22 | 61e3d320c | PLC | `X as X` re-export idiom preserved (radiation.py, collision.py); `.values()`/`.items()`; PLC0415 per-file-ignores |
| 23 | b99f28e44 | ERA (eradicate) | dead commented-out code removed / kept where intentional |
| 24 | 0b0c4a374 | INP | script/test trees are not packages by design |
| 25 | d19722678 | PD (pandas-vet) | `.values` → `.to_numpy()`, `inplace` → rebinding |
| 26 | 7c876c898 | LOG | module-level `logger = logging.getLogger(__name__)` in 9 files |
| 27 | d1e122e59 | PLW | see "real bugs found" below |
| 28 | 072b7adf9 | PLE | 10× `return super().__init__(...)` → `super().__init__(...)` in `__init__` |
| 29 | 5dcb10860 | NPY/EXE/PGH/DTZ/PYI/SLOT/YTT | `np.NaN`→`np.nan`; legacy `np.random.*` → `default_rng()`; `namedtuple` → `typing.NamedTuple`; `__slots__ = ()`; version-info tuple comparison; FLYonPIC `#! @detail` doc markers per-file-ignored |
| 30 | 40915ba40 | **select = ["ALL"]** | RSE102 + ICN001 fixed; justified family ignores added; SLF001/DTZ005 per-file-ignores; exception-minimisation pass |

## Decisions on the ALL step

- **Preview rules stay off** (no `preview = true`): they are unstable across
  ruff releases and the pre-commit rev is pinned; enabling them would shift
  lint outcomes on every ruff bump without a code change.
- **Justified family ignores** (each with a one-line+ justification in
  `ruff.toml`):
  - `D` (pydocstyle, ~3.8k violations): docstrings deliberately mix conventions
    (module headers, Google sections, project `@param`/`@detail`) and are
    consumed by Sphinx; normalising them is a separate documentation
    project.
  - `ANN` (~2.5k violations): full annotation coverage is a separate typing project;
    public API boundaries are runtime-guarded with `typeguard`.
  - `TRY`/`EM` (~600 violations): the codebase raises built-in exceptions with inline
    descriptive messages and has no custom exception classes; introducing
    them is API design, not lint hygiene.
  - `COM812`: conflicts with `ruff format`'s magic-trailing-comma (ruff
    docs recommend ignoring it when using the formatter).
  - `PTH` (~110 violations): `os.path` is the consistent style in
    scripts/tools; pathlib migration is a separate modernisation.
  - `FBT`: boolean flags mirror the C++ API; restructuring is breaking.
  - `BLE001`: broad `except Exception` catches are deliberate
    compatibility/fallback points.
  - `TID252` (80): relative imports are the package convention (TID251 is
    clean); rewriting parent imports is churn without benefit.
  - `C901`: joins the existing PLR09xx complexity ignores (physics
    functions carry many cases).
  - `TD`/`FIX`: TODO/XXX tags predate the `TODO(username):` convention;
    inventing assignees would be noise.
- **Kept from the incremental batches** (still needed, audited): E721
  (scoped to per-file-ignores for the two exact-type-check sites during
  the review rework), PLR0911/0912/0913/0915, PLR2004, PT009/011/012/027.

## Real bugs found by the linter (call-outs)

1. **`particle_functor.py` — `NotImplementedError()` without `raise`**
   (PLW0133): the `Particle.get` stub assigned nothing and returned `None`;
   calling it silently "worked" instead of raising. Now `raise
   NotImplementedError(...)`.
2. **`S110`** (bandit, batch 19, try-except-pass): the
   `try`/`except Exception`/`pass` block in `species_requirements.py`
   was restructured so the comparison result is returned inside the
   `try` and `False` from the `except`; the broad `except Exception`
   is kept deliberately because the operands may be incomparable.
3. **S101 in library, extra-script, and docs-example code** (batch 19):
   36 `assert`s (18/16/2) converted to `raise AssertionError(...)` —
   *intentionally* changes `python -O` behaviour
   (assertions are now kept). This is the desired direction (PIConGPU
   library code should not drop checks in optimized mode) but is a
   behaviour change.
4. **UP036** (final step): the friendly "Python 3.11 required" checks in
   `picmi/__init__.py` / `pypicongpu/__init__.py` would be removed by
   pyupgrade as "outdated"; they are kept with `# noqa: UP036` since they
   are user-facing errors.

## Verification (per step and final)

- `ruff check .` → 0 violations (ruff 0.12.10, matching the pinned
  pre-commit rev)
- `ruff format --check .` → 0 diffs (291 files)
- `pre-commit run --all-files` → all hooks passed
- `cd lib/python/test/picongpu && python -m pytest quick/` →
  **174 passed, 2 xfailed, 1 xpassed** — identical to the pre-PR baseline,
  i.e. no rule fix changed test-observable behaviour.

## Integration notes

- **This branch must merge last** among the concurrent Python-editing
  agents' branches: it touches ~240 Python files, so it will conflict with
  any branch that edits the same files.
- **Post-integration sweep:** after the other branches land and this one
  merges last, a final `ruff check --fix` + `ruff format` sweep runs on
  the *integrated* tree before merge (the coordinator's plan assumes it),
  so any new violations introduced by the other branches are resolved
  there rather than in this PR.
- **Task 03** (jupyter pre-commit hooks) also edits
  `.pre-commit-config.yaml`; suggested merge order is 03 → 08. The
  `types_or: [python, pyi, jupyter]` hooks are kept; the notebook linting
  is covered by this config (two example `.ipynb` files are linted, and the
  `pretty format json` hook is happy with the notebook edits).
- No CHANGELOG entry: the repo changelog is release-based (last entry
  0.8.0) and recent dev PRs do not add per-change entries; this will be
  picked up at release time.

## Suggested PR title

`Python: tighten ruff rule set to select = ["ALL"]`
