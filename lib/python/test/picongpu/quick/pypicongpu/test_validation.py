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
from picongpu.pypicongpu.species.constant import Charge, DensityRatio, Mass
from picongpu.pypicongpu.species.constant.synchrotron import (
    FirstSynchrotronFunctionParams,
    InterpolationParams,
    SynchrotronParams,
)
from picongpu.pypicongpu.species.species import Species
from picongpu.pypicongpu.species.attribute import Momentum, Position, Weighting
from picongpu.pypicongpu.species.operation.layout import OnePosition, Quiet, Random
from picongpu.pypicongpu.species.operation.momentum import Drift, Temperature
from picongpu.pypicongpu.species.operation.densityprofile import Uniform
from picongpu.pypicongpu.species.operation.densityprofile.gaussian import Gaussian
from picongpu.pypicongpu.species.operation.densityprofile.cylinder import Cylinder
from picongpu.pypicongpu.species.operation.densityprofile.plasmaramp import Exponential
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


class TestGridInvariants:
    """Grid3D physical/technical invariants."""

    @pytest.mark.parametrize("cell_size", [(0.0, 1e-6, 1e-6), (-1e-6, 1e-6, 1e-6)])
    def test_cell_size_must_be_positive(self, cell_size):
        with pytest.raises(ValidationError):
            make_grid(cell_size_si=cell_size)

    @pytest.mark.parametrize("cell_cnt", [(0, 16, 16), (16, -1, 16)])
    def test_cell_cnt_must_be_positive(self, cell_cnt):
        with pytest.raises(ValidationError):
            make_grid(cell_cnt=cell_cnt)

    @pytest.mark.parametrize("n_gpus", [(0, 1, 1), (1, -1, 1)])
    def test_gpu_cnt_must_be_positive(self, n_gpus):
        with pytest.raises(ValidationError):
            make_grid(n_gpus=n_gpus)

    @pytest.mark.parametrize("super_cell_size", [(0, 2, 2), (2, -2, 2)])
    def test_super_cell_size_must_be_positive(self, super_cell_size):
        with pytest.raises(ValidationError):
            make_grid(super_cell_size=super_cell_size)

    @pytest.mark.parametrize("grid_dist", [([0, 16], [16], [16]), ([16], [-16], [16])])
    def test_grid_dist_entries_must_be_positive(self, grid_dist):
        with pytest.raises(ValidationError):
            make_grid(grid_dist=grid_dist)

    def test_grid_dist_sum_mismatch_raises(self):
        with pytest.raises(ValidationError, match="sum of grid_dists"):
            make_grid(n_gpus=(2, 1, 1), grid_dist=([10, 16], [16], [16]))

    def test_grid_dist_not_multiple_of_super_cell_raises(self):
        with pytest.raises(ValidationError, match="multiple of the super cell size"):
            make_grid(super_cell_size=(3, 2, 2), grid_dist=([8, 8], [16], [16]))

    def test_super_cell_does_not_divide_grid_raises(self):
        # 16 cells in x cannot be split into a multiple of 3 super cells
        with pytest.raises(ValidationError, match="does not match grid size"):
            make_grid(super_cell_size=(3, 2, 2))

    def test_gpu_cnt_does_not_divide_grid_raises(self):
        with pytest.raises(ValidationError, match="does not match grid size"):
            make_grid(n_gpus=(3, 1, 1))

    def test_valid_grid(self):
        grid = make_grid()
        assert grid.cell_cnt == (16, 16, 16)


def make_species(name="electron", constants=(), attributes=None, **overrides):
    kwargs = dict(
        name=name,
        constants=list(constants),
        attributes=attributes if attributes is not None else [Position(), Weighting(), Momentum()],
    )
    kwargs |= overrides
    return Species(**kwargs)


class TestSpeciesConstantInvariants:
    def test_mass_negative_rejected(self):
        with pytest.raises(ValidationError):
            Mass(mass_si=-9.1e-31)

    def test_mass_zero_accepted_for_massless_particles(self):
        # photons are legitimately massless (Photon pusher)
        assert Mass(mass_si=0.0).mass_si == 0.0

    def test_charge_negative_accepted(self):
        # electrons carry a negative charge; the sign is free
        assert Charge(charge_si=-1.6e-19).charge_si == -1.6e-19

    @pytest.mark.parametrize("ratio", [0.0, -1.0])
    def test_density_ratio_must_be_positive(self, ratio):
        with pytest.raises(ValidationError):
            DensityRatio(ratio=ratio)


class TestSynchrotronInvariants:
    def test_log_end_must_be_positive(self):
        with pytest.raises(ValidationError):
            FirstSynchrotronFunctionParams(log_end=0.0)

    def test_num_sample_points_must_be_positive(self):
        with pytest.raises(ValidationError):
            FirstSynchrotronFunctionParams(num_sample_points=0)

    def test_number_table_entries_must_be_positive(self):
        with pytest.raises(ValidationError):
            InterpolationParams(number_table_entries=0)

    def test_max_zq_exponent_must_be_at_most_10(self):
        with pytest.raises(ValidationError):
            InterpolationParams(max_Zq_exponent=11.0)

    def test_min_zq_exponent_must_be_smaller_than_max(self):
        with pytest.raises(ValidationError, match="min_Zq_exponent"):
            InterpolationParams(min_Zq_exponent=10.0, max_Zq_exponent=10.0)

    def test_min_energy_must_be_positive(self):
        with pytest.raises(ValidationError):
            SynchrotronParams(min_energy=-1.0)


