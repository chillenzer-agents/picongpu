"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

import builtins
from unittest import TestCase

import picongpu.picmi as picmi_module
from picongpu import picmi
from picongpu.picmi import diagnostics, particle_functor
from picongpu.picmi.diagnostics import BinningFunctor, RadiationObserverConfiguration
from picongpu.picmi.particle_functor import ParticleFunctor, RNGArg, UnitDimension
from picongpu.picmi.particle_functor import I as I_public
from picongpu.picmi.particle_functor import L as L_public
from picongpu.picmi.particle_functor import M as M_public
from picongpu.picmi.particle_functor import T as T_public
from picongpu.picmi.particle_functor.unit_dimension import I as I_from_unit_dimension
from picongpu.picmi.particle_functor.unit_dimension import L as L_from_unit_dimension
from picongpu.picmi.particle_functor.unit_dimension import M as M_from_unit_dimension
from picongpu.picmi.particle_functor.unit_dimension import T as T_from_unit_dimension


class TestPromotedNames(TestCase):
    """
    the previously deep-path-only names must be reachable at picmi.X
    """

    def test_polarization_type(self):
        self.assertIs(picmi.PolarizationType, picmi.lasers.PolarizationType)

    def test_collisional_physics_setup(self):
        self.assertIs(picmi.CollisionalPhysicsSetup, picmi.interaction.CollisionalPhysicsSetup)

    def test_radiation_observer_configuration(self):
        self.assertIs(diagnostics.RadiationObserverConfiguration, RadiationObserverConfiguration)

    def test_binning_functor(self):
        # BinningFunctor is a module-level alias of ParticleFunctor
        self.assertIs(diagnostics.BinningFunctor, BinningFunctor)
        self.assertIs(BinningFunctor, ParticleFunctor)

    def test_rng_arg(self):
        self.assertIs(particle_functor.RNGArg, RNGArg)

    def test_unit_aliases_are_module_objects(self):
        self.assertIs(particle_functor.I, I_public)
        self.assertIs(particle_functor.L, L_public)
        self.assertIs(particle_functor.M, M_public)
        self.assertIs(particle_functor.T, T_public)
        self.assertIs(particle_functor.UnitDimension, UnitDimension)

    def test_unit_aliases_are_the_unit_dimension_module_objects(self):
        self.assertIs(I_public, I_from_unit_dimension)
        self.assertIs(L_public, L_from_unit_dimension)
        self.assertIs(M_public, M_from_unit_dimension)
        self.assertIs(T_public, T_from_unit_dimension)


class TestStarImport(TestCase):
    """
    the documented surface must be reachable via `from picongpu.picmi import *`,
    which now relies on the default (no `__all__`) star-import behaviour.
    """

    EXPECTED_NAMES = {
        # modules whose subpackage-import side effects are part of the surface
        "constants",
        "diagnostics",
        "distribution",
        "grid",
        "interaction",
        "lasers",
        "layout",
        "particle_functor",
        "simulation",
        "solver",
        "species",
        # classes
        "Simulation",
        "ParticleFunctor",
        "Cartesian3DGrid",
        "ElectromagneticSolver",
        "BinomialSmoother",
        "DispersivePulseLaser",
        "FromOpenPMDPulseLaser",
        "GaussianLaser",
        "TWTSLaser",
        "PlaneWaveLaser",
        "Species",
        "FilteredSpecies",
        "ParticleFilter",
        "PseudoRandomLayout",
        "GriddedLayout",
        "OnePositionLayout",
        "FoilDistribution",
        "UniformDistribution",
        "GaussianDistribution",
        "AnalyticDistribution",
        "CylindricalDistribution",
        "ADK",
        "ADKVariant",
        "BSI",
        "BSIExtension",
        "Keldysh",
        "ThomasFermi",
        "Synchrotron",
        "Interaction",
        "Collision",
        "ConstLogCollision",
        "DynamicLogCollision",
        # newly promoted flag-classes / types
        "PolarizationType",
        "CollisionalPhysicsSetup",
    }

    def test_no_all_anymore(self):
        self.assertFalse(hasattr(picmi_module, "__all__"))

    def _star_import(self):
        namespace = {"__builtins__": builtins}
        exec("from picongpu.picmi import *", namespace)  # noqa: S102
        return namespace

    def test_all_documented_names_reachable_via_star(self):
        namespace = self._star_import()
        missing = self.EXPECTED_NAMES - set(namespace)
        self.assertEqual(missing, set())

    def test_star_import_reaches_promoted_names(self):
        namespace = self._star_import()
        self.assertIs(namespace["PolarizationType"], picmi.PolarizationType)
        self.assertIs(namespace["CollisionalPhysicsSetup"], picmi.CollisionalPhysicsSetup)
