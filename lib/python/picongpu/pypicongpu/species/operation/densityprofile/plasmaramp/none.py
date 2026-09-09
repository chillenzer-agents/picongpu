"""
This file is part of PIConGPU.
Copyright 2023-2025 PIConGPU contributors
Authors: Kristin Tippey, Brian Edward Marre, Julian Lenz
License: GPLv3+
"""

from typing import Literal

from pydantic import BaseModel


class None_(BaseModel):  # noqa: N801 (intentional: the "None" plasma ramp, mirrors the C++ "None" value)
    """no plasma ramp, either up or down"""

    type_none: Literal[True] = True
