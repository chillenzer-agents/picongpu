"""
This file is part of PIConGPU.
Copyright 2021-2024 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre
License: GPLv3+
"""

from unittest import TestCase

import os
import tempfile

import pytest
from picongpu import picmi
from picongpu.picmi.grid import Cartesian3DGrid
from picongpu.picmi.species import Species
from picongpu.picmi.species_requirements import SimpleMomentumOperation, run_construction
from picongpu.pypicongpu import species
from picongpu.pypicongpu.species.operation.densityprofile import Uniform
from picongpu.pypicongpu.util import UnsupportedFeatureError
from pydantic import ValidationError

ARBITRARY_GRID = Cartesian3DGrid(
    lower_bound=[0, 0, 0],
    upper_bound=[1, 1, 1],
    number_of_cells=[1, 1, 1],
    lower_boundary_conditions=["periodic", "periodic", "periodic"],
    upper_boundary_conditions=["periodic", "periodic", "periodic"],
)

# the exact bytes rendered for a simulation whose only density profile is an
# unbounded (default) UniformDistribution; byte-identical to the pre-change
# rendering on `dev` (captured 2026-09-07). Any change to the unconditional
# render path for the uniform profile breaks this pin.
UNBOUNDED_UNIFORM_DENSITY_PARAM = "\n".join(
    [
        "/* Copyright 2013-2025 Axel Huebl, Heiko Burau, Rene Widera, Felix Schmitt,",
        " *                     Richard Pausch, Marco Garten, Brian Marre, Kristin Tippey",
        " *                     Hannes Troepgen, Masoud Afshari, Julian Lenz",
        " *",
        " * This file is part of PIConGPU.",
        " *",
        " * PIConGPU is free software: you can redistribute it and/or modify",
        " * it under the terms of the GNU General Public License as published by",
        " * the Free Software Foundation, either version 3 of the License, or",
        " * (at your option) any later version.",
        " *",
        " * PIConGPU is distributed in the hope that it will be useful,",
        " * but WITHOUT ANY WARRANTY; without even the implied warranty of",
        " * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the",
        " * GNU General Public License for more details.",
        " *",
        " * You should have received a copy of the GNU General Public License",
        " * along with PIConGPU.",
        " * If not, see <http://www.gnu.org/licenses/>.",
        " */",
        "",
        " #pragma once",
        "",
        '#include "picongpu/particles/densityProfiles/profiles.def"',
        '#include "picongpu/particles/traits/GetDensityRatio.hpp"',
        "",
        "namespace picongpu",
        "{",
        "    namespace densityProfiles::pypicongpu",
        "    {",
        "        ",
        "        // a species has always only exactly one profile, so only one of the following blocks below will be present",
        "",
        "",
        '            /** generate the initial macroparticle position for species "electron" (species_electron)',
        "             *",
        "             * @note the density may be further modified from this profile by the densityRatio of the species set in the",
        "             *  init-pipeline.",
        "             */",
        "            struct init_species_electron_functor",
        "            {",
        '                /** generate the initial macroparticle position for species "electron" (species_electron)',
        "                 *",
        "                 * @note the density may be further modified from this profile by the densityRatio of the species, set in",
        "                 *  the init-pipeline.",
        "                 */",
        "                HDINLINE float_X operator()(const floatD_64& position_SI, const float3_64& cellSize_SI)",
        "                {",
        "                    //! @todo respect bounding box, Brian Marre, 2023",
        "                    return static_cast<float_X>(42.420000000000002 / SI::BASE_DENSITY_SI);",
        "                }",
        "            };",
        "            using init_species_electron = FreeFormulaImpl<init_species_electron_functor>;",
        "",
        "",
        "",
        "",
        "",
        "    } // namespace densityProfiles::pypicongpu",
        "} // namespace picongpu",
    ]
)


class HelperTestPicmiBoundaries:
    """
    provides test functions to check proper handling of boundaries

    expects a method self._get_distribution(lower_bound, upper_bound), which
    creates a distribution w/ lower & upper bound passed straight through.
    """

    def __init__(self):
        if type(self) is HelperTestPicmiBoundaries:
            raise RuntimeError("This class is abstract, inherit from it!")

    def _get_distribution(self, lower_bound, upper_bound):
        """
        helper to check against

        Must create the distribution to test with arbitrary params;
        must pass lower_bound and upper_bound straight through.

        :param lower_bound: any, passed through to PICMI
        :param upper_bound: any, passed through to PICMI
        :return: PICMI distribution
        """
        raise NotImplementedError("must be implemented in child classes")


