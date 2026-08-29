# Task 01  -  PR Proposal: convert `python_package` doc snippets to tested code

**Branch:** `task-01-docs-tested-snippets` (based on `85365feb2`, tip of `origin/picmi-docs`)
**Pushed to:** `origin` (fork `chillenzer/picongpu`)
**PR target:** `picmi-docs` (NOT `dev`)  -  see branching workflow in `/workspace/tasks/01-pr5731-snippets-to-tested-code.md`
**Do NOT commit this file**  -  it is the handover document, not part of the PR.

---

## Suggested PR title

```
docs: render python_package snippets from CI-tested scripts
```

## Suggested PR description

> Part of PR 5731 ("[WIP] PICMI documentation").
>
> Converts every code snippet in `docs/source/python_package/` from untested
> inline text into a real script under `docs/source/python_package/snippets/`
> that is rendered into the docs via `literalinclude` and executed in CI
> (new `docs-snippets` GitLab job).
>
> ### What changed
>
> - **New snippet system** (`docs/source/python_package/snippets/`):
>   - 9 Python snippets + 15 bash snippets, one file per documented snippet.
>   - `run_snippet.py`: execution harness; `--no-run` replaces the build/submit
>     step of `simulation.run()` with a no-op (and emulates the
>     `EnergyHistogram` output where a snippet reads results), so CI never
>     compiles or submits jobs.
>   - `test_snippets.py`: pytest suite that executes every Python snippet in an
>     isolated environment (fresh cwd, isolated `HOME`, `PIC_RC` pointing at a
>     non-existent file) and asserts exit code 0 plus per-snippet expected
>     artifacts (files, file content, stdout/stderr). Bash snippets are
>     syntax-checked with `bash -n`.
>   - Whole-file includes by default; semantic `BEGIN-<NAME>`/`END-<NAME>`
>     markers only where one tested file feeds several doc sections
>     (`lwfa_example.py`, `multiple_simulations.py`).
>   - `docs/source/conf.py`: the snippet directory is excluded from being
>     collected as a Sphinx document.
> - **Doc rewrites** (`foundations/{configuring_environment,defining_simulation,running_simulation}.rst`):
>   all inline code blocks replaced by `literalinclude` of the tested scripts;
>   non-executable excerpts (TOML values, search-order lists, one-liners) stay inline.
> - **Correctness fixes** found while checking the snippets against the actual
>   package (the WIP docs described an interface that does not exist):
>   - `picrc-builder` tool does not exist -> section rewritten as
>     "The `.picongpurc.toml` File" (manual TOML) with the real search order
>     (incl. `PIC_RC` pointing at a directory).
>   - `picongpu.get_available_presets()` does not exist -> replaced by listing
>     `etc/picongpu` of the installed package.
>   - `rc_params.set_temporarily('dirty_reset_policy', 'ignore')` is a
>     `TypeError` (keyword-only signature) -> `set_temporarily(dirty_reset_policy="ignore")`.
>   - `MultiSpecies` is not supported by the PIConGPU frontend -> the LWFA
>     example uses two individual `Species` sharing a `GaussianDistribution`.
>   - `simulation.model_dump()` does not exist on the PICMI `Simulation` and
>     the PyPIConGPU representation cannot be round-tripped through
>     `model_validate(model_dump())` (e.g. the radiation lambda) -> the
>     (de-)serialization section now documents the PyPIConGPU dump (which is
>     what `metadata/pypicongpu_runner.json` actually contains) and
>     pydantic round-tripping of individual PICMI elements (`Species`).
>   - `metadata/picmi_simulation.json` does not exist ->
>     `metadata/pypicongpu_runner.json`.
>   - `picongpu_laser=[...]` -> `picongpu_lasers=[...]`.
>   - `GaussianLaser` requires `centroid_position` -> added (chosen so the
>     `pulse_init` warning does not trigger).
>   - Post-processing pseudocode (`EnergyHistogram(...).get(...)`) -> the real
>     API `picongpu.extra.plugins.data.EnergyHistogramData(run_dir).get(...)`
>     (energies in keV); the optimizer snippet fixes
>     `scipy.optimize.minimize` usage (`options={"xatol": ...}`) and the
>     re-generation crash on an existing setup dir.
> - **Broken internal links** in `quickstart.rst`, `foundations/index.rst`,
>   `selected_topics/index.rst`: `Link`_ hyperlinks replaced by `:ref:`
>   cross-references (autosectionlabel, document-prefixed); fixed a typo
>   ("exapnd").
> - **CI**: new `docs-snippets` job in `.gitlab-ci.yml` (stage `test`, reuses
>   the pypicongpu container `alpaka-ci-ubuntu24.04-gcc-pic:4.0`, python 3.11):
>   1. sources `share/ci/install/pypicongpu.sh` with the new
>      `PYPICONGPU_SKIP_QUICK_TEST=1` guard (skips writing `/.picongpurc.toml`
>       -  the snippet tests need a pristine `rc_params` state  -  and skips the
>      quick tests, which are covered by the pypicongpu jobs);
>   2. installs `docs/requirements.txt` and `doxygen`;
>   3. smoke-checks `pic-build`/`pic-configure`/`tbg --help`;
>   4. runs the snippet test suite;
>   5. generates a minimal input set with the `bash` preset and sources its
>      `workflow/scripts/picongpu.profile` (checks `PIC_BACKEND`/`PICSRC`,
>      mirroring `legacy_workflow.sh`  -  no compilation);
>   6. builds the docs (`doxygen` + `sphinx-build -b html`) and **explicitly
>      fails** on "Include file ... not found" (a missing snippet file is only
>      a Sphinx warning otherwise) and on a failed build.
>
> ### Verification (local, branch tip)
>
> - snippet suite: `25 passed` (9 python executions incl. `--no-run`
>   generation checks + 16 bash `bash -n`)
> - package gate: `pytest lib/python/test/picongpu/quick/ -q` ->
>   `174 passed, 2 xfailed, 1 xpassed` (unchanged vs. base)
> - docs: clean `sphinx-build -b html` succeeds, **0 warnings in
>   `python_package/`**, no snippet-inclusion failures, no marker lines
>   rendered into the HTML
> - `pre-commit run --all-files`: all hooks pass
>
> ### Notes / follow-ups
>
> - The PyPIConGPU JSON round-trip limitation is a package issue, not a docs
>   issue; it should get its own tracking (see also task 06/07 in the
>   documentation plan).
> - The optimization snippet needs a system-specific wait for the submitted
>   job in real use; this is documented in the text (the package does not
>   provide it).
> - The 381 pre-existing Sphinx warnings elsewhere in the docs are out of
>   scope.
> - Task 02 ("expand documentation") builds on top of this branch: new
>   pages should follow the same convention (snippet file + literalinclude).

