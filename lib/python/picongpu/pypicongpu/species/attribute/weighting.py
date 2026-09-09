"""
This file is part of PIConGPU.
Copyright 2021-2024 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre
License: GPLv3+
"""

from .attribute import Attribute


class Weighting(Attribute):
    """
    Weighting of a macroparticle, [dimensionless]; the particle weight.

    C++ name: weighting (speciesDefinition.param).
    """

    picongpu_name: str = "weighting"
    """C++ type name of the weighting attribute."""