class TestPicmiUniformDistribution(TestCase, HelperTestPicmiBoundaries):
    def _get_distribution(self, lower_bound, upper_bound):
        return picmi.UniformDistribution(density=1716273, lower_bound=lower_bound, upper_bound=upper_bound)

    def test_full(self):
        """full paramset"""
        uniform = picmi.UniformDistribution(density=42.42)
        pypic = uniform.get_as_pypicongpu(ARBITRARY_GRID)
        assert isinstance(pypic, species.operation.densityprofile.Uniform)

        assert pypic.density_si == 42.42

    def test_lower_upper_bound_fill_in(self):
        """construction accepts sub-volume bounds + fill_in and carries them to pypicongpu"""
        uniform = picmi.UniformDistribution(
            density=42.42,
            lower_bound=[1.0, 2.0, None],
            upper_bound=[3.0, None, 5.0],
            fill_in=True,
        )
        pypic = uniform.get_as_pypicongpu(ARBITRARY_GRID)
        assert pypic.lower_bound == {"x": {"value": 1.0}, "y": {"value": 2.0}, "z": {"value": None}}
        assert pypic.upper_bound == {"x": {"value": 3.0}, "y": {"value": None}, "z": {"value": 5.0}}
        assert pypic.fill_in is True

    def test_lower_upper_bound_fill_in_rendering_context(self):
        """sub-volume bounds + fill_in appear in the rendering context"""
        uniform = picmi.UniformDistribution(
            density=42.42,
            lower_bound=[1.0, None, None],
            upper_bound=[None, 2.0, None],
            fill_in=True,
        )
        pypic = uniform.get_as_pypicongpu(ARBITRARY_GRID)
        context = pypic.model_dump(mode="json")
        assert context["lower_bound"] == {"x": {"value": 1.0}, "y": {"value": None}, "z": {"value": None}}
        assert context["upper_bound"] == {"x": {"value": None}, "y": {"value": 2.0}, "z": {"value": None}}
        assert context["fill_in"] is True

    def test_lower_upper_bound_fill_in_default_unbounded(self):
        """bound/fill_in defaults map to an unbounded profile (no warnings, no errors)"""
        uniform = picmi.UniformDistribution(density=42.42)
        pypic = uniform.get_as_pypicongpu(ARBITRARY_GRID)
        assert pypic.lower_bound is None
        assert pypic.upper_bound is None
        assert pypic.fill_in is None

    def test_rendered_uniform_sub_volume(self):
        """the requested sub-volume is rendered into the generated species
        definition (omitted when unbounded)"""
        unbound_rendered = self._write_sim(picmi.UniformDistribution(density=42.42))
        bound_rendered = self._write_sim(
            picmi.UniformDistribution(
                density=42.42,
                lower_bound=[1.0, None, None],
                upper_bound=[None, 2.0, 3.0],
                fill_in=True,
            )
        )

        # unbounded: byte-identical to the pre-change ("dev") rendering
        assert unbound_rendered == UNBOUNDED_UNIFORM_DENSITY_PARAM + "\n"
        # ... and consequently no sub-volume is requested
        assert "requested lower bound of the sub-volume" not in unbound_rendered
        assert "requested upper bound of the sub-volume" not in unbound_rendered
        assert "requested to refill the sub-volume" not in unbound_rendered

        # bounded: the requested sub-volume is rendered into the density profile
        assert "requested lower bound of the sub-volume" in bound_rendered
        assert "lower_bound = (1.0, None, None)" in bound_rendered
        assert "requested upper bound of the sub-volume" in bound_rendered
        assert "upper_bound = (None, 2.0, 3.0)" in bound_rendered
        assert "requested to refill the sub-volume" in bound_rendered
        # ... plus the honesty marker (Python-side only, not C++ runtime)
        honesty = "not yet honoured by the C++ homogeneous profile"
        assert honesty in bound_rendered
        assert honesty not in unbound_rendered

    def test_rendered_fill_in_false_omits_comment(self):
        """fill_in=False renders nothing for the moving-window refill"""
        rendered = self._write_sim(
            picmi.UniformDistribution(
                density=42.42,
                lower_bound=[1, 2, 3],
                upper_bound=[4, 5, 6],
                fill_in=False,
            )
        )
        assert "requested to refill the sub-volume" not in rendered
        assert "requested lower bound of the sub-volume" in rendered

    def _write_sim(self, distribution) -> str:
        """render a minimal simulation with the given distribution and return the density.param content"""
        grid = Cartesian3DGrid(
            lower_bound=[0, 0, 0],
            upper_bound=[16, 16, 16],
            number_of_cells=[16, 16, 16],
            lower_boundary_conditions=["periodic", "periodic", "periodic"],
            upper_boundary_conditions=["periodic", "periodic", "periodic"],
        )
        solver = picmi.ElectromagneticSolver(method="Yee", grid=grid)
        sim = picmi.Simulation(time_step_size=0.1, max_steps=1, solver=solver)
        sim.add_species(
            Species(name="electron", mass=1, initial_distribution=distribution),
            picmi.PseudoRandomLayout(n_macroparticles_per_cell=1),
        )
        out_dir = os.path.join(tempfile.mkdtemp(), "out")
        sim.write_input_file(out_dir)
        with open(os.path.join(out_dir, "include", "picongpu", "param", "density.param")) as rendered_file:
            return rendered_file.read()

    def test_density_zero(self):
        """density set to zero is not accepted"""
        uniform = picmi.UniformDistribution(density=0)
        with pytest.raises(ValidationError):
            uniform.get_as_pypicongpu(ARBITRARY_GRID)

    def test_mandatory(self):
        """check that mandatory must be given"""
        # type of exception is not checked
        with pytest.raises(Exception):
            picmi.UniformDistribution().get_as_pypicongpu(ARBITRARY_GRID)

        # density is only required param
        picmi.UniformDistribution(density=3.14).get_as_pypicongpu(ARBITRARY_GRID)

    def test_drift(self):
        """drift is correctly translated"""
        # no drift
        uniform = picmi.UniformDistribution(density=1, directed_velocity=[0, 0, 0])
        drift = uniform.get_picongpu_drift()
        assert drift is None

        # some drift
        # uses velocity
        uniform = picmi.UniformDistribution(density=1, directed_velocity=[278487224.0, 103784563.0, 1283345.0])
        drift = uniform.get_picongpu_drift()
        assert drift is not None
        assert abs(drift.gamma - 7.6208808298928865) < 1e-10
        assert abs(drift.direction_normalized[0] - 0.9370354841199405) < 1e-10
        assert abs(drift.direction_normalized[1] - 0.34920746753855203) < 1e-10
        assert abs(drift.direction_normalized[2] - 0.004318114799291135) < 1e-10