---

## Verification log (this machine)

| Gate | Command | Result |
|---|---|---|
| Snippet suite | `python -m pytest docs/source/python_package/snippets -q -p no:cacheprovider` (from repo root) | **25 passed** in ~18 s |
| Package quick gate | `cd lib/python/test/picongpu && python -m pytest quick/ -q` | **174 passed, 2 xfailed, 1 xpassed** (== base `85365feb2`) |
| Sphinx (clean) | `cd docs && doxygen && sphinx-build -b html source build/html` | **build succeeded**, 381 warnings (all pre-existing, none in `python_package/`), **0** "Include file ... not found" |
| Rendered HTML | `defining_simulation.html` | no `BEGIN-`/`END-` marker lines rendered |
| pre-commit | `pre-commit run --all-files` | all hooks **Passed** |
| CI job dry-run | profile-check block executed locally (generate 16^3 setup with `bash` preset, source profile) | `PIC_BACKEND=omp2b:native`, `PICSRC=<source tree>`  -  OK |
| `.gitlab-ci.yml` | YAML parse of the new job | OK |

## Key decisions

1. **CI image**: reuse the existing pypicongpu container
   (`alpaka-ci-ubuntu24.04-gcc-pic:4.0`, python 3.11)  -  it already provides
   `micromamba`/`pip`/the repo layout and matches the sibling pypicongpu jobs;
   `doxygen` installed via `apt` in the job (the container does not ship it).
2. **`PYPICONGPU_SKIP_QUICK_TEST`** (new env guard in
   `share/ci/install/pypicongpu.sh`): skips writing `/.picongpurc.toml` and
   the quick-test run. Both are needed: the docs snippets require a pristine
   `rc_params` state (the rc-file parent-directory search would otherwise
   pick up the CI preset file), and the quick tests are already covered by
   the pypicongpu jobs. Existing jobs are unaffected (guard is opt-in).
3. **Whole-file literalinclude by default**; markers only for
   `lwfa_example.py` (7 sections) and `multiple_simulations.py` (2 sections).
   No line numbers anywhere.
4. **`--no-run` harness** instead of compiling: snippets that call
   `simulation.run()` are executed with the run step replaced by a no-op;
   where a snippet reads results, the harness emulates the
   `EnergyHistogram` output files. Fast, deterministic, no compiler needed.
5. **Explicit Sphinx failure on missing includes**: missing `literalinclude`
   files are only warnings, so the CI job greps the build log and fails on
   `Include file ... not found or reading it failed`, plus requires
   "build succeeded".

## Risks / open items

- **First real CI run** of `docs-snippets` still has to happen (container
  `apt install doxygen`, doxygen version in the ubuntu24.04 container,
  `program-output` directives in the rest of the docs running in CI  -  all
  validated locally against the same sources, but the container differs from
  this dev environment).
- `optimize_focal_position.py` regenerates setups in a loop; in a real (not
  emulated) run it would need a job-wait  -  documented, not implementable
  generically.
- Pre-existing: 381 Sphinx warnings in other parts of the docs (out of scope).

## Shared files (other tasks may touch)

- `docs/source/conf.py` (exclude_patterns entry)  -  task 02 adds more pages.
- `share/ci/install/pypicongpu.sh` (new guard)  -  used by all pypicongpu jobs.
- `.gitlab-ci.yml` (new job)  -  task 02 may add/extend docs jobs.
- `docs/source/python_package/snippets/`  -  task 02 extends this tree;
  convention is documented in `snippets/README.md`.

## Suggested commit list (to be created)

1. `docs: add tested snippet system for python_package docs`
   (`snippets/` harness + README + all snippets + `conf.py` exclude)
2. `docs: render configuring_environment from tested snippets` (+ correctness fixes)
3. `docs: render defining_simulation from tested snippets` (+ LWFA/tutorial fixes)
4. `docs: render running_simulation from tested snippets`
5. `docs: fix broken cross-references in python_package docs`
6. `ci: add docs-snippets job for python package documentation`
   (`.gitlab-ci.yml` + `pypicongpu.sh` guard)
