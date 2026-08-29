# PR Proposal - Task 07

## Title

`pypicongpu: round-trip safety - lossless (de)serialisation, Runner/Simulation reconstruction`

## Body

### What

Makes the `pypicongpu` pydantic models round-trip safe:
`type(inst).model_validate(inst.model_dump(mode="json"))` must hold, and
re-serialising the reconstructed instance must yield the identical dump. The
practical goal is that a valid `Runner`/`Simulation` can be reconstructed
from the metadata JSONs (`pypicongpu_rendering_context.json`,
`pypicongpu_runner.json`) written during `generate()`.

Task 06 made every *validator* satisfiable from the serialised form, but many
models were still not lossless: fields were excluded from the dump, computed
fields replaced real state, serializers had no inverse, or union types
mis-dispatched on re-validation. This pass fixes each asymmetry with
pydantic-native, symmetric mechanisms (annotated
`BeforeValidator`/`PlainSerializer` pairs, `field_serializer` +
`field_validator(mode="before")` pairs, discriminator tag fields, and
`populate_by_name` where dumps use field names):

1. **Field solvers** (`field_solver/Yee.py`, `Lehe.py`) - the `AnySolver`
   union had a smart-union tie (both members have zero required fields), so a
   serialised `Lehe` silently re-validated as `Yee`. Each solver now carries
   a `type_yee` / `type_lehe: Literal[True]` tag field (the codebase's
   discriminator idiom); rendered nowhere, so the C++ output is unchanged.
2. **Lasers** (`laser.py`) - `TWTSLaser` / `FromOpenPMDPulseLaser`
   `huygens_surface_positions` gained `BeforeValidator(deserialise_huygens)`
   (the serializer had no inverse).
3. **openPMD plugin** (`output/openpmd_plugin.py`) - `RangeSpec` gained a
   `model_validator(mode="before")` parsing its comma-separated string form;
   `OpenPMDConfig.range` accepts that string and delegates to `RangeSpec`.
   `OpenPMDPlugin`'s plain serializer now also carries the full plugin state
   (`sources` as a list of `{"period": ..., "source": ...}` dicts, and
   `config`), so the plugin re-validates; the extra keys are ignored by the
   templates. `config_filename(..., context="runtime")` is now always the
   relative `../input/etc/openPMD_config_<hash>.toml` - a pure function of
   the plugin state - so the serialised form no longer embeds a random
   temporary directory (the persistent-setup flow already rendered the
   relative form, so generated files are unchanged). `_generate_config_file`
   now `mkdir(parents=True, exist_ok=True)`s the config location.
4. **Binning** (`output/binning.py`) - `Binning`/`BinningAxis` gained
   `ConfigDict(populate_by_name=True)` (dumps use field names, constructors
   used aliases) and a before-validator parsing the JSON-string form of
   `openPMDBackendConfig` (inverse of its `field_serializer`).
5. **Radiation observer** (`output/radiation.py`) - `index_to_direction` was
   `Field(exclude=True)` (a callable, so it could never round-trip). It is now
   serialised losslessly as a dict of the three component sympy `srepr`
   strings keyed `x`/`y`/`z`, with a before-validator rebuilding the mapping
   (plain numbers are normalised back to python `int`/`float` so
   re-serialisation is stable). A dict - not a list - is used because the
   rendering context checker rejects lists that don't contain dicts; no
   template references the raw mapping (only the `component_expressions`
   computed field), so rendering is unchanged.
6. **Particle functors** (`particle_functor/*`) - `functor_expression` uses a
   new `pmaccprinter.serialise_expression` helper (str passthrough,
   sympy -> C++ string) as its before-validator, so already-serialised
   expressions validate again. The previously random per-dump `uuid4` in the
   `typename` computed field is now a real `typename_suffix` field, making
   the C++ typename stable across serialisation.
7. **UnitDimension** (`particle_functor/unit_dimension.py`) - a
   `model_validator(mode="before")` parses the C++
   `std::array<double, 7u>{...}` string form back into a list (inverse of the
   serializer).
8. **Elements** (`species/util/element.py`) - `Element` had a custom
   `__init__(openpmd_name)` that `model_validate` cannot use, and its dump
   carried only computed fields, so the isotope mass number was lost
   (`#14N` collapsed to `N`). `openpmd_name` is now a real field (source of
   truth, incl. isotope), the periodic-table lookup runs in a
   `model_validator(mode="after")`, and the three positional call sites in
   `picmi/species.py` use the keyword form (pydantic v2 init is
   keyword-only).
