"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

from functools import partial
from typing import Annotated, Literal

from pydantic import AfterValidator, BeforeValidator, BaseModel, Field, PlainSerializer


def serialise_vec(value) -> dict:
    return dict(zip("xyz", value))


def deserialise_vec(value):
    # accept the serialised form (dict with x/y/z keys) in addition to the
    # native tuple form, so that model_dump(mode="json") output can be
    # validated again (round-trip safety)
    if isinstance(value, dict):
        try:
            return (value["x"], value["y"], value["z"])
        except KeyError as error:
            raise ValueError(f"Expected a vector with the keys x, y, z. You gave: {value=}.") from error
    return value


def broadcast_validation(values, condition, message="Condition not met."):
    if not all(condition(value) for value in values):
        raise ValueError(f"{message} You gave: {values}.")
    return values


Vec3_int = Annotated[
    tuple[int, int, int],
    BeforeValidator(deserialise_vec),
    PlainSerializer(serialise_vec),
    AfterValidator(
        partial(
            broadcast_validation,
            condition=lambda v: v > 0,
            message="Number of points must be greater than 0 in each direction.",
        )
    ),
]


class Quiet(BaseModel):
    """
    place macroparticles on a regular (quiet) grid inside each cell

    C++ counterpart: the quiet layout in include/picongpu/param/particle.param
    (numParticlesPerDimension).

    Units policy: n_points is a count per dimension, ppc is a count.
    """

    type_quiet: Literal[True] = True
    """discriminator for the AnyLayout union."""

    n_points: Vec3_int = Field(default=(1, 1, 1))
    """number of particles per dimension inside a cell as 3-integer tuple,
    [dimensionless count]; must be > 0 in each direction.
    C++ name: numParticlesPerDimension (particle.param)."""

    ppc: Annotated[int, Field(gt=0)]
    """particles per cell, [dimensionless count]; must be > 0."""
