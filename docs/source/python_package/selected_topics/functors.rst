.. _functors:

Functors, Particle Functors and Filters
=======================================

Beyond the built-in distributions, PIConGPU can build quantities from
particle properties symbolically.
The same machinery is used for **analytic density profiles**,
**particle functors** (quantities computed per particle) and
**particle filters** (functor-valued predicates that select particles).

Analytic densities
------------------

The most direct use is an analytic density:
:class:`~picongpu.picmi.distribution.AnalyticDistribution`
describes three field families symbolically as functions of the three sympy
symbols ``x``, ``y``, ``z`` (in SI units):

* the density ``density_*`` (in SI units), and -- both optional, defaulting to
  no drift and no thermal spread -- the per-axis momentum ``momentum_*``
  (``gamma * velocity`` in m/s) and the per-axis momentum spread
  ``momentum_spread_*`` (a Gaussian thermal sigma in m/s).

The expressions are compiled into the simulation binary and evaluated on the
GPU at runtime. The three families are treated on the same footing: each can be
given as a sympy-parseable string, as a sympy callable, or read back as a parsed
sympy expression, and all three share the same keyword substitution.

The string spelling uses ``density_expression``, ``momentum_expressions`` and
``momentum_spread_expressions`` (the latter two are lists aligned per axis;
``None`` marks an axis that is not supplied). The strings are string-normalised
(as in the PICMI standard) and parsed with ``sympy.sympify``, so non-string
values are coerced to their string form (a bare number gives a constant):

.. literalinclude:: ../snippets/selected_topics/analytic_distribution.py
   :language: python
   :start-after: BEGIN-FIELD-EXPRESSIONS
   :end-before: END-FIELD-EXPRESSIONS

The callable spelling uses ``density_function``, ``momentum_functions`` and
``momentum_spread_functions`` with the same per-axis alignment. Provide exactly
one of the string or the callable spelling per field; the other is computed from
it, so after construction both are available and consistent. The two spellings
are interchangeable and describe the same distribution:

.. literalinclude:: ../snippets/selected_topics/analytic_distribution.py
   :language: python
   :start-after: BEGIN-FIELD-FUNCTIONS
   :end-before: END-FIELD-FUNCTIONS

The parsed sympy expressions are exposed as the public ``density_sympy``,
``momentum_sympy`` and ``momentum_spread_sympy`` properties (e.g. for inspection
or LaTeX export):

.. literalinclude:: ../snippets/selected_topics/analytic_distribution.py
   :language: python
   :start-after: BEGIN-FIELD-SYMPY
   :end-before: END-FIELD-SYMPY

Constants used in any of the expressions may be passed as additional keyword
arguments; they are collected automatically into ``user_defined_kw`` and
substituted before rendering, uniformly across the three families, mirroring
the PICMI standard. For an expression string, any identifier that appears in it
may be given this way. For a callable, only the extra parameters explicitly
named in the signature beyond ``x``, ``y`` and ``z`` are bound this way, and the
matching keyword arguments give their values:

.. literalinclude:: ../snippets/selected_topics/analytic_distribution.py
   :language: python
   :start-after: BEGIN-FIELD-KWARGS
   :end-before: END-FIELD-KWARGS

Momentum and momentum spread are rendered into the constant pypicongpu
``Drift`` and ``Temperature`` operations. Position-dependent (function of
``x``/``y``/``z``) momentum and spread expressions are not implemented yet and
raise an ``UnsupportedFeatureError`` at input-file generation. ``directed_velocity``
(a plain velocity) and ``rms_velocity`` are combined with the standard
parameters (``rms_velocity`` takes the per-axis maximum of itself and the
constant spread expressions). ``directed_velocity`` and ``momentum_expressions``
are mutually exclusive ways of setting the drift; supplying a non-zero
``directed_velocity`` together with a ``momentum_expressions`` entry raises.
An axis without a momentum expression falls back to ``directed_velocity``. The
standard's ``lower_bound``, ``upper_bound`` and ``fill_in`` are not supported and
raise if set to non-default values.

Use ``sympy.Piecewise`` for conditional profiles.

The same symbolic machinery is the natural building block for other
user-supplied, code-level expressions;
free-form lasers, for instance, are expected to reuse it later.

