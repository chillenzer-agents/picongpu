"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: chillenzer-agents
License: GPLv3+
"""

from unittest import TestCase

import pytest
from pydantic import ValidationError

from picongpu.pypicongpu.grid import BoundaryCondition, Grid2D, Grid3D, grid_dist_validate


class TestGridDistValidate(TestCase):
    """Focused tests for grid_dist_validate on the raw pypicongpu construction path."""

    GRID3D_KWARGS = dict(
        cell_size_si=(1.0, 1.0, 1.0),
        cell_cnt=(192, 2048, 12),
        boundary_condition=(BoundaryCondition.ABSORBING, BoundaryCondition.ABSORBING, BoundaryCondition.PERIODIC),
        n_gpus=(1, 1, 1),
        super_cell_size=(8, 8, 4),
    )

    GRID2D_KWARGS = dict(
        cell_size_si=(1.0, 1.0),
        cell_depth_si=1.0,
        cell_cnt=(192, 2048),
        boundary_condition=(BoundaryCondition.ABSORBING, BoundaryCondition.ABSORBING),
        n_gpus=(1, 1),
        super_cell_size=(8, 8),
    )

    def test_empty_axis_raises_value_error(self):
        """An empty axis must raise an explicit ValueError instead of falling through to None."""
        with pytest.raises(ValidationError, match="empty"):
            Grid3D(grid_dist=([], [], []), **self.GRID3D_KWARGS)

    def test_empty_outer_container_raises_value_error(self):
        """An empty outer container is rejected directly (unreachable through the models)."""
        with pytest.raises(ValueError, match="empty"):
            grid_dist_validate(())

    def test_single_empty_axis_raises_value_error(self):
        with pytest.raises(ValidationError, match="empty"):
            Grid3D(grid_dist=([192], [], [12]), **self.GRID3D_KWARGS)

    def test_all_zero_raises_value_error(self):
        """All-zero input must raise the all_gt ValueError."""
        with pytest.raises(ValidationError, match="contains values <="):
            Grid3D(grid_dist=([0], [0], [0]), **self.GRID3D_KWARGS)

    def test_2d_empty_axis_raises_value_error(self):
        with pytest.raises(ValidationError) as exc_info:
            Grid2D(grid_dist=([], []), **self.GRID2D_KWARGS)
        assert exc_info.value.error_count() == 1
        (error,) = exc_info.value.errors()
        assert error["loc"] == ("grid_dist",)
        assert error["type"] == "value_error"
        assert "empty" in error["msg"]

    def test_2d_single_empty_axis_raises_value_error(self):
        with pytest.raises(ValidationError, match="empty"):
            Grid2D(grid_dist=([192], []), **self.GRID2D_KWARGS)

    def test_valid_distribution_kept(self):
        grid = Grid3D(grid_dist=([192], [2048], [12]), **self.GRID3D_KWARGS)
        assert grid.grid_dist == ([192], [2048], [12])

    def test_2d_valid_distribution_kept(self):
        grid = Grid2D(grid_dist=([192], [2048]), **self.GRID2D_KWARGS)
        assert grid.grid_dist == ([192], [2048])

    def test_valid_distribution_still_validated(self):
        """Downstream sum check still runs after the validator returns the distribution."""
        with pytest.raises(ValidationError, match="sum of grid_dists in x must be equal to number_of_cells"):
            Grid3D(grid_dist=([100, 64], [2048], [12]), **self.GRID3D_KWARGS)
