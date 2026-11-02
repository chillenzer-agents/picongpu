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
    # DataSpace<simDim> is dimension dependent; 3 is the maximum number of
    # spatial components and bounds the indices available from ``get()``.
    n_components: int = 3
    # DataSpace has no std::tuple_size specialisation, so a structured binding
    # would not compile. Bind the whole value and index it in the expression.
    access_strategy: str = "whole"
