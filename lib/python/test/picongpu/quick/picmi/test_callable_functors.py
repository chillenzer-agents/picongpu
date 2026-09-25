"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
License: GPLv3+
"""

from unittest import TestCase

from pydantic import ValidationError

from picongpu import picmi
from picongpu.picmi.diagnostics import Binning, BinningAxis, BinSpec, DerivedFieldDump
from picongpu.picmi.distribution.AnalyticDistribution import AnalyticDistribution
from picongpu.picmi.particle_functor import ParticleFilter, ParticleFunctor
from picongpu.pypicongpu.util import as_functor


def positive(particle):
    return particle.get("momentum")[0] > 0


def kinetic_energy(particle):
    return particle.get("kinetic energy")


def density(x, y, z):
    return x + y + z


def bin_spec():
    return BinSpec(kind="linear", start=0, stop=1, nsteps=1)


class TestCallableFunctorsAccepted(TestCase):
    """A bare named callable of the right signature is coerced into the field's declared functor class."""

    def setUp(self):
        self.species = picmi.Species(name="e", particle_type="electron")

    def test_filtered_species_functor_is_coerced_to_particle_filter(self):
        # bare named callable -> ParticleFilter
        coerced = picmi.FilteredSpecies(species=self.species, functor=positive)
        explicit = picmi.FilteredSpecies(
            species=self.species, functor=ParticleFilter(name="positive", functor=positive)
        )

        self.assertIsInstance(coerced.functor, ParticleFilter)
        self.assertEqual(type(coerced.functor), type(explicit.functor))
        self.assertEqual(coerced.functor.name, explicit.functor.name)

        converted_coerced = coerced.get_as_pypicongpu(mode="Filter")
        converted_explicit = explicit.get_as_pypicongpu(mode="Filter")
        self.assertEqual(converted_coerced, converted_explicit)

    def test_binning_axis_functor_is_coerced_to_particle_functor(self):
        coerced = BinningAxis(functor=kinetic_energy, bin_spec=bin_spec())
        explicit = BinningAxis(
            functor=ParticleFunctor(name="kinetic_energy", functor=kinetic_energy), bin_spec=bin_spec()
        )

        self.assertIsInstance(coerced.functor, ParticleFunctor)
        self.assertNotIsInstance(coerced.functor, ParticleFilter)
        self.assertEqual(coerced.functor.name, explicit.functor.name)
        self.assertEqual(coerced.functor.name, "kinetic_energy")

        axis_coerced = coerced.get_as_pypicongpu()
        axis_explicit = explicit.get_as_pypicongpu()
        self.assertEqual(axis_coerced.axis_functor, axis_explicit.axis_functor)
        self.assertEqual(axis_coerced.axis_name, axis_explicit.axis_name)

    def test_binning_deposition_functor_is_coerced_to_particle_functor(self):
        coerced = Binning(
            name="b",
            deposition_functor=kinetic_energy,
            axes=[BinningAxis(functor=kinetic_energy, bin_spec=bin_spec())],
            species=self.species,
        )
        explicit = Binning(
            name="b",
            deposition_functor=ParticleFunctor(name="kinetic_energy", functor=kinetic_energy),
            axes=[
                BinningAxis(functor=ParticleFunctor(name="kinetic_energy", functor=kinetic_energy), bin_spec=bin_spec())
            ],
            species=self.species,
        )

        self.assertIsInstance(coerced.deposition_functor, ParticleFunctor)
        self.assertEqual(coerced.deposition_functor.name, explicit.deposition_functor.name)

        self.assertEqual(
            coerced.get_as_pypicongpu(time_step_size=1, num_steps=1),
            explicit.get_as_pypicongpu(time_step_size=1, num_steps=1),
        )

    def test_derived_field_dump_functor_is_coerced_to_particle_functor(self):
        coerced = DerivedFieldDump(species=self.species, functor=kinetic_energy)
        explicit = DerivedFieldDump(
            species=self.species, functor=ParticleFunctor(name="kinetic_energy", functor=kinetic_energy)
        )

        self.assertIsInstance(coerced.functor, ParticleFunctor)
        self.assertEqual(coerced.functor.name, explicit.functor.name)
        self.assertEqual(coerced.fieldname, explicit.fieldname)
        self.assertEqual(coerced.species_name, explicit.species_name)
        self.assertEqual(coerced.filtername, explicit.filtername)

    def test_species_initial_distribution_is_coerced_to_analytic_distribution(self):
        coerced = picmi.Species(name="e", particle_type="electron", initial_distribution=density)
        explicit = picmi.Species(
            name="e", particle_type="electron", initial_distribution=AnalyticDistribution(density_function=density)
        )

        self.assertIsInstance(coerced.initial_distribution, AnalyticDistribution)
        self.assertEqual(
            coerced.initial_distribution.density_expression, explicit.initial_distribution.density_expression
        )
        self.assertEqual(
            coerced.initial_distribution.get_as_pypicongpu(None),
            explicit.initial_distribution.get_as_pypicongpu(None),
        )

    def test_species_initial_distribution_list_of_callables_is_coerced(self):
        coerced = picmi.Species(name="e", particle_type="electron", initial_distribution=[density])
        explicit = picmi.Species(
            name="e", particle_type="electron", initial_distribution=[AnalyticDistribution(density_function=density)]
        )

        self.assertEqual(len(coerced.initial_distribution), 1)
        self.assertIsInstance(coerced.initial_distribution[0], AnalyticDistribution)
        self.assertEqual(
            coerced.initial_distribution[0].density_expression, explicit.initial_distribution[0].density_expression
        )

    def test_existing_instances_and_decorators_stay_unchanged(self):
        filter_instance = ParticleFilter(name="positive", functor=positive)
        self.assertIs(picmi.FilteredSpecies(species=self.species, functor=filter_instance).functor, filter_instance)

        distribution_instance = AnalyticDistribution(density_function=density)
        self.assertIs(
            picmi.Species(
                name="e", particle_type="electron", initial_distribution=distribution_instance
            ).initial_distribution,
            distribution_instance,
        )

        @ParticleFunctor
        def decorated(particle):
            return particle.get("weighting")

        self.assertIsInstance(decorated, ParticleFunctor)

        @ParticleFilter
        def decorated_filter(particle):
            return particle.get("momentum")[0] > 0

        self.assertIsInstance(decorated_filter, ParticleFilter)


