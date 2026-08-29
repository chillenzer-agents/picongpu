# TASK-13 Findings: aligning pypicongpu with the PIConGPU C++ interface

Task: "Make the overall design of #pypicongpu align more with the #picongpu
#C++ interface" — investigate where the structures diverge, how the
pypicongpu elements are coupled into the picmi layer, and tackle them
one-by-one.

Branch: `task-13-pypicongpu-alignment` (base `b6374eafd`).

Ground rules used throughout:

- The C++ interface (`include/`, `src/`) is the **fixed reference** and was
  never modified.
- Reorganisation only, no new features. Where a fix looked better on the C++
  side, it is noted here instead.
- For every item the rendered `.param`/`.cfg` output was diffed before/after
  (byte-identical for valid inputs unless the item intentionally changes the
  rendered representation, which is called out below).
- Test gate after every commit:
  `lib/python/test/picongpu/quick/` — baseline `534 passed, 2 xfailed,
  1 xpassed`; final `566 passed, 2 xfailed, 1 xpassed` (all new tests are
  positive/negative invariant tests).
- `pre-commit run --all-files` green after every commit.

## Divergence inventory and per-item status

| # | Priority | Divergence | Status | Commit(s) |
|---|----------|------------|--------|-----------|
| 1 | P0 | `Pusher`/`Shape` enum names diverged from the C++ struct names (`Higuera-Cary` is not a valid C++ identifier; picmi bridge raised `KeyError`) | done | `264d89a88` |
| 2 | P0 | stale test `test_add_ionization_model` asserted the removed `bound_electrons` attribute (silently skipped) | done | `51d0c9d39` |
| 3 | P1 | `SimpleDensity` did not model the C++ `CreateDensity` init-pipeline functor | done | `e8c128073` (+style `abe3bcbcd`) |
| 4 | P1 | mass/charge stored as SI only; the C++ `MassRatio_<T>`/`ChargeRatio_<T>` concept was implicit | done | `12700bc87` |
| 5 | P1 | density-ratio semantics: `Gaussian.density` naming, `DensityRatio` semantics undocumented | done | `410ea2980` |
| 6 | P1 | charge state vs bound-electron count conflated in `SetChargeState` docs; C++ compile-time assert not mirrored | done | `bbd32443a` |
| 7 | P1 | collision model declared in both layers; the dynamic-log/screening invariant lived only in picmi | done | `1b3aa0fe3` |
| 8 | P1 | ionization bridging: `ionization_current` silently dropped, `ThomasFermi` conversion broken | done | `39e42fa90` |
| 9 | P1 | simulation-level defaults & compile/runtime split | **verified aligned — no code change needed** (see below) | — |

The two remaining optional items of the original plan were not started (time
box); candidates are listed under "Next PRs".

## Item details

### 1. Pusher/Shape enum names (P0) — done

`pypicongpu.species.species.Pusher`/`Shape` now mirror the C++ struct names
in `pusher.param`/`shapes/*.hpp`: `Shape.COUNTER` → `Shape.Counter`,
`Pusher.Higuera` → `Pusher.HigueraCary` with value `"HigueraCary"` (was
`"Higuera-Cary"`, which rendered an invalid C++ identifier). The picmi
pusher-method bridge gained an explicit error for the standard's `Li` method
(which PIConGPU does not support) instead of a bare `KeyError`.

Rendered impact: for `HigueraCary` the rendered C++ is now valid (previously
it would not compile). All other pushers byte-identical.

### 2. Stale ionization test (P0) — done

`test_add_ionization_model` asserted `op.bound_electrons` (removed in the
task-06 reorganisation) inside a filter that never matched (it compared
against uppercase species names), so the assertion was silently skipped. It
now checks `op.charge_state` (the C++ `ChargeState<T_chargeState>` template
parameter) per species. Test-only change.

### 3. SimpleDensity → CreateDensity (P1) — done

**Option comparison** (this was the worked example for the remaining items):

- (a) **1:1 rename to the C++ functor model** — `CreateDensity` with
  `profile` (C++ `T_DensityFunctor`), `start_position` (C++
  `T_PositionFunctor`, was `layout`), and the species split into
  `created_species` (first) / `derived_species` (rest, C++
  `ManipulateDerive<DensityWeighting>`). Chosen.
- (b) Keep `SimpleDensity` and add C++-named aliases — rejected: two names
  for the same concept, the template would still render the C++ concept
  through a Python name that does not exist in C++.
