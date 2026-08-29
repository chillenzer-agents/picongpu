"""
This file is part of PIConGPU.
Copyright 2025 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

from os import PathLike
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, computed_field

from picongpu.picmi.particle_functor.particle_filter import FilteredSpecies
from picongpu.picmi.species import Species
from picongpu.pypicongpu.output.openpmd_plugin import NATIVE_FIELDS
from .backend_config import BackendConfig, OpenPMDConfig
from .timestepspec import TimeStepSpec
from picongpu.picmi.particle_functor import ParticleFunctor


class _FieldDump(BaseModel):
    """
    base class for openPMD field dumps (native fields and derived fields).

    Parameters
    ----------
    period: TimeStepSpec, optional
        The time steps at which the field is dumped (default: every step).

    options: OpenPMDConfig, optional
        The openPMD backend configuration (default: file prefix "simData").
    """

    period: TimeStepSpec = TimeStepSpec[:]("steps")
    """the time steps at which the field is dumped, [time-step number]"""

    options: BackendConfig = OpenPMDConfig(file="simData")
    """the openPMD backend configuration (file prefix, infix, extension, ...)"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def result_path(self, prefix_path: PathLike):
        return self.options.result_path(prefix_path=Path(prefix_path) / "simOutput" / "openPMD")


class NativeFieldDump(_FieldDump):
    """a dump of one of the native fields (E, B, or J)."""

    fieldname: Literal[*NATIVE_FIELDS]
    """the native field to dump (E, B, or J)"""

    filtername: None = None
    """always None (native fields cannot be particle-filtered)"""


class DerivedFieldDump(_FieldDump):
    """a dump of a derived field (a particle functor applied to a species)."""

    species: Species | FilteredSpecies
    """the species (or filtered species) the functor is applied to"""

    functor: ParticleFunctor
    """the particle functor computing the derived field"""

    @computed_field
    def filtername(self) -> None | str:
        return None if isinstance(self.species, Species) else self.species.functor.name

    @computed_field
    def fieldname(self) -> str:
        species_name = self.species.name if isinstance(self.species, Species) else self.species.species.name
        return f"{species_name}_{self.filtername or 'all'}_{self.functor.name}"
