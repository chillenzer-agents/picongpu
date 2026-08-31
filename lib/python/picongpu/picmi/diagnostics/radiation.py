"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

import warnings

from pydantic import ConfigDict, field_validator, model_validator

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

    @model_validator(mode="after")
    def _validate_gamma_filter_threshold(self):
        # The C++ gamma filter only acts on species carrying the radiationMask
        # attribute, which __init__ registers for plain species only. Without a
        # plain species the threshold would be silently ignored, so reject it.
        if self.gamma_filter_threshold is not None and all(isinstance(s, FilteredSpecies) for s in self.species):
            raise ValueError(
                "gamma_filter_threshold has no effect when all species are filtered, because "
                "filtered species are selected by their own particle filter; "
                "express the gamma cut inside your ParticleFilter instead"
            )
        return self

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
        if self.gamma_filter_threshold is not None and any(isinstance(s, FilteredSpecies) for s in self.species):
            # mixed species list: the threshold applies to the plain species,
            # but is ignored for the filtered ones; say so instead of dropping it silently
            warnings.warn(
                "gamma_filter_threshold applies only to plain species; "
                "filtered species are selected by their own particle filter"
            )

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
