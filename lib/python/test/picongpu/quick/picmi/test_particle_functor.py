"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

from unittest import TestCase

from picongpu.picmi import ParticleFunctor
from picongpu.picmi.particle_functor.particle_functor import MacroParticle, PhysicalParticle
from picongpu.picmi.particle_functor.unit_dimension import UnitDimension
from picongpu.pypicongpu.particle_functor import derive_requirements


def render(functor, mode="DerivedField"):
    return functor.get_as_pypicongpu(mode)


class TestRequirementDerivation(TestCase):
    """The C++ eligibility trait a functor emits (QA #1)."""

    def _ident_and_flag(self, functor):
        model = render(functor)
        return model.identifier_requirement_cpp, model.flag_requirement_cpp

    def test_mass_requires_mass_ratio_flag(self):
        @ParticleFunctor
        def mass(particle: MacroParticle):
            return particle.get("mass")

        identifiers, flag = self._ident_and_flag(mass)
        self.assertIn("MakeSeq_t<weighting>", identifiers)
        self.assertIn("HasFlag<FrameType, massRatio<>>", flag)

    def test_velocity_requires_mass_ratio_flag(self):
        @ParticleFunctor
        def velocity(particle: MacroParticle):
            return particle.get("velocity")[0]

        identifiers, flag = self._ident_and_flag(velocity)
        self.assertIn("momentum", identifiers)
        self.assertIn("weighting", identifiers)
        self.assertIn("HasFlag<FrameType, massRatio<>>", flag)

    def test_gamma_and_kinetic_energy_require_mass_ratio_flag(self):
        @ParticleFunctor
        def gamma(particle: MacroParticle):
            return particle.get("gamma")

        @ParticleFunctor
        def kinetic_energy(particle: MacroParticle):
            return particle.get("kinetic energy")

        for functor in (gamma, kinetic_energy):
            _, flag = self._ident_and_flag(functor)
            self.assertIn("HasFlag<FrameType, massRatio<>>", flag)

    def test_charge_requires_charge_ratio_flag(self):
        @ParticleFunctor
        def charge(particle: MacroParticle):
            return particle.get("charge")

        _, flag = self._ident_and_flag(charge)
        self.assertIn("HasFlag<FrameType, chargeRatio<>>", flag)

    def test_mass_over_charge_combines_both_flags(self):
        @ParticleFunctor
        def ratio(particle: MacroParticle):
            return particle.get("mass") / particle.get("charge")

        _, flag = self._ident_and_flag(ratio)
        self.assertIn("pmacc::mp_and<", flag)
        self.assertIn("HasFlag<FrameType, massRatio<>>::type", flag)
        self.assertIn("HasFlag<FrameType, chargeRatio<>>::type", flag)

    def test_attribute_free_functor_emits_true(self):
        @ParticleFunctor
        def nothing(particle: MacroParticle) -> float:
            return 1.0

        identifiers, flag = self._ident_and_flag(nothing)
        self.assertEqual(identifiers, "pmacc::mp_bool<true>")
        self.assertEqual(flag, "pmacc::mp_bool<true>")

    def test_derive_requirements_combines_and_dedups(self):
        identifiers, flags = derive_requirements({1: "mass", 2: "charge"})
        self.assertEqual(identifiers, ["weighting"])
        self.assertEqual(flags, ["chargeRatio<>", "massRatio<>"])

    def test_derive_requirements_ignores_position_and_random_number(self):
        identifiers, flags = derive_requirements(
            {
                1: ("position", "total", "cell", "cell"),
                2: "mass",
                3: "random_number",
            }
        )
        self.assertEqual(identifiers, ["weighting"])
        self.assertEqual(flags, ["massRatio<>"])

    def test_derive_requirements_empty(self):
        identifiers, flags = derive_requirements({})
        self.assertEqual(identifiers, [])
        self.assertEqual(flags, [])


