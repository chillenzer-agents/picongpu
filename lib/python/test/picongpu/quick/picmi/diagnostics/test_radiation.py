"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

import tempfile
from functools import partial
from pathlib import Path
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


def make_filtered_species():
    return FilteredSpecies(
        species=make_species(),
        functor=ParticleFilter(name="rangeFilter", functor=partial(range_filter, lo=0, hi=8)),
    )


def make_sim(diagnostics=()):
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
    for diagnostic in diagnostics:
        sim.add_diagnostic(diagnostic)
    return sim


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
        filtered_species = make_filtered_species()
        radiation = Radiation(species=filtered_species, period=TimeStepSpec[:], observer=make_observer())
        assert radiation.species == [filtered_species]

    def test_accepts_list_of_species_and_filtered_species(self):
        species = make_species()
        filtered_species = make_filtered_species()
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


class TestRadiationRequirements(TestCase):
    """MomentumPrev1 is required for every species, RadiationMask only for plain species with a gamma filter."""

    def test_momentum_prev_1_registered_for_plain_species(self):
        species = make_species()
        Radiation(species=species, period=TimeStepSpec[:], observer=make_observer())
        assert has_requirement(species, MomentumPrev1)

    def test_momentum_prev_1_registered_for_filtered_species(self):
        filtered_species = make_filtered_species()
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
        filtered_species = make_filtered_species()
        Radiation(
            species=filtered_species, period=TimeStepSpec[:], observer=make_observer(), gamma_filter_threshold=10.0
        )
        assert not has_requirement(filtered_species.species, RadiationMask)


class TestRadiationTranslation(TestCase):
    def test_get_as_pypicongpu_translates_plain_species(self):
        species = make_species()
        radiation = Radiation(species=species, period=TimeStepSpec[2:4:2], observer=make_observer())
        plugin = radiation.get_as_pypicongpu(time_step_size=1e-15, num_steps=4)
        assert [type(entry) for entry in plugin.species] == [PyPIConGPUSpecies]
        assert plugin.species[0].name == "electron"

    def test_get_as_pypicongpu_translates_filtered_species_in_filter_mode(self):
        filtered_species = make_filtered_species()
        radiation = Radiation(species=filtered_species, period=TimeStepSpec[2:4:2], observer=make_observer())
        plugin = radiation.get_as_pypicongpu(time_step_size=1e-15, num_steps=4)
        assert [type(entry) for entry in plugin.species] == [PyPIConGPUFilteredSpecies]
        assert plugin.species[0].species_name == "electron"
        assert plugin.species[0].filter_name == "rangeFilter"
        assert isinstance(plugin.species[0].functor, PyPIConGPUParticleFunctor)

    def test_collect_particle_filters_picks_up_radiation_filter(self):
        sim = make_sim(
            [Radiation(species=make_filtered_species(), period=TimeStepSpec[2:4:2], observer=make_observer())]
        )
        assert [functor.name for functor in sim._collect_particle_filters()] == ["rangeFilter"]

    def test_collect_particle_filters_empty_for_unfiltered_radiation(self):
        sim = make_sim([Radiation(species=make_species(), period=TimeStepSpec[2:4:2], observer=make_observer())])
        assert sim._collect_particle_filters() == []


class TestRadiationRendering(TestCase):
    """The generic particleFilters.param template must pick up radiation filters; N.cfg must not gain a .filter option."""

    def _render(self, diagnostics):
        sim = make_sim(diagnostics)
        with tempfile.TemporaryDirectory() as parent:
            # the runner requires the setup directory to not exist yet
            setup_dir = Path(parent) / "setup"
            sim.write_input_file(setup_dir)
            particle_filters = (setup_dir / "include/picongpu/param/particleFilters.param").read_text()
            n_cfg = (setup_dir / "etc/picongpu/N.cfg").read_text()
        return particle_filters, n_cfg

    def test_generated_setup_renders_radiation_filter_into_particle_filters_param(self):
        particle_filters, _ = self._render(
            [Radiation(species=make_filtered_species(), period=TimeStepSpec[2:4:2], observer=make_observer())]
        )
        assert 'static constexpr char const* name = "rangeFilter";' in particle_filters
        assert "using rangeFilter =" in particle_filters
        assert "using AllParticleFilters = MakeSeq_t<" in particle_filters
        assert "rangeFilter," in particle_filters

    def test_generated_setup_renders_unfiltered_radiation_without_particle_filters(self):
        particle_filters, _ = self._render(
            [Radiation(species=make_species(), period=TimeStepSpec[2:4:2], observer=make_observer())]
        )
        assert "struct" not in particle_filters
        # no filter is registered, so AllParticleFilters must only contain `All`
        block = particle_filters[particle_filters.index("using AllParticleFilters") :]
        block = block[: block.index(">;")]
        assert block.split() == ["using", "AllParticleFilters", "=", "MakeSeq_t<", "All"]

    def test_generated_setup_does_not_emit_radiation_filter_option(self):
        # The C++ radiation plugin does not have a .filter option yet (follow-up task),
        # so the generated N.cfg must not reference one.
        _, n_cfg = self._render(
            [Radiation(species=make_filtered_species(), period=TimeStepSpec[2:4:2], observer=make_observer())]
        )
        assert "_radiation.filter" not in n_cfg
