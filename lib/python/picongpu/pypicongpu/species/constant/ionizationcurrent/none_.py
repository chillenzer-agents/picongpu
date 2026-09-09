"""
This file is part of PIConGPU.
Copyright 2024-2024 PIConGPU contributors
Authors: Brian Edward Marre
License: GPLv3+
"""

from .ionizationcurrent import IonizationCurrent


class None_(IonizationCurrent):  # noqa: N801 (intentional: the "None" ionization current, mirrors the C++ "None" value)
    picongpu_name: str = "None"
