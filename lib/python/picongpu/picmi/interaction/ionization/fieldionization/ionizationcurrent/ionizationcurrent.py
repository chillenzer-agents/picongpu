"""
SPDX-FileCopyrightText: 2024-2024 PIConGPU contributors, Brian Edward Marre
SPDX-License-Identifier: GPL-3.0-or-later
"""

from pydantic import BaseModel


class IonizationCurrent(BaseModel):
    """common interface of all ionization current models"""

    MODEL_NAME: str
