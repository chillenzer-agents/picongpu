"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

import os
import tempfile
from unittest import TestCase

from sympy import Symbol, sqrt

from picongpu import picmi
from picongpu.picmi import ParticleFilter, ParticleFunctor
from picongpu.picmi.particle_functor.particle_functor import MacroParticle, PhysicalParticle
from picongpu.picmi.particle_functor.unit_dimension import UnitDimension
from picongpu.pypicongpu.species.attribute.boundelectrons import BoundElectrons
from picongpu.pypicongpu.species.attribute.momentum import Momentum
from picongpu.pypicongpu.species.attribute.momentum_prev_1 import MomentumPrev1
from picongpu.pypicongpu.species.attribute.particle_id import ParticleId
from picongpu.pypicongpu.species.attribute.probe_e import ProbeE
from picongpu.pypicongpu.species.attribute.radiation_mask import RadiationMask
from picongpu.pypicongpu.species.attribute.weighting import Weighting
from picongpu.pypicongpu.species.attribute.weighting_damping_factor import WeightingDampingFactor


def render(functor, mode="DerivedField"):
    return functor.get_as_pypicongpu(mode)


class TestRequiredAttributes(TestCase):
    """Attributes a functor asks ``Species.register_requirements`` to register."""

    def test_momentum_requires_momentum_attribute(self):
        @ParticleFunctor
        def momentum(particle: MacroParticle):
            return particle.get("momentum")[0]

        self.assertEqual(momentum.get_required_attributes(), [Momentum()])

    def test_momentum_prev_1_requires_its_attribute(self):
        @ParticleFunctor
        def damped(particle: MacroParticle):
            return particle.get("momentumPrev1")

        self.assertEqual(damped.get_required_attributes(), [MomentumPrev1()])

    def test_mass_and_charge_need_no_attribute(self):
        @ParticleFunctor
        def ratio(particle: MacroParticle):
            return particle.get("mass") / particle.get("charge")

        self.assertEqual(ratio.get_required_attributes(), [])

    def test_charge_state_requires_bound_electrons(self):
        @ParticleFunctor
        def state(particle: MacroParticle):
            return particle.get("charge_state")

        self.assertEqual(state.get_required_attributes(), [BoundElectrons()])

    def test_weighting_requires_weighting_attribute(self):
        @ParticleFunctor
        def weight(particle: MacroParticle):
            return particle.get("weighting")

        self.assertEqual(weight.get_required_attributes(), [Weighting()])

    def test_attribute_free_functor_requires_nothing(self):
        @ParticleFunctor
        def nothing(particle: MacroParticle) -> float:
            return 1.0

        self.assertEqual(nothing.get_required_attributes(), [])


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

    def test_unit_factor_number_overrides_auto_derivation(self):
        # A number is implicitly converted (rendered through the PMAccPrinter).
        self.assertEqual(self._get_unit(UnitDimension(M=1), unit_factor=1.0e6), "1000000.0")

    def test_unit_factor_callable_overrides_auto_derivation(self):
        # A no-argument callable returning a sympy expression is rendered through PMAccPrinter.
        self.assertEqual(self._get_unit(UnitDimension(M=1), unit_factor=lambda: sqrt(2)), "pmacc::math::sqrt(2)")

    def test_unit_factor_sympy_symbol_renders_verbatim(self):
        self.assertEqual(self._get_unit(UnitDimension(N=1), unit_factor=Symbol("sim.unit.mass()")), "sim.unit.mass()")

    def test_unit_factor_rejects_cpp_string(self):
        # No C++ strings in the interface: a raw code string must be rejected.
        with self.assertRaises(ValueError):
            self._get_unit(UnitDimension(M=1), unit_factor="my_factor()")

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


