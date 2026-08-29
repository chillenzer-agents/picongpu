"""
This file is part of PIConGPU.
Copyright 2025 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

from . import plasmaramp
from .cylinder import Cylinder
from .foil import Foil
from .free_formula import FreeFormula
from .gaussian import Gaussian
from .uniform import Uniform

AnyDensityProfile = Uniform | Foil | Gaussian | FreeFormula | Cylinder

__all__ = [
    "AnyDensityProfile",
    "Uniform",
    "Foil",
    "plasmaramp",
    "Gaussian",
    "FreeFormula",
    "Cylinder",
]
