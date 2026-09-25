"""
This file is part of PIConGPU.
Copyright 2024-2024 PIConGPU contributors
Authors: Brian Edward Marre
License: GPLv3+
"""

from ..constant import Constant


class IonizationCurrent(Constant):
    """
    base class for all ionization current models

    The ionization current is the rate at which electrons are collected by
    the ion; it is a template argument of the ionizer in
    include/picongpu/param/speciesDefinition.param.
    """

    picongpu_name: str
    """C++ type name of the ionization current (e.g. "None")."""
