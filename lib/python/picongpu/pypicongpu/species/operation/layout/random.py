"""
This file is part of PIConGPU.
Copyright 2025 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class Random(BaseModel):
    """
    place macroparticles at random positions inside each cell

    C++ counterpart: the random layout in include/picongpu/param/particle.param.

    Units policy: ppc is a count (dimensionless).
    """

    type_random: Literal[True] = True
    """discriminator for the AnyLayout union."""

    ppc: Annotated[int, Field(gt=0)]
    """particles per cell (random layout), [dimensionless count]; must be > 0."""
