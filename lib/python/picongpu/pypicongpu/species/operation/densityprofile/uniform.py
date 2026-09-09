"""
This file is part of PIConGPU.
Copyright 2021-2025 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre, Julian Lenz
License: GPLv3+
"""

from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, Field

_axes = ("x", "y", "z")


def _is_named_value(value) -> bool:
    """``{'value': ...}`` mapping, as used by the render-safe bound form."""
    return isinstance(value, dict) and set(value.keys()) == {"value"}


def _validate_bound_dict(value: dict) -> None:
    """Reject bounds with unknown/missing axes or malformed axis entries."""
    unknown = set(value.keys()) - set(_axes)
    if unknown:
        msg = "unknown axis in bound: {}, expected {}".format(
            sorted(unknown),
            list(_axes),
        )
        raise ValueError(msg)

    missing = set(_axes) - set(value.keys())
    if missing:
        msg = "missing axis in bound: {}, expected {}".format(
            sorted(missing),
            list(_axes),
        )
        raise ValueError(msg)

    for axis, axis_value in value.items():
        if not _is_named_value(axis_value):
            msg = "malformed value for axis {!r}: {!r}".format(
                axis,
                axis_value,
            )
            raise ValueError(msg)


def _bound_from_tuple(value) -> dict | None:
    """
    Convert a 3-component bound ``(lower|upper)`` into the render-safe dict
    form.

    ``None`` means "unbounded" (on the axis-level: *all* axes are unbounded;
    within a 3-component bound, an axis with value ``None`` is unbounded).

    Note: the dict-of-dicts form (``{"x": {"value": ...}, ...}``) is used
    because the rendering context rejects plain tuples/lists and the form
    round-trips losslessly through ``model_dump`` (needed for serialization).
    """
    if value is None:
        return None

    if isinstance(value, dict):
        _validate_bound_dict(value)
        return value

    if len(value) != 3:
        msg = "bound must have exactly 3 components, got: {!r}".format(value)
        raise ValueError(msg)

    components = zip(_axes, value)
    return {axis: {"value": component} for axis, component in components}


class Uniform(BaseModel):
    """
    globally constant density

    PIConGPU equivalent is the homogenous profile, but due to spelling
    ambiguities the PICMI name uniform is followed here.
    """

    type_uniform: Literal[True] = True

    density_si: float = Field(gt=0.0)
    """density at every point in space (kg * m^-3)"""

    lower_bound: Annotated[
        dict[str, dict[str, float | None]] | None,
        BeforeValidator(_bound_from_tuple),
    ] = Field(
        default=None,
        description=(
            "requested lower bound of the sub-volume; None axis = unbounded "
            "Python-side only: carried over to the render context; not yet "
            "honoured by the C++ homogeneous profile (see @todo)."
        ),
    )
    """requested lower bound of the sub-volume (m); None axis = unbounded.

    Python-side only: carried into the rendering context, but not yet honoured
    by the C++ homogeneous profile (see ``@todo respect bounding box``).
    """

    upper_bound: Annotated[
        dict[str, dict[str, float | None]] | None,
        BeforeValidator(_bound_from_tuple),
    ] = Field(
        default=None,
        description=(
            "requested upper bound of the sub-volume; None axis = unbounded "
            "Python-side only: carried over to the render context; not yet "
            "honoured by the C++ homogeneous profile (see @todo)."
        ),
    )
    """requested upper bound of the sub-volume (m); None axis = unbounded.

    Python-side only: carried into the rendering context, but not yet honoured
    by the C++ homogeneous profile (see ``@todo respect bounding box``).
    """

    fill_in: bool | None = Field(
        default=None,
        description=(
            "requested to refill the sub-volume exposed by a moving window; "
            "Python-side only (rendered as docs); not yet honoured by the C++ "
            "homogeneous profile (see @todo)."
        ),
    )
    """requested to refill the sub-volume newly exposed by a moving window.

    Python-side only: rendered as documentation, but not yet honoured by the
    C++ homogeneous profile (see ``@todo respect bounding box``).
    """
