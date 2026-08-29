"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+

Negative and positive tests for the physical/technical invariants
enforced by the pypicongpu pydantic models (task 06).
"""

import warnings
from datetime import timedelta

import pytest
from pydantic import ValidationError

from picongpu.pypicongpu.field_solver import YeeSolver
from picongpu.pypicongpu.grid import BoundaryCondition, Grid3D
from picongpu.pypicongpu.laser import GaussianLaser
from picongpu.pypicongpu.movingwindow import MovingWindow
from picongpu.pypicongpu.simulation import Simulation
from picongpu.pypicongpu.walltime import Walltime


def make_grid(**overrides):
    kwargs = dict(
        cell_size_si=(1e-6, 1e-6, 1e-6),
        cell_cnt=(16, 16, 16),
        boundary_condition=(BoundaryCondition.PERIODIC,) * 3,
        n_gpus=(1, 1, 1),
        super_cell_size=(2, 2, 2),
    )
    kwargs |= overrides
    return Grid3D(**kwargs)


def make_laser(**overrides):
    kwargs = dict(
        propagation_direction=(0.0, 1.0, 0.0),
        polarization_direction=(0.0, 0.0, 1.0),
        polarization_type="Linear",
        wavelength=0.8e-6,
        duration=1e-15,
        focal_position=(0.5, 0.5, 0.5),
        phi0=0.0,
        E0=1e10,
        pulse_init=1.0,
        huygens_surface_positions=[[1, -1], [1, -1], [1, -1]],
        waist=1e-5,
        laguerre_modes=[1.0],
        laguerre_phases=[0.0],
    )
    kwargs |= overrides
    return GaussianLaser(**kwargs)


def make_sim(**overrides):
    kwargs = dict(
        base_density=1.0e22,
        delta_t_si=1e-15,
        time_steps=100,
        grid=make_grid(),
        laser=None,
        solver=YeeSolver(),
        typical_ppc=4,
        customuserinput=None,
        moving_window=None,
        walltime=Walltime(walltime=timedelta(hours=1)),
        binomial_current_interpolation=False,
        output=None,
        species=[],
        init_operations=[],
    )
    kwargs |= overrides
    return Simulation(**kwargs)


class TestSimulationInvariants:
    """Simulation-level physical invariants."""

    @pytest.mark.parametrize("base_density", [0.0, -1.0e22])
    def test_base_density_must_be_positive(self, base_density):
        with pytest.raises(ValidationError):
            make_sim(base_density=base_density)

    def test_base_density_positive_ok(self):
        assert make_sim().base_density == 1.0e22

    @pytest.mark.parametrize("delta_t_si", [0.0, -1e-15])
    def test_delta_t_must_be_positive(self, delta_t_si):
        with pytest.raises(ValidationError):
            make_sim(delta_t_si=delta_t_si)

    def test_delta_t_positive_ok(self):
        assert make_sim().delta_t_si == 1e-15

    @pytest.mark.parametrize("time_steps", [-1, -100])
    def test_time_steps_must_be_non_negative(self, time_steps):
        with pytest.raises(ValidationError):
            make_sim(time_steps=time_steps)

    def test_time_steps_zero_ok(self):
        assert make_sim(time_steps=0).time_steps == 0

    @pytest.mark.parametrize("typical_ppc", [0, -4])
    def test_typical_ppc_must_be_positive(self, typical_ppc):
        with pytest.raises(ValidationError):
            make_sim(typical_ppc=typical_ppc)

    def test_laser_exceeding_run_warns(self):
        # technical invariant: warning, not an error
        with pytest.warns(UserWarning, match="exceeds the simulation time"):
            make_sim(laser=[make_laser(duration=1.0)], time_steps=10)

    def test_laser_within_run_does_not_warn(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            make_sim(laser=[make_laser(duration=1e-15)], time_steps=100)


class TestWalltimeInvariants:
    @pytest.mark.parametrize("walltime", [timedelta(0), timedelta(seconds=-1)])
    def test_walltime_must_be_positive(self, walltime):
        with pytest.raises(ValidationError):
            Walltime(walltime=walltime)

    def test_walltime_positive_ok(self):
        assert Walltime(walltime=timedelta(hours=1)).walltime == timedelta(hours=1)


class TestMovingWindowInvariants:
    @pytest.mark.parametrize("move_point", [-0.1, -1.0])
    def test_move_point_must_be_non_negative(self, move_point):
        with pytest.raises(ValidationError):
            MovingWindow(move_point=move_point)

    @pytest.mark.parametrize("stop_iteration", [0, -5])
    def test_stop_iteration_must_be_positive(self, stop_iteration):
        with pytest.raises(ValidationError):
            MovingWindow(move_point=0.5, stop_iteration=stop_iteration)

    def test_valid_moving_window(self):
        window = MovingWindow(move_point=0.5, stop_iteration=10)
        assert window.move_point == 0.5
        assert window.stop_iteration == 10
