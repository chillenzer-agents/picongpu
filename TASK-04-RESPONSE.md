# Re-work Response - Task 04 (radiation PICMI particle filters)

Base: review commit `26c1012a0`; all re-work is new commits on top (no history rewrites).
Every finding was independently re-verified (code + live renders) before disposition.

## Dispositions

| ID | Disposition | Commit(s) |
|----|-------------|-----------|
| M1 | Fixed: characterization test `test_n_cfg_radiation_block_is_known_wrong_until_task_15` pins all 9 lines of the known-wrong `--electron_rangeFilter_radiation.*` block (subTest per option), the absence of the correct `--electron_radiation.` prefix, and the absent `.filter` option; the old single-assert guard was folded into it | 3fa10d077 |
| M2 | Fixed: render/collect tests now wrap the species object actually added to the simulation (shared-object pattern, mirroring `end_to_end/test_diagnostics.py`); render tests additionally assert `momentumPrev1`/`radiationMask` in rendered `speciesDefinition.param`; new gamma render test covers the mask path end-to-end; plain-species path retained | 3fa10d077 |
| m1 | Fixed with deviation (see below): reject when all-filtered, warn when mixed | ec80e0285, 3fa10d077 |
| m2 | Fixed: `_validate_species` raises an actionable error (`species must be a Species or FilteredSpecies (or a list thereof), got ...`) instead of pydantic's `Input should be a valid list`; `ValidationError` contract preserved; new test asserts the message | ec80e0285, 3fa10d077 |
| n1 | Fixed: one-line note in `_collect_particle_filters` that the list-aware `UnpackChain` traversal also picks up filters of species lists such as `Radiation` | 749ca3f17 |
| n2 | Fixed: task-15 sketch corrected to `{{{species_name}}}` / `--{{{species_name}}}_radiation.filter {{{filter_name}}}` (inside `{{#species}}` the species entry is the context); note added that both pypicongpu species types expose the computed fields, and that task 15 must flip the characterization test | 729f6b9bc |

## m1 decision and rationale (deviation from the review sketch)

The review sketch rejects `gamma_filter_threshold` combined with *any* filtered
species (`any(isinstance(s, FilteredSpecies) ...)`). I reject only the
all-filtered case and warn on the mixed case. Evidence:

- The C++ gamma filter is the hardcoded `GammaFilterFunctor`, gated on the
  `radiationMask` attribute (`executeParticleFilter.hpp:39-52` compiles it out
  via `HasIdentifier`; `getRadiationMask.hpp:38-47` returns `true` when the
  attribute is absent), and this diagnostic registers `RadiationMask` for plain
  species only (task spec requirement 3).
- Mixed list `[plain, filtered]` + threshold: the threshold still applies to
  the plain species (mask registered, `radiationGamma` rendered) while the
  filtered species is selected by its own particle filter - a coherent
  configuration. The blanket rejection would kill it, so it is allowed with a
  `UserWarning` that the threshold is ignored for the filtered entries (loud,
  not a silent drop).
- All-filtered list + threshold: the threshold is a complete no-op (no species
  carries `radiationMask`), and after task 15 the run becomes possible, turning
  it into a silent wrong-physics foot-gun. Hence fail-fast `ValidationError`
  (raised in a `model_validator(mode="after")`, so no requirement side effects
  on failed construction). If task 15 makes gamma + particle filters composable
  in C++, it must relax this check (noted in the PR proposal's task-15 note).

## Rendered-output regression re-check

Re-rendered three configs (plain radiation + EnergyHistogram; plain radiation
with `gamma_filter_threshold=5.0`; filtered radiation) at the review commit and
at the re-work tip: all generated `.param`/`.cfg` files byte-identical, except
the `uuid4()`-based filter-struct suffix (`particle_functor.py:141`), which is
non-deterministic per render (a same-code double render produces different
suffixes) and predates this task.

## Final gate results (at tip)

- `pytest quick/ -q`: `193 passed, 2 xfailed, 1 xpassed` (baseline
  `190/2/1` + 3 new test methods; 3512 subtests).
- `pre-commit run --all-files`: all hooks pass except `require-ascii`, which
  flags **only** `TASK-04-REVIEW.md` - the review team's own artifact,
  non-ASCII at the review commit itself and read-only per the re-work rules.
  All files added/modified by the re-work are ASCII. (The PR proposal was
  itself non-ASCII at the author's original tip, so the original
  "pre-commit green" claim was not true; ASCII-ified in 1719c26e4. The review
  did not catch this because the full pre-commit run was not executed there.)
