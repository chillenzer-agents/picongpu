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
    sets the initial charge state of an ion species

    used for ionization of ions

    C++ counterpart: the `manipulators::unary::ChargeState<T_chargeState>`
    init-pipeline manipulator (include/picongpu/particles/manipulators/unary/
    ChargeState.hpp, rendered as `PreIonize_<typename>` in particle.param and
    applied via `Manipulate<...>` in speciesInitialization.param).

    Note the distinction between the two charge concepts:

    - the *charge state* (this operation's `charge_state`, the C++ template
      parameter `T_chargeState`) is the number of stripped electrons, i.e.
      the positive charge of the ion;
    - the *bound electron count* (the `boundElectrons` species attribute) is
      the number of electrons still bound to the nucleus,
      `atomic_number - charge_state`. It is what C++ stores on the ion and
      derives here in the `acc::ChargeState` functor via
      `atomicPhysics::SetChargeState`.

    Units policy: charge_state is an integer count (dimensionless).
    """

    species: Species
    """species which will have boundElectrons set"""

    charge_state: Annotated[int, Field(ge=0)]
    """initial ion charge state (number of stripped electrons),
    [dimensionless count]; must be >= 0 and (when the atomic number is known)
    <= atomic number, as enforced by the C++ compile-time assertion
    `Too_high_charge_state_for_atomic_number`."""

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
