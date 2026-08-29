"""
This file is part of PIConGPU.
Copyright 2021-2024 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre
License: GPLv3+
"""

from .attribute import Attribute


class MomentumPrev1(Attribute):
    """
    Momentum at the previous time step of a macroparticle, [kg*m/s].
    Required by the radiation plugin to compute the radiation mask.

    C++ name: momentumPrev1 (speciesDefinition.param).
    """

    picongpu_name: str = "momentumPrev1"
    """C++ type name of the previous-step momentum attribute."""
