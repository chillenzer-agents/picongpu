.. _pypicongpu-running-efp:

Running on the EuroHPC Federation Platform (EFP)
================================================

.. sectionauthor:: AI agent (task 11, rework)

This page describes how to run a PIConGPU simulation on the
`EuroHPC Federation Platform (EFP) <https://www.eurohpc-ju.europa.eu/supercomputers/eurohpc-federation-platform_en>`_
through the `EFP Workflows <https://docs.my-eurohpc.eu/workflows/quickstart/>`__
(``workflows.my-eurohpc.eu``), which are implemented on the
`LEXIS platform <https://docs.lexis.tech>`__.
The EFP Workflows execute **job scripts**, **Apptainer containers**, or
**custom LEXIS Workflow Definitions (LWD)** on the participating EuroHPC
systems. This page focuses on the **LWD + Py4Lexis** path (the recommended,
proof-of-concept primary) and documents the **job script** path (a working
fallback that reuses PIConGPU's existing
:ref:`TBG <usage-tbg>`/:ref:`profile <install-profile>` machinery).

.. note::

   This is a proof of concept (task 11, rework).
   It covers the submission configuration and the local part of the workflow;
   the final EFP smoke run (workflow creation, execution, output retrieval)
   requires EFP access and is documented as a pending verification step.

Prerequisites
-------------

- An EFP account via national AAI (``MyAccessID``) and an
  `EFP project/allocation <https://docs.my-eurohpc.eu/allocations/>`__ on the
  target system (the job script is charged to the JSC project/budget account
  configured in the profile).
- The PIConGPU Python interface (PyPIConGPU) on your laptop,
  see :ref:`the PyPIConGPU introduction <pypicongpu>` and :doc:`running`.
