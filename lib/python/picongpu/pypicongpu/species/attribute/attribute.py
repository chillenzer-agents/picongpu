"""
This file is part of PIConGPU.
Copyright 2021-2024 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre
License: GPLv3+
"""

from functools import partial
from typing import Annotated

from pydantic import AfterValidator, BaseModel

from picongpu.pypicongpu.validation import validate_cpp_identifier


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
    """

    picongpu_name: Annotated[str, AfterValidator(partial(validate_cpp_identifier, field="picongpu_name"))]
    """C++ Code implementing this attribute"""
