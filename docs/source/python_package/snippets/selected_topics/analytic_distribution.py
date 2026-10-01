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

Defines an analytic density profile in two equivalent ways:
as a sympy function handed over as a decorator, and as a
sympy-parseable ``density_expression`` string, and adds a
constant drift and thermal spread via the standard
``momentum_expressions`` / ``momentum_spread_expressions``.
"""

from pathlib import Path

from sympy import exp

from picongpu import picmi


# BEGIN-DENSITY-FUNCTION
@picmi.AnalyticDistribution
def density(x, y, z):
    return 1e25 * exp(-(((x - 1e-6) / 1e-7) ** 2))


# END-DENSITY-FUNCTION

# BEGIN-DENSITY-EXPRESSION
# the same profile as a sympy-parseable string of x, y and z:
density_string = picmi.AnalyticDistribution(density_expression="1e25 * exp(-((x - 1e-6) / 1e-7) ** 2)")
# END-DENSITY-EXPRESSION

# BEGIN-DENSITY-KWARGS
# constants used in the density may be passed as keyword arguments, both to a
# callable and to the decorator; they are collected into `user_defined_kw` and
# substituted, exactly as for the `density_expression` string above:
density_kwargs = picmi.AnalyticDistribution(
    density_function=lambda x, y, z, n0, width: n0 * exp(-(((x - 1e-6) / width) ** 2)),
    n0=1e25,
    width=1e-7,
)


@picmi.AnalyticDistribution(n0=1e25, width=1e-7)
def decorated_density(x, y, z, n0, width):
    return n0 * exp(-(((x - 1e-6) / width) ** 2))


assert decorated_density._density_expression() == density_kwargs._density_expression()
# END-DENSITY-KWARGS

# BEGIN-MOMENTUM-EXPRESSIONS
# a constant drift (gamma * velocity [m/s]) along z and a Gaussian
# thermal spread sigma [m/s] along the same axis; `n0`, `vz` and `vth`
# are collected automatically into `user_defined_kw`:
drifting = picmi.AnalyticDistribution(
    density_expression="n0 * exp(-(((x - 1e-6) / 1e-7) ** 2))",
    n0=1e25,
    momentum_expressions=[None, None, "vz"],
    momentum_spread_expressions=[None, None, "vth"],
    vz=1.0e6,
    vth=1.0e5,
)
# END-MOMENTUM-EXPRESSIONS

grid = picmi.Cartesian3DGrid(
    number_of_cells=[32, 32, 32],
    lower_bound=[0.0, 0.0, 0.0],
    upper_bound=[2e-6, 2e-6, 2e-6],
    lower_boundary_conditions=["periodic", "periodic", "periodic"],
    upper_boundary_conditions=["periodic", "periodic", "periodic"],
)
solver = picmi.ElectromagneticSolver(method="Yee", cfl=0.7, grid=grid)

electrons = picmi.Species(
    name="electrons",
    particle_type="electron",
    initial_distribution=drifting,
)
layout = picmi.PseudoRandomLayout(n_macroparticles_per_cell=2)

simulation = picmi.Simulation(
    max_steps=100,
    solver=solver,
    species=[electrons],
    layouts=[layout],
)

simulation.write_input_file(Path("analytic_distribution_setup"))
