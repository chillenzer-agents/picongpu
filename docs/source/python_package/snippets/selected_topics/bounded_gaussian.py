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

Defines a Gaussian density profile with sub-volume bounds. Giving
``lower_bound``/``upper_bound`` routes the :class:`GaussianDistribution`
to an analytic (free-formula) profile that reproduces the native
Gaussian exactly while carrying the full 3-vector bounds.
"""

from pathlib import Path

from picongpu import picmi

grid = picmi.Cartesian3DGrid(
    number_of_cells=[64, 64, 64],
    lower_bound=[0.0, 0.0, 0.0],
    upper_bound=[2e-6, 2.5e-6, 2e-6],
    lower_boundary_conditions=["periodic", "periodic", "periodic"],
    upper_boundary_conditions=["periodic", "periodic", "periodic"],
)
solver = picmi.ElectromagneticSolver(method="Yee", cfl=0.7, grid=grid)

# BEGIN-BOUNDED-GAUSSIAN
# sub-volume bounds make the Gaussian an analytic (free-formula) profile;
# the front/plateau/rear ramps and the vacuum front behave as without bounds.
bounded = picmi.GaussianDistribution(
    density=1.0e25,
    center_front=1.0e-6,
    center_rear=1.5e-6,
    sigma_front=2.0e-7,
    sigma_rear=1.0e-7,
    power=2.0,
    factor=-2.0,
    vacuum_front=5.0e-7,
    lower_bound=[0.0, 0.0, 0.0],
    upper_bound=[2.0e-6, 2.5e-6, 2.0e-6],
)
# END-BOUNDED-GAUSSIAN

electrons = picmi.Species(
    name="electrons",
    particle_type="electron",
    initial_distribution=bounded,
)
layout = picmi.PseudoRandomLayout(n_macroparticles_per_cell=2)

simulation = picmi.Simulation(
    max_steps=100,
    solver=solver,
    species=[electrons],
    layouts=[layout],
)

simulation.write_input_file(Path("bounded_gaussian_setup"))
