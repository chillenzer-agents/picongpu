"""
This file is part of PIConGPU.
Copyright 2021-2025 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre, Julian Lenz
License: GPLv3+
"""

from typing import Literal

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

from ..species import Species
from .densityprofile import AnyDensityProfile
from .layout import AnyLayout


class SimpleDensity(BaseModel):
    """
    Place a set of species together, using the same density profile

    These species will have **the same** macroparticle placement.

    For this operation, only the random layout is supported.

    parameters:

    - ppc: particles placed per cell
    - profile: density profile to use
    - species: species to be placed with the given profile
      note that their density ratios will be respected

    C++ counterpart: the species initialization blocks in
    include/picongpu/param/speciesInitialization.param.
    """

    profile: AnyDensityProfile
    """density profile to use, describes the actual density"""

    species: list[Species] = Field(exclude=True)
    """species to be placed (sorted by density ratio); excluded from serialization"""

    layout: AnyLayout
    """layout (macroparticle placement) to use for the species"""

    type_simpledensity: Literal[True] = True
    """discriminator for the AnyOperation union."""

    @model_validator(mode="before")
    @classmethod
    def _reconstruct_species(cls, data):
        # `species` is excluded from the serialised form; instead, the computed
        # fields placed_species_initial / placed_species_copied are dumped.
        # Rebuild the species list from them so that model_dump(mode="json")
        # output can be validated again (round-trip safety).
        if isinstance(data, dict) and "species" not in data and data.get("placed_species_initial") is not None:
            copied = data.get("placed_species_copied") or []
            data = {
                **data,
                "species": [Species.model_validate(data["placed_species_initial"])]
                + [Species.model_validate(entry) for entry in copied],
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
        return sorted(
            set(species),
            key=lambda species: 0 if species.constants.density_ratio is None else species.constants.density_ratio.ratio,
        )

    @computed_field
    def placed_species_initial(self) -> Species:
        return self.species[0]

    @computed_field
    def placed_species_copied(self) -> list[Species]:
        return self.species[1:]

    def __init__(self, *args, **kwargs):
        return BaseModel.__init__(self, *args, **kwargs)