.. _particle-functors:

Particle functors
-----------------

A :class:`~picongpu.picmi.particle_functor.ParticleFunctor`
is a Python function of one (or two) arguments
that describes a particle property symbolically.
It is used as a decorator, and its first argument must be annotated with the
particle flavour it operates on --
:class:`~picongpu.picmi.particle_functor.MacroParticle` (the default) or
:class:`~picongpu.picmi.particle_functor.PhysicalParticle`.
A minimal (tested) example is shown at the end of this section:

.. literalinclude:: ../snippets/selected_topics/particle_functors.py
   :language: python
   :start-after: BEGIN-PARTICLE-FUNCTOR
   :end-before: END-PARTICLE-FUNCTOR

The ``particle`` argument provides access to the particle's attributes
through ``particle.get("...")``:

* ``"position"``:
  a 3D vector; the keyword arguments ``origin``
  (``"total"`` (default), ``"local"``, ``"global"``,
  ``"moving_window"`` or ``"local_with_guards"``),
  ``precision`` (``"cell"`` (default) or ``"sub_cell"``)
  and ``unit`` (``"cell"`` (default), ``"pic"`` or ``"si"``)
  select the reference frame, the resolution and the units.
  (``"cell"`` is only available as an ``origin`` for derived-field and
  filter functors, not for binning functors.)
  With ``unit="cell"`` the value is a dimensionless cell coordinate,
  ``unit="si"`` is already converted to metres, and ``unit="pic"`` is in
  internal PIConGPU length units.  The generated ``getUnit()`` is a single
  scalar, so for ``"pic"`` it assumes an isotropic cell size; anisotropic
  cells are not represented per axis.
* ``"momentum"`` / ``"momentumPrev1"``:
  the 3D momentum (index it as
  ``px, py, pz = particle.get("momentum")``).
* ``"mass"``, ``"charge"``, ``"weighting"``:
  the particle's mass, charge and statistical weight.
* ``"gamma"``, ``"kinetic energy"``, ``"velocity"``:
  derived quantities, computed from mass and momentum.
* ``"damped_weighting"``:
  the weighting after applying the optional damping factor; the raw stored
  factor is available separately as ``"weightingDampingFactor"``.
* ``"timestep"`` / ``"timestep_size"``:
  the current iteration and the timestep size.  These are only available to
  binning functors, because only they receive the required ``domainInfo``.

All remaining predefined stored attributes are available by name.  Their value
type, component count, unit and weighting scaling come from a hand-maintained
Python registry that mirrors
``include/picongpu/param/speciesAttributes.param`` and
``include/picongpu/unitless/speciesAttributes.unitless``:

.. list-table::
   :header-rows: 1

   * - name
     - value type
     - notes
   * - ``"particleId"``
     - ``uint64_t``
     - unique macroparticle identifier
   * - ``"charge_state"``
     - ``float_X``
     - stored as ``boundElectrons``; requires an ion species with element
       atomic numbers (``atomicNumbers``, e.g. an element ``particle_type``
       plus an ionization model)
   * - ``"weightingDampingFactor"``
     - ``float_X``
     - optional raw damping factor (see ``"damped_weighting"`` above)
   * - ``"totalCellIdx"``
     - ``DataSpace<simDim>``
     - total cell index; index it per spatial axis
       (``particle.get("totalCellIdx")[0]`` in x), so only the first
       ``simDim`` components exist (three in 3D, two in 2D)
   * - ``"radiationMask"``, ``"transitionRadiationMask"``
     - ``bool``
     - **internal**: masks owned by the radiation plugins
   * - ``"probeE"``, ``"probeB"``
     - ``float3_X``
     - **internal**: interpolated fields owned by the probe plugin
   * - ``"atomicStateCollectionIndex"``, ``"processClass"``,
       ``"transitionIndex"``, ``"binIndex"``, ``"accepted"``
     - ``uint32_t`` / ``uint8_t`` / ``bool``
     - **internal**: atomic-physics bookkeeping

The vector attributes (``position``, ``momentum``, ``momentumPrev1``,
``probeE``, ``probeB``, ``totalCellIdx``) return a plain tuple, so they can be
indexed or unpacked just like ``momentum`` (``x, y, z =
particle.get("probeE")`` or ``ex = particle.get("probeE")[0]``); the tested
example below uses the indexed form.

