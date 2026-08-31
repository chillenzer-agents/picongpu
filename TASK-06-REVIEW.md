# Review — Task 06: Refine pypicongpu pydantic metadata (docstrings, constrained types, invariant validators)

- **Branch:** `task-06-pydantic-metadata` (tip `878f980b6`, base `task-04-radiation-picmi-filters` / `1bdb070aa`)
- **Reviewed:** 2026-08-31 · **Scope:** 17 commits, 64 files, +3281/−442
- **Verdict:** REQUEST CHANGES
  (One validator hard-rejects configurations PIConGPU actually runs (contradicting the confirmed "technical → warning" decision), and the advertised round-trip guarantee has an undocumented hole that task 07 will hit; both are fixable in a few lines.)

## 1. Summary

The branch executes the clarified scope well: every pypicongpu model got class/field docstrings with units and (mostly) correct C++ mappings, bare `float`/`int` quantities were tightened with `Annotated[..., Field(...)]` + a new machine-readable `SI("unit")` tag, 11 new `field_`/`model_validator`s encode physical/technical invariants, and the secondary picmi pass fixed real docstring errors (e.g. phase-space momentum `[kg*m/s]` → `[m_species c]`, verified against the C++ plugin help text). The two headline claims verify cleanly: the quick gate is 473 passed / 2 xfailed / 1 xpassed (base re-run: 190/2/1 — delta exactly the 283 new tests), and an independent 5-setup render battery (plain Yee, LWFA laser+species+moving window, radiation, checkpoint/binning/openPMD, synchrotron) produces **byte-identical** `.param`/`.cfg` files (80/80) and identical rendering contexts up to functor UUIDs. The new tests are not vacuous: 169 collected validation tests assert real invariants with `pytest.raises(ValidationError, match=...)`; the 94 docstring tests are the AST completeness check the task explicitly requires. The problems: (1) the new `Grid3D` divisibility check is a hard error where the C++ side auto-adjusts and the confirmed decision says technical invariants get warnings — it rejects previously runnable configurations; (2) `TWTSLaser`/`FromOpenPMDPulseLaser` break the branch's own "round-trip safety" guarantee; (3) laser.py docstrings cite C++ parameter names that don't exist in the rendered `.param`.

## 2. Findings

### 2.1 Critical

- **C1 — `grid.py:175-210` — the new super-cell/GPU divisibility invariants are hard `ValueError`s, but they are not C++ invariants; PIConGPU auto-adjusts, and the confirmed decision says technical soft invariants are warnings.**
  `Grid3D.check` now rejects (a) `cell_cnt` not evenly divisible by `gpu_cnt * super_cell_size` (grid.py:197-208) and (b) `grid_dist` chunks not multiples of `super_cell_size` (grid.py:187-194). The C++ side does not fail on such grids: `DomainAdjuster::multipleOfSuperCell` (include/picongpu/simulation/control/DomainAdjuster.hpp:172-194) rounds the local domain up to a full supercell, prints "Local grid size is not a multiple of supercell size.", adjusts the global size, and continues — the documented "automatic grid adjustment" behavior. So these are *soft technical* invariants, and the task's Decisions ("Soft invariants: hard error for physical, warning for technical — confirmed") plus the checklist's own hedge ("super cell divides grid (**if that's a C++ invariant**)") point to a warning, not a hard error. The PR also mislabels the provenance: "previous `assert`s converted to `ValueError`" — the pre-existing assert only checked `sum(grid_dist) == cell_cnt`; both divisibility checks are **new** in this branch.
  - *Evidence:* repro (`/tmp/opencode/review-06/probe2.py`), run against both trees:
    ```
    1a cell_cnt=(100,16,16) n_gpus=(3,1,1):   base: OK    branch: REJECTED
    1b cell_cnt=(16,16,16) super_cell=(3,2,2): base: OK    branch: REJECTED
    1c grid_dist=([10,6],...) super_cell=(3,..): base: OK  branch: REJECTED
    ```
    C++ path: `DomainAdjuster.hpp:88-96` (call site), `:172-194` (round-up + message + continue).
  - *Suggested fix:* downgrade both branches to `warnings.warn(...)` (keep the messages; note the rendered N.cfg is unchanged either way — C++ will adjust the domain at runtime and print the adjusted size), and update the class docstring to say PIConGPU rounds the domain up. If the maintainers prefer the hard error after all, that is a deliberate policy change: say so in the task/PR ("stricter than C++ on purpose: C++ silently resizes your domain") rather than presenting it as a port of an existing assert.

