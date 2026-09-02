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

from picongpu.pypicongpu.collisions import (
    Collision,
    CollisionalPhysicsSetup,
    CollisionNumericsConfig,
    ConstLogCollision,
    DynamicLogCollision,
)
from picongpu.pypicongpu.movingwindow import MovingWindow
from picongpu.pypicongpu.output.checkpoint import Checkpoint
from picongpu.pypicongpu.output.binning import BinSpec, Binning, BinningAxis
from picongpu.pypicongpu.output.checkpoint import Checkpoint
from picongpu.pypicongpu.output.openpmd_plugin import FieldDump, RangeSpec, RangeSpecEntry
from picongpu.pypicongpu.output.radiation import (
    FrequenciesFromList,
    LinearFrequencies,
    LogFrequencies,
    RadiationConfiguration,
    RadiationObserverConfiguration,
)
from picongpu.pypicongpu.output.timestepspec import Spec, TimeStepSpec
from sympy import Symbol

from picongpu.pypicongpu.particle_functor.filtered_species import FilteredSpecies
from picongpu.pypicongpu.particle_functor.particle_functor import ParticleFunctor
from picongpu.pypicongpu.particle_functor.unit_dimension import UnitDimension
from picongpu.pypicongpu.species.constant import (
    Charge,
    DensityRatio,
    ElementProperties,
    Mass,
    SPECIES_CONSTANTS,
    SpeciesConstants,
)
from picongpu.pypicongpu.species.constant.synchrotron import (
    FirstSynchrotronFunctionParams,
    InterpolationParams,
    SynchrotronParams,
)
from picongpu.pypicongpu.species.operation.densityprofile import Uniform
from picongpu.pypicongpu.species.operation.densityprofile.cylinder import Cylinder
from picongpu.pypicongpu.species.operation.densityprofile.gaussian import Gaussian
from picongpu.pypicongpu.species.operation.densityprofile.plasmaramp import Exponential
from picongpu.pypicongpu.species.species import Species
from picongpu.pypicongpu.species.attribute import BoundElectrons, Momentum, Position, Weighting
from picongpu.pypicongpu.species.operation.createdensity import CreateDensity
from picongpu.pypicongpu.species.operation.setchargestate import SetChargeState
from picongpu.pypicongpu.species.util import Element
from picongpu.pypicongpu.species.operation.layout import OnePosition, Quiet, Random
from picongpu.pypicongpu.species.operation.momentum import Drift, Temperature
from picongpu.pypicongpu.walltime import Walltime

from .model_factories import (
    make_binning_functor,
    make_energy_histogram,
    make_from_openpmd_laser,
    make_grid,
    make_laser,
    make_radiation_config,
    make_sim,
    make_species,
    make_twts_laser,
)


# -- Simulation-level invariants ------------------------------------------------


@pytest.mark.parametrize("base_density", [0.0, -1.0e22])
def test_base_density_must_be_positive(base_density):
    with pytest.raises(ValidationError):
        make_sim(base_density=base_density)


@pytest.mark.parametrize("delta_t_si", [0.0, -1e-15])
def test_delta_t_must_be_positive(delta_t_si):
    with pytest.raises(ValidationError):
        make_sim(delta_t_si=delta_t_si)


@pytest.mark.parametrize("time_steps", [-1, -100])
def test_time_steps_must_be_non_negative(time_steps):
    with pytest.raises(ValidationError):
        make_sim(time_steps=time_steps)


@pytest.mark.parametrize("typical_ppc", [0, -4])
def test_typical_ppc_must_be_positive(typical_ppc):
    with pytest.raises(ValidationError):
        make_sim(typical_ppc=typical_ppc)

