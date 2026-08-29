"""
This file is part of PIConGPU.
Copyright 2024-2024 PIConGPU contributors
Authors: Brian Edward Marre
License: GPLv3+
"""

from pydantic import model_validator

from .constant import Constant
from .ionizationmodel import AnyIonizationModel, IonizationModelGroups


class GroundStateIonization(Constant):
    """
    ground state ionization of a species

    Bundles the ground state only ionization models that apply to the species.

    C++ counterpart: the `ionizers<...>` particle flag in
    include/picongpu/param/speciesDefinition.param.
    """

    ionization_model_list: list[AnyIonizationModel]
    """list of ground state only ionization models to apply for the species;
    must be non-empty, at most one model per ionization model group."""

    @model_validator(mode="after")
    def check(self) -> None:
        # check that at least one ionization model in list
        if len(self.ionization_model_list) == 0:
            raise ValueError("at least one ionization model must be specified if ground_state_ionization is not none.")

        # call check() all ionization models
        for ionization_model in self.ionization_model_list:
            ionization_model.check()

        # check that no ionization model group is represented more than once
        by_model = IonizationModelGroups().get_by_model()
        group_members: dict[str, list[str]] = {}
        for ionization_model in self.ionization_model_list:
            group = by_model[type(ionization_model)]
            group_members.setdefault(group, []).append(type(ionization_model).__name__)

        conflicts = {g: names for g, names in group_members.items() if len(names) > 1}
        if conflicts:
            details = "; ".join(f"group {g!r}: {' and '.join(names)}" for g, names in conflicts.items())
            raise ValueError(
                f"Multiple ionization models from the same group are not allowed: {details}. "
                f"Remove all but one model per group."
            )
        return self
