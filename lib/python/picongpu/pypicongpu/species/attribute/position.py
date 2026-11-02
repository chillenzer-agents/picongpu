"""
This file is part of PIConGPU.
Copyright 2021-2024 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre
License: GPLv3+
"""

from .attribute import Attribute


class Position(Attribute):
    """
    Position of a macroparticle
    """

    picongpu_name: str = "position<position_pic>"
    cpp_type: str = "floatD_X"
    n_components: int = 3
    unit_dimension: tuple = (1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    unit: str = "sim.pic.getCellSize() * sim.unit.length()"