class TestCreateDensityInvariants:
    def test_created_and_derived_species(self):
        op = CreateDensity(
            profile=Uniform(density_si=42.0),
            species=[make_species(name="a"), make_species(name="b"), make_species(name="c")],
            start_position=Random(ppc=4),
        )
        assert [s.name for s in op.species] == ["a", "b", "c"]
        assert op.created_species.name == "a"
        assert [s.name for s in op.derived_species] == ["b", "c"]

    def test_species_sorted_by_ratio_then_name(self):
        # ratio-less species are placed first (as ratio 0), then increasing
        # ratio; equal ratios (incl. ratio-less) are ordered by name, so the
        # rendered species order is deterministic
        op = CreateDensity(
            profile=Uniform(density_si=42.0),
            species=[
                make_species(name="zeta"),
                make_species(name="alpha", constants=[DensityRatio(ratio=4)]),
                make_species(name="beta"),
                make_species(name="gamma", constants=[DensityRatio(ratio=2)]),
            ],
            start_position=Random(ppc=4),
        )
        assert [s.name for s in op.species] == ["beta", "zeta", "gamma", "alpha"]

    def test_species_must_be_a_list(self):
        with pytest.raises(ValidationError, match="species must be a list"):
            CreateDensity(
                profile=Uniform(density_si=42.0),
                species=make_species(name="a"),
                start_position=Random(ppc=4),
            )


class TestMomentumInvariants:
    @pytest.mark.parametrize("gamma", [0.5, 0.99])
    def test_drift_gamma_must_be_at_least_one(self, gamma):
        with pytest.raises(ValidationError):
            Drift(direction_normalized=(1.0, 0.0, 0.0), gamma=gamma)

    def test_drift_direction_must_be_unit_vector(self):
        with pytest.raises(ValidationError, match="unit vector"):
            Drift(direction_normalized=(2.0, 0.0, 0.0), gamma=1.0)

def test_laser_exceeding_run_warns():
    with pytest.warns(UserWarning, match="exceeds the simulation time"):
        make_sim(laser=[make_laser(duration=1.0)], time_steps=10)


def test_laser_within_run_does_not_warn():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        make_sim(laser=[make_laser(duration=1e-15)], time_steps=100)


def test_twts_window_exceeding_run_warns():
    laser = make_twts_laser(windowStart=0.0, windowEnd=1000.0, windowLength=10.0)
    with pytest.warns(UserWarning, match="exceeds the simulation time"):
        make_sim(laser=[laser], time_steps=10)


def test_twts_window_within_run_does_not_warn():
    laser = make_twts_laser(windowStart=10.0, windowEnd=50.0, windowLength=10.0)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        make_sim(laser=[laser], time_steps=100)


def test_plane_wave_does_not_warn():
    from .model_factories import make_plane_wave_laser

    laser = make_plane_wave_laser(duration=1.0)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        make_sim(laser=[laser], time_steps=10)


# -- Walltime invariants ---------------------------------------------------------


@pytest.mark.parametrize("walltime", [timedelta(0), timedelta(seconds=-1)])
def test_walltime_must_be_positive(walltime):
    with pytest.raises(ValidationError):
        Walltime(walltime=walltime)


# -- MovingWindow invariants ------------------------------------------------------


@pytest.mark.parametrize("move_point", [-0.1, -1.0])
def test_move_point_must_be_non_negative(move_point):
    with pytest.raises(ValidationError):
        MovingWindow(move_point=move_point)


@pytest.mark.parametrize("stop_iteration", [0, -5])
def test_stop_iteration_must_be_positive(stop_iteration):
    with pytest.raises(ValidationError):
        MovingWindow(move_point=0.5, stop_iteration=stop_iteration)


# -- Grid invariants ---------------------------------------------------------------


@pytest.mark.parametrize("cell_size", [(0.0, 1e-6, 1e-6), (-1e-6, 1e-6, 1e-6)])
def test_cell_size_must_be_positive(cell_size):
    with pytest.raises(ValidationError):
        make_grid(cell_size_si=cell_size)


@pytest.mark.parametrize("cell_cnt", [(0, 16, 16), (16, -1, 16)])
def test_cell_cnt_must_be_positive(cell_cnt):
    with pytest.raises(ValidationError):
        make_grid(cell_cnt=cell_cnt)


@pytest.mark.parametrize("n_gpus", [(0, 1, 1), (1, -1, 1)])
def test_gpu_cnt_must_be_positive(n_gpus):
    with pytest.raises(ValidationError):
        make_grid(n_gpus=n_gpus)


