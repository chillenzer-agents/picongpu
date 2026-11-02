"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: chillenzer-agents
License: GPLv3+
"""

from .attribute import Attribute


class BinIndex(Attribute):
    """Index of the atomic-physics interaction bin (atomic-physics internal)"""

    picongpu_name: str = "binIndex"
    cpp_type: str = "uint32_t"
    internal: bool = True
