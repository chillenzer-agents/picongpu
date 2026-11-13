"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: chillenzer-agents
License: GPLv3+
"""

from .attribute import Attribute


class ParticleId(Attribute):
    """Unique identifier of a macroparticle"""

    picongpu_name: str = "particleId"
    cpp_type: str = "uint64_t"
