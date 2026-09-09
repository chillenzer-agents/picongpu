"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

from collections.abc import Iterable
from typing import TypeVar

T = TypeVar("T")


def validate_huygens_surface_positions(huygens_surface_positions, cell_cnt=None, moving_window_enabled=False):
    """
    Check that the Huygens surface positions of an incident-field laser are well-formed.

    The Huygens surface is given as one ``[min, max]`` pair of cell indices per axis
    (x, y, z). A positive value counts cells in from the low/left edge. A negative
    value on the *max* side is interpreted as distance from the high/right edge, i.e.
    as the absolute coordinate ``cell_cnt + max``; a positive value on the *max* side
    is the absolute coordinate and hence the user is responsible for the grid-size
    arithmetic.

    With ``cell_cnt`` (the global number of cells per axis) given, this also checks
    that both surfaces lie inside the global domain and that the bounded volume is
    non-degenerate, i.e. spans at least 2 cells (mirroring the C++ ``checkPositioning``
    in ``Solver.hpp``). For moving-window simulations the YMax side is exempt from the
    inside-the-domain requirement, matching the C++ ``skipMaxCheck``.

    Without ``cell_cnt``, only the structural checks are performed.

    :param huygens_surface_positions: 3-element list of ``[min, max]`` integer pairs
    :param cell_cnt: optional 3-element tuple of ints, the global cell counts per axis
    :param moving_window_enabled: whether a moving window is active; if so the YMax
        (axis 1, max side) surface may be located outside the initially simulated volume
    :raise ValueError: if any of the checks fail
    :return: ``huygens_surface_positions`` unchanged
    """
    if not isinstance(huygens_surface_positions, (list, tuple)) or len(huygens_surface_positions) != 3:
        raise ValueError(
            "Huygens surface positions must be a list of exactly 3 [min, max] integer pairs, "
            "one for each of the axes x, y and z. "
            f"You gave: {huygens_surface_positions=}."
        )

    if cell_cnt is not None and len(cell_cnt) != 3:
        raise ValueError(
            f"The global cell count must have exactly 3 entries (one per axis x, y, z). You gave: {cell_cnt=}."
        )

    for axis in range(3):
        pair = huygens_surface_positions[axis]
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValueError(
                f"The Huygens surface position for axis {axis} must be a pair [min, max] of integers. "
                f"You gave: {pair=}."
            )
        minimum, maximum = pair
        for name, value in (("min", minimum), ("max", maximum)):
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(
                    f"The Huygens surface {name} position for axis {axis} must be an integer. You gave: {value=}."
                )

        if minimum <= 0:
            raise ValueError(
                f"The Huygens surface min position for axis {axis} must be > 0 "
                "(distance in cells from the low/left edge of the domain). "
                f"You gave: {minimum=}."
            )

        # a non-negative max is expressed as an absolute coordinate and hence must already be far
        # enough away from the corresponding min position to yield a non-degenerate volume with a
        # span of at least 2 cells (as required for a Fittable volume by the C++ checkPositioning)
        absolute_max = maximum if maximum >= 0 else None
        if absolute_max is not None and absolute_max <= minimum + 1:
            raise ValueError(
                f"The Huygens surface max position for axis {axis} is given as an absolute coordinate "
                "and must lie inside the domain beyond the min position, spanning at least 2 cells "
                "(a span of 1 would make the Huygens surface degenerate/crossing). "
                f"You gave: {minimum=} and {absolute_max=}."
            )

        if cell_cnt is not None:
            size = cell_cnt[axis]
            if minimum >= size:
                raise ValueError(
                    f"The Huygens surface min position for axis {axis} lies outside the global domain, "
                    f"which has {size} cells in that axis. You gave: {minimum=}."
                )
            max_coordinate = (size + maximum) if maximum < 0 else maximum
            # For moving-window simulations, the YMax surface may be located outside the initially
            # simulated volume (mirrors the C++ skipMaxCheck in Solver.hpp::checkPositioning)
            max_outside_allowed = (axis == 1) and moving_window_enabled
            if not max_outside_allowed and max_coordinate >= size:
                raise ValueError(
                    f"The Huygens surface max position for axis {axis} lies outside the global domain, "
                    f"which has {size} cells in that axis. You gave: {minimum=} and {maximum=} "
                    f"(absolute max position {max_coordinate})."
                )
            # C++ requires the volume bounded by the Huygens surface to be non-zero, i.e. its span
            # (distance between the min and max surfaces) must be at least 2 cells (Solver.hpp, checkPositioning)
            if max_coordinate < minimum + 2:
                raise ValueError(
                    f"The Huygens surface for axis {axis} does not fit into the global domain, "
                    f"which has {size} cells in that axis, with a non-degenerate span of at least 2 cells "
                    "(insufficient dimension; a span of 1 would make the surfaces cross). "
                    f"You gave: {minimum=} and {maximum=} (absolute max position {max_coordinate})."
                )

    return huygens_surface_positions


def validate_all_ge(values: Iterable | T, threshold: float | int, *, field: str) -> Iterable | T:
    """
    Check that every scalar in the iterable is greater than or equal to threshold, or return the scalar unchanged.

    Passes a non-iterable through untouched so that the same helper can wrap scalar fields.

    :param values: iterable of numbers or a single number
    :param threshold: inclusive lower bound
    :param field: name of the validated field, used in the error message
    :raise ValueError: if any element is smaller than threshold
    :return: the input unchanged
    """
    if isinstance(values, Iterable):
        if wrong := [x for x in values if x < threshold]:
            message = (
                f"{field=} contains values < {threshold=}, which is not allowed. The offending values are {wrong=}."
            )
            raise ValueError(message)
    return values


