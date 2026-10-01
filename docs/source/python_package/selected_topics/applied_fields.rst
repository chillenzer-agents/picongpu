.. _applied_fields:

Applied (Background) Fields
===========================

PIConGPU supports the PICMI-standard *applied fields*, which it implements as
**background fields**:

:class:`~picongpu.picmi.applied_field.ConstantAppliedField`
   A field that is constant in space and time.
   Its components use the PICMI-standard names ``Ex``, ``Ey``, ``Ez``
   (in V/m) and ``Bx``, ``By``, ``Bz`` (in T).

:class:`~picongpu.picmi.applied_field.AnalyticAppliedField`
   A field given by Python expressions.
   Use the variables ``x``, ``y``, ``z`` (position in m) and ``t`` (time in s);
   additional keyword arguments become named parameters inside the expressions.
   The ``*_expression`` arguments are in V/m for ``E`` and T for ``B``.

Construct the field, then attach it to the simulation with
:meth:`~picongpu.picmi.simulation.Simulation.add_applied_field`:

.. literalinclude:: ../snippets/selected_topics/applied_fields.py
   :language: python
   :start-at: BEGIN-APPLIED-FIELD-CONSTANT
   :end-before: END-APPLIED-FIELD-CONSTANT

.. literalinclude:: ../snippets/selected_topics/applied_fields.py
   :language: python
   :start-at: BEGIN-APPLIED-FIELD-ANALYTIC
   :end-before: END-APPLIED-FIELD-ANALYTIC

.. literalinclude:: ../snippets/selected_topics/applied_fields.py
   :language: python
   :start-at: BEGIN-APPLIED-FIELD-ADD
   :end-before: END-APPLIED-FIELD-ADD

Influence (visibility)
----------------------

A background field is **added** to the grid ``E`` and ``B`` fields around the
particle push, so the particles feel it, while the field solver itself does not
evolve it.
Both applied-field classes accept three PIConGPU-specific influence knobs.
They carry the ``picongpu_`` prefix that marks code-specific PICMI inputs and
correspond to options of the generated PIConGPU run configuration:

``picongpu_influence_particle_pusher`` (default ``True``)
   Whether the particles feel the background, i.e. whether it is added around
   the particle push.

``picongpu_influences_plugins`` (default ``True``)
   Whether plugins see the background.

``picongpu_influences_dumps`` (default ``True``)
   Whether dumps, including checkpoints, include the background.

.. warning::

   The three knobs are **not independent**.
   Setting ``picongpu_influence_particle_pusher=False`` disables the *whole*
   background, so ``picongpu_influences_plugins`` and
   ``picongpu_influences_dumps`` then have no effect: nothing adds the
   background to the fields, and no plugin or dump can see it.
   The two visibility knobs only take effect while the pusher knob is ``True``.
   (This mirrors the underlying PIConGPU behaviour, which the Python layer
   reproduces faithfully; separating "who sees it" from "is it active" is
   deliberately left for a later change.)

.. literalinclude:: ../snippets/selected_topics/applied_fields.py
   :language: python
   :start-at: BEGIN-APPLIED-FIELD-INFLUENCE
   :end-before: END-APPLIED-FIELD-INFLUENCE

When no background field is configured, the plugin/dump options are not written
to the generated run configuration at all, so the core defaults apply unchanged.

Semantics
---------

A configured background field is **added** to the grid ``E`` and ``B`` fields
around the particle push, so the particles feel it, while the field solver
itself does not evolve it.
The expressions of an :class:`~picongpu.picmi.applied_field.AnalyticAppliedField`
are evaluated in SI units and converted to PIConGPU's internal units
(see :ref:`units`).

Constraints
-----------

* Only the **whole simulation domain** is supported so far:
  ``lower_bound`` and ``upper_bound`` must be left at their default
  (all ``None``).
  Region restriction is rejected with a ``NotImplementedError``.
* At most **one** applied field may be added to a simulation;
  a second one is rejected with a ``NotImplementedError``.
* The expressions of an :class:`~picongpu.picmi.applied_field.AnalyticAppliedField`
  may only reference the free variables ``x``, ``y``, ``z`` and ``t``
  plus the named parameters passed as additional keyword arguments.
  Any other symbol is rejected with a ``ValueError`` before code generation.
  Parameter names must not collide with ``x``/``y``/``z``/``t`` or with
  generated C++ identifiers, and must not be C++ keywords.

.. note::

   The remaining PICMI applied-field surface is not implemented:
   ``as_initial`` / ``as_injected`` and field-arithmetic options map onto
   separate C++ mechanisms and are not available here.