class TestParticleDumpFilterRequirementRegistration(TestCase):
    """A filter used only by a ``ParticleDump`` still registers its attributes.

    ``ParticleDump`` has no diagnostic functor, so the old requirement
    walker skipped it entirely and a filtered dump could render a species
    without the attribute the filter reads.
    """

    def test_filter_in_particle_dump_registers_attribute(self):
        from picongpu.picmi.diagnostics import ParticleDump
        from picongpu.picmi.particle_functor import FilteredSpecies

        @ParticleFilter
        def has_prev_momentum(particle: MacroParticle) -> bool:
            return particle.get("momentumPrev1")[0] > 0

        grid = picmi.Cartesian3DGrid(
            number_of_cells=[8, 8, 8],
            lower_bound=[0, 0, 0],
            upper_bound=[8, 8, 8],
            lower_boundary_conditions=["open", "open", "periodic"],
            upper_boundary_conditions=["open", "open", "periodic"],
        )
        sim = picmi.Simulation(
            time_step_size=1.0,
            max_steps=4,
            solver=picmi.ElectromagneticSolver(method="Yee", grid=grid),
        )
        species = picmi.Species(particle_type="electron")
        sim.add_species(species, None)
        sim.add_diagnostic(ParticleDump(species=FilteredSpecies(species=species, functor=has_prev_momentum)))
        converted = sim.get_as_pypicongpu().species[0]
        self.assertIn(MomentumPrev1(), converted.attributes)


class TestCustomTemplatePropagation(TestCase):
    """``Simulation(picongpu_template_dir=...)`` relaxes unknown-name checks."""

    def test_simulation_propagates_custom_templates_to_functors(self):
        import tempfile

        from picongpu.picmi.diagnostics import DerivedFieldDump

        @ParticleFunctor
        def custom(particle: MacroParticle):
            return particle.get("myCustomAttribute")

        grid = picmi.Cartesian3DGrid(
            number_of_cells=[8, 8, 8],
            lower_bound=[0, 0, 0],
            upper_bound=[8, 8, 8],
            lower_boundary_conditions=["open", "open", "periodic"],
            upper_boundary_conditions=["open", "open", "periodic"],
        )
        with tempfile.TemporaryDirectory() as template_dir:
            sim = picmi.Simulation(
                time_step_size=1.0,
                max_steps=4,
                solver=picmi.ElectromagneticSolver(method="Yee", grid=grid),
                picongpu_template_dir=template_dir,
            )
            species = picmi.Species(particle_type="electron")
            sim.add_species(species, None)
            sim.add_diagnostic(DerivedFieldDump(species=species, functor=custom))
            sim._register_functor_requirements()
            self.assertTrue(custom._custom_templates)

        rendered = custom.get_as_pypicongpu("DerivedField")
        self.assertIn("particle[myCustomAttribute_]", rendered.functor_preamble[0].statement)


class TestPositionUnitMetadata(TestCase):
    """``position`` units are scalar for ``getUnit()`` and unit-dependent."""

    def _render(self, unit):
        @ParticleFunctor
        def f(particle: MacroParticle):
            return particle.get("position", origin="cell", unit=unit)[0]

        return render(f)

    def test_cell_unit_is_dimensionless(self):
        rendered = self._render("cell")
        self.assertEqual(rendered.get_unit_cpp, "1.")
        self.assertEqual(rendered.unit_dimension_cpp, "{0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0}")

    def test_si_unit_is_length_with_scalar_factor(self):
        rendered = self._render("si")
        # already converted to metres in the preamble, so getUnit() is 1.
        self.assertEqual(rendered.get_unit_cpp, "1.")
        self.assertEqual(rendered.unit_dimension_cpp, "{1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0}")

    def test_pic_unit_is_internal_length(self):
        rendered = self._render("pic")
        self.assertEqual(rendered.get_unit_cpp, "sim.unit.length()")
        self.assertEqual(rendered.unit_dimension_cpp, "{1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0}")

    def test_get_unit_is_never_a_vector_expression(self):
        for unit in ("cell", "si", "pic"):
            with self.subTest(unit=unit):
                self.assertNotIn("getCellSize", self._render(unit).get_unit_cpp)