class TestPypicongpuUniformBoundValidation(TestCase):
    """validation of the pypicongpu Uniform sub-volume bounds"""

    def test_bound_dict_passthrough(self):
        """a well-formed dict bound is accepted unchanged"""
        uniform = Uniform(
            density_si=1.0,
            lower_bound={
                "x": {"value": 1.0},
                "y": {"value": None},
                "z": {"value": 2.0},
            },
        )
        assert uniform.lower_bound == {
            "x": {"value": 1.0},
            "y": {"value": None},
            "z": {"value": 2.0},
        }

    def test_bound_dict_roundtrip(self):
        """the dict form round-trips through json serialization"""
        uniform = Uniform(
            density_si=1.0,
            lower_bound={
                "x": {"value": 1.0},
                "y": {"value": None},
                "z": {"value": 2.0},
            },
        )
        json_roundtrip = Uniform.model_validate(uniform.model_dump(mode="json"))
        assert json_roundtrip.lower_bound == uniform.lower_bound

    def test_bound_dict_unknown_axis_rejected(self):
        """a bound with an unknown axis key is rejected"""
        with pytest.raises(ValueError, match="unknown axis"):
            Uniform(density_si=1.0, lower_bound={"a": {"value": 1.0}})

    def test_bound_dict_missing_axis_rejected(self):
        """a bound missing one of x/y/z is rejected"""
        with pytest.raises(ValueError, match="missing axis"):
            Uniform(density_si=1.0, lower_bound={"x": {"value": 1.0}})

    def test_bound_dict_malformed_axis_value_rejected(self):
        """an axis value that is not a {"value": ...} mapping is rejected"""
        with pytest.raises(ValueError, match="malformed"):
            Uniform(
                density_si=1.0,
                lower_bound={
                    "x": 1.0,
                    "y": {"value": 2.0},
                    "z": {"value": 3.0},
                },
            )

    def test_bound_too_few_components_rejected(self):
        """a 2-component bound is rejected"""
        with pytest.raises(ValueError, match="exactly 3 components"):
            Uniform(density_si=1.0, lower_bound=[1.0, 2.0])

    def test_bound_too_many_components_rejected(self):
        """a 4-component bound is rejected"""
        with pytest.raises(ValueError, match="exactly 3 components"):
            Uniform(density_si=1.0, lower_bound=[1.0, 2.0, 3.0, 4.0])

    def test_picmi_malformed_bound_rejected(self):
        """a malformed bound passed through the picmi layer is rejected"""
        uniform = picmi.UniformDistribution(density=1.0, lower_bound=[1.0, 2.0])
        with pytest.raises(ValueError, match="exactly 3 components"):
            uniform.get_as_pypicongpu(ARBITRARY_GRID)