- A built ``picongpu`` executable for the target system's architecture
  (e.g. ``cuda:90`` for JUPITER's GH200).

Submission paths
----------------

Three paths were evaluated; the **LWD + Py4Lexis** path is the recommended,
proof-of-concept primary and the **job script** path is a working fallback:

1. **LEXIS Workflow Definition (LWD) + Py4Lexis (recommended, proof of concept).**
   The runner emits a `LEXIS Workflow Definition
   <https://docs.lexis.tech/user_interfaces/lexis_workflow_definition.html>`__
   (``workflow.lwd.yaml``) instead of the CWL workflow, and
   `Py4Lexis <https://docs.lexis.tech/user_interfaces/py4lexis.html>`__
   submits it to the EFP (create workflow → execute → poll), using EFP
   **dataset staging** for inputs/outputs. Configured via
   ``workflow_backend = "lexis"`` and a ``[lexis]`` table in
   ``picongpurc.toml``. See "Running via the LEXIS workflow definition"
   below.
2. **Job script (fallback, implemented).**
   A preset (``etc/picongpu/efp-<system>/``) renders a self-contained job
   script in the target system's batch dialect via :ref:`TBG <usage-tbg>`.
   The rendered script is uploaded to the EFP Workflows (Data Management →
   Job Scripts, with the target system selected), and the TBG ``input/``
   directory is uploaded as the input dataset.
   No changes to the PyPIConGPU runner are required: the preset mechanism
   (``picongpurc.toml`` / ``RCParams(preset=...)``, see the
   :ref:`PyPIConGPU API documentation <pypicongpu-misc-apidoc>`)
   selects the template, and ``tbg`` renders the script. This path needs no
   Py4Lexis and is useful where programmatic submission is not available.
3. **Apptainer/SIF container (fallback, documented only).**
   Package the ``picongpu`` binary and its runtime dependencies into an
   Apptainer-compatible image (build inside a CUDA/ROCm base image) and
   upload it to the EFP Workflows (Data Management → Containers), running it
   with a thin job script (``apptainer exec ... input/bin/picongpu ...``) or
   the container workflow type.
   Trade-off: a reproducible environment without relying on the target
   system's modules, but a large upload, one image per GPU architecture, and
   GPU pass-through must be supported by Apptainer on the target system.

Running via the LEXIS workflow definition (recommended)
---------------------------------------------------------

The recommended path (proof of concept) makes the runner emit a **LEXIS
Workflow Definition** (``workflow.lwd.yaml``) instead of the CWL workflow,
and submits it to the EFP through **Py4Lexis**.

1. **Configure the LEXIS backend in ``picongpurc.toml``**:

   .. code-block:: toml

      workflow_backend = "lexis"
      author = "Your Name"
      email = "you@example.com"

      [lexis]
      project_shortname = "your-efp-project"
      command_template_name = "picongpu"   # a template registered in the project
      location_name = "jupiter"            # target cluster
      location_resource = "gh200"          # optional
      walltime_limit = 7200
      max_cores = 64                       # optional
      input_dataset = "ddi://~/your-picongpu-setup"

   ``workflow_backend`` defaults to ``"cwl"`` (the existing behavior); set it
   to ``"lexis"`` to switch. The ``[lexis]`` table describes the HPC job node
   (cluster, command template, resources) and the input/output dataset
   staging. A ``[lexis.build]`` sub-table enables a two-node build → run
   workflow that shares the compiled binary.

2. **Generate the setup** with your PICMI script (``sim.write_input_file()``
   or ``Runner.generate()``). With ``workflow_backend = "lexis"`` the runner
   writes ``workflow/workflow.lwd.yaml`` (alongside the usual CWL files):

   .. code-block:: yaml

      id: picongpu-...
      project_shortname: your-efp-project
      jobs:
        picongpu:
          requirements:
            command_template_name: picongpu
            locations: [{location_name: jupiter, location_resource: gh200}]
            walltime_limit: 7200
            policy: preferred
          data_inputs: [{source: ddi://~/your-picongpu-setup, target: input/}]
          data_outputs:
            - source: output/
              target: ddi://~
              metadata: {$name: picongpu_output, access: project}

3. **Stage the setup as a dataset** (upload the generated ``setup_dir`` to the
   EFP as the input dataset referenced by ``input_dataset``).

4. **Submit via Py4Lexis** (install ``py4lexis[efp]`` and apply
   ``patches/py4lexis-create-workflow.diff`` to add the missing
   ``create_workflow`` method):

   .. code-block:: python

      from picongpu.pypicongpu.lexis_submit import submit
      submit("setup/workflow/workflow.lwd.yaml", dry_run=True)  # plan only
      # live: submit(..., dry_run=False, session=<logged-in LexisSession>)

   The submission plan is create workflow → execute → poll. ``dry_run=True``
   (the default) builds the plan without any network call.

.. note::

   The LWD is a portable artifact independent of the submission mechanism: it
   can also be uploaded directly in the EFP portal (Applications → User
   Workflows) and run there. The live create/execute/poll path requires EFP
   access and a registered command template (see "Pending verification").

Running via the job script path (fallback, laptop flow)
---------------------------------------------------------

The fallback flow: you have a ``picongpurc.toml`` and a PICMI input script
on your laptop; running the script prepares everything that the EFP Workflows
need (a self-contained job script to upload by hand).

1. **Select the EFP preset in ``picongpurc.toml``** (in the directory you
   run the PICMI script from — typically next to the script — or in
   ``$XDG_CONFIG_HOME/picongpu/picongpurc.toml``):

   .. code-block:: toml

      preset = "efp-jupiter-jsc"
      author = "Your Name"
      email = "you@example.com"
      pic_src_path = "/path/to/your/picongpu/checkout"
      pic_libs = "/path/to/your/local/libraries"

   The preset sets ``TBG_SUBMIT=sbatch`` and
   ``TBG_TPLFILE=etc/picongpu/efp-jupiter-jsc/gh200_efp.tpl``, and the
   profile carries the target system's module stack and the JSC
   project/account.
2. **Generate the simulation setup** with your PICMI script:

   .. code-block:: python

      from picongpu import picmi
      # ... build sim ...
      sim.write_input_file("setup")

   This copies the ``efp-jupiter-jsc`` preset into
   ``setup/etc/picongpu/`` and renders ``setup/etc/picongpu/N.cfg``.
3. **Build** the executable for the target system,
   e.g. ``cd setup && pic-build -j`` on the laptop (with the matching
   compiler/CUDA) or on an EFP/JUPITER interactive node.
   Note that a CUDA build is tied to the GPU architecture
   (``PIC_BACKEND=cuda:90`` in the profile).
4. **Create the TBG directory and render the job script**:

   .. code-block:: bash

       cd setup
       tbg -c etc/picongpu/N.cfg -t etc/picongpu/efp-jupiter-jsc/gh200_efp.tpl $SCRATCH/efp-run

   This creates ``$SCRATCH/efp-run/tbg/submit.start`` (the rendered job
   script) and ``$SCRATCH/efp-run/input/`` (``bin/``, ``etc/``, ...).
   Per-run overrides (queue, account, wall time, ...) work as usual
   through ``tbg -o``, e.g.
   ``tbg -c etc/picongpu/N.cfg -o "TBG_queue=debug TBG_wallTime=01:00:00"
   $SCRATCH/efp-run``;
   the overwritable variables are the ``.TBG_*`` computation lines of the
   template.
5. **Ship the environment profile with the input dataset**:

   .. code-block:: bash

      cp setup/workflow/scripts/picongpu.profile $SCRATCH/efp-run/input/picongpu.profile

   The job script sources ``input/picongpu.profile`` when present, so it is
   self-contained; otherwise it falls back to the profile of the user the
   job is submitted as (useful when submitting from a JUPITER interactive
   shell).
6. **Upload and run on EFP** (``workflows.my-eurohpc.eu``, after AAI login):

   - Data Management → Job Scripts → *Create Jobscript*: paste the content
     of ``tbg/submit.start``, select the target system (JUPITER).
   - Data Management → Datasets: upload ``$SCRATCH/efp-run/input`` as an
     input dataset of your project.
   - Workflows → *Create Workflow* from the job script: select the
     cluster/partition within your allocation, enable **input dataset
     staging** (the dataset is staged to ``./input`` relative to the job
     execution context) and **output dataset staging** for ``simOutput``.
   - *Create Workflow Execution*, then follow the workflow graph and
     *View HPC Job Logs*.

Why the job script is self-contained
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The EFP/LEXIS platform sets the working directory of the HPC job to its
*execution context* and stages the input dataset into ``./input`` relative
to it; it does not know about local paths on your laptop.
The ``gh200_efp.tpl`` template therefore differs from the
system-specific ``jupiter-jsc/gh200.tpl`` in exactly two ways:

- it pins the working directory with ``TBG_dstPath="$(pwd)"`` and has no
  ``#SBATCH --chdir`` line (a hard-coded local path would not exist on the
  target system), and
- it sources the profile from the input dataset
  (``input/picongpu.profile``) when present.

Everything else — the ``.TBG_*`` computation lines (devices per node,
memory, node count), the ``#SBATCH`` resource requests, and the
``srun ... input/bin/picongpu !TBG_programParams`` launch — is the same as
the regular JUPITER template.

Staging compatibility
---------------------

EFP/LEXIS staging maps onto PIConGPU's TBG layout directly:

- **Input dataset** → staged to ``/input`` relative to the job execution
  context = the TBG ``input/`` directory (``input/bin/picongpu``,
  ``input/etc/N.param``, ...), which is what the job script launches.
- **Output dataset** → the ``simOutput/`` directory that the job script
  creates and works in (PIConGPU output, ``stdout`` symlink).
- ``submission_information.txt``/``link_results.sh`` are produced by the
  PyPIConGPU CWL runner for local submission; with EFP, job management
  (id, logs, outputs) happens in the EFP Workflows UI, so they are not
  needed there.

Configurability
---------------

- **Target system**: one preset per system, ``etc/picongpu/efp-<system>/``,
  selectable via ``picongpurc.toml`` (``preset = "efp-<system>"``) or
  ``RCParams(preset=...)`` / ``TBGFlags(template_file=..., submit_system=...)``
  in the Python interface.
  This draft provides ``efp-jupiter-jsc`` (SLURM dialect, derived from
  ``jupiter-jsc``); add further EFP systems by copying the pattern with
  that system's batch dialect and resource parameters
  (e.g. LUMI's Slurm/CPE stack, Leonardo's Slurm, ...).
  As an alternative, a single ``efp`` preset with the system as a
  ``.TBG_*`` variable was considered and rejected: the batch *dialect*
  (directives, launchers, GPU allocation) differs per system, so a
  per-system template is required anyway, and the preset mechanism already
  provides per-system selection without new machinery.
- **Per-run overrides** (queue/partition, account, wall time, ...):
  ``tbg -o "VAR=value ..."``; the overwritable template variables are the
  ``.TBG_*`` computation lines (``TBG_queue``, ``TBG_nameProject``,
  ``TBG_wallTime``, ...).
  (The Python interface exposes the same mechanism as
  ``TBGFlags(overwrite_vars=[...])``/``o=[...]`` for the CWL runner; note
  that the CWL workflow currently declares that input as a string, so the
  list form is rejected by cwltool — a pre-existing issue independent of
  the EFP flow, which uses ``tbg`` directly.)
- **The CWL runner (``picongpu_run()``) is not the EFP submission path.**
  With the EFP preset, ``run_submit_system`` defaults to the profile's
  ``TBG_SUBMIT=sbatch``, so the CWL flow would submit locally via
  ``sbatch`` — it stays for local/SLURM execution. For EFP, use the job
  script path above (steps 4-6) and upload the rendered script and the
  ``input/`` directory through the portal.

Pending verification (requires EFP access)
-------------------------------------------

- Upload the rendered job script + input dataset, create a workflow
  execution, and confirm: the workflow graph runs, the logs show PIConGPU
  iterating, ``simOutput`` is staged out.
- Confirm the exact job execution context semantics (working directory,
  where ``./input`` is staged, whether ``#SBATCH`` directives are passed
  through unmodified) on the target system, and that ``jutil``/modules are
  available on its compute nodes.
- Confirm the JSC project/budget account the EFP allocation is charged to,
  and set it in the profile.
