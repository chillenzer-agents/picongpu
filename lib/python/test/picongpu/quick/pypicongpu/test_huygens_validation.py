"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

import pytest

from picongpu.pypicongpu import laser
from picongpu.pypicongpu.validation import validate_huygens_surface_positions


class TestValidateHuygensSurfacePositions:
    def test_valid_defaults(self):
        assert validate_huygens_surface_positions([[16, -16], [16, -16], [16, -16]]) == [
            [16, -16],
            [16, -16],
            [16, -16],
        ]
        assert validate_huygens_surface_positions([[1, -1], [1, -1], [1, -1]]) == [[1, -1], [1, -1], [1, -1]]
        assert validate_huygens_surface_positions([[16, -16], [16, -16], [16, -16]], cell_cnt=(128, 512, 256))
        assert validate_huygens_surface_positions([[1, -1], [1, -1], [1, -1]], cell_cnt=(40, 40, 40))

    def test_valid_positive_max(self):
        # a non-negative max is interpreted as an absolute coordinate
        assert validate_huygens_surface_positions([[16, 96], [1, -1], [1, -1]], cell_cnt=(128, 40, 40))

    @pytest.mark.parametrize(
        "positions",
        [
            [[0, -1], [1, -1], [1, -1]],
            [[-1, -1], [1, -1], [1, -1]],
        ],
    )
    def test_invalid_min(self, positions):
        with pytest.raises(ValueError):
            validate_huygens_surface_positions(positions)

    @pytest.mark.parametrize(
        "positions",
        [
            [[1, 0], [1, -1], [1, -1]],
            [[1, 1], [1, -1], [1, -1]],
        ],
    )
    def test_invalid_non_negative_max_without_valid_absolute_position(self, positions):
        # max == 0 and positive-absolute max not beyond min are invalid
        with pytest.raises(ValueError):
            validate_huygens_surface_positions(positions)

    @pytest.mark.parametrize(
        "positions",
        [
            [[1, -1], [1, -1]],
            [[1, -1], [1, -1], [1, -1], [1, -1]],
            [[1, -1], [1], [1, -1]],
            [[1, -1], [1.0, -1], [1, -1]],
            [[1, -1], ["a", -1], [1, -1]],
            "not a list",
            [1, 2, 3],
        ],
    )
    def test_invalid_shape(self, positions):
        with pytest.raises(ValueError):
            validate_huygens_surface_positions(positions)

    def test_insufficient_dimension(self):
        # default positions need each axis to be > 32 cells
        with pytest.raises(ValueError):
            validate_huygens_surface_positions([[16, -16], [16, -16], [16, -16]], cell_cnt=(32, 20, 32))

    def test_too_small_grid(self):
        # surfaces do not fit into the domain at all
        with pytest.raises(ValueError):
            validate_huygens_surface_positions([[16, -16], [16, -16], [16, -16]], cell_cnt=(16, 16, 16))

    def test_overlapping_surfaces(self):
        # positive absolute max must lie beyond the min position
        with pytest.raises(ValueError):
            validate_huygens_surface_positions([[20, 15], [1, -1], [1, -1]])
        # negative max reaching beyond the min position (insufficient dimension)
        with pytest.raises(ValueError):
            validate_huygens_surface_positions([[16, -16], [16, -16], [16, -16]], cell_cnt=(32, 20, 32))

    def test_wrong_grid_shape(self):
        with pytest.raises(ValueError):
            validate_huygens_surface_positions([[1, -1], [1, -1], [1, -1]], cell_cnt=(128, 512))


def _minimal_gaussian_laser(huygens_surface_positions):
    return laser.GaussianLaser(
        propagation_direction=[0, 1, 0],
        polarization_direction=[0, 0, 1],
        polarization_type=laser.PolarizationType.LINEAR,
        wavelength=1e-6,
        duration=30e-15,
        focal_position=[0, 0, 0],
        phi0=0.0,
        E0=1e14,
        pulse_init=4.0,
        waist=2e-6,
        laguerre_modes=[1.0],
        laguerre_phases=[0.0],
        huygens_surface_positions=huygens_surface_positions,
    )


class TestLaserModelValidator:
    def test_valid_defaults(self):
        _minimal_gaussian_laser([[16, -16], [16, -16], [16, -16]])

    def test_invalid_min(self):
        with pytest.raises(ValueError):
            _minimal_gaussian_laser([[0, -1], [1, -1], [1, -1]])

    def test_invalid_shape(self):
        with pytest.raises(ValueError):
            _minimal_gaussian_laser([[1, -1], [1, -1]])

    def test_from_openpmd_pulse_laser_valid(self):
        laser.FromOpenPMDPulseLaser(
            propagation_direction=[0, 1, 0],
            polarization_direction=[0, 0, 1],
            file_path="/tmp/pulse.h5",
            iteration=0,
            dataset_name="pulse",
            datatype="float64",
            time_offset_si=0.0,
            polarisationAxisOpenPMD="z",
            propagationAxisOpenPMD="y",
            huygens_surface_positions=[[1, -1], [1, -1], [1, -1]],
        )

    def test_from_openpmd_pulse_laser_invalid(self):
        with pytest.raises(ValueError):
            laser.FromOpenPMDPulseLaser(
                propagation_direction=[0, 1, 0],
                polarization_direction=[0, 0, 1],
                file_path="/tmp/pulse.h5",
                iteration=0,
                dataset_name="pulse",
                datatype="float64",
                time_offset_si=0.0,
                polarisationAxisOpenPMD="z",
                propagationAxisOpenPMD="y",
                huygens_surface_positions=[[0, -1], [1, -1], [1, -1]],
            )

    def test_twts_laser_inherits_shared_field(self):
        # TWTSLaser no longer redefines the field but inherits it from the base class
        assert "huygens_surface_positions" in laser.TWTSLaser.model_fields
