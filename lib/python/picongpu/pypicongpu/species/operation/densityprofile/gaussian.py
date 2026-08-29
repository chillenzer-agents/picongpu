"""
This file is part of PIConGPU.
Copyright 2024-2025 PIConGPU contributors
Authors: Brian Edward Marre, Masoud Afshari, Julian Lenz
License: GPLv3+
"""

from typing import Annotated, Literal
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from picongpu.pypicongpu.units import SI


def neq_0(value):
    if value == 0:
        raise ValueError("value is not allowed to be 0.")
    return value


class Gaussian(BaseModel):
    """
    gaussian density profile

    density=
    - for y < gasCenterFront;   density * exp(gasFactor * (abs( (y - gasCenterFront) / gasSigmaFront))^gasPower)
    - for gasCenterFront >= y >= gasCenterRear; density
    - for gasCenterRear < y;    density * exp(gasFactor * (abs( (y - gasCenterRear) / gasSigmaRear))^gasPower)

    C++ counterpart: the gaussian profile template in
    include/picongpu/param/density.param.

    Units policy: SI (m^-3 for densities, m for positions/sigmas).
    """

    # accept both the field names (as produced by model_dump) and the aliases
    # (e.g. center_front) upon construction, so that serialised output can be
    # validated again (round-trip safety)
    model_config = ConfigDict(populate_by_name=True)

    type_gaussian: Literal[True] = True
    """discriminator for the AnyDensityProfile union."""

    gas_center_front: Annotated[float, Field(ge=0.0, alias="center_front"), SI("m")]
    """position of the front edge of the constant middle of the density profile, [m]; must be >= 0.
    C++ name: gasCenterFront."""

    gas_center_rear: Annotated[float, Field(ge=0.0, alias="center_rear"), SI("m")]
    """position of the rear edge of the constant middle of the density profile, [m]; must be >= 0 and
    >= gas_center_front.
    C++ name: gasCenterRear."""

    gas_sigma_front: Annotated[float, AfterValidator(neq_0), Field(alias="sigma_front"), SI("m")]
    """distance from gasCenterFront until the gas density decreases to its 1/e-th part, [m]; must be != 0
    (the sign is irrelevant, the profile uses abs()).
    C++ name: gasSigmaFront."""

    gas_sigma_rear: Annotated[float, AfterValidator(neq_0), Field(alias="sigma_rear"), SI("m")]
    """distance from gasCenterRear until the gas density decreases to its 1/e-th part, [m]; must be != 0
    (the sign is irrelevant, the profile uses abs()).
    C++ name: gasSigmaRear."""

    gas_factor: Annotated[float, Field(lt=0.0, alias="factor")]
    """exponential scaling factor, see formula above, [dimensionless]; must be < 0 so that the density
    decays away from the plateau.
    C++ name: gasFactor."""

    gas_power: Annotated[float, AfterValidator(neq_0), Field(alias="power")]
    """power-exponent in exponent of density function, [dimensionless]; must be != 0.
    C++ name: gasPower."""

    vacuum_cells_front: Annotated[int, Field(ge=0)]
    """number of vacuum cells in front of foil for laser init, [cells]; must be >= 0.
    C++ name: vacuumFront."""

    density_si: Annotated[float, Field(gt=0.0, alias="density"), SI("m^-3")]
    """particle number density at the plateau, [m^-3]; must be > 0.
    C++ name: densityFactor (density.param), the dimensionless factor rendered as
    density_si / SI::BASE_DENSITY_SI (normalized to the base density)."""

    @model_validator(mode="after")
    def check(self):
        if self.gas_center_rear < self.gas_center_front:
            raise ValueError("gas_center_rear must be >= gas_center_front")
        return self
