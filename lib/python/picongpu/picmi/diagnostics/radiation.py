"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

from pydantic import ConfigDict, field_validator

from picongpu.picmi.diagnostics.timestepspec import TimeStepSpec
from picongpu.picmi.particle_functor.particle_filter import FilteredSpecies
from picongpu.picmi.species import Species
from picongpu.pypicongpu.output.radiation import (
    FormFactorConfiguration as FormFactorConfiguration,
    FrequenciesFromList as FrequenciesFromList,
    FrequencyConfiguration as FrequencyConfiguration,
    LinearFrequencies as LinearFrequencies,
    LogFrequencies as LogFrequencies,
    RadiationConfiguration as RadiationConfiguration,
    RadiationObserverConfiguration as RadiationObserverConfiguration,
    RadiationPlugin,
    RadiationPluginConfig,
    WindowFunctionConfiguration as WindowFunctionConfiguration,
)
from picongpu.pypicongpu.species.attribute.momentum_prev_1 import MomentumPrev1
from picongpu.pypicongpu.species.attribute.radiation_mask import RadiationMask


class Radiation(RadiationPluginConfig):
    species: list[Species | FilteredSpecies]
    period: TimeStepSpec

    @field_validator("species", mode="before")
    @classmethod
    def _validate_species(cls, value):
        if isinstance(value, (Species, FilteredSpecies)):
            return [value]
        if isinstance(value, (list, tuple)):
            return value
        raise ValueError(f"species must be a Species or FilteredSpecies (or a list thereof), got {value!r}")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for s in self.species:
            species = s.species if isinstance(s, FilteredSpecies) else s
            requirements = [MomentumPrev1()]
            # The C++ filter (plugins::radiation::executeParticleFilter) only
            # runs on species that carry the radiationMask attribute, and a mask
            # functor is rendered for exactly those species: a filtered species,
            # whose mask is set by its particle filter. A plain species has no
            # mask, so all of its particles contribute unfiltered. Register the
            # attribute for filtered species so the mask is actually written and
            # read.
            if isinstance(s, FilteredSpecies):
                requirements.append(RadiationMask())
            species.register_requirements(requirements)

    def get_as_pypicongpu(self, time_step_size, num_steps):
        return RadiationPlugin(
            config=self,
            species=[
                s.get_as_pypicongpu(mode="Filter") if isinstance(s, FilteredSpecies) else s.get_as_pypicongpu()
                for s in self.species
            ],
            period=self.period.get_as_pypicongpu(time_step_size=time_step_size, num_steps=num_steps),
        )

    model_config = ConfigDict(arbitrary_types_allowed=True)
