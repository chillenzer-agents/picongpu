"""
This file is part of PIConGPU.
Copyright 2025 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from ....rendering.pmaccprinter import serialise_expression


class FreeFormula(BaseModel):
    """
    free-form density profile given as a C++ expression

    The expression is evaluated per cell and must return the local number
    density.

    C++ counterpart: the free formula (user-defined) profile template in
    include/picongpu/param/density.param.

    Units policy: the expression must evaluate to a number density, [m^-3].
    """

    # accept both the field name (as produced by model_dump) and the alias
    # (density_expression) upon construction, so that serialised output can be
    # validated again (round-trip safety)
    model_config = ConfigDict(populate_by_name=True)

    type_freeformula: Literal[True] = True
    """discriminator for the AnyDensityProfile union."""

    function_body: Annotated[str, BeforeValidator(serialise_expression)] = Field(alias="density_expression")
    """C++ expression computing the local number density, [m^-3] (sympy expression or string)."""
