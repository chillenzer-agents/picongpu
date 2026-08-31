# PR Proposal — Task 04

## Title

`radiation PICMI: accept FilteredSpecies in the radiation diagnostic (Python side)`

## Body

### What

The PICMI `Radiation` diagnostic now accepts `Species | FilteredSpecies` (single or
list), mirroring the pattern already used by `EnergyHistogram`, `PhaseSpace`,
`ParticleDump`, `Binning`, and collisions:

- `picmi.Radiation.species` is now `list[Species | FilteredSpecies]`;
  `_validate_species` wraps a single `Species` or `FilteredSpecies` into a list.
- `Radiation.__init__` registers `MomentumPrev1()` for every species (for a
  `FilteredSpecies`, on the wrapped plain species) and `RadiationMask()` **only**
  for plain `Species` when `gamma_filter_threshold is not None` — never for
  filtered species, which select particles via their own particle filter.
- `Radiation.get_as_pypicongpu()` converts plain species via
  `get_as_pypicongpu()` and `FilteredSpecies` via `get_as_pypicongpu(mode="Filter")`.
- `pypicongpu.RadiationPlugin.species` is now `list[Species | FilteredSpecies]`
  (`pypicongpu/particle_functor/filtered_species.FilteredSpecies`).
- `gamma_filter_threshold` is made explicit: it only acts on plain species
  (the C++ gamma filter is gated on the `radiationMask` attribute, which is
  never registered for filtered species), so it is rejected with a
  `ValidationError` when all species are filtered (it would be a silent
  no-op), and construction warns when a mixed list ignores it for the
  filtered ones.
- `_validate_species` raises an actionable error for non-species inputs
  (e.g. a bare species name) instead of pydantic's "Input should be a valid list".

A `FilteredSpecies` used with `Radiation` is wired through the Python layer with
no template changes: its `ParticleFilter` is collected into
`Simulation.particle_filters` by the existing generic
`Simulation._collect_particle_filters()` (`UnpackChain` path) and rendered by the
**existing, unchanged, generic** `particleFilters.param.mustache`.

### Why

Radiation currently only supports a hardcoded gamma-based
`RadiationParticleFilter` (see C++ `Radiation.x.cpp` /
`include/picongpu/param/radiation.param`). Supporting the generic particle
functors/filters in PICMI for radiation is the Python half of that feature.

### Changes

- `lib/python/picongpu/picmi/diagnostics/radiation.py` — species type,
  validation (actionable error, `gamma_filter_threshold` no-op check),
  attribute registration, `get_as_pypicongpu` conversion.
- `lib/python/picongpu/pypicongpu/output/radiation.py` —
  `RadiationPlugin.species` accepts `FilteredSpecies`.
- `lib/python/picongpu/picmi/simulation.py` — one-line comment in
  `_collect_particle_filters()` noting that the list-aware `UnpackChain`
  traversal picks up filters of species lists (e.g. `Radiation`).
- `lib/python/test/picongpu/quick/picmi/diagnostics/test_radiation.py` — new
  quick tests (19): acceptance of `Species`/`FilteredSpecies`/lists;
  `ValidationError` on wrong types (with an actionable message for a bare
  species name); `MomentumPrev1`/`RadiationMask` registration rules;
  `gamma_filter_threshold` rejected when all species are filtered (it would
  be a silent no-op) and warned about for a mixed list;
  `_collect_particle_filters()` picks up the radiation filter;
  `get_as_pypicongpu()` maps `FilteredSpecies` via `mode="Filter"`; the
  generated setup (rendered with the filter wrapping the species actually
  added to the simulation) renders the filter struct into
  `particleFilters.param` and `momentumPrev1`/`radiationMask` into
  `speciesDefinition.param`; and a characterization test pinning the
  known-wrong `--<species>_<filter>_radiation.*` block in the rendered
  `N.cfg` (wrong prefix, no correct prefix, no `.filter` line) until task 15.
- `CHANGELOG.md` — short entry under `Unreleased`.

### Python-side readiness / scope

**This PR is Python-side only.** The C++ radiation plugin does not yet have a
`.filter` CLI option and no `AllParticleFilters` dispatch; that work is tracked
separately (follow-up task 15) and is intentionally **not** included here:

- No changes under `include/`, `src/`, or `etc/`.
- No `N.cfg.mustache` change: the one-line
  `--<species>_radiation.filter <filter>` emission is deferred to task 15
  (emitting it now would break runs because the C++ option does not exist).
  (Task 15 will also switch the radiation block's `{{{name}}}` to
  `{{{species_name}}}`, which is the wrong identifier for `FilteredSpecies`.)
- No user-facing documentation change (the feature is not end-to-end usable
  until task 15); the `radiation.rst` docs update belongs to task 15.

### Verification

- Quick test gate: `cd lib/python/test/picongpu && python -m pytest quick/ -q`
  → `193 passed, 2 xfailed, 1 xpassed` (baseline was `174 passed, 2 xfailed,
  1 xpassed`; the 19 additional passes are the new radiation tests).
- Rendered-output regression: for simulations **without** radiation filters
  (radiation diagnostic on a plain species, with and without
  `gamma_filter_threshold`, plus an `EnergyHistogram`), all generated
  `.param`/`.cfg` files are **byte-identical** before and after the change
  (rendered with the review commit and re-rendered after the rework, diffed).
- Pre-commit (`pre-commit run --all-files`) green.
- End-to-end verification of a *filtered* radiation run is impossible until
  task 15 exists (no filtered end-to-end run is possible yet); deferred there.

### Notes for follow-up tasks

- **Task 06** (pydantic metadata / validators/docstrings in
  `pypicongpu/output/radiation.py`) should be **based on / merged after this
  branch**: it will refine the same file (`RadiationPlugin`,
  `RadiationPluginConfig` docstrings/validators), while this branch only wires
  `species: list[Species | FilteredSpecies]` there, keeping the merge clean.
- **Task 15** (C++ `.filter` option + dispatch) must fix the
  `N.cfg.mustache` radiation block: that block iterates `{{#species}}`, so
  the species entry *is* the mustache context (the `species.` prefix only
  applies to the single-species `phaseSpace`/`energyHistogram` blocks).
  Inside the iteration, switch `{{{name}}}` to `{{{species_name}}}` and add
  the emission `--{{{species_name}}}_radiation.filter {{{filter_name}}}`,
  mirroring the phaseSpace block (N.cfg.mustache:95-96). Both pypicongpu
  `Species` and `FilteredSpecies` expose `species_name`/`filter_name`, so
  this works unconditionally. Task 15 must also flip the characterization
  test `test_n_cfg_radiation_block_is_known_wrong_until_task_15` (which
  pins the currently-wrong block), and, if it makes a gamma filter and a
  particle filter composable in C++, relax the Python-side rejection of
  `gamma_filter_threshold` with an all-filtered species list.