class TestTotalCellIdxRendering(TestCase):
    """``DataSpace<simDim>`` has no tuple protocol; bind it as a whole."""

    def test_preamble_does_not_use_structured_binding(self):
        @ParticleFunctor
        def f(particle: MacroParticle):
            return particle.get("totalCellIdx")[0]

        rendered = render(f)
        statements = [s.statement for s in rendered.functor_preamble]
        self.assertEqual(statements, ["auto const totalCellIdx_value = particle[totalCellIdx_];"])
        self.assertNotIn("[", statements[0].split("=")[0])
        self.assertEqual(rendered.functor_expression, "totalCellIdx_value[0]")

    def test_whole_vector_return_type_is_dataspace(self):
        @ParticleFunctor
        def f(particle: MacroParticle):
            return particle.get("totalCellIdx")

        rendered = render(f)
        self.assertEqual(rendered.return_type, "DataSpace<simDim>")
        self.assertIn("totalCellIdx_value[0]", rendered.functor_expression)


class TestWeightingPowerSingleSource(TestCase):
    """The registry encodes the PhysicalParticle rescaling exception explicitly."""

    def test_vs_cpp_trait_and_physical_override(self):
        from picongpu.pypicongpu.species.attribute.registry import ATTRIBUTE_REGISTRY

        self.assertEqual(ATTRIBUTE_REGISTRY["momentum"]().weighting_power, 1)
        self.assertEqual(ATTRIBUTE_REGISTRY["momentum"]().physical_weighting_power, 0)
        self.assertEqual(ATTRIBUTE_REGISTRY["momentumPrev1"]().physical_weighting_power, 0)
        self.assertEqual(ATTRIBUTE_REGISTRY["weighting"]().weighting_power, 1)
        self.assertEqual(ATTRIBUTE_REGISTRY["weighting"]().physical_weighting_power, 0)
        # bound electrons follow the C++ WeightingPower with no override
        self.assertEqual(ATTRIBUTE_REGISTRY["charge_state"]().weighting_power, 1)
        self.assertIsNone(ATTRIBUTE_REGISTRY["charge_state"]().physical_weighting_power)

    def test_physical_scaling_uses_registry(self):
        @ParticleFunctor
        def momentum(particle: PhysicalParticle):
            return particle.get("momentum")[0]

        @ParticleFunctor
        def weight(particle: PhysicalParticle):
            return particle.get("weighting")

        @ParticleFunctor
        def state(particle: PhysicalParticle):
            return particle.get("charge_state")

        self.assertEqual(render(momentum).functor_expression, "px")
        self.assertEqual(render(weight).functor_expression, "weighting")
        self.assertEqual(render(state).functor_expression, "charge_state/weighting")


class TestFilteredDerivedFieldRequirementRegistration(TestCase):
    """A filter inside a ``DerivedFieldDump`` must register its attributes.

    ``DerivedFieldDump`` is handled via the openPMD path, which reads the species
    by name and never converts the ``FilteredSpecies`` wrapper; the filter's
    accessed attributes still have to reach the owning species (regression for
    the ``momentumPrev1`` gap).
    """

    def _converted_species(self, diagnostic):
        grid = picmi.Cartesian3DGrid(
            number_of_cells=[8, 8, 8],
            lower_bound=[0, 0, 0],
            upper_bound=[8, 8, 8],
            lower_boundary_conditions=["open", "open", "periodic"],
            upper_boundary_conditions=["open", "open", "periodic"],
        )
        sim = picmi.Simulation(
            time_step_size=1.0,
            max_steps=4,
            solver=picmi.ElectromagneticSolver(method="Yee", grid=grid),
        )
        species = picmi.Species(particle_type="electron")
        sim.add_species(species, None)
        sim.add_diagnostic(diagnostic(species))
        return sim.get_as_pypicongpu().species[0]

    def test_filter_attributes_are_registered(self):
        from picongpu.picmi.diagnostics import DerivedFieldDump
        from picongpu.picmi.particle_functor import FilteredSpecies

        @ParticleFilter
        def fprev(particle: MacroParticle) -> bool:
            return particle.get("momentumPrev1")[0] > 0

        @ParticleFunctor
        def plain(particle: MacroParticle):
            return particle.get("gamma")

        converted = self._converted_species(
            lambda s: DerivedFieldDump(species=FilteredSpecies(species=s, functor=fprev), functor=plain)
        )
        self.assertIn(MomentumPrev1(), converted.attributes)


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


