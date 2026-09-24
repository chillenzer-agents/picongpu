"""
SPDX-FileCopyrightText: 2024-2024 PIConGPU contributors, Brian Edward Marre
SPDX-License-Identifier: GPL-3.0-or-later
"""

from .ionizationcurrent import IonizationCurrent


class None_(IonizationCurrent):
    picongpu_name: str = "None"
