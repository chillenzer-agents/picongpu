# Task 11 — Running PIConGPU via LEXIS / the EuroHPC Federation Platform (EFP)

**Status:** exploratory draft (design note + draft implementation)
**Branch:** `task-11-efp-lexis-config` (based on `dev` @ b4e4ca5b2)
**Date:** 2026-08-29

---

## 1. Context: what "run via lexis and EFP" means

The **EuroHPC Federation Platform (EFP)** federates the EuroHPC JU hosting
entities behind one AAI login, a shared software catalogue, data movement and
**workflows across systems**. Workflow execution is provided by the
**LEXIS Platform** (`workflows.my-eurohpc.eu`): the user uploads a **job
script** (in the *target system's* batch dialect) or an **Apptainer
container**, creates a workflow (cluster/partition selection within the
project allocation, input/output **dataset staging**), and starts an
execution; the LEXIS HEAppE middleware submits the HPC job to the target
system's scheduler, stages input datasets into `/input` relative to the job
execution context, and stages output datasets back.

For PIConGPU this means: make a simulation submittable through EFP
Workflows. PIConGPU already has the machinery for machine-dependent
submission:

- **TBG** (`bin/tbg`) renders a `.tpl` (with `.TBG_*` computation lines and
  `!var` substitution) into `tbg/submit.start` and runs `$submit_command
  tbg/submit.start` (bin/tbg:520-522).
- **Presets** under `etc/picongpu/<system>/` (a `*.profile.example` +
  `.tpl` files) select `TBG_SUBMIT`/`TBG_TPLFILE`.
- The **PyPIConGPU** `RCParams`/`picongpurc.toml` preset mechanism parses the
  profile into defaults (`lib/python/picongpu/_rc_params.py:49-78`) and
  `generate()` copies the preset dir into the setup
  (`lib/python/picongpu/pypicongpu/runner.py:412-413`); `TBGFlags`
  (`runner.py:132-163`) carries `submit_system`/`template_file`/
  `overwrite_vars` into the CWL workflow
  (`lib/python/picongpu/templates/workflow/`).

## 2. Design note: submission paths (comparison + trade-offs)

### (a) Job script in the target system's batch dialect — **RECOMMENDED (primary)**

TBG preset `etc/picongpu/efp-<system>/` whose `.tpl` is a **self-contained**
job script in the target system's batch dialect (SLURM for JSC-family
systems). The rendered `tbg/submit.start` is uploaded to EFP Workflows (Data
Management → Job Scripts) with the target system selected; the TBG `input/`
directory is uploaded as the input dataset.

- **Pros**
  - Reuses the entire existing TBG/preset/PyPIConGPU machinery: **zero
    runner changes** (verified, see §5).
  - The job script is portable text; per-run overrides (queue, account,
    wall time) keep working through `tbg -o` / `TBGFlags.overwrite_vars`
    without new machinery.
  - One preset per EFP target system matches the existing
    `etc/picongpu/<system>-<institute>/` convention and documents the
    system's dialect/resource parameters in one place.
  - Works with EFP's *interactive* access mode as well: the same preset can
    submit `sbatch` from a JUPITER interactive shell.
- **Cons**
  - Requires a **pre-built binary** for the target architecture
    (cross-compiled on the laptop or built on an interactive node); the
    binary + runtime libs travel inside the input dataset.
  - The final upload/workflow/execution step is not automated in this draft
    (manual UI, ~5 minutes; automatable via Py4Lexis, path (c)).
  - A new preset is needed per EFP target system (mitigated: copy the
    pattern; only the batch dialect + resource parameters differ).

### (b) Apptainer/SIF container — **fallback (documented, not built)**

Package `picongpu` + runtime dependencies into an Apptainer-compatible
image (build PIConGPU inside a CUDA/ROCm base image, e.g.
`FROM docker://nvidia/cuda:12.x-devel` + PIConGPU deps + `pic-build`),
upload it to EFP (Data Management → Containers) and run it either through
the container workflow type or a thin job script
(`apptainer exec --bind ... image /picongpu/bin/picongpu ...`).

