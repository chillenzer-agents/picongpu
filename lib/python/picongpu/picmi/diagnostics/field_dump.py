"""
This file is part of PIConGPU.
Copyright 2025 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

from os import PathLike
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, computed_field

from picongpu.picmi.particle_functor.particle_filter import FilteredSpecies
from picongpu.picmi.species import Species
from picongpu.pypicongpu.output.openpmd_plugin import NATIVE_FIELDS
from picongpu.pypicongpu.util import as_functor
from .backend_config import BackendConfig, OpenPMDConfig
from .timestepspec import TimeStepSpec
from picongpu.picmi.particle_functor import ParticleFunctor


class _FieldDump(BaseModel):
    period: TimeStepSpec = TimeStepSpec[:]("steps")
    options: BackendConfig = OpenPMDConfig(file="simData")

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def result_path(self, prefix_path: PathLike):
        return self.options.result_path(prefix_path=Path(prefix_path) / "simOutput" / "openPMD")


class NativeFieldDump(_FieldDump):
    fieldname: Literal[*NATIVE_FIELDS]
    filtername: None = None


class DerivedFieldDump(_FieldDump):
    species: Species | FilteredSpecies
    # A bare named callable is instantiated as the field's declared class (ParticleFunctor).
    functor: Annotated[
        ParticleFunctor, as_functor(ParticleFunctor, usage="ParticleFunctor(functor=..., name='my_functor').")
    ]

    @computed_field
    def filtername(self) -> None | str:
        return None if isinstance(self.species, Species) else self.species.functor.name

    @computed_field
    def species_name(self) -> str:
        """Compile-time name of the source species, for species-eligibility narrowing."""
        return self.species.name if isinstance(self.species, Species) else self.species.species.name

    @computed_field
    def fieldname(self) -> str:
        return f"{self.species_name}_{self.filtername or 'all'}_{self.functor.name}"
