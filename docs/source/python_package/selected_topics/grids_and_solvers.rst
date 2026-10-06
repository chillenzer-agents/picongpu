Grids and Solvers
=================

Every simulation needs a spatial domain and a field solver.
In PICMI the grid lives *inside* the solver
(the solver defines how the fields are advanced on the grid),
so the two are configured together.

.. literalinclude:: ../snippets/selected_topics/grids_and_solvers.py
   :language: python
   :start-at: grid = picmi.Cartesian3DGrid
   :end-before: simulation.write_input_file

Grids
-----

PIConGPU supports two grids:

:class:`~picongpu.picmi.grid.Cartesian3DGrid`
   A 3D Cartesian grid (3D3V).

:class:`~picongpu.picmi.grid.Cartesian2DGrid`
   A 2D Cartesian grid (2D3V);
   the position along the third axis is a fixed thickness
   (``picongpu_cell_depth_si``).
   A 3D grid can be reduced to a 2D one with ``Cartesian3DGrid.to_2d()``.

The domain of a Cartesian grid is given by

* ``number_of_cells``: the number of cells per dimension,
* ``lower_bound`` / ``upper_bound``: the extent in metres
  (**lower bound must be ``[0, 0, 0]``**),
* ``lower_boundary_conditions`` / ``upper_boundary_conditions``:
  ``"open"`` (absorbing) or ``"periodic"`` per axis.
  PIConGPU chooses boundary conditions **per axis**, so the lower and the
  upper condition of a dimension must be equal.

The cell size per dimension is derived as
``(upper_bound - lower_bound) / number_of_cells``.

Distributing over GPUs
^^^^^^^^^^^^^^^^^^^^^^

By default a simulation runs on a single GPU.
To distribute it, give the grid

* ``picongpu_n_gpus``: a list of GPU counts per dimension.
  A single number ``[N]`` distributes over ``N`` GPUs in ``y`` direction
  (the direction PIConGPU is optimized for); ``[Nx, Ny, Nz]``
  distributes over all three.
* ``picongpu_grid_dist`` (optional):
  the explicit number of cells assigned to each GPU per dimension.
  If given, each chunk must be a multiple of the super-cell size
  and the chunks must sum to ``number_of_cells``.
* ``picongpu_super_cell_size``:
  the super-cell size (default ``(8, 8, 4)``).
  The grid must be divisible by both the GPU count and the super-cell size;
  the frontend checks this and reports which dimension fails.

.. _grids_guard_cells:

Guard cells
^^^^^^^^^^^

``guard_cells`` (per axis) sets the number of guard cells.
It must be a non-negative multiple of the super-cell size;
if unset, PIConGPU's default is used.

.. _grids_particle_boundaries:

Particle boundary conditions
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The field boundary conditions above also define how the *fields* behave.
How *particles* behave at the box edges is set separately with the
PICMI-standard, per-axis particle boundary conditions:

* ``lower_boundary_conditions_particles`` /
  ``upper_boundary_conditions_particles``: a list of ``"periodic"``,
  ``"absorbing"``, ``"reflect"`` or ``"thermal"`` per axis
  (or the per-direction forms ``bc_xmin_particles``/…);
* unset axes **inherit the field boundary conditions**
  (``"open"`` becomes ``"absorbing"``, ``"periodic"`` stays ``"periodic"``);
* as for the field boundary conditions, PIConGPU chooses **per axis**,
  so the lower and the upper value of a dimension must be equal.

These grid-level conditions are the **default for every species**;
the resolved value is exposed as
``Cartesian3DGrid.picongpu_particle_boundary_conditions``
(a ``tuple`` in PICMI names, per axis).
A species can override it individually --
see :ref:`Particle boundaries <species_particle_boundaries>` on the
species page.

.. literalinclude:: ../snippets/selected_topics/particle_boundaries.py
   :language: python
   :start-after: # BEGIN-GRID
   :end-before: # END-GRID

.. note::

   ``reflect`` and ``thermal`` are only compatible with an **absorbing**
   (``"open"``) field boundary on the same axis, and ``periodic`` requires a
   **periodic** field boundary and a zero offset. The frontend enforces these
   rules when the input file is generated.

Solvers
-------

:class:`~picongpu.picmi.solver.ElectromagneticSolver` advances the electromagnetic fields.
The ``method`` selects the solver:

``"Yee"``
   The standard second-order Yee solver (fixed order).

``"Lehe"``
   The Cherenkov-free Lehe solver (fixed order).

``"CKC"``
   The extended Cole-Karkkainen-Cowan solver (fixed order).

``"other:ArbitraryOrderFDTD"``
   The arbitrary-order FDTD solver;
   ``stencil_order`` selects the order
   (it must be the same for all axes and even).

``"other:None"``
   Disables the vacuum update of E and B (no CFL limit).

Time step: ``cfl`` or ``time_step_size``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The time step is fixed by one of two equivalent quantities:

* ``solver.cfl``: the Courant-Friedrichs-Lewy number, or
* ``simulation.time_step_size`` in seconds.

Give exactly one and the other is derived from the cell size;
if you give both, they must be consistent or the frontend raises an error.
``other:None`` has no CFL limit, so any time step is legal.
Note that a 2D simulation uses the 2D CFL factor (``sqrt(2)`` on a square
grid, not ``sqrt(3)``).

Field smoothing
^^^^^^^^^^^^^^^

The current can be smoothed with :class:`~picongpu.picmi.solver.BinomialSmoother`
(passed via ``source_smoother``).
PIConGPU's binomial current deposition is a fixed, single-pass filter,
so ``n_pass`` may only be ``None``, ``1`` or an all-ones vector.
Any other field-smoother option is rejected.
