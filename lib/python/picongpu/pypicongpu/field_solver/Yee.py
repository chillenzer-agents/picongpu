"""
This file is part of PIConGPU.
Copyright 2021-2025 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre, Julian Lenz
License: GPLv3+
"""

from typing import Literal

from pydantic import BaseModel, computed_field
from ..rendering import RenderedObject


class YeeSolver(RenderedObject, BaseModel):
    """
    Yee solver as defined by PIConGPU

    note: has no parameters
    """

    type_yee: Literal[True] = True
    """tag field identifying the yee solver (discriminator for the AnySolver
    union; rendered nowhere, so it does not change the generated c++ code)"""

    @computed_field
    def name(self) -> str:
        return "Yee"
