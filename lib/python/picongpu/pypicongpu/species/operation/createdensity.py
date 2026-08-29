"""
This file is part of PIConGPU.
Copyright 2021-2026 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre, Julian Lenz
License: GPLv3+
"""

from typing import Literal

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

from ..species import Species
from .densityprofile import AnyDensityProfile
from .layout import AnyLayout


class CreateDensity(BaseModel):
    """
    place a set of species together, using the same density profile

    These species will have **the same** macroparticle placement.

    C++ counterpart: the `CreateDensity<T_DensityFunctor, T_PositionFunctor,
    T_SpeciesType>` init-pipeline functor
    (include/picongpu/particles/InitFunctors.hpp): the first species is
    *created* by sampling the density profile with the start-position
    functor (which derives the macroparticle positions, counts and
    weightings from the grid), and every further species is *derived* from
    it via `ManipulateDerive<manipulators::binary::DensityWeighting, ...>`,
    i.e. it copies the created positions and rescales the weighting by the
    species' density ratio.

    parameters:

    - start_position: the C++ T_PositionFunctor (startPosition::pypicongpu
      in particle.param) describing how macroparticles are placed inside a
      cell
    - profile: the C++ T_DensityFunctor (densityProfiles::pypicongpu in
      density.param) describing the actual density
    - species: species to be placed with the given profile; the first is
      created, the rest are derived (their density ratios are respected)
    """

    profile: AnyDensityProfile
    """density profile to use, describes the actual density
    (C++ T_DensityFunctor of CreateDensity)"""

    species: list[Species] = Field(exclude=True)
    """species to be placed (sorted by density ratio, ties broken by name);
    excluded from serialization"""

    start_position: AnyLayout
    """start position functor (macroparticle placement) to use for the
    species (C++ T_PositionFunctor of CreateDensity)"""

    type_createdensity: Literal[True] = True
    """discriminator for the AnyOperation union."""

    @model_validator(mode="before")
    @classmethod
    def _reconstruct_species(cls, data):
        # `species` is excluded from the serialised form; instead, the computed
        # fields created_species / derived_species are dumped.
        # Rebuild the species list from them so that model_dump(mode="json")
        # output can be validated again (round-trip safety).
        if isinstance(data, dict) and "species" not in data and data.get("created_species") is not None:
            derived = data.get("derived_species") or []
            data = {
                **data,
                "species": [Species.model_validate(data["created_species"])]
                + [Species.model_validate(entry) for entry in derived],
            }
        return data

    @field_validator("species", mode="before")
    @classmethod
    def validate_species(cls, species):
        if not isinstance(species, list):
            # let the field type validation (or the containing union) report a
            # proper error instead of failing with an AttributeError here
            raise ValueError(f"species must be a list of Species. You gave: {species=}.")
        species = [Species.model_validate(entry) if isinstance(entry, dict) else entry for entry in species]
        # the created species must be placed first: ratio-less species come
        # first, then species with increasing density ratio; ties are broken
        # by name, so the (rendered) species order is deterministic
        def sort_key(species):
            ratio = species.constants.density_ratio
            return (0 if ratio is None else ratio.ratio, species.name)

        return sorted(set(species), key=sort_key)

    @computed_field
    def created_species(self) -> Species:
        """species created via CreateDensity (C++ T_SpeciesType)"""
        return self.species[0]

    @computed_field
    def derived_species(self) -> list[Species]:
        """species derived from the created species via
        ManipulateDerive<DensityWeighting, ...>"""
        return self.species[1:]

    def __init__(self, *args, **kwargs):
        return BaseModel.__init__(self, *args, **kwargs)
