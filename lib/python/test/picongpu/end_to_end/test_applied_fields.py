"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+

Full end-to-end test of the applied (background) fields.

Unlike the density distributions, whose effect is visible in the particle
positions/densities, a background field is only applied around the particle
push and is *not* evolved by the field solver. Its most direct observable is
therefore the field dump: the Python layer translates the PICMI applied fields
into the C++ ``fieldBackground.param`` functors, the (compiled) simulation
evaluates them and writes E and B to the checkpoint. This test builds and runs
such a simulation and compares the dumped, unit-converted E/B values against the
analytic expression the PICMI input describes.

The setup adds several applied fields (constant, string-expression and callable)
so that the summation into the single C++ background functor pair is covered end
to end.
"""

import logging
from pathlib import Path
from unittest import TestCase

import numpy as np
import openpmd_api as opmd
from picongpu import rc_params
from picongpu.picmi import (
    Cartesian3DGrid,
    ElectromagneticSolver,
    PseudoRandomLayout,
    Simulation,
    Species,
    UniformDistribution,
)
from picongpu.picmi.diagnostics import Checkpoint, TS

from .applied_fields import APPLIED_FIELDS, EXPECTED
from .arbitrary_parameters import NUMBER_OF_CELLS, UPPER_BOUNDARY, directory_in_home, gather_results

logging.basicConfig(level=logging.INFO)

LAYOUT = PseudoRandomLayout(n_macroparticles_per_cell=1)


def basic_simulation():
    grid = Cartesian3DGrid(
        number_of_cells=NUMBER_OF_CELLS,
        lower_bound=[0, 0, 0],
        # cell size is slightly different from 1
        upper_bound=UPPER_BOUNDARY,
        lower_boundary_conditions=["open", "open", "open"],
        upper_boundary_conditions=["open", "open", "open"],
    )
    sim = Simulation(max_steps=0, solver=ElectromagneticSolver(method="Yee", cfl=1.0, grid=grid))
    sim.add_species(
        Species(particle_type="electron", initial_distribution=UniformDistribution(density=1.0e24)),
        LAYOUT,
    )
    for applied_field in APPLIED_FIELDS.values():
        sim.add_applied_field(applied_field())
    sim.diagnostics = [Checkpoint(period=TS[:])]
    return sim


RUN_DIR = ""


def setup_sim():
    sim = basic_simulation()
    if "rosi-hzdr" in rc_params.get("preset", "bash"):
        # On ROSI, the tmp directories are inaccessible to compute nodes.
        sim.picongpu_get_runner().setup_dir = directory_in_home() / "setup"
        sim.picongpu_get_runner().run_dir = directory_in_home() / "run"
    if RUN_DIR:
        sim.picongpu_get_runner().run_dir = RUN_DIR
    else:
        sim.step(0)
    return sim


SIM = None


def _read_field_components(path: Path, field_name: str):
    """
    Read the three components of ``field_name`` and return them in SI units.

    openPMD stores fields as ``F[z][y][x]``; the returned arrays keep that
    layout. Each component is multiplied by its stored ``unit_SI``.
    """
    series = opmd.Series(str(path), opmd.Access.read_only)
    mesh = series.iterations[0].meshes[field_name]
    components = {
        component: mesh[component].load_chunk() * mesh[component].unit_SI for component in ("x", "y", "z")
    }
    grid_spacing = np.asarray(mesh.grid_spacing) * mesh.grid_unit_SI
    grid_global_offset = np.asarray(mesh.grid_global_offset) * mesh.grid_unit_SI
    series.flush()
    series.close()
    return components, grid_spacing, grid_global_offset


def _cell_centers(shape, grid_spacing, grid_global_offset):
    """
    Return the SI coordinates of every cell center, in field layout ``[z][y][x]``.

    Both ``shape`` and openPMD's ``grid_spacing``/``grid_global_offset`` are in
    field order ``(z, y, x)`` (the writer stores them that way), so we build the
    three axis coordinates without reordering.
    """
    z, y, x = (
        grid_global_offset[axis] + np.arange(shape[axis]) * grid_spacing[axis] for axis in range(3)
    )
    z, y, x = np.meshgrid(z, y, x, indexing="ij")
    return x, y, z


class TestAppliedFields(TestCase):
    _result_path = None

    def setUp(self):
        global SIM
        if SIM is None:
            SIM = setup_sim()
            self.sim = SIM
            gather_results(self.result_path)
        self.sim = SIM

    @property
    def result_path(self):
        if self._result_path is None:
            self._result_path = Path(self.sim.picongpu_get_runner().run_dir)
        return self._result_path

    @property
    def checkpoint(self):
        return self.result_path / "simOutput" / "checkpoints" / "checkpoint_000000.bp5"

    def test_dumped_fields_match_the_combined_applied_fields(self):
        time = 0.0  # the step-0 checkpoint is dumped before the first push
        for field_name, prefix, components in (("E", "e", "xyz"), ("B", "b", "xyz")):
            values, grid_spacing, grid_global_offset = _read_field_components(self.checkpoint, field_name)
            shape = values["x"].shape
            self.assertEqual(tuple(shape), tuple(NUMBER_OF_CELLS[::-1]))
            x, y, z = _cell_centers(shape, grid_spacing, grid_global_offset)
            for component in components:
                with self.subTest(field=field_name, component=component):
                    expected = EXPECTED[f"{prefix}{component}"](x, y, z, time)
                    np.testing.assert_allclose(values[component], expected, rtol=1.0e-4)

    def test_single_applied_field_component_is_summed(self):
        # Ex is only contributed by the constant field; guard against a silent
        # loss of that (trivial) contribution.
        values, _, _ = _read_field_components(self.checkpoint, "E")
        np.testing.assert_allclose(values["x"], 1.0e6, rtol=1.0e-4)
