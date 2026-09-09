"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: PIConGPU AI Agent (TT-20)
License: GPLv3+
"""

import pytest
from picongpu.pypicongpu.validation import validate_huygens_against_absorber

_DEFAULT_THICKNESS = ((12, 12), (12, 12), (12, 12))
_DEFAULT_POSITIONS = [[16, -16], [16, -16], [16, -16]]


def test_default_absorber_reproduces_cpp_threshold():
    """with the C++ NUM_CELLS=12 default (Yee/order-2 margin 1) the required offset is exactly 12"""
    # exactly at the threshold is fine
    validate_huygens_against_absorber([[12, -12], [12, -12], [12, -12]], _DEFAULT_THICKNESS)
    # one cell too close raises
    with pytest.raises(ValueError, match=".*at least 12 cells away.*"):
        validate_huygens_against_absorber([[11, -12], [12, -12], [12, -12]], _DEFAULT_THICKNESS)
    with pytest.raises(ValueError, match=".*at least 12 cells away.*"):
        validate_huygens_against_absorber([[12, -11], [12, -12], [12, -12]], _DEFAULT_THICKNESS)


def test_zero_positions_raise():
    """surfaces on the boundary itself are rejected"""
    with pytest.raises(ValueError):
        validate_huygens_against_absorber([[0, 0], [0, 0], [0, 0]], _DEFAULT_THICKNESS)


def test_non_default_absorber_changes_threshold():
    """a non-default TT-19 thickness (32) raises for positions that are fine for the default (12)"""
    thickness = ((32, 32), (32, 32), (32, 32))
    with pytest.raises(ValueError, match=".*at least 32 cells away.*"):
        validate_huygens_against_absorber(_DEFAULT_POSITIONS, thickness)
    # exactly at the non-default threshold is fine
    validate_huygens_against_absorber([[32, -32], [32, -32], [32, -32]], thickness)


def test_asymmetric_thickness_per_axis_and_boundary():
    """thickness is honoured per axis and per boundary"""
    thickness = ((13, 4), (0, 12), (32, 32))
    # z is absorbing with 32: the 16-cell default positions are too close there
    with pytest.raises(ValueError, match=".*axis 'z'.*at least 32 cells away.*is only 16.*"):
        validate_huygens_against_absorber([[13, -4], [4, -12], [16, -16]], thickness)
    # all positions exactly matching their (asymmetric) thickness are fine
    validate_huygens_against_absorber([[13, -4], [4, -12], [32, -32]], thickness)


def test_moving_window_exempts_ymax():
    """with the moving window enabled, the YMax boundary is exempt, other boundaries still checked"""
    # y min too close -> raises, both with and without the moving window
    with pytest.raises(ValueError, match=".*axis 'y'.*'min'.*"):
        validate_huygens_against_absorber([[16, -16], [1, -1], [16, -16]], _DEFAULT_THICKNESS)
    with pytest.raises(ValueError, match=".*axis 'y'.*'min'.*"):
        validate_huygens_against_absorber([[16, -16], [1, -1], [16, -16]], _DEFAULT_THICKNESS, moving_window=True)
    # only y max is too close -> exempt, no raise
    validate_huygens_against_absorber([[16, -16], [16, -1], [16, -16]], _DEFAULT_THICKNESS, moving_window=True)


def test_all_violations_aggregated():
    """all violating axis/boundary pairs are collected into one error message"""
    with pytest.raises(ValueError) as excinfo:
        # x min and z max too close, y fine
        validate_huygens_against_absorber([[4, -16], [16, -16], [16, -4]], _DEFAULT_THICKNESS)
    message = str(excinfo.value)
    assert "axis 'x' at the 'min' boundary" in message
    assert "axis 'z' at the 'max' boundary" in message
    assert "axis 'y'" not in message


def test_periodic_axis_exempt_from_check():
    """a periodic axis carries no absorber (thickness zeroed like C++ getGlobalThickness), so it is exempt"""
    positions = [[16, -16], [16, -16], [1, -1]]
    # without the periodic flag the default 12-cell threshold rejects the z boundary surfaces
    with pytest.raises(ValueError, match="is only 1 cells away"):
        validate_huygens_against_absorber(positions, _DEFAULT_THICKNESS)
    # flagging z as periodic zeroes its threshold -> passes
    validate_huygens_against_absorber(positions, _DEFAULT_THICKNESS, is_periodic=(False, False, True))
    # the flag is per-axis: flagging x instead still leaves z checked
    with pytest.raises(ValueError, match=".*axis 'z' at the 'min' boundary.*"):
        validate_huygens_against_absorber(positions, _DEFAULT_THICKNESS, is_periodic=(True, False, False))


def test_positive_max_computed_as_size_minus_position():
    """a positive (absolute) max position is a distance of size - position from the max edge,
    mirroring the C++ Solver.hpp checkRequirements (review finding 2)"""
    # 112 on a 128-cell axis sits 16 cells from the max edge and passes the default threshold
    validate_huygens_against_absorber([[16, 112], [16, -16], [16, -16]], _DEFAULT_THICKNESS, grid_size=(128, 128, 128))
    # 125 on a 128-cell axis is only 3 cells away, reported as a positive actual distance
    with pytest.raises(ValueError, match=".*at least 12 cells away, but is only 3 cells away"):
        validate_huygens_against_absorber(
            [[16, 125], [16, -16], [16, -16]], _DEFAULT_THICKNESS, grid_size=(128, 128, 128)
        )


def test_positive_max_requires_grid_size():
    """an absolute max coordinate cannot be distance-checked without the global grid size"""
    with pytest.raises(ValueError, match="grid_size"):
        validate_huygens_against_absorber([[16, 112], [16, -16], [16, -16]], _DEFAULT_THICKNESS)
