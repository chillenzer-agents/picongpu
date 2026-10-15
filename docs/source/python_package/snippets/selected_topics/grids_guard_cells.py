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

Shows that the grid's guard cells must be deep enough to hold the field
solver's stencil: a too-shallow guard is rejected when the solver is
constructed. The arbitrary-order FDTD needs ``order // 2`` guard cells per
axis, the fixed-order Yee/Lehe/CKC solvers need at least one; an unset
``guard_cells`` (the PIConGPU default) and the ``"other:None"`` solver skip
the check.
"""

from picongpu import picmi

grid = picmi.Cartesian3DGrid(
    number_of_cells=[32, 32, 32],
    # a unit super cell, so any guard-cell count is a valid multiple:
    picongpu_super_cell_size=(1, 1, 1),
    guard_cells=[0, 0, 0],
    lower_bound=[0.0, 0.0, 0.0],
    upper_bound=[1e-6, 1e-6, 1e-6],
    lower_boundary_conditions=["periodic", "periodic", "periodic"],
    upper_boundary_conditions=["periodic", "periodic", "periodic"],
)

# Yee advances the fields one cell wide, so every axis needs >= 1 guard cell:
try:
    picmi.ElectromagneticSolver(method="Yee", grid=grid)
except ValueError as error:
    print(error)

# the arbitrary-order FDTD reaches order // 2 cells into the guard region
# (order 4 -> 2 cells), so [1, 1, 1] is still too shallow:
guard_one = grid.model_copy(update={"guard_cells": [1, 1, 1]})
try:
    picmi.ElectromagneticSolver(method="other:ArbitraryOrderFDTD", stencil_order=[4, 4, 4], grid=guard_one)
except ValueError as error:
    print(error)

# give each axis enough guard cells instead and the solver is accepted:
guard_two = grid.model_copy(update={"guard_cells": [2, 2, 2]})
solver = picmi.ElectromagneticSolver(
    method="other:ArbitraryOrderFDTD",
    stencil_order=[4, 4, 4],
    grid=guard_two,
)
print("accepted solver:", solver.method)

print("It worked!")
