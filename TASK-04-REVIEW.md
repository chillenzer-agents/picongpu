# Review — Task 04: Add particle filters to the radiation plugin in PICMI

- **Branch:** `task-04-radiation-picmi-filters` (tip `1bdb070aa`, base `dev` `b4e4ca5b2`)
- **Reviewed:** 2026-08-31 · **Scope:** 4 commits, 5 files, +316/−7
- **Verdict:** REQUEST CHANGES
  (Core wiring is correct, minimal, and in-scope, and every quantitative author claim re-verified — but the only test guarding the documented known-broken N.cfg output guards the wrong thing, and the render test exercises a configuration in which the C++ plugin can never be enabled.)

## 1. Summary

The branch makes `picmi.Radiation.species` and `pypicongpu.RadiationPlugin.species` accept `Species | FilteredSpecies`, registers `MomentumPrev1()` on the (wrapped) plain species and `RadiationMask()` only for plain species with `gamma_filter_threshold`, and converts `FilteredSpecies` via `get_as_pypicongpu(mode="Filter")`. The filter then flows through the existing generic `_collect_particle_filters()`/`particleFilters.param.mustache` path with no template change, exactly as the task prescribes. Scope is respected (only 2 Python source files + 1 new test file + CHANGELOG + artifact; nothing under `include/`, `src/`, `etc/`), the test gate re-runs at exactly the claimed 190/2/1 (baseline re-run: 174/2/1), and I independently verified byte-identical `.param`/`.cfg` output for five previously-valid configs (80 files). The problems are all about the *guarding* of the known deferred breakage: (1) for a filtered radiation species the entire N.cfg radiation block is emitted under a CLI prefix no C++ plugin registers (`--electron_rangeFilter_radiation.*`), yet the single guard test only asserts the absence of a `.filter` line and pins nothing about this; (2) the render tests wrap a species object that is never added to the simulation, so the rendered `speciesDefinition.param` lacks `momentumPrev1` and the C++ radiation plugin is not even eligible for that species — the realistic (same-object) pattern is never render-tested; (3) `gamma_filter_threshold` combined with a filtered species is silently ignored while still being rendered into `radiation.param`.

## 2. Findings

### 2.1 Critical

None found.

### 2.2 Major

**M1** — **`lib/python/test/picongpu/quick/picmi/diagnostics/test_radiation.py:193-199`** — The documented known issue ("filtered radiation species renders a wrong N.cfg prefix") is not actually guarded by any test; the sole guard asserts only `"_radiation.filter" not in n_cfg`, which is true for an entirely different reason than the one that matters.
- *Evidence:* I rendered the branch's own test configuration (Radiation on `FilteredSpecies(electron, rangeFilter)`). `etc/picongpu/N.cfg` contains **9 lines** (lines 75–83 of the rendered file; up to 13 with the optional `lastRadiation`/`totalRadiation`/`radPerGPU`/`distributedAmplitude` flags), all under a prefix that does not exist in C++:
  ```
  --electron_rangeFilter_radiation.period 1:4:2
  --electron_rangeFilter_radiation.dump 0
  --electron_rangeFilter_radiation.start 2
  ...
  --electron_rangeFilter_radiation.openPMDCheckpointConfig {}
  ```
  The C++ plugin registers `pluginPrefix = speciesName + "_radiation"` (`include/picongpu/plugins/radiation/Radiation.x.cpp:158`) and has **no** `.filter` option (verified against `pluginRegisterHelp`, `Radiation.x.cpp:194-249`). Consequently the rendered setup (a) would fail at CLI parse time with "unrecognised option" and (b) contains **zero** `--electron_radiation.*` lines, so even a parse-tolerant run would never enable the plugin. The template cause is `{{{name}}}` in the radiation block (`lib/python/picongpu/templates/etc/picongpu/N.cfg.mustache:115-144`), where a pypicongpu `FilteredSpecies` has `name == "<species>_<filter>"` (`pypicongpu/particle_functor/filtered_species.py:39-41`). The task defers the template fix to task 15, so emitting this today is *expected* — but the test suite gives no protection at all: nothing pins the currently-wrong prefix, and nothing will verify that task 15 produces the right one (`--electron_radiation.period … --electron_radiation.filter rangeFilter`). The test name/docstring ("must not reference one [the .filter option]") suggests the N.cfg situation is guarded when it is not.
