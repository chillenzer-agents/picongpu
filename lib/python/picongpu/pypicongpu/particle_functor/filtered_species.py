"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

from pydantic import BaseModel, computed_field

from picongpu.pypicongpu.particle_functor.particle_functor import ParticleFunctor
from picongpu.pypicongpu.rendering.renderedobject import RenderedObject
from picongpu.pypicongpu.species.species import Species


class FilteredSpecies(BaseModel, RenderedObject):
    """
    a species with a particle filter applied

    C++ counterpart: the misc::SpeciesFilter specialization rendered into
    include/picongpu/param/particleFilters.param and used wherever a
    (possibly filtered) species is referenced (collisions, diagnostics).

    The combined name `{species.name}_{functor.name}` is used as the C++
    type name of the filtered species.

    Units policy: see the species and the functor.
    """

    species: Species
    """the underlying species"""

    functor: ParticleFunctor
    """the particle filter (a boolean particle functor) selecting the
    subset of particles"""

    @computed_field
    def name_with_filter(self) -> str:
        return f"{self.species.name}_{self.functor.name}"

    @computed_field
    def species_name(self) -> str:
        return self.species.name

    @computed_field
    def filter_name(self) -> str:
        return self.functor.name

    @computed_field
    def filter_typename(self) -> str:
        return self.filter_name

    @computed_field
    def typename(self) -> str:
        return self.species.typename

    @computed_field
    def name(self) -> str:
        return self.name_with_filter

    @computed_field
    def type_filtered(self) -> bool:
        return True
