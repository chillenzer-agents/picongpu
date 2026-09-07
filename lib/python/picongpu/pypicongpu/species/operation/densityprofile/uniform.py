"""
This file is part of PIConGPU.
Copyright 2021-2025 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre, Julian Lenz
License: GPLv3+
"""

from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, Field

_axes = ("x", "y", "z")


def _bound_from_tuple(value) -> dict | None:
    """
    Convert a 3-component bound ``(lower|upper)`` into the render-safe dict form.

    ``None`` means "unbounded" (on the axis-level: *all* axes are unbounded;
    within a 3-component bound, an axis with value ``None`` is unbounded).
    """
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if len(value) != 3:
        raise ValueError(f"bound must have exactly 3 components, got: {value!r}")
    return {axis: {"value": component} for axis, component in zip(_axes, value)}


class Uniform(BaseModel):
    """
    globally constant density

    PIConGPU equivalent is the homogenous profile, but due to spelling
    ambiguities the PICMI name uniform is followed here.
    """

    type_uniform: Literal[True] = True

    density_si: float = Field(gt=0.0)
    """density at every point in space (kg * m^-3)"""

    lower_bound: Annotated[dict[str, dict[str, float | None]] | None, BeforeValidator(_bound_from_tuple)] = Field(
        default=None,
        description="lower bound of the sub-volume in which the density is placed (m), None axis = unbounded",
    )
    """lower bound of the sub-volume in which the density is placed (m), None axis = unbounded"""

    upper_bound: Annotated[dict[str, dict[str, float | None]] | None, BeforeValidator(_bound_from_tuple)] = Field(
        default=None,
        description="upper bound of the sub-volume in which the density is placed (m), None axis = unbounded",
    )
    """upper bound of the sub-volume in which the density is placed (m), None axis = unbounded"""

    fill_in: bool | None = Field(
        default=None,
        description="continue the density into the sub-volume exposed by a moving simulation window",
    )
    """continue the density into the sub-volume exposed by a moving simulation window"""
