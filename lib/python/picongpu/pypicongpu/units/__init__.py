"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+

EXPLORATORY PROOF OF CONCEPT (PoC) - DO NOT TREAT AS A FINAL API.

Actionable unit annotations for pypicongpu backed by the established external
package ``pint``.

The long-term design is written up in
``docs/source/dev/units_design.rst`` (TT-17). This module is a deliberately
small slice that demonstrates the core mechanism:

* ``Unit`` -- a pydantic-compatible ``Annotated[...]`` metadata marker carrying
  the *unit string* and a *value convention* (``scale``).  It is metadata-only:
  it neither changes ``model_dump`` output nor value round-trips.
* ``to_unit_dimension(unit)`` -- derives the openPMD/PIConGPU 7-vector
  (LMTIThetaNJ exponents, the same order as
  ``include/picongpu/traits/SIBaseUnits.hpp``) from a pint-parsable unit
  string. This is the interop channel with the internal C++ unit system and the
  openPMD ``unitDimension`` attribute.
* ``convert(value, from_unit, to_unit)`` -- classic runtime unit conversion
  (e.g. keV <-> J), the shape of the conversion lambdas that the picmi bridge
  already hard-codes today.

Only ``Unit`` is intended to be *used* by pypicongpu models; the two free
functions are the demonstrated pint surface.

NOTE ON THE DEPENDENCY: ``pint`` is already a declared dependency of the
picongpu Python package (see ``lib/python/pyproject.toml``), so nothing needs
to be added. The unit layer is what *consumes* it.
"""

from __future__ import annotations

from typing import Any

from pydantic import GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema

# Number of SI base measures used by openPMD's UnitDimension attribute and by
# PIConGPU's C++ unit traits.
N_UNIT_DIMENSION = 7

# pint's internal base-dimension *names*, in the canonical LMTIThetaNJ order
# shared by PIConGPU (include/picongpu/traits/SIBaseUnits.hpp) and openPMD.
# Indexing a pint dimensionality (a dict {base_name: exponent}) by this tuple
# yields the openPMD-compatible unit-dimension vector with no reordering.
_PINT_DIMENSION_ORDER = (
    "[length]",  # L  length
    "[mass]",  # M  mass
    "[time]",  # T  time
    "[current]",  # I  electric current
    "[temperature]",  # Theta  thermodynamic temperature
    "[substance]",  # N  amount of substance
    "[luminosity]",  # J  luminous intensity
)

# Single-letter/symbol index map mirroring SIBaseUnits.hpp's SIBaseUnits_t
# enum, so that python call-sites can write UnitDimension-style expressions.
L: int = 0  # length
M: int = 1  # mass
T: int = 2  # time
I: int = 3  # electric current  # noqa: E741
THETA: int = 4  # thermodynamic temperature
N: int = 5  # amount of substance
J: int = 6  # luminous intensity

_registry = None


def _ureg():
    """Return the shared pint unit registry (initialised on first use)."""
    global _registry
    if _registry is None:
        import pint

        _registry = pint.UnitRegistry()
    return _registry


def to_unit_dimension(unit: str) -> list[float]:
    """
    Derive the openPMD/PIConGPU unit-dimension vector for a unit string.

    :param unit: pint-parsable unit expression, e.g. ``"m"``, ``"m**-3"`` or
        ``"keV"``. ``"dimensionless"``/``"1"`` yields the null vector.
    :return: 7-vector of exponents in LMTIThetaNJ order.
    """
    ureg = _ureg()
    dimensionality = ureg.parse_units(unit).dimensionality
    return [float(dimensionality.get(name, 0.0)) for name in _PINT_DIMENSION_ORDER]


def convert(value: float, from_unit: str, to_unit: str) -> float:
    """
    Convert a numeric value between two pint-parsable units.

    :param value: quantity magnitude in ``from_unit``.
    :param from_unit: source unit string.
    :param to_unit: target unit string.
    :raises pint.errors.DimensionalityError: for incompatible dimensions.
    """
    ureg = _ureg()
    return float(ureg.Quantity(value, from_unit).to(to_unit).magnitude)


class Unit:
    """
    Pydantic metadata marker tagging a field with a physical unit.

    Drop-compatible with ``Annotated[quantity, Unit("kg")]``: the annotation is
    purely descriptive and adds no validation or serialisation of its own, so

    * ``model_dump(mode="json")`` value output is unchanged, and
    * value round-trips (dump -> validate) are unaffected.

    Machine-readable payload produced for the JSON schema (and reachable via
    ``model_fields[].metadata``):

    * ``unit`` -- the pint-parsable unit string (e.g. ``"kg"``).
    * ``scale`` -- the *value convention* of the stored number, ``"SI"`` by
      default, or a code-interface unit such as ``"keV"`` (documents the
      conversion lambdas that live in the picmi bridge today).
    * ``unit_dimension`` -- the openPMD/PIConGPU 7-vector derived via pint.

    EXPERIMENTAL - PoC surface; the final API is subject to
    ``docs/source/dev/units_design.rst``.
    """

    def __init__(self, unit: str, scale: str = "SI"):
        self.unit = unit
        self.scale = scale

    def __eq__(self, other):
        return type(other) is type(self) and (self.unit, self.scale) == (other.unit, other.scale)

    def __hash__(self):
        return hash((type(self), self.unit, self.scale))

    def __repr__(self):
        return f"{type(self).__name__}({self.unit!r}, scale={self.scale!r})"

    @property
    def dimension(self) -> list[float]:
        """openPMD/PIConGPU unit-dimension 7-vector (LMTIThetaNJ)."""
        return to_unit_dimension(self.unit)

    def __get_pydantic_core_schema__(self, source_type: Any, handler: Any) -> core_schema.CoreSchema:
        return handler(source_type)

    def __get_pydantic_json_schema__(self, schema: JsonSchemaValue, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        """Emit the unit metadata into the JSON schema of the tagged field."""
        json_schema = handler(schema)
        json_schema["unit"] = self.unit
        json_schema["unit_scale"] = self.scale
        json_schema["unit_dimension"] = self.dimension
        return json_schema
