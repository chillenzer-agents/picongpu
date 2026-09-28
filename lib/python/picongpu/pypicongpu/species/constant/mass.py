"""
This file is part of PIConGPU.
Copyright 2021-2024 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre
License: GPLv3+
"""

from typing import Annotated

from pydantic import Field

from ...units import Unit
from .constant import Constant


class Mass(Constant):
    """
    mass of a physical particle
    """

    mass_si: Annotated[float, Field(ge=0.0), Unit("kg")]
    """mass in kg of an individual particle"""