9. **Ionization models** (`species/constant/ionizationmodel/*`,
   `groundstateionization.py`) - `IonizationModel` gained
   `populate_by_name=True`; the new `AnyIonizationModel` union re-attaches
   the concrete class from the C++ ionizer name (`ionizer_picongpu_name` is
   unique per model) via a `BeforeValidator`, since the smart union would
   mis-dispatch (e.g. a serialised `ADKLinPol` validates against `BSI`).
   `GroundStateIonization.ionization_model_list` is now typed with
   `AnyIonizationModel`. `ionization_electron_species` (an `Any` field) is
   rehydrated from its dumped dict back into a `Species` (deferred import to
   avoid the circular import). `ionization_current` is typed with the
   concrete `None_` (the only current model) instead of the base class, so
   the concrete type survives re-validation.
10. **Collisions** (`collisions.py`) - before-validators reconstruct
    `species_pairs` (list of `{"species_lhs", "species_rhs"}` dicts) and
    `functor` (`{"type_constlog"/"type_dynamiclog", ...}`) from their
    serialised forms; `_serialize_functor` no longer calls a non-existent
    `get_rendering_context` on `ConstLogCollision`.
11. **SimpleDensity** (`species/operation/simpledensity.py`) - `species` is
    `exclude=True` and only its computed projections (`placed_species_initial`
    / `placed_species_copied`) are dumped; a `model_validator(mode="before")`
    rebuilds the species list from them. `validate_species` now raises a
    proper `ValueError` for non-list input instead of crashing with an
    `AttributeError`.
12. **Custom user input** (`customuserinput.py`, `simulation.py`) - the
    per-entry serializer is now lossless (`{"tags": ..., "rendering_context":
    ...}`); `Simulation.customuserinput` gains a before-validator accepting
    the flattened (merged) serialised form, and its field serializer reads
    the entry fields directly instead of a non-existent
    `get_rendering_context`.
13. **Density profiles** (`free_formula.py`, `gaussian.py`) -
    `populate_by_name=True` (dumps use field names, constructors used
    aliases); `FreeFormula.function_body` uses `serialise_expression` as its
    before-validator.
14. **Runner** (`runner.py`) - `TBGFlags.project_path` gains a before-validator
    accepting the CWL-style `{"class": "Directory", "location": ...}` form
    (inverse of its serializer). `Runner.sim`'s existing
    `BeforeValidator(alt(get_as_pypicongpu, identity))` already passes dicts
    through to `Simulation` validation, so no change was needed there.

### Why

- The metadata JSONs written during `generate()` must be re-loadable into a
  working `Runner`/`Simulation` - the explicit goal of task 07 - and task 13
  (pypicongpu <-> C++ alignment) builds on this branch and needs the fixes to
  be structural (annotated types, symmetric (de)serialisers), not test-side
  workarounds.
- Several of the asymmetries were silent correctness bugs, not just
  round-trip failures: a serialised `Lehe` solver re-parsed as `Yee`, a
  serialised `ADKLinPol` ionization model re-parsed as `BSI`, and a
  `#14N` isotope collapsed to `N` (wrong mass).

### Changes

- `lib/python/picongpu/pypicongpu/**` - 27 model files (solvers, lasers,
  openPMD plugin, binning, radiation, particle functors, unit dimension,
  elements, element properties, all 7 ionization models + groups +
  ground-state bundle, collisions, simple density, free formula, gaussian
  profile, custom user input, simulation, runner).
- `lib/python/picongpu/picmi/species.py` - three `Element` call sites to the
  keyword form.
- `lib/python/test/picongpu/quick/pypicongpu/test_roundtrip.py` - expanded
  from 20 to 79 parametrised model round-trips (via `model_validate`, the
  canonical reconstruction path) plus 2 end-to-end tests: the rendering
  context stored by `generate()` re-validates into an identical
  `Simulation`, and `pypicongpu_runner.json` re-validates into a `Runner`
  holding a `Simulation`.
- `CHANGELOG.md` - `Unreleased` entry ("round-trip fidelity").

### Key decisions and deliberate deviations

