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
from picongpu.pypicongpu.laser import DispersivePulseLaser
from picongpu.pypicongpu.movingwindow import MovingWindow
from picongpu.pypicongpu.output.timestepspec import Spec, TimeStepSpec
from picongpu.pypicongpu.species.operation.momentum import Temperature
from picongpu.pypicongpu.walltime import Walltime

from .model_factories import (
    base_laser_kwargs,
    make_energy_histogram,
    make_from_openpmd_laser,
    make_grid,
    make_laser,
    make_phase_space,
    make_plane_wave_laser,
    make_species,
    make_twts_laser,
)


def _build(name: str):
    if name == "Grid3D":
        return make_grid()
    if name == "Walltime":
        return Walltime(walltime=timedelta(hours=1))
    if name == "MovingWindow":
        return MovingWindow(move_point=0.5, stop_iteration=50)
    if name == "YeeSolver":
        return YeeSolver()
    if name == "GaussianLaser":
        return make_laser()
    if name == "PlaneWaveLaser":
        return make_plane_wave_laser()
    if name == "DispersivePulseLaser":
        return DispersivePulseLaser(
            **(
                base_laser_kwargs()
                | dict(waist=1e-5, spectral_support=2.0, sd_si=0.0, ad_si=0.0, gdd_si=0.0, tod_si=0.0)
            )
        )
    if name == "TWTSLaser":
        return make_twts_laser()
    if name == "FromOpenPMDPulseLaser":
        return make_from_openpmd_laser()
    if name == "TimeStepSpec":
        return TimeStepSpec([Spec(start=0, stop=-1, step=10)])
    if name == "Checkpoint":
        from picongpu.pypicongpu.output.checkpoint import Checkpoint

        return Checkpoint(period=TimeStepSpec([Spec(start=0, stop=-1, step=10)]))
    if name == "LinearFrequencies":
        from picongpu.pypicongpu.output.radiation import LinearFrequencies

        return LinearFrequencies()
    if name == "RadiationConfiguration":
        from picongpu.pypicongpu.output.radiation import RadiationConfiguration

        return RadiationConfiguration()
    if name == "PhaseSpace":
        return make_phase_space()
    if name == "EnergyHistogram":
        return make_energy_histogram()
    if name == "ConstLogCollision":
        return ConstLogCollision(coulomb_log=12.0)
    if name == "CollisionNumericsConfig":
        return CollisionNumericsConfig(precision=64, cell_list_chunk_size=128)
    if name == "Species":
        return make_species()
    if name == "OnePosition":
        from picongpu.pypicongpu.species.operation.layout import OnePosition

        return OnePosition(ppc=2, in_cell_offset=(0.5, 0.5, 0.5))
    if name == "Quiet":
        from picongpu.pypicongpu.species.operation.layout import Quiet

        return Quiet(ppc=8, n_points=(2, 2, 2))
    if name == "Random":
        from picongpu.pypicongpu.species.operation.layout import Random

        return Random(ppc=4)
    if name == "Drift":
        from picongpu.pypicongpu.species.operation.momentum import Drift

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
    "PlaneWaveLaser",
    "DispersivePulseLaser",
    "TWTSLaser",
    "FromOpenPMDPulseLaser",
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
    restored = type(model).model_validate(dumped)
    assert restored.model_dump(mode="json") == dumped, f"{name} does not round-trip through model_dump(mode='json')"
