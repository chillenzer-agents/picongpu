"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

from types import ModuleType
from unittest import TestCase

from picongpu import pypicongpu


class TestPyPIConGPUExplicitModules(TestCase):
    """
    modules that were previously only reachable as transitive import side
    effects of `simulation` must now be explicit attributes.
    """

    def test_modules_are_explicit_attributes(self):
        self.assertIsInstance(pypicongpu.collision, ModuleType)
        self.assertIsInstance(pypicongpu.field_solver, ModuleType)
        self.assertIsInstance(pypicongpu.particle_functor, ModuleType)
        self.assertIsInstance(pypicongpu.movingwindow, ModuleType)
        self.assertIsInstance(pypicongpu.walltime, ModuleType)


class TestPyPIConGPUClassSurface(TestCase):
    def test_solver_classes(self):
        self.assertEqual(pypicongpu.YeeSolver.__module__, "picongpu.pypicongpu.field_solver.Yee")
        self.assertEqual(pypicongpu.LeheSolver.__module__, "picongpu.pypicongpu.field_solver.Lehe")

    def test_any_solver(self):
        from picongpu.pypicongpu.field_solver import AnySolver

        self.assertIs(pypicongpu.field_solver.AnySolver, AnySolver)