class TestRegisteredAttributeRendering(TestCase):
    """Rendering and registry-driven defaults for extended attributes."""

    def test_scalar_particle_id(self):
        @ParticleFunctor
        def pid(particle: MacroParticle):
            return particle.get("particleId")

        rendered = render(pid)
        self.assertEqual(rendered.return_type, "uint64_t")
        self.assertIn("particle[particleId_]", rendered.functor_preamble[0].statement)
        self.assertEqual(rendered.functor_expression, "particleId")
        self.assertEqual(rendered.get_unit_cpp, "1.")

    def test_bool_radiation_mask(self):
        @ParticleFunctor
        def mask(particle: MacroParticle) -> bool:
            return particle.get("radiationMask")

        rendered = render(mask)
        self.assertEqual(rendered.return_type, "bool")
        self.assertIn("particle[radiationMask_]", rendered.functor_preamble[0].statement)

    def test_vector_probe_e_indexing_uses_structured_binding(self):
        @ParticleFunctor
        def e_x(particle: MacroParticle):
            return particle.get("probeE")[1]

        rendered = render(e_x)
        self.assertEqual(rendered.return_type, "float_X")
        self.assertEqual(
            rendered.functor_preamble[0].statement,
            "auto const [probeE_0,probeE_1,probeE_2] = particle[probeE_];",
        )
        self.assertEqual(rendered.functor_expression, "probeE_1")
        self.assertEqual(rendered.unit_dimension_cpp, "{1.0, 1.0, -3.0, -1.0, 0.0, 0.0, 0.0}")
        self.assertEqual(rendered.get_unit_cpp, "sim.unit.eField()")

    def test_vector_probe_b_structured_binding(self):
        @ParticleFunctor
        def b_y(particle: MacroParticle):
            return particle.get("probeB")[1]

        rendered = render(b_y)
        self.assertEqual(rendered.functor_expression, "probeB_1")
        self.assertEqual(rendered.unit_dimension_cpp, "{0.0, 1.0, -2.0, -1.0, 0.0, 0.0, 0.0}")
        self.assertEqual(rendered.get_unit_cpp, "sim.unit.bField()")

    def test_whole_vector_return_uses_registry_type(self):
        @ParticleFunctor
        def e_vec(particle: MacroParticle):
            return particle.get("probeE")

        rendered = render(e_vec)
        self.assertEqual(rendered.return_type, "float3_X")
        self.assertEqual(rendered.functor_expression, "{probeE_0, probeE_1, probeE_2}")

    def test_raw_weighting_damping_factor(self):
        @ParticleFunctor
        def damping(particle: MacroParticle):
            return particle.get("weightingDampingFactor")

        rendered = render(damping)
        self.assertEqual(rendered.return_type, "float_X")
        self.assertEqual(rendered.functor_expression, "weightingDampingFactor")
        self.assertIn("particle[weightingDampingFactor_]", rendered.functor_preamble[0].statement)

    def test_derived_damped_weighting_still_available(self):
        @ParticleFunctor
        def damped(particle: MacroParticle):
            return particle.get("damped_weighting")

        rendered = render(damped)
        self.assertIn("getDampedWeighting(particle)", rendered.functor_preamble[0].statement)
        self.assertEqual(rendered.functor_expression, "damped_weighting")

    def test_arbitrary_expression_falls_back_to_float(self):
        @ParticleFunctor
        def doubled(particle: MacroParticle):
            return 2.0 * particle.get("probeE")[0]

        self.assertEqual(render(doubled).return_type, "float_X")


