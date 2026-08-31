# Task 02 — response to TASK-02-REVIEW.md

Verdict was REQUEST CHANGES (1 critical / 2 major / 6 minor / 5 nits).
All findings were verified against the code first; every one is addressed
below. No finding is rejected. Rework = 11 new commits on top of the
review commit `873180e6f` (rebased base `7b086af5d`, reworked task-01).

## Per-finding disposition

| Finding | Disposition | Commit |
|---------|-------------|--------|
| C1 | **Fixed.** Verified: `PhaseSpace.x.cpp` help says `[m_species c]` and the constructor multiplies the unconverted value by `getMass<Species>()*getSpeedOfLight()`; `N.cfg.mustache` renders it as-is; `openPMDDefaultExtension.hpp` prefers ADIOS2 (bp5/bp4) over HDF5. Page now documents the actual unit (dimensionless multiple of the species rest-mass momentum), drops "HDF5 by default" (default backend = ADIOS2 when available, else HDF5), adds an explanatory note (a `2e-26` value covered ~1e-47 kg·m/s → all particles in the underflow bin), snippet now uses `-1.0`/`1.0` (±1 m_e·c) and the test pins the rendered `--electrons_phaseSpace.min/-max` lines. Also corrected the stale `Unit: kg*m/s` docstring in `picmi/diagnostics/phase_space.py` (review FYI: root source of the discrepancy; docstring-only change so the autodoc'd API page does not repeat the error). | `e6b276db6` |
| M1 | **Fixed.** Verified: fresh env with only `docs/requirements.txt` → `import picongpu.picmi` dies (`moosetash`), autodoc renders an empty page with one unattributed warning. Fix per suggested option (a): the canonical docs environments now install the package from the checkout being documented — `.readthedocs.yaml` gets `- {path: lib/python, method: pip}`, and the documented local builds (`dev/sphinx.rst` pip instructions + `picongpu-docs-env.yml`) get the `pip install ../lib/python` step. Deliberately NOT added to `docs/requirements.txt`: relative paths there have pip-version-dependent resolution, and the `docs-snippets` CI job (which runs `pip install -r docs/requirements.txt` after an editable install) would do a redundant non-editable reinstall of the package incl. its two git deps. Re-verified end-to-end: fresh py3.11 venv (RTD's version) + `docs/requirements.txt` + package install → `build succeeded`, 0 `python_package/` warnings, API page contains the class members (GaussianLaser ×12, Cartesian3DGrid ×15, PhaseSpace ×1). | `0022a0791` |
| M2 | **Fixed.** Verified: `UniformDistribution.get_as_pypicongpu` only emits `util.unsupported` warnings for `fill_in`/`lower_bound`/`upper_bound` (bounding-box code commented out, `@todo`). Page now marks the three parameters as accepted-but-ignored (warning when non-default) and points to `AnalyticDistribution`/`GaussianDistribution`/`FoilDistribution` for sub-volume densities (the review's preferred option). | `d5c69b582` |
| m1 | **Fixed.** Re-reproduced: `TWTSLaser` generation **succeeds** (complete `PyPIConGPUTWTSParam`: W0_SI, BETA_0, TDELAY, TWTS functors); `PlaneWaveLaser` generation **fails** with `ValidationError: sim.focal_position / sim.laser_nofocus_constant_si Field required`. Note narrowed to `PlaneWaveLaser` with its actual cause; short `TWTSLaser` entry added (documented as supported at the generation level the note's wording makes); PR-proposal limitation list corrected. | `163eab79d` |
| m2 | **Fixed.** Verified: `ionization_current` is a required field (`FieldIonization`, no default — constructing `picmi.ADK` without it raises `ValidationError: Field required`) and ADK/BSI/Keldysh `get_as_pypicongpu()` all hardcode `ionization_current=None_()`. Page now says: required, pass `None` to disable, choice not yet applied at render time. The tested snippets already pass `ionization_current=None` explicitly, so they stay consistent. | `dd375c1a4` |
| m3 | **Fixed.** Verified: `PhaseSpace.x.cpp` writes openPMD into `simOutput/phaseSpace/` (`createDirectoryWithPermissions("phaseSpace")`), while `BinEnergyParticles`/`CountParticles` write plain `.dat` files into the run dir. Bullet split (phase space → its own line, cross-ref via new `.. _phase-space:` label). Re-evaluation pass also found the same contradiction in `verification.rst` stage 5 ("phase-space / energy-histogram / macro-particle-count files in simOutput/") — fixed in the same commit. | `a39c12e9e` |
| m4 | **Fixed.** Verified: `BinEnergyParticles.x.cpp` opens one file per (species, filter) in the constructor (`restoreTxtFile`), writes the header once (`openNewFile`), appends one line per notified step. "(one per recorded time step)" replaced with "(one per species and filter)" + "each recorded time step appends one line of counts". | `a39c12e9e` |
| m5 | **Fixed.** Verified: the hatch wheel/sdist packages only `picongpu` (+ forced core includes), so `lib/python/test/picongpu` is absent from pip/uv installs. Stage 3 now states a source checkout is required; the command moved out of the inline code-block into tested snippet `verification/quick_suite.sh` (satisfies m6 for this page as well). | `011c55dc6` |
| m6 | **Fixed.** The `FilteredSpecies` inline code-block (which referenced an undefined `electrons`) is now the tested `binning.py` snippet (extended, the review's first suggested option): it builds `fast_enough` + `FilteredSpecies` + a second binner restricted to `electrons_fast`; the suite asserts the rendered filter functor (`Ekin > 1.6e-15`) and the `FilteredSpecies{...}` species tuple in `binningSetup.param`. The verification-page command is handled by m5. (The `interactions.rst` ellipsis block and TOML blocks were deemed acceptable by the review and are unchanged.) | `011c55dc6`, `cdc398f31` |
| n1 | **Fixed.** Verified against `particle_functor.py:_COORDINATE_SYSTEM`: `origin` now lists `total` (default), `cell`, `local`, `global`, `moving_window`, `local_with_guards`; `unit` lists `cell` (default), `pic`, `si`; defaults match `Particle.get`. | `cdc398f31` |
| n2 | **Fixed.** Reworded: `tbg` runs in the `prepare_submission` step (no job exists yet); the submit command is invoked for the *first* time by `submit.sh` in the `submit` step — verified against `steps/prepare_submission.cwl` / `steps/submit.cwl`. | `74f04cda3` |
| n3 | **Fixed.** Verified: `picongpu_run(setup_dir, run_dir, **flags)` consumes `setup_dir`/`run_dir` itself; only `**flags` reach `PicBuildFlags`/`TBGFlags` → `workflow/input.yaml`. Example now `simulation.run(jobs=8, force=True)` with the real input names listed; `setup_dir`/`run_dir` get their own sentence. | `74f04cda3` |
| n4 | **Fixed.** `restart=True` now documented as "latest checkpoint (or the specific step via `restartStep`)"; the "run aborts if it does not exist" caveat kept. Matches the model docstring. | `e529e2d45` |
| n5 | **Fixed.** Verified in `picmi/simulation.py:_picongpu_add_species`: the message is raised only for a layout with `initial_distribution=None`; the reverse fails with pydantic `layout: Field required` (`_DensityImpl`). "(or the reverse)" removed; the different reverse-case error is named. | `e529e2d45` |

Housekeeping: `d76f5a4bd` — pre-commit autofixes (new snippet committed
executable like the other `.sh` snippets; ruff-format blank line in
`binning.py`).

## Rejections

None. (M1 implemented via the RTD path-install + documented local-build
steps rather than a `docs/requirements.txt` entry — rationale above; this
achieves the review's preferred outcome of option (a) without changing the
`docs-snippets` CI job's install behavior.)

## Final gate results (rework tip `d76f5a4bd`)

- quick suite: `174 passed, 2 xfailed, 1 xpassed, 3499 subtests passed`
  (task-02 venv; gate match)
- snippet suite: `43 passed` (42 at the rebased base + 1 new bash snippet)
- Sphinx (`docs/`, task-02 venv): `build succeeded`, 398 warnings total,
  **0 from `python_package/`**, no "Include file ... not found"; API page
  renders the class members
- Sphinx (canonical docs env: fresh py3.11 venv, `docs/requirements.txt` +
  `pip install ../lib/python`): `build succeeded`, **0 from
  `python_package/`**, API page contains the members (M1 re-verification)
- pre-commit `--all-files`: all 21 hooks passed
  (`TASK-02-REVIEW.md` non-ASCII content is excluded by the inherited
  `^TASK-.*\.md$` require-ascii exclusion — verified)
- dry-run harness `share/ci/docs_snippets_profile_check.sh` (reworked
  task-01): `profile check OK`
- `compiling/` and `end_to_end/` marker tests: not run, per instructions

## Note for the PR description

The docs build now installs the package (RTD path install + documented
local step), so the API reference page renders in the canonical docs
environments; a reviewer building per `docs/requirements.txt` plus the
documented install step will see the populated page.