class TestPicmiFoilDistribution(TestCase, HelperTestPicmiBoundaries):
    def _get_distribution(self, lower_bound, upper_bound):
        return picmi.FoilDistribution(
            density=1716273,
            front=1.0,
            thicknes=2.0,
            exponential_pre_plasma_length=3.0,
            exponential_pre_plasma_cutoff=4.0,
            exponential_post_plasma_length=5.0,
            exponential_post_plasma_cutoff=6.0,
            lower_bound=lower_bound,
            upper_bound=upper_bound,
        )

    def test_full(self):
        """full paramset"""
        foil = picmi.FoilDistribution(
            density=42.42,
            front=1.0,
            thickness=2.0,
            exponential_pre_plasma_length=3.0,
            exponential_pre_plasma_cutoff=4.0,
            exponential_post_plasma_length=5.0,
            exponential_post_plasma_cutoff=6.0,
        )

        pypic = foil.get_as_pypicongpu(ARBITRARY_GRID)
        assert isinstance(pypic, species.operation.densityprofile.Foil)

        assert pypic.density_si == 42.42
        assert pypic.y_value_front_foil_si == 1.0
        assert pypic.thickness_foil_si == 2.0
        assert pypic.pre_foil_plasmaRamp.PlasmaLength == 3.0
        assert pypic.pre_foil_plasmaRamp.PlasmaCutoff == 4.0
        assert pypic.post_foil_plasmaRamp.PlasmaLength == 5.0
        assert pypic.post_foil_plasmaRamp.PlasmaCutoff == 6.0

    def test_lower_upper_bound_not_supported(self):
        """the foil profile has no bound support, so setting bounds must raise"""
        foil = picmi.FoilDistribution(
            density=42.42,
            front=1.0,
            thickness=2.0,
            lower_bound=[111, 222, 333],
            upper_bound=[444, 555, 666],
        )
        with pytest.raises(UnsupportedFeatureError, match="lower bound"):
            foil.get_as_pypicongpu(ARBITRARY_GRID)

    def _get_test_foils(self, cutoff, length):
        """
        helper function generating preRamp only, postRamp only
        and (pre+post ramp foil) with given cutoffs and lengths
        """
        foil_pre = picmi.FoilDistribution(
            density=1.0,
            thickness=2.0,
            front=3.0,
            exponential_pre_plasma_cutoff=cutoff,
            exponential_pre_plasma_length=length,
            exponential_post_plasma_cutoff=None,
            exponential_post_plasma_length=None,
        )

        foil_post = picmi.FoilDistribution(
            density=1.0,
            thickness=2.0,
            front=3.0,
            exponential_pre_plasma_cutoff=None,
            exponential_pre_plasma_length=None,
            exponential_post_plasma_cutoff=cutoff,
            exponential_post_plasma_length=length,
        )

        foil_both = picmi.FoilDistribution(
            density=1.0,
            thickness=2.0,
            front=3.0,
            exponential_pre_plasma_cutoff=cutoff,
            exponential_pre_plasma_length=length,
            exponential_post_plasma_cutoff=cutoff,
            exponential_post_plasma_length=length,
        )

        testFoils = [foil_pre, foil_post, foil_both]
        return testFoils

    def test_cutoff_zero(self):
        """cutoff set to zero is accepted"""
        testCases = self._get_test_foils(0, 1.0)

        for entry in testCases:
            pypic = entry.get_as_pypicongpu(ARBITRARY_GRID)
            # no error:
            assert pypic.density_si == 1.0
            assert pypic.thickness_foil_si == 2.0
            assert pypic.y_value_front_foil_si == 3.0

    def test_setting_noPlasmaRamps(self):
        testCases = self._get_test_foils(None, 1.0)

        for entry in testCases:
            with pytest.raises(
                ValueError,
                match="either both exponential_(pre|post)_plasma_"
                "length and exponential_(pre|post)_plasma_cutoff must be"
                " set to none or neither!",
            ):
                entry.get_as_pypicongpu(ARBITRARY_GRID)

        testCases = self._get_test_foils(1.0, None)
        for entry in testCases:
            with pytest.raises(
                ValueError,
                match="either both exponential_(pre|post)_plasma_"
                "length and exponential_(pre|post)_plasma_cutoff must be"
                " set to none or neither!",
            ):
                entry.get_as_pypicongpu(ARBITRARY_GRID)

    def test_mandatory(self):
        """check that mandatory must be given"""
        # type of exception is not checked
        with pytest.raises(Exception):
            picmi.FoilDistribution()

        # density, thickness and front are only required param
        picmi.FoilDistribution(density=3.14, thickness=1.0, front=3.0).get_as_pypicongpu(ARBITRARY_GRID)

    def test_drift(self):
        """drift is correctly translated"""
        # no drift
        foil = picmi.FoilDistribution(density=1.0, front=2.0, thickness=3.0, directed_velocity=[0, 0, 0])
        drift = foil.get_picongpu_drift()
        assert drift is None

        # some drift
        # uses velocity
        foil = picmi.FoilDistribution(
            density=1,
            front=2.0,
            thickness=3.0,
            directed_velocity=[278487224.0, 103784563.0, 1283345.0],
        )
        drift = foil.get_picongpu_drift()
        assert drift is not None
        assert abs(drift.gamma - 7.6208808298928865) < 1e-10
        assert abs(drift.direction_normalized[0] - 0.9370354841199405) < 1e-10
        assert abs(drift.direction_normalized[1] - 0.34920746753855203) < 1e-10
        assert abs(drift.direction_normalized[2] - 0.004318114799291135) < 1e-10


