.. _picmi-pordyna-setups-features:

PICMI feature gaps from pordyna's ``picongpu-setups-for-picmi-workflows``
=========================================================================

.. warning::

   This page is a **design / requirements capture** document.  It records which PICMI features
   are exercised by the real-world setups in
   `pawelsgroup/picongpu-setups-for-picmi-workflows <https://codebase.helmholtz.cloud/pawelsgroup/picongpu-setups-for-picmi-workflows>`_
   (Paweł Ordyna's private Helmholtz GitLab repo), cross-checks each feature against the
   current PICMI API, and tracks which gaps are already registered as issues.
   It is **not** a user guide: the "works on dev?" column refers to the state at the time of
   writing, not to the latest released PIConGPU version.

.. note::

   **Snapshot caveat.**  The "works on ``dev``?" verdicts below were verified against a fixed
   analysis snapshot, the local ``dev`` commit ``b4e4ca5b2``, which the TT-13 analysis recorded
   as 85 commits behind the fork's ``origin/dev`` at the time (see
   `#42 <https://github.com/chillenzer/picongpu/issues/42>`_).  E.g. the
   `#5413 <https://github.com/ComputationalRadiationPhysics/picongpu/pull/5413>`_
   ``GridedLayout`` fix is not part of this snapshot.  "Absent on analysed ``dev``" therefore
   does not imply "absent upstream"; check the linked issues for the current status.

The analysis behind this page lives in the project task tracker under
`TT-13 <https://github.com/chillenzer/picongpu/issues/42>`_ and the companion
`TT-22 <https://github.com/chillenzer/picongpu/issues/51>`_ (take-over of upstream PR
`#5761 <https://github.com/ComputationalRadiationPhysics/picongpu/pull/5761>`_).

.. contents::
   :local:

What the setups repo drives
---------------------------

``picongpu-setups-for-picmi-workflows`` is a monorepo of named scientific setups under
``setups/<name>/``, each with its own PICMI ``picmi_input.py`` entrypoint.  The primary and
only fully described setup is

``setups/filamentation-collision-hydrogen-plasma/picmi_input.py``

which models a relativistically drifting electron beam (``beam_electrons``) through a
hydrogen bulk plasma (``hydrogen`` + ``bulk_electrons``) -- the classic filamentation /
collision instability scenario.  It drives the PICMI layer plus PIConGPU-specific extensions
exclusively through:

- a ``Cartesian3DGrid`` with ``PseudoRandomLayout`` and the PIConGPU layout extensions
  (``picongpu_n_gpus``, ``picongpu_grid_dist``, ``picongpu_super_cell_size``);
- three species (bulk electrons, beam electrons, hydrogen) each with a
  ``UniformDistribution`` (density, ``rms_velocity`` and/or ``directed_velocity``);
- a ``Yee``/CFL ``ElectromagneticSolver``;
- ``Collision.construct_from_pairs(...)`` together with a ``ConstLogCollision`` wrapped in
  ``CollisionalPhysicsSetup``;
- particle-to-grid **native** derived-field output (``NativeDerivedFieldDump``) plus a
  magnetic-field ``NativeFieldDump``, ``MacroParticleCount`` and a ``Checkpoint``;
- ``OpenPMDConfig`` output configuration (``file=fields``, ``ext=bp5``,
  ``data_preparation_strategy=mappedMemory``);
- the PICMI ``TimeStepSpec`` notation (e.g. ``ts[::100, num_steps]``,
  ``ts[num_steps] + ts[::5.0e-15]("seconds")``);
- custom templates via ``picongpu_template_dir`` (a custom ``N.cfg.mustache`` and
  ``dimension.param.mustache``) together with ``CustomUserInput``
  (``custom_user_input.addToCustomInput({"ndim": ndim}, tag="dimensionality")``);
- the external helper package ``picmi-utils`` (``get_grid_dist``,
  ``submit_scan_from_cli``), and a parameter scan driver built around a pandas dataframe of
  Coulomb-log values.