### 2.2 Major

- **M1 — `laser.py:293,358` — the advertised "round-trip safety" guarantee is broken for `TWTSLaser` and `FromOpenPMDPulseLaser`; task 07 is told it can rely on it.**
  The PR's *Why* section claims "every validator is satisfiable from `model_dump(mode='json')` output, which task 07 (serialization) builds on". `TWTSLaser` re-declares `huygens_surface_positions` (laser.py:358) without the `BeforeValidator(deserialise_huygens)` that `_BaseLaser` has (laser.py:130-134); the re-declaration drops the deserializer. `FromOpenPMDPulseLaser` (plain `BaseModel`, laser.py:248) declares the field at laser.py:293 with the `PlainSerializer` only. Both therefore fail to reconstruct from their own dump:
  - *Evidence:* `/tmp/opencode/review-06/probe1.py`:
    ```
    2a FromOpenPMD round-trip: FAILS -> 1 validation error for FromOpenPMDPulseLaser (list_type)
    2b TWTS round-trip:        FAILS -> 1 validation error for TWTSLaser
    2c Gaussian round-trip:    OK
    ```
    (the dump serializes huygens to `{row_x:{negative,positive},...}` via `_get_huygens_surface_serialized`, which the field no longer accepts).
  - *Suggested fix:* in `TWTSLaser`, delete the re-declared field entirely (inherit the annotated one from `_BaseLaser`); in `FromOpenPMDPulseLaser`, add `BeforeValidator(deserialise_huygens)` (or factor the field into a small mixin shared by all three). Then add both classes to `_MODELS` in `test_roundtrip.py` so the guarantee is actually tested for every laser type, and fix the PR wording ("every laser type", not "every validator").

### 2.3 Minor

- **m1 — `laser.py:109,112,117,120` — four "C++ name:" references in the base-laser docstrings name constants that don't exist in the rendered `.param`.**
  Rendered names (lib/python/picongpu/templates/include/picongpu/param/incidentField.param.mustache:30-51): `WAVE_LENGTH_SI` (docstring says `lambda_SI`), `PULSE_DURATION_SI` (docstring says `pulselength_SI`), `LASER_PHASE` (docstring says `PHI` — `PHI` is the TWTS `laserIncidenceAngle` constant at mustache:146), `focus_position[]`/`FOCUS_POSITION_*_SI` (docstring says `focus_SI`). All four names are absent from `include/picongpu/param/` (verified with ripgrep). The rest of the package's C++ mappings are accurate (spot-checked simulation.param, incidentField param `AMPLITUDE_SI`/`W0_SI`/`PULSE_INIT`/`BETA_0`, synchrotron.param, UnitConversion.hpp, PhaseSpace.x.cpp, Checkpointing.hpp) — laser.py is the outlier.
  - *Suggested fix:* replace with the four real names; add a quick cross-check convention (grep the mustache before writing the mapping).
- **m2 — checklist item "enum/union exhaustiveness ... a model-level comment + test mapping model union members to templates" is missing.**
  No test or comment exists for `AnyLaser` (laser.py:373), `AnyPlugin` (output/__init__.py:17), `AnySolver` (field_solver/__init__.py:4), `AnyLayout`, `AnyOperation`: a future union member without a render template still fails only at render/compile time.
  - *Suggested fix:* one quick test that, for each `get_type_hints` member of the public unions, asserts the corresponding template fragment exists (or at least renders a minimal instance), plus a one-line comment at each union definition.
- **m3 — `openpmd_plugin.py:174-177` — `FieldDump.filtername` docstring asserts "must be a valid C++ identifier" but nothing enforces it.**
  Inconsistent with the species/functor/binner/axis name validators added in this same task; direct construction of `FieldDump(filtername="bad name")` passes and later renders broken C++.
  - *Suggested fix:* add `@field_validator("filtername")` with the existing `^[A-Za-z_][A-Za-z0-9_]*$` pattern (skip `None`), or soften the docstring to "derived from a validated functor name".