- **Pros**
  - Fully reproducible environment; no dependency on the target system's
    module stack; one artifact covers many systems *of the same GPU
    architecture*.
  - Matches EFP's "shared software catalogue" vision.
- **Cons**
  - One image per GPU architecture (CUDA builds are arch-specific);
    multi-GB uploads.
  - GPU pass-through with Apptainer (`--gpus`) must be supported on the
    target system; PIConGPU's CUDA/HIP specifics (e.g. UCX workarounds in
    the templates) still have to be expressed in the container job script.
  - More moving parts (image build/rebuild on every PIConGPU change) for
    the target "laptop flow".
  - **Verdict:** keep as fallback for systems where the module stack is
    fragile or where the same environment must run on several EFP systems;
    the recipe is documented in the EFP page, building the SIF is out of
    scope for this draft.

### (c) Py4Lexis programmatic submission — **follow-up, not implemented**

Drive upload (job script + datasets), workflow creation and execution
creation from the laptop via the LEXIS API/CLI (`Py4Lexis`).

- **Pros**
  - True "run the PICMI script and it handles the rest", including the
    platform part; no manual UI steps; scriptable parameter sweeps across
    EFP systems.
- **Cons**
  - New dependency + credentials (LEXIS platform config, access tokens) in
    the runner's environment; the API surface and EFP project/resource
    naming are platform-specific and still evolving.
  - Would need a new CWL step or an external wrapper behind a new
    `submit_system` value; more code to keep green.
  - **Verdict:** not pursued in this draft, but the design is
    *compatible*: the artifacts of path (a) (rendered job script + input
    dataset) are exactly Py4Lexis's inputs, so this is a drop-in
    extension later.

### (d) How the existing CWL runner drives the chosen path

