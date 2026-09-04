"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

import re
import tempfile
from functools import partial
from pathlib import Path
from types import SimpleNamespace

from picongpu import picmi
from picongpu.picmi import FilteredSpecies, ParticleFilter
from picongpu.picmi.diagnostics import Radiation, TimeStepSpec
from picongpu.picmi.particle_functor.rng_arg import RNGArg
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


def test_momentum_prev_1_registered_for_plain_species():
    species = make_species()
    Radiation(species=species, period=TimeStepSpec[:], observer=make_observer())
    assert has_requirement(species, MomentumPrev1)


def test_momentum_prev_1_registered_for_filtered_species():
    filtered_species = make_filtered_species(make_species())
    Radiation(species=filtered_species, period=TimeStepSpec[:], observer=make_observer())
    assert has_requirement(filtered_species.species, MomentumPrev1)


def test_radiation_mask_registered_for_filtered_species():
    # the C++ filter sets the mask from the particle filter's expression, so
    # the filtered species needs the radiationMask attribute to be written and
    # read
    filtered_species = make_filtered_species(make_species())
    Radiation(species=filtered_species, period=TimeStepSpec[:], observer=make_observer())
    assert has_requirement(filtered_species.species, RadiationMask)


def test_radiation_mask_not_registered_for_plain_species():
    # a plain species has no particle filter, so no mask functor is rendered
    # for it and every one of its particles contributes unfiltered
    species = make_species()
    Radiation(species=species, period=TimeStepSpec[:], observer=make_observer())
    assert not has_requirement(species, RadiationMask)


def test_radiation_mask_registered_only_for_filtered_species_in_mixed_list():
    species = make_species()
    filtered_species = make_filtered_species(make_species("proton"))
    Radiation(species=[species, filtered_species], period=TimeStepSpec[:], observer=make_observer())
    assert not has_requirement(species, RadiationMask)
    assert has_requirement(filtered_species.species, RadiationMask)


def test_get_as_pypicongpu_translates_plain_species():
    species = make_species()
    radiation = Radiation(species=species, period=TimeStepSpec[2:4:2], observer=make_observer())
    plugin = radiation.get_as_pypicongpu(time_step_size=1e-15, num_steps=4)
    assert [type(entry) for entry in plugin.species] == [PyPIConGPUSpecies]
    assert plugin.species[0].name == "electron"


def test_get_as_pypicongpu_translates_filtered_species_in_filter_mode():
    filtered_species = make_filtered_species(make_species())
    radiation = Radiation(species=filtered_species, period=TimeStepSpec[2:4:2], observer=make_observer())
    plugin = radiation.get_as_pypicongpu(time_step_size=1e-15, num_steps=4)
    assert [type(entry) for entry in plugin.species] == [PyPIConGPUFilteredSpecies]
    assert plugin.species[0].species_name == "electron"
    assert plugin.species[0].filter_name == "rangeFilter"
    assert isinstance(plugin.species[0].functor, PyPIConGPUParticleFunctor)


def test_collect_particle_filters_picks_up_radiation_filter():
    sim, electrons = make_sim()
    sim.add_diagnostic(
        Radiation(species=make_filtered_species(electrons), period=TimeStepSpec[2:4:2], observer=make_observer())
    )
    assert [functor.name for functor in sim._collect_particle_filters()] == ["rangeFilter"]


def test_collect_particle_filters_empty_for_unfiltered_radiation():
    sim, electrons = make_sim()
    sim.add_diagnostic(Radiation(species=electrons, period=TimeStepSpec[2:4:2], observer=make_observer()))
    assert sim._collect_particle_filters() == []


def _render(*, filtered=False):
    sim, electrons = make_sim()
    species = make_filtered_species(electrons) if filtered else electrons
    sim.add_diagnostic(Radiation(species=species, period=TimeStepSpec[2:4:2], observer=make_observer()))
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


def test_generated_setup_renders_radiation_filter_into_particle_filters_param():
    rendered = _render(filtered=True)
    assert 'static constexpr char const* name = "rangeFilter";' in rendered.particle_filters
    assert "using rangeFilter =" in rendered.particle_filters
    assert "using AllParticleFilters = MakeSeq_t<" in rendered.particle_filters
    assert "rangeFilter," in rendered.particle_filters
    # the wrapped species is the one added to the simulation, so the
    # requirements registered by the diagnostic must be rendered
    assert "momentumPrev1" in rendered.species_definition
    assert "radiationMask" in rendered.species_definition


