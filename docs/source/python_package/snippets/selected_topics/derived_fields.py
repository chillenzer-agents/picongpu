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

Defines a simulation that writes built-in derived fields:
the electron density (a scalar particle-to-grid operation),
the x component of the electron weighted velocity
(a directional operation, so a ``direction`` is required),
and the cell-wise average of that velocity.
Unlike ``DerivedFieldDump``, which compiles a user-supplied
:class:`~picongpu.picmi.particle_functor.ParticleFunctor`,
these use PIConGPU's native C++ implementations
and need no Python functor.
"""

from pathlib import Path

from picongpu import picmi
from picongpu.picmi.diagnostics import (
    AverageDerivedFieldDump,
    NativeDerivedFieldDump,
    TS,
)

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

density = NativeDerivedFieldDump(species=electrons, field="Density", period=TS[::5])
velocity_x = NativeDerivedFieldDump(
    species=electrons,
    field="WeightedVelocity",
    direction="x",
    period=TS[::5],
)
average_velocity_x = AverageDerivedFieldDump(
    species=electrons,
    field="WeightedVelocity",
    direction="x",
    period=TS[::5],
)

sim = picmi.Simulation(
    max_steps=100,
    solver=solver,
    species=[electrons],
    layouts=[layout],
    diagnostics=[density, velocity_x, average_velocity_x],
)

sim.run(setup_dir=Path("derived_fields_setup"), run_dir=Path("derived_fields_run"))

print(Path("derived_fields_setup/include/picongpu/param/fileOutput.param").read_text())
