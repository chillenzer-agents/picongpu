# Review — Task 02: PR 5731 — find missing details and expand the documentation

- **Branch:** `task-02-docs-expand` (tip `7374654bf`, base `6d9f158ab` / `task-01-docs-tested-snippets`)
- **Reviewed:** 2026-08-31 · **Scope:** 13 commits, 39 files, +2859/−35 (all under `docs/source/python_package/` plus one line in `docs/source/conf.py`, plus the proposal artifact)
- **Verdict:** REQUEST CHANGES
  (One factual error of the kind this task exists to eliminate — phase-space momentum units — plus a silently-empty API page in the canonical docs environment and a documented-but-unimplemented `UniformDistribution` feature.)

## 1. Summary

The branch executes all 10 work items of the task, one commit per item, with a genuinely high level of care: nearly every claim I spot-checked (rc-file search order, preset naming/ambiguity, required_information, the 4 CWL steps, run-dir layout, RO-Crate content, `tbg` internals and all its exported variables, every troubleshooting error string, diagnostic parameter names/defaults, output file names, `step()` semantics, the broken-collision/ThomasFermi/PlaneWave "not usable" notes) matches the code exactly. Test claims reproduce: quick suite `174 passed, 2 xfailed, 1 xpassed`, snippet suite `42 passed`, Sphinx build succeeds with **zero** warnings from `python_package/`. The three problems that block approval: (1) `phase_space.rst` documents `min_momentum`/`max_momentum` in "SI units (kg·m/s)" while the C++ plugin interprets the rendered value as a multiple of `m_species·c` (and "HDF5 by default" is also wrong) — following the page yields a physically meaningless momentum range; (2) the new autodoc-based API page renders **zero members** in any docs build that only installs `docs/requirements.txt` (ReadTheDocs and the documented local build), because `picongpu.picmi` cannot be imported without the package's dependency tree (`No module named 'moosetash'`) — the failure is a single unattributed warning buried in ~379; (3) `defining_simulation.rst` documents `UniformDistribution`'s `lower_bound`/`upper_bound`/`fill_in` as functional, but the frontend explicitly does not implement them (warning + commented-out code). Secondary issues: the "TWTSLaser is broken" note is refuted by a repro, an `ionization_current` description that is wrong twice over, and two inline code blocks that bypass the tested-snippet convention.

## 2. Findings

### 2.1 Critical

