"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+

Shared model factories for the pypicongpu quick tests.
"""

from datetime import timedelta

from sympy import Symbol

from picongpu.pypicongpu.field_solver import YeeSolver
from picongpu.pypicongpu.grid import BoundaryCondition, Grid3D
from picongpu.pypicongpu.laser import FromOpenPMDPulseLaser, GaussianLaser, PlaneWaveLaser, TWTSLaser
from picongpu.pypicongpu.output.energy_histogram import EnergyHistogram
from picongpu.pypicongpu.output.phase_space import PhaseSpace
from picongpu.pypicongpu.output.radiation import RadiationObserverConfiguration, RadiationPluginConfig
from picongpu.pypicongpu.output.timestepspec import Spec, TimeStepSpec
from picongpu.pypicongpu.particle_functor.particle_functor import ParticleFunctor
from picongpu.pypicongpu.simulation import Simulation
from picongpu.pypicongpu.species.attribute import Momentum, Position, Weighting
from picongpu.pypicongpu.species.species import Species
from picongpu.pypicongpu.walltime import Walltime


def make_species(name="electron", constants=(), attributes=None, **overrides):
    kwargs = dict(
        name=name,
        constants=list(constants),
        attributes=attributes if attributes is not None else [Position(), Weighting(), Momentum()],
    )
    kwargs |= overrides
    return Species(**kwargs)


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


def base_laser_kwargs():
    return dict(
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
    )


def make_laser(**overrides):
    kwargs = base_laser_kwargs() | dict(waist=1e-5, laguerre_modes=[1.0], laguerre_phases=[0.0])
    kwargs |= overrides
    return GaussianLaser(**kwargs)


def make_twts_laser(**overrides):
    kwargs = base_laser_kwargs() | dict(
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


def make_plane_wave_laser(**overrides):
    kwargs = base_laser_kwargs() | dict(laser_nofocus_constant_si=1.0)
    kwargs |= overrides
    return PlaneWaveLaser(**kwargs)


def make_from_openpmd_laser(**overrides):
    kwargs = dict(
        propagation_direction=(0.0, 1.0, 0.0),
        polarization_direction=(0.0, 0.0, 1.0),
        file_path="pulse.h5",
        iteration=0,
        dataset_name="E",
        datatype="float",
        time_offset_si=0.0,
        polarisationAxisOpenPMD="x",
        propagationAxisOpenPMD="y",
        huygens_surface_positions=[[1, -1], [1, -1], [1, -1]],
    )
    kwargs |= overrides
    return FromOpenPMDPulseLaser(**kwargs)


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


def make_binning_functor(name="positionCell", return_type="float_X"):
    return ParticleFunctor(
        name=name,
        functor_expression=Symbol("px"),
        functor_preamble=[],
        return_type=return_type,
        unit_dimension=None,
    )


def make_radiation_config(**overrides):
    kwargs = dict(
        observer=RadiationObserverConfiguration(
            N_observer=2,
            index_to_direction=lambda index: (1, 0, 0),
        ),
    )
    kwargs |= overrides
    return RadiationPluginConfig(**kwargs)


def make_energy_histogram(**overrides):
    kwargs = dict(
        species=make_species(),
        period=TimeStepSpec([Spec(start=0, stop=-1, step=1)]),
        bin_count=16,
        min_energy=0.0,
        max_energy=100.0,
    )
    kwargs |= overrides
    return EnergyHistogram(**kwargs)


def make_phase_space(**overrides):
    kwargs = dict(
        species=make_species(),
        period=TimeStepSpec([Spec(start=0, stop=-1, step=1)]),
        spatial_coordinate="x",
        momentum_coordinate="px",
        min_momentum=-1.0,
        max_momentum=1.0,
    )
    kwargs |= overrides
    return PhaseSpace(**kwargs)
