"""
This file is part of PIConGPU.
Copyright 2025 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

from collections.abc import Callable, Iterable
from inspect import signature
from typing import Any, get_type_hints

from pydantic import BaseModel, computed_field, model_validator
from sympy import Expr, Symbol, symbols

from picongpu.picmi.particle_functor.rng_arg import RNGArg
from picongpu.picmi.particle_functor.unit_dimension import UnitDimension
from picongpu.pypicongpu.particle_functor import (
    ParticleFunctor as PyPIConGPUParticleFunctor,
    UnitDimension as PyPIConGPUUnitDimension,
    derive_requirements,
    generate_preamble,
)
from picongpu.pypicongpu.util import alt, decorating_class, is_iterable

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


class MacroParticle(Particle):
    """A functor operating directly on macroparticles.

    The returned quantity is a macro-particle (weighting-scaled) property,
    which is what the accessors produce as-is.
    """

    needs_total_position = False

    def __init__(self):
        self.used_attributes = {}

    def get_attribute_map(self):
        return self.used_attributes

    def get(self, attribute, **kwargs) -> Expr | Iterable[Expr]:
        if attribute == "position":
            origin = kwargs.get("origin", "total")
            precision = kwargs.get("precision", "cell")
            unit = kwargs.get("unit", "cell")
            self.needs_total_position = self.needs_total_position or (origin.lower() not in ["cell", "local"])
            my_symbols = _COORDINATE_SYSTEM[(origin, precision, unit)]
            self.used_attributes |= {my_symbols: ("position", origin, precision, unit)}

        elif attribute == "momentum":
            my_symbols = symbols("px,py,pz")
            self.used_attributes |= {my_symbols: "momentum"}

        elif attribute == "momentumPrev1":
            my_symbols = symbols("p1x,p1y,p1z")
            self.used_attributes |= {my_symbols: "momentumPrev1"}

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
            self.used_attributes |= {my_symbols: attribute}

        else:
            my_symbols = Symbol(attribute)
            self.used_attributes |= {my_symbols: attribute}

        return my_symbols


# Symbols whose value scales linearly with the macroparticle weighting, and thus
# must be rescaled by ``weighting ** -1`` to obtain the single-particle value.
# Any symbol not listed here is already a per-particle quantity (e.g. momentum,
# velocity, position, damped_weighting), so it is left untouched (identity, 0).
_SCALING = {Symbol("mass"): 1, Symbol("Ekin"): 1, Symbol("charge"): 1}


class PhysicalParticle(MacroParticle):
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
            rescaled = tuple(s * (w ** (-_SCALING.get(s, 0))) for s in alt(lambda: iter(my_symbols), [my_symbols]))
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

    functor: Callable[[Any], Any]
    name: str | None = None
    return_type: type | str | None = None
    unit_dimension: UnitDimension | None = None
    unit_factor: str | None = None
    scales_with_weighting: int | None = None

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
        if isinstance(annotation, type) and issubclass(annotation, Particle):
            return annotation
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
        if self.return_type is None:
            self.return_type = float if sig.return_annotation == sig.empty else sig.return_annotation
        if self.unit_dimension is None:
            self.unit_dimension = UnitDimension()
        if self.scales_with_weighting is not None and self._particle_class() is not PhysicalParticle:
            raise TypeError(
                f"Can't apply scaling to a non-PhysicalParticle functor. You gave: {self.scales_with_weighting=}."
            )
        if len(rng_classes := self._rng_classes()) > 1:
            raise ValueError(
                f"ParticleFunctor can take at most one RNG. You have requested {rng_classes=} in your signature."
            )
        return self

    def get_as_pypicongpu(self, mode) -> PyPIConGPUParticleFunctor:
        particle = (
            self._particle_class()(self.scales_with_weighting)
            if self._particle_class() is PhysicalParticle
            else self._particle_class()()
        )
        rng = self.rng_class()
        functor_expression = self(particle) if rng is None else self(particle, rng)
        attribute_map = particle.get_attribute_map() | alt(lambda: rng.get_attribute_map(), {})
        identifiers, flags = derive_requirements(attribute_map)
        return PyPIConGPUParticleFunctor(
            name=self.name,
            functor_expression=functor_expression,
            functor_preamble=generate_preamble(attribute_map, mode=mode),
            return_type=self.return_type,
            unit_dimension=PyPIConGPUUnitDimension(unit_dimension=self.unit_dimension.unit_vector.tolist()),
            unit_factor=self.unit_factor,
            needs_total_position=particle.needs_total_position,
            required_identifiers=identifiers,
            required_flags=flags,
            rng_info=alt(lambda: rng.model_dump(mode="python"), None),
        )

    def __call__(self, *args):
        return args[0].finalize(self.functor(*args))
