"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

import tempfile
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase

import pytest
from pydantic import ValidationError

from picongpu import picmi
from picongpu.picmi import FilteredSpecies, ParticleFilter
from picongpu.picmi.diagnostics import Radiation, TimeStepSpec
from picongpu.pypicongpu.output.radiation import RadiationObserverConfiguration
from picongpu.pypicongpu.particle_functor import (
    FilteredSpecies as PyPIConGPUFilteredSpecies,
    ParticleFunctor as PyPIConGPUParticleFunctor,
)
from picongpu.pypicongpu.species.attribute.momentum_prev_1 import MomentumPrev1
from picongpu.pypicongpu.species.attribute.radiation_mask import RadiationMask
from picongpu.pypicongpu.species.species import Species as PyPIConGPUSpecies
from sympy import And


def make_observer():
    return RadiationObserverConfiguration(N_observer=16, index_to_direction=lambda _: [1, 0, 0])


def range_filter(particle, lo, hi):
    position = particle.get("position", origin="total", unit="cell")
    return And(position[0] >= lo, position[0] < hi)


def make_species(name="electron"):
    return picmi.Species(name=name, particle_type=name)


def make_filter():
    return ParticleFilter(name="rangeFilter", functor=partial(range_filter, lo=0, hi=8))


def make_filtered_species(species):
    return FilteredSpecies(species=species, functor=make_filter())


def make_sim():
    grid = picmi.Cartesian3DGrid(
        number_of_cells=[16, 16, 16],
        lower_bound=[0, 0, 0],
        upper_bound=[1.0, 1.0, 1.0],
        lower_boundary_conditions=["open", "open", "periodic"],
        upper_boundary_conditions=["open", "open", "periodic"],
    )
    solver = picmi.ElectromagneticSolver(method="Yee", grid=grid)
    sim = picmi.Simulation(time_step_size=1e-15, max_steps=4, solver=solver)
    electrons = make_species()
    electrons.initial_distribution = picmi.UniformDistribution(density=1.0)
    sim.add_species(electrons, picmi.PseudoRandomLayout(n_macroparticles_per_cell=2))
    return sim, electrons


def has_requirement(species, requirement):
    return any(isinstance(requirement_of_species, requirement) for requirement_of_species in species._requirements)


class TestRadiationSpecies(TestCase):
    """Radiation must accept Species, FilteredSpecies, and lists thereof."""

    def test_accepts_plain_species(self):
        species = make_species()
        radiation = Radiation(species=species, period=TimeStepSpec[:], observer=make_observer())
        # a single species is wrapped into a list
        assert radiation.species == [species]

    def test_accepts_filtered_species(self):
        filtered_species = make_filtered_species(make_species())
        radiation = Radiation(species=filtered_species, period=TimeStepSpec[:], observer=make_observer())
        assert radiation.species == [filtered_species]

    def test_accepts_list_of_species_and_filtered_species(self):
        species = make_species()
        filtered_species = make_filtered_species(make_species())
        other_species = make_species("proton")
        radiation = Radiation(
            species=[species, filtered_species, other_species], period=TimeStepSpec[:], observer=make_observer()
        )
        assert radiation.species == [species, filtered_species, other_species]

    def test_rejects_wrong_type(self):
        for wrong_type in (42, "electron", [42], ["electron"]):
            with self.subTest(wrong_type=wrong_type):
                with pytest.raises(ValidationError):
                    Radiation(species=wrong_type, period=TimeStepSpec[:], observer=make_observer())

    def test_rejects_scalar_species_with_actionable_message(self):
        # a bare species name is a likely mistake; the error must point at the
        # real fix (passing a Species/FilteredSpecies object), not "wrap in list"
        with pytest.raises(ValidationError, match="Species or FilteredSpecies"):
            Radiation(species="electron", period=TimeStepSpec[:], observer=make_observer())

    def test_rejects_gamma_filter_threshold_without_plain_species(self):
        # the C++ gamma filter only acts on species carrying the radiationMask
        # attribute, which is never registered for filtered species; with no
        # plain species the threshold would be silently ignored
        with pytest.raises(ValidationError, match="gamma_filter_threshold has no effect"):
            Radiation(
                species=[
                    make_filtered_species(make_species()),
                    make_filtered_species(make_species("proton")),
                ],
                period=TimeStepSpec[:],
                observer=make_observer(),
                gamma_filter_threshold=10.0,
            )