class TestRegisteredAttributeRequirements(TestCase):
    """The registry drives Species.register_requirements."""

    def test_scalar_bool_vector_requirements(self):
        def requirements_for(name):
            @ParticleFunctor
            def f(particle: MacroParticle, n=name):
                value = particle.get(n)
                return value[0] if hasattr(value, "__getitem__") else value

            return f.get_required_attributes()

        self.assertEqual(requirements_for("particleId"), [ParticleId()])
        self.assertEqual(requirements_for("radiationMask"), [RadiationMask()])
        self.assertEqual(requirements_for("probeE"), [ProbeE()])
        self.assertEqual(requirements_for("weightingDampingFactor"), [WeightingDampingFactor()])

    def _render_species_definition(self, diagnostics):
        grid = picmi.Cartesian3DGrid(
            number_of_cells=[8, 8, 8],
            lower_bound=[0, 0, 0],
            upper_bound=[8, 8, 8],
            lower_boundary_conditions=["open", "open", "periodic"],
            upper_boundary_conditions=["open", "open", "periodic"],
        )
        sim = picmi.Simulation(
            time_step_size=1.0,
            max_steps=4,
            solver=picmi.ElectromagneticSolver(method="Yee", grid=grid),
        )
        species = picmi.Species(particle_type="electron")
        sim.add_species(species, None)
        for diagnostic in diagnostics(species):
            sim.add_diagnostic(diagnostic)
        with tempfile.TemporaryDirectory() as tmpdir:
            sim.write_input_file(os.path.join(tmpdir, "input"))
            with open(os.path.join(tmpdir, "input", "include", "picongpu", "param", "speciesDefinition.param")) as f:
                return f.read()

    def test_binning_axis_registers_attribute(self):
        from picongpu.picmi.diagnostics import BinSpec, Binning, BinningAxis

        @ParticleFunctor
        def pid(particle: MacroParticle) -> int:
            return particle.get("particleId")

        @ParticleFunctor
        def count(particle: MacroParticle) -> float:
            return 1.0

        rendered = self._render_species_definition(
            lambda species: [
                Binning(
                    name="pid",
                    deposition_functor=count,
                    axes=[BinningAxis(functor=pid, bin_spec=BinSpec(kind="linear", start=0, stop=100, nsteps=10))],
                    species=species,
                )
            ]
        )
        self.assertIn("particleId", rendered)

    def test_derived_field_registers_vector_attribute(self):
        from picongpu.picmi.diagnostics import DerivedFieldDump

        @ParticleFunctor
        def e_x(particle: MacroParticle) -> float:
            return particle.get("probeE")[0]

        rendered = self._render_species_definition(lambda species: [DerivedFieldDump(species=species, functor=e_x)])
        self.assertIn("probeE", rendered)

    def test_filter_registers_bool_attribute(self):
        from picongpu.picmi.diagnostics import DerivedFieldDump
        from picongpu.picmi.particle_functor import FilteredSpecies

        @ParticleFilter
        def selected(particle: MacroParticle) -> bool:
            return particle.get("radiationMask")

        @ParticleFunctor
        def count(particle: MacroParticle) -> float:
            return 1.0

        rendered = self._render_species_definition(
            lambda species: [
                DerivedFieldDump(species=FilteredSpecies(species=species, functor=selected), functor=count)
            ]
        )
        self.assertIn("radiationMask", rendered)


