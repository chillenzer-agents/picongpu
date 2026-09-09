"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: PIConGPU AI Agent (TT-20)
License: GPLv3+
"""

import pytest
from picongpu import picmi, pypicongpu


def _grid(**kwargs) -> picmi.Cartesian3DGrid:
    base = dict(
        number_of_cells=[192, 2048, 128],
        lower_bound=[0, 0, 0],
        upper_bound=[3.40992e-5, 9.07264e-5, 2.27328e-5],
        lower_boundary_conditions=["open", "open", "periodic"],
        upper_boundary_conditions=["open", "open", "periodic"],
    )
    base.update(kwargs)
    return picmi.Cartesian3DGrid(**base)


def _sim(grid: picmi.Cartesian3DGrid, **kwargs) -> picmi.Simulation:
    solver = picmi.ElectromagneticSolver(method="Yee", grid=grid)
    base = dict(time_step_size=1.39e-16, max_steps=32, solver=solver)
    base.update(kwargs)
    return picmi.Simulation(**base)


def _laser(**kwargs) -> picmi.GaussianLaser:
    base = dict(
        wavelength=1,
        waist=2,
        duration=3,
        propagation_direction=[0, 1, 0],
        polarization_direction=[0, 0, 1],
        focal_position=[5, 4, 5],
        centroid_position=[5, -1.5, 5],
        E0=5,
        picongpu_huygens_surface_positions=[[16, -16], [16, -16], [16, -16]],
    )
    base.update(kwargs)
    return picmi.GaussianLaser(**base)


def _sim_with_laser(sim_kwargs=None, grid_kwargs=None, laser_kwargs=None) -> picmi.Simulation:
    sim = _sim(_grid(**(grid_kwargs or {})), **(sim_kwargs or {}))
    sim.add_laser(_laser(**(laser_kwargs or {})), None)
    return sim


def test_default_absorber_reproduces_cpp_threshold():
    """with the C++ NUM_CELLS=12 default the threshold is 12 cells from every boundary"""
    # exactly at the threshold is fine
    _sim_with_laser(
        laser_kwargs={"picongpu_huygens_surface_positions": [[12, -12], [12, -12], [12, -12]]}
    ).get_as_pypicongpu()
    # one cell too close raises at input time
    with pytest.raises(ValueError, match=".*at least 12 cells away.*is only 11.*"):
        _sim_with_laser(
            laser_kwargs={"picongpu_huygens_surface_positions": [[11, -12], [12, -12], [12, -12]]}
        ).get_as_pypicongpu()


def test_non_default_absorber_changes_threshold():
    """a non-default TT-19 absorber raises for positions that the default absorber would accept"""
    field_absorber = pypicongpu.fieldabsorber.FieldAbsorber(
        kind="exponential", thickness=((32, 32), (32, 32), (32, 32))
    )
    # the default 16-cell positions are now too close
    with pytest.raises(ValueError, match=".*at least 32 cells away.*is only 16.*"):
        _sim_with_laser(grid_kwargs={"picongpu_field_absorber": field_absorber}).get_as_pypicongpu()
    # explicitly moved out to 32 cells it passes
    _sim_with_laser(
        grid_kwargs={"picongpu_field_absorber": field_absorber},
        laser_kwargs={"picongpu_huygens_surface_positions": [[32, -32], [32, -32], [32, -32]]},
    ).get_as_pypicongpu()


def test_pml_cells_drive_threshold():
    """pml_cells (TT-19 symmetric sugar) likewise changes the required distance"""
    # pml_cells=32 makes the default 16-cell positions too close
    with pytest.raises(ValueError, match=".*axis 'x'.*at least 32 cells away.*"):
        _sim_with_laser(grid_kwargs={"pml_cells": [32, 32, 32]}).get_as_pypicongpu()


def test_pml_cells_do_not_drive_periodic_axes():
    """pml_cells raises the threshold only on absorbing axes, not on the periodic z axis"""
    # x/y exactly at the pml threshold, z only 5 cells from the (periodic) boundary -> passes
    _sim_with_laser(
        grid_kwargs={"pml_cells": [32, 32, 32]},
        laser_kwargs={"picongpu_huygens_surface_positions": [[32, -32], [32, -32], [5, -32]]},
    ).get_as_pypicongpu()
    # the same z distance on an absorbing (open) z axis is rejected
    with pytest.raises(ValueError, match=".*axis 'z'.*at least 32 cells away, but is only 5 cells away"):
        _sim_with_laser(
            grid_kwargs={
                "pml_cells": [32, 32, 32],
                "lower_boundary_conditions": ["open", "open", "open"],
                "upper_boundary_conditions": ["open", "open", "open"],
            },
            laser_kwargs={"picongpu_huygens_surface_positions": [[32, -32], [32, -32], [32, -5]]},
        ).get_as_pypicongpu()


def test_periodic_axis_exempt_from_check():
    """a surface hugging a periodic boundary passes even though it lies within the absorber thickness"""
    # z is periodic in the fixture grid: 5 cells from the z boundary is fine
    _sim_with_laser(
        laser_kwargs={"picongpu_huygens_surface_positions": [[16, -16], [16, -16], [5, -16]]}
    ).get_as_pypicongpu()
    # the same distance on the absorbing y axis is rejected
    with pytest.raises(ValueError, match=".*axis 'y' at the 'min' boundary.*is only 5 cells away"):
        _sim_with_laser(
            laser_kwargs={"picongpu_huygens_surface_positions": [[16, -16], [5, -16], [16, -16]]}
        ).get_as_pypicongpu()
    # an all-open grid has no exemption and rejects z too
    with pytest.raises(ValueError, match=".*axis 'z' at the 'min' boundary.*is only 5 cells away"):
        _sim_with_laser(
            grid_kwargs={
                "lower_boundary_conditions": ["open", "open", "open"],
                "upper_boundary_conditions": ["open", "open", "open"],
            },
            laser_kwargs={"picongpu_huygens_surface_positions": [[16, -16], [16, -16], [5, -16]]},
        ).get_as_pypicongpu()


def test_positive_max_absolute_coordinates():
    """a positive (absolute) max position is checked as size - position against the actual grid"""
    # x max at 112 on the 192-cell x axis is 80 cells from the edge -> passes
    _sim_with_laser(
        laser_kwargs={"picongpu_huygens_surface_positions": [[16, 112], [16, -16], [16, -16]]}
    ).get_as_pypicongpu()
    # x max at 188 is only 4 cells from the 192-cell edge -> rejected with a positive distance
    with pytest.raises(ValueError, match=".*axis 'x' at the 'max' boundary.*is only 4 cells away"):
        _sim_with_laser(
            laser_kwargs={"picongpu_huygens_surface_positions": [[16, 188], [16, -16], [16, -16]]}
        ).get_as_pypicongpu()


def test_too_close_to_boundary_raises_at_input_time():
    """a surface that passes the structural Depth-1 check but sits 1 cell from the
    boundary (too close for the Depth-2 absorber-distance check) is rejected at input time"""
    with pytest.raises(ValueError, match=".*at least 12 cells away.*is only 1.*"):
        _sim_with_laser(
            laser_kwargs={"picongpu_huygens_surface_positions": [[1, -12], [1, -12], [1, -12]]}
        ).get_as_pypicongpu()


def test_asymmetric_thickness_per_boundary():
    """per-boundary thickness from TT-19 is honoured by the input-time check"""
    field_absorber = pypicongpu.fieldabsorber.FieldAbsorber(thickness=((12, 4), (12, 12), (12, 12)))
    # x max only allows 4 cells -> 16 away is fine, 6 away is not
    _sim_with_laser(
        grid_kwargs={"picongpu_field_absorber": field_absorber},
        laser_kwargs={"picongpu_huygens_surface_positions": [[16, -6], [16, -16], [16, -16]]},
    ).get_as_pypicongpu()
    with pytest.raises(ValueError, match=".*axis 'x' at the 'max' boundary must be at least 4 cells away.*is only 3.*"):
        _sim_with_laser(
            grid_kwargs={"picongpu_field_absorber": field_absorber},
            laser_kwargs={"picongpu_huygens_surface_positions": [[16, -3], [16, -16], [16, -16]]},
        ).get_as_pypicongpu()


def test_moving_window_exempts_ymax():
    """with picongpu_moving_window_move_point set, the YMax boundary is not checked"""
    # without moving window: y max one cell away from the boundary is rejected
    with pytest.raises(ValueError, match=".*axis 'y' at the 'max' boundary.*"):
        _sim_with_laser(
            laser_kwargs={"picongpu_huygens_surface_positions": [[16, -16], [16, -1], [16, -16]]}
        ).get_as_pypicongpu()
    # the identical setup passes once the moving window is enabled
    _sim_with_laser(
        sim_kwargs={"picongpu_moving_window_move_point": 0.9},
        laser_kwargs={"picongpu_huygens_surface_positions": [[16, -16], [16, -1], [16, -16]]},
    ).get_as_pypicongpu()
