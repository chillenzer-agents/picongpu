"""
SPDX-FileCopyrightText: 2023-2025 PIConGPU contributors, Kristin Tippey, Brian Edward Marre, Julian Lenz
SPDX-License-Identifier: GPL-3.0-or-later
"""

from typing import Literal
from pydantic import BaseModel


class None_(BaseModel):
    """no plasma ramp, either up or down"""

    type_none: Literal[True] = True
