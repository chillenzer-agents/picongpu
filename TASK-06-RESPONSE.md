# Re-work Response - Task 06 (pypicongpu pydantic metadata)

Base: rebased review commit `b55c79ecf`; all re-work is new commits on top
(no history rewrites). Every finding was independently re-verified (code +
C++ + live renders) before disposition. No finding was rejected.

## Dispositions

| ID | Disposition | Commit(s) |
|----|-------------|-----------|
| C1 | Fixed: both new `Grid3D` divisibility checks downgraded from hard `ValueError` to `warnings.warn` (the per-axis `grid_dist` sum check stays a hard error). C++ evidence: `DomainAdjuster::multipleOfSuperCell` (include/picongpu/simulation/control/DomainAdjuster.hpp:176-192) rounds the local domain up to a full super cell, prints the adjusted size, and continues - PIConGPU runs such grids, so they are a soft technical invariant (warning per the confirmed decision). Docstrings updated to say PIConGPU rounds the domain up; the two "raises" tests now `pytest.warns`. Verified: the review's three repro cases construct and warn; sum mismatch still raises. | 63d0754b3 |
| M1 | Fixed: `TWTSLaser` no longer re-declares `huygens_surface_positions` (inherits the `BeforeValidator(deserialise_huygens)`-annotated field from `_BaseLaser`; field order and dumps unchanged); `FromOpenPMDPulseLaser` gains the deserializer. All five laser types added to `test_roundtrip.py`. Verified: both previously-failing round-trips pass; every laser's rendering context is byte-identical to the pre-rework tip. | 310722ef6, ad62a3040 |
| m1 | Fixed: corrected the four cited C++ names to `WAVE_LENGTH_SI`, `PULSE_DURATION_SI`, `focus_position[]`/`FOCUS_POSITION_*_SI`, `LASER_PHASE`. While verifying every laser docstring against incidentField.param.mustache, seven more mismatches were found and fixed in the same pass: `Polarization` (was POLARIZATION_ANGLE), `TDELAY` (was tdelay_user_SI), the ZMin/ZMax note for `laserIncidenceAnglePositive` (was "C++ name: phiPositive"), `FOCUS_Z_OFFSET_SI` (was focus_lateral_offset), `filename` (was file), `TIME_DELAY_SI` (was timeOffset), `dataType` (was datatype). | 2adff259a |
| m2 | Fixed: new quick test `test_union_templates.py` pins the mustache anchor for each member of AnyLaser/AnyPlugin/AnySolver/AnyLayout/AnyOperation and asserts the mapping covers exactly the union's members (a new member without an entry fails here, not at render time); one-line comments at the five union definitions. | 0123e99c0 |
| m3 | Fixed: added a `field_validator` on `FieldDump.filtername` enforcing `^[A-Za-z_][A-Za-z0-9_]*$` (None allowed), consistent with the species/functor/binner/axis name validators. PICMI derives the value from the already-validated functor name, so valid setups and rendering are untouched. | f27c36a57 |
| m4 | Fixed: removed `Species.check()` - its name regex duplicated `_validate_name` and its constants-uniqueness check is unreachable (Constants has one field per constant type, so duplicates are structurally impossible); it has no callers in the repo. | f602d8f06 |
| m5 | Fixed (extended per type, the review's first option): the laser-fits-in-run warning now models TWTSLaser via `windowEnd * delta_t_si` (an inactive window keeps the laser on for the whole run, so nothing is truncated), skips PlaneWaveLaser (continuous wave, never truncated), and is unchanged for Gaussian/dispersive. The heuristic's scope is documented in a comment. New tests cover the TWTS and plane-wave paths. | 4893dd667 |
| m6 | Fixed: corrected the PR proposal - grid provenance (the divisibility checks are new, not a port of the previous sum-only assert; and now a warning), "45 model files" -> 53, "131 tests" -> 138 functions/179 collected, "372 public fields" -> 325, "single remaining warning on a path no test triggers" -> two soft-invariant warnings both covered by `pytest.warns`, round-trip "20 representative models" -> 24 field-preserving models incl. all five laser types; added the union-exhaustiveness test; updated verification numbers to the post-rework gate. Changelog updated to note the soft invariants are warnings. | d5d35a847 |
| n1 | Fixed: the round-trip reconstruction now uses `type(model).model_validate(dumped)` (the canonical "this dict is valid model input" check, the same call task 07 makes) with a comment recording that computed-field keys are intentionally discarded via `extra='ignore'`. | 449bd457e |

## Gate requirement (not a review finding)

The committed, read-only `TASK-06-REVIEW.md` (and the inherited
`TASK-04-REVIEW.md`) are non-ASCII and tripped `require-ascii`; the inherited
config did NOT exclude `TASK-*.md` (verified against the reworked task-04
base). Added a documented exclusion for the `TASK-*.md` workflow-artifact
family. 3fe3dcd02.

## Rebase interaction (task-04 gamma_filter_threshold)

Verified coherent: task-04's all-filtered `gamma_filter_threshold`
rejection (a `model_validator` hard error) and mixed-list warning live in the
picmi `Radiation` model and do not overlap any task-06 invariant or the new
grid/laser warnings on the same input. The radiation tests (incl.
`test_mixed_species_list_warns`) and the render regression all pass.

## Final gate results (at tip)

- `pytest quick/ -q`: **515 passed, 2 xfailed, 1 xpassed** (3512 subtests).
  Rebased baseline at branch start: 476/2/1; +39 are the rework tests.
- `pre-commit run --all-files`: all 21 hooks pass.
- Render battery (hard constraint): a full laser + species + diagnostics
  setup (Gaussian laser, electron, Checkpoint, PhaseSpace, EnergyHistogram,
  MacroParticleCount, NativeFieldDump x2, DerivedFieldDump, Radiation,
  Binning) renders **16/16 `.param`/`.cfg` byte-identical** (functor-UUID
  normalised) to the pre-rework tip `b55c79ecf`; and all five laser types'
  rendering contexts are byte-identical.
- `compiling/` and `end_to_end/` marker tests not run (per instructions).