- *Suggested fix:* Turn the guard into an explicit characterization test of the known-wrong state, so any drift (accidental template edit now, incomplete fix in task 15) fails loudly, e.g.:
  ```python
  def test_n_cfg_radiation_prefix_is_known_wrong_until_task_15(self):
      # KNOWN ISSUE (task 15): the radiation block uses {{{name}}}, which for a
      # FilteredSpecies is "<species>_<filter>" -> the whole block lands under a
      # CLI prefix no C++ plugin registers. Task 15 must flip this to
      # --electron_radiation.* plus --electron_radiation.filter rangeFilter.
      _, n_cfg = self._render([Radiation(species=make_filtered_species(), ...)])
      assert "--electron_rangeFilter_radiation.period" in n_cfg   # pin the wrong prefix
      assert "--electron_radiation." not in n_cfg                 # correct prefix absent
      assert "_radiation.filter" not in n_cfg
  ```
  Alternatively (or additionally) add an `@pytest.mark.xfail(reason="fixed in task 15")` test asserting the *desired* final lines.

**M2** — **`lib/python/test/picongpu/quick/picmi/diagnostics/test_radiation.py:151-190` (render tests via `make_sim`, line 50-67)** — The render tests wrap a **fresh** `Species` object that is never added to the simulation, so the rendered setup they assert on is one in which the C++ radiation plugin can never be enabled; the only realistic wiring (wrapping the added species itself) is not render-tested.
- *Evidence:* `make_sim()` adds `electrons` to the simulation, while `make_filtered_species()` creates a *different* `picmi.Species(name="electron")` that is only referenced by the diagnostic. I rendered exactly this pattern (branch code): in `include/picongpu/param/speciesDefinition.param` the rendered `ParticleAttributes_species_electron` is `position, weighting, momentum` — **no `momentumPrev1`** — because `Radiation.__init__` registered `MomentumPrev1()` on the phantom wrapped object (`picmi/diagnostics/radiation.py:41,42`), which is not part of `sim.species` and is never rendered. C++ requires `momentumPrev1` for radiation eligibility: `RequiredIdentifiers = MakeSeq_t<position<>, weighting, momentum, momentumPrev1>` in `SpeciesEligibleForSolver<Radiation>` (`include/picongpu/plugins/radiation/Radiation.x.cpp:1239`) — without it the plugin is silently not registered for that species. So `test_generated_setup_renders_radiation_filter_into_particle_filters_param` passes on a setup where the feature *cannot work*, and a regression in the requirement wiring for filtered species (e.g. registering on the `FilteredSpecies` instead of its wrapped species, or dropping the registration) would not be caught by any render-level test. I separately rendered the realistic pattern (filter wraps the very species object added to the sim) and confirmed it is wired correctly (`momentumPrev1` present, no `radiationMask`), so the feature itself is sound — the test simply never exercises it.
- *Suggested fix:* In `make_sim`/the render tests, build the `FilteredSpecies` around the species object that is actually added to the simulation (mirroring the end-to-end pattern in `lib/python/test/picongpu/end_to_end/test_diagnostics.py:162-180`), and extend the render assertions to the species definition:
  ```python
  e = make_species(); sim.add_species(e, layout)
  fs = FilteredSpecies(species=e, functor=...)
  sim.add_diagnostic(Radiation(species=fs, ...))
  ...
  species_def = (setup_dir / "include/picongpu/param/speciesDefinition.param").read_text()
  assert "momentumPrev1" in species_def
  assert "radiationMask" not in species_def
  ```
  Keep one phantom-free test, but make the *rendering* tests use the shared-object pattern.

