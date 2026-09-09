"""
This file is part of PIConGPU.
Copyright 2025-2026 PIConGPU contributors
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


Vec3_float = Annotated[
    tuple[float, float, float],
    BeforeValidator(deserialise_vec),
    PlainSerializer(serialise_vec),
    AfterValidator(
        partial(
            broadcast_validation,
            condition=lambda v: v >= 0 and v < 1,
            message="All of in_cell_offset must be between 0 and 1.",
        )
    ),
]


class OnePosition(BaseModel):
    """
    place exactly one macroparticle per cell at a fixed position inside the cell

    C++ counterpart: the one-position layout in
    include/picongpu/param/particle.param (inCellOffset).

    Units policy: in_cell_offset is in units of the cell size (dimensionless),
    ppc is a count.
    """

    type_one_position: Literal[True] = True
    """discriminator for the AnyLayout union."""

    in_cell_offset: Vec3_float = Field(default=(0.0, 0.0, 0.0))
    """Offset inside of the cell relative to cell size, i.e., between 0 and 1,
    [dimensionless]; each component must satisfy 0 <= x < 1.
    C++ name: inCellOffset (particle.param)."""

    ppc: Annotated[int, Field(gt=0)]
    """particles per cell, [dimensionless count]; must be > 0."""
