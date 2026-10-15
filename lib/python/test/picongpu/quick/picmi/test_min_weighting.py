"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
License: GPLv3+
"""

import json
import math
import re

import numpy as np
import pytest
from pydantic import ValidationError
from sympy import Piecewise

from picongpu import picmi
from picongpu.pypicongpu.simulation import Simulation as BackendSimulation


CELL_SIZE = [6.177353e-8, 3.088676e-8, 6.177353e-8]
CELL_VOLUME = math.prod(CELL_SIZE)
BASE_DENSITY = 1e25
VACUUM_Y = 6720 * CELL_SIZE[1]


def make_simulation(**options):
    cells = [3584, 3584, 1792]
    grid = picmi.Cartesian3DGrid(
        number_of_cells=cells,
        lower_bound=[0.0] * 3,
        upper_bound=[n * dx for n, dx in zip(cells, CELL_SIZE)],
        lower_boundary_conditions=["open"] * 3,
        upper_boundary_conditions=["open"] * 3,
        picongpu_n_gpus=[8, 16, 8],
        picongpu_super_cell_size=[8, 8, 8],
    )
    return picmi.Simulation(
        solver=picmi.ElectromagneticSolver(grid=grid, method="CKC"),
        time_step_size=5.15136e-17,
        max_steps=1000,
        picongpu_moving_window_move_point=0.0,
        **options,
    )


@pytest.fixture
def backend_parameters():
    return dict(make_simulation().get_as_pypicongpu())


@pytest.mark.parametrize("layer", ["picmi", "backend"])
@pytest.mark.parametrize("value", [0, -0.1, float("nan"), float("inf"), -float("inf"), True, "0.1"])
def test_invalid_min_weighting(layer, value, backend_parameters):
    with pytest.raises(ValidationError):
        if layer == "picmi":
            make_simulation(picongpu_min_weighting=value)
        else:
            BackendSimulation(**(backend_parameters | {"min_weighting": value}))


def test_default_and_backend_omission(backend_parameters):
    assert make_simulation().picongpu_min_weighting is None
    backend_parameters.pop("min_weighting")
    backend = BackendSimulation(**backend_parameters)
    assert backend.min_weighting == 10.0
    assert backend.get_rendering_context()["min_weighting"] == 10.0


def test_explicit_none_retains_upstream_default(backend_parameters):
    assert make_simulation(picongpu_min_weighting=None).get_as_pypicongpu().min_weighting == 10.0
    assert BackendSimulation(**(backend_parameters | {"min_weighting": None})).min_weighting == 10.0


@pytest.mark.parametrize("value", [0.1, 1, 2.5, 1e-12])
def test_positive_values_survive_conversion_and_serialization(value):
    backend = make_simulation(picongpu_min_weighting=value).get_as_pypicongpu()
    assert backend.min_weighting == value
    assert backend.get_rendering_context()["min_weighting"] == value
    assert json.loads(backend.model_dump_json())["min_weighting"] == value


@pytest.mark.parametrize("value", [1e-50, 1e40])
def test_min_weighting_must_fit_selected_precision(value, backend_parameters):
    with pytest.raises(ValidationError, match="selected precision"):
        make_simulation(picongpu_min_weighting=value).get_as_pypicongpu()
    with pytest.raises(ValidationError, match="selected precision"):
        BackendSimulation(**(backend_parameters | {"min_weighting": value}))
    double = make_simulation(picongpu_min_weighting=value, picongpu_precision=64).get_as_pypicongpu()
    assert double.min_weighting == value


def reference_weight_macro_particles(real_count, minimum, ppc, dtype):
    """Python transcription of startPosition/detail/WeightMacroParticles.hpp.

    This is a source-based acceptance oracle, not execution of C++.
    Round each floating operation to the selected precision.
    """
    real_count, minimum = dtype(real_count), dtype(minimum)
    count = math.floor(min(dtype(ppc), dtype(real_count / minimum)))
    weight = dtype(real_count / dtype(count)) if count else dtype(0)
    return count, weight


@pytest.mark.parametrize("dtype", [np.float32, np.float64])
@pytest.mark.parametrize("minimum", [0.1, 1.0, 10.0])
def test_creation_at_threshold_and_neighboring_weights(dtype, minimum):
    threshold = dtype(minimum)
    below = np.nextafter(threshold, dtype(0))
    above = np.nextafter(threshold, dtype(np.inf))
    for real_count, expected_count in [(0, 0), (below, 0), (threshold, 1), (above, 1), (10, 1)]:
        count, weight = reference_weight_macro_particles(real_count, minimum, 1, dtype)
        assert count == expected_count
        assert weight == (dtype(real_count) if count else 0)
    # With multiple requested particles the C++ algorithm reduces the count
    # before discarding a cell; do not confuse minimum weighting with density.
    assert reference_weight_macro_particles(2.5 * threshold, minimum, 4, dtype)[0] == 2


@pytest.mark.parametrize("dtype", [np.float32, np.float64])
def test_representative_reference_ramp_cells(dtype):
    # On the transverse plateau, the reference density rises linearly over
    # 100 micrometres after VACUUM_Y. FreeFormulaImpl samples cell centers.
    expected_custom = [0, 1, 1, 1, 1]
    expected_default = [0, 0, 0, 0, 0]
    for index, (custom, default) in enumerate(zip(expected_custom, expected_default), start=-1):
        fraction = max(0, (index + 0.5) * CELL_SIZE[1] / 100e-6)
        real_count = dtype(fraction * BASE_DENSITY * CELL_VOLUME)
        assert reference_weight_macro_particles(real_count, 0.1, 1, dtype)[0] == custom
        assert reference_weight_macro_particles(real_count, 10.0, 1, dtype)[0] == default
    # A dilute transverse-ramp product can still fall below the custom cutoff.
    assert reference_weight_macro_particles(1e-5 * BASE_DENSITY * CELL_VOLUME, 0.1, 1, dtype)[0] == 0


def test_setup_generation_preserves_layout_and_normalization(tmp_path):
    """Compare default/custom Python input generation on the active grid.

    Only the reference's longitudinal ramp is represented here. Full density,
    lasers, PML and output integration remain part of the final migration.
    """
    headers = []
    for minimum in [None, 0.1]:
        sim = make_simulation(**({} if minimum is None else {"picongpu_min_weighting": minimum}))
        density = picmi.AnalyticDistribution(
            density_function=lambda x, y, z: Piecewise(
                (0, y < VACUUM_Y),
                (BASE_DENSITY * (y - VACUUM_Y) / 100e-6, y < VACUUM_Y + 100e-6),
                (BASE_DENSITY, True),
            )
        )
        sim.add_species(
            picmi.Species(name="e", particle_type="electron", initial_distribution=density),
            layout=picmi.PseudoRandomLayout(n_macroparticles_per_cell=1),
        )
        output = tmp_path / ("default" if minimum is None else "reference_weighting")
        sim.write_input_file(
            output, cmake="-DPARAM_OVERWRITES:LIST='-DPARAM_FIELD_BACKGROUND=0;-DPARAM_COMPONENTWISE=1'"
        )
        context = json.loads((output / "metadata/pypicongpu_rendering_context.json").read_text())
        assert context["min_weighting"] == (10.0 if minimum is None else minimum)
        assert context["base_density"] == BASE_DENSITY
        assert context["typical_ppc"] == 1
        assert context["time_steps"] == 1000
        assert context["delta_t_si"] == 5.15136e-17
        assert context["grid"]["cell_cnt"] == dict(x=3584, y=3584, z=1792)
        assert context["grid"]["gpu_cnt"] == dict(x=8, y=16, z=8)
        assert context["grid"]["cell_size"] == pytest.approx(dict(zip("xyz", CELL_SIZE)))
        param_dir = output / "include/picongpu/param"
        files = {p.name: p.read_text() for p in param_dir.glob("*.param")}
        particle = files["particle.param"]
        actual = float(re.search(r"MIN_WEIGHTING\s*=\s*([^;]+);", particle)[1])
        assert actual == context["min_weighting"]
        assert re.search(r"numParticlesPerCell\s*=\s*1;", particle)
        assert "RandomImpl<random_ppc_species_e>" in particle
        assert "SI::BASE_DENSITY_SI" in files["density.param"]
        assert not (output / ".build").exists()
        headers.append(files)
    # Changing the cutoff must not alter the layout, profile or normalization.
    custom_particle = headers[1].pop("particle.param")
    default_particle = headers[0].pop("particle.param")
    # Renderer writes floats with enough digits for a binary64 round trip.
    strip_minimum = lambda text: re.sub(r"MIN_WEIGHTING\s*=\s*[^;]+;", "MIN_WEIGHTING = <value>;", text)
    assert strip_minimum(default_particle) == strip_minimum(custom_particle)
    assert headers[0] == headers[1]
