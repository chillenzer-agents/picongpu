"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: chillenzer-agents
License: GPLv3+
"""

from .attribute import Attribute


class TotalCellIdx(Attribute):
    """Total cell index of a particle in the global domain"""

    picongpu_name: str = "totalCellIdx"
    cpp_type: str = "DataSpace<simDim>"
    n_components: int = 3
