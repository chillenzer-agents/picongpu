"""
This file is part of PIConGPU.
Copyright 2024-2024 PIConGPU contributors
Authors: Brian Edward Marre
License: GPLv3+
"""

import typing

from pydantic import ConfigDict, Field, field_validator

from picongpu.pypicongpu.species.constant import Constant
from picongpu.pypicongpu.species.constant.ionizationcurrent import None_


class IonizationModel(Constant):
    """
    base class for an ground state only ionization models of an ion species

    Owned by exactly one species.

    Identified by its PIConGPU name.

    PIConGPU term: "ionizer".

    C++ counterpart: the `particles::ionization::<ionizer>` template argument
    of the `ionizers<...>` particle flag in
    include/picongpu/param/speciesDefinition.param.
    """

    model_config = ConfigDict(populate_by_name=True)

    ionizer_picongpu_name: str = Field(alias="picongpu_name")
    """C++ type name of the ionizer (e.g. "BSI", "ADKLinPol"), rendered into the
    ionizers particle flag; must be a valid C++ identifier."""

    # no typecheck here -- would require circular imports
    ionization_electron_species: typing.Any
    """species to be used as the ionization electrons (rendered as a template
    argument of the ionizer)"""

    ionization_current: None_ | None = None
    """ionization current implementation to use (None = no current model)"""

    @field_validator("ionization_electron_species", mode="before")
    @classmethod
    def _rehydrate_electron_species(cls, value):
        # the model_dump of a species held in this (Any-typed) field is a plain
        # dict in json mode; reconstruct the species so that the model can be
        # used (e.g. rendered) again after a serialization round-trip.
        # import here to avoid a circular import (species -> constants -> species)
        if isinstance(value, dict):
            from picongpu.pypicongpu.species.species import Species

            return Species.model_validate(value)
        return value
