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

Selects subsets of the simulation workflow with the stable stage
vocabulary (``up_to`` / ``from_``).
"""

# BEGIN-PARTIAL-WORKFLOW
from pathlib import Path

from picongpu import picmi
from picongpu.picmi import Stage

sim = picmi.Simulation(
    max_steps=100,
    solver=picmi.ElectromagneticSolver(
        method="Yee",
        cfl=0.95,
        grid=picmi.Cartesian3DGrid(
            number_of_cells=[192, 2048, 192],
            lower_bound=[0, 0, 0],
            upper_bound=[0.1772e-6, 0.4430e-7, 0.1772e-6],
            lower_boundary_conditions=["periodic", "periodic", "periodic"],
            upper_boundary_conditions=["periodic", "periodic", "periodic"],
        ),
    ),
)

setup_dir = Path("partial_workflow_setup")
run_dir = Path("partial_workflow_run")

# the default: build, prepare, submit and collect in one go
sim.picongpu_run(setup_dir=setup_dir, run_dir=run_dir)

# only compile: run the stages up to (and including) 'build'
sim.picongpu_run(setup_dir=setup_dir, run_dir=run_dir, up_to=Stage.build)

# resume at 'submit': 'build' and 'prepare' are served from the job store
sim.picongpu_run(setup_dir=setup_dir, run_dir=run_dir, from_=Stage.submit)
# END-PARTIAL-WORKFLOW

print("It worked!")
