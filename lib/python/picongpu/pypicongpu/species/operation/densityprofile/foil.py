"""
This file is part of PIConGPU.
Copyright 2023-2025 PIConGPU contributors
Authors: Kristin Tippey, Brian Edward Marre, Julian Lenz
License: GPLv3+
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from picongpu.pypicongpu.units import SI

from .plasmaramp import AllPlasmaRamps, None_


class Foil(BaseModel):
    """
    Directional density profile with thickness and pre- and
    post-plasma lengths and cutoffs

    C++ counterpart: the foil profile template in
    include/picongpu/param/density.param.

    Units policy: SI (m^-3 for densities, m for positions/lengths).
    """

    type_foil: Literal[True] = True
    """discriminator for the AnyDensityProfile union."""

    density_si: Annotated[float, Field(gt=0.0), SI("m^-3")]
    """particle number density at the foil plateau, [m^-3]; must be > 0."""

    y_value_front_foil_si: Annotated[float, Field(ge=0.0), SI("m")]
    """position of the front of the foil plateau, [m]; must be >= 0."""

    thickness_foil_si: Annotated[float, Field(ge=0.0), SI("m")]
    """thickness of the foil plateau, [m]; must be >= 0."""

    pre_foil_plasmaRamp: AllPlasmaRamps = None_()
    """pre(lower y) foil-plateau ramp of density"""

    post_foil_plasmaRamp: AllPlasmaRamps = None_()
    """post(higher y) foil-plateau ramp of density"""
