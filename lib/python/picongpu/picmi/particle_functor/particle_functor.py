"""
This file is part of PIConGPU.
Copyright 2025 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

from collections.abc import Callable, Iterable
from inspect import signature
from typing import Any, get_type_hints

from pydantic import BaseModel, PrivateAttr, computed_field, field_validator, model_validator
from sympy import Expr, Symbol, symbols, sympify

from picongpu.picmi.particle_functor.rng_arg import RNGArg
from picongpu.picmi.particle_functor.unit_dimension import UnitDimension
from picongpu.pypicongpu.particle_functor import (
    ParticleFunctor as PyPIConGPUParticleFunctor,
    UnitDimension as PyPIConGPUUnitDimension,
    generate_preamble,
)
from picongpu.pypicongpu.rendering.pmaccprinter import PMAccPrinter
from picongpu.pypicongpu.species.attribute.attribute import Attribute
from picongpu.pypicongpu.species.attribute.registry import ATTRIBUTE_REGISTRY, DERIVED_ACCESSORS
from picongpu.pypicongpu.species.attribute.weighting import Weighting
from picongpu.pypicongpu.util import alt, decorating_class, is_iterable

# Derived accessors that still require a stored attribute on the owning species
# (the others come from species constants or are always available).
_ATTRIBUTE_BY_DERIVED_NAME = {
    "damped_weighting": Weighting,
}


def _attribute_name(attribute):
    """Extract the functor-facing name from an attribute-map value."""
    return attribute[0] if isinstance(attribute, tuple) else attribute


def _attribute_spec(attribute):
    """Return the registry/derived descriptor for an attribute-map value."""
    name = _attribute_name(attribute)
    if name in ATTRIBUTE_REGISTRY:
        return ATTRIBUTE_REGISTRY[name]()
    derived = DERIVED_ACCESSORS.get(name)
    return None if derived is None else _DerivedSpec(name, **derived)


class _DerivedSpec:
    """Lightweight descriptor for a derived accessor (not an ``Attribute``)."""

    def __init__(self, name, cpp_type="float_X", n_components=1, weighting_power=0, physical_weighting_power=None):
        self.name = name
        self.cpp_type = cpp_type
        self.n_components = n_components
        self.unit = "1."
        self.unit_dimension = (0.0,) * 7
        self.weighting_power = weighting_power
        self.physical_weighting_power = physical_weighting_power
        self.access_strategy = "structured_binding"

    @property
    def component_cpp_type(self):
        if self.n_components == 1:
            return self.cpp_type
        return "float_X"


def _weighting_power(attribute):
    """Physical-particle rescaling power for an accessed attribute.

    The registry is the single source of truth: ``weighting_power`` mirrors the
    C++ trait, and ``physical_weighting_power`` encodes the few explicit
    exceptions where the single-particle meaning differs (momentum and the
    weighting itself).  ``None`` falls back to ``weighting_power``.
    """
    spec = _attribute_spec(attribute)
    if spec is None:
        return 0
    override = getattr(spec, "physical_weighting_power", None)
    return spec.weighting_power if override is None else override


# ``position`` is special: the same stored value is exposed in one of three
# units, each with a different dimension and scalar ``getUnit()`` factor.
# ``getUnit()`` returns a single float, so the (anisotropic) cell size cannot
# be represented per axis; the factor assumes an isotropic cell.
_POSITION_UNIT_METADATA = {
    # in-cell/world cell indices: dimensionless
    "cell": ((0.0,) * 7, "1."),
    # already multiplied by the SI cell size: metres
    "si": ((1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0), "1."),
    # multiplied by the PIC cell size: internal length units
    "pic": ((1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0), "sim.unit.length()"),
}


def _position_unit(expression, attribute_map):
    """Unit keyword of an exact ``position`` access, or ``None``.

    Only a bare aligned access (one component symbol, or the whole vector)
    carries an unambiguous unit; arbitrary expressions keep the explicit
    ``unit_dimension``/``unit_factor`` interface.
    """
    for key, attribute in attribute_map.items():
        if _attribute_name(attribute) != "position":
            continue
        matches = (isinstance(expression, Symbol) and isinstance(key, tuple) and expression in key) or (
            isinstance(expression, tuple) and isinstance(key, tuple) and tuple(key) == tuple(expression)
        )
        if matches:
            return attribute[-1]
    return None


_COORDINATE_SYSTEM = {
    (
        origin.lower(),
        precision.lower(),
        unit.lower(),
    ): tuple(Symbol(f"{c}_{precision.lower()}_{unit.lower()}") for c in coords)
    for (origin, coords) in (
        ("TOTAL", ("xt", "yt", "zt")),
        ("GLOBAL", ("xg", "yg", "zg")),
        ("LOCAL", ("xl", "yl", "zl")),
        ("MOVING_WINDOW", ("xmw", "ymw", "zmw")),
        ("LOCAL_WITH_GUARDS", ("xlg", "ylg", "zlg")),
        ("CELL", ("xc", "yc", "zc")),
    )
    for precision in ("CELL", "SUB_CELL")
    for unit in ("CELL", "PIC", "SI")
}


class Particle:
    """Base class for the particle argument of a functor.

    A functor declares which flavour of particle it operates on by the type
    annotation of its first parameter (``MacroParticle`` or
    ``PhysicalParticle``). This is purely semantic: every functor is
    implemented on macroparticles, but the annotation controls whether the
    returned quantity is interpreted as a macro- or a physical-particle
    property.
    """

    def get(self, attribute, **kwargs) -> Expr | Iterable[Expr]:
        NotImplementedError()

    def finalize(self, expression):
        return expression


class AbstractParticle(Particle):
    """
    Particle implementation that tracks attribute access and returns sympy symbols.
    """

    needs_total_position = False

    def __init__(self):
        self.used_attributes = {}
        self._symbol_weighting_power = {}

    def get_attribute_map(self):
        return self.used_attributes

    def _record(self, symbols, attribute, weighting_power=None):
        """Record an access and the scaling of every produced symbol."""
        self.used_attributes |= {symbols: attribute}
        if weighting_power is None:
            weighting_power = _weighting_power(attribute)
        for symbol in symbols if isinstance(symbols, tuple) else (symbols,):
            self._symbol_weighting_power[symbol] = weighting_power

    def get(self, attribute, **kwargs) -> Expr | Iterable[Expr]:
        if attribute == "position":
            origin = kwargs.get("origin", "total")
            precision = kwargs.get("precision", "cell")
            unit = kwargs.get("unit", "cell")
            self.needs_total_position = self.needs_total_position or (origin.lower() not in ["cell", "local"])
            my_symbols = _COORDINATE_SYSTEM[(origin, precision, unit)]
            self._record(my_symbols, ("position", origin, precision, unit))

        elif attribute == "momentum":
            my_symbols = symbols("px,py,pz")
            self._record(my_symbols, "momentum")

        elif attribute == "momentumPrev1":
            my_symbols = symbols("p1x,p1y,p1z")
            self._record(my_symbols, "momentumPrev1")

        elif attribute in ["gamma", "kinetic energy", "velocity"]:
            # This relies on python dictionaries having a stable ordering.
            # We first add mass and momentum and later use their symbols
            # inside of the same preamble.
            self.get("mass")
            self.get("momentum")
            if attribute == "gamma":
                my_symbols = Symbol("gamma")
            elif attribute == "kinetic energy":
                my_symbols = Symbol("Ekin")
            elif attribute == "velocity":
                my_symbols = symbols("vx,vy,vz")
            else:
                raise ValueError("Reached impossible path.")
            self._record(my_symbols, attribute)

        else:
            spec = _attribute_spec(attribute)
            if spec is not None and spec.n_components > 1:
                if getattr(spec, "access_strategy", "structured_binding") == "whole":
                    # The C++ value is bound as a whole (e.g. DataSpace<simDim>,
                    # which has no tuple protocol); index it in the expression.
                    my_symbols = tuple(Symbol(f"{attribute}_value[{i}]") for i in range(spec.n_components))
                else:
                    my_symbols = tuple(Symbol(f"{attribute}_{i}") for i in range(spec.n_components))
            else:
                my_symbols = Symbol(attribute)
            self._record(my_symbols, attribute)

        return my_symbols


class MacroParticle(AbstractParticle):
    """A functor operating directly on macroparticles.

    The returned quantity is a macro-particle (weighting-scaled) property,
    which is what the accessors produce as-is.
    """


class PhysicalParticle(AbstractParticle):
    """A functor operating on single (physical) particles.

    The implementation still acts on macroparticles, but the returned quantity
    is interpreted as a single-particle property. This is achieved by
    symbolically dividing the scaling-sensitive symbols by the weighting (or,
    via ``scales_with_weighting``, by multiplying the whole result by an
    explicit power of the weighting).
    """

    def __init__(self, scales_with_weighting=None):
        self.scales_with_weighting = scales_with_weighting
        super().__init__()

    def get(self, *args, **kwargs):
        my_symbols = super().get(*args, **kwargs)
        if self.scales_with_weighting is None:
            w = super().get("weighting")
            rescaled = tuple(
                s * (w ** (-self._symbol_weighting_power.get(s, 0)))
                for s in alt(lambda: iter(my_symbols), [my_symbols])
            )
            my_symbols = rescaled if is_iterable(my_symbols) else rescaled[0]
        return my_symbols

    def finalize(self, expression):
        if self.scales_with_weighting is not None:
            expression *= super().get("weighting") ** (-self.scales_with_weighting)
        return expression


@decorating_class("functor")
class ParticleFunctor(BaseModel):
    """
    A functor that operates on a Particle and returns a sympy expression.

    Usage as decorator::

        @ParticleFunctor
        def kinetic_energy(particle):
            return particle.get("kinetic energy")

        @ParticleFunctor(unit_dimension=M * L / T)
        def momentum_x(particle):
            return particle.get("momentum")[0]

    Or as constructor::

        pf = ParticleFunctor(functor=lambda p: p.get("weighting"), name="density")
    """

    model_config = {"arbitrary_types_allowed": True}

    _custom_templates: bool = PrivateAttr(False)
    """whether the simulation supplies a custom template directory

    Custom templates may extend ``speciesAttributes.param`` with attributes the
    registry does not know about; such unknown names are allowed in that case.
    """

    functor: Callable[[Any], Any]
    name: str | None = None
    return_type: type | str | None = None
    unit_dimension: UnitDimension | None = None
    unit_factor: Callable[[], Expr] | Expr | int | float | None = None
    scales_with_weighting: int | None = None

    @field_validator("unit_factor", mode="after")
    @classmethod
    def _render_unit_factor(cls, value):
        """Render the Python ``unit_factor`` to the C++ text of ``getUnit()``.

        Accepts ``None`` (auto-derive), a number (implicitly converted), a
        sympy expression, or a no-argument :class:`~collections.abc.Callable`
        returning one, rendered through the :class:`PMAccPrinter`. Raw strings
        of C++ code are rejected: the interface is Python expressions, not C++
        strings, consistent with the ``AnalyticDistribution`` expression surface.
        """
        if value is None or isinstance(value, str):
            if isinstance(value, str):
                raise ValueError(
                    "unit_factor must be a number, a sympy expression, or a callable "
                    "returning one -- not a string of C++ code. The expression is "
                    "rendered through the PMAccPrinter, so use sympy (and e.g. "
                    "sympy.Symbol('sim.unit.mass()') if you need an internal-unit scale)."
                )
            return value
        if callable(value):
            value = value()
        return PMAccPrinter().doprint(sympify(value))

    def _rng_classes(self) -> list[type]:
        return [
            cls
            for p in signature(self.functor).parameters.values()
            if isinstance(p.annotation, type) and issubclass((cls := p.annotation), RNGArg)
        ]

    @computed_field
    def rng_class(self) -> Callable[[Any], Any]:
        rng_classes = self._rng_classes()
        return rng_classes[0] if rng_classes else (lambda: None)

    def _particle_class(self) -> type[Particle]:
        first = next(iter(signature(self.functor).parameters.values()), None)
        if first is None:
            return MacroParticle
        annotation = first.annotation
        if isinstance(annotation, str):
            # A string (forward) reference, e.g. under ``from __future__ import annotations``;
            # resolve it in the functor's module namespace rather than silently degrading.
            try:
                annotation = get_type_hints(self.functor).get(first.name, annotation)
            except (NameError, TypeError):
                pass
        # Only the concrete trackers (:class:`MacroParticle` and
        # :class:`PhysicalParticle`) can be instantiated to record attribute
        # access. The abstract bases ``Particle``/``AbstractParticle`` mean
        # "an ordinary particle" and default to the macro-particle flavour.
        if isinstance(annotation, type) and issubclass(annotation, PhysicalParticle):
            return PhysicalParticle
        return MacroParticle

    @model_validator(mode="after")
    def _init(self):
        sig = signature(self.functor)
        if len(sig.parameters) == 0:
            raise TypeError(
                "A particle functor must take the particle as its first argument, e.g. "
                "`def my_functor(particle: MacroParticle)`. You gave a zero-argument functor."
            )
        if self.name is None:
            self.name = self.functor.__name__
        if self.return_type is None and sig.return_annotation is not sig.empty:
            self.return_type = sig.return_annotation
        if self.scales_with_weighting is not None and self._particle_class() is not PhysicalParticle:
            raise TypeError(
                f"Can't apply scaling to a non-PhysicalParticle functor. You gave: {self.scales_with_weighting=}."
            )
        if len(rng_classes := self._rng_classes()) > 1:
            raise ValueError(
                f"ParticleFunctor can take at most one RNG. You have requested {rng_classes=} in your signature."
            )
        return self

    def _evaluate(self):
        particle = (
            self._particle_class()(self.scales_with_weighting)
            if self._particle_class() is PhysicalParticle
            else self._particle_class()()
        )
        rng = self.rng_class()
        expression = self(particle) if rng is None else self(particle, rng)
        attribute_map = particle.get_attribute_map() | alt(lambda: rng.get_attribute_map(), {})
        return particle, rng, expression, attribute_map

    @staticmethod
    def _infer_return_type(expression, attribute_map):
        """Infer the C++ value type from a bare registry attribute access.

        Only expressions that are exactly an accessed attribute (a scalar or a
        whole vector) get a registry-driven type; arbitrary expressions fall
        back to ``float_X`` as before.
        """
        if isinstance(expression, tuple):
            for key, attribute in attribute_map.items():
                if isinstance(key, tuple) and tuple(key) == tuple(expression):
                    spec = _attribute_spec(attribute)
                    if spec is not None and spec.n_components == len(expression) and spec.n_components > 1:
                        return spec.cpp_type
            return None
        if isinstance(expression, Symbol):
            for key, attribute in attribute_map.items():
                spec = _attribute_spec(attribute)
                if spec is None:
                    continue
                if isinstance(key, tuple):
                    if expression in key:
                        return spec.component_cpp_type
                elif key == expression:
                    return spec.cpp_type
        return None

    @staticmethod
    def _matching_spec(expression, attribute_map):
        """The descriptor of the attribute an expression is exactly taken from."""
        if isinstance(expression, tuple):
            for key, attribute in attribute_map.items():
                if isinstance(key, tuple) and tuple(key) == tuple(expression):
                    return _attribute_spec(attribute)
            return None
        if isinstance(expression, Symbol):
            for key, attribute in attribute_map.items():
                if isinstance(key, tuple):
                    if expression in key:
                        return _attribute_spec(attribute)
                elif key == expression:
                    return _attribute_spec(attribute)
        return None

    def get_required_attributes(self) -> list[Attribute]:
        """The pypicongpu species attributes this functor accesses.

        Drives ``Species.register_requirements`` so a species used with this
        functor actually carries the attributes it reads (e.g. ``momentumPrev1``)
        rather than being excluded as ineligible. Attributes that are not a
        concrete ``Attribute`` (e.g. ``mass``/``charge``, which come from species
        constants) are omitted.
        """
        _, _, _, attribute_map = self._evaluate()
        requirements = set()
        for value in attribute_map.values():
            name = _attribute_name(value)
            cls = ATTRIBUTE_REGISTRY.get(name) or _ATTRIBUTE_BY_DERIVED_NAME.get(name)
            if cls is not None:
                requirements.add(cls)
        return [attribute_type() for attribute_type in sorted(requirements, key=lambda cls: cls.__name__)]

    def get_as_pypicongpu(self, mode, custom_templates=None) -> PyPIConGPUParticleFunctor:
        allow_unknown = self._custom_templates if custom_templates is None else custom_templates
        particle, rng, functor_expression, attribute_map = self._evaluate()
        spec = self._matching_spec(functor_expression, attribute_map)
        if self.return_type is None:
            self.return_type = self._infer_return_type(functor_expression, attribute_map) or float
        if spec is not None and spec.n_components > 1 and isinstance(functor_expression, tuple):
            if mode != "DerivedField":
                raise ValueError(
                    f"Returning the whole vector attribute {_attribute_name(attribute_map[functor_expression])!r} "
                    f"is not supported in {mode} functors; index it to a single component or use a "
                    "DerivedField functor."
                )
        unit_dimension = self.unit_dimension
        unit_factor = self.unit_factor
        position_unit = _position_unit(functor_expression, attribute_map)
        if unit_dimension is None:
            if position_unit is not None:
                unit_dimension = UnitDimension(list(_POSITION_UNIT_METADATA[position_unit][0]))
                self.unit_dimension = unit_dimension
                if unit_factor is None:
                    unit_factor = _POSITION_UNIT_METADATA[position_unit][1]
            else:
                unit_dimension = UnitDimension() if spec is None else UnitDimension(list(spec.unit_dimension))
                self.unit_dimension = unit_dimension
                if unit_factor is None and spec is not None:
                    unit_factor = spec.unit
        return PyPIConGPUParticleFunctor(
            name=self.name,
            functor_expression=functor_expression,
            functor_preamble=generate_preamble(attribute_map, mode=mode, allow_unknown=allow_unknown),
            return_type=self.return_type,
            unit_dimension=PyPIConGPUUnitDimension(unit_dimension=unit_dimension.unit_vector.tolist()),
            unit_factor=unit_factor,
            needs_total_position=particle.needs_total_position,
            rng_info=alt(lambda: rng.model_dump(mode="python"), None),
        )

    def __call__(self, *args):
        return args[0].finalize(self.functor(*args))
