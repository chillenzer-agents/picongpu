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

Sets the particle boundary conditions of a simulation: a grid-wide default
(per axis, standard PICMI fields) and a per-species override (PIConGPU
extension).
"""

from pathlib import Path

from picongpu import picmi
from picongpu.picmi.particle_boundary import ParticleBoundary

# BEGIN-GRID
grid = picmi.Cartesian3DGrid(
    number_of_cells=[64, 64, 64],
    lower_bound=[0.0, 0.0, 0.0],
    upper_bound=[2e-6, 2e-6, 2e-6],
    # field boundary conditions: x periodic, y and z absorbing ("open"):
    lower_boundary_conditions=["periodic", "open", "open"],
    upper_boundary_conditions=["periodic", "open", "open"],
    # particle boundary conditions: unset axes inherit the field BCs, so
    # these are the grid-wide defaults for every species (lower == upper):
    lower_boundary_conditions_particles=["periodic", "absorbing", "absorbing"],
    upper_boundary_conditions_particles=["periodic", "absorbing", "absorbing"],
)
# END-GRID
solver = picmi.ElectromagneticSolver(method="Yee", cfl=0.9, grid=grid)

# BEGIN-SPECIES
electrons = picmi.Species(
    name="electrons",
    particle_type="electron",
    initial_distribution=picmi.UniformDistribution(density=1e24),
)

ions = picmi.Species(
    name="ions",
    particle_type="H",
    charge_state=1,
    initial_distribution=picmi.UniformDistribution(density=1e24),
    # per-species override of the grid default: reflect on x, thermal on the
    # absorbing y/z axes, with a 1-cell inward offset and a 10 keV temperature:
    picongpu_particle_boundary=ParticleBoundary(
        boundary=("periodic", "reflect", "thermal"),
        boundary_offset=[0, 2, 1],
        boundary_temperature=[0.0, 0.0, 10.0],
    ),
)
# END-SPECIES

simulation = picmi.Simulation(
    max_steps=100,
    solver=solver,
    species=[electrons, ions],
)

simulation.write_input_file(Path("particle_boundaries_setup"))