- **m4 — `species.py:250-277` — `Species.check()` no longer enforces anything that construction doesn't already.**
  The name regex duplicates `_validate_name` (species.py:196-206); the constants-uniqueness check is vacuous because `Constants` has one field per constant type (duplicates are structurally impossible); position/momentum/attribute-uniqueness now live in `_validate_attributes`. The PR's "kept for explicit re-checks of the remaining invariants" overstates what remains.
  - *Suggested fix:* either delete `check()` (it has no callers in the repo) or reduce it to the constants check with a comment that it is retained for API compatibility.
- **m5 — `simulation.py:129-143` — the laser-fits-in-run warning assumes `pulse_duration_si * pulse_init` for every laser type.**
  For `TWTSLaser` the on/off window (`windowStart/windowEnd`, in step units) defines the pulse's temporal extent, and `PlaneWaveLaser` is a continuous wave — for both, the Gaussian-pulse heuristic can silently not fire (or misfire). Low impact (soft warning), but the comment should say the check is a heuristic that only models `_BaseLaser`-style pulses.
  - *Suggested fix:* keep the heuristic; either extend per type (TWTS: `windowEnd * delta_t_si`) or note the limitation in the docstring/comment.
- **m6 — PR artifact contains small inaccurate claims.**
  (a) "test_validation.py — new (131 tests)": 131 *test functions* → **169** collected tests (the +283 total is nonetheless exact: 169+94+20). (b) "The single remaining warning ... is on a path no test triggers": false — `test_laser_exceeding_run_warns` (test_validation.py:142-145) triggers it (caught via `pytest.warns`). (c) "94 models / 372 public fields": the shipped AST logic yields 94 models / **325** public fields. (d) "45 model files refined": 53 pypicongpu module files changed. (e) the grid "(previous `assert`s converted to `ValueError`)" provenance claim — see C1.
  - *Suggested fix:* correct the numbers/wording in TASK-06-PR-PROPOSAL.md before merge; none of the functional claims are affected.

### 2.4 Nits

- **n1 — `test_roundtrip.py:163-168` — round-trip reconstruction passes computed-field keys (`modenumber`, `species_name`, ... — verified present in `model_dump(mode="json")`) back into the constructor and passes only because pydantic's default is `extra='ignore'`.**
  If any model ever opts into `extra='forbid'`, these tests break in a confusing way. Consider `type(model).model_validate(dumped)` with an explicit comment, or dumping with computed fields excluded.

## 3. Requirement traceability