@pytest.mark.parametrize("super_cell_size", [(0, 2, 2), (2, -2, 2)])
def test_super_cell_size_must_be_positive(super_cell_size):
    with pytest.raises(ValidationError):
        make_grid(super_cell_size=super_cell_size)


@pytest.mark.parametrize("grid_dist", [([0, 16], [16], [16]), ([16], [-16], [16])])
def test_grid_dist_entries_must_be_positive(grid_dist):
    with pytest.raises(ValidationError):
        make_grid(grid_dist=grid_dist)


def test_grid_dist_sum_mismatch_raises():
    with pytest.raises(ValidationError, match="sum of grid_dists"):
        make_grid(n_gpus=(2, 1, 1), grid_dist=([10, 16], [16], [16]))


def test_grid_dist_not_multiple_of_super_cell_warns():
    with pytest.warns(UserWarning, match="multiple of the super cell size"):
        make_grid(super_cell_size=(3, 2, 2), grid_dist=([8, 8], [16], [16]))


def test_super_cell_does_not_divide_grid_warns():
    with pytest.warns(UserWarning, match="does not match grid size"):
        make_grid(super_cell_size=(3, 2, 2))


def test_gpu_cnt_does_not_divide_grid_warns():
    with pytest.warns(UserWarning, match="does not match grid size"):
        make_grid(n_gpus=(3, 1, 1))


def test_valid_grid_does_not_warn():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        make_grid()


# -- Species constant invariants ---------------------------------------------------


def test_mass_negative_rejected():
    with pytest.raises(ValidationError):
        Mass(mass_si=-9.1e-31)


def test_charge_negative_accepted():
    assert Charge(charge_si=-1.6e-19).charge_si == -1.6e-19


@pytest.mark.parametrize("ratio", [0.0, -1.0])
def test_density_ratio_must_be_positive(ratio):
    with pytest.raises(ValidationError):
        DensityRatio(ratio=ratio)


# -- Synchrotron invariants ---------------------------------------------------------


def test_log_end_must_be_positive():
    with pytest.raises(ValidationError):
        FirstSynchrotronFunctionParams(log_end=0.0)


def test_num_sample_points_must_be_positive():
    with pytest.raises(ValidationError):
        FirstSynchrotronFunctionParams(num_sample_points=0)


def test_number_table_entries_must_be_positive():
    with pytest.raises(ValidationError):
        InterpolationParams(number_table_entries=0)


def test_max_zq_exponent_must_be_at_most_10():
    with pytest.raises(ValidationError):
        InterpolationParams(max_Zq_exponent=11.0)


def test_min_zq_exponent_must_be_smaller_than_max():
    with pytest.raises(ValidationError, match="min_Zq_exponent"):
        InterpolationParams(min_Zq_exponent=10.0, max_Zq_exponent=10.0)


def test_min_energy_must_be_positive():
    with pytest.raises(ValidationError):
        SynchrotronParams(min_energy=-1.0)


# -- Species model invariants --------------------------------------------------------


@pytest.mark.parametrize("name", ["with space", "with.dot", "with-dash", "with_newline\n", ""])
def test_species_name_must_be_cpp_identifier(name):
    with pytest.raises(ValidationError, match="C\\+\\+ identifier"):
        make_species(name=name)


def test_position_attribute_mandatory():
    from picongpu.pypicongpu.species.attribute import Momentum, Weighting

    with pytest.raises(ValidationError, match="position attribute"):
        make_species(attributes=[Weighting(), Momentum()])


def test_momentum_attribute_mandatory():
    from picongpu.pypicongpu.species.attribute import Position, Weighting

    with pytest.raises(ValidationError, match="momentum attribute"):
        make_species(attributes=[Position(), Weighting()])


def test_duplicate_attribute_rejected():
    from picongpu.pypicongpu.species.attribute import Momentum, Position, Weighting

    with pytest.raises(ValidationError, match="unique"):
        make_species(attributes=[Position(), Weighting(), Momentum(), Weighting()])


# -- Layout invariants -----------------------------------------------------------------


@pytest.mark.parametrize("offset", [(1.0, 0.0, 0.0), (-0.1, 0.0, 0.0)])
def test_one_position_offset_must_be_in_unit_interval(offset):
    with pytest.raises(ValidationError, match="between 0 and 1"):
        OnePosition(ppc=1, in_cell_offset=offset)


