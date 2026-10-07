#!/usr/bin/env python
# /// script
# requires-python = ">=3.11,<3.14"
# dependencies = [
#   "picongpu @ git+https://github.com/ComputationalRadiationPhysics/picongpu@dev#subdirectory=lib/python"
# ]
# ///
"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

# BEGIN-SIMULATION-GROUP
from pathlib import Path

from picongpu import picmi

grid = picmi.Cartesian3DGrid(
    number_of_cells=[192, 2048, 192],
    lower_bound=[0, 0, 0],
    upper_bound=[0.1772e-6, 0.4430e-7, 0.1772e-6],
    lower_boundary_conditions=["periodic", "periodic", "periodic"],
    upper_boundary_conditions=["periodic", "periodic", "periodic"],
)


def make_simulation(cfl):
    return picmi.Simulation(
        max_steps=100,
        solver=picmi.ElectromagneticSolver(method="Yee", cfl=cfl, grid=grid),
    )


group = picmi.SimulationGroup(
    simulations={
        "stable": make_simulation(0.95),
        "coarse": make_simulation(0.99),
    }
)

group.write_input_file(Path("simulation_group_setup"))
# END-SIMULATION-GROUP

for path, _ in group.simulations_by_path:
    print(f"sub-simulation: {path}")
