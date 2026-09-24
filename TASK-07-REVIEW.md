# Review — Task 07: Make serialization output reconstructible (pydantic round-trip fidelity)

- **Branch:** `task-07-roundtrip-fidelity` (tip `b6374eafd`, base `task-06-pydantic-metadata` / `878f980b6`)
- **Reviewed:** 2026-08-31 · **Scope:** 8 commits, 31 files, +1132/−147
- **Verdict:** REQUEST CHANGES
  (round-trip machinery is solid and well-tested, but collision setups cannot be generated at all — the e2e guarantee is broken for that class with a 2-line verified fix — and the PR's verification claims overstate what was tested.)

## 1. Summary

The branch makes `pypicongpu` models losslessly (de)serialisable: symmetric `BeforeValidator`/`PlainSerializer` pairs, `field_serializer` + `field_validator(mode="before")` pairs, per-member `Literal[True]` tag fields (solvers), `populate_by_name`, and ionization-model dispatch by C++ ionizer name. The corpus grows from 20 to 79 models and two top-level tests reconstruct `Simulation`/`Runner` from the real `metadata/*.json` artifacts. I re-ran the gate (exact match: 534 passed, 2 xfailed, 1 xpassed, 3503 subtests), ran 20 additional model-level round-trip probes (all pass except one pre-existing crash), and reproduced the end-to-end flow: generate → reload both metadata JSONs → re-serialise identically → regenerate byte-identical `include/`+`etc/` for a rich setup (Lehe solver, laser, ion with charge state, openPMD dump, radiation, moving window, 2-entry custom user input) and for filtered binning. Two problems block approval:

1. **Any simulation containing a real collision cannot be generated** — the rendering-context schema check rejects the serialized `species_pairs` shape (`collisions.py:135` lacks `return_type`/annotation); the branch fixed the first blocker in that pipeline (the functor serializer crash) but not the second, and the green corpus tests mask it. A 2-line fix was verified end-to-end in a scratch copy.
2. **The PR's "10-setup byte-identical render battery" claim is not accurate as written** — a "collisions" setup with real collisions cannot be generated in either codebase, and a filtered "binning" setup is *by design* not byte-identical to base (base renders a fresh random uuid into the filter typename every generation; branch renders a stable suffix).

## 2. Findings

### 2.1 Critical

**C1 — Collision setups cannot be generated; the rendering-context schema check rejects the serialized `species_pairs`**
- **`lib/python/picongpu/pypicongpu/collisions.py:135-140`** — `_species_pairs_serializer` (`mode="plain"`, no `return_type`, no return annotation) emits a list of `{"species_lhs", "species_rhs"}` dicts, but `model_json_schema(mode="serialization")` — which `RenderedObject.check_context_for_type` (`renderedobject.py:197-216`) applies to the `Simulation` dump inside `Runner._render_templates` (`runner.py:295-299`) — derives the schema from the field type `list[tuple[Species | FilteredSpecies, Species | FilteredSpecies]]` (an array of 2-element arrays). `generate()` therefore dies before writing any artifact, so the task's generate → reload → regenerate guarantee cannot hold for collision setups.
  - *Evidence:* minimal repro (Yee solver, 2 species, one `ConstLogCollision(coulomb_log=12.0)` via the picmi interaction API) → `jsonschema.exceptions.ValidationError: {'species_lhs': {...}, 'species_rhs': {...}} is not of type 'array'` during `write_input_file`; same failure in a richer ionization+collisions setup. Schema check in isolation: `Collision.model_dump(mode="json")` fails `Collision.model_json_schema(mode="serialization")` at `species_pairs/0`.
  - *Suggested fix:* declare the serialization shape, e.g.
    ```python
    @field_serializer("species_pairs", mode="plain", return_type=list[dict[str, Any]])
    def _species_pairs_serializer(self, value): ...

    @field_serializer("functor", return_type=dict[str, Any])
    def _serialize_functor(self, value): ...
    ```
    (verified in a scratch copy: with this, the collision setup generates, `pypicongpu_runner.json`/`pypicongpu_rendering_context.json` reload with the functor value intact, regeneration is byte-identical, and `collision.param` renders `coulombLog = 12.0_X` and `Pair<species_electron,species_hydrogen>` correctly). The `functor` side currently passes the check only by accident (the dumped constlog dict matches the looser `DynamicLogCollision` anyOf branch); annotate it anyway.
  - *Context:* the schema mismatch itself is inherited — on base the same pipeline fails one step earlier (`_serialize_functor` called the non-existent `ConstLogCollision.get_rendering_context` → `PydanticSerializationError`, which this branch fixed). So "collisions don't generate" is not a regression; but the branch explicitly undertook the collisions fix ("make collisions round-trip safe"), its model-level corpus tests pass (masking the remaining blocker), and the PR presents the work as complete — the e2e path through this very code was never exercised.
  - *Alternative:* add a regression test that runs `get_rendering_context()` (i.e. the schema check) over the round-trip corpus — that single test would have caught this before the PR.

### 2.2 Major

**M1 — The "10-setup byte-identical render regression" claim is not accurate as written**
- **`TASK-07-PR-PROPOSAL.md` (Verification)** — "a battery of 10 representative setups (basic, binning, collisions, ionization, laser, moving window, openPMD, profiles, radiation, synchrotron) rendered against the task-06 base commit and this branch produces **byte-identical** `.param`/`.cfg` files".
  - *Evidence (collisions):* a setup containing a real `Collision` cannot be generated on **either** codebase (branch: C1 schema failure; base: `_serialize_functor` AttributeError). So the battery's "collisions" entry could only be a degenerate `CollisionalPhysicsSetup()` (empty `collisions` list) — which exercises none of the collision round-trip fixes.
  - *Evidence (binning):* for a binning diagnostic with a `FilteredSpecies`, base renders `auto rangeFilter_b283ed7a1fda4c17ad5ec88f5e8fa0b8` (a fresh `uuid4` per generation — `ParticleFunctor.typename` was `f"{name}_{uuid().hex}"`) into `binningSetup.param`/`particleFilters.param`, while the branch renders a stable `rangeFilter_68d40adcb18948d585cd96b32bd3ac5e` (`typename_suffix`). These can never be byte-identical; my base↔branch diff of exactly this setup shows precisely those two files differing, nothing else. The deviation itself is legitimate and disclosed (PR "Key decisions" item 6), but it contradicts the unconditional "byte-identical" claim.
  - *What I verified as true:* my rich setup (Lehe, 2 species incl. charge-state ion, Gaussian laser, PhaseSpace + openPMD ParticleDump + Checkpoint + Radiation, moving window, custom user input) and an unfiltered binning setup render **byte-identical** `include/`+`etc/` base↔branch; the metadata JSONs differ only by the stated reconstruction fields (`type_lehe`, `index_to_direction`, openPMD `sources`/`config`) plus env-specific paths.
  - *Suggested fix:* restate the claim (e.g. "byte-identical except the deliberate stable-functor-typename change"), and once C1 is fixed, include a real collision setup — and a filtered binning setup with the typename diff explicitly accounted for — in the battery.

### 2.3 Minor

**m1 — The top-level `Runner` e2e test does not enforce the re-serialization contract**
- **`lib/python/test/picongpu/quick/pypicongpu/test_roundtrip.py:590-601`** (`test_runner_roundtrips_from_runner_metadata`) — asserts only `isinstance(restored, Runner)` and `isinstance(restored.sim, Simulation)`. The task's contract is that the reconstructed instance re-serialises identically; the `Simulation` counterpart test asserts that, the `Runner` test does not. I checked manually (reloaded `Runner.model_dump(mode="json")` is identical to the on-disk `pypicongpu_runner.json` for my rich setup) so nothing is broken today, but a future regression (e.g. a field whose serializer is not a pure function of state) would pass this suite.
  - *Suggested fix:* add `assert reloaded.model_dump(mode="json") == runner_json`; ideally also regenerate from the reloaded sim and diff `include/`+`etc/` (the task's Verification step) — this is the check that would have caught C1.

**m2 — `Collision._parse_functor` raises raw `KeyError` on malformed input**
- **`lib/python/picongpu/pypicongpu/collisions.py:101-113`** — `ConstLogCollision(coulomb_log=value["data"]["coulomb_log"])` throws `KeyError` (not a `pydantic.ValidationError`) when a dict has `type_constlog` but no `data.coulomb_log`.
  - *Suggested fix:* `coulomb_log = value.get("data", {}).get("coulomb_log"); if coulomb_log is None: raise ValueError(...)` so re-validation failures read like validation errors.

**m3 — The radiation-observer round-trip guarantee silently excludes every non-unit direction**
- **`lib/python/picongpu/pypicongpu/output/radiation.py:211-222` + `test_roundtrip.py` (`RadiationObserverConfiguration` entry)** — the corpus only covers unit-magnitude directions (`lambda _: [1, 0, 0]`; I additionally verified `lambda i: (cos(i), sin(i), 0)` round-trips with functional equivalence). Any direction whose magnitude is not symbolically `== 1` is replaced by the validator's normalising lambda, which is broken with the installed sympy: `itemgetter(2)` on 2-tuples from `.components.items()` → `IndexError`, and with free symbols `sorted(..., key=itemgetter(1))` → `TypeError: cannot determine truth value of Relational`. Such instances crash in `model_dump` (both via the new `serialise_index_to_direction` and via the pre-existing computed field `component_expressions`).
  - *Evidence:* `RadiationObserverConfiguration(index_to_direction=lambda i: (i, 1, 0)).model_dump(mode="json")` → `PydanticSerializationError` on the branch; the **identical** crash occurs on base (I ran the same construct against the task-06 tree), because base's dump also evaluates `component_expressions` — so non-unit directions were never renderable/dumpable, and this is **inherited** root cause (FYI). The branch-relevant part is that the new serializer path and the "radiation observer direction mapping" losslessness claim only hold for unit directions, and no test covers the other case.
  - *Suggested fix (follow-up):* repair the normaliser (sort by basis, take the coefficient, e.g. `tuple(c for _, c in sorted(vec.normalize().subs(index, arg).components.items(), key=lambda kv: kv[0]))`), and add a non-unit corpus entry such as `lambda i: (i, 1, 0)`.

**m4 — `TBGFlags._parse_project_path` accepts any dict with a `location` key**
- **`lib/python/picongpu/pypicongpu/runner.py:205-215`** — the inverse of `_serialize_project_path` accepts `{"location": ...}` from any dict, not just CWL Directory objects (`{"class": "Directory", ...}`). Harmless in practice (the value is just a path string), but the "inverse" is looser than its forward direction claims.
  - *Suggested fix:* also require `value.get("class") in (None, "Directory")`, or document the leniency.

### 2.4 Nits

**n1 — The canonical deserialisation symbol can collide with user symbols**
- **`lib/python/picongpu/pypicongpu/output/radiation.py:149-151,179-183`** — `deserialise_index_to_direction` binds every component's free `index` symbol to the module-level `_OBSERVER_INDEX` via `subs`; a user direction that legitimately uses a *different* symbol also named `index` (e.g. `Symbol("index", real=True)` with distinct assumptions) would be silently re-bound. Extremely unlikely in practice; consider a mangled symbol name (e.g. `pypicongpu_observer_index`) for the canonical placeholder.

**n2 — PR "Notes for follow-up tasks" overstates the guarantee**
- **`TASK-07-PR-PROPOSAL.md`** — "Task 13 can rely on the **full** round-trip guarantee: **every** model's `model_dump(mode="json")` is valid input to `model_validate`…" is true for the tested corpus but not for (a) collision *generation* (C1) and (b) non-unit radiation directions (m3). Task 13 will hit both. Qualify the sentence with the two exceptions (or fix them first).

## 3. Requirement traceability

| # | Requirement (from task file) | Status | Where / note |
|---|---|---|---|
| 1 | Round-trip contract `model_validate(model_dump(mode="json"))` + identical re-dump for `Runner`/`Simulation` + embedded models | **partial** | Holds for the 79-model corpus, my 20 extra probes, and e2e — except non-unit radiation directions (m3, inherited root cause) and collision *generation* (C1). |
| 2 | `pypicongpu_rendering_context.json` → valid `Simulation` | met | `test_simulation_roundtrips_from_rendering_context` + my e2e (re-dump identical to on-disk file). |
| 3 | `pypicongpu_runner.json` → valid `Runner` | met | `test_runner_roundtrips_from_runner_metadata` (asserts only isinstance — see m1) + my stronger e2e check (re-dump == on-disk). |
| 4 | Test suite enforcing round-trip for a corpus of realistic instances | met | 79 models via `model_validate` + type assertion + re-dump identity; 2 e2e tests. Gaps: m1 (Runner contract not asserted), no generation-level test (would have caught C1). |
| 5 | Reconstructed `Runner` renders the same setup (compare `.param` files) | partial | No automated test; done manually per PR (claim accuracy: M1); my independent reproduction: byte-identical for the rich setup and filtered binning (strict recursive diff, no ignore rules). |
| 6 | Rendered C++ output byte-identical for valid inputs | met (with disclosed, justified deviation) | Verified byte-identical base↔branch except functor typenames in filtered binning (base was non-deterministic — fresh uuid per render; the stable suffix is the fix, PR decision 6). |
| 7 | No JSON-schema files generated or checked in | met | No schema files in the diff; the self-generated `model_json_schema(mode="serialization")` fallback in `renderedobject.py` is untouched, as instructed. |
| 8 | Audit listed asymmetry sites (customuserinput, grid Vec3, runner `sim`, openPMD, collisions, lasers, functors, unit dimension, elements, ionization, density profiles, binning, radiation) | met | All sites addressed; grid `Vec3` already had `deserialise_vec` from task 06 (verified). Each fix verified by my probes (element isotope mass, solver/laser/ionization union dispatch, huygens positions, range spec, backend-config string, functor expressions, unit-dimension string, customuserinput flattening). |
| 9 | Computed/derived values re-derivable or excluded; no state mutation the JSON doesn't capture | met | `index_to_direction` now lossless; `typename_suffix` promoted to real field (verified stable); openPMD `config_filename` now a pure function of state (verified: hash-stable across reload, relative runtime form unchanged in generated files). |

## 4. Claim verification (author artifact)

| Claim (from TASK-07-PR-PROPOSAL.md) | Re-verified? | Result / delta |
|---|---|---|
| Quick gate `534 passed, 2 xfailed, 1 xpassed, 3503 subtests passed` (baseline 473) | yes | Exact match (7.15 s). The +61 = 59 new corpus entries + 2 e2e tests; xfail/xpass set is the pre-existing rocrate trio. |
| "79 representative models … satisfy `model_validate(model_dump(mode="json"))` with an identical re-dump and the same concrete type" | yes | `_MODELS` has exactly 79 entries; all pass in the gate. My 20 independent probes (union dispatch through `AnySolver`/`AnyLaser`, nested types after reload, isotope mass, hash-stable openPMD config, merged custom user input, …) all pass except the non-unit radiation direction (m3). |
| "End-to-end reconstruction … `Runner.model_validate` on `pypicongpu_runner.json` yields a `Runner` whose `sim` is a `Simulation`" | yes (stronger) | Verified plus: reloaded `Runner` re-dumps **identically** to the on-disk JSON, and a regenerated setup from the reloaded sim is byte-identical (`include/`+`etc/`, strict diff, no ignores) — for a setup the author's test doesn't cover (Lehe, laser, ion, openPMD, radiation, moving window, custom user input) and for filtered binning. |
| "Battery of 10 representative setups … byte-identical `.param`/`.cfg`" vs task-06 base | **partially** | Rich setup + unfiltered binning: byte-identical, metadata diffs exactly as documented. Filtered binning: differs in functor typenames (by design, disclosed). "collisions": cannot contain a real collision (C1) — see M1. |
| "Pre-commit green (ruff, ruff-format, …)" | yes | ruff + ruff-format + generic hooks pass on all changed Python files. |
| "the previously excluded/lossy models (`OpenPMDPlugin`, `Element`, ionization models, the radiation observer direction mapping)" now round-trip | yes, with caveats | `OpenPMDPlugin` is in the corpus and round-trips (my probes: hash-stable config filename, nested `TimeStepSpec`/`Species`/`FilteredSpecies` types survive). Coordinator's "known exclusions" note is superseded by this branch's design. Caveats: m3 (radiation, unit directions only) and C1 (collisions generation). |
| "SimpleDensity … reconstructed species list is in canonical order — identical to the first dump" | yes | Verified (multi-species probe: dump-identical, types preserved). Note: `SimpleDensity(species=[])` crashes in the pre-existing computed field (`IndexError`) — degenerate input, inherited (FYI). |

## 5. Design discussion

- **Shape-changing serializers must declare their serialization schema.** The one real bug found (C1) is a systemic pattern: the runtime rendering-context check validates `model_dump(mode="json")` against `model_json_schema(mode="serialization")`, and pydantic only honors a serializer's shape if it has `return_type` **or** a return annotation. This branch adds ~15 (de)serializer pairs without reconciling any of them with the serialization schema; it only matters where the shape actually changes (collisions today; latent for others). Recommend a standing rule: every serializer that changes shape declares `return_type`; and a corpus-level test that runs `get_rendering_context()` on every model — one test that would have caught C1 before the PR landed.
- **Discriminator style.** Per-member `Literal[True]` tag fields and the `BeforeValidator`-based ionizer-name dispatch match the codebase idiom and are the right call here; pydantic's `Discriminator` (incl. callable dispatch on `ionizer_picongpu_name`) would be marginally cleaner for `AnyIonizationModel` but is not worth a refactor. One edge: the dispatch map keys on each model's *default* ionizer name, so a user-overridden `ionizer_picongpu_name` falls through to the smart union (which may mis-dispatch) — the re-dump-identity test would catch it loudly, so this is acceptable.
- **`alt()` swallowing exceptions.** `Runner.sim`'s `BeforeValidator(lambda s: alt(lambda: s.get_as_pypicongpu(), s))` converts any conversion error into a confusing `Input should be a valid dictionary or instance of Simulation` (reproduced while debugging a binning setup). Inherited, but worth a follow-up: re-raise with the original exception chained.
- **Side-effectful serializers.** `OpenPMDPlugin`'s `model_serializer` writes the config toml to disk during `model_dump` (inherited; now with `mkdir(parents=True)`). A dump should be pure; the config write belongs in `generate()`. Follow-up for task 13, which will start treating dumps as data.
- **`SimpleDensity` reconstruction from computed fields** is the right pragmatic choice (`species` is `exclude=True`); the PR documents the canonical ordering. The `validate_species` `ValueError` fix is a nice touch.

## 6. Prioritized next steps

1. **Fix C1:** add `return_type=list[dict[str, Any]]` to `_species_pairs_serializer` and `return_type=dict[str, Any]` to `_serialize_functor` (`collisions.py`); add an e2e test that generates a setup containing a real `Collision`, reloads both metadata JSONs, and diffs the regenerated trees. (Verified working in a scratch copy.)
2. **Fix the PR claim (M1):** restate the render-regression battery (byte-identical except the deliberate stable-typename change) and include a real collision setup + a filtered-binning setup once (1) lands.
3. **Strengthen `test_runner_roundtrips_from_runner_metadata` (m1):** assert `reloaded.model_dump(mode="json") == runner_json`.
4. **Follow-up (m3):** repair the radiation normalising lambda and add a non-unit-direction entry to the corpus so the "direction mapping is lossless" claim is actually tested.
5. **Polish (m2, m4, n1, n2):** `_parse_functor` error handling, `project_path` parser leniency, canonical-symbol collision, qualify the "full round-trip guarantee" sentence for task 13.

## FYI (inherited from base, not scored here)

- **Broken radiation normaliser (root cause of m3):** `_validate_index_to_direction`'s normalising lambda (`radiation.py:220-222`, byte-identical on base) is broken with the installed sympy — any non-unit `index_to_direction` crashes `model_dump` **and** rendering (via the `component_expressions` computed field used by `radiationObserver.param.mustache:45`) on base too.
- **Collision generation on base:** dies in `_serialize_functor` (`ConstLogCollision.get_rendering_context` AttributeError) — the branch fixed half of this pipeline (C1 is the other half).
- **`OpenPMDPlugin.setup_dir`** creates a `TemporaryDirectory(delete=False)` per instance when unset — leaked temp dirs (inherited; now also `mkdir`'d and written to during dumps).
- **`alt()` exception swallowing** in `Runner.sim` (and the `species()`/`functor()` helpers in `collisions.py`) produces opaque `model_type` validation errors when `get_as_pypicongpu` fails internally.
- **`SimpleDensity(species=[])`** crashes in the pre-existing computed field `placed_species_initial` (`IndexError`) — degenerate input, but the model accepts it at construction.
- **`RadiationPlugin` default injection** (`Simulation._output_validation`) builds its default observer as `lambda _: [1, 0, 0]` — unit-magnitude, so it sidesteps the broken normaliser; that's why no standard setup hits m3 today.

## Additional FYI (added in coordinator QC, 2026-08-31)

- **Silent collision drop via `add_interaction`** (inherited, `lib/python/picongpu/picmi/simulation.py:360-363`): `sim.add_interaction(picmi.Collision(...))` only prints "unsupported: PICMI standard interactions are not supported by PIConGPU" and **drops the collision without error** — but `picmi.Collision` is PIConGPU's own model, not a PICMI-standard interaction, so a user following the obvious API path silently generates a setup with no collisions (reproduced: `write_input_file` succeeds, `collisional_physics.collisions == []`, no collision content in rendered `collision.param`). No quick test covers collision generation at all (no test uses `picongpu_interaction=` with a collision), which is why neither this nor C1 was caught.
- **`KeyError: 'other'` crash** (inherited, `simulation.py:138`): passing only bare `Collision` objects to `picongpu_interaction=[...]` (no other interaction types) crashes in `_validate_collisional_physics_setup` with an unhandled `KeyError: 'other'` instead of a clean validation error (reproduced).
- **`CollisionalPhysicsSetup` is not in the top-level `picmi` namespace** (only `picmi.interaction`), so the one working collision path requires importing from a subpackage while the natural paths drop (above) or crash (above). Together these three inherited issues mean the "collisions" story the PR presents as fixed is still user-hostile end-to-end; worth a follow-up ticket (picmi API layer, arguably task 13's alignment scope).
