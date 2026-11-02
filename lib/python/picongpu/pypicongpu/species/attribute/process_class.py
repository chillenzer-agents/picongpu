"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: chillenzer-agents
License: GPLv3+
"""

from .attribute import Attribute


class ProcessClass(Attribute):
    """Process class of the selected atomic-physics transition (atomic-physics internal)"""

    picongpu_name: str = "processClass"
    cpp_type: str = "uint8_t"
    internal: bool = True
