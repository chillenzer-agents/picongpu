# Task 11 - Running PIConGPU via LEXIS / the EuroHPC Federation Platform (EFP)

**Status:** REWORK - design note + proof-of-concept implementation
**Branch:** `task-11-efp-lexis-config` (based on `dev` @ b4e4ca5b2)
**Date:** 2026-09-01 (rework)

## 0. The corrected goal, and why this is a rework

**Goal.** Configure PICMI via `rc_params` / `picongpurc.toml` so the runner
**generates a LEXIS Workflow Definition (LWD) instead of a CWL workflow**, and
**submits it to the EFP via Py4Lexis**. This is a **large design task**; the
implementation is a **proof of concept** only. Patching features into Py4Lexis
(including upstreaming them) is in scope.

**Why the rework.** The round-1 branch implemented a **JUPITER job-script
preset** as the *primary* submission path and demoted Py4Lexis to "follow-up,
not implemented" (the codebase showed ~55 jupiter/preset mentions vs ~6
Py4Lexis). That is the **inverse** of the actual goal. The rework makes the
**lexis-workflow + Py4Lexis** path the primary and **retains** the job-script
preset as a documented *fallback* (it is a valid, working TBG-based path).

### The two submission paths (corrected prioritization)

- **(A) LEXIS Workflow Definition (LWD) + Py4Lexis** - **PRIMARY (this rework).**
  Generate an LWD YAML from the PICMI config and submit it through Py4Lexis
  (create workflow -> execute -> poll), using EFP dataset staging for
  inputs/outputs.
- **(B) Job-script preset** (TBG, target-system batch dialect) - **FALLBACK**
  (round 1, retained). The rendered `tbg/submit.start` is uploaded to EFP
  Workflows by hand. See appendix (section 10).
- **(C) Apptainer/SIF container** - **FALLBACK** (documented, not built).

---

## 1. Research: LEXIS + Py4Lexis (verified against source, 2026-09-01)

Sources: `docs.lexis.tech` (LWD spec, workflow how-to, API endpoints, Py4Lexis)
and the Py4Lexis / `efp` client sources
(`opencode.it4i.eu/lexis-platform/clients/{py4lexis,efp}`).

### 1.1 LEXIS Platform
Federates EuroHPC hosting entities behind one **AAI login**, a shared software
catalogue, **DDI** (Distributed Data Infrastructure = dataset upload/download/
staging), and **workflow execution** across systems. Workflows run on the
**LEXIS Platform** (Airflow + the LEXIS provider / plugin).

### 1.2 LEXIS Workflow Definition (LWD)
A **YAML** format for workflows with job dependencies, data flow, and resource
requirements. Structure (from the official spec):

```yaml
id: <workflow id>
desc: <human description>
project_shortname: <LEXIS project>
jobs:
  <job_name>:
    requirements:
      command_template_name: <registered command template>
      locations:
        - location_name: <cluster>
          location_resource: <resource>     # optional
      walltime_limit: <seconds>
      max_cores: <n>                         # optional
      policy: preferred                      # preferred | required
      template_parameters: {k: v}            # optional
    data_inputs:
      - source: ddi://~/... | job://<job>/<name>
        target: <local dir>/
    data_outputs:
      - source: <local dir>/
        target: ddi://~                      # optional (defaults to job storage)
        metadata:
          $name: <internal ref>              # job-to-job only, NOT in dataset metadata
          title: <human title>
          access: project                    # public | project | private (public => datacite)
    depends_on: [<job>]                      # optional explicit deps
metadata:
  catchup: false
```

Key facts:
- **Data sources:** `ddi://` (external DDI dataset) or `job://<job>/<$name>`
  (output of another job). **Data flow creates implicit dependencies.**
- **`$name`** is an internal job-to-job reference (not in the final dataset
  metadata); non-`$` properties become dataset metadata. `public` access
  requires a `datacite` block.
