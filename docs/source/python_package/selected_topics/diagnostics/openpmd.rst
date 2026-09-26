.. _openpmd:

openPMD Output
==============

`openPMD <https://www.openpmd.org/>`__ is the general-purpose,
hierarchical data standard for particle and field data in computational physics.
It is the most flexible of the output formats PIConGPU offers:
fields, particles and arbitrarily derived quantities
are stored together in a single, self-describing file
that can be read by `openPMD-tools <https://github.com/openPMD/openPMD-api>`__,
`yt <https://yt-project.org/>`__ and similar analysis tools.

Three diagnostics write their data through openPMD,
all parameterized by the same :class:`~picongpu.picmi.diagnostics.OpenPMDConfig`:

``ParticleDump``
   Dumps all data of a species (position, momentum, weighting, ...)
   on the given time steps.

``NativeFieldDump``
   Dumps one of the native fields ``"E"``, ``"B"`` or ``"J"``
   (the fields PIConGPU solves for and the current).

``DerivedFieldDump``
   Deposition of an arbitrary particle quantity to the grid --
   e.g. a species' charge density, current density or kinetic energy --
   via a :ref:`particle functor <particle-functors>`.
   The field name is derived from the species, the optional filter
   and the functor name.

.. literalinclude:: ../../snippets/selected_topics/openpmd.py
   :language: python
   :start-at: @ParticleFunctor(name="kineticEnergy")
   :end-before: for config in sorted

Built-in derived fields
-----------------------

A :class:`~picongpu.picmi.diagnostics.DerivedFieldDump` always compiles a
Python :class:`~picongpu.picmi.particle_functor.ParticleFunctor` into the
binary. For the most common deposition operations PIConGPU ships a native
C++ implementation, which is used by
:class:`~picongpu.picmi.diagnostics.NativeDerivedFieldDump` without any
Python functor:

.. literalinclude:: ../../snippets/selected_topics/derived_fields.py
   :language: python
   :start-at: density = NativeDerivedFieldDump(
   :end-before: sim = picmi.Simulation(

:class:`~picongpu.picmi.diagnostics.NativeDerivedFieldDump` takes a
``field`` from the built-in set:

* scalar fields:
  ``"Density"``, ``"BoundElectronDensity"``, ``"ChargeDensity"``,
  ``"Counter"``, ``"Energy"``, ``"EnergyDensity"``, ``"LarmorPower"``
  and ``"MacroCounter"``;
* combined fields:
  ``"RelativisticDensity"`` and ``"ScreeningInvSquared"``;
* directional fields:
  ``"MidCurrentDensityComponent"``, ``"Momentum"``, ``"MomentumDensity"``
  and ``"WeightedVelocity"`` -- these deposit one vector component and
  therefore require an explicit ``direction`` (``"x"``, ``"y"`` or ``"z"``).

A different ``direction`` or ``field`` produces a separate grid field;
the direction is part of the stored field name
(e.g. ``electrons_all_weightedVelocity/x``).
For a directional field, omitting ``direction``
(or passing one to a non-directional field) is a validation error.

Use :class:`~picongpu.picmi.diagnostics.AverageDerivedFieldDump`
to store the cell-wise *average* of a built-in field instead of its sum
it is the total weighted value divided by the number of contributing
particles (the C++ ``AverageAttribute`` operation).
This is physically meaningful for per-particle quantities such as
``"WeightedVelocity"`` or ``"Momentum"``; averaging a scalar per-cell
quantity such as ``"Density"`` reduces it to a value of about 1
and PIConGPU emits a warning for those fields.

Both classes accept the same ``species``
(a :class:`~picongpu.picmi.species.Species` or a
:class:`~picongpu.picmi.particle_functor.FilteredSpecies`) and ``period``
as :class:`~picongpu.picmi.diagnostics.DerivedFieldDump`,
and support the built-in set only -- arbitrary expressions still go through
:class:`~picongpu.picmi.diagnostics.DerivedFieldDump`.

.. note::

   Above, ``electrons`` is a plain species, but a
   :class:`~picongpu.picmi.particle_functor.FilteredSpecies` restricts the
   deposition to the selected particles, exactly as for
   :class:`~picongpu.picmi.diagnostics.DerivedFieldDump`.

Output files
------------

Each diagnostic's ``options`` (an ``OpenPMDConfig``)
determines the file it writes to:

* all openPMD files are written into ``simOutput/openPMD/``;
* the full file name is ``<file><infix>.<ext>``,
  with defaults ``infix="_%06T"`` (zero-padded iteration number)
  and ``ext="bp5"`` (the BP5 backend, the fastest one available;
  ``"h5"`` for HDF5 is also common);
* diagnostics that share an *equal* ``options``
  (and therefore the same file)
  are grouped into a single openPMD plugin --
  in the example above, the particle dump, the electric field
  and the derived field all use the default ``file="simData"``,
  so they are stored together in ``simData_%06T.bp5``.

For every group of shared options,
the input file generation writes an openPMD configuration file
to ``etc/`` of the setup directory (a TOML file,
referenced from the generated ``N.cfg`` via ``--openPMD.pluginConfig``).
It lists, per time step, which fields and particles are written:

.. literalinclude:: ../../snippets/selected_topics/openpmd.py
   :language: python
   :start-at: for config in sorted

.. note::

   The example above prints the generated configuration files.
   In a real setup directory, look for
   ``etc/openPMD_config_*.toml`` --
   the suffix is a hash of the configuration content,
   so the name changes when you change the diagnostics.

``OpenPMDConfig`` parameters
----------------------------

* ``file``:
  the file name base (required);
  an absolute path writes outside of ``simOutput/openPMD/``.
* ``infix``:
  inserted between file name and extension;
  the default ``"_%06T"`` makes each time step a separate file.
  Use ``infix=""`` to append to a single file (not recommended for parallel runs).
* ``ext``:
  the openPMD backend, ``"bp5"`` (default) or e.g. ``"h5"``.
* ``range``:
  restrict the dumped region to a cell range
  (a ``RangeSpec`` with one entry per dimension;
  each entry is ``None`` (full extent), a single cell index
  or a ``(start, stop)`` pair --
  e.g. ``RangeSpec((10, 20), None, None)`` dumps cells 10-20 in ``x`` only);
  the default is the full grid.
* ``data_preparation_strategy``:
  ``"mappedMemory"`` (default) or ``"doubleBuffer"``
  (lower memory, but the output of one step is only available after the next).
* ``backend_config``:
  additional openPMD backend options that are not exposed here,
  passed as an inline TOML/JSON configuration rather than a file path
  (rendered into the plugin's ``backendConfig`` setting).
