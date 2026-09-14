"""
This file is part of PIConGPU.
Copyright 2021-2025 PIConGPU contributors
Authors: Masoud Afshari, Julian Lenz
License: GPLv3+
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from picongpu.pypicongpu.output.timestepspec import TimeStepSpec
from picongpu.pypicongpu.particle_functor.filtered_species import FilteredSpecies
from picongpu.pypicongpu.species import Species


class EnergyHistogram(BaseModel):
    """
    the energy histogram diagnostic for one species

    C++ counterpart: the BinEnergyParticles plugin parameters
    (--<species>_energyHistogram.* in etc/picongpu/N.cfg).

    Units policy: energy in [keV] (C++ convention, not SI); time steps are
    dimensionless.
    """

    species: Species | FilteredSpecies
    """the species (or filtered species) whose energy histogram is dumped"""

    period: TimeStepSpec
    """the time steps at which the histogram is dumped, [time-step number]"""

    bin_count: Annotated[int, Field(gt=0)]
    """number of bins covering the energy range, [dimensionless]; must be > 0
    (C++: --<species>_energyHistogram.binCount)"""

    min_energy: Annotated[float, Field(ge=0.0)]
    """lower bound of the energy range, [keV]; must be >= 0 (energy is
    non-negative) and < max_energy (C++: --<species>_energyHistogram.minEnergy)"""

    max_energy: float
    """upper bound of the energy range, [keV]; must be > min_energy
    (C++: --<species>_energyHistogram.maxEnergy)"""

    type_energyhistogram: Literal[True] = True
    """tag field identifying the energy-histogram diagnostic (discriminator)"""

    @model_validator(mode="after")
    def check(self):
        if self.min_energy >= self.max_energy:
            raise ValueError(
                "EnergyHistogram's min_energy should be smaller than max_energy. "
                f"You gave: {self.min_energy=} and {self.max_energy=}."
            )
        return self
