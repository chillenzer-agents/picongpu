"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: chillenzer-agents
License: GPLv3+
"""

from .attribute import Attribute


class Accepted(Attribute):
    """Whether the selected atomic-physics transition was accepted (atomic-physics internal)"""

    picongpu_name: str = "accepted"
    cpp_type: str = "bool"
    internal: bool = True
