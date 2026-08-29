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
        return [value] if isinstance(value, (Species, FilteredSpecies)) else value

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for s in self.species:
            species = s.species if isinstance(s, FilteredSpecies) else s
            requirements = [MomentumPrev1()]
            if isinstance(s, Species) and self.gamma_filter_threshold is not None:
                # Filtered species are selected by their own particle filter
                # and therefore do not need the hardcoded gamma mask.
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