| # | Requirement (from task file) | Status | Where / note |
|---|---|---|---|
| 1 | Docstrings: class + every public field with meaning, quantity, SI units, range, C++ parameter | met (one file deficient) | 94/94 models pass the new AST completeness test (base: 68 fail); units stated everywhere incl. documented non-SI exceptions (keV for `Temperature`/`EnergyHistogram`, matching the C++ interface). laser.py C++ names wrong → m1. |
| 2 | Constrained types instead of bare `float`/`int` for quantities with known invariants | met | e.g. `base_density: Annotated[float, Field(gt=0.0), SI("m^-3")]` (simulation.py:48), counts `Field(ge=1)`, fractions `gt/lt`. |
| 3 | `field_validator`/`model_validator` invariants raising `ValidationError` | met, one mis-calibrated | 11 new validators + many field constraints, all verified against C++ (nyquist (0,1) per radiation.param:97-100; minEnergy default hbar/dt per synchrotron.param:41; inCellOffset [0,1) per particle.param:222; log-axis zero rule per LogAxis.hpp:229-231; `checkpoint.timePeriod` in minutes per Checkpointing.hpp:135-136; PhaseSpace momentum `[m_species c]` per PhaseSpace.x.cpp:90-91). C1 is the exception. |
| 4 | Negative test per new/changed validator + existing positive tests keep passing | met | every new invariant has ≥1 `pytest.raises(ValidationError, match=...)` (checked one-by-one); suite green at 473. |
| 5 | Per-module passes in suggested order | met | commit log: simulation/walltime/movingwindow → grid → species → laser → timestepspec → radiation → checkpoint → openpmd → output → collisions/functors → docstrings → round-trip. |
| 6 | House style: `Annotated[..., Field(...)]` idiom (grid.py) | met | used consistently across the package. |
| 7 | Pydantic-native, machine-readable invariants (Field/Annotated metadata; SI tag; no parallel machinery) | met | `SI` tags and constraints are visible in `model_fields[].metadata` (verified: `Gt(gt=0.0), SI('m^-3')` for `base_density`); no side-channel. |
| 8 | Rendered `.param`/`.cfg` byte-identical for valid inputs | met | independent 5-setup battery vs task-04 base: identical file sets (630 files), **80/80 `.param`/`.cfg` byte-identical (sha256, no normalization needed)**; rendering contexts identical after functor-UUID normalization; remaining diffs are machine-specific paths only. |
| 9 | Changelog entry "stricter input validation" | met | CHANGELOG.md Unreleased (also mentions round-trip). |
| 10 | Physical invariants (positive magnitudes, free charge sign, counts, min<max ranges, v<c) | met | mass `ge=0` with documented, correct photon exception (rendered synchrotron setup shows `MassRatio 0.0` accepted); charge sign free; `Drift` gamma≥1 + unit vector; TWTS `\|beta0\|≤1`; all frequency/Zq/range `min<max` checks in place. |
| 11 | Cross-field: laser pulse within run time | met (as warning) | `Simulation._check_laser_fits_in_run` (simulation.py:129) — warning per the technical/soft decision; see m5 for the heuristic's limits. |
| 12 | Cross-field: radiation `start`/`end` within `[0, time_steps]` (if set) | partial | only `start >= 0`, `end >= 0` (matches C++ `uint32_t`, Radiation.x.cpp:216-222); no bound against `time_steps` — not expressible at the plugin level, would need a `Simulation`-level validator; not implemented, not documented as deferred. |
| 13 | Cross-field: TimeStepSpec `start <= end` | met (justified deviation) | deliberately not enforced: the existing quick suite runs `start > stop` specs through the PICMI conversion expecting an empty set (e.g. `TimeStepSpec[-20:-50:10]` in test_timestepspec.py), under `filterwarnings = error` (lib/python/pyproject.toml:92) — enforcement would break the suite. Documented in `Spec.stop` docstring + PR. |
| 14 | walltime vs steps consistency as warning (decide) | met (decided: not implemented) | documented rationale (walltime is hardware-dependent; no computable invariant) in PR notes — reasonable. |
| 15 | Technical: species/plugin/functor names are C++ identifiers at model level | met | `Species._validate_name` (moved out of dead `check()`), `ParticleFunctor._validate_name`, `Binning._validate_binner_name`, `BinningAxis._validate_axis_name`; gap: `FieldDump.filtername` → m3. |
| 16 | `customuserinput` keys at pydantic level (consider) | met (decided: serializer level) | documented as duplicate layer; existing serializer `ValueError`s unchanged. |
| 17 | Enum/union exhaustiveness (model comment + template-mapping test) | missed | nothing implemented → m2. |
| 18 | Secondary picmi pass (docstrings where picmi has own fields) | met | docstring corrections only (incl. the correct `m_species c` fix); invariants enforced downstream via conversion to the now-validated pypicongpu models — no duplicate layers, as decided. |
| 19 | Decisions: physical → hard error, technical → warning | violated (one instance) | grid divisibility hard error → C1; laser warning and TimeStepSpec handling are compliant. |
| 20 | Verification: quick gate green; docstring-check pytest step; pre-commit green | met | 473/2/1 re-run (base 190/2/1 re-run); 94 docstring tests; pre-commit passes on all 64 changed files (ruff, ruff-format, encoding, ...). |

## 4. Claim verification (author artifact)

