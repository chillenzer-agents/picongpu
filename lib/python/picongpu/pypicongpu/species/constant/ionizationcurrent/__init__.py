from typing import Annotated

from pydantic import BeforeValidator

from .ionizationcurrent import IonizationCurrent
from .none_ import None_
from .energyconservation import EnergyConservation


def _dispatch_ionization_current(value):
    # the serialised form of an ionization current (model_dump(mode="json")) does
    # not name the concrete class; the C++ name (picongpu_name) is its
    # discriminator, as each concrete current has a distinct one (None_ -> "None",
    # EnergyConservation -> "EnergyConservation"). Re-attach the concrete type so
    # that a serialised ionization current can be re-validated without losing the
    # model-specific fields (round-trip safety). The smart union would mis-dispatch
    # because all concrete currents share the same (picongpu_name, ) field layout.
    if not isinstance(value, dict):
        return value
    name = value.get("picongpu_name")
    if name is not None:
        for current_name, cls in _PICONGPU_NAME_TO_CURRENT.items():
            if name == current_name:
                return cls.model_validate(value)
    return value


# the C++ name (the default of picongpu_name) -> current class, for all concrete
# ionization currents
_PICONGPU_NAME_TO_CURRENT: dict[str, type[IonizationCurrent]] = {
    current.model_fields["picongpu_name"].default: current for current in (None_, EnergyConservation)
}

AnyIonizationCurrent = Annotated[
    None_ | EnergyConservation,
    BeforeValidator(_dispatch_ionization_current),
]
"""union of all concrete ionization currents, with a before validator that
re-attaches the concrete class from the serialized C++ name (round-trip safety)"""

__all__ = ["IonizationCurrent", "None_", "EnergyConservation", "AnyIonizationCurrent"]