@pytest.mark.parametrize("n_points", [(0, 1, 1), (1, -1, 1)])
def test_quiet_n_points_must_be_positive(n_points):
    with pytest.raises(ValidationError, match="greater than 0"):
        Quiet(ppc=1, n_points=n_points)


@pytest.mark.parametrize("ppc", [0, -1])
def test_ppc_must_be_positive(ppc):
    with pytest.raises(ValidationError):
        Random(ppc=ppc)


# -- Momentum invariants -----------------------------------------------------------------


@pytest.mark.parametrize("gamma", [0.5, 0.99])
def test_drift_gamma_must_be_at_least_one(gamma):
    with pytest.raises(ValidationError):
        Drift(direction_normalized=(1.0, 0.0, 0.0), gamma=gamma)


def test_drift_direction_must_be_unit_vector():
    with pytest.raises(ValidationError, match="unit vector"):
        Drift(direction_normalized=(2.0, 0.0, 0.0), gamma=1.0)


def test_drift_from_velocity_above_c_rejected():
    from scipy.constants import c as speed_of_light

    with pytest.raises(ValueError, match="less than the speed of light"):
        Drift.from_velocity((2 * speed_of_light, 0.0, 0.0))


def test_temperature_negative_directional_rejected():
    with pytest.raises(ValidationError, match=">= 0"):
        Temperature(temperature_kev_directional=(1.0, -1.0, 1.0))


def test_temperature_exactly_one_set():
    with pytest.raises(ValidationError, match="Exactly one"):
        Temperature(temperature_kev=1.0, temperature_kev_directional=(1.0, 1.0, 1.0))


# -- Density profile invariants -------------------------------------------------------------


@pytest.mark.parametrize("density_si", [0.0, -1.0])
def test_uniform_density_must_be_positive(density_si):
    with pytest.raises(ValidationError):
        Uniform(density_si=density_si)


def test_gaussian_center_ordering():
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

    def test_gaussian_density_si_field(self):
        # the SI field name is density_si (like Uniform/Foil/Cylinder);
        # the picmi attribute name `density` is accepted as an alias
        g = Gaussian(
            center_front=0.2,
            center_rear=0.4,
            sigma_front=0.01,
            sigma_rear=0.01,
            factor=-1.0,
            power=2.0,
            vacuum_cells_front=0,
            density_si=42.0,
        )
        assert g.density_si == 42.0
        # serialisation uses the field name, so round-trips via the alias-free key
        assert Gaussian.model_validate(g.model_dump()).density_si == 42.0

    @pytest.mark.parametrize("density_si", [0.0, -1.0])
    def test_gaussian_density_must_be_positive(self, density_si):
        with pytest.raises(ValidationError):
            Gaussian(
                center_front=0.2,
                center_rear=0.4,
                sigma_front=0.01,
                sigma_rear=0.01,
                factor=-1.0,
                power=2.0,
                vacuum_cells_front=0,
                density_si=density_si,
            )

def test_cylinder_radius_too_small_for_ramp():
    with pytest.raises(ValidationError, match="reduced radius"):
        Cylinder(
            density_si=1.0,
            center_position_si=(0.5, 0.5, 0.5),
            radius_si=0.01,
            cylinder_axis=(0.0, 0.0, 1.0),
            pre_plasma_ramp=Exponential(PlasmaLength=0.1, PlasmaCutoff=0.5),
        )


# -- Laser invariants -----------------------------------------------------------------------


@pytest.mark.parametrize("wavelength", [0.0, -0.8e-6])
def test_wavelength_must_be_positive(wavelength):
    with pytest.raises(ValidationError):
        make_laser(wavelength=wavelength)


@pytest.mark.parametrize("duration", [0.0, -1e-15])
def test_pulse_duration_must_be_positive(duration):
    with pytest.raises(ValidationError):
        make_laser(duration=duration)


@pytest.mark.parametrize("E0", [0.0, -1e10])
def test_E0_must_be_positive(E0):
    with pytest.raises(ValidationError):
        make_laser(E0=E0)


