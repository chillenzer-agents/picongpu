"""
This file is part of PIConGPU.
Copyright 2023-2025 PIConGPU contributors
Authors: Kristin Tippey, Brian Edward Marre, Julian Lenz
License: GPLv3+
"""

from typing import Annotated, Literal
from pydantic import BaseModel, Field


class Exponential(BaseModel):
    """exponential plasma ramp, either up or down

    C++ counterpart: the exponential ramp in include/picongpu/param/density.param.

    Units policy: SI (m).
    """

    type_exponential: Literal[True] = True
    """discriminator for the AllPlasmaRamps union."""

    PlasmaLength: Annotated[float, Field(gt=0.0)]
    """scale length of the exponential pre-plasma ramp, [m]; must be > 0.
    C++ name: PlasmaLength."""

    PlasmaCutoff: Annotated[float, Field(ge=0.0)]
    """cutoff of the exponential pre-plasma ramp, [m]; must be >= 0.
    C++ name: PlasmaCutoff."""