Its ``picmi_input.py.lock`` (the PEP-723 script lock used by the entrypoint's ``uv run``
shebang) pins ``picongpu`` to pordyna's fork branch ``production_filaments_created_2026_08_26``
(rev ``3fce3c675e``); the repo's ``pyproject.toml``, by contrast, depends on upstream
``ComputationalRadiationPhysics/picongpu@dev``.  I.e. the setup is developed against a fork
branch that already contains the not-yet-merged features listed below.  That fork divergence is
the key fact behind the "no/bug" rows of the table.

Verified feature-gap table
--------------------------

Each row lists a feature the setups drive, whether it works on current ``dev``, and the
gap/reference.  The evidence column cites the current source location (``lib/python/...``)
and the upstream PIConGPU issue/PR that tracks the gap.

.. list-table::
   :widths: 5 18 12 45
   :header-rows: 1

   * - #
     - Feature driven by the setups
     - Works on ``dev``?
     - Gap / reference
   * - A
     - **Native (built-in C++) particle-to-grid derived fields** in openPMD output
       (``Density``, ``EnergyDensity``, ``WeightedVelocity``, ``Momentum``,
       ``Average_*``, ``RelativisticDensity``, ``ScreeningInvSquared``) -- heavily used per
       species for ``Density``/``EnergyDensity``
     - **No** (draft PR
       `#5761 <https://github.com/ComputationalRadiationPhysics/picongpu/pull/5761>`_)
     - PICMI only knows ``NativeFieldDump`` (E/B/J) and custom-``ParticleFunctor``
       ``DerivedFieldDump``
       (``picmi/diagnostics/field_dump.py:22,32,37``); every particle-to-grid quantity needs a
       user-defined Python functor and generates a custom C++ struct.
   * - B
     - **Deterministic particle-functor C++ struct names** (dedup/reuse/reproducibility of
       derived fields; part of ``#5761``)
     - **No**
     - ``pypicongpu/particle_functor/particle_functor.py:141`` uses
       ``f"{self.name}_{uuid().hex}"`` (non-reproducible); ``#5761`` computes a sha256 of the
       definition instead.  Load-bearing for rows A and H.
   * - C
     - ``sim.write_input_file(..., exist_ok=True)`` ("regenerate over existing setup dir";
       the setups' iterative scan workflow)
     - **No** (bug, upstream issue
       `#5752 <https://github.com/ComputationalRadiationPhysics/picongpu/issues/5752>`_)
     - ``pypicongpu/runner.py:413`` ``copytree(...)`` lacks ``dirs_exist_ok=True`` (the second
       ``copytree`` at ``runner.py:425`` has it) -> ``FileExistsError`` when regenerating.
   * - D
     - ``ConstLogCollision`` PICMI input generation (filamentation-collision setup uses it via
       an in-repo ``RenderableConstLogCollision`` adapter that manually supplies the missing
       rendering method)
     - **No** (bug, upstream issues
       `#5754 <https://github.com/ComputationalRadiationPhysics/picongpu/issues/5754>`_ and
       `#5753 <https://github.com/ComputationalRadiationPhysics/picongpu/issues/5753>`_)
     - ``pypicongpu/collisions.py:24`` ``ConstLogCollision(BaseModel)`` has no
       ``get_rendering_context()`` (called from ``collisions.py:77``) -> ``AttributeError``;
       plus mustache/schema/serializer shape mismatches.
   * - E
     - **MultiSpecies / charge-neutral collective init** with varying momentum (density,
       drift/temperature); the setups' three ``UniformDistribution`` species match this
       scenario verbatim
     - **No** (upstream issue
       `#5762 <https://github.com/ComputationalRadiationPhysics/picongpu/issues/5762>`_)
     - No ``MultiSpecies`` anywhere in ``picmi/`` or ``pypicongpu/``; only heuristic grouping.
       Tracked as fork issue
       `#36 <https://github.com/chillenzer/picongpu/issues/36>`_.
   * - F
     - **Binning of selected particle regions** (e.g. bin "leaving" particles)
     - **No** (upstream issue
       `#5773 <https://github.com/ComputationalRadiationPhysics/picongpu/issues/5773>`_)
     - PICMI binning diagnostics
       (``picmi/diagnostics/binning.py``) do not expose species-region selection.  Tracked as
       fork issue `#38 <https://github.com/chillenzer/picongpu/issues/38>`_.
   * - G
     - Compile-parallelism control for the CWL workflow (``pic-build -j N``)
     - **No** (upstream issue
       `#5766 <https://github.com/ComputationalRadiationPhysics/picongpu/issues/5766>`_)
     - The ``-j``/``jobs`` knob exists in ``PicBuildFlags`` (``runner.py:95-102``, default 4,
       serialised as ``build_jobs`` -> ``pic-build -j N``), but its default is hardcoded and not
       configurable via ``picongpurc`` (upstream #5766).  Tracked as fork issue
       `#39 <https://github.com/chillenzer/picongpu/issues/39>`_.
   * - H
     - **Reproducible serialisation of the picmi ``Simulation``** into ``metadata/`` of the
       generated setup_dir (setups are generated many times / reused as inputs)
     - **partial**
     - ``runner.py:395`` ``store_metadata`` dumps only pypicongpu artefacts
       (``pypicongpu_runner.json``, ``rc_params.json``); the picmi ``Simulation`` itself is not
       serialised.  Tracked as fork issue `#35 <https://github.com/chillenzer/picongpu/issues/35>`_.
   * - I
     - ``custom_user_input`` survives serialisation round-trips (the setups pass
       ``{"ndim": ndim}``)
     - **partial / bug**
     - Excluded inverse path / arbitrary types in the current serialisation.  Tracked as fork
       issue `#33 <https://github.com/chillenzer/picongpu/issues/33>`_.
   * - J
     - Grid distribution + super-cell size from PICMI (``picongpu_grid_dist``,
       ``picongpu_super_cell_size``; the setups use ``get_grid_dist`` plus
       ``picongpu_n_gpus``)
     - **Yes**
     - ``picmi/grid.py:60-62`` (merged upstream `#5350 <https://github.com/ComputationalRadiationPhysics/picongpu/pull/5350>`_).  No gap.
   * - K
     - Multiple lasers in one setup
     - **Yes**
     - Already landed upstream (`#5519 <https://github.com/ComputationalRadiationPhysics/picongpu/pull/5519>`_).
   * - L
     - Auto (field) output via PICMI (the setups' ``NativeFieldDump(B)`` + ``OpenPMDConfig``)
     - **Yes**
     - ``NativeFieldDump``/``OpenPMDConfig`` in ``picmi/diagnostics/field_dump.py:32`` /
       merged upstream `#5316 <https://github.com/ComputationalRadiationPhysics/picongpu/pull/5316>`_ (``backend_config.py``).  The *native derived* auto-output is the missing piece and is covered by row A.
   * - M
     - Distribution-level features used by the setups (``UniformDistribution`` with
       ``rms_velocity`` / ``directed_velocity``, thermal ``rms`` speed from ``plasmapy``)
     - **Yes**
     - ``picmi/distribution/`` present; directional temperature merged upstream
       (`#5677 <https://github.com/ComputationalRadiationPhysics/picongpu/pull/5677>`_).  Row E is
       the remaining distribution-level gap.
   * - N
     - Field ionization models (ADK/ADKVariant) in PICMI
     - **Yes** (not exercised by this setup)
     - ``picmi/interaction/ionization/`` present.  No evidence of a gap beyond D/E.
   * - O
     - openPMD/simOutput path & backend config (TOML) from PICMI diagnostics
     - **Yes**
     - ``picmi/diagnostics/backend_config.py`` + ``_FieldDump.options``.  No gap.

Which gaps are already tracked
------------------------------

Every row above that is a genuine gap maps onto an open issue so the knowledge here stays
actionable:

* Native derived fields + deterministic functor names (rows A+B) -- upstream DRAFT PR
  `#5761 <https://github.com/ComputationalRadiationPhysics/picongpu/pull/5761>`_, to be taken
  over by the team (from this task's follow-up fork issue
  `#51 <https://github.com/chillenzer/picongpu/issues/51>`_).
* ``exist_ok=True`` regen bug (row C) -- upstream issue
  `#5752 <https://github.com/ComputationalRadiationPhysics/picongpu/issues/5752>`_.
* ``ConstLogCollision`` / collision rendering (row D) -- upstream issues
  `#5754 <https://github.com/ComputationalRadiationPhysics/picongpu/issues/5754>`_ and
  `#5753 <https://github.com/ComputationalRadiationPhysics/picongpu/issues/5753>`_.
* MultiSpecies / charge-neutral init (row E) -- upstream
  `#5762 <https://github.com/ComputationalRadiationPhysics/picongpu/issues/5762>`_, tracked as
  fork issue `#36 <https://github.com/chillenzer/picongpu/issues/36>`_.
* Binning of selected particle regions (row F) -- upstream
  `#5773 <https://github.com/ComputationalRadiationPhysics/picongpu/issues/5773>`_, tracked as
  fork issue `#38 <https://github.com/chillenzer/picongpu/issues/38>`_.
* Compile-parallelism knob (row G) -- upstream
  `#5766 <https://github.com/ComputationalRadiationPhysics/picongpu/issues/5766>`_, tracked as
  fork issue `#39 <https://github.com/chillenzer/picongpu/issues/39>`_.
* picmi-``Simulation`` metadata dump (row H) -- fork issue
  `#35 <https://github.com/chillenzer/picongpu/issues/35>`_.
* ``custom_user_input`` serialisation (row I) -- fork issue
  `#33 <https://github.com/chillenzer/picongpu/issues/33>`_.

Recommendation: take over ``#5761``
-----------------------------------

The single most valuable follow-up extracted from this analysis is to **take over upstream
DRAFT PR `#5761 <https://github.com/ComputationalRadiationPhysics/picongpu/pull/5761>`_**
("support native derived functors in picmi", branch ``topic-supportNativeDerivedFunctorsInPicmi``).
It is the feature the setups repo depends on (its lock pins a fork branch that already
contains it) and it bundles rows A and B:

- ``picmi/diagnostics/field_dump.py`` -- add ``_BuiltinDerivedFieldDump``,
  ``NativeDerivedFieldDump``, ``AverageDerivedFieldDump``; export in
  ``picmi/diagnostics/__init__.py`` and add to ``AnyDiagnostic``;
- ``picmi/simulation.py`` ``_generate_openpmd_plugins`` (:ref:`see code
  <picmi-pordyna-evidence>`) -- thread ``species`` + ``builtin_solver`` through to
  ``pypicongpu.output.openpmd_plugin.FieldDump``;
- ``pypicongpu/output/openpmd_plugin.py`` -- add ``BuiltinFieldSolver``/``DerivedFieldSolver``
  and extend the ``FieldDump`` serialiser (``openpmd_plugin.py:164``) to emit all sources,
  not just custom functors;
- ``pypicongpu/simulation.py`` -- computed fields ``derived_field_functors`` and
  ``field_tmp_solvers`` (dedup by species+attribute+filter);
- ``templates/include/picongpu/param/fileOutput.param.mustache`` -- replace the
  custom-functor-only struct generation with per-species ``FieldTmpSolverConfig<Species,
  Attribute, Filter>`` + ``ValidateFieldTmpSolver_t`` + ``pmacc::mp_transform`` (compile-time
  "only used species/solver/filter combinations" win, relevant for large setups);
- deterministic (sha256-of-definition) ``ParticleFunctor.typename`` (row B), required by the
  solver dedup and by row H.

Explicitly out of scope of ``#5761`` even after the port: ``EnergyDensityCutoff`` (needs a
user-parameterised C++ class -- a future ``custom_user_input``/template mechanism, tied to
fork issue `#33 <https://github.com/chillenzer/picongpu/issues/33>`_).

The port is scheduled as the **last** task of the current round
(`TT-22 <https://github.com/chillenzer/picongpu/issues/51>`_): it touches
``openpmd_plugin.py``, ``particle_functor.py`` and ``simulation.py``, the same files as the
round-trip and alignment tasks, so it should land on the stabilised base.  The small bug-fixes
rows C/D (``#5752``, ``#5754``/``#5753``) are independent and can land early -- they unblock
the setups immediately.

File:line evidence used above
-----------------------------

The following table summarises the exact source locations that back the "gap/reference"
column.  "no match" means the symbol is absent from ``lib/python/`` on the analysed ``dev``.

.. _picmi-pordyna-evidence:

.. list-table::
   :widths: 8 40 22
   :header-rows: 1

   * - Feature
     - Evidence in ``lib/python/`` (analysed ``dev``)
     - Verdict
   * - Native derived fields (A)
     - ``picmi/diagnostics/field_dump.py:22`` ``_FieldDump``, ``:32`` ``NativeFieldDump`` (E/B/J only),
       ``:37`` ``DerivedFieldDump`` (custom functor only); ``pypicongpu/output/openpmd_plugin.py:96``
       ``FieldDump`` and ``:164`` serialiser emits ``derived_fields`` only for custom functors;
       ``picmi/diagnostics/__init__.py`` exports no built-in derived classes; no
       ``BuiltinFieldSolver`` / ``derived_field_functors`` / ``NativeDerivedFieldDump`` match
     - absent (DRAFT
       `#5761 <https://github.com/ComputationalRadiationPhysics/picongpu/pull/5761>`_)
   * - Deterministic typename (B)
     - ``pypicongpu/particle_functor/particle_functor.py:138-141`` ``typename`` =
       ``f"{self.name}_{uuid().hex}"``
     - non-reproducible
   * - ``exist_ok`` regen (C)
     - ``pypicongpu/runner.py:413`` ``copytree`` without ``dirs_exist_ok=True`` (vs ``:425`` with it)
     - bug (upstream
       `#5752 <https://github.com/ComputationalRadiationPhysics/picongpu/issues/5752>`_)
   * - ``ConstLogCollision`` (D)
     - ``pypicongpu/collisions.py:24`` ``ConstLogCollision(BaseModel)`` without
       ``get_rendering_context()``; ``:77`` requires it
     - bug (upstream
       `#5754 <https://github.com/ComputationalRadiationPhysics/picongpu/issues/5754>`_ /
       `#5753 <https://github.com/ComputationalRadiationPhysics/picongpu/issues/5753>`_)
   * - MultiSpecies (E)
     - no ``MultiSpecies`` match in ``picmi/`` or ``pypicongpu/``
     - absent (upstream
       `#5762 <https://github.com/ComputationalRadiationPhysics/picongpu/issues/5762>`_)
   * - Binning regions (F)
     - ``picmi/diagnostics/binning.py`` has no species-region selection
     - absent (upstream
       `#5773 <https://github.com/ComputationalRadiationPhysics/picongpu/issues/5773>`_)
   * - Compile threads (G)
     - ``pypicongpu/runner.py:95-102`` ``PicBuildFlags.jobs`` (default 4, serialised to
       ``build_jobs``) -- the knob exists; only its default is hardcoded, not configurable via
       ``rc_params``/``picongpurc`` (``runner.py:303`` ``generate_build_command`` ->
       ``pic-build $@``)
     - absent (upstream
       `#5766 <https://github.com/ComputationalRadiationPhysics/picongpu/issues/5766>`_)
   * - picmi metadata (H)
     - ``pypicongpu/runner.py:395-398,440-441`` ``store_metadata`` dumps only pypicongpu JSON
     - partial (fork
       `#35 <https://github.com/chillenzer/picongpu/issues/35>`_)
   * - ``custom_user_input`` (I)
     - ``picmi/simulation.py:307`` ``picongpu_add_custom_user_input``; serialisation excludes
       the inverse path / arbitrary types
     - partial / bug (fork
       `#33 <https://github.com/chillenzer/picongpu/issues/33>`_)
   * - Grid layout (J)
     - ``picmi/grid.py:60-62`` ``picongpu_n_gpus``/``picongpu_grid_dist``/
       ``picongpu_super_cell_size``
     - works
   * - Multi-laser (K)
     - ``picmi/simulation.py:362-363`` only a compat check for ``laser_injection_methods``
       remains
     - works
   * - Auto field output (L)
     - ``picmi/diagnostics/field_dump.py:32`` ``NativeFieldDump``; ``backend_config.py``
     - works (derived case missing, row A)
   * - Distributions (M)
     - ``picmi/distribution/`` ``UniformDistribution`` with ``rms_velocity``/``directed_velocity``
     - works
   * - Ionization (N)
     - ``picmi/interaction/ionization/`` ADK/ADKVariant
     - works
   * - openPMD config (O)
     - ``picmi/diagnostics/backend_config.py`` + ``_FieldDump.options``
     - works
