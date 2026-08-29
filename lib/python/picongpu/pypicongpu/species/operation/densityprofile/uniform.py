"""
This file is part of PIConGPU.
Copyright 2021-2025 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre, Julian Lenz
License: GPLv3+
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from picongpu.pypicongpu.units import SI


class Uniform(BaseModel):
    """
    globally constant density

    PIConGPU equivalent is the homogenous profile, but due to spelling
    ambiguities the PICMI name uniform is followed here.

    C++ counterpart: the homogenous profile template in
    include/picongpu/param/density.param.

    Units policy: SI (m^-3).
    """

    type_uniform: Literal[True] = True
    """discriminator for the AnyDensityProfile union (renders the homogenous profile)."""

    density_si: Annotated[float, Field(gt=0.0), SI("m^-3")]
    """number density at every point in space, [m^-3]; must be > 0."""