**No runner changes were needed** (the requirement's ideal). The laptop
flow splits cleanly at the submission boundary:

1. `sim.write_input_file("setup")` (or `Runner.generate()`) — copies the
   `efp-<system>` preset into the setup, renders `N.cfg` and the bare
   profile. Driven by `preset = "efp-<system>"` in `picongpurc.toml` or
   `RCParams(preset=...)`.
2. `pic-build` — build the binary for the target architecture.
3. `tbg -c etc/picongpu/N.cfg [-t <tpl>] <dest>` — renders the self-contained
   job script (preset defaults from the profile; `-t`/`-o` for
   overrides). *No `-s` → tbg renders only and does not submit*, which is
   exactly what a laptop without a local scheduler wants.
4. EFP upload/execution (manual in this draft; Py4Lexis later).

The CWL `run()` path (steps build → prepare_submission → submit) is left
untouched: with an EFP preset it still works for *local* execution
(`submit_system="bash"` on a matching local machine), because the template
degrades gracefully (the `TBG_dstPath="$(pwd)"` line is rewritten by the
generated `submit.sh`'s `sed` exactly like `TBG_dstPath="!TBG_dstPath"` —
verified in §5).

## 3. Configurability options (compared)

| Option | Verdict |
|---|---|
| **Preset per system** `etc/picongpu/efp-<system>/` | **Chosen.** The batch *dialect* (directives, launchers, GPU allocation, UCX workarounds) genuinely differs per system, so a per-system template is required anyway; the preset mechanism already provides per-system selection via `picongpurc.toml`/`RCParams`/`TBGFlags` with zero new machinery. |
| Single `efp` preset with the system as a `.TBG_*` variable | Rejected. It would still need per-system template fragments (the dialect differs), i.e. the per-system split appears inside one preset, but with worse discoverability (`preset_dir`/`generate()` rely on the preset dir name) and no clean `preset = "efp-<system>"` selection. |
| `picongpurc.toml` vs Python args | Both supported, as with all presets: `preset = "efp-<system>"` in `picongpurc.toml` (laptop flow) or `RCParams(preset=...)` / `TBGFlags(submit_system=..., template_file=..., overwrite_vars=...)` programmatically. |

**Per-run overrides** (queue/partition, account, wall time, ...) work
through the existing `-o`/`overwrite_vars` mechanism: the overwritable
template variables are the `.TBG_*` computation lines (`TBG_queue`,
`TBG_nameProject`, `TBG_wallTime`, `TBG_memPerDevice`, ...), e.g.
`tbg -o "TBG_queue=debug TBG_wallTime=01:00:00"`. Verified in §5.

Discovered pre-existing issue (not fixed, out of scope): the Python
interface exposes the same mechanism as `TBGFlags(overwrite_vars=[...])`
(validation alias `o`, mirroring tbg's `-o`), but the CWL workflow
declares `run_overwrite_vars` as `string?` while `model_dump` emits a JSON
array, so cwltool rejects `picongpu_run(o=[...])` ("value is a list,
expected null or string"). This predates the EFP work (both the list field
and the string CWL input date from the original flag plumbing) and is
independent of the EFP flow, which renders via `tbg` directly. Suggested
fix for the runner owners (task 09's area): serialize the list to a
space-joined string (tbg's `-o` takes one string) or widen the CWL input
to `Array<string>`.

## 4. Staging compatibility (EFP `/input` ↔ PIConGPU `setup_dir`/`simOutput`)

EFP stages input datasets into `/input` **relative to the HPC job execution
context** (the job's working directory) and stages output datasets out of
the same context. PIConGPU's TBG destination layout is:

```
<dest>/            <- job execution context (cwd)
  input/           <- binary (bin/picongpu) + runtime config (etc/...)
    bin/picongpu
    etc/N.param ...
    picongpu.profile   (shipped by the documented packaging step)
  tbg/submit.start     <- rendered job script (uploaded as the EFP job script)
  simOutput/         <- created by the job; PIConGPU output + stdout symlink
```

The mapping is therefore **direct**:

- **Input dataset** = the TBG `input/` directory → staged to `./input` =
  exactly where the job script expects `input/bin/picongpu` and
  `input/etc`. (The `tbg/` dir may be included for reproducibility; the job
  script does not need it at run time.)
- **Output dataset** = `simOutput/` (enable output dataset staging on the
  workflow).
- `TBG_dstPath` semantics: the template pins it with
  `TBG_dstPath="$(pwd)"` (the job's cwd) instead of a hard-coded local path,
  and drops `#SBATCH --chdir` (a local absolute path would not exist on the
  target system). When the script runs through the PyPIConGPU CWL flow
  instead, the generated `submit.sh` rewrites the same line to the CWL
  workdir, so both modes work.
- `link_results.sh`/`submission_information.txt` are local-submission
  conveniences of the CWL runner; under EFP, job id/logs/outputs are managed
  in the EFP Workflows UI, so they are not needed.

## 5. What was drafted (implementation)

All in `etc/picongpu/efp-jupiter-jsc/` (JUPITER/JSC chosen as the
representative EFP target system: JSC is an EFP hosting entity, JUPITER is
its current GPU system, and `jupiter-jsc/` is the closest existing
template):

- `efp_picongpu.profile.example` — adapted from `jupiter-jsc/
  gh200_picongpu.profile.example`: same module stack, `jutil`
  project/account auto-detection, `PIC_BACKEND=cuda:90`,
  `getDevice()`/`getNode()`; sets `TBG_SUBMIT=sbatch` and
  `TBG_TPLFILE=etc/picongpu/efp-jupiter-jsc/gh200_efp.tpl`.
- `gh200_efp.tpl` — self-contained EFP job script template:
  - same `#SBATCH` resource requests and `.TBG_*` computation lines as
    `jupiter-jsc/gh200.tpl` (4 GH200/node, 72 cores blocked per GPU, UCX
    workarounds, `srun --threads-per-core=1 ... --mpiDirect` launch);
  - **no `#SBATCH --chdir`**, pins the working directory via
    `TBG_dstPath="$(pwd)"`;
  - sources `input/picongpu.profile` (the bare profile shipped with the
    input dataset) when present, falling back to `!TBG_profile` (the user's
    profile) otherwise;
  - sanity-checks `input/bin/picongpu` with a clear error.
- **Runner changes: none.** `lib/python/picongpu/pypicongpu/runner.py` and
  the CWL templates are untouched.

Note on preset naming: the profile file is named
`efp_picongpu.profile.example` (not `gh200_...`) deliberately — a
same-named file would make the pre-existing `jupiter-jsc/gh200_picongpu`
preset selection ambiguous via the substring matcher in
`_rc_params._preset_path` (regression found and fixed during development).

Docs + changelog:

- `docs/source/pypicongpu/running_on_efp.rst` — "Running on the EuroHPC
  Federation Platform (EFP)" page (paths + trade-offs, laptop workflow,
  staging, configurability, pending verification), added to the PyPIConGPU
  toctree (`docs/source/index.rst`).
- `docs/source/install/profile.rst` — "EFP (JUPITER, JSC)" section with
  `literalinclude` of the profile (`docs/source/install/profiles` is a
  symlink to `etc/picongpu`, so no mirroring was needed).
- `docs/source/usage/tbg.rst` — short EFP note under the batch system
  examples.
- `CHANGELOG.md` — 0.9.0 entry (features + documentation).

Tests (`lib/python/test/picongpu/quick/pypicongpu/test_efp_preset.py`, 7
tests):

- preset discovery + unambiguous resolution (incl. that `jupiter-jsc/
  gh200_picongpu` is not affected);
- submission defaults parsed from the profile (`tbg_submit=sbatch`,
  `tbg_tpl_file=...gh200_efp.tpl`, `pic_backend=cuda:90`);
- `tbg` smoke-render of the template: exit 0, no unresolved `!var`,
  `TBG_dstPath="$(pwd)"`, no `--chdir`, dataset profile path, correct
  SLURM resource lines;
- per-run overrides through `tbg -o`;
- `Runner.generate()` with the preset: preset dir copied into the setup,
  bare profile rendered with the EFP template, CWL inputs carry
  `run_submit_system=sbatch` / `run_template_file=...gh200_efp.tpl`.

## 6. What was verified locally (short feedback loop)

1. **TBG render** of `gh200_efp.tpl` with a minimal cfg: valid job script,
   no unresolved variables, `bash -n` syntax OK.
2. **Simulated EFP execution context** (laptop): staged a fake `input/`
   (stub `picongpu` + fake profile) into a rendered TBG dir, executed
   `tbg/submit.start` with a stub `srun` on `PATH` → profile sourced from
   the dataset, `simOutput/` created with the `output` symlink,
   `picongpu` launched with the full parameter list; exit 0. Missing
   `input/` → clear error, exit 1.
3. **`-o` overrides**: `TBG_queue=debug`, `TBG_wallTime=01:00:00` reflected
   in the rendered `#SBATCH` lines.
4. **CWL compatibility**: the generated `submit.sh`'s `sed` rewrite
   (`TBG_dstPath=...` / `--chdir=...`) behaves correctly with the new
   template (line rewritten to the CWL workdir; `--chdir` a no-op).
5. **Full laptop flow E2E** (without cluster): PICMI script +
   `picongpurc.toml` (`preset = "efp-jupiter-jsc"`) →
   `write_input_file()` → setup contains the preset + rendered `N.cfg` +
   bare profile; `tbg` from the setup renders the job script and assembles
   `input/`; with the bare profile copied to `input/picongpu.profile`, the
   simulated run launches `picongpu` with the real generated parameters
   (`-d 1 1 1 -g 32 32 32 -s 10 --periodic 0 0 0 ...`).
   (Expected non-fatal `jutil`/`module: command not found` noise on the
   laptop — both exist on JUPITER nodes; the profile has no `set -e`.)
6. **Preset selection**: `RCParams(preset="efp-jupiter-jsc")`, short name
   `"efp"`, and `picongpurc.toml`-based selection all resolve; profile
   rendering requires `author`/`email`/`pic_libs` as with all presets.
7. **Test gate:** `pytest quick/` → **181 passed, 2 xfailed, 1 xpassed**
   (baseline 174/2/1 + 7 new tests). `pre-commit run --all-files` → all
   hooks passed.
8. **Docs:** RST of the new/changed pages parses (Sphinx directives check
   via docutils; full Sphinx build not run here — it requires Doxygen/
   breathe tooling).

## 7. Pending verification (requires EFP access — OUT OF SCOPE here)

Plan for the EFP smoke run (JUPITER assumed; adjust per confirmed target):

1. On the laptop: steps 1–5 of §5/§6 with a real build
   (`pic-build`, `PIC_BACKEND=cuda:90`).
2. EFP Workflows (`workflows.my-eurohpc.eu`, AAI login):
   - upload `tbg/submit.start` as a job script (target system: JUPITER);
   - upload the TBG `input/` directory as a project dataset;
   - create a workflow from the job script: cluster/partition within the
     allocation, **input dataset staging** enabled, **output dataset
     staging** on `simOutput`;
   - create an execution; watch the workflow graph.
3. Success criteria: graph completes; HPC job logs show PIConGPU
   initializing and iterating; `simOutput/` (openPMD output, stdout)
   staged back as the output dataset.
4. Also confirm (see §8): execution-context cwd, `#SBATCH` pass-through,
   `jutil`/modules on compute nodes, account/QoS requirements.

## 8. Open EFP specifics the requester must confirm

1. **Target system(s)** covered by the allocation and their batch dialects
   (JUPITER/SLURM assumed for the draft; LUMI = SLURM+CPE, Leonardo =
   SLURM, Discoverer = SLURM, ... — each needs its own
   `efp-<system>` preset following the pattern).
2. **EFP project/account names**: the JSC project/budget account the EFP
   allocation is charged to (profile `proj`/`account`, auto via `jutil` on
   JSC or set manually), and any required **QoS**.
3. **Job execution context semantics** on the target system: working
   directory of the HPC job, where `/input` is staged, whether `#SBATCH`
   directives in the uploaded script are passed through to the scheduler
   unmodified (assumed yes for SLURM systems).
4. **Availability of `jutil` and the module system on compute nodes** (the
   shipped profile uses them; if unavailable, the profile must be trimmed
   for the EFP flow).
5. **Dataset size limits / packaging**: whether the TBG `input/` directory
   (a few hundred MB with binary + libs) is acceptable as a single dataset,
   and whether tarring is required by the portal.
6. Whether to invest in the **container fallback** (SIF build) and/or
   **Py4Lexis automation** as follow-up tasks.

## 9. Interaction with parallel tasks (conflict note)

- **Task 05** (TBG_dstPath/`.cwl_cache` semantics): my template keeps the
  `TBG_dstPath=` line format that `submit.sh`'s `sed` rewrites, and I did
  not touch `runner.py`, `submit.cwl`, or the `.cwl_cache` handling — no
  interaction expected.
- **Task 09** (runner.py stages rework): the draft deliberately keeps
  **zero** runner changes; if task 09's rework changes how the setup/stages
  are assembled, the only coupling point is that the EFP preset dir must
  still be copied into the setup and the bare profile still generated at
  `workflow/scripts/picongpu.profile` (both are core `generate()`
  behaviors, and the quick test
  `test_efp_preset_generate_copies_preset_and_drives_flags` pins them).
- All assumptions are based on `dev` @ b4e4ca5b2.

## 10. Risks

- **EFP platform behavior unverified**: execution-context cwd, `#SBATCH`
  pass-through, and staging paths are from the EFP/LEXIS documentation,
  not from a live run (§7/§8).
- **Binary portability**: the laptop-built binary must match the target
  system's GPU architecture *and* its runtime libraries; if the profile's
  module-provided libraries (openPMD, Blosc, ...) differ from what the
  laptop build linked against, the staged binary may not load — the
  documented mitigation is to build on an EFP interactive node.
- **JUPITER specifics** (partition name `booster`, 4 GH200/node, 72
  cores/GPU, UCX workarounds) are copied from the current `jupiter-jsc`
  preset and may drift with system updates.
- **Docs build** was not run end-to-end locally (Doxygen/breathe tooling
  not available in this environment); RST syntax was checked only.
