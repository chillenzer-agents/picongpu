.. _phase-space:

Phase Space
===========

The phase-space diagnostic records a 2D histogram of a spatial coordinate
against a momentum coordinate for one species --
the standard tool to inspect the structure of your particle population
(e.g. the wake in a laser wakefield acceleration run).

.. literalinclude:: ../../snippets/selected_topics/phase_space.py
   :language: python
   :start-at: phase_space = PhaseSpace
   :end-before: sim = picmi.Simulation(

Parameters:

* ``species``:
  the species (or :ref:`filtered species <particle-filters>`) to record.
* ``period``:
  the :ref:`time steps <time-steps>` at which to write output.
* ``spatial_coordinate``:
  one of ``"x"``, ``"y"``, ``"z"`` -- the position axis of the histogram.
* ``momentum_coordinate``:
  one of ``"px"``, ``"py"``, ``"pz"`` -- the momentum axis.
* ``min_momentum`` / ``max_momentum``:
   the range of the momentum axis, given as **SI momenta in kg·m/s**
   (the frontend converts them to the plugin's internal unit ``m_species·c``);
   ``min_momentum`` must be smaller than ``max_momentum``.
   For example, ``1.0 * m_e * c`` (≈ ``2.73e-22`` kg·m/s) is one electron
   rest-mass momentum.
* ``picongpu_extension`` (optional):
   the bare openPMD filename extension, for example ``"bp"``, ``"bp5"`` or
   ``"h5"``, without a leading dot. This new option is a PIConGPU extension,
   not a parameter adopted by the PICMI standard. Omission or ``None`` leaves
   the C++ plugin default unchanged and emits no extension option.
   The value must start with an ASCII letter or digit and otherwise contain
   only ASCII letters, digits, underscores or hyphens. Python validates the
   token, not backend availability in the eventual openPMD installation.

For example, request the reference electron y/py diagnostic as:

.. code-block:: python

   from picongpu.picmi import constants
   from picongpu.picmi.diagnostics import PhaseSpace, TS

   phase_space = PhaseSpace(
       species=electrons,
       period=TS[::812],
       spatial_coordinate="y",
       momentum_coordinate="py",
       min_momentum=-50 * constants.m_e * constants.c,
       max_momentum=2000 * constants.m_e * constants.c,
       picongpu_extension="bp",
   )

Extensions are selected per diagnostic. Different diagnostics of the same
species may use different formats. The C++ CLI indexes extension values in
diagnostic order, independently for each species; all filters of a species
share that sequence. An explicit extension must therefore precede any omitted
extensions for that species. For example, ``["bp", "h5", None]`` is supported,
but ``[None, "bp"]`` is rejected during simulation conversion because omitting
the first CLI entry would incorrectly apply ``"bp"`` to the first diagnostic.
Set explicit values on the preceding diagnostics or add diagnostics with
explicit extensions first. Entries for other species do not affect this rule.
No diagnostics are automatically reordered or assigned an assumed default.

The output is written as `openPMD <https://www.openpmd.org/>`__ files
into the ``simOutput/phaseSpace/`` directory;
the openPMD backend is selected by file extension
(default: ADIOS2 (``bp5``/``bp4``) when it is available,
otherwise HDF5);
one file per species, coordinate pair and time step.
The spatial extent of the recorded region follows the particles,
so in a moving-window simulation the covered region changes with time.

.. note::

   The momentum range is fixed for the whole run.
   Choose it wide enough for the highest momenta you expect,
   or you will miss them.

   ``min_momentum``/``max_momentum`` are SI momenta (kg·m/s), *not* raw
   plugin units. The frontend divides the value you give by the species
   rest-mass momentum (``m_species·c``) before handing it to the C++
   plugin, which is what produces the dimensionless ``m_species·c``
   range shown in ``N.cfg``. Do not pass raw plugin units (a
   dimensionless multiple of ``m_species·c``) here: a value of ``2.0``
   intended as two ``m_e·c`` would be interpreted as ``2.0`` kg·m/s,
   i.e. about ``7e21`` ``m_e·c``, and every particle would fall into
   the underflow bin.