- **Per-member `type_<name>: Literal[True]` tags** (solvers, and the
  existing codebase pattern for lasers/operations/plugins) rather than a
  shared discriminator field: no schema change beyond adding the tag, and it
  matches every other union in `pypicongpu`.
- **`index_to_direction` serialises to a dict, not a list**: the rendering
  context checker rejects lists that don't contain dicts, and the
  rendering context *is* `model_dump(mode="json")`. A dict of `x`/`y`/`z`
  srepr strings passes the checker, round-trips, and is referenced by no
  template (only `component_expressions` is rendered), so the rendered
  `.param` files are byte-identical.
- **`config_filename` runtime form is always relative**
  (`../input/etc/openPMD_config_<hash>.toml`): a serialised value must be a
  pure function of the plugin state; the old code embedded a random
  temporary directory when no persistent setup dir was set. The real
  generation flow (persistent setup dir via `spread_directory_information`)
  already produced the relative form, so generated `N.cfg` files are
  unchanged.
- **`OpenPMDPlugin` dump gains `sources`/`config`**: ignored by the
  templates (they read `type_openPMD`, `config_filename`, `derived_fields`),
  required for reconstruction. `sources` is a list of *dicts* (not pairs) for
  the same renderer-checker reason as `index_to_direction`.
- **`Element` as a real pydantic field, dropping the custom `__init__`**:
  pydantic v2 `model_validate` cannot route through a custom positional
  `__init__`, and the old dump dropped the isotope mass number. The three
  call sites moved to keyword construction; invalid names still raise
  `NameError` from the lookup validator.
- **Ionization dispatch by C++ ionizer name**: the serialized form carries no
  class name, and the smart union is ambiguous (e.g. `BSI` accepts an
  `ADKLinPol` dump). The `ionizer_picongpu_name` default is unique per model,
  making it the natural discriminator.

### Verification

- Quick test gate: `cd lib/python/test/picongpu && python -m pytest quick/
  -q` -> **`534 passed, 2 xfailed, 1 xpassed, 3503 subtests passed`**
  (baseline at branch start: `473 passed, 2 xfailed, 1 xpassed`; the +61 are
  the new round-trip and reconstruction tests). The xfail/xpass sets are
  unchanged.
- Round-trip corpus: 79 representative models (all solvers, all 5 lasers,
  openPMD config/plugin/range, binning, all 7 ionization models, ground-state
  bundle, radiation observer/plugin, collisions, elements incl. `#14N`
  isotope, synchrotron, species operations, layouts, functors, custom user
  input) satisfy `model_validate(model_dump(mode="json"))` with an identical
  re-dump and the same concrete type.
- End-to-end reconstruction: a representative simulation's
  `write_input_file` output is read back - `Simulation.model_validate` on
  `pypicongpu_rendering_context.json` re-dumps identically, and
  `Runner.model_validate` on `pypicongpu_runner.json` yields a `Runner`
  whose `sim` is a `Simulation`.
- Rendered-output regression (hard constraint): a battery of 10
  representative setups (basic, binning, collisions, ionization, laser,
  moving window, openPMD, profiles, radiation, synchrotron) rendered against
  the task-06 base commit and this branch produces **byte-identical**
  `.param`/`.cfg` files; the metadata JSONs differ only by the added
  reconstruction fields (`type_yee`, `index_to_direction`,
  `typename_suffix`, `openpmd_name`, openPMD `sources`/`config`). A second,
  independent single-setup diff (explorer simulation) confirms the same.
- Pre-commit: `pre-commit run` on all changed files green (ruff, ruff-format,
  gersemi, pyproject-fmt, ...).

### Notes for follow-up tasks

- **Task 13** (pypicongpu <-> C++ alignment) can rely on the full round-trip
  guarantee: every model's `model_dump(mode="json")` is valid input to
  `model_validate` and re-serialises identically, including the previously
  excluded/lossy models (`OpenPMDPlugin`, `Element`, ionization models, the
  radiation observer direction mapping).
- The picmi-side `IonizationCurrent` interface (a different class from the
  pypicongpu one) was left untouched: it has no subclasses and its dump
  round-trips trivially.
- `SimpleDensity` re-validates its species through the *sorted/deduplicated*
  `validate_species` path, so the reconstructed species list is in canonical
  (density-ratio) order - identical to the first dump, since the first
  construction went through the same normalisation.
