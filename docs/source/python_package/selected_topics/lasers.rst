.. _lasers:

Lasers
======

Lasers are added to a simulation via the ``lasers`` parameter:

.. code-block:: python

   sim = picmi.Simulation(max_steps=..., solver=solver, lasers=[laser])

A Gaussian pulse specified by its normalized vector potential ``a0``:

.. literalinclude:: ../snippets/selected_topics/lasers.py
   :language: python
   :start-at: laser = picmi.GaussianLaser
   :end-before: grid = picmi.Cartesian3DGrid

A simulation can carry several lasers at once;
the :ref:`tutorial <python_package/tutorial:Tutorial: Setting up a simple LWFA>`
adds a Gaussian pulse to a full setup.

Analytic fields
---------------

Several lasers can evaluate the analytic electric field they describe, which is
what PIConGPU injects for them.
:meth:`~picongpu.picmi.lasers.GaussianLaser.complex_amplitude` returns the
complex field amplitude, :meth:`~picongpu.picmi.lasers.GaussianLaser.envelope`
its absolute value, and
:meth:`~picongpu.picmi.lasers.GaussianLaser.E` the real vector field
(also available per component as ``Ex``/``Ey``/``Ez``).

Two categories of lasers
~~~~~~~~~~~~~~~~~~~~~~~~

The analytic methods do not mean the same thing for every laser:

**Category A -- derived from the focus properties.**
:class:`~picongpu.picmi.lasers.GaussianLaser`,
:class:`~picongpu.picmi.lasers.DispersivePulseLaser` and
:class:`~picongpu.picmi.lasers.TWTSLaser` describe the beam through its focus
(``waist``, ``focal_position``, ...).
For them ``E`` is *what the laser would look like in perfect vacuum* at
``(x, y, z, t)``: a complete, diffraction-aware description.
Only category-A lasers expose meaningful **bulk** properties (amplitude,
transverse and longitudinal width away from the injection surface).

**Category B -- defined by the input shape.**
:class:`~picongpu.picmi.lasers.PlaneWaveLaser` and
:class:`~picongpu.picmi.lasers.FromOpenPMDPulseLaser` are defined by the
waveform that is fed in.
For them ``E`` is *what it would look like if we fed this in* at
``(x, y, z, t)`` -- the incident waveform, not a self-consistent vacuum field.
Consequently category-B lasers must not be held to bulk-property assertions;
they are only checked at the feed-in (Huygens) surface.

Call-operator contract
~~~~~~~~~~~~~~~~~~~~~~

``E(x, y, z, t=0.0)``, ``complex_amplitude(x, y, z, t=0.0)``,
``envelope(x, y, z, t=0.0)`` and the per-component ``Ex``/``Ey``/``Ez`` follow
one contract:

* **units.** Coordinates are metres (SI), time is seconds (SI), fields are V/m.
  The methods return SI values; no unit system is involved.
* **layout.** The vector field ``E`` (and ``Ex``/``Ey``/``Ez``) is returned
  *component first*, i.e. with shape ``(3,) + x.shape``.
  ``complex_amplitude`` and ``envelope`` are scalar and have shape
  ``x.shape``.
  The inputs ``x``, ``y`` and ``z`` may be numpy arrays of equal shape
  (e.g. from ``numpy.meshgrid``) or scalars.
* **domain.** The formulas are valid for the electromagnetic field *outside*
  the laser focus on the upstream side, i.e. where the paraxial/focus-derived
  description applies.  They are not a solution of the full Maxwell system:
  the model is a scalar field times a polarization vector.

The analytic interface currently exposes the electric field only: there is no
``B`` method.  The C++ incident-field solver derives its magnetic counterpart
from ``E`` through the slowly-varying-envelope approximation, so no separate
Python formula exists.

Documented limitations
~~~~~~~~~~~~~~~~~~~~~~

The analytic ``E`` is an idealised description.  The residual mismatch against
a PIConGPU run has a **tolerance floor** from

* physical approximations: the scalar-field model drops the sub-permille
  transverse/longitudinal vector components (the polarization rotation across
  the curved wavefront) and it does not back-propagate the field from the focus
  to the Huygens surface;
* numerical artifacts: the finite-order Yee solver (numerical dispersion /
  phase-velocity error) and the sampling of the carrier and envelope.

The tests are therefore designed with a clear scale separation
``envelope >> wavelength >> cell size`` (e.g. 10 cells per wavelength and
more than a hundred samples per envelope): a *Huygens-proximate* probe a few
cells inside the injection surface can be asserted tightly (no propagation
yet), whereas *bulk* envelope properties after propagation are only compared
within a documented, looser tolerance.

The pulse is defined in the single, user-visible reference frame of the PICMI
input and the openPMD output: the pulse maximum (for a symmetric pulse, the
centroid) is at ``centroid_position`` at ``t = 0``.  ``E(x, y, z, t)`` is
evaluated in that frame, so it reproduces the field written to the result
files directly.  The Huygens-surface timing used internally by the PIConGPU
core is an implementation detail of the translation layer and never appears in
a user-facing formula.

.. literalinclude:: ../snippets/selected_topics/laser_fields.py
   :language: python
   :start-after: # BEGIN-LASER-FIELDS
   :end-before: # END-LASER-FIELDS

