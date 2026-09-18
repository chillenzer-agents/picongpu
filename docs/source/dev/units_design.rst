.. _development-units-design:

Actionable Unit Annotations Driven by External Units Packages
=============================================================

Status: **exploratory design + minimal PoC** (TT-17).

This document evaluates the use of an established, reliable *external* units
package (``pint`` / ``astropy.units`` / ``unyt`` / ``quantities``) to make the
unit annotations on pypicongpu and picmi fields *actionable*, i.e. retained
across (de)serialisation, testable, and **consistent with the other unit
systems in the codebase** (internal C++ unit traits, the openPMD unit
attributes, and picmistandard's units). It supersedes the earlier "prose only"
decision (task-13): machine-readable units are to be reintroduced **together
with concrete consumers** so they cannot be tagged dead code again.

A minimal proof of concept accompanies this document (see
:ref:`PoC scope <units-poc-scope>`), living in
``lib/python/picongpu/pypicongpu/units/`` with a single pilot field
(``species.constant.mass.Mass.mass_si``).

Background: the three unit systems that must interoperate
---------------------------------------------------------

There is no single unit concept in the codebase; three distinct ones coexist,
and conflating them is the root cause of most of the confusion:

1. **Unit *dimension*** - which physical quantity (the 7 SI base exponents,
   ``L M T I Θ N J``). System independent. This is what openPMD's
   ``unitDimension`` and PIConGPU's C++ traits use, and what the Python
   functor ``UnitDimension`` already models.
2. **Unit *convention*/*scale* of a stored number** - whether a value is SI or
   some code-interface unit (``keV``, ``m_species*c``) or unitless PIC-internal
   (``.param``). Governs numeric semantics; this is where the picmi bridge does
   explicit conversion lambdas today.
3. **SI conversion factor** (``unitSI``) - a scalar per record, *runtime*-
   derived on the C++ side from PIConGPU's configurable base-unit system
   (``sim.unit.*``). It can **never** be statically annotated in Python for
   output records.

The canonical, shared representation the design keys on is the **7-element
exponent vector in ``L M T I Θ N J`` order**, agreed on by:
``include/picongpu/traits/SIBaseUnits.hpp`` (enum ``SIBaseUnits_t``),
``include/picongpu/plugins/binning/UnitConversion.hpp`` (``makeOpenPMDUnitMap``
maps ``{L, M, T, I, theta, N, J}`` onto ``openPMD::UnitDimension``), the
pypicongpu functor ``UnitDimension``
(``lib/python/picongpu/pypicongpu/particle_functor/unit_dimension.py``), and
the picmi functor ``UnitDimension``
(``lib/python/picongpu/picmi/particle_functor/unit_dimension.py``,
``_UNIT_INDEX_MAP``).

Current state (findings)
------------------------

**Internal C++ layer (the fixed reference, never modified).**
``traits::Unit<T_Identifier>::get()`` returns the SI conversion factor vector
for a particle attribute (e.g. ``sim.unit.mass()*sim.unit.speed()`` for
momentum) and ``traits::UnitDimension<T_Identifier>::get()`` the 7-vector of
exponents (e.g. momentum ``{L=1, M=1, T=-1}``) - see ``traits/Unit.hpp`` and the
``unitless/`` manifests. ``.param`` inputs are unitless **by convention**: the
physical units live in the traits, not in the numbers. The binning plugin
(``plugins/binning/UnitConversion.hpp``) is the one place a *Python-supplied*
dimension reaches C++/openPMD: ``axis_functor.unit_dimension`` is rendered into
a ``createFunctorDescription<...>(functor, "name", std::array<double,7u>)``
and used to convert user-supplied SI bin ranges (``toPICUnits``) and to write
the openPMD ``unitSI``/``unitDimension`` attributes (``WriteHist.hpp``).

**openPMD layer.** Output records carry two attributes: ``unitSI`` (a scalar
conversion factor) and ``unitDimension`` (the 7 powers). Both are entirely
C++-side concepts fed by ``traits::Unit*`` and bridged via
``traits/PICToOpenPMD.tpp``. openPMD itself defines the attribute semantics but
no Python unit API.

**pypicongpu layer.** Units are handled by two mechanisms:

* **Prose ``Units policy:`` docstring convention** plus member docstrings such
  as ``wave_length_si: "wave length, [m]; must be > 0"``
  (``laser.py``), ``[kg]``/``[C]`` on the species constants
  (``species/constant/mass.py``, ``charge.py``). Field *names* are themselves
  machine-readable by suffix convention (``_si``). None of this survives the
  value dump except as names/docstrings.
* **The functor ``UnitDimension``** (``particle_functor/unit_dimension.py``)
  - a genuine, machine-readable, runtime-consumed channel: a 7-entry list
  model with a ``model_validator(mode="before")`` (parses the serialised C++
  ``std::array<double, 7u>{...}`` back into a list) and a ``model_serializer``
  (renders the C++ array string). It is the strongest existing anchor this
  design generalises from.

**picmi layer.** The functor ``UnitDimension`` is a first-class pydantic model
field on ``ParticleFunctor`` and is bridged to the pypicongpu ``UnitDimension``
via ``unit_vector.tolist()`` - the only unit metadata that survives model state
at functor level. Every other unit is **prose** (member docstrings such as
``GaussianDistribution.density: "particle number density, [m^-3]"`` or the
standard's own ``Field(description="... [m]")`` strings; the installed
picmistandard has no machine-readable unit API). Unit *conversions* at the
picmi -> pypicongpu bridge are explicit lambdas:

* ``diagnostics/energy_histogram.py``: ``min_energy / constants.keV`` - picmi
  takes joule (SI), the backend option takes keV.
* ``diagnostics/phase_space.py``: ``momentum_si / (mass_si * c)`` - picmi takes
  kg*m/s (SI), the backend option takes ``m_species*c``.
* ``picmi/constants.py`` exposes ``eV``/``keV`` next to the fundamental
  constants (used by the above divisions).

**Serialisation behaviour (verified).** ``model_dump(mode="json")`` retains
only *values* for plain quantity fields. Unit metadata survives in
``model_fields[].metadata`` (pydantic-native, in-session) and in the emitted
JSON schema via ``json_schema_extra`` / ``__get_pydantic_json_schema__`` - this
is the pydantic-native, serialisable unit channel. The task-07/13 round-trip
corpus guarantees value fidelity and must not regress; unit metadata is
annotative and must not change the value dumps.

Candidate external packages
---------------------------

Four established, maintained units libraries were assessed (all installed and
verified in the working venv; versions in :ref:`the appendix <units-appendix>`):

``pint``
    Lightweight, pure-Python unit system built around a central
    ``UnitRegistry``. Parses arbitrary unit *strings* (``"m"``, ``"m**-3"``,
    ``"keV"``, ``"V/m"``; custom symbols such as ``"m_species"`` only once
    registered via ``registry.define(...)``, see open question 6) and exposes
    each unit's dimensionality as a ``{base_name: exponent}`` dict over
    exactly the seven SI base measures: ``[length]``, ``[mass]``, ``[time]``,
    ``[current]``, ``[temperature]``, ``[substance]``, ``[luminosity]``. The
    dict is *insertion-ordered* (e.g. ``parse_units("keV").dimensionality``
    yields ``{'[time]': -2, '[mass]': 1, '[length]': 2}``), so it does **not**
    arrive in the canonical PIConGPU/openPMD ``L M T I Θ N J`` vector order;
    lookups into it must be **name-keyed** (as ``to_unit_dimension`` does via
    ``dict.get``), never positional, or the exponents would land in the wrong
    slots. Numeric conversion is ``ureg.Quantity(v, "keV").to("J")`` or
    ``ureg.convert(v, "keV", "J")``. Uses the post-2019 exact SI relationships
    (``1 keV == 1.602176634e-16 J``).

``astropy.units``
    A very rich, astronomy-capable quantity system (8 SI base units: it treats
    ``rad`` as an independent base dimension, so *angle is **not** dimensionless*
    by default), bundled with ``Quantity``/``Unit`` types and unit databases
    (iers, species). Decomposing to SI requires custom slicing of ``bases``/
    ``powers`` and mapping onto the 7-vector; the angle-vs-dimensionless
    difference is a **semantic mismatch with openPMD**, where angle is
    dimensionless (a field declared ``[rad]`` in astropy is a different
    dimension class than in openPMD). Heavy dependency footprint (``pyerfa``,
    ``astropy-iers-data``, ...).

``unyt``
    numpy-array-backed quantities developed by the yt project. Dimensions are
    expressed as symbolic products over the 7 base measures
    (``(length)*(mass)/(time)**2``), which map cleanly onto the 7-vector, but
    the ``Quantity`` API is coupled to ndarrays; its molecular/energy
    conversion constants lag the 2019 redefinition slightly
    (``1 keV -> 1.602176562e-16 J``). Depends on ``sympy``, ``numpy``,
    ``packaging``.

``quantities``
    The smallest and oldest of the four. Works fine for basic conversion
    (``Quantity(1, "keV").rescale("J")``) but its constants predate the 2019 SI
    redefinition (``1 keV -> 1.60217653e-16 J``) and the project is only
    sporadically maintained.

Evaluation against the three consumer unit systems
--------------------------------------------------

Legend: ``+`` native/smooth, ``~`` needs a thin mapping layer, ``-`` poor/absent.

.. list-table:: External library vs. PIConGPU unit systems
   :header-rows: 1
   :widths: 16 30 30 34

   * - Library
     - Internal C++ traits
       (7-vector ``LMTIΘNJ``)
     - openPMD ``unitSI`` / ``unitDimension``
     - picmi units (conversion lambdas)
   * - ``pint``
     - ``+`` - dimensionality is a dict over exactly the seven SI base
       measures; name-keyed map into the 7-vector
     - ``+`` - identical base measures/ordering as openPMD
       ``unitDimension``; ``unit_dimension(unit)`` is the 7-vector;
       ``unitSI`` stays C++-side
     - ``+`` - converts keV<->J, m<->cm, V/m<->kV/cm out of the box;
       custom symbols (``m_species``) via registry ``define(...)``
   * - ``astropy.units``
     - ``~`` - bases/powers must be sliced and order-matched to the
       7-vector
     - ``-`` - extra ``rad`` base dimension makes angle-vs-dimensionless a
       mismatch with openPMD
     - ``~`` - rich conversions but different semantics for angles; heavy
       dependency
   * - ``unyt``
     - ``~`` - symbolic base measures map onto the 7-vector
     - ``~`` - clean 7-base symbolic dimensions but API is
       ndarray-coupled
     - ``~`` - ndarray-coupled API; slight constant drift vs 2019 SI
   * - ``quantities``
     - ``~`` - basic dimensional information only
     - ``~`` - basic mapping possible
     - ``-`` - mostly unmaintained; pre-2019 constants

On every axis that matters here the deciding rows are the first: pint's base
dimension set **is** the openPMD/PIConGPU 7-vector with identical name set and
semantics, its string parser covers the unit spellings the codebase uses once
written in canonical pint form (``keV``, ``V/m``, ``rad`` as dimensionless),
and it brings the runtime conversion that the picmi bridge currently
hard-codes by hand - all without dragging in astronomy-specific or
ndarray-coupled semantics that would need to be undone to talk to openPMD.

.. note:: **Canonical unit spellings.** pint needs *pint* spellings, not the
   prose-idiom ones used in the codebase's docstrings. The bracket notation
   ``[m^-3]`` (as in ``GaussianDistribution.density: "...[m^-3]"``) is **not**
   pint-parsable (a ``TokenError``) - use the canonical ``m**-3`` instead.
   Custom call-site symbols (``m_species*c``) are undefined until registered
   in a configured registry (open question 6). The PoC guards against this:
   ``to_unit_dimension`` (and hence ``Unit`` schema emission) raises a clear
   ``ValueError`` for such strings instead of surfacing the raw pint error.

Recommended mechanism
---------------------

Combine two cooperating layers:

1. **A pydantic-native ``Unit`` metadata marker**
   (``Annotated[float, Unit("m")]``) carrying the machine-readable payload:

   * ``unit`` - the unit *string* (pint-parsable; survives as plain data).
   * ``dimension`` - the openPMD/PIConGPU **7-vector**, derived *from pint*
     (``to_unit_dimension("kg") == [0, 1, 0, 0, 0, 0, 0]``).
   * ``scale`` - the *value convention* (``"SI"`` default; ``"keV"`` for the
     code-interface units the picmi bridge converts to).

   The PoC enforces the *unit/scale consistency invariant*: ``unit`` must be
   pint-parsable, and ``scale="SI"`` requires an SI-convention unit string
   (no residual scale factor, so ``Unit("keV", scale="SI")`` raises a
   ``ValueError`` instead of emitting contradictory schema metadata). Non-``SI``
   ``scale`` values are documentative convention markers and deliberately left
   unchecked (subject to open question 3).

   It is metadata-only: it adds **no** validation or serialisation, so
   ``model_dump(mode="json")`` output and the task-07 round-trip corpus are
   untouched. ``__get_pydantic_json_schema__`` emits
   ``{"unit": ..., "unit_scale": ..., "unit_dimension": [...]}`` into
   ``model_json_schema()``.

2. **pint as the runtime conversion engine.** ``convert(value, from, to)`` and
   ``to_unit_dimension(unit)`` (both thin ``pint`` wrappers) are the consumers
   that keep the annotation honest: any field's declared ``unit`` can be run
   through them, and the declared dimension can be fed directly into the
   existing functor ``UnitDimension`` (see the *functor unification* open
   question below).

This satisfies the requester's frame: **an established, reliable external
package for units** (``pint``) providing the numeric/dimensional machinery, and
a **pydantic-native metadata layer** providing the actionable annotation whose
serialisable payload is the exact openPMD-compatible 7-vector - one "unit of
units" across picmi, pypicongpu, C++ and openPMD.

Why not a pure ``Annotated`` tag without pint, and why not pint-only:
a hand-rolled tag (the earlier ``SI("m^-3")`` design) duplicated dimensional
arithmetic that a ten-year-mature external library already gets right and,
crucially, had no consumer. pint-only (values as ``pint.Quantity`` in every
model) would thread a heavy, serialisation-hostile type through ~hundreds of
fields and would fight ``model_dump`` value fidelity. The split keeps values
plain and puts all unit *logic* behind one well-tested external dependency.

.. _units-poc-scope:

PoC scope
---------

Implemented on this branch (clearly marked **EXPLORATORY PoC**, module
``lib/python/picongpu/pypicongpu/units/``):

* ``Unit`` - the pydantic metadata marker (unit string + ``scale``), with JSON-
  schema emission of ``unit``/``unit_scale``/``unit_dimension``. Construction
  is guarded by a PoC-level consistency check: ``unit`` must be pint-parsable
  and ``scale="SI"`` must pair with an SI-convention unit (see above).
* ``to_unit_dimension(unit)`` - seven-SI-vector derivation via pint; raises a
  clear ``ValueError`` for unparseable (e.g. prose-bracket) unit strings.
* ``convert(value, from_unit, to_unit)`` - pint conversion.
* One pilot field: ``species.constant.mass.Mass.mass_si`` annotated
  ``Annotated[float, Field(ge=0.0), Unit("kg")]``. Verified:

  * ``Mass.model_json_schema()["properties"]["mass_si"]`` carries
    ``unit="kg"``, ``unit_scale="SI"`` and
    ``unit_dimension=[0,1,0,0,0,0,0]``;
  * the value dump is unchanged (``{"mass_si": ...}``) and round-trips.

Tests (``lib/python/test/picongpu/quick/pypicongpu/test_units.py``, free-
function pytest): dimension derivation for ``m``, ``m**-3``, ``keV`` and
dimensionless (plus a clear error for unparseable spellings); keV->J
conversion; metadata round-trip of ``Unit``; the ``scale="SI"``-vs-unit
consistency check; the pilot field's schema emission in both pydantic's
``mode="validation"`` (default) and ``mode="serialization"`` - the latter is
what the real schema consumer ``renderedobject.py`` uses; value-dump/round-trip
invariance; the pint-derived vector feeding the existing functor
``UnitDimension``.

Deliberately out of scope (future work): annotating the full model corpus
(lasers, grid, all species constants), openPMD-read-side consumption, a
persistence sidecar, and any C++ change (none needed - the 7-vector maps 1:1
onto ``UnitConversion.hpp``/openPMD already).

Migration path
--------------

* Keep ``pint`` as an ordinary dependency (already listed in
  ``lib/python/pyproject.toml``; no API is exposed to users, so no version pin
  beyond what is there today).
* Annotate pypicongpu first, one module per pass (lasers, grid, species
  constants), then mirror into the pydantic picmi models; keep the standard's
  prose ``description`` strings (the implemented SEP convention) and derive a
  docstring<->metadata **cross-check test** so the two cannot drift.
* Cross-check the picmi bridge conversion lambdas against the declared
  ``scale`` (e.g. an EnergyHistogram field declared ``scale="J"`` while the
  backend option is ``keV`` documents/verifies the existing division by
  ``constants.keV``).
* Later, drive ``to_unit_dimension`` output into the existing functor
  ``UnitDimension`` call sites so the C++-consumed dimension and the schema-
  emitted dimension provably come from the same expression.

Open questions
--------------

1. **Persistence target.** Schema-only (``model_json_schema``, cheapest; the
   schema is plain JSON and survives as an on-disk artifact) vs. a sidecar
   unit map written next to the rendering-context JSON vs. embedding the map in
   the simulation metadata. Schema-only is enough for introspection; a sidecar
   is what makes the units survive the full on-disk pipeline.
2. **Strict vs lenient coverage.** Require every quantity field to declare
   machine-readable units (with the docstring cross-check test) in one sweep,
   or annotate the pilot set first and grow incrementally? Strict matches
   "handle all instances of a pattern once tagged"; lenient is lower-risk now.
3. **``scale`` granularity.** Store just the unit string + 7-vector, or also an
   explicit SI conversion factor for code-interface units (``keV``,
   ``m_species*c``) so the picmi bridge conversions can be *derived/verified*
   from metadata? The latter is where pint earns its keep at runtime.
4. **Functor unification.** Should ``Unit`` also author the functor
   ``UnitDimension`` value (one expression ``Unit("M*L/T")`` producing both the
   schema 7-vector and the C++-consumed functor dimension), or keep the two
   mechanisms separate (functor dimension is consumed by C++, field annotation
   is introspection)? The PoC already shows the vector flows into the functor
   unchanged.
5. **Shared location.** One shared ``Unit``/``to_unit_dimension``/``convert``
   helper in ``pypicongpu.units`` used by both pypicongpu and picmi (picmi
   already imports pypicongpu - safe), vs. separate mirrors. Prefer shared;
   confirm no layer-inversion concern.
6. **pint registry configuration.** Whether to ship a single configured
   ``UnitRegistry`` (defining call-site symbols such as ``m_species``, PIC-internal
   units, and non-SI contexts) centrally, to keep unit strings stable across the
   codebase instead of relying on pint's defaults per module.

.. _units-appendix:

Appendix: verified library facts (2026-09-07, working venv)
-----------------------------------------------------------

* ``pint 0.25.3`` - ``parse_units("keV").dimensionality`` is
  ``{'[time]': -2, '[mass]': 1, '[length]': 2}``; ``ureg.convert(1, "keV", "J")
  == 1.602176634e-16``; light deps (``flexparser``, ``typing-extensions``).
* ``astropy 8.0.1`` - ``u.si.bases`` is ``{kg, K, rad, A, m, mol, cd, s}`` (8
  bases incl. ``rad``); ``(1*u.keV).to(u.J) == 1.602176634e-16``; heavy deps.
* ``unyt 3.1.0`` - ``keV`` dimension ``(length)**2*(mass)/(time)**2``;
  ``(1*unyt.keV).to("J") == 1.602176562e-16`` (pre-2019-constant drift); deps
  ``numpy``, ``packaging``, ``sympy``.
* ``quantities 0.16.4`` - ``Quantity(1, "keV").rescale("J") ==
  1.60217653e-16`` (pre-2019-constant drift); deps ``numpy``; low maintenance.
* ``pint`` is already a declared dependency of the Python package
  (``lib/python/pyproject.toml``).
* The 7-dimensional ordering used here is the one PIConGPU and openPMD agree
  on: ``include/picongpu/traits/SIBaseUnits.hpp`` (length, mass, time,
  electric current, thermodynamic temperature, amount of substance, luminous
  intensity = indices 0..6) mirrored by
  ``include/picongpu/plugins/binning/UnitConversion.hpp``
  (``{L, M, T, I, theta, N, J}``) and openPMD's ``unitDimension`` attribute.
