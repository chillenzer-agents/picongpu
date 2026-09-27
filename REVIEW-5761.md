# Review of upstream PR #5761 "support native derived functors in picmi"

TT-22 (issue #51) - exhaustive review of pordyna's DRAFT `ComputationalRadiationPhysics/picongpu#5761`
(`topic-supportNativeDerivedFunctorsInPicmi`, +800/-30, includes `handover.md` and two draft test
files), performed against the stabilised pydantic-era base (fork `dev` @ `5087d5d6c`, merged #5639).

Scope of review: every hunk of the PR - the picmi diagnostic classes, the pypicongpu solver
plumbing and serializer, the deterministic functor typename, the `fileOutput.param.mustache`
rewrite (per-species `FieldTmpSolverConfig<Species, Attribute, Filter>` +
`ValidateFieldTmpSolver_t` + `pmacc::mp_transform`), and the interaction with the round-trip /
serde / pydantic-metadata work (issues #35, #33, #44, #45, #69).

## Verdict summary

| Area | Verdict |
|------|---------|
| Per-species solver dedup (`derived_field_functors` / `field_tmp_solvers`) | **Accept** (correct; minor notes) |
| `fileOutput.param.mustache` rewrite | **Accept** (C++ API verified against `include/`; compile CI-pending) |
| Deterministic `sha256` functor typename | **Accept** (load-bearing for dedup + reproducibility) |
| Serialisation / schema agreement (`sources` vs `derived_fields`) | **Accept** (deliberate, richer metadata format; round-trip note) |
| Interaction with round-trip / serde (#35/#33/#44+45/#69) | **Accept** - no material conflict; based on `dev` |
| `EnergyDensityCutoff` excluded | **Accept** (intentionally out of scope) |
| Two draft test files + tutorial change | **Accept** with minor port adaptations |

No change was rejected wholesale. A few weaknesses found during review were resolved by
clarifying tests/assertions and by clean-up during the port (see "Clean-up applied (not
rubber-stamping)").

## 1. Per-species solver deduplication - ACCEPT

- `pypicongpu/output/openpmd_plugin.py::DerivedFieldSolver` carries the complete compile-time
  solver identity: `species`, `attribute_type` (the C++ `derivedAttributes::<T>` or
  `combinedAttributes::<T>` type), `attribute_typename` and `filtername`.
- `pypicongpu/simulation.py` collects solvers via `_derived_field_dumps()` (all
  `FieldDump` sources with a non-`None` solver, across all `OpenPMDPlugin`s) and dedupes with
  the existing `util.unique` (list-membership equality over the full model, not only the
  typename).
- **Correctness verified:** dedup key == species + attribute + filter, exactly as documented in
  `handover.md`:
  - same field+species+filter at several periods / configs -> one solver,
  - same field, two species -> two solvers,
  - same field+species, two filters -> two solvers,
  - one custom functor reused across species -> one functor definition, several solvers
    (`derived_field_functors` dedupes by functor equality; `field_tmp_solvers` by solver
    equality).
- The `DerivedFieldSolver.typename` computed field (`attribute_typename_species_<filter-or-All>`)
  is only used for identification; the template consumes the individual fields.
- `Unique` is quadratic but the lists are tiny; not a concern.

## 2. `fileOutput.param.mustache` rewrite - ACCEPT (compile CI-pending)

The new template replaces the custom-functor-only generation (`CreateEligible_t<VectorAllSpecies,
...>` + per-functor `_Seq`) with:

```cpp
FieldTmpSolverConfig<Species, Attribute, Filter>
FieldTmpSolverConfigs = MakeSeq_t< ... >                // only requested combos
template<typename T_Config> struct ValidateFieldTmpSolver { static_assert(SpeciesEligibleForSolver<...>); using type = CreateFieldTmpOperation_t<...>; };
using FieldTmpSolvers = pmacc::mp_transform<ValidateFieldTmpSolver_t, FieldTmpSolverConfigs>;
```

Verified against the base `include/` tree (this repo cannot compile C++):

- `particleToGrid::CreateFieldTmpOperation_t<Species, Attribute, Filter>` - present,
  `ComputeGridValuePerFrame.def` (`CreateFieldTmpOperation` + `_t` alias), default filter
  `filter::All`. [OK]
- `particles::traits::SpeciesEligibleForSolver<Species, FilteredDerivedAttribute<A, F>>::type::value` -
  present; `FilteredDerivedAttribute.hpp` specialises the trait to `pmacc::mp_and<...>`
  (an `integral_constant` with `::value`); `FilteredDerivedAttribute.hpp` is transitively
  included via `ComputeGridValuePerFrame.def`. [OK] (There is also a filter-level
  `SpeciesEligibleForSolver` expectation in `particleFilters.param`, consistent with the
  per-species + per-filter eligibility check.)
- `pmacc::mp_transform<MetaFn, Seq>` argument order matches existing uses, e.g.
  `PluginRegistry.hpp:79`. [OK]
- `MakeSeq_t<>` (empty list) is already used in the pre-change template; an empty
  `FieldTmpSolverConfigs` yields an empty `FieldTmpSolvers`, so simulations *without* derived
  fields keep the same `FileOutputFields` shape. [OK]
- The per-species `static_assert` turns an unsupported species/field/filter request into a
  compile-time error instead of the previous empty-solver-list + missing-source runtime error. [OK]
- Compile-time saving ("only used species/solver/filter combinations compiled") is a genuine
  improvement for pordyna's large setups, and is what the tutorial's generated input exercises.

Weakness found: none blocking; but the C++ fragments are not compiled in this environment -
**compile verification is explicitly CI-pending** (marked in the PR body).

## 3. Deterministic `sha256` `ParticleFunctor.typename` - ACCEPT

- `typename = f"{name}_{sha256(json.dumps(model_dump(mode='json', exclude={'typename'}), sort_keys=True)[:32]}"`.
- Deterministic for a given (fixed-schema) definition -> identical functors produce identical
  C++ struct names -> required for solver dedup, compilation reuse and byte-identical
  regeneration (the setups repo regenerates the same inputs iteratively).
- `exclude={"typename"}` is correct: `typename` is a `computed_field` and therefore present in
  `model_dump` by default; excluding it avoids self-referential digest input.
- `sort_keys=True` sorts top-level JSON keys; nested key order originates from `model_dump`
  (fixed per class schema) and is therefore reproducible across processes/machines.
- Truncation to 32 hex chars is ample for collision avoidance and matches the PR.

## 4. Serialisation / schema agreement (`sources` vs `derived_fields`) - ACCEPT

The `OpenPMDPlugin` serializer now emits `"sources"` - *all* sources (species dumps, E/B/J
native fields, custom and built-in derived fields) as `{period, source}` pairs with each
source's rendering context - instead of the previous `"derived_fields"` (deduped custom-functor
dumps only).

- `source.get_rendering_context()` is uniformly available on `Species`, `FilteredSpecies` and
  `FieldDump` (via `RenderedObject` / `model_dump`), so no type special-casing is needed.
- The richer metadata (period + full source description) matches the handover's stated intent
  and is a prerequisite for the round-trip battery to reason about *which* solver a period
  targets.
- `FieldDump` gained `species`, `builtin_solver` plus a `_validate_solver_kind` invariant:
  custom functor and built-in solver are mutually exclusive; any solver requires a species.
  Only construction site is `picmi/simulation.py`, which provides both - no other caller breaks.
- Note for the round-trip work (issues #35/#33/#44+45/#69): the `period` is serialised via the
  existing `to_string(...)` ("start:stop:step", not directly re-parseable into `TimeStepSpec`).
  This matches the pre-existing behaviour for the config file and is not a regression; turning
  it into lossless round-trippable metadata is left to the serde stack, not this feature.

## 5. Interaction with round-trip / serde stack (#35/#33/#44+45/#69) - ACCEPT, based on `dev`

- The reviewer's #69 ("TT-15+16", unmerged, base `dev`) touches `openpmd_plugin.py`
  (`filtername` annotation) and `particle_functor.py` (`name` annotation,
  `random_number_command`) - **adjacent, non-overlapping lines** vs. this port (which touches
  `species`/`builtin_solver`/serializer and `typename` resp.). No material conflict => the port
  is based on `dev` and will merge cleanly after or before #69.
- The deterministic typename is load-bearing for the round-trip/equality work: it makes
  functor identity comparable across processes, which is exactly what issue #35's metadata
  re-import and #44/#45's serde conventions need.
- No changes to the `Simulation` serialisation schema beyond the new computed fields
  `derived_field_functors` / `field_tmp_solvers`, which are generated from `model_dump` and
  therefore consistent with the schema.

## 6. `EnergyDensityCutoff` - ACCEPT as out-of-scope

`EnergyDensityCutoff<T_ParamClass>` requires a user-provided C++ parameter class (verified:
`derivedAttributes/EnergyDensityCutoff.hpp` is a template over `T_ParamClass`). Excluding it is
correct; it belongs to the future `custom_user_input`/template mechanism (ties to #33).

## 7. Draft tests + tutorial example - ACCEPT with port adaptations

- `test_derived_field_dump.py` (picmi) - validates name mapping, directional fields, solver
  type strings, and negative cases. Verified against the C++ `IsWeighted` trait (the
  `AverageableDerivedField` set == every built-in that specialises `IsWeighted<...> :
  std::true_type`, excluding `MacroCounter` : `std::false_type` and the combined attributes).
- `test_openpmd_derived_fields.py` (pypicongpu) - asserts no functor struct / no `_Seq` /
  no `CreateEligible_t`/`VectorAllSpecies` in the rendered derived-field section, presence of
  `FieldTmpSolverConfig`/`mp_transform`/`static_assert`, and solver dedup including species and
  filter.
  - Weakness found: the `"VectorAllSpecies" not in rendered.split("using FieldTmpSolvers")[0]`
    assertion is brittle/under-scoped (the trailing `FileOutputParticles = VectorAllSpecies;`
    legitimately still references `VectorAllSpecies` and is deliberately excluded by the split).
    Ported with a cleaner, equally meaningful assertion.
- Tutorial `03.2_particle_functors.py`: adds native density, raw `WeightedVelocity/x` and
  `AverageDerivedFieldDump` of `WeightedVelocity/x` to the diagnostics list - adopted.

## Clean-up applied (deliberate deviations from the WIP)

- `picmi/simulation.py::_generate_openpmd_plugins`: the walrus-operator expression for
  `builtin_solver` is kept behaviour-identical but written readably (review-approved cleanup).
- Test assertion above clarified. Everything else is ported as-is.

## Verification performed in this repo

- Baseline quick suite before port: 200 passed, 2 xfailed, 1 xpassed (matches shared baseline).
- After port: see PR description - ported tests green, full quick green, pre-commit green,
  generated `fileOutput.param` / `openPMD_config_*.toml` for the tutorial inspected, and
  byte-identical regeneration verified (deterministic typename).
- C++ compilation of the generated input is **CI-pending** (no toolchain in this environment).

## Port base decision

This port is based on fork `dev` (`5087d5d6c`, merged #5639 pydantic era). Reviewer PR #69
("TT-15+16", unmerged, base `dev`) touches the same two modules (`openpmd_plugin.py`:
`filtername` annotation; `particle_functor.py`: `name` annotation /
`random_number_command`) but only on lines adjacent to, and not overlapping with, this port's
`species`/`builtin_solver`/serializer/`typename` changes; therefore it does not conflict
materially and the port does not need to rebase onto #69's branch. Chosen base: **fork `dev`**.
On merge, #69 and this port resolve without conflicts (verified by the disjoint line ranges).
