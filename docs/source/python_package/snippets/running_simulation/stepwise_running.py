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

Runs a simulation in stepwise chunks that resume from a checkpoint:
``step()`` executes exactly the requested steps and each chunk restarts from
the checkpoint written at the end of the previous one.
"""

from pathlib import Path

from picongpu import picmi

grid = picmi.Cartesian3DGrid(
    number_of_cells=[32, 32, 32],
    lower_bound=[0, 0, 0],
    upper_bound=[1e-6, 1e-6, 1e-6],
    lower_boundary_conditions=["periodic", "periodic", "periodic"],
    upper_boundary_conditions=["periodic", "periodic", "periodic"],
)
solver = picmi.ElectromagneticSolver(method="Yee", cfl=0.5, grid=grid)
distribution = picmi.UniformDistribution(density=1e23)
layout = picmi.PseudoRandomLayout(n_macroparticles_per_cell=1)
electrons = picmi.Species(name="electrons", particle_type="electron", initial_distribution=distribution)

sim = picmi.Simulation(max_steps=100, solver=solver, species=[electrons], layouts=[layout])

# the setup and run directory are chosen once, as for run(); every chunk
# accumulates its output and checkpoints in the same run directory
sim.picongpu_get_runner(setup_dir=Path("stepwise_setup"), run_dir=Path("stepwise_run"))

# BEGIN-STEPWISE-RUNNING
# Run the simulation in the foreground, chunk by chunk. Each step() call
# covers exactly the steps it is asked to and resumes from the checkpoint
# written at the end of the previous chunk.
sim.step(nsteps=10)  # chunk [0, 10)
sim.step(nsteps=10)  # chunk [10, 20)
sim.step(start=20, end=25)  # the explicit range [20, 25)
# END-STEPWISE-RUNNING
