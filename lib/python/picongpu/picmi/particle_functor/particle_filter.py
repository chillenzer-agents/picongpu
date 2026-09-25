"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

from typing import Annotated, Any, Callable

from pydantic import BaseModel, ConfigDict, computed_field

from picongpu.picmi.particle_functor.particle_functor import Particle, ParticleFunctor
from picongpu.picmi.species import Species
from picongpu.pypicongpu.particle_functor import FilteredSpecies as PyPIConGPUFilteredSpecies
from picongpu.pypicongpu.util import as_functor


class ParticleFilter(ParticleFunctor):
    def __init__(self, functor: Callable[[Particle], Any], name: str | None = None):
        super().__init__(name=name, functor=functor, return_type=bool, unit_dimension=None)

    def get_as_pypicongpu(self, mode="Filter"):
        return super().get_as_pypicongpu(mode=mode)


class FilteredSpecies(BaseModel):
    species: Species
    # A bare named callable is turned into a ParticleFilter (the field's declared class);
    # @ParticleFilter remains the explicit way to obtain a filter. Anonymous callables
    # and C++-invalid names are rejected eagerly by the coercion helper.
    functor: Annotated[ParticleFilter, as_functor(ParticleFilter, usage="@ParticleFilter(name='my_filter').")]

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @computed_field
    def name_with_filter(self) -> str:
        return f"{self.species.name}_{self.functor.name}"

    @computed_field
    def species_name(self) -> str:
        return self.species.name

    @computed_field
    def name(self) -> str:
        return self.name_with_filter

    def get_as_pypicongpu(self, mode="Filter", *args, **kwargs):
        # additional arguments (e.g. time_step_size, num_steps) are forwarded by the conversion
        # machinery of diagnostics and are not used by this class
        return PyPIConGPUFilteredSpecies(
            species=self.species.get_as_pypicongpu(*args, **kwargs),
            functor=self.functor.get_as_pypicongpu(mode=mode),
        )
