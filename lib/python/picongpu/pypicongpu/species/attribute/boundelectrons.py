"""
This file is part of PIConGPU.
Copyright 2021-2024 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre
License: GPLv3+
"""

from .attribute import Attribute


class BoundElectrons(Attribute):
    """
    number of electrons still bound to the nucleus of a macroparticle

    [dimensionless, integer count]; the complement of the charge state:
    `boundElectrons = atomic_number - charge_state`.

    Set by the SetChargeState operation, whose C++ counterpart
    (`manipulators::unary::acc::ChargeState`) derives this value from the
    charge state and stores it via `atomicPhysics::SetChargeState`.

    C++ name: boundElectrons (speciesDefinition.param).
    """

    picongpu_name: str = "boundElectrons"
    """C++ type name of the bound electrons attribute."""
