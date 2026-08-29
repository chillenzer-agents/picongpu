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
from picongpu.pypicongpu.laser import FromOpenPMDPulseLaser, GaussianLaser, TWTSLaser
from picongpu.pypicongpu.movingwindow import MovingWindow
from picongpu.pypicongpu.output.checkpoint import Checkpoint
from picongpu.pypicongpu.output.radiation import (
    FrequenciesFromList,
    LinearFrequencies,
    LogFrequencies,
    RadiationConfiguration,
    RadiationObserverConfiguration,
    RadiationPluginConfig,
)
from picongpu.pypicongpu.output.timestepspec import Spec, TimeStepSpec
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


def make_gaussian_laser(**overrides):
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


class TestLaserInvariants:
    @pytest.mark.parametrize("wavelength", [0.0, -0.8e-6])
    def test_wavelength_must_be_positive(self, wavelength):
        with pytest.raises(ValidationError):
            make_gaussian_laser(wavelength=wavelength)

    @pytest.mark.parametrize("duration", [0.0, -1e-15])
    def test_pulse_duration_must_be_positive(self, duration):
        with pytest.raises(ValidationError):
            make_gaussian_laser(duration=duration)

    @pytest.mark.parametrize("E0", [0.0, -1e10])
    def test_E0_must_be_positive(self, E0):
        with pytest.raises(ValidationError):
            make_gaussian_laser(E0=E0)

    @pytest.mark.parametrize("waist", [0.0, -1e-5])
    def test_waist_must_be_positive(self, waist):
        with pytest.raises(ValidationError):
            make_gaussian_laser(waist=waist)

    @pytest.mark.parametrize("pulse_init", [-1.0, -0.5])
    def test_pulse_init_must_be_non_negative(self, pulse_init):
        with pytest.raises(ValidationError):
            make_gaussian_laser(pulse_init=pulse_init)

    def test_laguerre_modes_must_be_non_empty(self):
        with pytest.raises(ValidationError):
            make_gaussian_laser(laguerre_modes=[], laguerre_phases=[])

    def test_laguerre_modes_phases_must_match(self):
        with pytest.raises(ValidationError, match="equal length"):
            make_gaussian_laser(laguerre_modes=[1.0, 2.0], laguerre_phases=[0.0])

    def test_valid_gaussian_laser(self):
        laser = make_gaussian_laser()
        assert laser.wave_length_si == 0.8e-6


def make_twts_laser(**overrides):
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
        laserIncidenceAngle=1.0,
        laserIncidenceAnglePositive=True,
        polarizationAngle=0.0,
        beta0=1.0,
        time_offset_si=0.0,
        focus_lateral_offset_si=0.0,
        windowStart=0.0,
        windowEnd=0.0,
        windowLength=0.0,
    )
    kwargs |= overrides
    return TWTSLaser(**kwargs)


class TestTWTSLaserInvariants:
    @pytest.mark.parametrize("beta0", [1.5, -1.5])
    def test_beta0_must_not_exceed_speed_of_light(self, beta0):
        with pytest.raises(ValidationError):
            make_twts_laser(beta0=beta0)

    def test_beta0_at_c_allowed(self):
        # the C++ default is beta0 = 1.0 (overlap propagates with c)
        assert make_twts_laser(beta0=1.0).beta0 == 1.0

    @pytest.mark.parametrize("field", ["windowStart", "windowEnd", "windowLength"])
    @pytest.mark.parametrize("value", [-1.0, -10.0])
    def test_window_parameters_must_be_non_negative(self, field, value):
        with pytest.raises(ValidationError):
            make_twts_laser(**{field: value})

    def test_active_window_requires_end_after_start(self):
        with pytest.raises(ValidationError, match="windowEnd"):
            make_twts_laser(windowStart=100.0, windowEnd=50.0, windowLength=10.0)

    def test_inactive_window_allows_default_values(self):
        assert make_twts_laser().windowLength == 0.0

    def test_active_window_valid(self):
        assert make_twts_laser(windowStart=10.0, windowEnd=100.0, windowLength=10.0).windowEnd == 100.0


class TestFromOpenPMDPulseLaserInvariants:
    def laser_kwargs(self, iteration=0, file_path="pulse.h5"):
        return dict(
            propagation_direction=(0.0, 1.0, 0.0),
            polarization_direction=(0.0, 0.0, 1.0),
            file_path=file_path,
            iteration=iteration,
            dataset_name="E",
            datatype="float",
            time_offset_si=0.0,
            polarisationAxisOpenPMD="x",
            propagationAxisOpenPMD="y",
            huygens_surface_positions=[[1, -1], [1, -1], [1, -1]],
        )

    @pytest.mark.parametrize("iteration", [-1, -100])
    def test_iteration_must_be_non_negative(self, iteration):
        with pytest.raises(ValidationError):
            FromOpenPMDPulseLaser(**self.laser_kwargs(iteration=iteration))

    def test_file_path_must_not_be_empty(self):
        with pytest.raises(ValidationError):
            FromOpenPMDPulseLaser(**self.laser_kwargs(file_path=""))

    def test_valid_laser(self):
        laser = FromOpenPMDPulseLaser(**self.laser_kwargs())
        assert laser.iteration == 0


