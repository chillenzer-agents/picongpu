# Review — Task 13: Reorganise pypicongpu to align with the PIConGPU C++ interface

- **Branch:** `task-13-pypicongpu-alignment` (tip `a7c8bbe4b`, base `b6374eafd`)
- **Reviewed:** 2026-08-31 · **Scope:** 10 commits, 36 files, +1101/−225
- **Verdict:** APPROVE — high-quality reorganisation that mirrors the C++ interface
  across all 9 core items without touching C++, keeps rendered output byte-identical
  (except the intentional, numerically-identical item-4 ratio change), with a green
  test gate that matches the reported numbers exactly; only minor artifact/tracking
  issues and a few nits.

## 1. Summary

The branch reorganises the pypicongpu (render-model) and picmi (bridge) layers to
mirror the PIConGPU C++ interface, one divergence item at a time, for items 1–9 of
the task inventory. It never modifies `include/`/`src/` (verified: no C++ files in
the diff), introduces no new features, and for every item the rendered
`.param`/`.cfg` output is byte-identical for valid inputs — except item 4, where the
mass/charge ratio is now rendered as a precomputed literal instead of the compile-time
expression `<si> / sim.si.getBaseMass()` (documented, and numerically identical). I
re-ran the test gate (base `534 passed, 2 xfailed, 1 xpassed` → branch `566 passed,
2 xfailed, 1 xpassed` — exactly as the artifact claims), re-rendered a 13-config
battery on base vs branch (only `speciesDefinition.param` differs), verified the
created/derived `CreateDensity` → `ManipulateDerive<DensityWeighting>` C++ render,
and confirmed the Python base constants are bit-exact with the C++ `SI::BASE_*`
constants. No Critical or Major defects found. The notable issues are all in the
author's artifact (FINDINGS doc): two deferred items (10/11) are dropped from
tracking, the item-4 "electron → 1.0" example is off by ~3.4e-12, and the
"pre-existing bug #2" scope is overstated; plus a couple of test nits.

## 2. Findings

### 2.1 Critical
None found.

### 2.2 Major
None found.

### 2.3 Minor