class TestPicmiGaussianDistribution(TestCase, HelperTestPicmiBoundaries):
    values = {
        "density": 42.42,
        "center_front": 1.0,
        "center_rear": 2.0,
        "sigma_front": 3.0,
        "sigma_rear": 4.0,
        "power": 5.0,
        "factor": -6.0,
        "vacuum_front": 50,
    }

    def _get_distribution(self, lower_bound=[None, None, None], upper_bound=[None, None, None], **kwargs):
        return picmi.GaussianDistribution(
            **dict(
                density=self.values["density"],
                center_front=self.values["center_front"],
                center_rear=self.values["center_rear"],
                sigma_front=self.values["sigma_front"],
                sigma_rear=self.values["sigma_rear"],
                power=self.values["power"],
                factor=self.values["factor"],
                vacuum_front=self.values["vacuum_front"],
                lower_bound=lower_bound,
                upper_bound=upper_bound,
            )
            | kwargs
        )

    def test_full(self):
        """full paramset"""
        gaussian = self._get_distribution()

        pypic = gaussian.get_as_pypicongpu(ARBITRARY_GRID)
        assert isinstance(pypic, species.operation.densityprofile.Gaussian)

        assert pypic.density == self.values["density"]
        assert pypic.gas_center_front == self.values["center_front"]
        assert pypic.gas_center_rear == self.values["center_rear"]
        assert pypic.gas_sigma_front == self.values["sigma_front"]
        assert pypic.gas_sigma_rear == self.values["sigma_rear"]
        assert pypic.gas_power == self.values["power"]
        assert pypic.gas_factor == self.values["factor"]
        assert pypic.vacuum_cells_front == self.values["vacuum_front"]

        # @todo repect bounding boxes, Brian Marre, 2024

    def test_density_zero(self):
        """density set to zero is not accepted"""
        gaussian = self._get_distribution(density=0.0)
        with pytest.raises(ValueError, match=".*density must be > 0.*"):
            gaussian.get_as_pypicongpu(ARBITRARY_GRID)

    def test_front_rear_swapped(self):
        """front and rear swapped is not accepted"""
        gaussian = self._get_distribution(
            center_front=self.values["center_rear"], center_rear=self.values["center_front"]
        )
        with pytest.raises(ValueError, match=".*center_front must be <= center_rear.*"):
            gaussian.get_as_pypicongpu(ARBITRARY_GRID)

    def test_sigma_zero(self):
        """sigma == 0 is not accepted"""
        gaussian = self._get_distribution(sigma_front=0.0)
        with pytest.raises(ValidationError):
            gaussian.get_as_pypicongpu(ARBITRARY_GRID).get_rendering_context()

        gaussian = self._get_distribution(sigma_rear=0.0)
        with pytest.raises(ValidationError):
            gaussian.get_as_pypicongpu(ARBITRARY_GRID).get_rendering_context()

    def test_drift(self):
        """drift is correctly translated"""
        # no drift
        gaussian = self._get_distribution(directed_velocity=[0, 0, 0])
        drift = gaussian.get_picongpu_drift()
        assert drift is None

        # some drift
        # uses velocity
        gaussian = self._get_distribution(directed_velocity=[278487224.0, 103784563.0, 1283345.0])

        drift = gaussian.get_picongpu_drift()
        assert drift is not None
        assert abs(drift.gamma - 7.6208808298928865) < 1e-10
        assert abs(drift.direction_normalized[0] - 0.9370354841199405) < 1e-10
        assert abs(drift.direction_normalized[1] - 0.34920746753855203) < 1e-10
        assert abs(drift.direction_normalized[2] - 0.004318114799291135) < 1e-10


