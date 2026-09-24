"""
This file is part of PIConGPU.
Copyright 2024-2024 PIConGPU contributors
Authors: Brian Edward Marre
License: GPLv3+
"""

from .ionizationcurrent import IonizationCurrent


class None_(IonizationCurrent):
    """
    no ionization current (the ionization rate is computed without an
    explicit current model)

    C++ counterpart: the absence of a current template argument in
    include/picongpu/param/speciesDefinition.param.
    """

    picongpu_name: str = "None"
    """C++ type name of the (non-existent) ionization current."""
