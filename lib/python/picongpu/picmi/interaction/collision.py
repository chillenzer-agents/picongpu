"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

from itertools import combinations, combinations_with_replacement

from pydantic import BaseModel, Field, field_validator

from picongpu.picmi.species import Species
from picongpu.picmi.particle_functor.particle_filter import FilteredSpecies
from picongpu.pypicongpu.collisions import Collision as PyPIConGPUCollision
from picongpu.pypicongpu.collisions import CollisionalPhysicsSetup as PyPIConGPUCollisionalPhysicsSetup
from picongpu.pypicongpu.collisions import CollisionFunctor
from picongpu.pypicongpu.collisions import CollisionNumericsConfig as CollisionNumericsConfig
from picongpu.pypicongpu.collisions import ConstLogCollision as ConstLogCollision
from picongpu.pypicongpu.collisions import DynamicLogCollision as DynamicLogCollision


class Collision(BaseModel):
    """
    one collision interaction between species pairs (user-facing wrapper)

    Thin PICMI-layer bridge: holds the PICMI species until conversion and
    delegates the model semantics (validation, serialisation, rendering) to
    the pypicongpu model `picongpu.pypicongpu.collisions.Collision`; the
    single source of truth (see it for the C++ counterpart and the units
    policy).
    """

    species_pairs: list[tuple[Species | FilteredSpecies, Species | FilteredSpecies]]
    """the interacting species pairs (PICMI species; see pypicongpu
    `Collision.species_pairs` for the invariants)"""

    functor: CollisionFunctor
    """the collision functor (constant or dynamic Coulomb logarithm;
    defined by pypicongpu)"""

    @classmethod
    def construct_from_pairs(cls, species_pairs, **kwargs):
        """Construct from Collision from pairs. Same as normal constructor."""
        return cls(species_pairs=species_pairs, **kwargs)

    @classmethod
    def construct_one_to_all(cls, one, to_all_of, **kwargs):
        """Construct collision of one species with all of the `to_all_of` species."""
        return cls(species_pairs=[(one, a) for a in to_all_of], **kwargs)

    @classmethod
    def construct_all_to_all(cls, species, include_self_collisions=True, **kwargs):
        """Construct collisions among all the given species."""
        combine = combinations_with_replacement if include_self_collisions else combinations
        return cls(species_pairs=list(combine(species, 2)), **kwargs)

    def get_as_pypicongpu(self):
        return PyPIConGPUCollision(
            species_pairs=map(lambda x: map(lambda y: y.get_as_pypicongpu(), x), self.species_pairs),
            functor=self.functor,
        )


class CollisionalPhysicsSetup(BaseModel):
    """
    the collisional physics setup (user-facing wrapper)

    Thin PICMI-layer bridge: holds the PICMI species until conversion and
    delegates the model semantics (validation, serialisation, rendering) to
    the pypicongpu model `picongpu.pypicongpu.collisions.CollisionalPhysicsSetup`
    (the single source of truth; see it for the C++ counterpart and the
    invariants, e.g. that a dynamic-log collision requires screening species;
    that check now runs when the setup is converted to pypicongpu).
    """

    collisions: list[Collision] = Field(default_factory=list)
    """the collisions (a single Collision is accepted and wrapped in a list)"""

    screening_species: list[Species | FilteredSpecies] = Field(default_factory=list)
    """the species contributing to the Debye screening length"""

    numerics_config: CollisionNumericsConfig = CollisionNumericsConfig()
    """the numerics configuration of the collision plugin (defined by pypicongpu)"""

    def __init__(self, *args, **kwargs):
        if len(args) == 1:
            if "collisions" not in kwargs:
                kwargs["collisions"] = args[0]
                args = tuple()
            else:
                raise ValueError(f"Duplicated collisions argument given: You gave {args=} and {kwargs=}.")
        return super().__init__(*args, **kwargs)

    @field_validator("collisions", mode="before")
    @classmethod
    def _validate_collisions(cls, value):
        if isinstance(value, Collision):
            return [value]
        return value

    def get_as_pypicongpu(self):
        return PyPIConGPUCollisionalPhysicsSetup(
            collisions=[c.get_as_pypicongpu() for c in self.collisions],
            screening_species=[s.get_as_pypicongpu() for s in self.screening_species],
            numerics_config=self.numerics_config,
        )
