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

Defines a constant and an analytic applied (background) field
and attaches one of them to a simulation.
"""

from pathlib import Path

from picongpu import picmi

grid = picmi.Cartesian3DGrid(
    number_of_cells=[128, 128, 128],
    lower_bound=[0.0, 0.0, 0.0],
    upper_bound=[1.0e-6, 1.0e-6, 1.0e-6],
    lower_boundary_conditions=["open", "open", "open"],
    upper_boundary_conditions=["open", "open", "open"],
)
solver = picmi.ElectromagneticSolver(method="Yee", cfl=0.95, grid=grid)

# BEGIN-APPLIED-FIELD-CONSTANT
# a spatially and temporally constant field: Ex in V/m, Bz in T
constant_field = picmi.ConstantAppliedField(
    Ex=1.0e6,
    Bz=0.5,
)
# END-APPLIED-FIELD-CONSTANT

# BEGIN-APPLIED-FIELD-ANALYTIC
# x, y, z (position in m) and t (time in s) are the free variables;
# named parameters are passed as additional keyword arguments
analytic_field = picmi.AnalyticAppliedField(
    Ex_expression="E0 * sin(2 * pi * y / wavelength) * cos(2 * pi * t / period)",
    E0=1.0e5,
    wavelength=0.8e-6,
    period=50.0e-15,
)
# END-APPLIED-FIELD-ANALYTIC

simulation = picmi.Simulation(max_steps=100, solver=solver)

# BEGIN-APPLIED-FIELD-ADD
# at most one applied field is supported so far
simulation.add_applied_field(analytic_field)
# END-APPLIED-FIELD-ADD

simulation.write_input_file(Path("applied_fields_setup"))