def validate_nested_3x2_shape(values, *, field: str):
    """
    Check that the given nested structure has the shape [3][2].

    Intended to mirror the C++ ``constexpr T[NUM_CELLS[3][2]]`` (.param) grids,
    i.e. three axes, each with an (negative, positive) boundary pair.

    :param values: nested iterable of shape [3][2]
    :param field: name of the validated field, used in the error message
    :raise ValueError: if the structure does not have shape [3][2]
    :return: the input unchanged
    """
    try:
        flattened = [values[axis][boundary] for axis in range(3) for boundary in range(2)]
    except (IndexError, TypeError) as error:
        raise ValueError(f"{field=} must have shape [3][2], but got {values=}.") from error
    return flattened


def validate_absorber_matrix(values, *, field: str):
    """
    Validate a per-axis x per-boundary "[3][2]" matrix, mirroring NUM_CELLS / exponential::STRENGTH.

    Every entry must be present and (for NUM_CELLS thickness) greater than or equal to 0; the
    STRENGTH of the exponential absorber is bounded from below by 0 as well.

    :param values: nested structure of shape [3][2]
    :param field: name of the validated field, used in the error message
    :raise ValueError: on wrong shape or negative entries
    :return: the input unchanged
    """
    validate_nested_3x2_shape(values, field=field)
    for axis in values:
        validate_all_ge(axis, 0, field=field)
    return values


_AXIS_NAMES = ("x", "y", "z")
_BOUNDARY_NAMES = ("min", "max")


def validate_huygens_against_absorber(
    positions,
    absorber_thickness_by_axis_boundary,
    solver_margin: int = 1,
    moving_window: bool = False,
    grid_size: Iterable[int] | None = None,
    is_periodic: Iterable[bool] | None = None,
):
    """
    Check that a Huygens surface is far enough away from each global-domain boundary.

    Mirrors the C++ run-time check in include/picongpu/fields/incidentField/Solver.hpp
    (checkRequirements): for every axis d and boundary b the distance of the Huygens
    surface from the respective global-domain boundary must be at least

        absorber_thickness(d, b) + solver_margin - 1

    cells, where ``solver_margin`` is the field solver's ``FDTD_spatial_order / 2``
    (Yee/order-2 ``=> 1``, i.e. the required offset equals the absorber thickness alone).

    Positions use the C++ convention: the ``min`` (negative boundary) entry is the
    distance in cells from the min edge of the global domain. The ``max`` (positive
    boundary) entry is negative and its magnitude is the distance from the max edge
    (``-positions[d][1]``); a *positive* ``max`` entry is an absolute coordinate and
    its distance from the max edge is ``grid_size[d] - positions[d][1]``, mirroring
    the C++ ``else if(POSITION[axis][boundaryIdx] > 0) offset = size - POSITION`` case.

    Periodically connected axes carry no absorber: mirroring the C++
    ``fields::absorber::Absorber::getGlobalThickness()`` (which zeroes the thickness on
    periodic axes), axes flagged via ``is_periodic`` have their thickness zeroed and are
    hence exempt from the distance check.

    The YMax boundary (positive y) is exempt from the check when the moving window is
    enabled, as in the C++ check.

    :param positions: Huygens surface positions, shape [3][2] (axis x/y/z, boundary min/max)
    :param absorber_thickness_by_axis_boundary: absorber thickness per (axis, boundary), shape [3][2]
    :param solver_margin: FDTD_spatial_order / 2 of the field solver (default 1 for Yee)
    :param moving_window: whether the moving window is enabled (exempts YMax)
    :param grid_size: global cell count per axis, required to interpret a positive
                      (absolute) max position as a distance from the max edge
    :param is_periodic: per-axis periodic flags; periodic axes are exempt from the check
    :raise ValueError: if any (axis, boundary) is too close to the boundary; all violations
                       are collected into a single error message
    """
    validate_nested_3x2_shape(positions, field="huygens_surface_positions")
    validate_nested_3x2_shape(absorber_thickness_by_axis_boundary, field="absorber_thickness")
    if grid_size is not None and len(grid_size) != 3:
        raise ValueError(f"The global cell count must have exactly 3 entries (one per axis). You gave: {grid_size=}.")
    thickness = [list(pair) for pair in absorber_thickness_by_axis_boundary]
    if is_periodic is not None:
        for axis, periodic in enumerate(is_periodic):
            if periodic:
                thickness[axis][0] = 0
                thickness[axis][1] = 0
    violations = []
    for axis in range(3):
        for boundary in range(2):
            if moving_window and axis == 1 and boundary == 1:
                continue
            required = thickness[axis][boundary] + solver_margin - 1
            if boundary == 0:
                distance = positions[axis][0]
            else:
                maximum = positions[axis][1]
                if maximum > 0:
                    if grid_size is None:
                        raise ValueError(
                            "A positive (absolute) max position needs the global grid_size to compute the "
                            "distance from the max boundary. You gave grid_size=None with "
                            f"huygens_surface_positions[{axis}][1]={maximum}."
                        )
                    distance = grid_size[axis] - maximum
                else:
                    distance = -maximum
            if distance < required:
                violations.append(
                    f"axis '{_AXIS_NAMES[axis]}' at the '{_BOUNDARY_NAMES[boundary]}' boundary must be "
                    f"at least {required} cells away, but is only {distance} cells away"
                )
    if violations:
        raise ValueError(
            "Huygens surface too close to a global-domain boundary for the used field solver and absorber: "
            + "; ".join(violations)
        )
    return positions
