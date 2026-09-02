"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+

Shared unit metadata for pypicongpu pydantic models.

Physical quantities in the pypicongpu models are documented in SI units and
carry their unit as machine-readable metadata via the `SI` tag, so that
introspection (e.g. `model_fields`) and schema generation expose it alongside
the pydantic-native constraints (Field/Annotated metadata).

Usage:

    mass_si: Annotated[float, Field(gt=0.0), SI("kg")]

The unit string uses plain ASCII, e.g. "kg", "m", "s", "m^-3", "1/s", "V/m".
Dimensionless quantities are left untagged and documented as "dimensionless"
in their docstring. `pint` is a package dependency should a richer unit
representation be wanted in the future; the `SI` string is intentionally
kept independent of it.
"""


class SI:
    """Machine-readable tag marking a field as a physical quantity in SI units."""

    def __init__(self, units: str):
        self.units = units

    def __repr__(self) -> str:
        return f"SI({self.units!r})"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, SI) and self.units == other.units

    def __hash__(self) -> int:
        return hash(self.units)
