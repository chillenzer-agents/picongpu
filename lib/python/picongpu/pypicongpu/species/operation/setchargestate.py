"""
This file is part of PIConGPU.
Copyright 2021-2025 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre, Masoud Afshari
License: GPLv3+
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from ..species import Species


class SetChargeState(BaseModel):
    """
    assigns boundElectrons attribute and sets it to the initial charge state

    used for ionization of ions

    C++ counterpart: the boundElectrons initialization in
    include/picongpu/param/speciesInitialization.param.

    Units policy: charge_state is an integer count (dimensionless).
    """

    species: Species
    """species which will have boundElectrons set"""

    charge_state: Annotated[int, Field(ge=0)]
    """initial ion charge state, [dimensionless count]; must be >= 0."""

    type_setchargestate: Literal[True] = True
    """discriminator for the AnyOperation union."""

    @model_validator(mode="after")
    def check(self) -> "SetChargeState":
        element_properties = self.species.constants.element_properties
        if element_properties is not None:
            atomic_number = element_properties.element.get_atomic_number()
            if self.charge_state > atomic_number:
                raise ValueError(
                    f"initial charge state ({self.charge_state}) exceeds the atomic number "
                    f"({atomic_number}) of element {element_properties.element.symbol}"
                )
        return self
