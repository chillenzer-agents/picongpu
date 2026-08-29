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


class PhaseSpace(BaseModel):
    """
    the phase-space diagnostic for one species

    C++ counterpart: the PhaseSpace plugin parameters
    (--<species>_phaseSpace.* in etc/picongpu/N.cfg).

    Units policy: momentum in units of [m_species * c] (dimensionless
    multiple of the species rest momentum); time steps are dimensionless.
    """

    species: Species | FilteredSpecies
    """the species (or filtered species) whose phase space is dumped"""

    period: TimeStepSpec
    """the time steps at which the phase space is dumped,
    [time-step number]"""

    spatial_coordinate: Literal["x", "y", "z"]
    """the spatial coordinate plotted against the momentum
    (C++: --<species>_phaseSpace.space)"""

    momentum_coordinate: Literal["px", "py", "pz"]
    """the momentum component used for the phase space
    (C++: --<species>_phaseSpace.momentum)"""

    min_momentum: float
    """lower bound of the momentum range, [m_species * c];
    must be < max_momentum (C++: --<species>_phaseSpace.min)"""

    max_momentum: float
    """upper bound of the momentum range, [m_species * c];
    must be > min_momentum (C++: --<species>_phaseSpace.max)"""

    type_phasespace: Literal[True] = True
    """tag field identifying the phase-space diagnostic (discriminator)"""

    @model_validator(mode="after")
    def check(self):
        if self.min_momentum >= self.max_momentum:
            raise ValueError(
                "PhaseSpace's min_momentum should be smaller than max_momentum. "
                f"You gave: {self.min_momentum=} and {self.max_momentum=}."
            )
        return self
