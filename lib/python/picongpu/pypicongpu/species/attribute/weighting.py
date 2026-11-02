"""
This file is part of PIConGPU.
Copyright 2021-2024 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre
License: GPLv3+
"""

from .attribute import Attribute


class Weighting(Attribute):
    """
    Weighting of a macroparticle
    """

    picongpu_name: str = "weighting"
    macro_weighted: bool = True
    weighting_power: int = 1