class TestRegisteredAttributeModeValidation(TestCase):
    """Mode-invalid access raises clearly (including the former broken renders)."""

    def _render(self, attribute, mode="DerivedField", **kwargs):
        @ParticleFunctor
        def f(particle: MacroParticle):
            return particle.get(attribute, **kwargs)

        return render(f, mode)

    def test_position_global_in_derived_field_raises(self):
        with self.assertRaisesRegex(ValueError, "origin='global'.*DerivedField"):
            self._render("position", origin="global")

    def test_position_total_in_derived_field_raises(self):
        with self.assertRaisesRegex(ValueError, "origin='total'.*DerivedField"):
            self._render("position", origin="total")

    def test_position_local_in_derived_field_is_balanced(self):
        @ParticleFunctor
        def f(particle: MacroParticle):
            return particle.get("position", origin="local")[0]

        rendered = render(f)
        self.assertEqual(
            rendered.functor_preamble[0].statement,
            "auto const [xl_cell_cell,yl_cell_cell,zl_cell_cell] = (static_cast<float3_X>(particle[localCellIdx_]));",
        )

    def test_position_cell_in_derived_field_is_balanced(self):
        @ParticleFunctor
        def f(particle: MacroParticle):
            return particle.get("position", origin="cell")[0]

        rendered = render(f)
        self.assertEqual(
            rendered.functor_preamble[0].statement,
            "auto const [xc_cell_cell,yc_cell_cell,zc_cell_cell] = (static_cast<float3_X>(particle[position_]));",
        )

    def test_position_local_in_filter_is_balanced(self):
        @ParticleFunctor
        def f(particle: MacroParticle) -> bool:
            return particle.get("position", origin="local")[0] > 0

        rendered = render(f, "Filter")
        self.assertIn("(static_cast<float3_X>(particle[localCellIdx_]))", rendered.functor_preamble[0].statement)

    def test_position_cell_in_binning_raises(self):
        @ParticleFunctor
        def f(particle: MacroParticle):
            return particle.get("position", origin="cell")[0]

        with self.assertRaisesRegex(ValueError, "origin='cell'.*Binning"):
            render(f, "Binning")

    def test_timestep_unavailable_outside_binning(self):
        for mode in ("DerivedField", "Filter"):
            with self.subTest(mode=mode):
                with self.assertRaisesRegex(ValueError, "only available in Binning"):
                    self._render("timestep", mode)
                with self.assertRaisesRegex(ValueError, "only available in Binning"):
                    self._render("timestep_size", mode)

    def test_timestep_available_in_binning(self):
        rendered = self._render("timestep", "Binning")
        self.assertEqual(rendered.functor_preamble[0].statement, "auto const timestep = domainInfo.currentStep;")

    def test_unknown_attribute_raises_without_custom_templates(self):
        @ParticleFunctor
        def f(particle: MacroParticle):
            return particle.get("nonexistentThing")

        with self.assertRaisesRegex(ValueError, "Unknown particle attribute 'nonexistentThing'"):
            render(f)

    def test_unknown_attribute_allowed_with_custom_templates(self):
        @ParticleFunctor
        def f(particle: MacroParticle):
            return particle.get("myCustomAttribute")

        rendered = f.get_as_pypicongpu("DerivedField", custom_templates=True)
        self.assertIn("particle[myCustomAttribute_]", rendered.functor_preamble[0].statement)

    def test_whole_vector_outside_derived_field_raises(self):
        for mode in ("Binning", "Filter"):
            with self.subTest(mode=mode):

                @ParticleFunctor
                def f(particle: MacroParticle):
                    return particle.get("probeE")

                with self.assertRaisesRegex(ValueError, "whole vector attribute 'probeE'"):
                    render(f, mode)


class TestRegisteredAttributeScaling(TestCase):
    """Registry ``WeightingPower`` drives PhysicalParticle rescaling."""

    def _expression(self, functor):
        return render(functor).functor_expression

    def test_charge_state_is_now_rescaled(self):
        @ParticleFunctor
        def state(particle: PhysicalParticle):
            return particle.get("charge_state")

        self.assertEqual(self._expression(state), "charge_state/weighting")

    def test_probe_e_is_not_rescaled(self):
        @ParticleFunctor
        def e_x(particle: PhysicalParticle):
            return particle.get("probeE")[0]

        self.assertEqual(self._expression(e_x), "probeE_0")

    def test_particle_id_is_not_rescaled(self):
        @ParticleFunctor
        def pid(particle: PhysicalParticle):
            return particle.get("particleId")

        self.assertEqual(self._expression(pid), "particleId")

    def test_momentum_remains_per_particle(self):
        @ParticleFunctor
        def momentum(particle: PhysicalParticle):
            return particle.get("momentum")[0]

        self.assertEqual(self._expression(momentum), "px")


if __name__ == "__main__":
    import unittest

    unittest.main()
