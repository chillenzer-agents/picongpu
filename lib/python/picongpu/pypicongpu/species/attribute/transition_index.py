"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: chillenzer-agents
License: GPLv3+
"""

from .attribute import Attribute


class TransitionIndex(Attribute):
    """Index of the chosen atomic-physics transition (atomic-physics internal)"""

    picongpu_name: str = "transitionIndex"
    cpp_type: str = "uint32_t"
    internal: bool = True
