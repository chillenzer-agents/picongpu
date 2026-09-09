"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

from itertools import chain
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    Field,
    computed_field,
    field_serializer,
    field_validator,
)

from picongpu.pypicongpu.particle_functor.filtered_species import FilteredSpecies
from picongpu.pypicongpu.species.species import Species
from picongpu.pypicongpu.util import alt, unique


class ConstLogCollision(BaseModel):
    """
    collision functor with a constant Coulomb logarithm

    C++ counterpart: the constant-log Coulomb collision functor
    (particles/collision/relativistic/RelativisticCollisionConstLog.hpp,
    the `coulombLog` parameter).

    Units policy: dimensionless.
    """

    type_constlog: Literal[True] = True
    """tag field identifying the constant-log collision functor (discriminator)"""

    coulomb_log: Annotated[float, Field(gt=0.0)]
    """the Coulomb logarithm, [dimensionless]; must be > 0 (it is the
    logarithm of the Debye-screened range ratio)"""


class DynamicLogCollision(BaseModel):
    """
    collision functor with a dynamically computed Coulomb logarithm

    C++ counterpart: the dynamic-log Coulomb collision functor
    (particles/collision/relativistic/RelativisticCollisionDynamicLog.hpp);
    the Coulomb logarithm is computed from the Debye length and clamped to
    >= 2 by the C++ implementation.

    Units policy: dimensionless.
    """

    type_dynamiclog: Literal[True] = True
    """tag field identifying the dynamic-log collision functor (discriminator)"""


CollisionFunctor = ConstLogCollision | DynamicLogCollision


def species(s: Species | FilteredSpecies):
    return alt(lambda: s.species, lambda: s)


def functor(s: Species | FilteredSpecies):
    return alt(lambda: s.functor, None)


class Collision(BaseModel):
    """
    one collision interaction between species pairs

    C++ counterpart: one entry of the CollisionPipeline
    (include/picongpu/param/collision.param).

    Units policy: see the collision functor.
    """

    species_pairs: list[tuple[Species | FilteredSpecies, Species | FilteredSpecies]]
    """the interacting species pairs; pairs with the same species but
    different filters are rejected (not supported by PIConGPU)"""

    functor: CollisionFunctor
    """the collision functor (constant or dynamic Coulomb logarithm)"""

    @field_validator("species_pairs", mode="after")
    @classmethod
    def _validate_species_pairs(cls, pairs):
        invalid_pairs = [
            pair for pair in pairs if species(pair[0]) == species(pair[1]) and functor(pair[0]) != functor(pair[1])
        ]
        if invalid_pairs:
            raise ValueError(
                f"Intra-species collisions with differently filtered species are not supported by PIConGPU. You gave: {invalid_pairs=}."
            )
        return pairs

    @computed_field
    def species(self) -> list[Species]:
        return unique(sum(self.species_pairs, tuple()))

    @computed_field
    def has_filters(self) -> bool:
        return any(isinstance(s, FilteredSpecies) for p in self.species_pairs for s in p)

    @field_serializer("species_pairs", mode="plain")
    def _species_pairs_serializer(self, value):
        return [
            {"species_lhs": pair[0].model_dump(mode="json"), "species_rhs": pair[1].model_dump(mode="json")}
            for pair in value
        ]

    @field_serializer("functor")
    def _serialize_functor(self, value):
        return value.get_rendering_context()


class CollisionNumericsConfig(BaseModel):
    """
    the numerics configuration of the collision plugin

    C++ counterpart: include/picongpu/param/collision.param
    (float_COLL precision, cellListChunkSize, debugScreeningLength).

    Units policy: dimensionless.
    """

    precision: Literal[32, 64, "X"] = 64
    """floating-point precision of the collision kernel
    (C++: precision::float_COLL; 32, 64, or X = double precision)"""

    cell_list_chunk_size: Annotated[int, Field(gt=0)] | None = None
    """chunk size for the cell-list allocations, [particle count];
    must be > 0 when set (C++: cellListChunkSize, uint32_t);
    None = the C++ default"""

    debug_screening_length: bool = False
    """if True, write the average Debye screening length to a file for
    debugging (C++: debugScreeningLength)"""


def split_into_single(collision):
    return (Collision(species_pairs=[pair], functor=collision.functor) for pair in collision.species_pairs)


class CollisionalPhysicsSetup(BaseModel):
    """
    the collisional physics setup (top level)

    C++ counterpart: include/picongpu/param/collision.param
    (CollisionPipeline, CollisionScreeningSpecies, numerics settings).

    Units policy: see the sub-models.
    """

    collisions: list[Collision] = Field(default_factory=list)
    """the collisions; each is split into single-pair collisions during
    validation (the C++ pipeline syntax does not support per-pair filters)"""

    screening_species: list[Species | FilteredSpecies] = Field(default_factory=list)
    """the species contributing to the Debye screening length
    (C++: CollisionScreeningSpecies)"""

    numerics_config: CollisionNumericsConfig = CollisionNumericsConfig()
    """the numerics configuration of the collision plugin"""

    @field_validator("collisions", mode="after")
    @classmethod
    def _validate_collisions(cls, collisions):
        # Applying filters inside of the collision pipeline has a weird syntax
        # which makes it pretty hard to apply arbitrary filters to individual pairs.
        # What we do instead is that we split each collision to only hold a single pair.
        return list(chain(*map(split_into_single, collisions)))

    @computed_field
    def num_tmp_field_slots(self) -> int:
        if len(self.screening_species) == 0:
            return 1
        if len(self.screening_species) == 1:
            return 2
        return 3