Common properties and constraints
---------------------------------

All lasers share a few properties:

* ``wavelength`` in metres,
* ``duration`` in seconds:
  for the standard Gaussian lasers (``GaussianLaser`` and the dispersive
  pulse) this is the 1/e half-width of the electric-field envelope
  (``E ~ exp(-t^2 / duration^2)``), i.e. the intensity (``E^2``) has the
  1-sigma width ``duration / 2``;
  ``PlaneWaveLaser`` and ``TWTSLaser`` instead take ``duration`` directly
  as the 1-sigma width of the intensity profile,
* ``propagation_direction`` and ``polarization_direction``:
  normalized 3D vectors.
  The propagation direction must point *into* the simulation box;
  its dominant component determines the entry face
  (see `Propagation direction and entry face`_ below).
* ``centroid_position``: the position of the pulse at time zero.
  It must be *outside* of the simulation box on the entry side
  (see `Propagation direction and entry face`_ below),
  so that the pulse enters the box during the simulation.
* the field amplitude, given by exactly one of
  ``a0`` (the normalized vector potential) or
  ``E0`` (the peak electric field in V/m);
  the other is derived.

Propagation direction and entry face
------------------------------------

A laser enters the simulation box through the coordinate face whose normal
is the dominant component of its ``propagation_direction``: the component
with the largest absolute value. A positive dominant component selects the
``Min`` face of that axis (low side), a negative one the ``Max`` face
(high side). For example ``[0, 1, 0]`` enters through ``YMin`` (the
conventional head-on case), ``[1, 0, 0]`` through ``XMin`` and
``[0, 0, -1]`` through ``ZMax``. Exactly the same rule validates
``centroid_position``: it must lie outside the box on the entry side, i.e.
the entry-axis component of the centroid must not point along the
propagation direction (``centroid[axis] * propagation_direction[axis] <= 0``).

For a genuinely diagonal direction with several equally large components
(e.g. a 45-degree incidence), the tie is resolved to the first axis in
``x``, ``y``, ``z`` order by convention, not by physics. Use a
non-symmetric direction so the dominant component is unambiguous.

The example below places three lasers on three different faces — ``XMin``,
``YMax`` and ``ZMin`` — and checks the generated incident field:

.. literalinclude:: ../snippets/selected_topics/laser_entry_faces.py
   :language: python
   :start-after: # BEGIN-LASER-ENTRY-FACES
   :end-before: # END-LASER-ENTRY-FACES

:class:`~picongpu.picmi.lasers.TWTSLaser` is the exception: it keeps its
dedicated fixed placement (always ``YMin``, plus ``ZMin``/``ZMax`` chosen
by the sign of ``laserIncidenceAngle``) and its ``+y``-only validation,
regardless of the entry-face rule above.

Laser types
-----------

:class:`~picongpu.picmi.lasers.GaussianLaser`
   A Gaussian pulse.
   Structured beams can be described with the (matching-length) arrays
   ``picongpu_laguerre_modes`` and ``picongpu_laguerre_phases``.
   By default the polarization is linear;
   circular polarization is selected via
   ``picongpu_polarization_type=picmi.lasers.PolarizationType.CIRCULAR``.

:class:`~picongpu.picmi.lasers.DispersivePulseLaser`
   A Gaussian pulse with additional dispersion parameters:
   ``picongpu_spectral_support`` (width of the spectral support),
   ``picongpu_sd_si`` (spatial dispersion),
   ``picongpu_ad_si`` (angular dispersion),
   ``picongpu_gdd_si`` (group delay dispersion) and
   ``picongpu_tod_si`` (third-order dispersion).
   It does not support Laguerre modes.

:class:`~picongpu.picmi.lasers.TWTSLaser`
   An obliquely incident, pulse-front-tilted Gaussian pulse
   for traveling-wave Thomson-scattering setups;
   ``laserIncidenceAngle`` and ``polarizationAngle`` parameterize
   the incidence relative to the ``y`` axis.
   Its placement is fixed to the ``YMin``/``ZMin``/``ZMax`` faces
   (it always enters through ``YMin``); ``propagation_direction``
   must still point into the box (positive ``y`` component).

:class:`~picongpu.picmi.lasers.PlaneWaveLaser`
   A plane wave with a temporal shape:
   a Gaussian ramp followed by a plateau of length
   ``picongpu_plateau_duration`` and a Gaussian fall-off.
   The focus is fixed at the origin
   (``focal_position`` and ``laser_nofocus_constant_si``
   are supplied by the frontend).

:class:`~picongpu.picmi.lasers.FromOpenPMDPulseLaser`
   A pulse imported from an `openPMD <https://www.openpmd.org/>`__ file
   (``file_path``, ``iteration``, ``dataset_name``, ...),
   for initial conditions that are too complex to describe analytically.

.. note::

   The PICMI-standard laser *injection method* is not supported:
   the injection method must be left at ``None``.

   ``picongpu_huygens_surface_positions`` optionally sets, per axis, the
   distance (in cells) from the global domain boundary at which the laser
   is injected; the distance must be at least the absorbing boundary size.
   The default is ``[[16, -16], [16, -16], [16, -16]]`` and rarely needs
   changing.
