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

Semantics
---------

A configured background field is **added** to the grid ``E`` and ``B`` fields
around the particle push, so the particles feel it, while the field solver
itself does not evolve it.
The expressions of an :class:`~picongpu.picmi.applied_field.AnalyticAppliedField`
are evaluated in SI units and converted to PIConGPU's internal units
(see :ref:`units`).

The Python layer renders the field expressions into the C++
``fieldBackground.param`` functors
(see ``FieldBackground.hpp``).

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