class TestUnitDerivation(TestCase):
    """getUnit / getUnitDimension auto-derivation (QA #4/#5)."""

    def _get_unit(self, unit_dimension, unit_factor=None):
        @ParticleFunctor(unit_dimension=unit_dimension, unit_factor=unit_factor)
        def f(particle: MacroParticle) -> float:
            return 1.0

        return render(f).get_unit_cpp

    def _unit_dimension_cpp(self, unit_dimension):
        @ParticleFunctor(unit_dimension=unit_dimension)
        def f(particle: MacroParticle) -> float:
            return 1.0

        return render(f).unit_dimension_cpp

    def test_mass(self):
        self.assertEqual(self._get_unit(UnitDimension(M=1)), "sim.unit.mass()")

    def test_momentum(self):
        self.assertEqual(
            self._get_unit(UnitDimension(L=1, M=1, T=-1)),
            "(sim.unit.length() * sim.unit.mass()) / (sim.unit.time())",
        )

    def test_energy(self):
        self.assertEqual(
            self._get_unit(UnitDimension(L=2, M=1, T=-2)),
            "(sim.unit.length() * sim.unit.length() * sim.unit.mass()) / (sim.unit.time() * sim.unit.time())",
        )

    def test_charge(self):
        self.assertEqual(self._get_unit(UnitDimension(I=1)), "(sim.unit.charge()) / (sim.unit.time())")

    def test_dimensionless(self):
        self.assertEqual(self._get_unit(UnitDimension()), "1.")

    def test_unit_factor_overrides_auto_derivation(self):
        self.assertEqual(self._get_unit(UnitDimension(M=1), unit_factor="my_factor()"), "my_factor()")

    def test_unit_dimension_rendered_as_seven_vector(self):
        self.assertEqual(
            self._unit_dimension_cpp(UnitDimension(L=2, M=1, T=-2)), "{2.0, 1.0, -2.0, 0.0, 0.0, 0.0, 0.0}"
        )

    def test_fractional_exponent_raises(self):
        @ParticleFunctor(unit_dimension=UnitDimension(L=0.5))
        def f(particle: MacroParticle) -> float:
            return 1.0

        # A non-integer 7-vector cannot be turned into a numeric getUnit(); it must be
        # rejected (not silently rounded to a plausible-looking but wrong scale).
        with self.assertRaises(ValueError):
            render(f)

    def test_non_base_unit_component_raises(self):
        @ParticleFunctor(unit_dimension=UnitDimension(N=1))
        def f(particle: MacroParticle) -> float:
            return 1.0

        with self.assertRaises(ValueError):
            render(f)


class TestPhysicalParticleScaling(TestCase):
    """Default (non-manual) PhysicalParticle rescaling must not crash (QA #2)."""

    def _expression(self, functor):
        return render(functor).functor_expression

    def test_physical_momentum_is_identity(self):
        @ParticleFunctor
        def momentum(particle: PhysicalParticle):
            return particle.get("momentum")[0]

        self.assertEqual(self._expression(momentum), "px")

    def test_physical_velocity_is_identity(self):
        @ParticleFunctor
        def velocity(particle: PhysicalParticle):
            return particle.get("velocity")[0]

        self.assertEqual(self._expression(velocity), "vx")

    def test_physical_position_is_identity(self):
        @ParticleFunctor
        def position(particle: PhysicalParticle):
            return particle.get("position", origin="cell")[0]

        self.assertEqual(self._expression(position), "xc_cell_cell")

    def test_physical_damped_weighting_is_identity(self):
        @ParticleFunctor
        def damped(particle: PhysicalParticle):
            return particle.get("damped_weighting")

        self.assertEqual(self._expression(damped), "damped_weighting")

    def test_physical_mass_is_rescaled(self):
        @ParticleFunctor
        def mass(particle: PhysicalParticle):
            return particle.get("mass")

        self.assertEqual(self._expression(mass), "mass/weighting")

    def test_physical_charge_is_rescaled(self):
        @ParticleFunctor
        def charge(particle: PhysicalParticle):
            return particle.get("charge")

        self.assertEqual(self._expression(charge), "charge/weighting")


class TestParticleClassResolution(TestCase):
    """First-argument annotation resolution (QA #3)."""

    def test_explicit_macro(self):
        @ParticleFunctor
        def f(particle: MacroParticle):
            return particle.get("mass")

        self.assertIs(f._particle_class(), MacroParticle)

    def test_explicit_physical(self):
        @ParticleFunctor
        def f(particle: PhysicalParticle):
            return particle.get("mass")

        self.assertIs(f._particle_class(), PhysicalParticle)

    def test_string_forward_ref_resolves_to_physical(self):
        @ParticleFunctor
        def f(particle: "PhysicalParticle"):
            return particle.get("mass")

        self.assertIs(f._particle_class(), PhysicalParticle)

    def test_string_forward_ref_allows_scaling(self):
        @ParticleFunctor(scales_with_weighting=1)
        def f(particle: "PhysicalParticle"):
            return particle.get("mass")

        # A string-annotated PhysicalParticle must NOT be rejected as non-Physical.
        self.assertIs(f._particle_class(), PhysicalParticle)
        # And it must render without error.
        render(f)

    def test_no_annotation_defaults_to_macro(self):
        @ParticleFunctor
        def f(particle):
            return particle.get("mass")

        self.assertIs(f._particle_class(), MacroParticle)

    def test_zero_arg_functor_raises_clear_error(self):
        with self.assertRaises(TypeError):

            @ParticleFunctor
            def f():
                return 1

    def test_scaling_on_non_physical_raises(self):
        with self.assertRaises(TypeError):

            @ParticleFunctor(scales_with_weighting=1)
            def f(particle: MacroParticle):
                return particle.get("mass")


if __name__ == "__main__":
    import unittest

    unittest.main()
