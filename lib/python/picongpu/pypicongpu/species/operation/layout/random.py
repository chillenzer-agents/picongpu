"""
This file is part of PIConGPU.
Copyright 2025 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

from typing import Literal

from pydantic import BaseModel, Field


class Random(BaseModel):
    type_random: Literal[True] = True
    ppc: int = Field(gt=0)
    """particles per cell (random layout), >0"""

    seed: int | None = Field(default=None)
    """seed of the pseudo-random number generator

    .. warning::

        Grouping discriminator only: the ``seed`` is never rendered into C++
        (no ``.param``/``include`` output references it), so a random layout with
        a ``seed`` produces byte-identical generated C++ to one without. It has
        no effect on the (shared, externally-seeded) device RNG stream and does
        not make positions reproducible. Its only role is equality: two
        equal-``ppc`` random layouts with different seeds are considered distinct
        (and therefore not merged / initialised independently).
    """