@pytest.mark.parametrize("waist", [0.0, -1e-5])
def test_waist_must_be_positive(waist):
    with pytest.raises(ValidationError):
        make_laser(waist=waist)


@pytest.mark.parametrize("pulse_init", [-1.0, -0.5])
def test_pulse_init_must_be_non_negative(pulse_init):
    with pytest.raises(ValidationError):
        make_laser(pulse_init=pulse_init)


def test_laguerre_modes_must_be_non_empty():
    with pytest.raises(ValidationError):
        make_laser(laguerre_modes=[], laguerre_phases=[])


def test_laguerre_modes_phases_must_match():
    with pytest.raises(ValidationError, match="equal length"):
        make_laser(laguerre_modes=[1.0, 2.0], laguerre_phases=[0.0])


# -- TWTSLaser invariants --------------------------------------------------------------------


@pytest.mark.parametrize("beta0", [1.5, -1.5])
def test_beta0_must_not_exceed_speed_of_light(beta0):
    with pytest.raises(ValidationError):
        make_twts_laser(beta0=beta0)


@pytest.mark.parametrize("field", ["windowStart", "windowEnd", "windowLength"])
@pytest.mark.parametrize("value", [-1.0, -10.0])
def test_window_parameters_must_be_non_negative(field, value):
    with pytest.raises(ValidationError):
        make_twts_laser(**{field: value})


def test_active_window_requires_end_after_start():
    with pytest.raises(ValidationError, match="windowEnd"):
        make_twts_laser(windowStart=100.0, windowEnd=50.0, windowLength=10.0)


# -- FromOpenPMDPulseLaser invariants -----------------------------------------------------------


@pytest.mark.parametrize("iteration", [-1, -100])
def test_from_openpmd_iteration_must_be_non_negative(iteration):
    with pytest.raises(ValidationError):
        make_from_openpmd_laser(iteration=iteration)


def test_from_openpmd_file_path_must_not_be_empty():
    with pytest.raises(ValidationError):
        make_from_openpmd_laser(file_path="")


# -- TimeStepSpec invariants ----------------------------------------------------------------------


def test_timespec_negative_start_rejected():
    with pytest.raises(ValidationError, match="start"):
        TimeStepSpec([Spec(start=-1, stop=10, step=1)])


def test_timespec_stop_below_minus_one_rejected():
    with pytest.raises(ValidationError, match="stop"):
        TimeStepSpec([Spec(start=0, stop=-2, step=1)])


def test_timespec_zero_or_negative_step_rejected():
    for step in (0, -1):
        with pytest.raises(ValidationError, match="step"):
            TimeStepSpec([Spec(start=0, stop=10, step=step)])


# -- Radiation frequency invariants ------------------------------------------------------------------


def test_linear_N_omega_must_be_positive():
    with pytest.raises(ValidationError, match="N_omega"):
        LinearFrequencies(N_omega=0)


def test_linear_omega_min_must_be_below_omega_max():
    with pytest.raises(ValidationError, match="omega_min"):
        LinearFrequencies(omega_min=1e17, omega_max=1e14)


def test_linear_equal_bounds_rejected():
    with pytest.raises(ValidationError, match="omega_min"):
        LinearFrequencies(omega_min=1e14, omega_max=1e14)


def test_log_omega_min_must_be_positive():
    with pytest.raises(ValidationError, match="omega_min"):
        LogFrequencies(omega_min=0.0)


def test_log_omega_min_must_be_below_omega_max():
    with pytest.raises(ValidationError, match="omega_min"):
        LogFrequencies(omega_min=1e17, omega_max=1e14)


def test_from_list_location_must_not_be_empty():
    with pytest.raises(ValidationError, match="list_location"):
        FrequenciesFromList(list_location="")


# -- Radiation config invariants -----------------------------------------------------------------------


def test_nyquist_factor_must_be_in_open_unit_interval():
    for factor in (0.0, 1.0, -0.5, 1.5):
        with pytest.raises(ValidationError, match="nyquist_factor"):
            RadiationConfiguration(nyquist_factor=factor)


