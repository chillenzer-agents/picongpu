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
from picongpu.pypicongpu.species.species import CurrentDeposition, Shape
from picongpu.pypicongpu.species.species import Species as BackendSpecies


TEMPLATE = (
    Path(picmi.__file__).resolve().parents[1]
    / "templates/include/picongpu/param/speciesDefinition.param.mustache"
)


def render_species(*species):
    context = {"species": [s.get_rendering_context() for s in species]}
    return Renderer.get_rendered_template(Renderer.get_context_preprocessed(context), TEMPLATE.read_text())


def assert_species_methods(rendered, name, algorithm, shape):
    """Resolve species shape aliases and compare the actual C++ flag types."""
    aliases = dict(re.findall(r"using\s+(\w+)\s*=\s*(particles::shapes::\w+)\s*;", rendered))
    flags = re.search(rf"using ParticleFlags_species_{name}\s*=\s*MakeSeq_t<(.*?)>;", rendered, re.S)
    assert flags is not None
    resolved = re.sub(r"\b\w+\b", lambda m: aliases.get(m[0], m[0]), flags[1])
    resolved = re.sub(r"\s+", "", resolved)
    assert f"shape<particles::shapes::{shape}>" in resolved
    assert (
        f"interpolation<FieldToParticleInterpolation<particles::shapes::{shape},AssignedTrilinearInterpolation>>"
        in resolved
    )
    assert f"current<currentSolver::{algorithm}<particles::shapes::{shape}>>" in resolved


@pytest.mark.parametrize(
    "algorithm,shape,cpp_shape",
    [
        ("Esirkepov", "NGP", "NGP"),
        ("Esirkepov", "linear", "CIC"),
        ("Esirkepov", "quadratic", "TSC"),
        ("Esirkepov", "cubic", "PQS"),
        ("Esirkepov", "other:quartic", "PCS"),
        ("EmZ", "linear", "CIC"),
        ("EmZ", "quadratic", "TSC"),
        ("EmZ", "cubic", "PQS"),
        ("EmZ", "other:quartic", "PCS"),
        ("EZ", "linear", "CIC"),
        ("EZ", "quadratic", "TSC"),
        ("EZ", "cubic", "PQS"),
        ("EZ", "other:quartic", "PCS"),
    ],
)
def test_deposition_conversion_and_rendering(algorithm, shape, cpp_shape):
    species = picmi.Species(
        name="e", particle_type="electron", particle_shape=shape, picongpu_current_deposition=algorithm
    ).get_as_pypicongpu()
    canonical = "EmZ" if algorithm == "EZ" else algorithm
    assert species.current_deposition == CurrentDeposition(canonical)
    context = species.get_rendering_context()
    assert context["current_deposition"] == canonical
    assert BackendSpecies.model_validate(context).current_deposition == species.current_deposition
    assert_species_methods(render_species(species), "e", canonical, cpp_shape)


def test_ez_alias_has_identical_backend_context_and_rendering():
    emz = picmi.Species(
        name="e", particle_type="electron", particle_shape="cubic", picongpu_current_deposition="EmZ"
    ).get_as_pypicongpu()
    ez = picmi.Species(
        name="e", particle_type="electron", particle_shape="cubic", picongpu_current_deposition="EZ"
    ).get_as_pypicongpu()
    assert ez.get_rendering_context() == emz.get_rendering_context()
    assert render_species(ez) == render_species(emz)
    direct = BackendSpecies(name="e", constants=[], attributes=[], shape=Shape.cubic, current_deposition="EZ")
    assert direct.current_deposition is CurrentDeposition.EmZ
    assert direct.get_rendering_context()["current_deposition"] == "EmZ"


@pytest.mark.parametrize("layer", ["picmi", "backend"])
def test_default_deposition_is_esirkepov_tsc(layer):
    species = (
        picmi.Species(name="e", particle_type="electron").get_as_pypicongpu()
        if layer == "picmi"
        else BackendSpecies(name="e", constants=[], attributes=[])
    )
    assert_species_methods(render_species(species), "e", "Esirkepov", "TSC")


