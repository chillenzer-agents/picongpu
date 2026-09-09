"""
This file is part of PIConGPU.
Copyright 2021-2024 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre
License: GPLv3+
"""

from .attribute import Attribute


class BoundElectrons(Attribute):
    """
    Number of bound electrons per nucleus of a macroparticle,
    [dimensionless, integer count]; set by the SetChargeState operation.

    C++ name: boundElectrons (speciesDefinition.param).
    """

    picongpu_name: str = "boundElectrons"
    """C++ type name of the bound electrons attribute."""
