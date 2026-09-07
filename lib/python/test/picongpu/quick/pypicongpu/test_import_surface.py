"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

import builtins
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


class TestStarImport(TestCase):
    """
    pin the exact `from picongpu.pypicongpu import *` surface so that neither
    drift of documented names nor leaked internals (e.g. `sys`) go unnoticed.
    """

    EXPECTED_NAMES = {
        # explicit submodules
        "collision",
        "customuserinput",
        "field_solver",
        "grid",
        "laser",
        "movingwindow",
        "output",
        "particle_functor",
        "rendering",
        "runner",
        "simulation",
        "species",
        "util",
        "walltime",
        # classes
        "Checkpoint",
        "EnergyHistogram",
        "LeheSolver",
        "MacroParticleCount",
        "PhaseSpace",
        "Runner",
        "Simulation",
        "YeeSolver",
    }

    def test_star_surface_is_exactly_the_expected_set(self):
        namespace = {"__builtins__": builtins}
        exec("from picongpu.pypicongpu import *", namespace)  # noqa: S102
        namespace.pop("__builtins__", None)
        self.assertEqual(set(namespace), self.EXPECTED_NAMES)
