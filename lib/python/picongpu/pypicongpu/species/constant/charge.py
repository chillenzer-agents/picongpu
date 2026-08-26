"""
SPDX-FileCopyrightText: 2021-2024 PIConGPU contributors, Hannes Troepgen, Brian Edward Marre
SPDX-License-Identifier: GPL-3.0-or-later
"""

from .constant import Constant


class Charge(Constant):
    """
    charge of a physical particle
    """

    charge_si: float
    """charge in C of an individual particle"""
