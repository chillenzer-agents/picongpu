"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: chillenzer-agents
License: GPLv3+
"""

from .attribute import Attribute


class TransitionRadiationMask(Attribute):
    """Mask selecting particles for transition-radiation calculation (plugin-internal)"""

    picongpu_name: str = "transitionRadiationMask"
    cpp_type: str = "bool"
    internal: bool = True
