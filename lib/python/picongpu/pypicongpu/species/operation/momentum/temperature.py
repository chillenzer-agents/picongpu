"""
This file is part of PIConGPU.
Copyright 2021-2024 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre
License: GPLv3+
"""

from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field, PlainSerializer, model_validator

from ....rendering import RenderedObject
from ....validation import exactly_one
from ....vector import deserialise_vec, serialise_vec

# Note to the future maintainer:
# If you want to add another way to specify the temperature, please turn
# Temperature() into an (abstract) parent class, and add one child class per
# method. (Currently only initialization by giving a temperature in keV is
# supported, so such a structure would be overkill.)


Vec3_float_temperature = Annotated[
    tuple[float, float, float],
    BeforeValidator(deserialise_vec),
    PlainSerializer(serialise_vec),
]


class Temperature(RenderedObject, BaseModel):
    """
    Initialize momentum from temperature

    Exactly one of temperature_kev (isotropic) or temperature_kev_directional
    (per-component) must be set.
    """

    temperature_kev: float | None = Field(default=None, gt=0.0)
    """isotropic temperature in keV"""

    temperature_kev_directional: Vec3_float_temperature | None = None
    """per-component temperature (x, y, z) in keV for directional initialization"""

    @model_validator(mode="after")
    def _validate_exactly_one(self):
        exactly_one(
            {
                "temperature_kev": self.temperature_kev is not None,
                "temperature_kev_directional": self.temperature_kev_directional is not None,
            },
            message="Exactly one of temperature_kev or temperature_kev_directional must be set",
        )
        return self
