"""
This file is part of PIConGPU.
Copyright 2021-2025 PIConGPU contributors
Authors: Masoud Afshari, Julian Lenz
License: GPLv3+
"""

from typing import Literal

from pydantic import BaseModel, model_validator

from picongpu.pypicongpu.output.timestepspec import TimeStepSpec
from picongpu.pypicongpu.particle_functor.filtered_species import FilteredSpecies
from picongpu.pypicongpu.species import Species
from picongpu.pypicongpu.validation import less_than


class PhaseSpace(BaseModel):
    species: Species | FilteredSpecies
    period: TimeStepSpec
    spatial_coordinate: Literal["x", "y", "z"]
    momentum_coordinate: Literal["px", "py", "pz"]
    min_momentum: float
    max_momentum: float

    type_phasespace: Literal[True] = True

    @model_validator(mode="after")
    def check(self):
        less_than(self.min_momentum, self.max_momentum, lesser_field="min_momentum", greater_field="max_momentum")
        return self