class TestTimeStepSpecInvariants:
    def test_negative_start_rejected(self):
        with pytest.raises(ValidationError, match="start"):
            TimeStepSpec([Spec(start=-1, stop=10, step=1)])

    def test_stop_below_minus_one_rejected(self):
        with pytest.raises(ValidationError, match="stop"):
            TimeStepSpec([Spec(start=0, stop=-2, step=1)])

    def test_zero_or_negative_step_rejected(self):
        for step in (0, -1):
            with pytest.raises(ValidationError, match="step"):
                TimeStepSpec([Spec(start=0, stop=10, step=step)])

    def test_valid_specs(self):
        spec = TimeStepSpec([Spec(start=0, stop=-1, step=5)])
        assert spec.specs[0].stop == -1

    def test_start_greater_than_stop_allowed(self):
        # PICMI slice semantics: such a spec selects an empty set of time
        # steps, which is deliberately not rejected (not even as a warning,
        # since the test suite runs with warnings-as-errors).
        spec = TimeStepSpec([Spec(start=10, stop=5, step=1)])
        assert spec.specs[0].start == 10


def make_radiation_config(**overrides):
    kwargs = dict(
        observer=RadiationObserverConfiguration(
            N_observer=2,
            index_to_direction=lambda index: (1, 0, 0),
        ),
    )
    kwargs |= overrides
    return RadiationPluginConfig(**kwargs)


class TestRadiationFrequencyInvariants:
    def test_linear_N_omega_must_be_positive(self):
        with pytest.raises(ValidationError, match="N_omega"):
            LinearFrequencies(N_omega=0)

    def test_linear_omega_min_must_be_below_omega_max(self):
        with pytest.raises(ValidationError, match="omega_min"):
            LinearFrequencies(omega_min=1e17, omega_max=1e14)

    def test_linear_equal_bounds_rejected(self):
        with pytest.raises(ValidationError, match="omega_min"):
            LinearFrequencies(omega_min=1e14, omega_max=1e14)

    def test_log_omega_min_must_be_positive(self):
        with pytest.raises(ValidationError, match="omega_min"):
            LogFrequencies(omega_min=0.0)

    def test_log_omega_min_must_be_below_omega_max(self):
        with pytest.raises(ValidationError, match="omega_min"):
            LogFrequencies(omega_min=1e17, omega_max=1e14)

    def test_from_list_location_must_not_be_empty(self):
        with pytest.raises(ValidationError, match="list_location"):
            FrequenciesFromList(list_location="")

    def test_linear_default_valid(self):
        assert LinearFrequencies().omega_min == 0.0


class TestRadiationConfigInvariants:
    def test_nyquist_factor_must_be_in_open_unit_interval(self):
        for factor in (0.0, 1.0, -0.5, 1.5):
            with pytest.raises(ValidationError, match="nyquist_factor"):
                RadiationConfiguration(nyquist_factor=factor)

    def test_observer_count_must_be_positive(self):
        with pytest.raises(ValidationError, match="N_observer"):
            RadiationObserverConfiguration(N_observer=0, index_to_direction=lambda index: (1, 0, 0))

    def test_gamma_filter_threshold_must_be_positive(self):
        with pytest.raises(ValidationError, match="gamma_filter_threshold"):
            make_radiation_config(gamma_filter_threshold=0.0)

    def test_num_jobs_must_be_positive(self):
        with pytest.raises(ValidationError, match="num_jobs"):
            make_radiation_config(num_jobs=0)

    def test_window_bounds_must_be_non_negative(self):
        with pytest.raises(ValidationError, match="start"):
            make_radiation_config(start=-1)
        with pytest.raises(ValidationError, match="end"):
            make_radiation_config(end=-1)

    def test_accumulation_steps_must_be_non_negative(self):
        with pytest.raises(ValidationError, match="num_accumulation_steps"):
            make_radiation_config(num_accumulation_steps=-1)

    def test_verbose_level_must_be_non_negative(self):
        with pytest.raises(ValidationError, match="verbose_level"):
            make_radiation_config(radiation=RadiationConfiguration(verbose_level=-1))

    def test_default_config_valid(self):
        assert make_radiation_config().gamma_filter_threshold is None


class TestCheckpointInvariants:
    def test_requires_period_or_time_period(self):
        with pytest.raises(ValidationError, match="period"):
            Checkpoint(directory="checkpoints")

    def test_time_period_must_be_non_negative(self):
        with pytest.raises(ValidationError, match="timePeriod"):
            Checkpoint(timePeriod=-1)

    def test_restart_step_must_be_non_negative(self):
        with pytest.raises(ValidationError, match="restartStep"):
            Checkpoint(timePeriod=0, restartStep=-1)

    def test_restart_chunk_size_must_be_positive(self):
        with pytest.raises(ValidationError, match="restartChunkSize"):
            Checkpoint(timePeriod=0, restartChunkSize=0)

    def test_restart_loop_must_be_non_negative(self):
        with pytest.raises(ValidationError, match="restartLoop"):
            Checkpoint(timePeriod=0, restartLoop=-1)

    def test_file_prefix_must_not_be_empty(self):
        with pytest.raises(ValidationError, match="file"):
            Checkpoint(timePeriod=0, file="")

    def test_restart_file_prefix_must_not_be_empty(self):
        with pytest.raises(ValidationError, match="restartFile"):
            Checkpoint(timePeriod=0, restartFile="")

    def test_restart_directory_must_not_be_empty(self):
        with pytest.raises(ValidationError, match="restartDirectory"):
            Checkpoint(timePeriod=0, restartDirectory="")

    def test_period_only_valid(self):
        checkpoint = Checkpoint(period=TimeStepSpec([Spec(start=0, stop=-1, step=10)]))
        assert checkpoint.period.specs[0].step == 10

    def test_time_period_only_valid(self):
        assert Checkpoint(timePeriod=5).timePeriod == 5
