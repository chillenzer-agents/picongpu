# PR Proposal - Task 06

## Title

`pypicongpu: refine pydantic metadata - docstrings, constrained types, invariant validators`

## Body

### What

Refines the `pypicongpu` pydantic representation (primary) and the mirroring
`picmi` models with own fields (secondary) so that physical quantities carry
machine-readable metadata and physical/technical invariants are upheld by
pydantic-native constraints and validators at construction time. No rendered
C++ interface (`.param`/`.cfg`) is changed for valid inputs.

Per the clarified scope ("docstrings, type annotations, and
`field_validator`/`model_validator`s that uphold physical and technical
invariants"), each pypicongpu module/subpackage got a pass in the order
docstrings -> constrained types -> validators -> tests:

1. `simulation.py` / `walltime.py` / `movingwindow.py` - `base_density > 0`
   (m^-3), `delta_t_si > 0` (s), `time_steps >= 0`, `typical_ppc >= 1`; laser
   exceeding the run is a **warning** (technical); new shared `SI("unit")`
   metadata tag in `pypicongpu/units.py`.
2. `grid.py` - `cell_cnt`/`super_cell_size`/`gpu_cnt` > 0, cell size > 0;
   cross-field: grid distribution chunks are multiples of the super cell size
   and `cell_cnt` is evenly divisible by `gpu_cnt * super_cell_size`
   (previous `assert`s converted to `ValueError`).
3. `species/**` (33 files) - mass/charge/density/synchrotron/element/
   ground-state-constant constraints; C++-identifier species name check moved
   from dead `check()` code into a `field_validator`; position + momentum
   attributes mandatory and attribute names unique (model validators);
   `max_Zq_exponent <= 10`, `min_Zq < max_Zq`, synchrotron `min_energy > 0`;
   layout/operation constraints (`OnePosition` offset in [0,1), `Quiet`
   `n_points > 0`, `Drift` gamma >= 1 with unit direction, `Temperature`
   >= 0 / exactly one of isotropic|directional).
4. `laser.py` - wavelength/duration/waist > 0, E0 > 0, `|beta0| <= 1`,
   active pulse window `windowEnd > windowStart`, FromOpenPMD `iteration >= 0`
   and non-empty file path.
5. `output/**` - `TimeStepSpec` bounds (`start >= 0`, `stop >= -1`,
   `step >= 1`); radiation frequency scales (`N_omega >= 1`,
   `omega_min < omega_max`, log `omega_min > 0`, `nyquist_factor` in (0,1),
   `gamma_filter_threshold > 0`, `num_jobs >= 1`); checkpoint
   (`timePeriod`/`restartStep`/`restartLoop >= 0`, `restartChunkSize > 0`,
   non-empty file prefixes, period-or-timePeriod); openPMD range
   (cell indices >= 0, `lo <= hi`); binning (`nsteps >= 1`, `start < stop`,
   log ranges must not include zero, `kind` restricted to `Literal["Linear",
   "Log"]` matching the C++ `axis::createLinear`/`createLog`, binner/axis
   names must be C++ identifiers); phase space (`min_momentum <
   max_momentum`); energy histogram (`bin_count > 0`, `min_energy >= 0`,
   `min < max`); macro particle count.
6. `collisions.py` / `particle_functor/**` - `coulomb_log > 0` (physical),
   `cell_list_chunk_size > 0`; `ParticleFunctor.name` must be a C++
   identifier (it renders into `using {name} = ...` and struct
   `{name}_{uuid}`); docstrings for all particle-functor models.
7. Secondary `picmi` pass - docstring fixes (e.g. phase-space momentum is in
   `[m_species c]`, not "kg*m/s") and field docstrings for the diagnostic
   mirror models; their invariants are enforced downstream via conversion to
   the now-validated pypicongpu models (no duplicate validation layers).

### Why

- The models previously accepted unphysical values (zero/negative mass or
  density, inverted min/max ranges, zero bin counts, negative time steps)
  that only failed later (at render/compile time or not at all), or not at
  all. Failing at construction with a `pydantic.ValidationError` names the
  exact field and invariant.
- The invariants are captured in pydantic's native, machine-understandable
  form (`Field`/`Annotated` metadata, `SI` unit tags) so introspection and
  schema generation carry them - a requester requirement.
- Round-trip safety: every validator is satisfiable from
  `model_dump(mode="json")` output, which task 07 (serialization) builds on.

### Changes

- `lib/python/picongpu/pypicongpu/**` - 45 model files refined
  (simulation, grid, laser, walltime, movingwindow, collisions, all
  `species/**`, all `output/**`, all `particle_functor/**`, runner,
  ionization groups), plus the new shared `units.py` `SI` tag.
- `lib/python/picongpu/picmi/diagnostics/**` - docstring corrections and
  field docstrings for the diagnostic mirror models.
- `lib/python/test/picongpu/quick/pypicongpu/test_validation.py` - new
  (131 tests): one or more `pytest.raises(ValidationError)` negative tests
  per new invariant, plus positive construction tests.
- `lib/python/test/picongpu/quick/pypicongpu/test_docstrings.py` - new
  (94 parametrized AST-based tests): every `BaseModel` subclass in
  `pypicongpu` has a class docstring and every public annotated field a
  docstring (the pydantic house idiom).
- `lib/python/test/picongpu/quick/pypicongpu/test_roundtrip.py` - new (20
  tests): representative models survive
  `Model(**m.model_dump(mode="json"))` with an identical re-dump.
- `CHANGELOG.md` - `Unreleased` entry ("stricter input validation").

### Key decisions and deliberate deviations

- **Mass is `ge=0`, not `gt=0`** (deviation from the audit hint): PICMI
  constructs `Mass(mass_si=0.0)` for photon species, so zero mass is a
  legitimate input; positive mass is still enforced everywhere a photon
  species is impossible.
- **No `start <= stop` invariant on `TimeStepSpec`** (deviation from the
  checklist): the PICMI slice semantics deliberately allow `start > stop`
  (selecting an empty set of time steps), the quick suite runs such specs
  through the conversion, and the test config uses `filterwarnings = error`
  - so it is enforced neither as an error nor as a warning (documented in
  the model).
- **Warnings are used sparingly**: the suite runs with `filterwarnings =
  error`, so a validator `warnings.warn` would fail any test that triggers
  it. The single remaining warning (laser pulse longer than the run) is on a
  path no test triggers; everything else is a hard error (physical) or a
  documented non-enforcement (technical where tests exercise the "invalid"
  shape).
- **Checkpoint file prefixes `min_length=1`**: an explicitly set empty
  prefix would be silently dropped by the mustache rendering (falsy
  section), hiding a typo - rejected at the model level instead.
- **Binning `kind` = `Literal["Linear", "Log"]`**: the value is interpolated
  into the C++ function `axis::create{kind}`; only `createLinear`/`createLog`
  exist for this template. (The internal render-regression battery used
  `kind="position"` - invalid C++ - and was corrected to `"linear"`.)
- **Round-trip deserializers** (additive `BeforeValidator`s accepting the
  serialised form in addition to the native form): 3-vector dicts
  (`Grid3D`, `OnePosition`, `Quiet`, `Drift`, `Temperature`),
  `boundary_condition` cfg strings, `grid_dist`, laser Huygens surface
  positions, and `Species` reconstruction of `constants` (list **or** the
  serialised dict) and attributes (concrete class restored from
  `picongpu_name`). `Grid3D` and the laser base class gained
  `ConfigDict(populate_by_name=True)` so field names (as produced by
  `model_dump`) are accepted next to the existing aliases.
- **Bug fix**: a duplicated `TBGFlags` definition in
  `pypicongpu/runner.py` (the second copy silently shadowed the first) was
  removed.

### Verification

- Quick test gate: `cd lib/python/test/picongpu && python -m pytest quick/ -q`
  -> **`473 passed, 2 xfailed, 1 xpassed`** (baseline at branch start:
  `190 passed, 2 xfailed, 1 xpassed`; the +283 are the new validation,
  docstring, and round-trip tests). The xfail/xpass sets are unchanged.
- Docstring completeness: 94 models / 372 public fields, **0 violations**
  (audit baseline: 231 violations), now enforced permanently by the 94
  AST-based quick tests.
- Rendered-output regression (hard constraint): a battery of 10
  representative setups (basic, binning, collisions, ionization, laser,
  moving window, openPMD, profiles, radiation, synchrotron) renders
  **byte-identical** `.param`/`.cfg`/rendering-context files before and after
  every pass (functor-uuid suffixes normalised before diffing).
- Round-trip: 20 representative models (incl. `Simulation`-building blocks
  `Grid3D`, `GaussianLaser`, `Species`, `TimeStepSpec`, diagnostics,
  collisions, layouts, momentum operations) satisfy
  `Model(**m.model_dump(mode="json"))` with an identical re-dump.
- Pre-commit: `pre-commit run --all-files` green (ruff, ruff-format,
  gersemi, pyproject-fmt, ...).

### Notes for follow-up tasks

- **Task 07** (serialization) can rely on `model_dump(mode="json")` output
  being valid model input for the field-preserving models (covered by
  `test_roundtrip.py`); models with custom top-level `model_serializer`s
  (`OpenPMDPlugin`, `UnitDimension`) are intentionally excluded from that
  guarantee - their serialisation is a string/config artifact, not a
  re-instantiable dict.
- The `@typeguard.typechecked` decorators on the pypicongpu `Checkpoint`
  model and the picmi `Checkpoint` are now largely redundant (pydantic
  validates) but were left in place to avoid changing error behaviour; a
  cleanup can follow.
- `walltime` vs. `time_steps` consistency was deliberately **not**
  implemented (not even as a warning): wall time is a hardware-dependent
  limit, so no invariant relating the two is computable on the Python side.
- `CustomUserInput` keys are validated at the existing
  `Simulation` serializer level (duplicate keys/identifiers already raise
  `ValueError` per `test_simulation.py`); a pydantic-level validator was
  deemed a duplicate layer and left as-is.
