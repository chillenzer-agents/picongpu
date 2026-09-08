.. _picmi-partial-workflow:

Partial Workflow Execution (Stages)
===================================

Running a PIConGPU simulation with the Python package drives a small
`CWL <https://www.commonwl.org/>`_ workflow (``workflow.cwl``) that performs
several actions in a row. These actions are exposed to users as **stages** -
coarse-grained, stable milestones of a simulation run:

=========  =====================================================
Stage      What it does
=========  =====================================================
``build``  compiles the PIConGPU executable (``pic-build``)
``prepare`` prepares the submission (``tbg``)
``submit`` launches the simulation job on the batch system
``collect`` organizes the results into the run directory
=========  =====================================================

The stages are a *thin* vocabulary: each stage is an alias over the
corresponding step of ``workflow.cwl`` and over the workflow's top-level
outputs that expose what that step produces. The Python package only uses
them to **generate the right cwltool invocation** for the requested subset.
All actual workflow logic - which steps to run, wiring, skipping completed
steps, resuming - is performed by cwltool itself, nothing is reimplemented.

Selecting a subset of the workflow
----------------------------------

``Simulation.picongpu_run()`` accepts two additional keyword arguments to
select which stages are executed:

.. code-block:: python

   from picongpu.picmi import Simulation, Stage

   sim = Simulation(...)

   # the default: run the whole pipeline, exactly as before
   sim.picongpu_run()

   # run everything up to and including the given stage
   sim.picongpu_run(up_to=Stage.build)

   # resume at the given stage
   sim.picongpu_run(from_=Stage.submit)

``up_to`` and ``from_`` both accept a :class:`~picongpu.picmi.Stage` or its
string value (e.g. ``"build"``). They are mutually exclusive.

``up_to`` (a prefix)
~~~~~~~~~~~~~~~~~~~~

``up_to=Stage.X`` executes the given stage and everything before it, in one
cwltool invocation. The runner hands cwltool the **full** workflow but
requests *only the outputs of stage X* as the desired final outputs
(cwltool's ``--target`` option). cwltool then executes exactly the steps
that contribute to those outputs and **prunes every step after the stage**,
so the stages after ``X`` are not run at all.

This is the way to do a "build only" or "prepare and submit only" run
(e.g. to compile/test the setup without touching the submitted job, or to
run a job without collecting its results yet).

``from_`` and the job store (a resume)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``from_=Stage.X`` resumes at the given stage: the workflow is run in full,
but against the persistent cwltool **job store** (``<run_dir>/.cwl_cache``).
Steps whose inputs are byte-identical to a previous run (everything before
the resume point) are served from the store without re-executing, and only
the requested stage and everything after it recompute.

This is how an interrupted run is continued without redoing the completed
stages - e.g. after ``picongpu_run(up_to=Stage.submit)`` failed inside
``submit``:

.. code-block:: python

   # first attempt: failed inside 'submit' ('build' and 'prepare' succeeded)
   sim.picongpu_run(up_to=Stage.submit)

   # after fixing the problem: 'build' and 'prepare' are served from the job
   # store, only 'submit' and 'collect' recompute
   sim.picongpu_run(from_=Stage.submit)

The job store is the **only** state: the runner itself persists nothing.
Because cwltool's job-store keys are hashes of the step inputs, a resume is
guaranteed to skip steps whose inputs are unchanged; if you change the
inputs of a step you also want re-run, run from a fresh setup/run directory
(or delete ``<run_dir>/.cwl_cache``) so everything computes again.

Semantics
---------

- **The default behavior is unchanged.** ``picongpu_run()`` without stage
  arguments runs the complete workflow in a single invocation, exactly as
  before (asking for the collect stage's outputs, which walks the whole
  pipeline).
- **Partial execution is cwltool's, not Python's.** ``up_to`` merely
  translates into ``--target`` flags; cwltool decides which steps to run.
  ``from_`` translates into a full run against the job store.
- **Workflow flags cannot be changed after generation.** ``picongpu_run()``
  accepts the usual generation flags (``jobs``, ``cmake``, ...), but only for
  a setup that has not been generated yet; changing them afterwards is
  rejected with an error.

.. note::

   The per-stage outputs (e.g. ``build_bin_directory``) that make ``up_to``
   possible are *raw* step outputs, exposed as top-level workflow outputs
   purely so a prefix run can request them. The default run requests only
   the collect outputs, so it produces the exact same run directory layout
   as before, and the per-stage aliases are never materialized there.

.. note::

   For the default local (``bash``) submit system the submitted job runs
   ``<run_dir>/input/bin/picongpu`` from the run directory. The submit stage
   pre-stages the ``bin/`` and ``etc/`` subdirectories there, but the rest
   of the input (metadata, ``.build``, ``ro-crate.json``, ...) is only
   copied into the run directory by the ``collect`` stage. A run that stops
   after ``submit`` (e.g. ``picongpu_run(up_to=Stage.submit)``) therefore
   leaves a *partial* ``input/`` directory: the local job can find its
   binary, but it runs against the partial input, and the organized
   artifacts (``tbg/``, the ``simOutput`` link, the submission information)
   only appear in the run directory after ``collect``. Let the job finish
   before running ``collect`` (or stage the remaining inputs by hand) if
   the job needs the complete input directory.

Implementation note
-------------------

``Runner.run_command()`` (the package-internal heart of this feature) only
builds the cwltool command line: the full ``workflow.cwl`` plus
``--target`` flags for the requested stage's outputs (or none extra for the
default full run), ``--outdir <run_dir>`` and ``--cachedir
<run_dir>/.cwl_cache``. The mapping from stages to output names is the small
``STAGE_OUTPUTS`` table in ``picongpu/pypicongpu/runner.py``; if the
workflow steps are ever reorganized, only that table (and
``workflow.cwl``) change, not the invocation logic.
