"""
This file is part of PIConGPU.
Copyright 2025 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

from os import PathLike
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from picongpu.picmi.diagnostics.backend_config import BackendConfig, OpenPMDConfig
from picongpu.picmi.diagnostics.timestepspec import TimeStepSpec
from picongpu.picmi.particle_functor.particle_filter import FilteredSpecies
from picongpu.picmi.species import Species


class ParticleDump(BaseModel):
    """
    a dump of all particles of a (filtered) species into the openPMD output.

    Parameters
    ----------
    species: Species or FilteredSpecies
        The species (or filtered species) whose particles are dumped.

    period: TimeStepSpec, optional
        The time steps at which the dump is written (default: every step).

    options: OpenPMDConfig, optional
        The openPMD backend configuration (default: file prefix "simData").
    """

    species: Species | FilteredSpecies
    """the species (or filtered species) whose particles are dumped"""

    period: TimeStepSpec = TimeStepSpec[:]("steps")
    """the time steps at which the dump is written, [time-step number]"""

    options: BackendConfig = OpenPMDConfig(file="simData")
    """the openPMD backend configuration (file prefix, infix, extension, ...)"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def result_path(self, prefix_path: PathLike):
        return self.options.result_path(prefix_path=Path(prefix_path) / "simOutput" / "openPMD")