class TestCallableFunctorsRejected(TestCase):
    """Anonymous callables and C++-invalid names fail eagerly with a pydantic ValidationError."""

    def setUp(self):
        self.species = picmi.Species(name="e", particle_type="electron")

    def test_lambda_rejected_everywhere(self):
        cases = {
            "FilteredSpecies": lambda: picmi.FilteredSpecies(species=self.species, functor=lambda p: True),
            "BinningAxis": lambda: BinningAxis(functor=lambda p: 1.0, bin_spec=bin_spec()),
            "Binning": lambda: Binning(
                name="b",
                deposition_functor=lambda p: 1.0,
                axes=[BinningAxis(functor=kinetic_energy, bin_spec=bin_spec())],
                species=self.species,
            ),
            "DerivedFieldDump": lambda: DerivedFieldDump(species=self.species, functor=lambda p: 1.0),
            "Species": lambda: picmi.Species(
                name="e", particle_type="electron", initial_distribution=lambda x, y, z: x + y + z
            ),
        }
        for label, construct in cases.items():
            with self.subTest(site=label):
                with self.assertRaises(ValidationError):
                    construct()

    def test_invalid_cpp_identifier_rejected_everywhere(self):
        def müller(particle):
            return 1.0

        cases = {
            "FilteredSpecies": lambda: picmi.FilteredSpecies(species=self.species, functor=müller),
            "BinningAxis": lambda: BinningAxis(functor=müller, bin_spec=bin_spec()),
            "Binning": lambda: Binning(
                name="b",
                deposition_functor=müller,
                axes=[BinningAxis(functor=kinetic_energy, bin_spec=bin_spec())],
                species=self.species,
            ),
            "DerivedFieldDump": lambda: DerivedFieldDump(species=self.species, functor=müller),
            "Species": lambda: picmi.Species(name="e", particle_type="electron", initial_distribution=müller),
        }
        for label, construct in cases.items():
            with self.subTest(site=label):
                with self.assertRaises(ValidationError):
                    construct()

    def test_particle_functor_name_is_validated(self):
        with self.assertRaises(ValidationError):
            ParticleFunctor(functor=positive, name="not a valid identifier")
        # the explicit valid spelling still works
        self.assertEqual(ParticleFunctor(functor=positive, name="valid_name").name, "valid_name")

    def test_classes_are_rejected_eagerly_at_all_sites(self):
        # A class is callable and has a valid __name__, but passing it is a user
        # error: it must not be coerced into a functor wrapping the class itself.
        cases = {
            "FilteredSpecies": lambda: picmi.FilteredSpecies(species=self.species, functor=ParticleFilter),
            "BinningAxis": lambda: BinningAxis(functor=ParticleFunctor, bin_spec=bin_spec()),
            "Binning": lambda: Binning(
                name="b",
                deposition_functor=ParticleFunctor,
                axes=[BinningAxis(functor=kinetic_energy, bin_spec=bin_spec())],
                species=self.species,
            ),
            "DerivedFieldDump": lambda: DerivedFieldDump(species=self.species, functor=ParticleFunctor),
            "Species": lambda: picmi.Species(
                name="e", particle_type="electron", initial_distribution=AnalyticDistribution
            ),
        }
        for label, construct in cases.items():
            with self.subTest(site=label):
                with self.assertRaises(ValidationError):
                    construct()


class TestAsFunctorHelper(TestCase):
    """The generic coercion helper only fires for callables that are not already instances."""

    def test_helper_returns_instances_unchanged(self):
        validator = as_functor(AnalyticDistribution, usage="AnalyticDistribution(density_function=...).")
        check = validator.func

        instance = AnalyticDistribution(density_function=density)
        self.assertIs(check(instance), instance)

        coerced = check(density)
        self.assertIsInstance(coerced, AnalyticDistribution)

    def test_helper_rejects_anonymous_and_invalid_names(self):
        validator = as_functor(AnalyticDistribution, usage="AnalyticDistribution(density_function=...).")
        check = validator.func

        with self.assertRaises(ValueError):
            check(lambda x, y, z: x)

        def müller(x, y, z):
            return x

        with self.assertRaises(ValueError):
            check(müller)