class TestRadiationRequirements(TestCase):
    """MomentumPrev1 is required for every species, RadiationMask only for plain species with a gamma filter."""

    def test_momentum_prev_1_registered_for_plain_species(self):
        species = make_species()
        Radiation(species=species, period=TimeStepSpec[:], observer=make_observer())
        assert has_requirement(species, MomentumPrev1)

    def test_momentum_prev_1_registered_for_filtered_species(self):
        filtered_species = make_filtered_species(make_species())
        Radiation(species=filtered_species, period=TimeStepSpec[:], observer=make_observer())
        assert has_requirement(filtered_species.species, MomentumPrev1)

    def test_radiation_mask_registered_for_plain_species_with_gamma_filter(self):
        species = make_species()
        Radiation(species=species, period=TimeStepSpec[:], observer=make_observer(), gamma_filter_threshold=10.0)
        assert has_requirement(species, RadiationMask)

    def test_radiation_mask_not_registered_for_plain_species_without_gamma_filter(self):
        species = make_species()
        Radiation(species=species, period=TimeStepSpec[:], observer=make_observer())
        assert not has_requirement(species, RadiationMask)

    def test_radiation_mask_never_registered_for_filtered_species(self):
        # only observable in the mixed case: an all-filtered list with a gamma
        # filter is rejected, and there the threshold would be a silent no-op
        species = make_species()
        filtered_species = make_filtered_species(make_species("proton"))
        with pytest.warns(UserWarning, match="gamma_filter_threshold applies only to plain species"):
            Radiation(
                species=[species, filtered_species],
                period=TimeStepSpec[:],
                observer=make_observer(),
                gamma_filter_threshold=10.0,
            )
        assert has_requirement(species, RadiationMask)
        assert not has_requirement(filtered_species.species, RadiationMask)


class TestRadiationTranslation(TestCase):
    def test_get_as_pypicongpu_translates_plain_species(self):
        species = make_species()
        radiation = Radiation(species=species, period=TimeStepSpec[2:4:2], observer=make_observer())
        plugin = radiation.get_as_pypicongpu(time_step_size=1e-15, num_steps=4)
        assert [type(entry) for entry in plugin.species] == [PyPIConGPUSpecies]
        assert plugin.species[0].name == "electron"

    def test_get_as_pypicongpu_translates_filtered_species_in_filter_mode(self):
        filtered_species = make_filtered_species(make_species())
        radiation = Radiation(species=filtered_species, period=TimeStepSpec[2:4:2], observer=make_observer())
        plugin = radiation.get_as_pypicongpu(time_step_size=1e-15, num_steps=4)
        assert [type(entry) for entry in plugin.species] == [PyPIConGPUFilteredSpecies]
        assert plugin.species[0].species_name == "electron"
        assert plugin.species[0].filter_name == "rangeFilter"
        assert isinstance(plugin.species[0].functor, PyPIConGPUParticleFunctor)

    def test_collect_particle_filters_picks_up_radiation_filter(self):
        sim, electrons = make_sim()
        sim.add_diagnostic(
            Radiation(species=make_filtered_species(electrons), period=TimeStepSpec[2:4:2], observer=make_observer())
        )
        assert [functor.name for functor in sim._collect_particle_filters()] == ["rangeFilter"]

    def test_collect_particle_filters_empty_for_unfiltered_radiation(self):
        sim, electrons = make_sim()
        sim.add_diagnostic(Radiation(species=electrons, period=TimeStepSpec[2:4:2], observer=make_observer()))
        assert sim._collect_particle_filters() == []