- (c) Defer until the init-pipeline is modelled more deeply — rejected:
  the C++ concept is small and stable.

Chosen: (a). `operation/simpledensity.py` deleted, `operation/createdensity.py`
added; `speciesInitialization.param.mustache`, `density.param.mustache`,
`particle.param.mustache` updated (`type_simpledensity` →
`type_createdensity`, `layout` → `start_position`,
`placed_species_*` → `created_species`/`derived_species`).

A pre-existing flake was fixed along the way: the species sort inside
`CreateDensity` used `set(species)` with a ratio key that ties arbitrarily
under hash randomisation; the sort key is now `(ratio-or-0, name)`.

Rendered impact: byte-identical; only the metadata JSON keys change.

### 4. Mass/charge ratio concept (P1) — done

C++ (`speciesDefinition.param`) only knows the dimensionless
`MassRatio_<typename>`/`ChargeRatio_<typename>` relative to the fixed base
constants `SI::BASE_MASS_SI`/`SI::BASE_CHARGE_SI` (`speciesConstants.param`,
electron mass / negative electron charge, 2022 CODATA). pypicongpu stored
only the SI values and rendered the compile-time expression
`<si> / sim.si.getBaseMass()`.

Design (option B, same family as item 3): keep the stored SI values (task-06
unit policy, `SI(...)` metadata, all call sites) and add the C++-side concept
on top — a new `SpeciesConstants` model (default instance mirrors the C++
fixed base values) and computed `mass_ratio`/`charge_ratio` fields on
`Mass`/`Charge`. `speciesDefinition.param` now renders the precomputed ratio
directly, exactly like the C++ default file.

Rendered impact: **intentional text change, numerically identical** — e.g.
electron `9.109…e-31 / sim.si.getBaseMass()` → `1.0`; proton mass ratio
→ `1836.15267…`, charge ratio → `-1.0`. Same IEEE double C++ computed.
All other rendered files byte-identical.

### 5. Density-ratio semantics (P1) — done

- `Gaussian.density` → `Gaussian.density_si` (matches `Uniform`/`Foil`/
  `Cylinder` and the SI unit policy). The PICMI attribute name `density` is
  kept as an alias, so the picmi bridge (name/alias matching in
  `copy_attributes`) and all call sites are unchanged. The C++ counterpart is
  `densityFactor` (the base-density-normalised constant), now documented.
- `DensityRatio` docstring rewritten to the actual C++ semantics:
  `DensityRatio_<typename>` is a runtime `value_identifier` passed as the
  `densityRatio<>` frame flag, read via `traits::GetDensityRatio` (default
  1.0 when absent); species derived inside a `CreateDensity` are scaled by
  the ratio of their density ratios (`manipulators::binary::DensityWeighting`).
- Deliberate decision (documented in the model docstrings): density profiles
  stay stored in absolute SI and render the normalising expression
  `<density_si> / SI::BASE_DENSITY_SI`. Unlike the mass/charge base
  constants, the base density is a **user-configurable simulation parameter**
  (`Simulation.base_density` → `simulation.param`), so the normalisation is
  left to the C++ compile time rather than coupling profile models to the
  simulation.

Rendered impact: byte-identical; only the metadata JSON key of the Gaussian
profile changes (`density` → `density_si`).

### 6. Charge state vs bound electrons (P1) — done

C++ (`manipulators::unary::ChargeState<T_chargeState>`) is parameterised by
the **charge state** (number of stripped electrons) and **derives** the
bound-electron count (`atomic number - charge state`) stored in the
`boundElectrons` species attribute. pypicongpu's `SetChargeState` docstring
conflated the two and named a non-existent C++ counterpart.

- `SetChargeState`/`BoundElectrons`/PICMI `Species.charge_state` docstrings
  now document the distinction and the real C++ counterpart.
- `SetChargeState` rejects unphysical charge states (charge state > atomic
  number) at construction time, mirroring the C++ compile-time assertion
  `Too_high_charge_state_for_atomic_number`, whenever the species carries the
  `ElementProperties` constant (otherwise the C++ check still applies).

Rendered impact: byte-identical (the new validation only rejects inputs that
would not compile in C++ anyway).

### 7. Collision model: single source of truth (P1) — done

The collision model was declared in both layers (picmi
`picmi/interaction/collision.py` and `pypicongpu/collisions.py`); `functor`
and `numerics_config` were already single-sourced from pypicongpu. The
documented C++ requirement "a dynamic-log collider needs at least one
screening species" was enforced only by the picmi layer.

