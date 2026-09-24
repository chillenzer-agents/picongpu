"""
This file is part of PIConGPU.
Copyright 2021-2024 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre
License: GPLv3+
"""

from pydantic import BaseModel


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

    PIConGPU term: "particle attributes".

    C++ counterpart: the particle attribute types registered in
    include/picongpu/param/speciesDefinition.param.

    Units policy: attribute-specific (see the individual attributes).
    """

    picongpu_name: str
    """C++ type name of this attribute (e.g. "weighting"), rendered into the
    species particle typedef; must be a valid C++ identifier/typename."""
