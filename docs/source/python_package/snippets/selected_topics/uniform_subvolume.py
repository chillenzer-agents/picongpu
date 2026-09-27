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

Requests a uniform density restricted to a sub-volume that may be re-filled
when a moving simulation window exposes new space.
"""

from pathlib import Path

from picongpu import picmi

grid = picmi.Cartesian3DGrid(
    number_of_cells=[64, 64, 64],
    lower_bound=[0.0, 0.0, 0.0],
    upper_bound=[2e-6, 2e-6, 2e-6],
    lower_boundary_conditions=["periodic", "periodic", "periodic"],
    upper_boundary_conditions=["periodic", "periodic", "periodic"],
)
solver = picmi.ElectromagneticSolver(method="Yee", cfl=0.7, grid=grid)

# BEGIN-UNIFORM-SUBVOLUME
distribution = picmi.UniformDistribution(
    density=1.0e24,
    lower_bound=[0.0, None, None],  # None = unbounded on that axis
    upper_bound=[None, 0.5e-6, None],
    fill_in=True,  # re-fill the sub-volume newly exposed by a moving window
)
# END-UNIFORM-SUBVOLUME

electrons = picmi.Species(
    name="electrons",
    particle_type="electron",
    initial_distribution=distribution,
)

simulation = picmi.Simulation(max_steps=100, solver=solver)
simulation.add_species(electrons, picmi.PseudoRandomLayout(n_macroparticles_per_cell=2))

simulation.write_input_file(Path("uniform_subvolume_setup"))