def test_observer_count_must_be_positive():
    with pytest.raises(ValidationError, match="N_observer"):
        RadiationObserverConfiguration(N_observer=0, index_to_direction=lambda index: (1, 0, 0))


def test_gamma_filter_threshold_must_be_positive():
    with pytest.raises(ValidationError, match="gamma_filter_threshold"):
        make_radiation_config(gamma_filter_threshold=0.0)


def test_num_jobs_must_be_positive():
    with pytest.raises(ValidationError, match="num_jobs"):
        make_radiation_config(num_jobs=0)


def test_radiation_window_bounds_must_be_non_negative():
    with pytest.raises(ValidationError, match="start"):
        make_radiation_config(start=-1)
    with pytest.raises(ValidationError, match="end"):
        make_radiation_config(end=-1)


def test_accumulation_steps_must_be_non_negative():
    with pytest.raises(ValidationError, match="num_accumulation_steps"):
        make_radiation_config(num_accumulation_steps=-1)


def test_verbose_level_must_be_non_negative():
    with pytest.raises(ValidationError, match="verbose_level"):
        make_radiation_config(radiation=RadiationConfiguration(verbose_level=-1))


# -- Checkpoint invariants --------------------------------------------------------------------------------


def test_checkpoint_requires_period_or_time_period():
    with pytest.raises(ValidationError, match="period"):
        Checkpoint(directory="checkpoints")


def test_checkpoint_time_period_must_be_non_negative():
    with pytest.raises(ValidationError, match="timePeriod"):
        Checkpoint(timePeriod=-1)


def test_checkpoint_restart_step_must_be_non_negative():
    with pytest.raises(ValidationError, match="restartStep"):
        Checkpoint(timePeriod=0, restartStep=-1)


def test_checkpoint_restart_chunk_size_must_be_positive():
    with pytest.raises(ValidationError, match="restartChunkSize"):
        Checkpoint(timePeriod=0, restartChunkSize=0)


def test_checkpoint_restart_loop_must_be_non_negative():
    with pytest.raises(ValidationError, match="restartLoop"):
        Checkpoint(timePeriod=0, restartLoop=-1)


def test_checkpoint_file_prefix_must_not_be_empty():
    with pytest.raises(ValidationError, match="file"):
        Checkpoint(timePeriod=0, file="")


def test_checkpoint_restart_file_prefix_must_not_be_empty():
    with pytest.raises(ValidationError, match="restartFile"):
        Checkpoint(timePeriod=0, restartFile="")


# -- OpenPMD RangeSpec invariants -----------------------------------------------------------------------------


def test_range_negative_single_index_rejected():
    with pytest.raises(ValidationError, match="cell indices"):
        RangeSpecEntry(data=-1)


def test_range_negative_range_rejected():
    with pytest.raises(ValidationError, match="cell indices"):
        RangeSpecEntry(data=(-1, 5))


def test_range_inverted_range_rejected():
    with pytest.raises(ValidationError, match="start must not exceed"):
        RangeSpecEntry(data=(5, 1))


def test_range_serialization():
    assert RangeSpecEntry(data=None).model_dump() == ""
    assert RangeSpecEntry(data=42).model_dump() == "42"
    assert RangeSpecEntry(data=(1, 10)).model_dump() == "1:10"
    assert RangeSpec(data=(RangeSpecEntry(data=1), RangeSpecEntry(), RangeSpecEntry(data=42))).model_dump() == "1,,42"


# -- FieldDump invariants ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("filtername", ["bad name", "with.dot", "1leading", "with-dash"])
def test_filtername_must_be_c_identifier(filtername):
    with pytest.raises(ValidationError, match="C\\+\\+ identifier"):
        FieldDump(name="E", filtername=filtername)


# -- EnergyHistogram invariants -------------------------------------------------------------------------------------


def test_energy_histogram_bin_count_must_be_positive():
    with pytest.raises(ValidationError, match="bin_count"):
        make_energy_histogram(bin_count=0)


def test_energy_histogram_min_energy_must_be_non_negative():
    with pytest.raises(ValidationError, match="min_energy"):
        make_energy_histogram(min_energy=-1.0)