- That invariant now lives in `pypicongpu.collisions.CollisionalPhysicsSetup`
  (next to the other collision invariants; applies to directly constructed
  pypicongpu setups as well). The picmi layer no longer carries a copy.
  For picmi users the specific error now surfaces at conversion time instead
  of construction time.
- The picmi `Collision`/`CollisionalPhysicsSetup` are documented as thin
  bridges holding the picmi species until conversion.

**Discovered pre-existing bug (not fixed here, see next PRs):** rendering a
simulation that contains collisions fails in the render-context schema check
(`RenderedObject.check_context_for_type` vs `model_dump(mode="json")`)
because the plain-mode `field_serializer`s of `Collision.species_pairs` and
`Collision.functor` change the serialised shape while the fallback
`model_json_schema(mode="serialization")` does not. Reproduced at the task
base commit (`b6374eafd`) — i.e. picmi collision setups could not be rendered
at all before or after this item. The same family affects any model whose
plain-mode field serializer changes the shape (e.g. `Simulation.customuserinput`
when non-empty, `Binning.openPMDBackendConfig`). Verified for item 7 that the
pypicongpu `CollisionalPhysicsSetup` `model_dump(mode="json")` is
byte-identical before/after.

### 8. Ionization name bridging (P1) — done

The pypicongpu `ionizer_picongpu_name` values were verified against the C++
ionizer type names (`BSI`, `BSIEffectiveZ`, `BSIStarkShifted`, `ADKLinPol`,
`ADKCircPol`, `Keldysh`, `ThomasFermi`) — all match, and the rendered
`particles::ionization::<name><T_DestSpecies[, current]>` matches the C++
template signatures (`T_DestSpecies` = electron species to be created).

Two bridge bugs fixed:

- ADK/BSI/Keldysh (`get_as_pypicongpu`) hard-coded the pypicongpu `None_`
  ionization current and **silently dropped** a user-provided
  `ionization_current`. The current is now bridged via
  `FieldIonization._get_ionization_current()`: `None` → `None_()` (C++
  default `current::None`); a concrete current must convert to a pypicongpu
  ionization current model or is rejected with a clear error.
- The picmi `ThomasFermi` conversion was broken: it constructed the
  pypicongpu model without the required `ionization_electron_species`
  (`ValidationError`). It now bridges the electron species (the C++
  `ThomasFermi<T_DestSpecies>` argument).
- The pypicongpu `ThomasFermi` model no longer accepts an ionization current:
  the C++ byCollision `ThomasFermi` takes **no** ionization-current template
  argument, unlike the byField ionizers (the inherited field is narrowed to
  `None`).

Rendered impact: byte-identical for all previously valid inputs (the fixed
paths previously either crashed or were unreachable).

### 9. Simulation-level defaults & compile/runtime split (P1) — verified aligned, no code change

Checked against the C++ defaults:

- `BASE_DENSITY_SI`: C++ default `1.e25`; picmi default
  (`Simulation._get_base_density`) `1.0e25`; pypicongpu `Simulation.base_density`
  is required (explicit) with `gt=0`. Aligned.
- `TYPICAL_PARTICLES_PER_CELL`: C++ default `2u` (constexpr); pypicongpu
  `typical_ppc` required (`ge=1`); picmi auto-computes the median layout ppc
  as a convenience default (documented). The `collision.param` default
  `cellListChunkSize = std::min(TYPICAL_PARTICLES_PER_CELL, 4u)` is rendered
  verbatim when the user leaves it unset. Aligned.
- Compile-time values (`DELTA_T_SI`, `CELL_*_SI`, `BASE_DENSITY_SI`,
  `TYPICAL_PARTICLES_PER_CELL`) are `constexpr` in the C++ default and are
  rendered `constexpr` by `simulation.param.mustache`. Aligned.
- Runtime values (`TBG_steps` ← `time_steps`, `TBG_wallTime` ← `walltime`,
  grid/GPU counts, output periods) go to `N.cfg`/`.cfg`, as in C++. Aligned.
- Runtime-overridable compile-time defaults (C++ `value_identifier`s) are the
  species mass/charge/density ratios — rendered as `value_identifier`s by
  pypicongpu (items 4/5). Aligned.
