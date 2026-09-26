.. _species:

Species, Distributions and Layouts
==================================

Adding particles to a simulation takes three components:
a **species** (what the particles are),
a **distribution** (where they are placed and how they move), and a
**layout** (their positions *within* a cell).
They are passed to the simulation together:

.. code-block:: python

   sim = picmi.Simulation(
       ...,
       species=[ion, electron],
       layouts=[ion_layout, electron_layout],
   )

.. literalinclude:: ../snippets/selected_topics/species_distributions_layouts.py
   :language: python
   :start-at: plasma = picmi.UniformDistribution
   :end-before: simulation.write_input_file

Species
-------

A :class:`~picongpu.picmi.species.Species` describes one type of particle.
Its most important parameters are:

* ``name``:
  the name of the species (also used in the output files).
  If not given, the name is derived from the particle type.
* ``particle_type``:
  the physical identity of the particle.
  This is either an element symbol (``"H"``, ``"He"``, ``"C"``, ...),
  one of the predefined particle types
  (``"electron"``, ``"positron"``, ``"proton"``, ``"anti-proton"``, ``"photon"``, ...),
  or a custom particle of the form ``"other:<name>"``
  (which then requires an explicit ``name``).
  The mass and charge of known particle types are filled in automatically.
* ``charge_state``:
  the initial charge state of an ion
  (0 for neutral, 1 for singly ionized, ...).
  Only meaningful together with an element ``particle_type``.
  Ions that can be ionized further during the simulation
  (see :ref:`Interactions <python_package/selected_topics/interactions:Interactions>`)
  must specify their initial charge state explicitly.
* ``picongpu_fixed_charge``:
  for ion species that are *not* subject to ionization,
  this fixes the charge of all their particles for the entire simulation.
* ``mass`` / ``charge``:
  override the (element-)derived mass and charge in SI units.
  This is how you define custom particles.
* ``particle_shape``:
  the particle shape used for current/charge deposition
  (default ``"quadratic"``, i.e. TSC).
* ``method``:
  the particle pusher (default ``"Boris"``;
  ``"Vay"`` and ``"Higuera-Cary"`` are relativistic variants,
  ``"LLRK4"`` adds radiation reaction).
* ``density_scale``:
  rescales the species' density relative to a shared profile
  (see below).

By default, every species is initialised **independently**: even when several
species happen to share the same distribution and layout, each one draws its
own in-cell positions.
To place several species *collectively* -- i.e. on exactly the same in-cell
positions, the standard way to build charge-neutral plasmas -- group them in a
:class:`~picongpu.picmi.multi_species.MultiSpecies`
(see :ref:`multi_species`).

.. _multi_species:

MultiSpecies: collective initialisation
---------------------------------------

A :class:`~picongpu.picmi.multi_species.MultiSpecies` is the explicit way to
request **collective (coordinated) initialisation**: all its members share one
``initial_distribution`` and are placed with a single density operation, so they
occupy exactly the same in-cell positions -- and are therefore charge-neutral by
construction, irrespective of per-member momentum or temperature.

.. literalinclude:: ../snippets/selected_topics/multi_species.py
   :language: python
   :start-after: BEGIN-MULTI-SPECIES
   :end-before: END-MULTI-SPECIES

Each member is a plain :class:`~picongpu.picmi.species.Species` and is added to
the simulation individually (typically with the same layout).
The value at each position of ``proportions`` becomes the corresponding member's
``density_scale`` (its ``DensityRatio`` on the C++ level), so a
``proportions=[1.0, 1.0]`` ion/electron pair yields a neutral plasma.

.. note::

   Collective initialisation requires the members to agree on the layout.
   In particular, two :class:`~picongpu.picmi.layout.PseudoRandomLayout`\ s
   with different ``seed``\ s are treated as distinct and are therefore
   initialised independently (deliberately non-neutral).
   See the :class:`~picongpu.picmi.layout.PseudoRandomLayout` warning for what
   the ``seed`` does and does not do.

.. warning::

   Prior to the introduction of ``MultiSpecies``, species sharing the same
   distribution *and* the same layout were merged implicitly. This heuristic has
   been removed: such species are now initialised independently and PIConGPU
   emits a ``UserWarning`` naming the affected species. Wrap them in a
   :class:`~picongpu.picmi.multi_species.MultiSpecies` to restore the previous
   charge-neutral behaviour.

.. _distributions:

Particle Distributions
----------------------

A distribution describes *where* the particles of a species are placed
(their density profile) and *how they move* initially.
All distributions take

* ``rms_velocity``:
  a 3D vector of thermal velocity spreads in m/s
  (they are converted to a temperature internally), and
* ``directed_velocity``:
  a 3D vector of a collective drift velocity in m/s.

The available distributions are:

:class:`~picongpu.picmi.distribution.UniformDistribution`
   A constant density throughout the box (``density`` in m⁻³).

   .. note::

      The ``lower_bound``/``upper_bound`` and ``fill_in`` parameters
      are not supported: setting them to non-default values raises an
      ``UnsupportedFeatureError`` at input-file generation, while the
      density fills the entire simulation box. For sub-volume densities
      use ``AnalyticDistribution``, ``GaussianDistribution`` or
      ``FoilDistribution`` instead.

:class:`~picongpu.picmi.distribution.GaussianDistribution`
   A constant-density region with Gaussian ramps at the front and the rear
   of the box (in ``y`` direction):
   ``center_front``/``center_rear`` and ``sigma_front``/``sigma_rear``
   give the position and width of the ramps,
   ``power`` the exponent (2 is Gaussian, 4 and up super-Gaussian),
   ``factor`` the (negative) scaling of the ramps,
   and ``vacuum_front`` the vacuum in front of the profile.

:class:`~picongpu.picmi.distribution.FoilDistribution`
   A thin foil of constant ``thickness`` at position ``front``
   (perpendicular to ``y``),
   with optional exponential pre- and post-plasma ramps
   (``exponential_pre_plasma_length``/``_cutoff`` and
   ``exponential_post_plasma_length``/``_cutoff``).

:class:`~picongpu.picmi.distribution.CylindricalDistribution`
   A cylinder of ``radius`` around the axis ``cylinder_axis``
   through the point ``center_position``,
   with an optional exponential pre-plasma ramp
   (``exponential_pre_plasma_length``/``_cutoff``).

:class:`~picongpu.picmi.distribution.AnalyticDistribution`
   A density given by an analytic expression
   (see :ref:`the functors page <functors>`).

The reference density used to normalize the code units is
``simulation.picongpu_base_density`` (default ``1.0e25`` m⁻³).

Layouts
-------

The layout determines the positions of the particles *within* a cell.
It is given per species via the ``layouts`` list:

:class:`~picongpu.picmi.layout.PseudoRandomLayout`
  ``n_macroparticles_per_cell`` particles per cell at pseudo-random positions.
  This is the default choice for most simulations.

:class:`~picongpu.picmi.layout.GriddedLayout`
  A regular sub-grid of ``n_macroparticle_per_cell = [nx, ny, nz]``
  positions per cell (``nx * ny * nz`` particles per cell).
  Useful for well-resolved, low-noise configurations.

:class:`~picongpu.picmi.layout.OnePositionLayout`
  A single position per cell
  (``n_macroparticles_per_cell`` particles per cell, all at the same point,
  shifted by ``in_cell_offset`` in units of the cell size).

A species that starts out empty (``initial_distribution=None``,
e.g. electrons filled by ionization) gets the layout ``None``.
Giving a layout to a species without a distribution raises an error.
