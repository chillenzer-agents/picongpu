"""
This file is part of PIConGPU.
Copyright 2021-2025 PIConGPU contributors
Authors: Masoud Afshari, Julian Lenz
License: GPLv3+
"""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from picongpu.pypicongpu.output.timestepspec import TimeStepSpec
from picongpu.pypicongpu.particle_functor.filtered_species import FilteredSpecies
from picongpu.pypicongpu.species import Species
from picongpu.pypicongpu.validation import less_than


class EnergyHistogram(BaseModel):
    species: Species | FilteredSpecies
    period: TimeStepSpec
    bin_count: int = Field(gt=0)
    min_energy: float
    max_energy: float

    type_energyhistogram: Literal[True] = True

    @model_validator(mode="after")
    def check(self):
        less_than(self.min_energy, self.max_energy, lesser_field="min_energy", greater_field="max_energy")
        return self
