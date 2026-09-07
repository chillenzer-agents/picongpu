"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""


def validate_huygens_surface_positions(huygens_surface_positions, cell_cnt=None):
    """
    Check that the Huygens surface positions of an incident-field laser are well-formed.

    The Huygens surface is given as one ``[min, max]`` pair of cell indices per axis
    (x, y, z). A positive value counts cells in from the low/left edge. A negative
    value on the *max* side is interpreted as distance from the high/right edge, i.e.
    as the absolute coordinate ``cell_cnt + max``; a positive value on the *max* side
    is the absolute coordinate and hence the user is responsible for the grid-size
    arithmetic.

    With ``cell_cnt`` (the global number of cells per axis) given, this also checks
    that both surfaces lie inside the global domain and do not overlap ("insufficient
    dimension"). Without it, only the structural checks are performed.

    :param huygens_surface_positions: 3-element list of ``[min, max]`` integer pairs
    :param cell_cnt: optional 3-element tuple of ints, the global cell counts per axis
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

        # a non-negative max is expressed as an absolute coordinate and hence must
        # already be larger than the corresponding min position
        absolute_max = maximum if maximum >= 0 else None
        if absolute_max is not None and absolute_max <= minimum:
            raise ValueError(
                f"The Huygens surface max position for axis {axis} is given as an absolute coordinate "
                "and must lie inside the domain beyond the min position. "
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
            if max_coordinate >= size or max_coordinate <= minimum:
                raise ValueError(
                    f"The Huygens surface for axis {axis} does not fit inside the global domain, "
                    f"which has {size} cells in that axis: the surfaces must be inside the domain "
                    "and must not overlap (insufficient dimension). "
                    f"You gave: {minimum=} and {maximum=}."
                )

    return huygens_surface_positions
