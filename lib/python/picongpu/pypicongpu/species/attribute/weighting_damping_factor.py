"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: chillenzer-agents
License: GPLv3+
"""

from .attribute import Attribute


class WeightingDampingFactor(Attribute):
    """Optional damping factor for the weighting (absorbing boundaries/PML)"""

    picongpu_name: str = "weightingDampingFactor"