- **C1 — `docs/source/python_package/selected_topics/phase_space.rst:24-26` (+ snippet `docs/source/python_package/snippets/selected_topics/phase_space.py:42-43`)** — wrong units for `min_momentum`/`max_momentum`, and wrong default backend.
  - The page states the momentum range is "in SI units (kg·m/s)" and the output is "openPMD files (HDF5 by default) into the `simOutput/phaseSpace/` directory". But the value is passed through unconverted (`lib/python/picongpu/templates/etc/picongpu/N.cfg.mustache:99-100` renders `--<species>_phaseSpace.min/max {{{min_momentum}}}`) and the C++ plugin scales it: `include/picongpu/plugins/PhaseSpace/PhaseSpace.x.cpp:89-91` documents the option as `min range momentum [m_species c]` and `:280-284` computes `momentum_range_min * (getMass<Species>() * getSpeedOfLight())`. So the documented unit is off by a factor of `m_species·c` (≈ 2.7e-22 for electrons). The snippet's `±2e-26` is only sensible as SI — under the actual units it is a range of ±5e-48 kg·m/s, i.e. every particle falls into the underflow bin and the diagnostic is silently empty. Separately, the default extension is `openPMD::getDefaultExtension()`, which prefers ADIOS/BP5 over HDF5 (`include/picongpu/plugins/common/openPMDDefaultExtension.hpp`), so "HDF5 by default" is also wrong.
  - *Evidence:* code-path argument above; no conversion exists anywhere in `picmi/diagnostics/phase_space.py` → `pypicongpu/output/phase_space.py` → mustache → C++. The SI claim is inherited from the stale `picmi` docstring (`phase_space.py` docstring "Unit: kg*m/s"), which this task's correctness pass should have caught — it is exactly the class of discrepancy work item 1 targets.
  - *Suggested fix:* first reproduce with a real short run (or read the plugin's `--help`) to pin down the intended convention; then document the units as the code actually uses them (most likely "in units of `m_species·c`, i.e. a dimensionless multiple of the species rest-mass momentum") and change the snippet to matching values (e.g. `min_momentum=-1.0, max_momentum=1.0` for ±1 `m_e·c` for electrons). If the SI convention is what is *intended*, that is a code bug in the C++ plugin (or a missing conversion in the renderer) — file it and say so in the page, like the other known-limitation notes. Drop "HDF5 by default" (say "openPMD, default backend (BP5 when ADIOS2 is available, else HDF5)").

### 2.2 Major

- **M1 — `docs/source/python_package/api/index.rst:15-18` (+ `docs/source/conf.py`)** — the API page renders an empty reference in the canonical docs environment.
  - `.. automodule:: picongpu.picmi` requires importing the package. `conf.py` puts `lib/python` on `sys.path`, but `import picongpu.picmi` fails in any environment that only installed `docs/requirements.txt` (which is exactly what `.readthedocs.yaml` and the documented local build in `docs/source/dev/sphinx.rst` do): the import chain dies in `_rc_params.py` with `ModuleNotFoundError: No module named 'moosetash'` (plus `pydantic`, `picmistandard`, `cwltool`, `rocrate`, … would follow). The `automodule` then documents nothing, and the only signal is one *unattributed* warning (`WARNING: autodoc: failed to import module 'picmi' from module 'picongpu'`) that does not count against the "zero warnings from python_package" check and does not fail the build.
  - *Evidence:* fresh build with `docs/requirements.txt` venv → `docs/build/html/python_package/api/index.html` is 17 kB and contains none of `Simulation`, `GaussianLaser`, `Cartesian3DGrid`, `ElectromagneticSolver`, `PhaseSpace`, …; the body between "…re-exports the classes you will use most:" and "Submodules" is empty. In the task-02 venv (full deps) `import picongpu.picmi` works and the classes have docstrings, so the page only renders in environments like the internal `docs-snippets` CI job.
  - *Suggested fix:* make the docs build install the package so autodoc has something to import, e.g. add to `docs/requirements.txt` (and it then also works on RTD) — `picongpu @ git+https://github.com/ComputationalRadiationPhysics/picongpu@<ref>#subdirectory=lib/python` or, for the local build, `pip install ../lib/python` as a documented step. Alternatively render a visible fallback when the import fails (e.g. keep a static `autoclass` list, or a note "API reference unavailable: package not importable in this build"). `autodoc_mock_imports` is *not* a viable alternative here — mocking `pydantic`/`picmistandard` breaks class definition at import time.
  - *Alternative:* if the page should stay dependency-free, generate it from docstrings at build time (a small script emitting `autoclass` stubs) — but installing the package is simpler and matches the "stays in sync with the code" intent.
  - The artifact's claim "which is stable and renders" (known limitation 3) is therefore only true in the author's environment; flag it in the PR description so a reviewer building per `docs/requirements.txt` is not surprised.

- **M2 — `docs/source/python_package/foundations/defining_simulation.rst` (Particle Distributions section)** — `UniformDistribution`'s bounding-box parameters are documented as functional but are not implemented.
  - The page says "``lower_bound``/``upper_bound`` restrict it to a sub-volume, ``fill_in`` controls whether the density is continued when the simulation window moves". In reality `UniformDistribution.get_as_pypicongpu` (`lib/python/picongpu/picmi/distribution/UniformDistribution.py:44-57`) only emits `util.unsupported(...)` warnings for all three; the bounding-box code is commented out with a `@todo respect bounding box`. A user who restricts a species to a sub-volume per the docs gets a full-box density (with an easy-to-miss log warning).
  - *Evidence:* code path above; `util.unsupported` only logs (`pypicongpu/util.py:254-270`).
  - *Suggested fix:* either (preferred, matches the interactions-page style) note that `lower_bound`/`upper_bound`/`fill_in` are accepted but currently ignored (log a warning) and not implemented, or remove them from the parameter list and point users at `AnalyticDistribution`/`GaussianDistribution`/`FoilDistribution` for sub-volume densities.

### 2.3 Minor

- **m1 — `docs/source/python_package/foundations/defining_simulation.rst` (Laser Pulses note) + `TASK-02-PR-PROPOSAL.md` limitation 1** — the "TWTSLaser does not work" claim is refuted.
  - The note says "The ``PlaneWaveLaser`` and ``TWTSLaser`` classes exist but currently do not work: generating the input files from a simulation that uses one of them fails". Repro (task-02 venv, `write_input_file`): `PlaneWaveLaser` indeed fails (`pydantic ValidationError`: `sim.focal_position`, `sim.laser_nofocus_constant_si` missing — the pypicongpu model `pypicongpu/laser.py:139-148` requires fields the frontend never supplies), but `TWTSLaser` **succeeds** and renders a complete `PyPIConGPUTWTSParam` (W0, BETA_0, TDELAY, windows, Huygens `POSITION` array) into `incidentField.param`.
  - *Suggested fix:* narrow the note to `PlaneWaveLaser` only; keep TWTSLaser documented as supported (or verify with a compiled run first — generation-level evidence is what the note's wording makes).

- **m2 — `docs/source/python_package/selected_topics/interactions.rst` (Ionization section)** — the `ionization_current` description is wrong twice over.
  - The page says "All of them additionally take ``ionization_current``, which selects how the ionization current … is treated for energy conservation; ``None`` (the default) disables it". (a) The field has **no default** — it is required: `fieldionization.py:18` `ionization_current: IonizationCurrent | None` (constructing `picmi.ADK` without it raises `ValidationError: ionization_current Field required`). (b) The given value is **ignored at render time**: `ADK`/`BSI`/`Keldysh` `get_as_pypicongpu()` all hardcode `ionization_current=None_()` (e.g. `fieldionization/ADK.py:42,47`), so passing a non-None value changes nothing.
  - *Suggested fix:* "all models take a **required** `ionization_current` argument (pass `None` to disable); note that the currently rendered output always uses `None` — the choice is not yet applied."

- **m3 — `docs/source/python_package/selected_topics/time_steps.rst` ("Where the Output Lands")** — contradicts `phase_space.rst`.
  - "the **phase space**, **energy histogram** and **macro-particle count** plugins write plain files directly into ``simOutput/``" is wrong for phase space: the C++ plugin writes openPMD into `simOutput/phaseSpace/` (`PhaseSpace.x.cpp:385` `createDirectoryWithPermissions("phaseSpace")`), which `phase_space.rst` itself says. Fix the bullet (move phase space to the openPMD group / its own line).

- **m4 — `docs/source/python_package/selected_topics/energy_histogram.rst`** — "(one per recorded time step)" is wrong.
  - The plugin opens one file per (species, filter) in its constructor and appends one line per notified step (`BinEnergyParticles.x.cpp:329,396-413,455-480`); the header line (`#step <edges> count`) is written once. So: one file, header + one line per recorded step — as the very next sentence of the page already says. Delete/rewrite the parenthetical to avoid the contradiction.

- **m5 — `docs/source/python_package/selected_topics/verification.rst` (stage 3)** — the quick suite is not available to the page's audience.
  - The page tells users to `cd lib/python/test/picongpu && python -m pytest quick/ -q` "on this machine". The test tree is not shipped with a pip/uv install: the hatch wheel/sdist only package `picongpu` plus forced `core/` includes (`lib/python/pyproject.toml:62-77`), and the quickstart's install path is exactly pip/uv. The command only works from a source checkout.
  - *Suggested fix:* state that this stage needs a source checkout (`git clone … && cd lib/python/test/picongpu`), or replace it with an install-agnostic smoke test (import + one `write_input_file` round trip, which stage 2 already covers).

- **m6 — convention: new inline executable code blocks** — two new pages put executable code in inline `code-block`s instead of the task-01 tested-snippet system (task: "move any code into the tested-script system … rather than inline blocks").
  - `selected_topics/binning.rst` (Particle Filters): a `.. code-block:: python` with `def fast_enough(particle): … FilteredSpecies(…)` — not executed by `test_snippets.py`, and not runnable as shown (references an undefined `electrons`). The filtered-species mechanism deserves a tested snippet (e.g. extend `binning.py` or add `filters.py`) with an `N.cfg`/param expectation like the others.
  - `selected_topics/verification.rst` (stage 3): `.. code-block:: bash` with the pytest command — executable, but not a `bash -n`'d snippet file (see m5 for why it also needs rewording).
  - (The `interactions.rst` `picongpu_interaction=[…]` block is a non-executable ellipsis illustration; the TOML `::` literal blocks match the pre-existing house style — both acceptable.)

### 2.4 Nits

- **n1 — `binning.rst` (Particle Functors)** — the `particle.get("position")` keyword list is presented exhaustively but omits valid `origin` values (`"global"`, `"moving_window"`, `"local_with_guards"`) and the `"pic"` unit (`particle_functor/particle_functor.py:_COORDINATE_SYSTEM`). Say "e.g." or list them.
- **n2 — `hpc_submission.rst`** — "the runner invokes `tbg` once … and the generated `submit.sh` script invokes the submit command **a second time**" is confusing: the submit command is invoked for the *first* time there; `tbg` is what ran in the prepare step.
- **n3 — `running_simulation.rst`** — the example `simulation.run(setup_dir=…, run_dir=…, jobs=8, force=True)` mixes runner kwargs (`setup_dir`/`run_dir` are consumed by `picongpu_run` and never reach `workflow/input.yaml`) with actual workflow inputs (`jobs`, `force`, `cfg_file`, `submit_system`, `template_file`, `overwrite_vars` — `pypicongpu/runner.py:95-161`). Split the example.
- **n4 — `checkpoint.rst`** — "``restart=True`` — Restart from the given checkpoint" vs. the model docstring ("restart from the **latest** checkpoint"); the specific one is selected via `restartStep`. Align the wording.
- **n5 — `troubleshooting.rst`** — the "An initial distribution needs a layout" entry says "(or the reverse)"; the reverse case (distribution without layout) fails with a pydantic `layout: Field required` error in `_DensityImpl`, not with that message.

## 3. Requirement traceability

| # | Requirement (from task file) | Status | Where / note |
|---|------------------------------|--------|--------------|
| 1 | Correctness pass vs. post-5639 code | **partial** | rc search order, preset naming/ambiguity, `required_information`, `dirty_reset_policy`, `step()` semantics, run-dir layout, RO-Crate, all troubleshooting strings verified accurate; but C1 (phase-space units), M2 (UniformDistribution bounds), m1 (TWTSLaser note) remain |
| 2 | Quickstart, install → first Simulation → run, Python-only | met | `quickstart.rst`; PEP 723 + uv/pip paths; no C++ cross-references; cell-size arithmetic checks out (1e-6/128 = 7.8125e-9) |
| 3 | Environment/preset configuration (`picongpurc.toml`, presets, `tbg_submit`/`tbg_tpl_file`) | met | `configuring_environment.rst`; `picrc-builder` named in the task's ground-truth list does not exist in this branch (no module/script/entry point — verified), correctly flagged in the artifact |
| 4 | Defining a simulation (grids/solvers, lasers, species, distributions, layouts) | **partial** | comprehensive and mostly verified (CFL coupling, n_gpus list semantics, super-cell check, a0/E0 exclusivity, pushers, `charge_state` error, layouts); M2 + m1 accuracy issues |
| 5 | Running & workflow internals (4 CWL steps, run-dir layout, RO-Crate, resubmission/restart) | met | `running_simulation.rst`; matches `templates/workflow/*`, `organize_output.sh`, `runner.py`, `_rc_params.py` RO-Crate code; `step()` full-run-only + `@todo` at `simulation.py:365` accurate |
| 6 | Diagnostics/plugins — one page per diagnostic | **partial** | one page each for time_steps, phase_space, energy_histogram, macro_particle_count, openPMD, binning, radiation, checkpoint + 8 tested snippets; C1/m3/m4 accuracy issues |
| 7 | Interactions (deep-dive; C++ cross-refs allowed) | met | ADK/BSI/Keldysh/Synchrotron + tested snippet; broken-collision and ThomasFermi notes verified by repro; m2 nuance |
| 8 | HPC submission specifics (deep-dive) | met | `hpc_submission.rst`; `tbg` flags, `.Name=`/`!Name` mechanics, exported `TBG_*` vars, two-stage prepare/submit, job-id semantics all verified against `bin/tbg` + CWL steps |
| 9 | Troubleshooting/common failure modes | met | every quoted error string located verbatim in the sources (`grid.py`, `runner.py`, `_rc_params.py`, `bin/tbg`, …); n5 aside |
| 10 | Testing/validation guidance for users | **partial** | `verification.rst` staged cheap→expensive; m5 (quick suite not shipped in pip install) |
| — | API page in sync with public API | **partial** | mechanism right (`automodule` + `__all__`, 33 exports), but M1: renders empty in the canonical docs env |
| — | Sphinx build passes; cross-refs/TOC consistent | met | build succeeded; 0 warnings from `python_package/`; all `:ref:`s resolve; C++ deep-dive refs (`usage-plugins-binningPlugin`, `usage-tbg`, `model-*`, `synchrotronRadiation`) resolve via breathe |
| — | Audience: C++ cross-refs only in deep dives | met | none in quickstart/foundations; only in binning/interactions/hpc notes |
| — | One commit per work item + final re-evaluation loop | met | 12 item commits + re-evaluation fix (`picongpu_n_gpus` list typing — verified against `grid.py:62` typeguard) |
| — | Snippet convention (tested scripts) | **partial** | all new python snippets run with expectations in `test_snippets.py`; all new `.sh` get `bash -n`; m6: two inline code blocks bypass it |

## 4. Claim verification (author artifact)

| Claim (from TASK-02-PR-PROPOSAL.md) | Re-verified? | Result / delta |
|-------------------------------------|--------------|----------------|
| Snippet suite 42 passed (25 at baseline) | yes | `42 passed in 49.59s` — exact |
| Quick suite 174 passed / 2 xfailed / 1 xpassed | yes | `174 passed, 2 xfailed, 1 xpassed, 3499 subtests passed` — exact |
| Sphinx: exit 0, build succeeded, zero warnings from `python_package/`, no "Include file … not found" | yes | build succeeded; 0 python_package warnings; 0 include-not-found. Total warnings 379 here vs. "398" claimed — environment-dependent delta, all outside `python_package/` |
| pre-commit `--all-files`: all passed | no | not re-verifiable here (pre-commit not installed) |
| Known limitation: collision classes broken — `_serialize_functor` → `get_rendering_context()` AttributeError | yes | reproduced exactly: `PydanticSerializationError … AttributeError: 'ConstLogCollision' object has no attribute 'get_rendering_context'` (both at `model_dump` and at `write_input_file` with mixed interactions) |
| Known limitation: ThomasFermi missing `ionization_electron_species` | yes | reproduced: `ValidationError: sim.ionization_electron_species Field required` |
| Known limitation: PlaneWaveLaser / TWTSLaser "rendering path incomplete" / generation fails | partially | PlaneWaveLaser: reproduced (`focal_position`, `laser_nofocus_constant_si` missing). **TWTSLaser: generation succeeds** with a complete render — see m1 |
| `picrc-builder` does not exist in this branch | yes | no module/script/entry point anywhere under `lib/python` |
| autoapi broken ("Unable to read file") in this environment | yes | 80+ such warnings, all `pypicongpu` sources — pre-existing, correctly scoped |
| "10 pre-existing RST warnings … via autodoc" from `picmi` docstrings | not reproduced | 0 such warnings in the minimal docs venv (the `picmi` import fails before autodoc reads docstrings); presumably true in the author's full-deps env — see M1 |
| Diff: 38 files, ~2756 insertions, 35 deletions | yes | 38 files / +2756 / −35 excluding the proposal artifact itself |

Worked as intended / verified: the correctness fixes in commit `46c0f3f38` (rc search order, preset naming, `step()`/`picongpu_run` semantics), the `rc_params_list_presets.py` rewrite (matches `_read_preset` semantics exactly, incl. zero-profile dirs like `davinci-rice` being correctly *not* listed), the quickstart, and the HPC/troubleshooting pages.

## 5. Design discussion

The overall design — one tested snippet per documented capability, deep-dive pages under `selected_topics/`, literal blocks only for configuration (TOML) and non-executable illustrations — is the right shape for this codebase and is executed consistently; the snippet harness (inherited from task 01) is doing its job (42/42, including file-content assertions on generated `.param`/`N.cfg`).

The two structural weaknesses are both about **build-environment coupling**:

1. **API page via live `autodoc` (M1).** Autodoc-ing a package whose import needs a git-dependency tree (`moosetash`, `rocrate`, `cwltool`, …) that `docs/requirements.txt` deliberately does not install means the reference page's content depends on the build environment in a way that fails *silently* (unattributed warning, "build succeeded", empty page). Alternatives, in order of preference: (a) install the package into the docs env — one line in `docs/requirements.txt` and the documented local build; it then works on RTD too, and the "stays in sync with the code" promise is real; (b) a build-time generated static `autoclass` list that degrades visibly when imports fail. Mocking is not viable (`pydantic`/`picmistandard` bases are needed to *define* the classes). A maintainer should weigh that (a) adds heavy deps (incl. two git deps) to the docs env; given the internal CI already installs the package before the docs build, (a) merely aligns RTD with CI.

2. **Documenting intended vs. actual behavior for broken/incomplete features.** The branch sets a good pattern of "known limitation" notes that name the exact failure (verified accurate for collisions, ThomasFermi, PlaneWaveLaser). The failure mode to avoid is notes drifting from the code (m1: TWTSLaser) and docstrings propagating into pages without checking the consuming C++ (C1: the SI-units claim exists in the `picmi` docstring *and* in the new page, while the C++ has said `[m_species c]` since the 2024 compile-unit transform). Since this PR will sit in a WIP PR for a while, each such note should be re-verified at merge time (the artifact's reviewer checklist already asks for this — good).

On the phase-space units (C1) specifically: the right fix may be a code change (either the renderer converts SI → `m_species·c`, or the C++ stop multiplying) — the doc should describe what the code does *today* and flag the inconsistency, mirroring how the collision/ThomasFermi notes are handled.

## 6. Prioritized next steps

1. Fix `phase_space.rst` + `phase_space.py` (C1): determine the actual unit convention by rendering/running, document it correctly, fix the snippet values, drop "HDF5 by default". If the SI convention is intended, file the C++/renderer bug and note it on the page.
2. Make the API page render in the canonical docs environment (M1): install the package in `docs/requirements.txt` / `.readthedocs.yaml` / documented local build (and say so in the PR), or add a visible fallback; re-verify the built HTML actually contains the class members.
3. Fix the `UniformDistribution` bounds/fill_in description (M2): mark as accepted-but-unimplemented or remove.
4. Narrow the laser note to `PlaneWaveLaser` (m1) and correct the PR-proposal limitation list accordingly.
5. Correct `ionization_current` (required, currently ignored at render) in `interactions.rst` (m2).
6. Resolve the phase-space output contradiction (m3), the energy-histogram "(one per recorded time step)" parenthetical (m4), and the verification-page quick-suite availability (m5).
7. Move the `FilteredSpecies` example into a tested snippet (m6); reword the two nits-level confusions in `hpc_submission.rst` / `running_simulation.rst` (n2/n3) while touching those files.

## FYI (inherited from base, not scored here)

- The `picmi` `PhaseSpace` docstring itself claims "Unit: kg*m/s" — root source of C1; fixing docs without touching the docstring (or the C++) will let this discrepancy recur.
- `Simulation.__init__`'s `_validate_collisional_physics_setup` (`picmi/simulation.py:114-141`) crashes with `KeyError: 'other'` when the interaction list contains exactly one bare `Collision` (reproduced) — an additional, undocumented collision failure mode on top of the serialization bug the page already documents. The page's bottom line ("collisions cannot be used") still holds.
- autoapi "Unable to read file" warnings for all `pypicongpu` sources and the `pypicongpu/misc.rst` → `autoapi/…` toctree warning are pre-existing and correctly scoped by the artifact.
- `usage/picmi/intro.rst:92` undefined label `_picmi_extensions` — pre-existing warning, outside this task's tree.
- The task file's ground-truth list mentions `picrc_builder.py` / `scripts.picrc-builder`; neither exists in this lineage (correctly reported by the artifact).