### 2.3 Minor

**m1** — **`lib/python/picongpu/picmi/diagnostics/radiation.py:43-46`** — `gamma_filter_threshold` set together with a filtered species is silently ignored, yet still rendered into `radiation.param` (dead constant that misleads later readers and task 15).
- *Evidence:* I rendered `Radiation(species=FilteredSpecies(...), gamma_filter_threshold=5.0)`: `speciesDefinition.param` has **no** `radiationMask` attribute (correct by design), so C++ compiles the gamma filter out (`executeParticleFilter.hpp:39-52` is gated on `HasIdentifier<…, radiationMask>`; `getRadiationMask.hpp:38-47` returns `true` when absent) — the threshold has no effect. But `radiation.param` still renders `static constexpr float_X radiationGamma = 5.0;` plus the full `GammaFilterFunctor`/`RadiationParticleFilter` definition (`templates/include/picongpu/param/radiation.param.mustache:186-208` key off `config.gamma_filter_threshold`). The user asked for "only γ ≥ 5" and silently gets "all particles passing my range filter". Today this is masked because the run cannot happen anyway (M1), but after task 15 it becomes a silent physics-output foot-gun.
- *Suggested fix:* In `Radiation.__init__` (or a `field_validator`/`model_post_init`), detect the combination and be explicit:
  ```python
  if self.gamma_filter_threshold is not None and any(isinstance(s, FilteredSpecies) for s in self.species):
      raise ValueError(
          "gamma_filter_threshold only applies to plain species; "
          "remove it or express the gamma cut inside your ParticleFilter"
      )
  ```
  (a `warnings.warn` is an acceptable weaker alternative; document the choice in the PR body and task 15).

**m2** — **`lib/python/picongpu/picmi/diagnostics/radiation.py:33-36`** — The `mode="before"` validator passes unknown values through, so a string species name yields the unhelpful `Input should be a valid list [type=list_type, input_value='electron']`. Since this task broadens the accepted surface (users of the new `FilteredSpecies` support are prime candidates for passing a name), the validator should produce an actionable message.
- *Evidence:* `Radiation(species="electron", period=…, observer=…)` → `1 validation error for Radiation / species / Input should be a valid list [type=list_type, input_value='electron', input_type=str]` (reproduced). The message suggests the fix is "wrap it in a list", when the real issue is that a `Species`/`FilteredSpecies` object is required.
- *Suggested fix:* In `_validate_species`, raise/annotate for obviously-wrong types:
  ```python
  @field_validator("species", mode="before")
  @classmethod
  def _validate_species(cls, value):
      if isinstance(value, (Species, FilteredSpecies)):
          return [value]
      if isinstance(value, list):
          return value
      raise ValueError("species must be a Species or FilteredSpecies, or a list thereof")
  ```
  (this keeps the existing `ValidationError` contract the new tests rely on).

### 2.4 Nits

**n1** — **`lib/python/picongpu/picmi/simulation.py:418-424`** — The optional "update the stale comment in `_collect_particle_filters`" from the task was not done. The comment currently explains only the Binning special case; with `Radiation` now contributing a *list* of (possibly filtered) species, a one-liner ("list-aware `UnpackChain` traversal also picks up `Radiation.species` filters; see task-04") would prevent a future "cleanup" from breaking this wiring.
- *Suggested fix:* Append one sentence to the existing comment.

