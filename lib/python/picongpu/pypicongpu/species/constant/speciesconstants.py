"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

from typing import Annotated

from pydantic import BaseModel, Field, field_validator


class SpeciesConstants(BaseModel):
    """
    base (reference) mass and charge for the species mass/charge ratios

    C++ counterpart: the SI namespace in
    include/picongpu/param/speciesConstants.param
    (``SI::BASE_MASS_SI = ELECTRON_MASS_SI``,
    ``SI::BASE_CHARGE_SI = ELECTRON_CHARGE_SI``).

    In C++ these values are fixed to the electron mass and (negative)
    electron charge and the file is not templated, i.e. they are not
    user-configurable per simulation. The defaults here mirror the C++
    constants exactly (2022 CODATA, physicalConstants.param); the species
    mass/charge ratios (see Mass/Charge) are relative to them.
    """

    base_mass_si: Annotated[float, Field(gt=0.0)] = 9.1093837139e-31
    """base particle mass, [kg]; reference for the mass ratio
    (C++: SI::BASE_MASS_SI, fixed to the electron mass); must be > 0"""

    base_charge_si: float = -1.602176634e-19
    """base particle charge, [C]; reference for the charge ratio
    (C++: SI::BASE_CHARGE_SI, fixed to the negative electron charge); must be != 0"""

    @field_validator("base_charge_si")
    @classmethod
    def _base_charge_nonzero(cls, value: float) -> float:
        if value == 0.0:
            raise ValueError("base_charge_si must be non-zero (it is the reference for the charge ratio)")
        return value


# C++ fixes the base values to the electron values; the default instance is
# used for the SI <-> ratio conversion
SPECIES_CONSTANTS = SpeciesConstants()
