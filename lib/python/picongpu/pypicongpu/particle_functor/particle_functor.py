"""
This file is part of PIConGPU.
Copyright 2025 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

from typing import Annotated, Literal
from uuid import uuid4 as uuid

from pydantic import BaseModel, BeforeValidator, Field, computed_field, model_validator

from picongpu.pypicongpu.particle_functor.translate_to_cpp_type import translate_to_cpp_type
from picongpu.pypicongpu.particle_functor.rng_info import RNGInfo
from picongpu.pypicongpu.particle_functor.unit_dimension import UnitDimension
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
    "timestep": "domainInfo.currentStep",
    "timestep_size": "sim.pic.getDt()",
}

BINNING_ACCESSORS = (
    COMMON_ACCESSORS
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
    ("local", f"static_cast<float3_X>({by_bracket('localCellIdx')}"),
    ("cell", f"static_cast<float3_X>({by_bracket('position')}"),
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


# Maps each particle attribute a functor may access to the C++ requirement that
# a species' particle frame must satisfy for the corresponding accessor to be
# usable. ``identifiers`` are particle attributes checked with
# ``pmacc::traits::HasIdentifiers`` (``value_identifier`` attributes are named
# bare, ``alias`` attributes are named with ``<>``); ``flags`` are boolean
# capabilities checked with ``pmacc::traits::HasFlag`` (always ``alias``, hence
# the ``<>`` suffix). The strings are stored in their exact C++ spelling.
_ATTRIBUTE_REQUIREMENTS = {
    "mass": {"identifiers": ["weighting"]},
    "momentum": {"identifiers": ["momentum"]},
    "momentumPrev1": {"identifiers": ["momentumPrev1"]},
    "charge": {"identifiers": ["weighting"], "flags": ["chargeRatio<>"]},
    "charge_state": {"identifiers": ["boundElectrons"], "flags": ["atomicNumbers<>"]},
    "damped_weighting": {"identifiers": ["weighting"]},
    "gamma": {"identifiers": ["weighting", "momentum"]},
    "kinetic energy": {"identifiers": ["weighting", "momentum"]},
    "velocity": {"identifiers": ["weighting", "momentum"]},
}
_NO_REQUIREMENT = {"identifiers": [], "flags": []}


def derive_requirements(attribute_mapping):
    """Derive the C++ identifiers and flags a species must carry.

    Combines :data:`_ATTRIBUTE_REQUIREMENTS` over the particle attributes a
    functor touches, returning a de-duplicated, sorted ``(identifiers, flags)``
    pair of C++-spelled strings that can be rendered into a
    ``SpeciesEligibleForSolver`` trait.

    ``position`` (any origin/precision/unit) and ``random_number`` require no
    attribute because the particle's cell offset and the RNG are always
    available.
    """
    identifiers, flags = set(), set()
    for value in attribute_mapping.values():
        attribute = value[0] if isinstance(value, tuple) else value
        if attribute in ("position", "random_number"):
            continue
        requirement = _ATTRIBUTE_REQUIREMENTS.get(attribute, _NO_REQUIREMENT)
        identifiers.update(requirement.get("identifiers", []))
        flags.update(requirement.get("flags", []))
    return sorted(identifiers), sorted(flags)


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


def generate_preamble(attribute_mapping, mode: Literal["Binning", "Filter", "DerivedField"]):
    statements = {
        symbol: ACCESSORS[mode](attribute, by_bracket(attribute)) for symbol, attribute in attribute_mapping.items()
    }
    if unsupported_synbols := [symbol for symbol, statement in statements.items() if statement is NotImplemented]:
        raise ValueError(f"Found {unsupported_synbols=} trying to generate C++ code for one of your functors.")
    return [
        {"statement": f"auto const {symbol_to_string(symbol)} = {statement};"}
        for symbol, statement in statements.items()
    ]


class _PreambleStatement(BaseModel):
    statement: str


class ParticleFunctor(RenderedObject, BaseModel):
    name: str
    functor_expression: Annotated[str, BeforeValidator(PMAccPrinter().doprint)]
    functor_preamble: list[_PreambleStatement]
    return_type: Annotated[str, BeforeValidator(translate_to_cpp_type)]
    unit_dimension: UnitDimension | None = UnitDimension()
    unit_factor: str | None = None
    needs_total_position: bool = False
    rng_info: RNGInfo | None = None
    required_identifiers: list[str] = Field(default_factory=list, exclude=True)
    required_flags: list[str] = Field(default_factory=list, exclude=True)

    @computed_field
    def typename(self) -> str:
        return f"{self.name}_{uuid().hex}"

    @computed_field
    def identifier_requirement_cpp(self) -> str:
        """Render the ``HasIdentifiers`` check for the eligibility trait.

        Emits ``pmacc::mp_bool<true>`` when the functor touches no particle
        attribute, otherwise the (single) ``HasIdentifiers`` expression.
        """
        if not self.required_identifiers:
            return "pmacc::mp_bool<true>"
        identifiers = ", ".join(self.required_identifiers)
        return f"typename pmacc::traits::HasIdentifiers<FrameType, MakeSeq_t<{identifiers}>>::type"

    @computed_field
    def flag_requirement_cpp(self) -> str:
        """Render the ``HasFlag`` check(s) for the eligibility trait.

        Emits ``pmacc::mp_bool<true>`` when no flag is required, otherwise a
        single ``HasFlag`` expression or an ``mp_and`` of them.
        """
        if not self.required_flags:
            return "pmacc::mp_bool<true>"
        checks = [f"typename pmacc::traits::HasFlag<FrameType, {flag}>::type" for flag in self.required_flags]
        return checks[0] if len(checks) == 1 else f"pmacc::mp_and<{', '.join(checks)}>"

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
        if self.needs_total_position and self.rng_info is not None:
            raise ValueError(
                f"PIConGPU does not support particle functors that need total position and random numbers. You gave: {self.rng_info=}."
            )
        return self
