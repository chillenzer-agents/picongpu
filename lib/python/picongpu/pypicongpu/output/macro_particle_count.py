"""
This file is part of PIConGPU.
Copyright 2021-2025 PIConGPU contributors
Authors: Masoud Afshari, Julian Lenz
License: GPLv3+
"""

from typing import Literal

from pydantic import BaseModel

from picongpu.pypicongpu.output.timestepspec import TimeStepSpec
from picongpu.pypicongpu.species import Species


class MacroParticleCount(BaseModel):
    """
    the macro-particle count diagnostic for one species

    C++ counterpart: the macroParticlesCount plugin parameters
    (--<species>_macroParticlesCount.period in etc/picongpu/N.cfg).

    Units policy: time steps are dimensionless.
    """

    species: Species
    """the species whose macro-particle count is dumped"""

    period: TimeStepSpec
    """the time steps at which the count is dumped, [time-step number]"""

    type_macroparticlecount: Literal[True] = True
    """tag field identifying the macro-particle-count diagnostic (discriminator)"""