A derived-field functor may also return the whole vector
(``return particle.get("probeE")``); its return type is then the registry's
C++ vector type.  Binning and filter functors must reduce it to a scalar
component.

The aliases and flags from ``speciesAttributes.param`` are **not** particle
attributes and are deliberately excluded: ``shape``, ``particlePusher``,
``interpolation``, ``current``, ``synchrotron``, ``ionizers``,
``ionizationEnergies``, ``atomicNumbers``, ``effectiveNuclearCharge``,
``atomicPhysicsParticle``, ``massRatio``, ``chargeRatio``, ``densityRatio``,
``exchangeMemCfg`` and ``boundaryCondition``.  Configure those through the
species or diagnostic API instead.

.. literalinclude:: ../snippets/selected_topics/particle_functors.py
   :language: python
   :start-after: BEGIN-EXTENDED-ATTRIBUTES
   :end-before: END-EXTENDED-ATTRIBUTES

The function body is written with `sympy <https://www.sympy.org/>`__
expressions -- it is never executed as plain Python,
but *symbolically* (with dummy particle attributes)
and the resulting expression tree is compiled into the simulation binary,
where it is evaluated on the GPU.
The functor's ``name`` defaults to the function name;
use ``@ParticleFunctor(name="...")`` to override it.
Use ``return_type`` (e.g. ``int``) when the annotation of your function
is not enough, and ``unit_dimension``
(a :class:`~picongpu.picmi.particle_functor.UnitDimension`)
to declare the physical unit of the result.

Single-particle semantics
-------------------------

Every functor is *implemented* on macroparticles, but the type annotation of
its first argument declares what the returned quantity *means*:

* :class:`~picongpu.picmi.particle_functor.MacroParticle`
  (also the default when no annotation is given) is a macro-particle,
  weighting-scaled property -- this is what the accessors produce as-is.
* :class:`~picongpu.picmi.particle_functor.PhysicalParticle`
  interprets the result as a single-particle property.
  The generated code symbolically divides the weighting out of the
  scaling-sensitive symbols (``"mass"``, ``"charge"``,
  ``"kinetic energy"``, and ``"charge_state"`` / ``boundElectrons``), so
  e.g. a mass functor returns the physical particle mass rather than the
  macroparticle mass.  Per-particle quantities such as momentum, velocity,
  position and ``"damped_weighting"`` are already unaffected.
  The C++ ``WeightingPower`` trait of ``momentum``, ``momentumPrev1`` and
  ``weighting`` is ``1`` (their macro-particle bookkeeping), but they are
  deliberately *not* divided by the weighting here: momentum is taken as an
  already per-particle quantity, and dividing the weighting by itself would
  be meaningless.  These exceptions live in the registry
  (``physical_weighting_power``), which is the single source of truth for
  the rescaling.

.. literalinclude:: ../snippets/selected_topics/particle_functors.py
   :language: python
   :start-after: BEGIN-PHYSICAL-PARTICLE
   :end-before: END-PHYSICAL-PARTICLE

A quantity that is *not* a pure per-particle property but still scales with a
known power of the weighting (e.g. a density) can set
``scales_with_weighting`` on a ``PhysicalParticle`` functor.
Setting it **replaces** the automatic per-symbol rescaling described above
rather than adding to it: the automatic ``/weighting`` of ``"mass"``,
``"charge"`` and ``"kinetic energy"`` is switched off and, instead, the
*whole* returned expression is scaled by ``weighting**(-scales_with_weighting)``.
In the example in this section, adding ``scales_with_weighting=2`` to the mass
functor therefore yields ``mass/weighting**2`` -- **not**
``weighting**2 * mass/weighting``: the automatic division is *not* applied in
addition.
``scales_with_weighting`` is only allowed on ``PhysicalParticle`` functors and
is the manual escape hatch for quantities the automatic per-symbol rescaling
cannot express.