def test_energy_histogram_min_must_be_below_max():
    with pytest.raises(ValidationError, match="min_energy"):
        make_energy_histogram(min_energy=100.0, max_energy=50.0)


# -- PhaseSpace invariants ----------------------------------------------------------------------------------------------


def test_phase_space_min_must_be_below_max():
    from .model_factories import make_phase_space

    with pytest.raises(ValidationError, match="min_momentum"):
        make_phase_space(min_momentum=1.0, max_momentum=-1.0)


# -- Binning invariants ---------------------------------------------------------------------------------------------------


def test_bin_spec_nsteps_must_be_positive():
    with pytest.raises(ValidationError, match="nsteps"):
        BinSpec(kind="Linear", start=0.0, stop=1.0, nsteps=0)


def test_bin_spec_start_must_be_below_stop():
    with pytest.raises(ValidationError, match="smaller than its stop"):
        BinSpec(kind="Linear", start=1.0, stop=0.0, nsteps=1)


def test_bin_spec_equal_bounds_rejected():
    with pytest.raises(ValidationError, match="smaller than its stop"):
        BinSpec(kind="Linear", start=1.0, stop=1.0, nsteps=1)


def test_log_bin_spec_must_not_include_zero():
    for start, stop in ((-1.0, 1.0), (0.0, 1.0), (-1.0, 0.0)):
        with pytest.raises(ValidationError, match="zero"):
            BinSpec(kind="Log", start=start, stop=stop, nsteps=4)


def test_bin_spec_kind_must_be_linear_or_log():
    with pytest.raises(ValidationError, match="kind"):
        BinSpec(kind="position", start=0.0, stop=1.0, nsteps=4)


def test_axis_name_must_be_c_identifier():
    with pytest.raises(ValidationError, match="axis_name"):
        BinningAxis(
            name="x-y",
            functor=make_binning_functor(),
            bin_spec_raw=BinSpec(kind="Linear", start=0.0, stop=1.0, nsteps=1),
            use_overflow_bins=True,
        )


def test_binner_name_must_be_c_identifier():
    with pytest.raises(ValidationError, match="binner_name"):
        Binning(
            name="my-binner",
            deposition_functor=make_binning_functor("deposition"),
            axes=[
                BinningAxis(
                    name="x",
                    functor=make_binning_functor(),
                    bin_spec_raw=BinSpec(kind="Linear", start=0.0, stop=1.0, nsteps=1),
                    use_overflow_bins=True,
                )
            ],
            species=[make_species()],
            period=TimeStepSpec([Spec(start=0, stop=-1, step=1)]),
            openPMDBackendConfig=None,
            openPMDExt=None,
            openPMDInfix=None,
            dumpPeriod=1,
        )


class TestCollisionInvariants:
    def test_coulomb_log_must_be_positive(self):
        with pytest.raises(ValidationError, match="coulomb_log"):
            ConstLogCollision(coulomb_log=0.0)
        with pytest.raises(ValidationError, match="coulomb_log"):
            ConstLogCollision(coulomb_log=-1.0)

    def test_valid_const_log(self):
        assert ConstLogCollision(coulomb_log=12.0).coulomb_log == 12.0

    def test_valid_dynamic_log(self):
        assert DynamicLogCollision().type_dynamiclog is True

    def test_intra_species_differently_filtered_rejected(self):
        e = make_species()
        filtered = FilteredSpecies(species=e, functor=make_binning_functor("myFilter"))
        with pytest.raises(ValidationError, match="not supported"):
            Collision(species_pairs=[(e, filtered)], functor=ConstLogCollision(coulomb_log=10.0))

    def test_cell_list_chunk_size_must_be_positive(self):
        with pytest.raises(ValidationError, match="cell_list_chunk_size"):
            CollisionNumericsConfig(cell_list_chunk_size=0)

    def test_default_numerics_config_valid(self):
        assert CollisionNumericsConfig().cell_list_chunk_size is None

    def test_dynamic_log_requires_screening_species(self):
        # C++ requirement: the dynamic Coulomb logarithm is computed from the
        # Debye screening length, which needs at least one screening species
        e = make_species()
        with pytest.raises(ValidationError, match="screening"):
            CollisionalPhysicsSetup(collisions=[Collision(species_pairs=[(e, e)], functor=DynamicLogCollision())])

    def test_dynamic_log_with_screening_species_valid(self):
        e = make_species()
        setup = CollisionalPhysicsSetup(
            collisions=[Collision(species_pairs=[(e, e)], functor=DynamicLogCollision())],
            screening_species=[e],
        )
        assert len(setup.screening_species) == 1

    def test_const_log_without_screening_species_valid(self):
        e = make_species()
        setup = CollisionalPhysicsSetup(
            collisions=[Collision(species_pairs=[(e, e)], functor=ConstLogCollision(coulomb_log=10.0))]
        )
        assert setup.screening_species == []


