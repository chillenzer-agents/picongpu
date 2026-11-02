"""
This file is part of PIConGPU.
Copyright 2021-2024 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre
License: GPLv3+
"""

from .attribute import Attribute


class RadiationMask(Attribute):
    """
    Radiation mask of a macroparticle (plugin-internal)
    """

    picongpu_name: str = "radiationMask"
    cpp_type: str = "bool"
    internal: bool = True