| Claim (from TASK-06-PR-PROPOSAL.md) | Re-verified? | Result / delta |
|---|---|---|
| Quick gate: `473 passed, 2 xfailed, 1 xpassed`; baseline `190 passed, 2 xfailed, 1 xpassed`; +283 = new validation/docstring/round-trip tests | yes | Exact match on both sides (base re-run in scratch checkout: 190/2/1). Delta decomposes exactly: 169 validation + 94 docstring + 20 round-trip. xfail/xpass sets unchanged. |
| Rendered-output regression: battery of 10 setups renders byte-identical `.param`/`.cfg`/rendering-context (functor-uuid suffixes normalised) | yes (independent 5-setup battery) | Verified with basic, lwfa (laser+2 species+moving window), radiation (gamma filter), checkpoint/binning/openPMD/ParticleDump, synchrotron (photon species): identical file sets; 80/80 `.param`/`.cfg` byte-identical with no normalization; rendering contexts identical modulo functor UUIDs; other diffs are environment paths only. |
| Docstring completeness: 94 models / 372 public fields, 0 violations (audit baseline: 231 violations) | partial | 94 models ✓ and 0 violations ✓ (and the base code fails the same checker: 68/94 models — direction verified). Field count not reproducible: the shipped AST logic counts 325 public fields, not 372 (m6c). |
| test_validation.py "131 tests" | partial | 131 test *functions*, 169 collected tests (m6a); total +283 still exact. |
| "The single remaining warning ... is on a path no test triggers" | no | `test_laser_exceeding_run_warns` triggers it and passes via `pytest.warns` (m6b). |
| "45 model files refined" | partial | 53 pypicongpu module files changed (m6d). |
| Round-trip: "every validator is satisfiable from `model_dump(mode='json')` output, which task 07 builds on"; 20 representative models round-trip | no | The 20 tested models do round-trip, but `TWTSLaser` and `FromOpenPMDPulseLaser` fail on their own dumps (M1) — the universal claim is false. |
| Mass `ge=0` (deviation from audit hint) | yes | Justified and verified: PICMI photon species render `MassRatio 0.0 / baseMass` in the synchrotron battery; a `gt=0` would break the only massless-species path. Good override of the audit hint. |
| `TimeStepSpec` without `start <= stop` (deviation from checklist) | yes | Justified: existing suite exercises `start > stop` → empty set under `filterwarnings = error` (test_timestepspec.py, lib/python/pyproject.toml:92). |
| Checkpoint `@typeguard.typechecked` now redundant, left in, cleanup later (coordinator open item) | yes | Documented consistently in PR "Notes for follow-up tasks"; decorator remains at checkpoint.py:17. |
| Custom-serializer models (`OpenPMDPlugin`, `UnitDimension`) excluded from round-trip guarantee (coordinator open item) | yes | Accurate — both have top-level `model_serializer` (unit_dimension.py:38-40) producing non-re-instantiable output; exclusion documented in PR notes and the test_roundtrip module docstring. |
| Pre-commit green | yes (changed files) | `pre-commit run --files <64 changed>` — all hooks passed. |

## 5. Design discussion

**The approach is right and the execution is largely high-quality.** Building invariants as `Field`/`Annotated` metadata + `model_validator`s (with `SI` tags as plain `Annotated` metadata) is exactly the "pydantic-native, machine-readable" machinery the requester asked for; the constraints are visible in `model_fields` and JSON-schema generation, and the rendered interface is provably untouched (independently verified). The docstring discipline (units policy line per class, C++ counterpart per class, C++ name + units + range per field) is consistent and, in 52 of 53 files, factually correct — the laser.py exceptions (m1) are the only real metadata-accuracy defect. The secondary picmi pass correctly avoids a duplicate validation layer (picmi models validate at conversion time), and the "no duplicate validation layers" principle was followed everywhere else (customuserinput, picmi).

**Where the judgment calls went wrong or thin:**