def test_generated_setup_renders_mask_functor_for_filtered_species():
    rendered = _render(filtered=True)
    # the filter expression is inlined into a mask functor that writes the
    # radiationMask attribute
    assert "struct electron_rangeFilterMaskFunctor" in rendered.radiation_param
    assert "DataSpace< simDim > const & particleOffsetToTotalOrigin," in rendered.radiation_param
    assert "particle[picongpu::radiationMask_] = xt_cell_cell >= 0 && xt_cell_cell < 8;" in rendered.radiation_param
    # a hardcoded gamma filter is not supported (it is expressible as a
    # general particle filter instead)
    assert "struct GammaFilterFunctor" not in rendered.radiation_param
    assert "Free<GammaFilterFunctor>" not in rendered.radiation_param
    # the mask manipulator is selected per species via a template
    # specialization keyed on the species type
    assert "struct RadiationParticleFilterFor<species_electron>" in rendered.radiation_param
    assert "manipulators::unary::FreeTotalCellOffset<" in rendered.radiation_param
    assert "electron_rangeFilterMaskFunctor" in rendered.radiation_param
    assert "struct RadiationParticleFilter" in rendered.radiation_param


def test_generated_setup_renders_unfiltered_radiation_without_particle_filters():
    rendered = _render()
    assert "struct" not in rendered.particle_filters
    # no filter is registered, so AllParticleFilters must only contain `All`
    block = rendered.particle_filters[rendered.particle_filters.index("using AllParticleFilters") :]
    block = block[: block.index(">;")]
    assert block.split() == ["using", "AllParticleFilters", "=", "MakeSeq_t<", "All"]
    assert "momentumPrev1" in rendered.species_definition
    assert "radiationMask" not in rendered.species_definition
    # an unfiltered radiation species renders the generic, non-gamma filter
    # path: no mask functor, no specialization, no mask references
    assert "struct GammaFilterFunctor" not in rendered.radiation_param
    assert re.search(r"struct \w*MaskFunctor", rendered.radiation_param) is None
    assert "struct RadiationParticleFilterFor<" not in rendered.radiation_param
    assert "particle[picongpu::radiationMask_]" not in rendered.radiation_param


def test_generated_setup_renders_rng_mask_functor_for_filtered_species():
    def keep_half(particle, rng: RNGArg):
        return rng.get("uniform") > 0.5

    sim, electrons = make_sim()
    filtered_species = FilteredSpecies(species=electrons, functor=ParticleFilter(name="keepHalf", functor=keep_half))
    sim.add_diagnostic(Radiation(species=filtered_species, period=TimeStepSpec[2:4:2], observer=make_observer()))
    with tempfile.TemporaryDirectory() as parent:
        # the runner requires the setup directory to not exist yet
        setup_dir = Path(parent) / "setup"
        sim.write_input_file(setup_dir)
        radiation_param = (setup_dir / "include/picongpu/param/radiation.param").read_text()
    assert "struct electron_keepHalfMaskFunctor" in radiation_param
    assert "using RNGType = typename std::remove_cvref_t<decltype(rng.m_rng)>;" in radiation_param
    assert "particle[picongpu::radiationMask_] = random0 > 0.5;" in radiation_param
    assert "manipulators::generic::FreeRng<" in radiation_param
    assert "pmacc::random::distributions::Uniform< float_X >" in radiation_param


def test_n_cfg_radiation_block_is_known_wrong_until_task_15():
    # KNOWN BROKEN STATE, deferred to task 15: the radiation block of
    # N.cfg.mustache iterates {{#species}} and uses {{{name}}}, which for a
    # FilteredSpecies is "<species>_<filter>". The whole block is therefore
    # emitted under a CLI prefix no C++ plugin registers, and it carries no
    # .filter line (the C++ option does not exist yet). Task 15 must flip
    # this block to --electron_radiation.* plus
    # --electron_radiation.filter rangeFilter.
    rendered = _render(filtered=True)
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
        assert f"--electron_rangeFilter_radiation.{option}" in rendered.n_cfg
    # the prefix the C++ plugin actually registers is absent
    assert "--electron_radiation." not in rendered.n_cfg
    # the C++ radiation plugin has no .filter option until task 15
    assert "_radiation.filter" not in rendered.n_cfg