- **m1** — `TASK-13-FINDINGS.md` (status table lines 27–37; "Next PRs" lines 288–300)
  — items 10 (synchrotron) and 11 (radiation-plugin trivial mirrors) are deferred but
  recorded in **neither** the per-item status table (which stops at item 9) **nor** the
  "Next PRs" list (4 entries: schema fix, `value_identifier`s, Axel struct, `MODEL_NAME`).
  The body (line 40) says "The two remaining optional items of the original plan were
  not started (time box); candidates are listed under 'Next PRs'" — which is inaccurate:
  10/11 are not listed under Next PRs. The task's Verification section requires "This
  file's inventory carries a status per item (`open` / `done in <PR>` / `won't do
  (reason)`)"; 10/11 have no status.
  - *Evidence:* `grep -n` over FINDINGS — status table rows end at `| 9 |`; Next PRs has
    no synchrotron/radiation entry; only the body prose mentions "the two remaining
    optional items".
  - *Suggested fix:* add two rows `| 10 | P1(opt) | synchrotron params | open —
    deferred (optional trivial mirror, after core items) | — |` and `| 11 | … |` to the
    table (or add them to Next PRs explicitly) so the deferral is actually tracked.

- **m2** — `TASK-13-FINDINGS.md` (item-7 section, "Discovered pre-existing bugs" #2)
  — the FINDINGS claims the render-context schema/serializer mismatch "affects any
  model whose plain-mode field serializer changes the shape (e.g.
  `Simulation.customuserinput` when non-empty, `Binning.openPMDBackendConfig`)" and
  lists them as "latent" affected models. I verified **both render fine** on base and
  branch, so the scope is overstated: only the collision setup actually fails.
  - *Evidence:* `probe_latent.py` → `customuserinput OK`, `binning_backend_config OK`
    on both `b6374eafd` and branch tip. (The underlying collision bug is pre-existing and
    not scored here; this finding is about the *description* of that bug in the artifact.)
  - *Suggested fix:* scope bug #2 to the collision setup only, or explain the specific
    serializer-shape difference that makes `Collision.species_pairs`/`functor` fail while
    `customuserinput`/`Binning.openPMDBackendConfig` do not; do not list models that
    render fine.

### 2.4 Nits

- **n1** — `test/picongpu/quick/picmi/test_species.py:33-37`
  — `test_pusher_members_match_cpp_struct_names` (and the shape twin, :55-57) guard only
  C++ *identifier*-ness via the regex `[A-Za-z_][A-Za-z0-9_]*`, not whether the C++
  struct actually exists. So `Pusher.Axel` (`pypicongpu/species/species.py:72`, value
  `"Axel"`, pre-existing) passes this test even though `pusher.param` declares
  `struct HigueraCary/Free/ReducedLandauLifshitz` but **no `struct Axel`** — i.e. it
  renders non-compiling `particles::pusher::Axel`. The class docstring "the
  picmi→pypicongpu pusher/shape bridge must not drift from the C++ names" overstates
  what is checked.
  - *Suggested fix:* assert `pusher.value` / `shape.value` against a set of known-declared
    C++ struct names, or drop/marker `Axel`, or (cheapest) tighten the test docstring to
    say it checks identifier-ness only.

- **n2** — `test/picongpu/quick/picmi/test_species.py:44` and `:61`
  — tautological assertions: `assert Pusher[method.name] is Pusher[method.name]` and
    `assert Shape[particle_shape.name] is Shape[particle_shape.name]`. These are always
    true and add no coverage (the meaningful check is on the following line, e.g.
    `:46`/`:63`).
  - *Suggested fix:* delete both tautologies.

- **n3** — `TASK-13-FINDINGS.md` (item-4, lines 139–140)
  — the worked example "electron `9.109…e-31 / sim.si.getBaseMass()` → `1.0`" is
  inaccurate. The rendered electron **mass** ratio is `0.99999999999656941` (the
  `particle`-package electron mass is 2018-CODATA `9.1093837138687491e-31`, while the
  Python/C++ base is the rounded `9.1093837139e-31`); only the electron **charge**
  ratio is exactly `1.0`. The CHANGELOG "numerically identical" claim is correct — this
  is just the illustrative number.
  - *Evidence:* rendered `yee_bare/include/picongpu/param/speciesDefinition.param:39`
    → `MassRatio_species_electrons, 0.99999999999656941`; `:40` →
    `ChargeRatio_species_electrons, 1.0`.
  - *Suggested fix:* correct the example to `0.99999999999656941` (or phrase as
    "≈1.0; charge exactly 1.0, mass ≈ 1−3.4e-12 because the particle-package CODATA
    value differs from the rounded C++ base").

## 3. Requirement traceability

| # | Requirement (task file) | Status | Where / note |
|---|---|---|---|
| D | C++ is the fixed reference — never modified | met | no `include/`/`src/` files in the diff (36 files: pypicongpu/picmi/templates/tests/docs/CHANGELOG) |
| D | No new features (reorganisation only) | met | every change reorganises an existing concept |
| 1 | Pusher 3-way enum mismatch (P0) | met | `Pusher.Higuera`→`HigueraCary` value `"HigueraCary"`; picmi `Li` → explicit error; rendered C++ valid (battery `pushers` rendered) |
| 2 | Stale test `bound_electrons` (P0) | met | test now asserts `charge_state` |
| 3 | SimpleDensity → deriving model (worked example) | met | `SimpleDensity`→`CreateDensity`; created/derived split; rendered `CreateDensity<…,species_a>` + `ManipulateDerive<DensityWeighting,species_a,species_b>` verified |
| 4 | Mass/charge SI → ratio concept | met | `SpeciesConstants` + computed `mass_ratio`/`charge_ratio`; template renders precomputed ratio; base consts bit-exact with C++ |
| 5 | Density-ratio semantics | met | `Gaussian.density`→`density_si` (picmi alias kept); `DensityRatio` docstring documents C++ semantics |
| 6 | Charge state vs bound electrons | met | docstrings; unphysical charge state rejected at construction (mirrors C++ `assert`) |
| 7 | Collision model single source of truth | met | invariant moved to pypicongpu `CollisionalPhysicsSetup`; picmi thin bridge |
| 8 | Ionization name/current bridging | met | `ionization_current` bridged (no silent drop); `ThomasFermi` electron species bridged; `ThomasFermi` rejects current (battery `ionization` rendered) |
| 9 | Simulation defaults & compile/runtime split | met | verified aligned, no code change needed (documented) |
| 10 | Synchrotron params (optional) | partial | not started; deferral acceptable but untracked (m1) |
| 11 | Radiation plugin defaults (optional) | partial | not started; deferral acceptable but untracked (m1) |
| V | Test gate green per PR | met | 534→566 passed, 2 xfailed, 1 xpassed (re-verified, exact) |
| V | Rendered output byte-identical (modulo documented) | met | battery base vs branch: all `.param`/`.cfg` byte-identical except item-4 ratio |
| V | Per-item status in inventory | partial | items 10/11 missing status (m1) |

## 4. Claim verification (author artifact)

| Claim (TASK-13-FINDINGS.md) | Re-verified? | Result / delta |
|---|---|---|
| Test gate baseline `534 passed, 2 xfailed, 1 xpassed`; final `566 passed, 2 xfailed, 1 xpassed` | yes | **MATCH exactly** — branch `566 passed, 2 xfailed, 1 xpassed`; base `534 passed, 2 xfailed, 1 xpassed` (re-run in this env) |
| "rendered `.param`/`.cfg` byte-identical for valid inputs" per item | yes (13-config battery, base vs branch) | **MATCH** — every `.param`/`.cfg` byte-identical; only `speciesDefinition.param` differs (item 4, intentional) |
| Item-4 "electron → 1.0, proton → 1836.15, charge → −1.0" | partial | charge ratio exactly `1.0` (correct); electron **mass** ratio is `0.99999999999656941`, not `1.0` (n3). CHANGELOG "numerically identical" is correct |
| Item-3 "byte-identical; only metadata JSON keys change" | yes | MATCH for the render; created/derived C++ verified |
| Item-7 "collision render broken at base; same family affects customuserinput/binning" | yes | collision broken — reproduced on base **and** branch (battery `collisions_const`/`collisions_dynamic` fail; dumps identical). But customuserinput/binning render **fine** on both → bug #2 scope overclaimed (m2) |
| "Next PRs" lists the deferred candidates | no | items 10/11 are **not** in Next PRs (m1) |

## 5. Design discussion

- **Item 4 (option B: keep stored SI, add computed ratio on top)** is the right
  mechanism. It preserves the task-06 SI unit policy and every existing call site while
  adding the C++-side `MassRatio_<T>`/`ChargeRatio_<T>` concept. Precomputing the ratio
  in Python and rendering the literal (instead of the compile-time expression) is safe
  because the Python `SpeciesConstants` base values (`9.1093837139e-31`,
  `-1.602176634e-19`) are bit-exact with the C++ `SI::BASE_MASS_SI` /
  `SI::BASE_CHARGE_SI` (both = the C++ `ELECTRON_MASS_SI` / `ELECTRON_CHARGE_SI`), so the
  IEEE double is identical to what C++ would have computed. Trade-off a maintainer should
  weigh: the generated `.param` now shows only a number — the human reading the output can
  no longer see it is "electron-mass-normalised". Acceptable for this task (the C++
  default file has the same property), worth a one-line comment in the template.
- **Item 3 (created/derived split)** mirrors the C++ `InitPipeline`
  (`CreateDensity` first species, `ManipulateDerive<DensityWeighting>` for the rest)
  exactly, and the deterministic sort key `(ratio-or-0, name)` is a clean fix for the
  `set(species)` hash-randomisation flake. One **sharp edge** (pre-existing, not
  introduced here, but now load-bearing for the ratio-based sort): `density_scale` must
  be set **at `Species` construction** — `picmi/species.py:157` registers initial
  requirements in `__init__`, so setting `density_scale` afterwards is silently ignored
  (no `DensityRatio` constant). The task's own test sets it in the constructor, so this
  is only a gotcha for hand-built setups; a docstring note on `Species.density_scale`
  would help.
- **The collision render-context schema-check bug** (FYI) is the most significant
  *unfixed* robustness issue, but it is genuinely pre-existing and correctly deferred.
  The author's suggested fix (align fallback schema generation with the actual
  plain-mode serialised shape, or ship the pre-generated schemas under
  `share/picongpu/pypicongpu/schema/`) is the right direction — that mechanism already
  exists in `renderedobject.py`.
- **Alternative for item 4:** keeping the compile-time expression and merely *documenting*
  the C++ ratio concept would avoid the precomputed literal, but it would leave the
  pypicongpu model not mirroring C++'s "ratio" structure — which is the explicit goal of
  this task. Option B is better.

## 6. Prioritized next steps

1. Add a status for items 10 & 11 to the FINDINGS (table rows or Next PRs) — close the
   tracking gap (m1).
2. Correct the artifact's factual claims: item-4 electron example → `0.99999999999656941`
   (n3), and scope bug #2 to the collision setup only (m2).
3. Delete the two tautological asserts in `TestPusherShapeTranslation` (n2).
4. Strengthen the pusher/shape drift test to check declared C++ struct names, or
   drop/marker `Axel` (n1).
5. (Already-tracked next PR) fix the collision render-context schema check and add an
   end-to-end collision-render quick test (would have caught it).

## FYI (inherited from base, not scored here)

- **Collision rendering is broken** by the render-context schema check
  (`RenderedObject.check_context_for_type` validates `model_dump(mode="json")` against
  `model_json_schema(mode="serialization")`, which ignores plain-mode `field_serializer`s;
  `Collision.species_pairs`/`functor` serialise to a different shape). Reproduced on base
  `b6374eafd` **and** branch (battery `collisions_const`/`collisions_dynamic` fail; base vs
  branch dumps identical). Author documented it and deferred to Next PRs #1. (Note: the
  FINDINGS' claim that `customuserinput`/`Binning.openPMDBackendConfig` are also affected
  is inaccurate — both render fine on base and branch; see m2.)
- **`Pusher.Axel` renders non-compiling C++** — `particles::pusher::Axel` has no
  `struct Axel` in `pusher.param` (pre-existing; documented, Next PRs #3, C++-side fix).
- **TWTSLaser / FromOpenPmdPulseLaser round-trip breakage** — pre-existing, untouched by
  this diff.
- **Dead `MODEL_NAME` field** on the picmi ionization models — declared but never read
  (pre-existing; documented; public API → separate cleanup PR, Next PRs #4).
