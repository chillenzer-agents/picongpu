"""
This file is part of PIConGPU.
Copyright 2021-2024 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre
License: GPLv3+
"""

from pydantic import BaseModel, Field


class Attribute(BaseModel):
    """
    attribute of a species

    Property of individual macroparticles (i.e. can be different from
    macroparticle to macroparticle).
    Can change over time (not relevant for initialization here).

    Owned by exactly one species.

    Set by exactly one operation (an operation may define multiple attributes
    even across multiple species though).

    Identified by its PIConGPU name.

    PIConGPU term: "particle attributes"

    Besides the C++ name used to register the attribute on a species, the
    metadata below mirrors the mandatory traits from
    ``include/picongpu/unitless/speciesAttributes.unitless``.  They make this
    class the authoritative Python description of the predefined particle
    attributes, used by the particle-functor registry to derive return types,
    units and weighting scaling.
    """

    picongpu_name: str
    """C++ Code implementing this attribute"""

    cpp_type: str = Field(default="float_X", exclude=True)
    """C++ value type of one component of the attribute"""

    n_components: int = Field(default=1, exclude=True)
    """number of value components (1 for scalars, 3 for the usual vectors)"""

    unit_dimension: tuple[float, float, float, float, float, float, float] = Field(default=(0.0,) * 7, exclude=True)
    """powers of the seven SI base units (L, M, T, I, theta, N, J)"""

    unit: str = Field(default="1.", exclude=True)
    """C++ expression for the SI value of one internal unit (``getUnit()``)"""

    macro_weighted: bool = Field(default=False, exclude=True)
    """whether the stored value is macro-particle weighted (``MacroWeighted``)"""

    weighting_power: int = Field(default=0, exclude=True)
    """power of the weighting the stored value scales with (``WeightingPower``)"""

    physical_weighting_power: int | None = Field(default=None, exclude=True)
    """rescale exponent for ``PhysicalParticle`` access, if it differs from ``weighting_power``

    ``weighting_power`` mirrors the C++ ``WeightingPower`` trait.  For a few
    attributes that trait describes the macro-particle bookkeeping rather than
    the single-particle meaning used by ``PhysicalParticle`` functors (for
    example ``weighting`` must not be divided by itself).  Those entries set
    this override explicitly; ``None`` means "use ``weighting_power``".
    """

    access_strategy: str = Field(default="structured_binding", exclude=True)
    """how the preamble binds the stored value

    ``"structured_binding"`` (default) emits ``auto const [a, b, ...] = value;``
    and therefore requires the C++ type to support the tuple protocol (e.g.
    ``pmacc::math::Vector``).  ``"whole"`` emits a single
    ``auto const name = value;`` and indexes it in the functor expression
    (``name[0]``, ...), which also works for types without a tuple protocol
    such as ``DataSpace<simDim>``.
    """

    internal: bool = Field(default=False, exclude=True)
    """implementation detail rather than a first-class user-facing quantity"""

    @property
    def stored_identifier(self) -> str:
        """the identifier as stored in ``speciesAttributes.param``

        ``position`` is registered through the alias-based
        ``position<position_pic>`` expression, but the stored
        ``value_identifier`` is ``position_pic``.
        """
        if "<" in self.picongpu_name and self.picongpu_name.endswith(">"):
            return self.picongpu_name.split("<", 1)[1][:-1]
        return self.picongpu_name

    @property
    def component_cpp_type(self) -> str:
        """C++ type of one component when the whole attribute is a vector"""
        if self.n_components == 1:
            return self.cpp_type
        if self.cpp_type.startswith("float"):
            return "float_X"
        if self.cpp_type.startswith("DataSpace"):
            return "int"
        return self.cpp_type