- **Creation flow:** (1) create the workflow (from an uploaded job script, a
  container, or **a custom LWD - upload the YAML or submit it via the API**);
  (2) the LWD is **translated to an Airflow DAG** (`LexisWorkflowTranslator`);
  (3) execute it (an execution = one run; data inputs/outputs + requirements
  are specified per execution).
- HPC jobs run under a **command template** (per project, per computing
  resource); input datasets are staged to `/input` relative to the job cwd.

### 1.3 Py4Lexis (current capabilities, from source)
- **Auth:** Keycloak (login via the LEXIS portal; `B2Access`/`MyAccessID`).
  The session carries an API base (`session.api_air`).
- **`Airflow` class** (`py4lexis.core.workflows.airflow`) can:
  `get_workflows_list`, `get_workflow_info`, `get_workflow_details`,
  `get_workflow_params`, **`execute_workflow`** (POST `/dags/{id}/dagRuns`),
  `get_workflow_states`, `get_single_workflow_state`.
- **DDI** (dataset upload/download/list) and **iRODS** managers are also
  provided.
- **GAP:** there is **no method to CREATE a workflow from an LWD**. Py4Lexis
  can list/info/**execute**/**check-state** existing workflows but not create
  one. **This is the patch the PoC adds** (section 4).
- **`[efp]` extra:** installs a separate tiny `efp` package that just provides
  **EFP base URLs** (`AR`/`API`/`AP`) which override the session defaults
  (via `py4lexis.core.helper`), so the client points at the **EFP** instance.
- **Not on PyPI.** Install: `pip install "py4lexis[efp]" --index-url
  https://opencode.it4i.eu/api/v4/projects/107/packages/pypi/simple`.

---

## 2. Design: mapping the PIConGPU CWL pipeline onto an LWD

The current runner generates a **CWL** workflow
(`templates/workflow/workflow.cwl`): **build -> prepare_submission -> submit ->
organize_output**, orchestrated by cwltool on the laptop, where `submit` talks
to the *local* batch system. In the LEXIS model the **platform** orchestrates
and the HPC work is expressed as **LWD job nodes** with **dataset staging**.

**Primary mapping (PoC) - single HPC job node.** One LWD job `picongpu` whose
*command template* performs build + run + collect. The command template is an
**EFP-side registered** template (the "how to run"); PIConGPU only supplies the
LWD + the staged setup. This mirrors EFP's "create workflow from a job script"
model and keeps the PoC minimal and fully testable:

- **input dataset** = the PIConGPU `setup_dir` (staged from a `ddi://` source
  into `input/`);
- **output dataset** = the simulation output (staged out to `ddi://~` under the
  `[lexis].output_*` metadata).

**Two-node variant (faithful CWL mapping).** `build` -> `run`, where `build`
publishes the compiled binary as a `$name: picongpu_bin` dataset and `run`
consumes it via `job://build/picongpu_bin`. Used when a build step should be a
separate, cacheable HPC job. Selected by providing a `[lexis.build]` job.

**Staging compatibility** (carried over from the round-1 investigation, still
valid): EFP stages input datasets to `/input` relative to the job cwd and
output datasets out of the same context; PIConGPU's `simOutput/` maps directly
to the output dataset. `link_results.sh` / `submission_information.txt` are
local-submission conveniences and are not needed under EFP (the platform
manages job id/logs/outputs).

## 3. Configurability

- **`workflow_backend = "cwl" | "lexis"`** (default `"cwl"` - **no behavior
  change**) in `picongpurc.toml` / `RCParams`. When `"lexis"`,
  `Runner.generate()` additionally writes `workflow.lwd.yaml`.
- **`[lexis]` table** (RCParams is dict-backed with `extra="allow"`, so the
  table passes through as a plain dict):

  ```toml
  workflow_backend = "lexis"

  [lexis]
  project_shortname = "picongpu"
  command_template_name = "picongpu"
  location_name = "jupiter"          # target cluster
  location_resource = "gh200"        # optional
  walltime_limit = 7200
  max_cores = 64                     # optional
  input_dataset = "ddi://~/setup"    # staged PIConGPU setup
  # output_name / output_title / output_access   # optional
  ```

  A **nested** form (`[lexis.run]`, and optional `[lexis.build]`) and a
  **flat** form (the run-job keys directly under `[lexis]`) are both accepted
  by `parse_lexis_config`.

