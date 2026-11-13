"""
This file is part of PIConGPU.
Copyright 2021-2024 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre
License: GPLv3+
"""

from .attribute import Attribute


class Momentum(Attribute):
    """
    Momentum of a macroparticle
    """

    picongpu_name: str = "momentum"
    cpp_type: str = "float3_X"
    n_components: int = 3
    unit_dimension: tuple = (1.0, 1.0, -1.0, 0.0, 0.0, 0.0, 0.0)
    unit: str = "sim.unit.mass() * sim.unit.speed()"
    macro_weighted: bool = True
    weighting_power: int = 1
    # macro = per-real-particle value * weighting (C++ WeightingPower), but
    # PhysicalParticle keeps momentum as an already per-particle quantity
    # (see the docs), so it must not be divided by the weighting again.
    physical_weighting_power: int = 0