class TestPicmiCylindricalDistribution(TestCase, HelperTestPicmiBoundaries):
    def _get_distribution(
        self,
        density=1.0,
        center_position=(0.0, 0.0, 0.0),
        radius=2.0,
        cylinder_axis=(0.0, 1.0, 0.0),
        exponential_pre_plasma_length=None,
        exponential_pre_plasma_cutoff=None,
    ):
        return picmi.CylindricalDistribution(
            density=density,
            center_position=center_position,
            radius=radius,
            cylinder_axis=cylinder_axis,
            exponential_pre_plasma_length=exponential_pre_plasma_length,
            exponential_pre_plasma_cutoff=exponential_pre_plasma_cutoff,
        )

    def test_full(self):
        """full paramset"""
        dist = self._get_distribution(
            density=42.42,
            center_position=(1.0, 2.0, 3.0),
            radius=4.0,
            cylinder_axis=(0.5, 0.5, 0.707),
            exponential_pre_plasma_length=0.1,
            exponential_pre_plasma_cutoff=0.2,
        )
        pypic = dist.get_as_pypicongpu(ARBITRARY_GRID)
        assert isinstance(pypic, species.operation.densityprofile.Cylinder)
        assert abs(pypic.density_si - 42.42) < 1e-10
        assert pypic.center_position_si == (1.0, 2.0, 3.0)
        assert abs(pypic.radius_si - 4.0) < 1e-10
        assert pypic.cylinder_axis == (0.5, 0.5, 0.707)

    def test_density_zero(self):
        """density set to zero is not accepted"""
        dist = self._get_distribution(density=0.0)
        with pytest.raises(ValueError, match=".*density must be > 0.*"):
            dist.get_as_pypicongpu(ARBITRARY_GRID).get_rendering_context()

    def test_radius_zero(self):
        """radius smaller sqrt(2)*preplasma_length is not axcepted"""
        dist = self._get_distribution(
            radius=0.05,
            exponential_pre_plasma_length=0.1,
            exponential_pre_plasma_cutoff=0.2,
        )
        with pytest.raises(ValueError, match=".*radius must be > sqrt(2)*"):
            dist.get_as_pypicongpu(ARBITRARY_GRID).get_rendering_context()

    def test_cutoff_zero(self):
        """cutoff set to zero is accepted"""
        dist = self._get_distribution(
            exponential_pre_plasma_length=1.0,
            exponential_pre_plasma_cutoff=0.0,
        )
        pypic = dist.get_as_pypicongpu(ARBITRARY_GRID)
        # no error
        assert abs(pypic.density_si - 1.0) < 1e-10
        assert abs(pypic.radius_si - 2.0) < 1e-10

    def test_cutoff_below_zero(self):
        """cutoff below zero is not accepted (depends on ramp checks)"""
        dist = self._get_distribution(
            exponential_pre_plasma_length=1.0,
            exponential_pre_plasma_cutoff=-0.5,
        )
        with pytest.raises(ValidationError):
            dist.get_as_pypicongpu(ARBITRARY_GRID).get_rendering_context()

    def test_length_zero(self):
        """length set to zero is not accepted"""
        dist = self._get_distribution(
            exponential_pre_plasma_length=0.0,
            exponential_pre_plasma_cutoff=1.0,
        )
        with pytest.raises(ValidationError):
            dist.get_as_pypicongpu(ARBITRARY_GRID).get_rendering_context()

    def test_length_below_zero(self):
        """length below zero is not accepted"""
        dist = self._get_distribution(
            exponential_pre_plasma_length=-1.0,
            exponential_pre_plasma_cutoff=1.0,
        )
        with pytest.raises(ValidationError):
            dist.get_as_pypicongpu(ARBITRARY_GRID).get_rendering_context()

    def test_setting_noPrePlasma(self):
        """must set either both cutoffs and length, or none"""
        # only one set
        dist = self._get_distribution(exponential_pre_plasma_length=1.0)
        with pytest.raises(
            ValueError,
            match="either both exponential_pre_plasma_length and exponential_pre_plasma_cutoff must be set.*",
        ):
            dist.get_as_pypicongpu(ARBITRARY_GRID).get_rendering_context()

        # partial other way
        dist = self._get_distribution(exponential_pre_plasma_cutoff=1.0)
        with pytest.raises(
            ValueError,
            match="either both exponential_pre_plasma_length and exponential_pre_plasma_cutoff must be set.*",
        ):
            dist.get_as_pypicongpu(ARBITRARY_GRID).get_rendering_context()

    def test_mandatory(self):
        """check that mandatory must be given"""
        with pytest.raises(Exception):
            picmi.CylindricalDistribution().get_as_pypicongpu(ARBITRARY_GRID)

        # minimal valid
        dist = self._get_distribution()
        dist.get_as_pypicongpu(ARBITRARY_GRID)


