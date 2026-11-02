"""
This file is part of PIConGPU.
Copyright 2025 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

from typing import Annotated, Literal
from uuid import uuid4 as uuid

from pydantic import BaseModel, BeforeValidator, computed_field, model_validator

from picongpu.pypicongpu.particle_functor.translate_to_cpp_type import translate_to_cpp_type
from picongpu.pypicongpu.particle_functor.rng_info import RNGInfo
from picongpu.pypicongpu.particle_functor.unit_dimension import UnitDimension
from picongpu.pypicongpu.species.attribute.registry import ATTRIBUTE_REGISTRY, DERIVED_ACCESSORS
from picongpu.pypicongpu.rendering.pmaccprinter import PMAccPrinter
from picongpu.pypicongpu.rendering.renderedobject import RenderedObject
from picongpu.pypicongpu.util import alt


def by_bracket(attribute):
    return f"particle[{attribute}_]"


COMMON_ACCESSORS = {
    "mass": "picongpu::traits::attribute::getMass(particle[weighting_], particle)",
    # CAUTION: The names in the gamma formula are currently hardcoded.
    # We'll certainly trip over this, should we ever dare to change the internal names.
    "gamma": "picongpu::Gamma()(momentum::type{px, py, pz}, mass)",
    "kinetic energy": "picongpu::KinEnergy()(momentum::type{px, py, pz}, mass)",
    "velocity": "picongpu::Velocity()(momentum::type{px, py, pz}, mass)",
    "charge": "picongpu::traits::attribute::getCharge(particle[weighting_], particle)",
    "charge_state": "picongpu::traits::attribute::getChargeState(particle)",
    "damped_weighting": "picongpu::traits::attribute::getDampedWeighting(particle)",
}

BINNING_ACCESSORS = (
    COMMON_ACCESSORS
    | {
        "timestep": "domainInfo.currentStep",
        "timestep_size": "sim.pic.getDt()",
    }
    | {
        (
            "position",
            origin.lower(),
            precision.lower(),
            unit.lower(),
        ): f"getParticlePosition<DomainOrigin::{origin}, PositionPrecision::{precision}, PositionUnits::{unit}>(domainInfo, particle)"
        for origin in ("TOTAL", "GLOBAL", "LOCAL", "MOVING_WINDOW", "LOCAL_WITH_GUARDS")
        for precision in ("CELL", "SUB_CELL")
        for unit in ("CELL", "PIC", "SI")
    }
    | {"random_number": NotImplemented}
)

_ORIGINS = [
    ("local", f"static_cast<float3_X>({by_bracket('localCellIdx')})"),
    ("cell", f"static_cast<float3_X>({by_bracket('position')})"),
    ("total", "static_cast<float3_X>(particleOffsetToTotalOrigin)"),
]
_PRECISIONS = [("cell", ""), ("sub_cell", " + " + by_bracket("position"))]
_UNITS = [("cell", ""), ("si", "* sim.si.getCellSize()"), ("pic", "* sim.pic.getCellSize()")]

DERIVED_FIELD_ACCESSORS = (
    COMMON_ACCESSORS
    | {
        ("position", origin, precision, unit): f"({o_expr}{p_expr}){u_expr}"
        for origin, o_expr in _ORIGINS
        if origin != "total"
        for precision, p_expr in _PRECISIONS
        for unit, u_expr in _UNITS
    }
    | {"random_number": NotImplemented}
)

FILTER_ACCESSORS = (
    DERIVED_FIELD_ACCESSORS
    | {
        ("position", origin, precision, unit): f"({o_expr}{p_expr}){u_expr}"
        for origin, o_expr in _ORIGINS
        if origin == "total"
        for precision, p_expr in _PRECISIONS
        for unit, u_expr in _UNITS
    }
    | {"random_number": "rng()"}
)


def random_number_command(**kwargs):
    scale = kwargs.get("scale", 1)
    if scale < 0:
        raise ValueError(f"{scale=} must be >= 0.")
    return f"random_number(rng, static_cast<typename RNGType::result_type>({kwargs.get('loc', 0)}), static_cast<typename RNGType::result_type>({scale}))"


def filter_access(name, default):
    if name in FILTER_ACCESSORS:
        return FILTER_ACCESSORS[name]
    if alt(lambda: name[0] == "random_number", False):
        return random_number_command(**dict(name[1]))
    return default


ACCESSORS = {
    "Binning": lambda name, default: BINNING_ACCESSORS.get(name, default),
    "DerivedField": lambda name, default: DERIVED_FIELD_ACCESSORS.get(name, default),
    "Filter": filter_access,
}


def _format_exponent(exponent):
    value = float(exponent)
    return f"{int(value)}.0" if value == int(value) else repr(value)


def _unit_monomial(exponents):
    """Render the numeric ``sim.unit.*`` monomial for ``getUnit()``.

    The internal unit system is a monomial in the base SI values
    (``sim.unit.length = c * dt``, ``.mass``, ``.time = dt``, ``.charge``),
    so for any pure-monomial quantity the SI value of one internal unit is
    fully determined by the 7-vector. Temperature, amount-of-substance (the
    ``N_ppm`` count factor) and luminous intensity cannot be derived and must
    be provided via an explicit ``unit_factor`` instead.
    """
    length, mass, time, current = (float(exp) for exp in exponents[:4])
    if any(abs(float(exp)) > 1.0e-12 for exp in exponents[4:]):
        raise ValueError(
            "getUnit() cannot be auto-derived from this unit_dimension "
            "(it has temperature/amount-of-substance/luminous-intensity components). "
            "Provide an explicit unit_factor."
        )
    if any(abs(float(exp) - round(float(exp))) > 1.0e-12 for exp in exponents[:4]):
        raise ValueError(
            f"getUnit() cannot be auto-derived from a non-integer unit_dimension. "
            f"Provide an explicit unit_factor. You gave: {list(exponents[:4])}."
        )
    # The SI current is a charge per time, so it folds into charge^I * time^-I.
    aggregated = {
        "sim.unit.length()": int(round(length)),
        "sim.unit.mass()": int(round(mass)),
        "sim.unit.time()": int(round(time - current)),
        "sim.unit.charge()": int(round(current)),
    }
    numerator, denominator = [], []
    for base, exponent in aggregated.items():
        if exponent > 0:
            numerator.extend([base] * exponent)
        elif exponent < 0:
            denominator.extend([base] * -exponent)
    if not numerator and not denominator:
        return "1."
    if numerator and not denominator:
        return " * ".join(numerator)
    if not numerator:
        return f"1. / {' * '.join(denominator)}"
    return f"({' * '.join(numerator)}) / ({' * '.join(denominator)})"


def symbol_to_string(symbol):
    return str(symbol) if not isinstance(symbol, tuple) else "[" + ",".join(map(str, symbol)) + "]"


_MISSING_ACCESSOR = object()


def _mode_table(mode):
    return {
        "Binning": BINNING_ACCESSORS,
        "DerivedField": DERIVED_FIELD_ACCESSORS,
        "Filter": FILTER_ACCESSORS,
    }[mode]


def _accessor(name, mode):
    table = _mode_table(mode)
    if name in table:
        return table[name]
    if mode == "Filter" and alt(lambda: name[0] == "random_number", False):
        return random_number_command(**dict(name[1]))
    return _MISSING_ACCESSOR


def _fallback_accessor(name, mode, allow_unknown):
    """Resolve a plain stored attribute or raise a clear mode/name error."""
    table = _mode_table(mode)
    if isinstance(name, tuple):
        kind = name[0]
        if kind == "position":
            available = sorted({key[1] for key in table if isinstance(key, tuple) and key[0] == "position"})
            raise ValueError(
                f"Particle position with origin={name[1]!r} is not available in {mode} functors. "
                f"Available origins here: {', '.join(available) or 'none'}."
            )
        raise ValueError(f"Particle attribute access {name!r} is not available in {mode} functors.")
    if name in ("timestep", "timestep_size"):
        raise ValueError(
            f"{name!r} is only available in Binning functors because only they receive domainInfo; "
            f"it is not available in {mode} functors."
        )
    if name in ATTRIBUTE_REGISTRY or name in DERIVED_ACCESSORS:
        return by_bracket(name)
    if allow_unknown:
        # Custom templates may extend speciesAttributes.param with attributes the
        # Python registry does not know about.
        return by_bracket(name)
    supported = ", ".join(sorted(ATTRIBUTE_REGISTRY))
    raise ValueError(
        f"Unknown particle attribute {name!r} in {mode} functor. Supported stored attributes: {supported}. "
        "Unknown names are only allowed when a custom template directory is configured."
    )


def _preamble_spec(attribute):
    """Registry descriptor of a preamble attribute value, if available."""
    name = attribute[0] if isinstance(attribute, tuple) else attribute
    cls = ATTRIBUTE_REGISTRY.get(name)
    return None if cls is None else cls()


def generate_preamble(
    attribute_mapping, mode: Literal["Binning", "Filter", "DerivedField"], allow_unknown: bool = False
):
    lines = []
    unsupported = []
    for symbol, attribute in attribute_mapping.items():
        statement = _accessor(attribute, mode)
        if statement is _MISSING_ACCESSOR:
            statement = _fallback_accessor(attribute, mode, allow_unknown)
        if statement is NotImplemented:
            unsupported.append(symbol)
            continue
        spec = _preamble_spec(attribute)
        if spec is not None and getattr(spec, "access_strategy", "structured_binding") == "whole":
            # Types such as DataSpace<simDim> have no std::tuple_size
            # specialisation, so bind the whole value and index it in the
            # functor expression (the symbols are named ``<name>_value[i]``).
            name = attribute[0] if isinstance(attribute, tuple) else attribute
            statement = f"auto const {name}_value = {statement};"
        else:
            statement = f"auto const {symbol_to_string(symbol)} = {statement};"
        lines.append({"statement": statement})
    if unsupported:
        raise ValueError(f"Found {unsupported=} trying to generate C++ code for one of your functors.")
    return lines


class _PreambleStatement(BaseModel):
    statement: str


class ParticleFunctor(RenderedObject, BaseModel):
    name: str
    functor_expression: Annotated[str, BeforeValidator(PMAccPrinter().doprint)]
    functor_preamble: list[_PreambleStatement]
    return_type: Annotated[str, BeforeValidator(translate_to_cpp_type)]
    unit_dimension: UnitDimension | None = UnitDimension()
    # Already-rendered C++ text of ``getUnit()``; the public (picmi) interface
    # accepts Python expressions/callables and renders them before constructing
    # this pypicongpu model.
    unit_factor: str | None = None
    needs_total_position: bool = False
    rng_info: RNGInfo | None = None

    @computed_field
    def typename(self) -> str:
        return f"{self.name}_{uuid().hex}"

    @computed_field
    def unit_dimension_cpp(self) -> str:
        """Render the 7-vector as a C++ brace-initializer for ``getUnitDimension()``."""
        return "{" + ", ".join(_format_exponent(exp) for exp in self._exponents()) + "}"

    @computed_field
    def get_unit_cpp(self) -> str:
        if self.unit_factor is not None:
            return self.unit_factor
        return _unit_monomial(self._exponents())

    def _exponents(self) -> list[float]:
        return list(self.unit_dimension.unit_dimension) if self.unit_dimension is not None else [0.0] * 7

    @model_validator(mode="after")
    def _validate(self):
        if "int" in self.return_type:
            if self.unit_dimension == UnitDimension():
                self.unit_dimension = None
            if self.unit_dimension is not None:
                raise ValueError(
                    f"unit_dimension is not supported for integral types. You gave {self.unit_dimension=}."
                )
        # Validate up front that `getUnit()` can be auto-derived (or an explicit
        # `unit_factor` was given), so a non-derivable dimension is rejected at
        # construction rather than surfacing a wrong value at render time.
        self.get_unit_cpp
        if self.needs_total_position and self.rng_info is not None:
            raise ValueError(
                f"PIConGPU does not support particle functors that need total position and random numbers. You gave: {self.rng_info=}."
            )
        return self
