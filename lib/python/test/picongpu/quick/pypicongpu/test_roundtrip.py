"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+

Round-trip safety (task 06): every model's own serialised output
(``model_dump(mode="json")``) must be accepted again by the model's
constructor, and re-serialising the reconstructed instance must yield the
identical dump. This guarantees that the (machine-readable) constraints and
validators captured in the pydantic models do not reject the models' own
serialisation, so that downstream tooling (e.g. task 07) can validate
``model_dump(mode="json")`` output against the models.

Only models whose serialisation is field-preserving are covered here; models
with a custom top-level ``model_serializer`` (e.g. the openPMD plugin) are
covered by the rendered-output regression instead.
"""

from datetime import timedelta

import pytest

from picongpu.pypicongpu.collisions import CollisionNumericsConfig, ConstLogCollision
from picongpu.pypicongpu.field_solver import YeeSolver
from picongpu.pypicongpu.grid import BoundaryCondition, Grid3D
from picongpu.pypicongpu.laser import GaussianLaser
from picongpu.pypicongpu.movingwindow import MovingWindow
from picongpu.pypicongpu.output.checkpoint import Checkpoint
from picongpu.pypicongpu.output.energy_histogram import EnergyHistogram
from picongpu.pypicongpu.output.phase_space import PhaseSpace
from picongpu.pypicongpu.output.radiation import LinearFrequencies, RadiationConfiguration
from picongpu.pypicongpu.output.timestepspec import Spec, TimeStepSpec
from picongpu.pypicongpu.species.attribute import Momentum, Position, Weighting
from picongpu.pypicongpu.species.constant import Charge, Mass
from picongpu.pypicongpu.species.operation.layout import OnePosition, Quiet, Random
from picongpu.pypicongpu.species.operation.momentum import Drift, Temperature
from picongpu.pypicongpu.species.species import Species
from picongpu.pypicongpu.walltime import Walltime


def _make_species():
    return Species(
        name="electron",
        constants=[Mass(mass_si=9.109e-31), Charge(charge_si=-1.602e-19)],
        attributes=[Position(), Weighting(), Momentum()],
    )


def _make_grid():
    return Grid3D(
        cell_size_si=(1e-6, 1e-6, 1e-6),
        cell_cnt=(16, 16, 16),
        boundary_condition=(BoundaryCondition.PERIODIC,) * 3,
        n_gpus=(1, 1, 1),
        super_cell_size=(2, 2, 2),
    )


def _make_laser():
    return GaussianLaser(
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


def _spec(**kwargs):
    return Spec(**kwargs)


def _build(name: str):
    if name == "Grid3D":
        return _make_grid()
    if name == "Walltime":
        return Walltime(walltime=timedelta(hours=1))
    if name == "MovingWindow":
        return MovingWindow(move_point=0.5, stop_iteration=50)
    if name == "YeeSolver":
        return YeeSolver()
    if name == "GaussianLaser":
        return _make_laser()
    if name == "TimeStepSpec":
        return TimeStepSpec([_spec(start=0, stop=-1, step=10)])
    if name == "Checkpoint":
        return Checkpoint(period=TimeStepSpec([_spec(start=0, stop=-1, step=10)]))
    if name == "LinearFrequencies":
        return LinearFrequencies()
    if name == "RadiationConfiguration":
        return RadiationConfiguration()
    if name == "PhaseSpace":
        return PhaseSpace(
            species=_make_species(),
            period=TimeStepSpec([_spec(start=0, stop=-1, step=1)]),
            spatial_coordinate="x",
            momentum_coordinate="px",
            min_momentum=-1.0,
            max_momentum=1.0,
        )
    if name == "EnergyHistogram":
        return EnergyHistogram(
            species=_make_species(),
            period=TimeStepSpec([_spec(start=0, stop=-1, step=1)]),
            bin_count=16,
            min_energy=0.0,
            max_energy=100.0,
        )
    if name == "ConstLogCollision":
        return ConstLogCollision(coulomb_log=12.0)
    if name == "CollisionNumericsConfig":
        return CollisionNumericsConfig(precision=64, cell_list_chunk_size=128)
    if name == "Species":
        return _make_species()
    if name == "OnePosition":
        return OnePosition(ppc=2, in_cell_offset=(0.5, 0.5, 0.5))
    if name == "Quiet":
        return Quiet(ppc=8, n_points=(2, 2, 2))
    if name == "Random":
        return Random(ppc=4)
    if name == "Drift":
        return Drift.from_velocity((1e5, 0.0, 0.0))
    if name == "Temperature_kev":
        return Temperature(temperature_kev=1e4)
    if name == "Temperature_directional":
        return Temperature(temperature_kev_directional=(1.0, 2.0, 3.0))
    raise AssertionError(f"unknown round-trip candidate {name=}")


_MODELS = [
    "Grid3D",
    "Walltime",
    "MovingWindow",
    "YeeSolver",
    "GaussianLaser",
    "TimeStepSpec",
    "Checkpoint",
    "LinearFrequencies",
    "RadiationConfiguration",
    "PhaseSpace",
    "EnergyHistogram",
    "ConstLogCollision",
    "CollisionNumericsConfig",
    "Species",
    "OnePosition",
    "Quiet",
    "Random",
    "Drift",
    "Temperature_kev",
    "Temperature_directional",
]


@pytest.mark.parametrize("name", _MODELS)
def test_model_roundtrip(name):
    model = _build(name)
    dumped = model.model_dump(mode="json")
    restored = type(model)(**dumped)
    assert restored.model_dump(mode="json") == dumped, f"{name} does not round-trip through model_dump(mode='json')"
