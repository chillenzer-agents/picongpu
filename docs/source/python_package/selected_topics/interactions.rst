Interactions
============

Interactions describe the physics that acts on your particles
*in addition to* the electromagnetic fields
the solver provides:
ionization, binary collisions and radiation reaction.
There are two entry points:
the PIConGPU-specific ``picongpu_interaction`` parameter,
which takes the concrete interaction objects documented below,
and the PICMI-standard
:meth:`~picongpu.picmi.simulation.Simulation.add_interaction`,
which accepts field ionization
(the standard
:class:`~picongpu.picmi.interaction.ionization.fieldionization.PICMI_FieldIonization`,
converted to the matching concrete model)
as well as PIConGPU's own interaction objects.

.. code-block:: python

   sim = picmi.Simulation(max_steps=100, solver=solver, picongpu_interaction=[...])

.. note::

   ``add_interaction()`` accepts only field ionization
   and PIConGPU's own interaction types;
   other PICMI-standard interaction types still raise an
   ``UnsupportedFeatureError``.
   The generic ``picongpu_interaction`` parameter accepts them all.

Each interaction is attached to the species it acts on
(and, where applicable, creates new species);
the species themselves are added to the simulation
as usual via ``add_species``.

.. _ionization:

Ionization
----------

An ionization model couples an *ion species*
(an element species with a fixed ``charge_state``)
to an *electron species* that receives the freed electrons.
In a typical setup the electron species starts out empty
(``initial_distribution=None``)
and is populated purely by ionization.
Each model is one of:

:class:`~picongpu.picmi.interaction.ionization.fieldionization.ADK`
   ADK tunnel ionization
   (``ADK_variant`` selects ``picmi.ADKVariant.LinearPolarization``
   or ``picmi.ADKVariant.CircularPolarization``).
   This is the model of the :ref:`LWFA tutorial <python_package/tutorial:Tutorial: Setting up a simple LWFA>`.

:class:`~picongpu.picmi.interaction.ionization.fieldionization.BSI`
   Barrier suppression ionization;
   ``BSI_extensions`` (a tuple, required -- pass ``()`` to use the plain
   model without extensions) adds
   ``picmi.BSIExtension.StarkShift`` or ``picmi.BSIExtension.EffectiveZ``.

:class:`~picongpu.picmi.interaction.ionization.fieldionization.Keldysh`
   The quantum Keldysh model, which interpolates between
   tunnel (ADK) and multiphoton ionization.

All of them take a **required** ``ionization_current`` argument,
which selects how the ionization current
(the momentum carried away by the electrons)
is treated for energy conservation
(pass ``None`` to disable it).
A non-``None`` choice is bridged to the corresponding pypicongpu
ionization-current model and applied in the rendered output;
an unknown current that cannot be converted raises an error instead of
being silently dropped.

.. literalinclude:: ../snippets/selected_topics/interactions.py
   :language: python
   :start-after: BEGIN-INTERACTIONS-ADK
   :end-before: END-INTERACTIONS-ADK

The same snippet also shows the BSI variant:

.. literalinclude:: ../snippets/selected_topics/interactions.py
   :language: python
   :start-after: BEGIN-INTERACTIONS-BSI
   :end-before: END-INTERACTIONS-BSI

.. note::

   ``picmi.ThomasFermi``
   (collisional ionization / electronic collisional equilibrium)
   exists in the API,
   but currently fails at input-file generation;
   it is therefore not documented here in detail.

   Deep dive:
   :ref:`the ionization models in the PIConGPU code <model-fieldIonization>`
   and :ref:`the collisional ionization model <model-collisionalIonization>`.

Standard interface
^^^^^^^^^^^^^^^^^^

The PICMI-standard field ionization object

:class:`~picongpu.picmi.interaction.ionization.fieldionization.PICMI_FieldIonization`
   A thin, standard-compatible adapter taking the standard arguments
   ``model``, ``ionized_species`` and ``product_species``,
   plus the PIConGPU-specific knobs
   ``ionization_current``, ``ADK_variant`` and ``BSI_extensions``.
   It is passed to :meth:`~picongpu.picmi.simulation.Simulation.add_interaction`
   and converted to the matching concrete model
   (``ADK``, ``BSI`` or ``Keldysh``) at add time,
   so the rest of the workflow is identical to using ``picongpu_interaction``.

The ``model`` string is matched case-insensitively against the concrete
models' ``MODEL_NAME``
(``"adk"``, ``"Adk"`` and ``"ADK"`` all select the ADK model).
Model-specific knobs are required rather than defaulted:
the ADK model requires ``ADK_variant``
and the BSI model requires ``BSI_extensions``.
As with the concrete models, a bare standard field ionization uses
``ionization_current=None``
(the C++ ``current::None`` default).

.. literalinclude:: ../snippets/selected_topics/interactions.py
   :language: python
   :start-after: BEGIN-INTERACTIONS-STANDARD
   :end-before: END-INTERACTIONS-STANDARD

.. _collisions:

Collisions
----------

Binary collisions between particle species
(Coulomb collisions with a constant or dynamically computed
Coulomb logarithm) are represented by

:class:`~picongpu.picmi.interaction.collision.Collision`
   One collision between pairs of species
   (``species_pairs`` is a list of ``(lhs, rhs)`` pairs;
   convenience constructors ``construct_one_to_all``
   and ``construct_all_to_all`` are available).
   The ``functor`` selects the physics:
   ``picmi.ConstLogCollision(coulomb_log=...)``
   or ``picmi.DynamicLogCollision()``
   (the latter requires *screening species* to compute the log from).

:class:`~picongpu.picmi.interaction.collision.CollisionalPhysicsSetup`
   An optional container that holds several collisions
   together with the ``screening_species`` and a ``numerics_config``
   (a ``CollisionNumericsConfig`` with ``precision``,
   ``cell_list_chunk_size`` and ``debug_screening_length``).
   If you pass bare ``Collision`` objects,
   they are combined into such a setup automatically;
   if you pass a setup, *all* collisions must be subsumed under it.

Deep dive:
:ref:`the binary collision model in the PIConGPU code <model-binaryCollisions>`.

.. _synchrotron:

Synchrotron Radiation
---------------------

:class:`~picongpu.picmi.interaction.synchrotron.Synchrotron`
   Couples an *electron species* to a *photon species*
   (``particle_type="photon"``; the species starts out empty
   and is populated by the radiation):
   the electrons emit synchrotron radiation
   and (optionally) receive the recoil.

.. literalinclude:: ../snippets/selected_topics/interactions.py
   :language: python
   :start-after: BEGIN-INTERACTIONS-SYNCHROTRON
   :end-before: END-INTERACTIONS-SYNCHROTRON

The optional ``synchrotron_parameters``
(a ``SynchrotronParams`` model)
exposes ``electron_recoil`` (default ``True``)
and ``min_energy``,
an energy high-pass filter for the generated photons.

Deep dive:
:ref:`the synchrotron radiation extension <synchrotronRadiation>`.
