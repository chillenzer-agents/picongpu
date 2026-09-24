"""
This file is part of PIConGPU.
Copyright 2021-2024 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre
License: GPLv3+
"""

from .attribute import Attribute


class Momentum(Attribute):
    """
    Momentum of a macroparticle, [kg*m/s] (reduced: stored as momentum/mass ratio in C++).

    C++ name: momentum (speciesDefinition.param).
    """

    picongpu_name: str = "momentum"
    """C++ type name of the momentum attribute."""
