"""
This file is part of PIConGPU.
Copyright 2025 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

import re
from unittest import TestCase

import pytest
from picongpu.picmi.interaction.ionization.fieldionization import ADK, BSI
from picongpu.picmi.species import Species
from picongpu.picmi.species_requirements import RequirementConflict, SetChargeStateOperation, run_construction
from picongpu.pypicongpu.species.attribute.weighting import Weighting
from picongpu.pypicongpu.species.constant.mass import Mass
from picongpu.pypicongpu.species.operation.setchargestate import SetChargeState
from picongpu.pypicongpu.species.species import Pusher, Shape


def species(**kwargs):
    return Species(name="electron", particle_type="electron", **kwargs)


class TestSpeciesShapeAndMethod(TestCase):
    def _assert_converts(self, shape, method, expected_shape, expected_pusher):
        pypicongpu_species = species(particle_shape=shape, method=method).get_as_pypicongpu()
        self.assertIs(pypicongpu_species.shape, expected_shape)
        self.assertIs(pypicongpu_species.pusher, expected_pusher)

    def test_standard_shapes(self):
        for shape, expected in {
            "NGP": Shape.NGP,
            "linear": Shape.linear,
            "quadratic": Shape.quadratic,
            "cubic": Shape.cubic,
        }.items():
            with self.subTest(shape=shape):
                self._assert_converts(shape, "Boris", expected, Pusher.Boris)

    def test_standard_pusher_methods(self):
        for method, expected in {
            "Boris": Pusher.Boris,
            "Vay": Pusher.Vay,
            "Higuera-Cary": Pusher.HigueraCary,
            "free-streaming": Pusher.Free,
            "LLRK4": Pusher.ReducedLandauLifshitz,
        }.items():
            with self.subTest(method=method):
                self._assert_converts("quadratic", method, Shape.quadratic, expected)

    def test_picongpu_extensions(self):
        self._assert_converts("other:quartic", "other:Acceleration", Shape.quartic, Pusher.Acceleration)
        self._assert_converts("other:counter", "other:Photon", Shape.counter, Pusher.Photon)
        self._assert_converts("other:quartic", "other:Probe", Shape.quartic, Pusher.Probe)
        self._assert_converts("other:quartic", "other:Axel", Shape.quartic, Pusher.Axel)

    def test_method_explicitly_set_does_not_crash(self):
        # Regression: picmistandard's _validate_method used to raise
        # AttributeError for any explicit (non-default) method.
        pypicongpu_species = species(method="Vay").get_as_pypicongpu()
        self.assertIs(pypicongpu_species.pusher, Pusher.Vay)

    def test_standard_unimplemented_method_accepted_but_rejected_at_conversion(self):
        # "Li" is a standard method that PIConGPU does not implement.
        construct = species(method="Li")
        self.assertEqual(construct.method, "Li")
        with self.assertRaises(ValueError, msg="Li must be rejected at conversion time"):
            construct.get_as_pypicongpu()

    def test_unknown_other_accepted_but_rejected_at_conversion(self):
        for value in ("other:SomeUnknownPusher", "other:SomeUnknownShape"):
            with self.subTest(value=value):
                field = "method" if value.startswith("other:SomeUnknownPusher") else "particle_shape"
                construct = species(**{field: value})
                with self.assertRaises(ValueError, msg=f"{value} must be rejected at conversion time"):
                    construct.get_as_pypicongpu()


def unique_in(elements, collection):
    collection = list(collection)
    return (collection.count(e) == 1 for e in elements)


def _cpp_identifier(name: str) -> bool:
    return re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) is not None


class TestPusherShapeTranslation(TestCase):
    """the picmi->pypicongpu pusher/shape bridge must not drift from the C++
    names (identifier-ness only: the existence of the matching C++ struct is
    not checked here, see the `Pusher.Axel` note in `species.py`)"""

    def test_pusher_members_are_cpp_identifiers(self):
        # the pypicongpu Pusher values render into particles::pusher::<value>,
        # so every value must be a valid C++ identifier (identifier-ness only,
        # the C++ struct itself is not checked)
        for pusher in Pusher:
            assert _cpp_identifier(pusher.value), f"pusher value {pusher.value!r} is not a C++ identifier"

    def test_particle_shape_members_are_cpp_identifiers(self):
        # identifier-ness only, the C++ struct itself is not checked
        for shape in Shape:
            assert _cpp_identifier(shape.value), f"shape value {shape.value!r} is not a C++ identifier"


class TestSpeciesRequirementResolution(TestCase):
    def test_deduplicate_attributes(self):
        species = Species(name="dummy")
        requirements = [Weighting()]
        species.register_requirements(2 * requirements)
        assert all(unique_in(requirements, species.get_as_pypicongpu().attributes))

    def test_deduplicate_delayed_construction(self):
        species = Species(name="dummy", particle_type="H", charge_state=1)
        requirements = [SetChargeStateOperation(species)]
        species.register_requirements(2 * requirements)
        assert all(unique_in(requirements, species.get_operation_requirements()))

    def test_conflicting_constants(self):
        species = Species(name="dummy")
        requirements = [Mass(mass_si=1.0), Mass(mass_si=2.0)]
        with pytest.raises(RequirementConflict):
            # Not yet decided which one should raise, but one of them definitely will.
            species.register_requirements(requirements)
            species.get_as_pypicongpu()

    def test_ionization(self):
        ion = Species(name="ion", particle_type="H", charge_state=1)
        electron = Species(name="electron", particle_type="electron")
        # These all register requirements:
        ionizations = [
            # Not great: Production code would use the enums not their integer represenation.
            ADK(ion_species=ion, ionization_electron_species=electron, ADK_variant=0, ionization_current=None),
            BSI(ion_species=ion, ionization_electron_species=electron, BSI_extensions=[0], ionization_current=None),
        ]

        # Ionization makes the ion depend on the electron species.
        # This is important for rendering the corresponding C++ header,
        # so the electron species gets defined before the ion species.
        assert electron < ion

        set_charge_state_op = [
            run_construction(op) for op in ion.get_operation_requirements() if op.metadata.Type == SetChargeState
        ][0]
        assert set_charge_state_op.charge_state == ion.charge_state
        assert len(ion.get_as_pypicongpu().constants.ground_state_ionization.ionization_model_list) == len(ionizations)


class TestIonizationBridging(TestCase):
    """the picmi ionization models bridge to the pypicongpu (C++-named) ionizers"""

    def _species(self):
        ion = Species(name="ion", particle_type="H", charge_state=1)
        electron = Species(name="electron", particle_type="electron")
        return ion, electron

    def test_adk_none_current_bridges_to_none_current_model(self):
        ion, electron = self._species()
        model = ADK(ion_species=ion, ionization_electron_species=electron, ADK_variant=0, ionization_current=None)
        pypic = model.get_as_pypicongpu()
        # no current given -> the pypicongpu None_ current (C++ default current::None)
        from picongpu.pypicongpu.species.constant.ionizationcurrent import None_

        self.assertIsInstance(pypic.ionization_current, None_)
        self.assertEqual(pypic.ionization_electron_species.name, electron.name)

    def test_adk_custom_current_not_silently_dropped(self):
        from picongpu.picmi.interaction.ionization.fieldionization.ionizationcurrent import IonizationCurrent

        ion, electron = self._species()

        class UnsupportedCurrent(IonizationCurrent):
            MODEL_NAME: str = "unsupported"

        model = ADK(
            ion_species=ion,
            ionization_electron_species=electron,
            ADK_variant=0,
            ionization_current=UnsupportedCurrent(),
        )
        with pytest.raises(ValueError, match="Unsupported ionization current"):
            model.get_as_pypicongpu()

    def test_thomas_fermi_bridges_electron_species(self):
        from picongpu.picmi.interaction.ionization.electroniccollisionalequilibrium import ThomasFermi

        ion, electron = self._species()
        model = ThomasFermi(ion_species=ion, ionization_electron_species=electron)
        pypic = model.get_as_pypicongpu()
        # the C++ ThomasFermi ionizer is parameterised by the electron species
        self.assertEqual(pypic.ionization_electron_species.name, electron.name)
        self.assertEqual(pypic.ionizer_picongpu_name, "ThomasFermi")

    def test_thomas_fermi_rejects_ionization_current(self):
        # the C++ ThomasFermi (byCollision) takes no ionization current template
        # argument, so the pypicongpu model must not accept one
        from picongpu.pypicongpu.species.constant.ionizationcurrent import None_
        from picongpu.pypicongpu.species.constant.ionizationmodel import ThomasFermi as PypicongpuThomasFermi
        from pydantic import ValidationError

        ion, electron = self._species()
        with pytest.raises(ValidationError):
            PypicongpuThomasFermi(
                ionization_electron_species=electron.get_as_pypicongpu(),
                ionization_current=None_(),
            )
