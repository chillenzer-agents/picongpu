"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""


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