class TestRadiationRendering(TestCase):
    """
    The rendering tests use the realistic wiring: the (filtered) species the
    radiation diagnostic refers to is the species object added to the
    simulation, so the rendered setup is one the C++ radiation plugin can be
    enabled for (it requires momentumPrev1 on the rendered species).
    """

    def _render(self, *, filtered=False, **radiation_kwargs):
        sim, electrons = make_sim()
        species = make_filtered_species(electrons) if filtered else electrons
        sim.add_diagnostic(
            Radiation(species=species, period=TimeStepSpec[2:4:2], observer=make_observer(), **radiation_kwargs)
        )
        with tempfile.TemporaryDirectory() as parent:
            # the runner requires the setup directory to not exist yet
            setup_dir = Path(parent) / "setup"
            sim.write_input_file(setup_dir)
            return SimpleNamespace(
                particle_filters=(setup_dir / "include/picongpu/param/particleFilters.param").read_text(),
                n_cfg=(setup_dir / "etc/picongpu/N.cfg").read_text(),
                species_definition=(setup_dir / "include/picongpu/param/speciesDefinition.param").read_text(),
                radiation_param=(setup_dir / "include/picongpu/param/radiation.param").read_text(),
            )

    def test_generated_setup_renders_radiation_filter_into_particle_filters_param(self):
        rendered = self._render(filtered=True)
        assert 'static constexpr char const* name = "rangeFilter";' in rendered.particle_filters
        assert "using rangeFilter =" in rendered.particle_filters
        assert "using AllParticleFilters = MakeSeq_t<" in rendered.particle_filters
        assert "rangeFilter," in rendered.particle_filters
        # the wrapped species is the one added to the simulation, so the
        # requirement registered by the diagnostic must be rendered
        assert "momentumPrev1" in rendered.species_definition
        assert "radiationMask" not in rendered.species_definition

    def test_generated_setup_renders_unfiltered_radiation_without_particle_filters(self):
        rendered = self._render()
        assert "struct" not in rendered.particle_filters
        # no filter is registered, so AllParticleFilters must only contain `All`
        block = rendered.particle_filters[rendered.particle_filters.index("using AllParticleFilters") :]
        block = block[: block.index(">;")]
        assert block.split() == ["using", "AllParticleFilters", "=", "MakeSeq_t<", "All"]
        assert "momentumPrev1" in rendered.species_definition
        assert "radiationMask" not in rendered.species_definition

    def test_generated_setup_renders_gamma_filter_for_plain_species(self):
        rendered = self._render(gamma_filter_threshold=5.0)
        assert "momentumPrev1" in rendered.species_definition
        assert "radiationMask" in rendered.species_definition
        assert "static constexpr float_X radiationGamma = 5.0;" in rendered.radiation_param
        # a plain species uses the prefix the C++ plugin actually registers
        assert "--electron_radiation.period" in rendered.n_cfg

    def test_n_cfg_radiation_block_is_known_wrong_until_task_15(self):
        # KNOWN BROKEN STATE, deferred to task 15: the radiation block of
        # N.cfg.mustache iterates {{#species}} and uses {{{name}}}, which for a
        # FilteredSpecies is "<species>_<filter>". The whole block is therefore
        # emitted under a CLI prefix no C++ plugin registers, and it carries no
        # .filter line (the C++ option does not exist yet). Task 15 must flip
        # this block to --electron_radiation.* plus
        # --electron_radiation.filter rangeFilter.
        rendered = self._render(filtered=True)
        for option in (
            "period",
            "dump",
            "start",
            "end",
            "numJobs",
            "openPMDSuffix",
            "openPMDCheckpointExtension",
            "openPMDConfig",
            "openPMDCheckpointConfig",
        ):
            with self.subTest(option=option):
                assert f"--electron_rangeFilter_radiation.{option}" in rendered.n_cfg
        # the prefix the C++ plugin actually registers is absent
        assert "--electron_radiation." not in rendered.n_cfg
        # the C++ radiation plugin has no .filter option until task 15
        assert "_radiation.filter" not in rendered.n_cfg
