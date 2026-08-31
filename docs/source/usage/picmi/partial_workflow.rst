.. _picmi-partial-workflow:

Partial Workflow Execution (Stages)
===================================

.. note::

   This feature is a **draft** that was developed as an exploratory feature
   request. The stage names and the argument names of
   ``picongpu_run()`` are considered stable, but the overall interface may
   still change before it is declared final.

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

Stages are intentionally decoupled from the individual CWL steps of the
workflow: the number and the names of the workflow steps may change over time
(e.g. when remote execution steps are added), while the stage names and their
meaning stay stable. A stage may be implemented by one or several workflow
steps; that mapping lives entirely inside the Python package.

Selecting a subset of the workflow
----------------------------------

``Simulation.picongpu_run()`` accepts three additional keyword arguments to
select which stages are executed:

.. code-block:: python

   from picongpu.picmi import Simulation, Stage

   sim = Simulation(...)

   # the default: run the whole pipeline, exactly as before
   sim.picongpu_run()

   # run everything up to and including the given stage
   sim.picongpu_run(up_to=Stage.build)

   # start with the given stage; earlier stages must already be completed
   sim.picongpu_run(from_=Stage.submit)

   # combine both to run exactly one stage
   sim.picongpu_run(from_=Stage.submit, up_to=Stage.submit)

   # re-run completed stages
   sim.picongpu_run(force=True)                 # the whole pipeline
   sim.picongpu_run(force=Stage.build)          # build and everything
                                                # that depends on it

The stages are executed in the order ``build``, ``prepare``, ``submit``,
``collect``. ``from_`` and ``up_to`` both accept a :class:`~picongpu.picmi.Stage`
or its string value (e.g. ``"build"``).

Resuming after a failure
------------------------

The progress of a run is persisted in ``<run_dir>/.workflow_state.json``.
Stages that finished successfully are recorded there (keyed by stage name,
never by workflow step name), together with the locations of their
artifacts. When ``picongpu_run()`` is called again, completed stages are
skipped and the run continues with the first incomplete stage.

Stage-level resume applies to runs started with an explicit stage range
(``up_to``/``from_``): the stages are executed one at a time and each is
recorded as soon as it finishes, so after a failure only the failed stage
and the stages after it are re-run:

.. code-block:: python

   # first attempt: failed inside 'submit' ('build' and 'prepare' succeeded)
   sim.picongpu_run(up_to=Stage.submit)

   # after fixing the problem: only 'submit' and 'collect' are re-run
   sim.picongpu_run()

A failed *default* run (no stage arguments) works differently: it executes
the complete workflow in a single cwltool invocation and records the stage
state only after the whole workflow has succeeded. A failed default run
therefore leaves no stage state behind; calling ``picongpu_run()`` again
resumes at *job* granularity through the cwltool job cache: jobs whose
inputs are byte-identical to the first attempt are skipped, and any changed
input re-runs the workflow from that point on. (Recording per-stage progress
during the single-invocation default run would change the historical
"default = one workflow invocation" behavior and is a possible improvement
for a later iteration.)

Changed inputs are detected: each stage records a digest of the workflow
inputs it was run with (see below), so an edit of ``workflow/input.yaml``
after a completed run re-runs the affected stages (and the stages that
depend on them) instead of silently skipping them.

Semantics
---------

- **Missing prerequisites are an error.** Starting at a stage whose
  prerequisites are not completed raises a ``WorkflowPrerequisiteError``
  instead of silently running the missing stages. This is deliberate:
  implicit execution could start work (e.g. compile a full binary) that the
  user did not ask for.
- **``force`` invalidates dependents.** Forcing a stage re-runs it and marks
  all stages that depend on it as stale, so they are re-run as well
  (e.g. ``force=Stage.build`` also re-runs ``submit`` and ``collect``, because
  their inputs depend on the new binaries).
- **The default behavior is unchanged.** ``picongpu_run()`` without stage
  arguments runs the complete workflow in a single invocation, exactly as
  before; stage-based execution only kicks in for explicit ranges and for
  resuming partially completed runs.
- **Workflow flags cannot be changed after generation.** ``picongpu_run()``
  accepts the usual generation flags (``jobs``, ``cmake``, ...), but only for
  a setup that has not been generated yet; changing them afterwards would
  invalidate the recorded state and is rejected with an error.

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

The workflow state file
-----------------------

``<run_dir>/.workflow_state.json`` records, for each stage, its status
(``running``, ``completed``, ``failed``, ``invalidated``), a timestamp, a
digest of the workflow inputs the stage was run with, and the locations of
its artifacts (as CWL file objects). It is safe to delete: the next run then
starts from scratch. Use ``Runner.reset_workflow_state()`` for the same
effect from Python.

The input digest is what detects edits to ``workflow/input.yaml`` between
runs: a completed stage whose inputs changed is marked as stale (together
with the stages that depend on it) and re-run, instead of being silently
skipped with its stale artifacts.

.. note::

   The state file complements, and does not replace, the cwltool job cache
   (``<run_dir>/.cwl_cache``), which the default single-invocation run uses
   as an internal optimization. Per-step (stage-range) runs do not consult
   the job cache: the stage state is their skip mechanism, and every
   invoked step executes freshly.
