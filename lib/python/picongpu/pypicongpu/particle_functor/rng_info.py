"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

from typing import Annotated, Literal
from pydantic import BaseModel, BeforeValidator, computed_field

from picongpu.pypicongpu.particle_functor.translate_to_cpp_type import translate_to_cpp_type


class UniformRNGInfo(BaseModel):
    """
    uniform random number distribution for a particle functor

    C++ counterpart: pmacc::random::distributions::Uniform (rendered into
    include/picongpu/param/particleFilters.param).

    Units policy: dimensionless.
    """

    dist: Literal["uniform"] = "uniform"
    """tag field identifying the uniform distribution (discriminator)"""

    return_type: Annotated[str, BeforeValidator(translate_to_cpp_type)]
    """the C++ type of the generated random numbers (e.g. "float_X", "int")"""

    @computed_field
    def typename(self) -> str:
        return "pmacc::random::distributions::Uniform"


class NormalRNGInfo(BaseModel):
    """
    normal (Gaussian) random number distribution for a particle functor

    C++ counterpart: pmacc::random::distributions::Normal (rendered into
    include/picongpu/param/particleFilters.param).

    Units policy: see the return type.
    """

    dist: Literal["normal"] = "normal"
    """tag field identifying the normal distribution (discriminator)"""

    return_type: Annotated[str, BeforeValidator(translate_to_cpp_type)]
    """the C++ type of the generated random numbers (e.g. "float_X", "int")"""

    @computed_field
    def typename(self) -> str:
        return "pmacc::random::distributions::Normal"


RNGInfo = UniformRNGInfo | NormalRNGInfo