class TestSpeciesModelInvariants:
    @pytest.mark.parametrize("name", ["with space", "with.dot", "with-dash", "with_newline\n", ""])
    def test_name_must_be_cpp_identifier(self, name):
        with pytest.raises(ValidationError, match="c\\+\\+ compatible"):
            make_species(name=name)

    def test_valid_name(self):
        assert make_species(name="my_species2").name == "my_species2"

    def test_position_attribute_mandatory(self):
        with pytest.raises(ValidationError, match="position attribute"):
            make_species(attributes=[Weighting(), Momentum()])

    def test_momentum_attribute_mandatory(self):
        with pytest.raises(ValidationError, match="momentum attribute"):
            make_species(attributes=[Position(), Weighting()])

    def test_duplicate_attribute_rejected(self):
        with pytest.raises(ValidationError, match="unique"):
            make_species(attributes=[Position(), Weighting(), Momentum(), Weighting()])


class TestLayoutInvariants:
    @pytest.mark.parametrize("offset", [(1.0, 0.0, 0.0), (-0.1, 0.0, 0.0)])
    def test_one_position_offset_must_be_in_unit_interval(self, offset):
        with pytest.raises(ValidationError, match="between 0 and 1"):
            OnePosition(ppc=1, in_cell_offset=offset)

    @pytest.mark.parametrize("n_points", [(0, 1, 1), (1, -1, 1)])
    def test_quiet_n_points_must_be_positive(self, n_points):
        with pytest.raises(ValidationError, match="greater than 0"):
            Quiet(ppc=1, n_points=n_points)

    def test_quiet_default_satisfies_constraints(self):
        assert Quiet(ppc=1).n_points == (1, 1, 1)

    @pytest.mark.parametrize("ppc", [0, -1])
    def test_ppc_must_be_positive(self, ppc):
        with pytest.raises(ValidationError):
            Random(ppc=ppc)


class TestMomentumInvariants:
    @pytest.mark.parametrize("gamma", [0.5, 0.99])
    def test_drift_gamma_must_be_at_least_one(self, gamma):
        with pytest.raises(ValidationError):
            Drift(direction_normalized=(1.0, 0.0, 0.0), gamma=gamma)

    def test_drift_direction_must_be_unit_vector(self):
        with pytest.raises(ValidationError, match="unit vector"):
            Drift(direction_normalized=(2.0, 0.0, 0.0), gamma=1.0)

    def test_drift_from_velocity_above_c_rejected(self):
        from scipy.constants import c as speed_of_light

        with pytest.raises(ValueError, match="less than the speed of light"):
            Drift.from_velocity((2 * speed_of_light, 0.0, 0.0))

    def test_temperature_negative_directional_rejected(self):
        with pytest.raises(ValidationError, match=">= 0"):
            Temperature(temperature_kev_directional=(1.0, -1.0, 1.0))

    def test_temperature_exactly_one_set(self):
        with pytest.raises(ValidationError, match="Exactly one"):
            Temperature(temperature_kev=1.0, temperature_kev_directional=(1.0, 1.0, 1.0))

    def test_temperature_scalar_ok(self):
        assert Temperature(temperature_kev=1.0).temperature_kev == 1.0


class TestDensityProfileInvariants:
    @pytest.mark.parametrize("density_si", [0.0, -1.0])
    def test_uniform_density_must_be_positive(self, density_si):
        with pytest.raises(ValidationError):
            Uniform(density_si=density_si)

    def test_gaussian_center_ordering(self):
        with pytest.raises(ValidationError, match="gas_center_rear"):
            Gaussian(
                center_front=0.2,
                center_rear=0.1,
                sigma_front=0.01,
                sigma_rear=0.01,
                factor=-1.0,
                power=2.0,
                vacuum_cells_front=0,
                density=1.0,
            )

    def test_gaussian_valid(self):
        g = Gaussian(
            center_front=0.2,
            center_rear=0.4,
            sigma_front=0.01,
            sigma_rear=0.01,
            factor=-1.0,
            power=2.0,
            vacuum_cells_front=0,
            density=1.0,
        )
        assert g.gas_center_rear == 0.4

    def test_cylinder_radius_too_small_for_ramp(self):
        with pytest.raises(ValidationError, match="reduced radius"):
            Cylinder(
                density_si=1.0,
                center_position_si=(0.5, 0.5, 0.5),
                radius_si=0.01,
                cylinder_axis=(0.0, 0.0, 1.0),
                pre_plasma_ramp=Exponential(PlasmaLength=0.1, PlasmaCutoff=0.5),
            )
