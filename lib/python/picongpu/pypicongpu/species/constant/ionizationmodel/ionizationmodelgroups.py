"""
This file is part of PIConGPU.
Copyright 2024-2024 PIConGPU contributors
Authors: Brian Edward Marre
License: GPLv3+
"""

from .BSI import BSI
from .BSIeffectiveZ import BSIEffectiveZ
from .BSIstarkshifted import BSIStarkShifted
from .ADKlinearpolarization import ADKLinearPolarization
from .ADKcircularpolarization import ADKCircularPolarization
from .keldysh import Keldysh
from .thomasfermi import ThomasFermi
from .ionizationmodel import IonizationModel

import copy
from typing import Annotated

from pydantic import BaseModel, BeforeValidator


def _dispatch_ionization_model(value):
    # the serialized form of an ionization model (model_dump(mode="json")) does
    # not name the concrete class; the C++ ionizer name
    # (ionizer_picongpu_name, alias picongpu_name) is its discriminator, as
    # each concrete model has a distinct one. Re-attach the concrete type so
    # that a serialized list of ionization models can be re-validated without
    # losing the model-specific fields (round-trip safety).
    if not isinstance(value, dict):
        return value
    name = value.get("ionizer_picongpu_name", value.get("picongpu_name"))
    if name is not None:
        for model_name, cls in _IONIZER_NAME_TO_MODEL.items():
            if name == model_name:
                return cls.model_validate(value)
    return value


class IonizationModelGroups(BaseModel):
    """
    grouping of ionization models into sub groups that may not be used at the same time

    every instance of this class is immutable, all method always return copies of the data contained
    """

    by_group: dict[str, list[type[IonizationModel]]] = {
        "BSI_like": [BSI, BSIEffectiveZ, BSIStarkShifted],
        "ADK_like": [ADKLinearPolarization, ADKCircularPolarization],
        "Keldysh_like": [Keldysh],
        "electronic_collisional_equilibrium": [ThomasFermi],
    }
    """the mutual exclusion groups: ionization models in the same group
    (e.g. the BSI variants) must not be used at the same time; the key is
    the group name, the value the member model classes"""

    def get_by_group(self) -> dict[str, list[type[IonizationModel]]]:
        return copy.deepcopy(self.by_group)

    def get_by_model(self) -> dict[type[IonizationModel], str]:
        return_dict: dict[type[IonizationModel], str] = {}

        for ionization_model_type, list_ionization_model in self.by_group.items():
            for ionization_model in list_ionization_model:
                return_dict[ionization_model] = copy.deepcopy(ionization_model_type)

        return return_dict


# the C++ ionizer name (the default of ionizer_picongpu_name) -> model class,
# for all concrete ionization models
_IONIZER_NAME_TO_MODEL: dict[str, type[IonizationModel]] = {
    ionization_model.model_fields["ionizer_picongpu_name"].default: ionization_model
    for ionization_model in (
        BSI,
        BSIEffectiveZ,
        BSIStarkShifted,
        ADKLinearPolarization,
        ADKCircularPolarization,
        Keldysh,
        ThomasFermi,
    )
}

AnyIonizationModel = Annotated[
    BSI | BSIEffectiveZ | BSIStarkShifted | ADKLinearPolarization | ADKCircularPolarization | Keldysh | ThomasFermi,
    BeforeValidator(_dispatch_ionization_model),
]
"""union of all concrete ionization models, with a before validator that
re-attaches the concrete class from the serialized ionizer name (round-trip
safety)"""
