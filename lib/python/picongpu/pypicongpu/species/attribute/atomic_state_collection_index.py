"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: chillenzer-agents
License: GPLv3+
"""

from .attribute import Attribute


class AtomicStateCollectionIndex(Attribute):
    """Collection index of an ion's atomic state (atomic-physics internal)"""

    picongpu_name: str = "atomicStateCollectionIndex"
    cpp_type: str = "uint32_t"
    internal: bool = True