@pytest.mark.parametrize("layer", ["picmi", "backend"])
@pytest.mark.parametrize("value", [None, "ez", "emz", "other:EmZ", "currentSolver::EmZ<PQS>", 1])
def test_invalid_deposition_choice(layer, value):
    with pytest.raises(ValidationError):
        if layer == "picmi":
            picmi.Species(particle_type="electron", picongpu_current_deposition=value)
        else:
            BackendSpecies(name="e", constants=[], attributes=[], current_deposition=value)


@pytest.mark.parametrize("layer", ["picmi", "backend"])
@pytest.mark.parametrize("algorithm", ["EmZ", "EZ"])
def test_emz_ngp_rejected(layer, algorithm):
    with pytest.raises(ValidationError, match="EmZ current deposition does not support NGP"):
        if layer == "picmi":
            picmi.Species(
                particle_type="electron", particle_shape="NGP", picongpu_current_deposition=algorithm
            ).get_as_pypicongpu()
        else:
            BackendSpecies(name="e", constants=[], attributes=[], shape=Shape.NGP, current_deposition=algorithm)


@pytest.mark.parametrize("algorithm", ["Esirkepov", "EmZ", "EZ"])
def test_counter_remains_invalid(algorithm):
    with pytest.raises(ValidationError, match="diagnostic counting shape"):
        picmi.Species(
            particle_type="electron", particle_shape="other:counter", picongpu_current_deposition=algorithm
        ).get_as_pypicongpu()


def test_mixed_species_keep_independent_deposition_choices():
    species = [
        picmi.Species(
            name="emz_e", particle_type="electron", particle_shape="cubic", picongpu_current_deposition="EmZ"
        ),
        picmi.Species(name="cubic_e", particle_type="electron", particle_shape="cubic"),
        picmi.Species(name="linear_e", particle_type="electron", particle_shape="linear"),
        picmi.Species(name="default_e", particle_type="electron"),
    ]
    rendered = render_species(*(s.get_as_pypicongpu() for s in species))
    for name, algorithm, shape in [
        ("emz_e", "EmZ", "PQS"),
        ("cubic_e", "Esirkepov", "PQS"),
        ("linear_e", "Esirkepov", "CIC"),
        ("default_e", "Esirkepov", "TSC"),
    ]:
        assert_species_methods(rendered, name, algorithm, shape)


@pytest.mark.parametrize("smoothing", [False, True])
@pytest.mark.parametrize("algorithm", ["EmZ", "EZ"])
@pytest.mark.parametrize("simulation_shape,inherited_shape", [(None, "TSC"), ("cubic", "PQS")])
def test_current_deposition_setup_generation(smoothing, algorithm, tmp_path, simulation_shape, inherited_shape):
    """Generate on the active grid without compiling or running PIConGPU.

    Extra species verify independence; uniform density, PML and diagnostics
    are not the final migrated setup. Smoothing must not select deposition.
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
            picongpu_current_deposition=algorithm,
        ),
        picmi.Species(
            name="linear_e", particle_type="electron", particle_shape="linear", initial_distribution=plasma
        ),
        picmi.Species(name="default_e", particle_type="electron", initial_distribution=plasma),
    ]
    simulation = picmi.Simulation(
        particle_shape=simulation_shape,
        solver=picmi.ElectromagneticSolver(
            grid=grid, method="CKC", source_smoother=picmi.BinomialSmoother() if smoothing else None
        ),
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
    for name, algorithm, shape in [
        ("e", "EmZ", "PQS"),
        ("linear_e", "Esirkepov", "CIC"),
        ("default_e", "Esirkepov", inherited_shape),
    ]:
        assert_species_methods(rendered, name, algorithm, shape)
    cfg = (output / "etc/picongpu/N.cfg").read_text()
    assert ('TBG_currentInterpolation="--currentInterpolation binomial"' in cfg) == smoothing
    assert not (output / ".build").exists()
