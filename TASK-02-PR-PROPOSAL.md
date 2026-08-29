# Task 02 — PR proposal: expand the PICMI (Python package) documentation

**Status:** ready for review
**Branch:** `task-02-docs-expand` (12 commits on top of `6d9f158ab`)
**Base branch:** `picmi-docs` (after task 01's snippet system has landed; the
branch was built on the current tip of the PR work, which already contains the
tested-snippet system)
**Target:** PR against `picmi-docs`, per the clarified branching workflow
(requester 2026-08-29). Fork remote: `origin` = `chillenzer/picongpu`.

> Push handoff (not executed here):
> ```
> git push origin task-02-docs-expand
> ```
> then open the PR against `picmi-docs`.

## Proposed PR title

> [WIP] PICMI documentation: correctness pass + expanded topics (PR 5731 task 02)

## Proposed PR body

### What this PR does

Task 02 of PR 5731 ("find missing details and expand the documentation"):
audit every page of `docs/source/python_package/` against the post-PR-5639
code, fix every factual discrepancy, and add the missing topics — one commit
per work item, code moved into the tested-snippet system from task 01.

Audience rule honored throughout: new users are onboarded purely on the
Python interface; C++ cross-references appear only in deep-dive sections
(interactions, HPC submission, troubleshooting), never in the quickstart or
beginner pages.

### Commits (one per work item)

| # | Commit | Work item |
|---|--------|-----------|
| 1 | `46c0f3f38` | **Correctness pass** (priority 0): fix stale names/defaults/workflows in `foundations/` and `quickstart` vs. the post-5639 code (preset handling, `picongpu_run()`/`step()` semantics, `write_input_file()`, metadata outputs, dependency list) |
| 2 | `06e11b392` | **Quickstart** expanded: install → first `Simulation` → run, Python-only |
| 3 | `c993fa0d7` | **Environment/preset configuration**: `picongpurc.toml`, preset discovery from `etc/picongpu/*.profile*`, setting up a system without a preset, `tbg_submit`/`tbg_tpl_file` |
| 4 | `f28c3c974` | **Defining a simulation (core PICMI)**: grids/solvers, lasers, species, distributions, layouts — with tested snippets |
| 5 | `a9504cf39` | **Running & workflow internals**: the 4 CWL steps, run-dir layout (`bin/`, `tbg/`, `link_results.sh`, `submission_information.txt`, `metadata/`), RO-Crate, resubmission/restart reality (cwltool job cache; `step()` is full-run only — todo at `picmi/simulation.py:365`) |
| 6 | `58e7624b9` | **Diagnostics/plugins**: one page per diagnostic under `selected_topics/` — `time_steps`, `phase_space`, `energy_histogram`, `macro_particle_count`, `openpmd` (ParticleDump / NativeFieldDump / DerivedFieldDump), `binning`, `radiation`, `checkpoint` — with 8 tested snippets and verified output locations |
| 7 | `f34a2f167` | **Interactions** (deep-dive): field ionization (ADK/BSI/Keldysh), synchrotron, collisions — with tested snippet; documents `picongpu_interaction` constructor path and why `add_interaction()` is not usable |
| 8 | `d1eb0c977` | **HPC submission specifics** (deep-dive): `tbg` options, template/`.tpl` mechanics, two-stage prepare→submit, job IDs, `link_results.sh`, `submission_information.txt` — with a tested `manage_submission.sh` snippet |
| 9 | `4966fc8f3` | **Troubleshooting / common failure modes**: verified error strings (grid divisibility, missing template variables, dirty-reset policy, distribution/layout, destination-in-use, cyclic dependencies, missing profile) + tested `validate_before_submit.py` |
| 10 | `7bb6e5430` | **Verification guide for users**: clean-install verification, `--help` smoke checks, unitless tests, end-to-end expectations — with tested `verify_install.sh` |
| 11 | `90a7f204b` | Re-evaluation fix: `picongpu_n_gpus` is a **grid** parameter taking a list (bare int is rejected by typeguard); corrected in `defining_simulation` |
| 12 | `8bd557950` | **API page in sync**: `api/index.rst` now generated via `automodule:: picongpu.picmi` (added `sphinx.ext.autodoc` to `conf.py`) |

Diff: 38 files changed, ~2756 insertions, 35 deletions — all under
`docs/source/python_package/` except the one-line `conf.py` extension add.

### Verification (all green)

- **Sphinx** (fresh build of `docs/`): exit 0, `build succeeded`; **zero
  warnings from `python_package/`**, no "Include file ... not found".
  (398 total build warnings are pre-existing and live in other doc trees.)
- **Snippet suite** (`docs/source/python_package/snippets`, task-01 system):
  **42 passed** (25 at baseline) — every new snippet actually runs; bash
  snippets pass `bash -n`.
- **Package tests**: `lib/python/test/picongpu quick/` →
  `174 passed, 2 xfailed, 1 xpassed` (baseline match; the SHACL
  stderr noise is pre-existing).
- **pre-commit** `--all-files`: all passed.

### Known limitations / follow-ups (flag for the PR description)

1. **Code bugs documented as "not currently usable"** (out of docs scope;
   each page states the exact failure):
   - All collision classes (`ConstLogCollision`, `DynamicLogCollision`,
     `Collision`, `CollisionalPhysicsSetup`): `_serialize_functor` calls
     `get_rendering_context()` on a plain pydantic `BaseModel`
     (AttributeError at generation).
   - `ThomasFermi` ionization: pypicongpu rendering is missing
     `ionization_electron_species`.
   - `PlaneWaveLaser` / `TWTSLaser`: rendering path incomplete.
   These deserve a separate bug-fix task/PR.
2. **`picrc-builder` does not exist in this branch** (no module, no script,
   no entry point) — the task's ground-truth list mentions it, but there is
   nothing to document; the docs cover preset configuration via
   `picongpurc.toml` only.
3. **autoapi is broken in this environment** ("Unable to read file" for all
   `pypicongpu` sources; the pre-existing toctree ref
   `pypicongpu/autoapi/...` already warned before this PR). The API page now
   uses plain `autodoc` on the public `picongpu.picmi` package instead, which
   is stable and renders.
4. **10 pre-existing RST warnings** now surface from malformed docstrings in
   `lib/python/picongpu/picmi/` (GaussianLaser, DispersivePulseLaser,
   TWTSLaser, AnalyticDistribution, UniformDistribution) via autodoc. They
   are attributed to `lib/python`, not `python_package`; build still
   succeeds. Fixing the docstrings is a small follow-up.
5. `picongpu_n_gpus` accepts only a **list** (`[N]` for y-axis,
   `[Nx, Ny, Nz]` full grid) — documented, and worth a friendlier error in
   the code.

### Reviewer checklist (request per task spec)

- [ ] Maintain pass on `foundations/` for post-5639 API accuracy
- [ ] Spot-check the new `selected_topics/` pages against a real run
- [ ] Confirm the "not usable" code-bug notes are still accurate at merge
- [ ] Approve `conf.py` extension add (`sphinx.ext.autodoc`)