If the functor's result has a physical unit, declare it with the
``unit_dimension`` (see :ref:`units`); the generated derived-field trait then
reports it through ``getUnit()`` / ``getUnitDimension()``.
For pure monomial quantities these are derived automatically from the
7-component unit vector, matching the built-in derived attributes.
``unit_factor`` is an optional escape hatch for the cases the automatic
derivation cannot handle: it gives the numeric scale factor returned by
``getUnit()`` (the openPMD ``unitSI`` factor, i.e. the value of one internal
unit in SI units). It defaults to ``None``, meaning "derive the
``sim.unit.*`` monomial from ``unit_dimension``"; setting it overrides that
derivation. It accepts a number (implicitly converted), a sympy expression,
or a :class:`~collections.abc.Callable` returning one, and is rendered
through the same ``PMAccPrinter`` as the rest of the functor interface -- like
the ``AnalyticDistribution`` expressions, there are **no C++ code strings** in
the interface. Use it when the dimension is not a pure monomial -- it has
a temperature, amount-of-substance or luminous-intensity component, or a
non-integer exponent -- because such a dimension cannot be turned into a
numeric scale, and input-file generation raises instead.
A typical case is a count/density quantity whose unit carries the
macro-particle weighting ``N_ppm``. As a number you would write e.g.
``unit_factor=1e6`` when one internal unit corresponds to :math:`10^6` SI
units; if the factor itself must reference an internal unit expression, pass a
sympy expression built from ``sympy.Symbol("sim.unit.mass()")`` and friends
(rendered verbatim by the printer).

.. literalinclude:: ../snippets/selected_topics/particle_functors.py
   :language: python
   :start-after: BEGIN-UNIT-FACTOR
   :end-before: END-UNIT-FACTOR

Because a functor or filter accesses concrete particle attributes, using one
with a species registers those attributes on that species (via
``Species.register_requirements``): a functor reading ``"momentumPrev1"``, for
instance, adds the ``momentumPrev1`` attribute to the species it is used with,
so the attribute need not be declared by hand.  The registry drives this
registration, so every attribute listed above (including the internal ones) is
registered automatically.  Registering a plugin-internal attribute only
allocates its storage on the species; it does **not** enable the consuming
plugin, and it costs memory per particle — register only what a functor really
reads.

Attribute names are validated when the input file is generated.  An unknown
name raises a clear Python error instead of silently emitting an undefined C++
identifier; when a custom template directory is configured this check is
relaxed, because such templates may extend ``speciesAttributes.param`` with
attributes the Python registry cannot know about.

.. _particle-filters:

Particle filters
----------------

The same mechanism can be used to *select* particles instead of measuring them:
a :class:`~picongpu.picmi.particle_functor.ParticleFilter`
is a functor that must return a boolean,
and wrapping a species and a filter in a
:class:`~picongpu.picmi.particle_functor.FilteredSpecies`
gives a "species" that contains only the selected particles:

.. literalinclude:: ../snippets/selected_topics/particle_functors.py
   :language: python
   :start-after: BEGIN-PARTICLE-FILTER
   :end-before: END-PARTICLE-FILTER

``FilteredSpecies`` is accepted everywhere a ``Species`` is
(phase space, energy histogram, particle dump, binning, ...).
The name of the filtered species is
``<species name>_<filter name>``,
which is also what you will find in the output files.

.. note::

   Mode restrictions are enforced when the input file is generated.  Binning
   functors support ``origin`` values ``"total"``, ``"global"``, ``"local"``,
   ``"moving_window"`` and ``"local_with_guards"`` (but not ``"cell"``);
   derived-field functors support ``"local"`` and ``"cell"`` (they have no
   total-origin offset); filter functors additionally support ``"total"``.
   ``timestep`` and ``timestep_size`` are binning-only.  A functor that returns
   a whole vector from a binning axis or a filter, or uses a mode-invalid
   access, raises a Python error naming the offending attribute and mode.

   Deep dive:
   functors are compiled into the binary -- binning expressions as
   ``ALPAKA_FN_ACC`` lambdas, derived attributes (file output) as
   ``DINLINE`` call operators of generated functor structs -- in
   ``binningSetup.param`` / ``fileOutput.param``
   (see :ref:`the binning plugin documentation <usage-plugins-binningPlugin>`
   for the underlying C++ implementation).
   A functor that cannot be expressed in terms of the available
   particle attributes will fail at input-file generation
   with a message pointing at the offending expression.