## 4. Py4Lexis gap + patch (the "patch Py4Lexis" part)

`patches/py4lexis-create-workflow.diff` adds `Airflow.create_workflow(lwd,
project)` to the Py4Lexis fork: it POSTs the LWD to the **lexis extension**
API (deriving the base from `session.api_air`, stripping the trailing `/v1`)
and returns the created workflow. The submission loop then becomes:

```
create_workflow(lwd) -> execute_workflow(dag_id, conf) -> poll get_workflow_states(dag_id)
```

**Open item (requires EFP access):** the exact lexis-extension *create*
endpoint + payload shape must be confirmed against the **live** EFP OpenAPI
(`api.lexis.tech/airflow/api/lexis/openapi`), which redirects to an internal
host and is not publicly fetchable. The patch uses a best-effort default path,
overridable via `PY4LEXIS_CREATE_WORKFLOW_PATH`. Everything up to the actual
POST (LWD generation, plan building, execute/poll calls) is implemented and
testable without EFP access.

## 5. PoC implementation (this branch)

- `lib/python/picongpu/pypicongpu/lexis_workflow.py` - the LWD generator:
  `LexisJobSpec`, `LexisWorkflowSpec` (`build_lwd` / `to_yaml`, single- and
  two-node), `parse_lexis_config`, `lwd_from_yaml`. Pure Python, no network.
- `lib/python/picongpu/pypicongpu/lexis_submit.py` - the submission driver:
  `build_submission_plan`, `submit(..., dry_run=True)` (default: no network),
  `wait_for_completion`. Py4Lexis is an **optional** dependency (imported only
  in the live path).
- `lib/python/picongpu/_rc_params.py` - `workflow_backend` default (`"cwl"`).
- `lib/python/picongpu/pypicongpu/runner.py` - `workflow_lwd_path` property,
  `generate_lexis_workflow()`, and the `generate()` hook (emits the LWD when
  `workflow_backend == "lexis"`; the CWL is still generated - non-destructive).
- `patches/py4lexis-create-workflow.diff` - the Py4Lexis `create_workflow`
  patch (for upstreaming).
- `lib/python/test/picongpu/quick/pypicongpu/test_lexis_workflow.py` - 12
  tests: LWD structure, YAML round-trip, two-node variant, optional
  location_resource, config parsing (nested + flat + missing-table error),
  `workflow_backend` default, submission plan (dry-run + project override +
  live-without-session guard), and an **end-to-end** `generate()` that writes
  a valid `workflow.lwd.yaml`.

## 6. Verified locally

- `pytest quick/pypicongpu/test_lexis_workflow.py` -> **12 passed**.
- Full `pytest quick/` -> **199 passed, 2 xfailed, 1 xpassed** (no
  regressions from the `_rc_params.py` / `runner.py` changes).
- End-to-end: a minimal PICMI `Simulation` + `picongpurc.toml`
  (`workflow_backend = "lexis"`, `[lexis]`) -> `generate()` writes a valid
  `workflow.lwd.yaml` (project_shortname, single `picongpu` job, `ddi://`
  input + output), with the CWL `workflow.cwl` still present.

## 7. Fallback retained from round 1 (path B): job-script preset

The round-1 **JUPITER job-script preset** is retained as a valid *manual*
submission path (no Py4Lexis needed). Files: `etc/picongpu/efp-jupiter-jsc/`
(`efp_picongpu.profile.example`, `gh200_efp.tpl`), the `_rc_params.py`
preset-discovery + CWD `picongpurc.toml` fixes, `test_efp_preset.py`, and the
`running_on_efp.rst` fallback section. The full round-1 analysis is preserved
in the appendix (section 10).

## 8. Open items (require EFP access - OUT OF SCOPE here)

