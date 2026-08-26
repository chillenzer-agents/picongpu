"""
SPDX-FileCopyrightText: 2021-2024 PIConGPU contributors, Hannes Troepgen, Brian Edward Marre
SPDX-License-Identifier: GPL-3.0-or-later
"""

from .attribute import Attribute


class BoundElectrons(Attribute):
    """
    Number of bound electrons per nucleus of a macroparticle
    """

    picongpu_name: str = "boundElectrons"