def _gaussian_distribution(rms_velocity):
    return picmi.GaussianDistribution(
        density=1.0,
        lower_bound=[0, 0, 0],
        upper_bound=[1, 1, 1],
        center_front=0.2,
        center_rear=0.8,
        sigma_front=0.01,
        sigma_rear=0.02,
        power=2.0,
        factor=-9.0,
        vacuum_front=0.0,
        vacuum_rear=0.0,
        rms_velocity=rms_velocity,
    )


def _momentum_of(rms_velocity):
    """translate the temperature of a distribution with the given rms_velocity"""
    species = Species(name="e", particle_type="electron", initial_distribution=_gaussian_distribution(rms_velocity))
    return run_construction(SimpleMomentumOperation(species)).temperature


class TestDirectionalTemperature(TestCase):
    """
    rms_velocity may be anisotropic; it is translated to a directional (per-component)
    temperature (see #5677) instead of requiring isotropic components.
    """

    def test_anisotropic_rms_velocity_accepted(self):
        distribution = _gaussian_distribution([1e5, 2e5, 3e5])
        assert distribution.rms_velocity == (1e5, 2e5, 3e5)

    def test_anisotropic_rms_velocity_gives_directional_temperature(self):
        temperature = _momentum_of([1e5, 2e5, 3e5])
        assert temperature is not None
        assert temperature.temperature_kev is None
        assert temperature.temperature_kev_directional is not None
        expected = (5.685630111285689e-05, 2.2742520445142756e-04, 5.11706710015712e-04)
        for given, want in zip(temperature.temperature_kev_directional, expected):
            assert abs(given - want) < 1e-12

    def test_isotropic_rms_velocity_gives_scalar_temperature(self):
        temperature = _momentum_of([1e5, 1e5, 1e5])
        assert temperature is not None
        assert temperature.temperature_kev_directional is None
        assert abs(temperature.temperature_kev - 5.685630111285689e-05) < 1e-12

    def test_zero_rms_velocity_gives_no_temperature(self):
        assert _momentum_of([0, 0, 0]) is None
