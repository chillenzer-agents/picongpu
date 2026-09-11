"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

from functools import partial
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, BeforeValidator, Field, PlainSerializer

from ....validation import all_positive
from ....vector import deserialise_vec, serialise_vec


Vec3_int = Annotated[
    tuple[int, int, int],
    BeforeValidator(deserialise_vec),
    AfterValidator(partial(all_positive, field="n_points")),
    PlainSerializer(serialise_vec),
]


class Quiet(BaseModel):
    type_quiet: Literal[True] = True
    n_points: Vec3_int = Field(default=(0, 0, 0))
    ppc: int = Field(gt=0)
    """particles per cell, >0"""
