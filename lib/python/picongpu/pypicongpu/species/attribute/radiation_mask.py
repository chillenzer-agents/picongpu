"""
This file is part of PIConGPU.
Copyright 2021-2024 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre
License: GPLv3+
"""

from .attribute import Attribute


class RadiationMask(Attribute):
    """
    Radiation mask of a macroparticle, [dimensionless flag];
    marks particles that are included in the radiation calculation
    (e.g. above a gamma threshold).

    C++ name: radiationMask (speciesDefinition.param).
    """

    picongpu_name: str = "radiationMask"
    """C++ type name of the radiation mask attribute."""