class TestParticleFunctorInvariants:
    @pytest.mark.parametrize("name", ["with space", "with-dot", "1leading", "with\nnewline", ""])
    def test_name_must_be_c_identifier(self, name):
        with pytest.raises(ValidationError, match="valid C\\+\\+ identifier"):
            make_binning_functor(name=name)

    def test_valid_functor(self):
        functor = make_binning_functor()
        assert functor.name == "positionCell"
        assert functor.unit_dimension is None

    def test_float_return_type_keeps_unit_dimension(self):
        functor = ParticleFunctor(
            name="positionCell",
            functor_expression=Symbol("px"),
            functor_preamble=[],
            return_type="float_X",
        )
        assert functor.unit_dimension is not None


def test_binning_requires_axes_and_species():
    kwargs = dict(
        name="posBinning",
        deposition_functor=make_binning_functor("deposition"),
        period=TimeStepSpec([Spec(start=0, stop=-1, step=1)]),
        dumpPeriod=1,
    )
    axis = BinningAxis(
        name="x",
        functor=make_binning_functor(),
        bin_spec_raw=BinSpec(kind="Linear", start=0.0, stop=1.0, nsteps=1),
        use_overflow_bins=True,
    )
    with pytest.raises(ValidationError, match="axes"):
        Binning(**kwargs, axes=[], species=[make_species()])
    with pytest.raises(ValidationError, match="species"):
        Binning(**kwargs, axes=[axis], species=[])


def test_binning_dump_period_must_be_non_negative():
    with pytest.raises(ValidationError, match="dumpPeriod"):
        Binning(
            name="posBinning",
            deposition_functor=make_binning_functor("deposition"),
            axes=[
                BinningAxis(
                    name="x",
                    functor=make_binning_functor(),
                    bin_spec_raw=BinSpec(kind="Linear", start=0.0, stop=1.0, nsteps=1),
                    use_overflow_bins=True,
                )
            ],
            species=[make_species()],
            period=TimeStepSpec([Spec(start=0, stop=-1, step=1)]),
            openPMDBackendConfig=None,
            openPMDExt=None,
            openPMDInfix=None,
            dumpPeriod=-1,
        )


# -- Collision invariants ---------------------------------------------------------------------------------------------------


def test_coulomb_log_must_be_positive():
    with pytest.raises(ValidationError, match="coulomb_log"):
        ConstLogCollision(coulomb_log=0.0)
    with pytest.raises(ValidationError, match="coulomb_log"):
        ConstLogCollision(coulomb_log=-1.0)


def test_intra_species_differently_filtered_rejected():
    e = make_species()
    filtered = FilteredSpecies(species=e, functor=make_binning_functor("myFilter"))
    with pytest.raises(ValidationError, match="not supported"):
        Collision(species_pairs=[(e, filtered)], functor=ConstLogCollision(coulomb_log=10.0))


def test_cell_list_chunk_size_must_be_positive():
    with pytest.raises(ValidationError, match="cell_list_chunk_size"):
        CollisionNumericsConfig(cell_list_chunk_size=0)


# -- ParticleFunctor invariants --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["with space", "with-dot", "1leading", "with\nnewline", ""])
def test_functor_name_must_be_c_identifier(name):
    with pytest.raises(ValidationError, match="C\\+\\+ identifier"):
        make_binning_functor(name=name)


def test_unit_dimension_length_must_be_seven():
    with pytest.raises(ValidationError, match="must match"):
        UnitDimension(unit_dimension=[0.0] * 6)