1. **Confirm the lexis-extension create endpoint + payload** against the live
   EFP OpenAPI (adjust `create_workflow` / `PY4LEXIS_CREATE_WORKFLOW_PATH`).
2. **Live smoke run:** generate the LWD, create + execute the workflow on a
   real target system, and confirm dataset staging + `simOutput` output.
3. **Target system(s)** + **EFP project/account/QoS** + the **command
   template** registration (the EFP-side "how to run" for PIConGPU).
4. Whether to upstream the Py4Lexis `create_workflow` patch (and propose the
   exact endpoint to the LEXIS team).

## 9. Risks

- **EFP platform behavior unverified:** the create endpoint, staging paths,
  and command-template semantics are from documentation/source, not a live run.
- **Command template coupling:** the LWD references an EFP-registered command
  template; until that is registered, the workflow cannot actually run (the
  LWD itself is still a correct, portable artifact).
- **Py4Lexis churn:** the client is evolving; the patch may need re-basing.

---

## 10. Appendix - round-1 analysis (JUPITER job-script preset, now path B)

> Retained for reference; this was the *primary* in the round-1 draft and is
> now the *fallback*. The research below (TBG/preset machinery, staging
> compatibility) remains valid for path B.

### B.1 What path B does
A TBG preset `etc/picongpu/efp-jupiter-jsc/` whose `.tpl` is a **self-contained**
SLURM job script. `tbg` renders `tbg/submit.start` (no `-s`, so it renders
only, does not submit - what a laptop without a local scheduler wants); the
script + the TBG `input/` dir are uploaded to EFP Workflows by hand (job
script + input dataset), a workflow is created (cluster/partition, input/output
dataset staging on `simOutput`), and an execution started. **No runner changes.**

### B.2 Drafted files
- `efp_picongpu.profile.example` - adapted from `jupiter-jsc/gh200_picongpu`:
  module stack, `jutil` project/account auto-detection, `PIC_BACKEND=cuda:90`,
  `getDevice()`/`getNode()`; `TBG_SUBMIT=sbatch`,
  `TBG_TPLFILE=etc/picongpu/efp-jupiter-jsc/gh200_efp.tpl`.
- `gh200_efp.tpl` - self-contained SLURM script: same resource requests +
  `.TBG_*` computation lines as `jupiter-jsc/gh200.tpl` (4 GH200/node, 72
  cores/GPU, UCX workarounds, `srun --mpiDirect`); **no `--chdir`**
  (`TBG_dstPath="$(pwd)"`); sources `input/picongpu.profile` when present.
- `_rc_params.py` fixes (round-1 rework): preset-matcher disambiguation (C1)
  and CWD `picongpurc.toml` discovery (M1) - kept because they are generic and
  improve preset handling independent of EFP.

### B.3 Staging compatibility (path B)
EFP stages input datasets to `/input` relative to the job cwd; PIConGPU's TBG
layout maps directly: `input/` (binary + runtime config) -> the job's `input/`;
`simOutput/` -> the output dataset. `TBG_dstPath="$(pwd)"` pins the cwd instead
of a local absolute path; `link_results.sh`/`submission_information.txt` are
local-submission conveniences, not needed under EFP.

### B.4 Round-1 verification
TBG render (valid script, no unresolved `!var`, `bash -n` OK); simulated EFP
execution context (staged `input/`, stub `srun` -> profile sourced, `simOutput/`
created, `picongpu` launched with real params); `-o` overrides; CWL
compatibility; full laptop flow E2E (PICMI + `picongpurc.toml` ->
`write_input_file()` -> `tbg` render -> simulated run). Round-1 gate: 187
passed, 2 xfailed, 1 xpassed; `pre-commit run --all-files` green.

### B.5 Round-1 rework (independent review)
Review (TASK-11-REVIEW.md, REQUEST CHANGES) addressed: C1 (preset matcher
disambiguation), M1 (CWD rc-file discovery), m1 (ASCII + hook exclusion),
m2/m3 (RST defects), n1/n2 (doc clarifications). Dispositions in
TASK-11-RESPONSE.md.
