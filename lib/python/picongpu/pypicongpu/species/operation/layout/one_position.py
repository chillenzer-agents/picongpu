"""
This file is part of PIConGPU.
Copyright 2025-2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

from functools import partial
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, BeforeValidator, Field, PlainSerializer

from ....validation import in_unit_interval
from ....vector import deserialise_vec, serialise_vec


Vec3_float = Annotated[
    tuple[float, float, float],
    BeforeValidator(deserialise_vec),
    AfterValidator(partial(in_unit_interval, field="in_cell_offset")),
    PlainSerializer(serialise_vec),
]


class OnePosition(BaseModel):
    type_one_position: Literal[True] = True
    in_cell_offset: Vec3_float = Field(default=(0.0, 0.0, 0.0))
    """Offset inside of the cell relative to cell size, i.e., between 0 and 1"""
    ppc: int = Field(gt=0)
    """particles per cell, >0"""