- Scope note (not a divergence): pypicongpu is 3D-only and does not model
  the C++ build-configuration files (`dimension.param`, `precision.param`),
  and does not cover C++-only feature defaults (e.g. `fieldAbsorber.param`,
  `png.param`, `shadowgraphy.param`). The C++ attribute defaults
  (`speciesAttributes.param`) are part of the static include tree, not
  per-simulation input, and are not templated by pypicongpu.

## Coupling map (pypicongpu → picmi → C++)

The picmi layer holds user-facing models and defers conversion via
`get_as_pypicongpu()`; pypicongpu holds the render models; templates render
the C++ interface. The main couplings:

- `picmi.Simulation` → `pypicongpu.simulation.Simulation` (single conversion
  in `get_as_pypicongpu`; defaults for base density / typical ppc / walltime
  / time steps / empty collision & synchrotron setups applied here).
- Species: `picmi.Species` registers *requirements* (constants, attributes,
  operations) from the outside (distributions, ionization models,
  `density_scale`, `charge_state`); `DelayedConstruction` resolves them at
  conversion time. Ionization models and layouts register on the species;
  `organise_init_operations` assembles the init pipeline
  (`pypicongpu.init_operations` → `speciesInitialization.param`).
- Interactions: `picmi.picongpu_interaction` (validated to a single
  `CollisionalPhysicsSetup` in `_validate_collisional_physics_setup`) →
  `collisional_physics` → `collision.param`.
- Distributions: picmi distribution classes ↔ pypicongpu profile models via
  name/alias matching (`copy_attributes`/`converts_to`); the pypicongpu
  profile field names are the C++-aligned ones (`density_si` etc.), the picmi
  names are the aliases.
- Ionization: picmi `ADK`/`BSI`/`Keldysh`/`ThomasFermi` → pypicongpu
  ionizer constants (fixed `ionizer_picongpu_name` = C++ type name) →
  `ionizers<...>` particle flag in `speciesDefinition.param`.
- Filters: picmi/pypicongpu `FilteredSpecies` ↔ `particleFilters.param` +
  `FilterPair`/`SpeciesFilter` in `collision.param`.

## Discovered pre-existing bugs (not fixed in this task — next PRs)

1. **Collision rendering is broken by the render-context schema check.**
   `RenderedObject.check_context_for_type` validates `model_dump(mode="json")`
   against `model_json_schema(mode="serialization")`, which does not account
   for plain-mode `field_serializer`s. `Collision.species_pairs` (and
   `functor`) serialise to a different shape than their declared type, so any
   simulation containing collisions fails to render (jsonschema
   `ValidationError`). Reproduced at base `b6374eafd`. Suggested fix: align
   the fallback schema generation with the actual serialised shapes (or
   provide the pre-generated schemas in `share/picongpu/pypicongpu/schema/`,
   the mechanism already exists in `renderedobject.py`).
2. **Same schema/serializer mismatch family** for `Simulation.customuserinput`
   (non-empty) and `Binning.openPMDBackendConfig` (set): not exercised by any
   quick test, so latent.
3. **Dead field**: `MODEL_NAME` on the picmi ionization models is declared
   but never read anywhere (the C++ name comes from the pypicongpu
   `ionizer_picongpu_name` defaults). Candidate for removal in a cleanup PR
   (public API, hence not touched here).
4. **`Pusher.Axel` renders C++ that will not compile** until the
   `particles::pusher::Axel` struct declaration is restored on the C++ side
   (noted in `species.py`; C++-side fix, out of scope here).

## Next PRs (suggested order)

1. Fix the render-context schema check for shape-changing serializers
   (pre-existing bug #1/#2 above); add a quick test that renders a
   collision setup end-to-end (this would have caught it).
2. Expose the remaining C++ `value_identifier`s (the species attribute
   defaults in `speciesAttributes.param`) as pypicongpu defaults where
   pypicongpu currently hard-codes them.
3. C++-side: restore the `particles::pusher::Axel` struct declaration in
   `pusher.param` (or drop `Pusher.Axel` on the Python side); see the note
   in `species.py`.
4. Cleanup: remove the dead `MODEL_NAME` fields on the picmi ionization
   models (public API change, hence a separate PR).

## Test gate

- Baseline (before item 1): `534 passed, 2 xfailed, 1 xpassed`.
- Final: `566 passed, 2 xfailed, 1 xpassed` (+32 tests, all positive/negative
  invariant and bridge tests). `pre-commit run --all-files` green at every
  commit. `compiling/`/`end_to_end/` marker tests were not run (out of scope).
