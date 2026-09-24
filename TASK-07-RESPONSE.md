# Task 07 - Rework Response

All findings verified against the real flow (reproduced the C1 and m3 crashes
in the venv; ran the base<->branch render battery in scratch with both the
task-06 and task-07 venvs). No findings rejected; two suggested fixes were
corrected for correctness (noted below).

## Findings

- **C1 - accepted** (`dd250a7b0`). Added `return_type=list[dict[str, Any]]`
  to `_species_pairs_serializer` and `return_type=dict[str, Any]` to
  `_serialize_functor`. Reproduced the rendering-context `ValidationError` on
  a `ConstLogCollision` setup first; after the fix it generates,
  `collision.param` renders `coulombLog = 12.0_X` and
  `Pair<species_electron,species_hydrogen>`, and reload -> regenerate is
  byte-identical. Added the committed e2e quick test (generate a real
  collision setup via the picmi interaction API, reload both metadata JSONs,
  regenerate, diff `include/`+`etc/`).
- **M1 - accepted** (`da02b19f4`). Restated the render-regression claim
  against a re-run 11-setup battery (task-06 base vs this branch, `diff -r`
  of the rendered `include/`+`etc/`): 9 setups byte-identical; filtered
  binning differs only in the deliberate stable functor typename (the base
  was a fresh random `uuid4` per generation, inconsistent even across files
  of one render); the real-collision setup is new to this branch (the base
  cannot generate it). Real results recorded in the PR proposal.
- **m1 - accepted** (`31e36500d`). Added
  `assert restored.model_dump(mode="json") == runner_json` to
  `test_runner_roundtrips_from_runner_metadata`, matching the Simulation
  counterpart test.
- **m2 - accepted** (`52bb22a5c`, style `e61e5c3ac`). `_parse_functor` now
  raises a `ValueError` (surfacing as a `ValidationError`) instead of a raw
  `KeyError` when `data.coulomb_log` is missing, and guards against `data`
  not being a dict. Added a regression test.
- **m3 - accepted, suggested fix corrected** (`19aa1242f`). Reproduced the
  `model_dump` crash on `lambda i: (i, 1, 0)`. The review's sort-by-basis fix
  does not work: the installed sympy (1.14) basis terms are not orderable
  (`TypeError` on `e.i < e.j`), so I normalised component-wise (divide by the
  symbolic magnitude) instead. Also canonicalised the (de)serializer through
  `sympify`/`srepr` so a python scalar and its sympy counterpart serialise
  identically. Added a non-unit corpus entry (`lambda i: (i, 1, 0)`) and a
  test asserting the reconstructed mapping is unit-length and collinear with
  the original.
- **m4 - accepted** (`78ea173d0`). `_parse_project_path` now requires
  `class in (None, "Directory")` plus a `location`, so unrelated dicts are
  rejected with a validation error; plain strings and the round-tripped
  Directory form are still accepted.
- **n1 - accepted, fix extended** (`4091b4bbd`). Mangled the canonical
  placeholder to `pypicongpu_observer_index`. The rename alone was not
  enough: the validator evaluated the user mapping at a plain
  `Symbol("index")`, which still conflated a user's own `index` constant with
  the observer index at construction, so the validator/normaliser now use the
  mangled placeholder too. Verified a user `Symbol("index")` constant survives
  the round-trip as a free symbol; rendered C++ is unchanged
  (`component_expressions` still renders `index`).
- **n2 - accepted** (`da02b19f4`). The two exceptions the review flagged
  (collision generation, non-unit radiation directions) are fixed (C1, m3),
  so the task-13 guarantee now holds; the PR note says so and cites the
  covering regression tests.

## Out of scope / notes

- **Pre-existing flake fixed** (`f97d5d629`): `SimpleDensity.validate_species`
  sorted `set(species)` by density ratio only, so equal-ratio species were
  ordered by set iteration order (per-process string-hash-seed + insertion
  order dependent). The reconstruction path feeds a different insertion
  order, so the round trip flipped the order in roughly one of eight
  processes, breaking the identical re-serialisation contract and flaking
  `test_model_roundtrip[SimpleDensity]`. Reproduced on the review tip, so it
  is not a regression of this branch. Tie-broke the sort on the (unique)
  species name; distinct-ratio setups are unchanged.
- **Baseline count discrepancy**: the review cites `534 passed` at tip
  `b6374eafd`, but the review commit `99c463cf4` is a later, updated tip at
  which the gate is `572 passed` (38 tests were added between the two tips).
  My gate numbers are measured against `99c463cf4`.
- **Inherited picmi-layer issues** (coordinator QC, not scored): the
  `add_interaction` silent collision drop, the `KeyError: 'other'` crash, and
  `CollisionalPhysicsSetup` missing from the top-level `picmi` namespace are
  inherited and out of scope. Noted here for a follow-up ticket; not fixed.

## Gates

- `cd lib/python/test/picongpu && python -m pytest quick/ -q` ->
  **577 passed, 2 xfailed, 1 xpassed, 3512 subtests passed** (review tip
  `99c463cf4`: 572 passed; +5 = the rework's new regression tests).
- `pre-commit run --all-files` -> exit 0 (all hooks passed, incl.
  require-ascii).