1. **Grid divisibility (C1).** The task file's "if that's a C++ invariant" was the operative condition, and the C++ answer is unambiguous: `DomainAdjuster` auto-adjusts (rounds up, prints, continues). The confirmed decision then dictates a warning. The PR's "(previous `assert`s converted to `ValueError`)" suggests the author believed this was pre-existing check behavior; it wasn't. A maintainer should decide policy explicitly: (a) warning + docstring "PIConGPU will round the domain up at runtime" (decision-compliant, my recommendation), or (b) hard error as a *deliberate* strictening beyond C++ (then say so, since it rejects previously-working user setups and goes against the confirmed decision).
2. **Round-trip as a load-bearing guarantee (M1).** Round-trip safety is not a task requirement — the author introduced it as the foundation for task 07. That makes the gap worse, not better: a self-declared contract that task 07 is told to rely on must be complete (every laser type) and tested. The fix is small (remove one field re-declaration, add one `BeforeValidator`, add two test entries); the follow-up notes should then say "all field-preserving models incl. all lasers" instead of implying the 20 tested models are representative.
3. **Warning calibration.** The laser-fits-in-run warning is the only `warnings.warn` in the branch, and it's the right choice for a soft technical concern — but the PR's "no test triggers it" claim shows the author under-verified their own test suite. With `filterwarnings = error` in the suite config, any future test that constructs a too-long laser will fail unless it catches the warning; a short comment in the suite config or test module pointing this out would help the next task.
4. **What a human maintainer should weigh:** the branch changes construction-time behavior for users (unphysical values now raise at model time — intended, changelog covers it). The *only* behavior change that goes beyond "reject unphysical" is the grid divisibility error (C1), which rejects *physical but suboptimally-decomposed* grids; that is the one to fix before merge. The remaining minors are cleanup/accuracy items that could also be follow-ups, except m2 (union-exhaustiveness test), which is cheap insurance for exactly the kind of render-time surprise this task set out to eliminate.

## 6. Prioritized next steps

1. **C1:** change both new branches of `Grid3D.check` (grid.py:187-210) from `raise ValueError` to `warnings.warn` (keep messages, add "PIConGPU will round the domain up at runtime"), update the field docstring, convert the two "raises" tests in test_validation.py:212-223 to `pytest.warns`, and correct the PR's "previous assert" provenance claim. (Or: get explicit maintainer sign-off for the hard-error policy and document it as a deliberate deviation.)
2. **M1:** delete the re-declared `huygens_surface_positions` in `TWTSLaser` (laser.py:358), add `BeforeValidator(deserialise_huygens)` to `FromOpenPMDPulseLaser` (laser.py:293), add both to `test_roundtrip.py::_MODELS`, and fix the universal round-trip wording in the PR.
3. **m1:** correct the four C++ names in laser.py:109,112,117,120 to `WAVE_LENGTH_SI`, `PULSE_DURATION_SI`, `LASER_PHASE`, `focus_position[]`/`FOCUS_POSITION_*_SI`.
4. **m2:** add the union-exhaustiveness quick test (union members → template presence) and one-line comments at `AnyLaser`/`AnyPlugin`/`AnySolver`/`AnyLayout`/`AnyOperation`.
5. **m3:** enforce (or soften) the `FieldDump.filtername` identifier invariant.
6. **m4/m5/m6/n1:** delete or shrink `Species.check()`, note the laser-warning heuristic's scope, correct the PR's small number/wording inaccuracies, and add the `extra='ignore'` comment in test_roundtrip.py.

## FYI (inherited from base, not scored here)

- `Temperature.temperature_kev` uses `gt=0.0` (rejects 0 keV) while directional components allow `>= 0` — pre-existing asymmetry at the base (mass.py/temperature.py unchanged in behavior by this task).
- The quick-suite log is polluted by `rocrate_validator` SHACL noise ("ConjunctiveGraph is deprecated...") in both base and branch runs — pre-existing environment issue.
- `@typeguard.typechecked` also remains on `Species` (species.py) and `None_` (ionizationcurrent/none_.py); the PR notes only mention the `Checkpoint` instances. Same "redundant but left in" treatment — a single cleanup commit could cover all of them.
- At the base, picmi `BinSpec` accepted any `kind` string, so `kind="position"` rendered `axis::createPosition` — nonexistent C++ (only `createLinear`/`createLog` exist, axis/LinearAxis.hpp:204, LogAxis.hpp:225). The task-06 `Literal["Linear","Log"]` plus the picmi `.capitalize()` conversion now fail fast on such input — an improvement, though the base's latent bug is inherited context.
