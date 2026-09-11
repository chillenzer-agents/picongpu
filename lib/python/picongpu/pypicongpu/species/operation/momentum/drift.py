"""
This file is part of PIConGPU.
Copyright 2021-2024 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre
License: GPLv3+
"""

import math
from typing import Annotated

from pydantic import AfterValidator, BaseModel, BeforeValidator, Field, PlainSerializer
from scipy import constants

from ....rendering import RenderedObject
from ....validation import unit_vector
from ....vector import deserialise_vec, serialise_vec

# Note to the future maintainer:
# If you want to add another way to specify the drift, please turn
# Drift() into an (abstract) parent class, and add one child class per
# method.


Vec3_float = Annotated[
    tuple[float, float, float],
    BeforeValidator(deserialise_vec),
    AfterValidator(unit_vector),
    PlainSerializer(serialise_vec),
]


class Drift(RenderedObject, BaseModel):
    """
    Add drift to a species (momentum)

    Note that the drift is specified by a direction (normalized velocity
    vector) and gamma. Helpers to load from other representations (originating
    from PICMI) are provided.
    """

    direction_normalized: Vec3_float
    """direction of drift, length of one"""

    gamma: float = Field(ge=1.0, allow_inf_nan=False)
    """gamma, the physicists know"""

    @classmethod
    def from_velocity(cls, velocity: tuple[float, float, float]):
        """
        set attributes to represent given velocity vector

        computes gamma and direction_normalized for self

        :param velocity: velocity given as vector
        """
        if (0, 0, 0) == velocity:
            raise ValueError("velocity must not be zero")

        velocity_linear = math.sqrt(sum(map(lambda x: x**2, velocity)))
        if velocity_linear >= constants.speed_of_light:
            raise ValueError(
                "linear velocity must be less than the speed of light (currently: {})".format(velocity_linear)
            )

        return cls(
            gamma=math.sqrt(1 / (1 - (velocity_linear**2 / constants.speed_of_light**2))),
            direction_normalized=tuple(map(lambda x: x / velocity_linear, velocity)),
        )

    @classmethod
    def from_gamma_velocity(cls, gamma_velocity: tuple[float, float, float]):
        """
        set attributes to represent given velocity vector multiplied with gamma

        computes gamma and direction_normalized for self

        :param velocity: velocity given as vector multiplied with gamma
        """
        if (0, 0, 0) == gamma_velocity:
            raise ValueError("velocity must not be zero")

        gamma_velocity_linear = math.sqrt(sum(map(lambda x: x**2, gamma_velocity)))
        gamma = math.sqrt(1 + ((gamma_velocity_linear) ** 2 / constants.speed_of_light**2))

        return cls(direction_normalized=tuple(map(lambda x: x / gamma_velocity_linear, gamma_velocity)), gamma=gamma)
