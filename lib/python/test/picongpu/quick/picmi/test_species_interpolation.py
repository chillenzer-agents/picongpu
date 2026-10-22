"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
License: GPLv3+
"""

import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from picongpu import picmi
from picongpu.pypicongpu.rendering import Renderer
from picongpu.pypicongpu.species.species import Species as BackendSpecies
from picongpu.pypicongpu.species.species import Shape


TEMPLATE = (
    Path(picmi.__file__).resolve().parents[1]
    / "templates/include/picongpu/param/speciesDefinition.param.mustache"
)


def render_species(*species):
    context = {"species": [s.get_rendering_context() for s in species]}
    return Renderer.get_rendered_template(Renderer.get_context_preprocessed(context), TEMPLATE.read_text())


def assert_species_shape_and_interpolation(rendered, name, expected_shape):
    """Resolve shape aliases and inspect the flags belonging to this species."""
    aliases = dict(re.findall(r"using\s+(\w+)\s*=\s*(particles::shapes::\w+)\s*;", rendered))
    flags = re.search(rf"using ParticleFlags_species_{name}\s*=\s*MakeSeq_t<(.*?)>;", rendered, re.S)
    assert flags is not None
    shape = re.search(r"\bshape<\s*([^<>]+?)\s*>", flags[1])
    interpolation = re.search(
        r"\binterpolation<\s*FieldToParticleInterpolation<\s*([^<>]+?)\s*,\s*AssignedTrilinearInterpolation\s*>\s*>",
        flags[1],
    )
    deposition = re.search(r"\bcurrent<\s*currentSolver::Esirkepov<\s*([^<>]+?)\s*>\s*>", flags[1])
    assert shape is not None
    assert interpolation is not None, flags[1]
    assert deposition is not None, flags[1]
    expected = f"particles::shapes::{expected_shape}"
    assert aliases.get(shape[1], shape[1]) == expected
    assert aliases.get(interpolation[1], interpolation[1]) == expected
    assert aliases.get(deposition[1], deposition[1]) == expected


@pytest.mark.parametrize(
    "parameters,expected_shape",
    [
        ({}, "TSC"),
        ({"particle_shape": None}, "TSC"),
        ({"particle_shape": "NGP"}, "NGP"),
        ({"particle_shape": "linear"}, "CIC"),
        ({"particle_shape": "quadratic"}, "TSC"),
        ({"particle_shape": "cubic"}, "PQS"),
        ({"particle_shape": "other:quartic"}, "PCS"),
    ],
)
def test_interpolation_uses_species_shape(parameters, expected_shape):
    species = picmi.Species(name="e", particle_type="electron", **parameters).get_as_pypicongpu()
    assert_species_shape_and_interpolation(render_species(species), "e", expected_shape)


def test_backend_default_interpolation_is_tsc():
    species = BackendSpecies(name="e", constants=[], attributes=[])
    assert_species_shape_and_interpolation(render_species(species), "e", "TSC")


@pytest.mark.parametrize("layer", ["picmi", "backend"])
def test_counter_shape_rejected_for_species_interpolation(layer):
    with pytest.raises(ValidationError, match="diagnostic counting shape"):
        if layer == "picmi":
            picmi.Species(particle_type="electron", particle_shape="other:counter").get_as_pypicongpu()
        else:
            BackendSpecies(name="e", constants=[], attributes=[], shape=Shape.counter)


def test_mixed_species_interpolation():
    species = [
        picmi.Species(name="cubic_e", particle_type="electron", particle_shape="cubic"),
        picmi.Species(name="linear_e", particle_type="electron", particle_shape="linear"),
        picmi.Species(name="default_e", particle_type="electron"),
    ]
    rendered = render_species(*(s.get_as_pypicongpu() for s in species))
    for name, shape in [("cubic_e", "PQS"), ("linear_e", "CIC"), ("default_e", "TSC")]:
        assert_species_shape_and_interpolation(rendered, name, shape)


@pytest.mark.parametrize("simulation_shape,inherited_shape", [(None, "TSC"), ("cubic", "PQS")])
def test_species_interpolation_setup_generation(tmp_path, simulation_shape, inherited_shape):
    """Generate mixed species on the reference grid; no C++ compilation or run.

    The extra species test independent shape selection. This is an isolated
    acceptance setup, not the final migrated plasma, lasers and diagnostics.
    """
    cells = [3584, 3584, 1792]
    cell_size = [6.177353e-8, 3.088676e-8, 6.177353e-8]
    grid = picmi.Cartesian3DGrid(
        number_of_cells=cells,
        lower_bound=[0.0] * 3,
        upper_bound=[n * dx for n, dx in zip(cells, cell_size)],
        lower_boundary_conditions=["open"] * 3,
        upper_boundary_conditions=["open"] * 3,
        picongpu_n_gpus=[8, 16, 8],
        picongpu_super_cell_size=[8, 8, 8],
    )
    plasma = picmi.UniformDistribution(density=1e25)
    species = [
        picmi.Species(
            name="e",
            particle_type="electron",
            particle_shape="cubic",
            initial_distribution=plasma,
        ),
        picmi.Species(
            name="linear_e", particle_type="electron", particle_shape="linear", initial_distribution=plasma
        ),
        picmi.Species(name="default_e", particle_type="electron", initial_distribution=plasma),
    ]
    simulation = picmi.Simulation(
        particle_shape=simulation_shape,
        solver=picmi.ElectromagneticSolver(grid=grid, method="CKC", source_smoother=picmi.BinomialSmoother()),
        time_step_size=5.15136e-17,
        max_steps=1000,
        picongpu_moving_window_move_point=0.0,
        species=species,
        layouts=[picmi.PseudoRandomLayout(n_macroparticles_per_cell=1) for _ in species],
    )
    output = tmp_path / "setup"
    simulation.write_input_file(
        output, cmake="-DPARAM_OVERWRITES:LIST='-DPARAM_FIELD_BACKGROUND=0;-DPARAM_COMPONENTWISE=1'"
    )
    context = json.loads((output / "metadata/pypicongpu_rendering_context.json").read_text())
    assert context["time_steps"] == 1000
    assert context["grid"]["cell_cnt"] == dict(zip("xyz", cells))
    assert context["grid"]["gpu_cnt"] == dict(zip("xyz", [8, 16, 8]))
    assert context["grid"]["cell_size"] == pytest.approx(dict(zip("xyz", cell_size)))
    rendered = (output / "include/picongpu/param/speciesDefinition.param").read_text()
    for name, shape in [("e", "PQS"), ("linear_e", "CIC"), ("default_e", inherited_shape)]:
        assert_species_shape_and_interpolation(rendered, name, shape)
    assert not (output / ".build").exists()
