"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: chillenzer-agents
License: GPLv3+
"""

from .attribute import Attribute


class ProbeB(Attribute):
    """Interpolated magnetic field at the particle position (plugin-internal)"""

    picongpu_name: str = "probeB"
    cpp_type: str = "float3_X"
    n_components: int = 3
    unit_dimension: tuple = (0.0, 1.0, -2.0, -1.0, 0.0, 0.0, 0.0)
    unit: str = "sim.unit.bField()"
    internal: bool = True
