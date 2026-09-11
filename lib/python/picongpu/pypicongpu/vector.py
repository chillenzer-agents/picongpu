"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz, opencode
License: GPLv3+

Shared vector (de-)serialisation helpers for pypicongpu pydantic models.

3-component vectors (``x``, ``y``, ``z``) are serialised into exactly one
canonical JSON shape -- an openPMD-style dict ``{"x": .., "y": .., "z": ..}``
-- produced by :func:`serialise_vec` and accepted back by :func:`deserialise_vec`
for round-tripping (``model_dump(mode="json")`` => ``model_validate``).

The same family of per-axis dict (de-)serialisers is provided for the grid
distribution (:func:`serialise_grid_dist` / :func:`deserialise_grid_dist`) and
the Huygens surface positions (:func:`serialise_huygens` /
:func:`deserialise_huygens`).
"""

from typing import Literal


def serialise_vec(value) -> dict:
    """serialise a 3-component vector ``(x, y, z)`` into an openPMD-style ``{x, y, z}`` dict"""
    return dict(zip("xyz", value))


def deserialise_vec(value):
    """inverse of :func:`serialise_vec`.

    Accepts the serialised ``{x, y, z}`` dict as well as any 3-element iterable
    (list, tuple, numpy array, ... -- as fed e.g. by PICMI), always returning a
    3-tuple.
    """
    if isinstance(value, dict):
        try:
            value = (value["x"], value["y"], value["z"])
        except KeyError as error:
            raise ValueError(f"Expected a vector with the keys x, y, z. You gave: {value=}.") from error
    if not isinstance(value, (list, tuple)):
        try:
            value = tuple(value)
        except (TypeError, ValueError) as error:
            raise TypeError(f"Expected a vector (iterable of length 3). You gave: {value=}.") from error
    if len(value) != 3:
        raise ValueError(f"Expected a vector of length 3. You gave: {value=}.")
    return tuple(value)


def serialise_grid_dist(
    value,
) -> None | dict[Literal["x", "y", "z"], list[dict[Literal["device_cells"], int]]]:
    """serialise a per-axis grid distribution into ``{"x": [{"device_cells": ..}, ..], ..}`` form"""
    return (
        value
        if value is None
        else {
            "x": [{"device_cells": x} for x in value[0]],
            "y": [{"device_cells": x} for x in value[1]],
            "z": [{"device_cells": x} for x in value[2]],
        }
    )


def deserialise_grid_dist(value):
    """inverse of :func:`serialise_grid_dist`; accepts the serialised dict or the native tuple-of-lists form."""
    if isinstance(value, dict):
        try:
            return tuple([entry["device_cells"] for entry in value[axis]] for axis in ("x", "y", "z"))
        except (KeyError, TypeError) as error:
            raise ValueError(f"Expected a serialised grid distribution. You gave: {value=}.") from error
    return value


def serialise_huygens(huygens_surface_positions) -> dict:
    """serialise the Huygens surface positions (3x2 list) into per-axis row dicts"""
    return {
        f"row_{axis}": {
            "negative": huygens_surface_positions[idx][0],
            "positive": huygens_surface_positions[idx][1],
        }
        for idx, axis in enumerate(("x", "y", "z"))
    }


def deserialise_huygens(value):
    """inverse of :func:`serialise_huygens`; accepts the serialised dict or the native 3x2 list form."""
    if isinstance(value, dict):
        try:
            return [[value[f"row_{axis}"]["negative"], value[f"row_{axis}"]["positive"]] for axis in ("x", "y", "z")]
        except (KeyError, TypeError) as error:
            raise ValueError(f"Expected a serialised huygens surface position. You gave: {value=}.") from error
    return value
