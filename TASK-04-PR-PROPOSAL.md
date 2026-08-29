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
  validation, attribute registration, `get_as_pypicongpu` conversion.
- `lib/python/picongpu/pypicongpu/output/radiation.py` —
  `RadiationPlugin.species` accepts `FilteredSpecies`.
- `lib/python/test/picongpu/quick/picmi/diagnostics/test_radiation.py` — new
  quick tests (16): acceptance of `Species`/`FilteredSpecies`/lists;
  `ValidationError` on wrong types; `MomentumPrev1`/`RadiationMask` registration
  rules; `_collect_particle_filters()` picks up the radiation filter;
  `get_as_pypicongpu()` maps `FilteredSpecies` via `mode="Filter"`; the
  generated setup renders the filter struct into `particleFilters.param`
  (asserted on rendered text); guard that no `.filter` line appears in the
  rendered `N.cfg`.
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
  → `190 passed, 2 xfailed, 1 xpassed` (baseline was `174 passed, 2 xfailed,
  1 xpassed`; the 16 additional passes are the new radiation tests).
- Rendered-output regression: for a simulation **without** radiation filters
  (radiation diagnostic on a plain species, no `gamma_filter_threshold`, plus an
  `EnergyHistogram`), all generated `.param`/`.cfg` files are
  **byte-identical** before and after the change (sha256 of all rendered
  `include/picongpu/param/*.param` and `etc/picongpu/*.cfg` compared).
- Pre-commit (`pre-commit run --all-files`) green.
- End-to-end verification of a *filtered* radiation run is impossible until
  task 15 exists (no filtered end-to-end run is possible yet); deferred there.

### Notes for follow-up tasks

- **Task 06** (pydantic metadata / validators/docstrings in
  `pypicongpu/output/radiation.py`) should be **based on / merged after this
  branch**: it will refine the same file (`RadiationPlugin`,
  `RadiationPluginConfig` docstrings/validators), while this branch only wires
  `species: list[Species | FilteredSpecies]` there, keeping the merge clean.
- **Task 15** (C++ `.filter` option + dispatch) must switch the
  `N.cfg.mustache` radiation block to `{{{species_name}}}` and add the
  `--{{{species.species_name}}}_radiation.filter {{{species.filter_name}}}`
  emission, mirroring the phaseSpace block (N.cfg.mustache:95-96).