**n2** — **`TASK-04-PR-PROPOSAL.md` ("Notes for follow-up tasks")** — The task-15 emission sketch `--{{{species.species_name}}}_radiation.filter {{{species.filter_name}}}` is not valid mustache for the radiation block: that block iterates `{{#species}}` (N.cfg.mustache:116), so inside it the context *is* the species entry and the correct expressions are `{{{species_name}}}` / `{{{filter_name}}}` (the `species.` prefix applies only to the single-species `phaseSpace`/`energyHistogram` blocks, which don't iterate). Plain pypicongpu `Species` exposes both computed fields (`species.py:127-132`), so task 15 can use them unconditionally; the sketch as written would render `--_radiation.filter` (empty keys) and mislead the task-15 implementer.
- *Suggested fix:* Correct the sketch to `--{{{species_name}}}_radiation.filter {{{filter_name}}}` inside the `{{#species}}` iteration.

## 3. Requirement traceability

| # | Requirement (from task file) | Status | Where / note |
|---|------------------------------|--------|--------------|
| 1 | `picmi.Radiation.species: list[Species \| FilteredSpecies]`; single value wrapped | met | `picmi/diagnostics/radiation.py:30,36`; 3 acceptance tests |
| 2 | `pypicongpu.RadiationPlugin.species` accepts both | met | `pypicongpu/output/radiation.py:236` |
| 3 | `__init__`: `MomentumPrev1()` for all species (filtered → on wrapped species); `RadiationMask()` only for plain species when `gamma_filter_threshold is not None` | met | `radiation.py:39-46`; 5 requirement tests; verified by repro (no mask for filtered+γ, `MomentumPrev1` present) |
| 4 | `get_as_pypicongpu` maps `FilteredSpecies` via `mode="Filter"` | met | `radiation.py:51-56`; verified: pypicongpu entry is `FilteredSpecies` with `functor` a `ParticleFunctor` |
| 5 | Filter collected into `Simulation.particle_filters` and rendered into `particleFilters.param` | met | No change needed (as predicted); verified in rendered output: struct + `using rangeFilter = generic::FreeTotalCellOffset<…>` + entry in `AllParticleFilters` |
| 6 | No C++ interface change; PR touches nothing under `include/`, `src/`, `etc/` | met | `git diff --name-only dev...HEAD` → 5 files, all under `lib/python/`, `CHANGELOG.md`, artifact |
| 7 | Do not emit `--<species>_radiation.filter` in N.cfg | met | Verified absent in rendered N.cfg; but see M1 — the surrounding known-wrong prefix is not pinned |
| 8 | Rendered `.param`/`.cfg` byte-identical for previously-valid inputs | met | Independently verified: 5 configs (plain/gamma/two-species radiation, no radiation, mixed diagnostics), 80 param/cfg files, sha256-identical baseline (dev code) vs branch |
| 9 | Quick test: accepts `Species \| FilteredSpecies \| list[...]` | met | `TestRadiationSpecies` (4 tests) |
| 10 | Quick test: wrong types rejected (`ValidationError`) | met | `test_rejects_wrong_type` (message quality: m2) |
| 11 | Quick test: `MomentumPrev1`/`RadiationMask` registration rules | met | `TestRadiationRequirements` (5 tests) |
| 12 | Quick test: `_collect_particle_filters()` picks up the radiation filter | met | `test_collect_particle_filters_*` (2 tests) |
| 13 | Quick test: generated setup renders filter struct into `particleFilters.param` (assert rendered text) | partial | Present, but uses a phantom (never-added) species, so the rendered setup lacks `momentumPrev1` and the plugin could never be enabled there — M2 |
| 14 | Quick test: no `.filter` line in rendered N.cfg (guard against premature emission) | partial | Present, but guards only the `.filter` line, not the documented wrong-prefix breakage — M1 |
| 15 | No user-facing doc change; state readiness in PR description | met | `TASK-04-PR-PROPOSAL.md` "Python-side readiness / scope" section is accurate |
| 16 | (optional) Update stale comment in `_collect_particle_filters` | missed (optional) | `simulation.py:418-424` unchanged — n1 |
| 17 | (optional) Unfiltered radiation e2e smoke test | missed (optional) | Not added; acceptable (no C++ build in quick CI) |
| 18 | (implicit) Configuration must remain coherent for C++ to consume | partial | Unfiltered: coherent (verified). Filtered: N.cfg prefix incoherent (deferred by design, M1) and γ-threshold silently dropped (m1) |

## 4. Claim verification (author artifact)

| Claim (from TASK-04-PR-PROPOSAL.md) | Re-verified? | Result / delta |
|-------------------------------------|--------------|----------------|
| Quick gate: `190 passed, 2 xfailed, 1 xpassed` (baseline `174, 2, 1`; 16 new) | yes | **Exact match.** Re-ran `pytest quick/ -q` in the task venv: `190 passed, 2 xfailed, 1 xpassed, 3503 subtests passed in 5.74s`. Independently re-ran the *baseline* (dev code via a scratch package, branch test tree minus the new file): `174 passed, 2 xfailed, 1 xpassed`. New file contains exactly 16 test methods. |
| Rendered-output regression: all generated `.param`/`.cfg` byte-identical (sha256 of `include/picongpu/param/*.param` + `etc/picongpu/*.cfg`) for unfiltered configs (plain-species radiation w/o γ + `EnergyHistogram`) | yes | **Holds.** I rendered 5 previously-valid configs (their named one plus gamma-filtered radiation, two-species radiation list, no-radiation-with-injected-default, radiation+PhaseSpace+EnergyHistogram) with dev code and branch code: all 80 `.param`/`.cfg` files sha256-identical. Only diffs anywhere in the trees are environmental (absolute paths in `metadata/`, `workflow/`, timestamps). |
| No changes under `include/`, `src/`, `etc/`; no `N.cfg.mustache` change | yes | **Holds.** `git diff --name-only dev...HEAD`: `CHANGELOG.md`, `TASK-04-PR-PROPOSAL.md`, 2 Python source files, 1 test file. |
| `pre-commit run --all-files` green | partially | ruff (pinned `v0.12.10`) `check --ignore E721` and `format --line-length 120 --check` pass on all three changed Python files; all changed files are ASCII (`require-ascii`). Full pre-commit run not executed (hook environments need network) — the Python-relevant gate is verified. |
| "Task 15 will also switch the radiation block's `{{{name}}}` to `{{{species_name}}}`" | yes (content) | Accurate statement of the template state (`N.cfg.mustache:115-144`), but the emission sketch in the same note is not valid mustache for that block — n2. |
| C++ context statements (no `.filter` option; hardcoded `RadiationParticleFilter`; prefix `<species>_radiation`) | yes | **Accurate** against `Radiation.x.cpp:158,194-249,1163-1223`, `executeParticleFilter.hpp:39-52`, `include/picongpu/param/radiation.param:165-187`. |

## 5. Design discussion

**The chosen mechanism is the right one.** Mirroring the established `Species | FilteredSpecies` pattern of `EnergyHistogram`/`PhaseSpace`/`ParticleDump`, reusing the generic `UnpackChain`-based `_collect_particle_filters()` and the generic `particleFilters.param.mustache`, and touching exactly two source files (+23 lines of logic) is the minimal correct design for this codebase. I verified the wiring end-to-end at the render level: the filter struct lands in `particleFilters.param` with the correct `generic::FreeTotalCellOffset` wrapper (the functor uses total position), the pypicongpu translation is a real `ParticleFunctor`, and unfiltered behavior is bit-for-bit unchanged. The C++-coherence cross-check also came out clean: the Python side invents no `.cfg` keys the C++ side doesn't understand (no `.filter` line, no new option), and the C++ filter-execution path tolerates a missing `radiationMask` attribute (`executeParticleFilter.hpp`, `getRadiationMask.hpp`), so "mask only with γ-threshold" is a coherent contract.

**The real design tension is the half-feature window.** The task deliberately accepts `FilteredSpecies` now while the N.cfg block stays broken for that input until task 15. That is a sound sequencing decision *for a same-series follow-up*, but it means the feature's headline input currently produces a silently-unrunnable `N.cfg` (M1), and the test suite's "guard" for this state is narrower than the documented problem. A maintainer should weigh: (a) characterization-test the known-wrong prefix now (M1's sketch) — cheap, makes the breakage visible and makes task 15's fix verifiable; (b) reject `FilteredSpecies` at the picmi level until task 15 — contradicts the task's explicit "models accept `FilteredSpecies`" requirement and would have to be reverted, so not recommended; (c) status quo plus documentation — the current state, which is the weakest of the three because the only protection is a test that doesn't protect. I'd take (a): it costs ~10 lines and converts a latent trap into a pinned, trackable state.

**Test representativeness (M2) is a general lesson for this codebase:** because picmi never cross-validates that a diagnostic's species is one of the simulation's species (the same phantom-object trick is possible with `PhaseSpace`/`EnergyHistogram` today), a diagnostic test that constructs a *fresh* species object proves model-level behavior but not rendered-setup behavior. The new tests' model-level assertions are fine; their *render* assertions should use the shared-object pattern and assert on `speciesDefinition.param`, which is where C++ actually decides plugin eligibility (`Radiation.x.cpp:1239`).

**Silent configuration drops (m1):** when a user-supplied parameter (`gamma_filter_threshold`) becomes a no-op depending on *other* parameters' types, the least a config layer should do is say so loudly. Fail-fast is preferable to a warning here because the alternative outcome is wrong physics output after task 15 lands, not a failed run.

**Inherited, not changed here (for completeness):** the `__init__`-side-effect pattern (requirements registered during construction, bypassed by `model_validate`) is shared by all diagnostics and is currently unreachable in practice for `Radiation` because `model_validate` fails on the non-serializable observer lambda; `model_dump_json` of picmi diagnostics fails for the same reason (verified on `EnergyHistogram` too). Neither is a finding for this task.

## 6. Prioritized next steps

1. **Fix the render tests to use the realistic pattern (M2):** wrap the species object actually added to the simulation in `FilteredSpecies`; assert the rendered `speciesDefinition.param` contains `momentumPrev1` (and, for the γ-less case, no `radiationMask`).
2. **Replace/extend the N.cfg guard (M1):** pin the known-wrong `--electron_rangeFilter_radiation` prefix with an explicit "known issue, fixed in task 15" comment (characterization test), or add an `xfail` test asserting the desired `--electron_radiation.*` + `.filter` lines.
3. **Make `gamma_filter_threshold` + filtered species explicit (m1):** raise (or at minimum warn) in `Radiation.__init__`.
4. **Polish (optional, cheap):** actionable `ValidationError` message for wrong `species` types (m2); append the one-line comment to `_collect_particle_filters` (n1); correct the task-15 mustache sketch in the PR proposal (n2).
5. **Carry into task 15:** the correct radiation-block expressions (`{{{species_name}}}` + `--{{{species_name}}}_radiation.filter {{{filter_name}}}` inside the `{{#species}}` iteration; plain species expose `filter_name == "all"`), plus a decision on what `γ-threshold + filtered species` should mean (composable? rejected?).

## FYI (inherited from base, not scored here)

- picmi `Simulation` never validates that a diagnostic's species (plain or `FilteredSpecies.species`) is one of the simulation's species; wrapping a fresh, never-added species object renders a setup where plugins referencing it are silently inoperative. All species-based diagnostics are exposed; this task's tests merely reuse the pattern (addressed via M2's test-side fix).
- Diagnostics register species requirements in a custom `__init__`; `model_validate`/`model_copy` would skip that. Currently unreachable in practice because validation round-trips of these models fail on non-serializable fields (observer lambda, `TimeStepSpec` — `model_dump_json` also fails, verified on `EnergyHistogram`).
- The quick-suite log is flooded with `rocrate_validator` SHACL deprecation warnings (hundreds of lines) from some metadata-validation test; noisy but harmless.
- The pytest gate output includes 3499→3503 subtests growth from the new `subTest` loop — the author's "16 additional passes" correctly counts test methods, not subtests.
