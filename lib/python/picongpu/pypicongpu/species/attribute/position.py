"""
This file is part of PIConGPU.
Copyright 2021-2024 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre
License: GPLv3+
"""

from .attribute import Attribute


class Position(Attribute):
    """
    Position of a macroparticle, [cell] (sub-cell precision).

    C++ name: position<position_pic> (speciesDefinition.param).
    """

    picongpu_name: str = "position<position_pic>"
    """C++ type name of the position attribute."""
