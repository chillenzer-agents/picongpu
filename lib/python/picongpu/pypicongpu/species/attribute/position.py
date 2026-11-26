"""
This file is part of PIConGPU.
Copyright 2021-2024 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre
License: GPLv3+
"""

from .attribute import Attribute


class Position(Attribute):
    """
    Position of a macroparticle

    ``unit_dimension`` and ``unit`` mirror the C++ traits of the *stored*
    ``position<T>`` value (``UnitDimension``/``Unit`` in
    ``speciesAttributes.unitless``): length, with a per-axis SI factor.  A
    ``getUnit()`` expression is a scalar, so a functor access cannot use this
    directly; its per-access units (``cell``/``si``/``pic``) are defined in
    ``picmi.particle_functor._POSITION_UNIT_METADATA``.  Keep both in sync:
    this class describes the stored value, the map the functor view.
    """

    picongpu_name: str = "position<position_pic>"
    cpp_type: str = "floatD_X"
    n_components: int = 3
    # UnitDimension<position<T>>: length (L).
    unit_dimension: tuple = (1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    # Unit<position<T>>: per-axis SI factor (anisotropic cell size); not a
    # scalar getUnit() expression, see the docstring and the picmi-side map.
    unit: str = "sim.pic.getCellSize() * sim.unit.length()"
