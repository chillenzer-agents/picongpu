"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: opencode
License: GPLv3+
"""

from picongpu.pypicongpu import laser as laser_module
from picongpu.pypicongpu.grid import BoundaryCondition, Grid3D
from picongpu.pypicongpu.laser import GaussianLaser
from picongpu.pypicongpu.species.operation.densityprofile.cylinder import Cylinder
from picongpu.pypicongpu.species.operation.densityprofile.plasmaramp import Exponential, None_
from picongpu.pypicongpu.species.operation.layout.one_position import OnePosition
from picongpu.pypicongpu.species.operation.layout.quiet import Quiet
from picongpu.pypicongpu.species.operation.momentum.drift import Drift
from picongpu.pypicongpu.species.operation.momentum.temperature import Temperature
from picongpu.pypicongpu.vector import (
    deserialise_grid_dist,
    deserialise_huygens,
    deserialise_vec,
    serialise_grid_dist,
    serialise_huygens,
    serialise_vec,
)
from pytest import raises


def test_serialise_vec_canonical_shape():
    """3-vectors are serialised into the canonical openPMD-style {x, y, z} dict"""
    assert serialise_vec((1.0, 2.0, 3.0)) == {"x": 1.0, "y": 2.0, "z": 3.0}


def test_deserialise_vec_accepts_all_input_forms():
    """deserialise_vec accepts the serialised dict, lists and tuples alike"""
    assert deserialise_vec({"x": 1.0, "y": 2.0, "z": 3.0}) == (1.0, 2.0, 3.0)
    assert deserialise_vec([1.0, 2.0, 3.0]) == (1.0, 2.0, 3.0)
    assert deserialise_vec((1.0, 2.0, 3.0)) == (1.0, 2.0, 3.0)
    # general iterables (numpy arrays, generators) are accepted as well
    import numpy

    assert deserialise_vec(numpy.array([1.0, 2.0, 3.0])) == (1.0, 2.0, 3.0)
    assert deserialise_vec(x for x in [1.0, 2.0, 3.0]) == (1.0, 2.0, 3.0)


def test_deserialise_vec_rejects_missing_keys():
    with raises(ValueError):
        deserialise_vec({"x": 1.0, "y": 2.0})


def test_deserialise_vec_rejects_non_vector():
    with raises(TypeError):
        deserialise_vec(42)


def test_serialise_deserialise_round_trip():
    """serialise -> deserialise recovers the original vector"""
    for value in [
        (1.0, 2.0, 3.0),
        (0.0, 0.0, 0.0),
        (-1.0, 0.5, 2.0),
    ]:
        assert deserialise_vec(serialise_vec(value)) == tuple(value)


def test_serialise_grid_dist_round_trip():
    grid_dist = ([64, 64], [32], [16])
    assert serialise_grid_dist(grid_dist) == {
        "x": [{"device_cells": 64}, {"device_cells": 64}],
        "y": [{"device_cells": 32}],
        "z": [{"device_cells": 16}],
    }
    assert deserialise_grid_dist(serialise_grid_dist(grid_dist)) == grid_dist
    assert serialise_grid_dist(None) is None


def test_serialise_huygens_round_trip():
    positions = [[1, -1], [2, -2], [3, -3]]
    serialised = serialise_huygens(positions)
    assert serialised == {
        "row_x": {"negative": 1, "positive": -1},
        "row_y": {"negative": 2, "positive": -2},
        "row_z": {"negative": 3, "positive": -3},
    }
    assert deserialise_huygens(serialised) == positions


def test_grid_rendering_context_uses_canonical_vec_shape():
    grid = Grid3D(
        cell_size_si=(1e-6, 1e-6, 1e-6),
        cell_cnt=(32, 32, 32),
        boundary_condition=(BoundaryCondition.ABSORBING, BoundaryCondition.ABSORBING, BoundaryCondition.PERIODIC),
        super_cell_size=(8, 8, 4),
        n_gpus=(1, 1, 1),
        grid_dist=([32], [32], [32]),
    )
    context = grid.get_rendering_context()
    assert context["cell_size"] == {"x": 1e-6, "y": 1e-6, "z": 1e-6}
    assert context["cell_cnt"] == {"x": 32, "y": 32, "z": 32}
    assert context["super_cell_size"] == {"x": 8, "y": 8, "z": 4}
    assert context["gpu_cnt"] == {"x": 1, "y": 1, "z": 1}
    assert context["grid_dist"] == {
        "x": [{"device_cells": 32}],
        "y": [{"device_cells": 32}],
        "z": [{"device_cells": 32}],
    }


def test_grid3d_roundtrips_from_rendering_context():
    grid = Grid3D(
        cell_size_si=(1e-6, 1e-6, 1e-6),
        cell_cnt=(32, 32, 32),
        boundary_condition=(BoundaryCondition.ABSORBING, BoundaryCondition.ABSORBING, BoundaryCondition.PERIODIC),
        super_cell_size=(8, 8, 4),
        n_gpus=(1, 1, 1),
        grid_dist=([32], [32], [32]),
    )
    context = grid.get_rendering_context()
    # the serialised boundary-condition dict-of-strings is a special case that
    # keeps its own round-trip form; feed the native tuple instead, and use the
    # alias for the cell-size field (as the model's constructor expects)
    context["boundary_condition"] = (
        BoundaryCondition.ABSORBING,
        BoundaryCondition.ABSORBING,
        BoundaryCondition.PERIODIC,
    )
    context["cell_size_si"] = context.pop("cell_size")
    assert Grid3D.model_validate(context).cell_size == (1e-6, 1e-6, 1e-6)


def test_laser_uses_canonical_vec_shape():
    laser = GaussianLaser(
        propagation_direction=[0, 1, 0],
        polarization_direction=[0, 0, 1],
        polarization_type=laser_module.PolarizationType.LINEAR,
        wavelength=1e-6,
        duration=30e-15,
        focal_position=[1e-5, 5e-6, 1e-5],
        phi0=0.0,
        E0=1e11,
        pulse_init=1.0,
        huygens_surface_positions=[[1, -1], [1, -1], [1, -1]],
        waist=5e-6,
        laguerre_modes=[2.0, 3.0],
        laguerre_phases=[4.0, 5.0],
    )
    context = laser.model_dump(mode="json")
    assert context["propagation_direction"] == {"x": 0.0, "y": 1.0, "z": 0.0}
    assert context["polarization_direction"] == {"x": 0.0, "y": 0.0, "z": 1.0}
    assert context["focus_pos_si"] == {"x": 1e-5, "y": 5e-6, "z": 1e-5}
    # arbitrary-length numeric sequences are plain lists, not component vectors
    assert context["laguerre_modes"] == [2.0, 3.0]
    assert context["laguerre_phases"] == [4.0, 5.0]
    assert context["huygens_surface_positions"] == {
        "row_x": {"negative": 1, "positive": -1},
        "row_y": {"negative": 1, "positive": -1},
        "row_z": {"negative": 1, "positive": -1},
    }


def test_laser_roundtrips_from_serialised_context():
    laser = GaussianLaser(
        propagation_direction=[0, 1, 0],
        polarization_direction=[0, 0, 1],
        polarization_type=laser_module.PolarizationType.LINEAR,
        wavelength=1e-6,
        duration=30e-15,
        focal_position=[1e-5, 5e-6, 1e-5],
        phi0=0.0,
        E0=1e11,
        pulse_init=1.0,
        huygens_surface_positions=[[1, -1], [1, -1], [1, -1]],
        waist=5e-6,
        laguerre_modes=[2.0, 3.0],
        laguerre_phases=[4.0, 5.0],
    )
    context = laser.model_dump(mode="json")
    # the wrapped fields are given by their aliases, which is what the constructor
    # (and hence model_validate) expects
    aliased = {
        "wavelength": context["wave_length_si"],
        "duration": context["pulse_duration_si"],
        "focal_position": context["focus_pos_si"],
        "phi0": context["phase"],
        "E0": context["E0_si"],
        "waist": context["waist_si"],
    }
    for key in ["wave_length_si", "pulse_duration_si", "focus_pos_si", "phase", "E0_si", "waist_si", "modenumber"]:
        context.pop(key)
    roundtripped = GaussianLaser.model_validate({**context, **aliased})
    assert roundtripped.propagation_direction == (0.0, 1.0, 0.0)
    assert roundtripped.polarization_direction == (0.0, 0.0, 1.0)
    assert roundtripped.laguerre_modes == [2.0, 3.0]
    assert roundtripped.huygens_surface_positions == [[1, -1], [1, -1], [1, -1]]


def test_cylinder_uses_canonical_vec_shape():
    cylinder = Cylinder(
        density_si=1e24,
        center_position_si=[1e-5, 2e-5, 3e-5],
        radius_si=4e-6,
        cylinder_axis=[0.0, 1.0, 0.0],
        pre_plasma_ramp=None_(),
    )
    context = cylinder.model_dump(mode="json")
    assert context["center_position_si"] == {"x": 1e-5, "y": 2e-5, "z": 3e-5}
    assert context["cylinder_axis"] == {"x": 0.0, "y": 1.0, "z": 0.0}
    roundtripped = Cylinder.model_validate(context)
    assert roundtripped.center_position_si == (1e-5, 2e-5, 3e-5)


def test_cylinder_with_exponential_ramp_roundtrips():
    cylinder = Cylinder(
        density_si=1e24,
        center_position_si=(1e-5, 2e-5, 3e-5),
        radius_si=4e-6,
        cylinder_axis=(0.0, 1.0, 0.0),
        pre_plasma_ramp=Exponential(PlasmaLength=0.5e-6, PlasmaCutoff=1e-6),
    )
    roundtripped = Cylinder.model_validate(cylinder.model_dump(mode="json"))
    assert roundtripped.cylinder_axis == (0.0, 1.0, 0.0)


def test_drift_uses_canonical_vec_shape():
    drift = Drift(direction_normalized=(0.0, 1.0, 0.0), gamma=2.0)
    context = drift.model_dump(mode="json")
    assert context["direction_normalized"] == {"x": 0.0, "y": 1.0, "z": 0.0}
    assert Drift.model_validate(context).direction_normalized == (0.0, 1.0, 0.0)


def test_temperature_directional_uses_canonical_vec_shape():
    temperature = Temperature(temperature_kev_directional=(1.0, 2.0, 3.0))
    context = temperature.model_dump(mode="json")
    assert context["temperature_kev_directional"] == {"x": 1.0, "y": 2.0, "z": 3.0}
    assert Temperature.model_validate(context).temperature_kev_directional == (1.0, 2.0, 3.0)


def test_quiet_n_points_uses_canonical_vec_shape():
    quiet = Quiet(n_points=(2, 2, 2), ppc=8)
    context = quiet.model_dump(mode="json")
    assert context["n_points"] == {"x": 2, "y": 2, "z": 2}
    assert Quiet.model_validate(context).n_points == (2, 2, 2)


def test_one_position_in_cell_offset_uses_canonical_vec_shape():
    layout = OnePosition(in_cell_offset=(0.1, 0.2, 0.3), ppc=2)
    context = layout.model_dump(mode="json")
    assert context["in_cell_offset"] == {"x": 0.1, "y": 0.2, "z": 0.3}
    assert OnePosition.model_validate(context).in_cell_offset == (0.1, 0.2, 0.3)
