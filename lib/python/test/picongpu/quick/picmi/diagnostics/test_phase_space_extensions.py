"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
License: GPLv3+
"""

import json
import re
import shlex
from collections import defaultdict

import pytest
from pydantic import ValidationError

from picongpu import picmi
from picongpu.picmi import constants
from picongpu.picmi.diagnostics import PhaseSpace, TS
from picongpu.pypicongpu.output.phase_space import PhaseSpace as BackendPhaseSpace
from picongpu.pypicongpu.rendering import Renderer
from picongpu.pypicongpu.simulation import Simulation as BackendSimulation
from picongpu import templates


def diagnostic(species=None, **options):
    species = species or picmi.Species(name="e", particle_type="electron")
    return PhaseSpace(
        **(
            dict(
                species=species,
                period=TS[::812],
                spatial_coordinate="x",
                momentum_coordinate="px",
                min_momentum=-20 * constants.m_e * constants.c,
                max_momentum=20 * constants.m_e * constants.c,
            )
            | options
        )
    )


def convert(diag):
    return diag.get_as_pypicongpu(time_step_size=5.15136e-17, num_steps=1000)


def make_simulation(diagnostics=()):
    cells = [3584, 3584, 1792]
    dx = [6.177353e-8, 3.088676e-8, 6.177353e-8]
    grid = picmi.Cartesian3DGrid(
        number_of_cells=cells,
        lower_bound=[0.0] * 3,
        upper_bound=[n * d for n, d in zip(cells, dx)],
        lower_boundary_conditions=["open"] * 3,
        upper_boundary_conditions=["open"] * 3,
        picongpu_n_gpus=[8, 16, 8],
        picongpu_super_cell_size=[8, 8, 8],
    )
    sim = picmi.Simulation(
        solver=picmi.ElectromagneticSolver(grid=grid, method="CKC"),
        time_step_size=5.15136e-17,
        max_steps=1000,
        picongpu_min_weighting=0.1,
        picongpu_moving_window_move_point=0.0,
    )
    seen = set()
    for diag in diagnostics:
        species = diag.species.species if isinstance(diag.species, picmi.FilteredSpecies) else diag.species
        if species.name not in seen:
            layout = picmi.PseudoRandomLayout(n_macroparticles_per_cell=1) if species.initial_distribution else None
            sim.add_species(species, layout=layout)
            seen.add(species.name)
        sim.add_diagnostic(diag)
    return sim


def options_by_species(cfg):
    """Read the generated CLI as data; never execute the shell configuration."""
    body = re.search(r'pypicongpu_output_with_newlines="(.*?)"', cfg, re.S)[1]
    tokens = shlex.split(body)
    options = defaultdict(lambda: defaultdict(list))
    for i, token in enumerate(tokens):
        match = re.fullmatch(r"--(\w+)_phaseSpace\.(\w+)", token)
        if match:
            options[match[1]][match[2]].append(tokens[i + 1])
    return options


def render_cfg(backend):
    template = (templates.path() / "etc/picongpu/N.cfg.mustache").read_text()
    return Renderer.get_rendered_template(
        Renderer.get_context_preprocessed(backend.get_rendering_context()), template
    )


@pytest.mark.parametrize("extension", [None, "bp", "bp4", "bp5", "h5", "json", "future_backend-1"])
def test_extension_conversion_and_serialization(extension):
    backend = convert(diagnostic(picongpu_extension=extension))
    assert backend.extension == extension
    assert json.loads(backend.model_dump_json())["extension"] == extension
    assert BackendPhaseSpace(**dict(backend)).extension == extension


def test_omission_preserves_plugin_default():
    backend = convert(diagnostic())
    assert backend.extension is None
    parameters = dict(backend)
    parameters.pop("extension")
    assert BackendPhaseSpace(**parameters).extension is None
    cfg = render_cfg(make_simulation([diagnostic()]).get_as_pypicongpu())
    assert "_phaseSpace.ext" not in cfg


@pytest.mark.parametrize("layer", ["picmi", "backend"])
@pytest.mark.parametrize("extension", ["", ".bp", "bp\n", " bp", "bp h5", "foo/bar", "bp;echo", "$(echo)", True, 1])
def test_invalid_extension_tokens(layer, extension):
    with pytest.raises(ValidationError):
        if layer == "picmi":
            diagnostic(picongpu_extension=extension)
        else:
            BackendPhaseSpace(**(dict(convert(diagnostic())) | {"extension": extension}))


@pytest.mark.parametrize("extensions", [[None, None], ["bp", "bp"], ["bp", "h5"], ["bp", None], ["h5", None, None]])
def test_per_instance_values_and_trailing_defaults(extensions):
    species = picmi.Species(name="e", particle_type="electron")
    diagnostics = [
        diagnostic(species, picongpu_extension=ext, spatial_coordinate=axis)
        for ext, axis in zip(extensions, "xyz")
    ]
    backend = make_simulation(diagnostics).get_as_pypicongpu()
    options = options_by_species(render_cfg(backend))["e"]
    explicit = [ext for ext in extensions if ext is not None]
    assert options["ext"] == explicit
    assert options["space"] == list("xyz"[: len(extensions)])
    # multi::Option::get(id) uses the default only beyond the explicit vector.
    resolved = [options["ext"][i] if i < len(explicit) else None for i in range(len(extensions))]
    assert resolved == extensions


@pytest.mark.parametrize("layer", ["picmi", "backend"])
@pytest.mark.parametrize("extensions", [[None, "bp"], ["bp", None, "h5"], [None, None, "bp"]])
def test_default_before_explicit_extension_rejected(layer, extensions):
    species = picmi.Species(name="e", particle_type="electron")
    diagnostics = [diagnostic(species, picongpu_extension=ext) for ext in extensions]
    with pytest.raises(ValidationError, match="species 'e'.*omitted extension"):
        if layer == "picmi":
            make_simulation(diagnostics).get_as_pypicongpu()
        else:
            parameters = dict(make_simulation().get_as_pypicongpu())
            BackendSimulation(**(parameters | {"output": [convert(d) for d in diagnostics]}))


def test_species_index_independent_but_filters_share_it():
    electrons = picmi.Species(name="e", particle_type="electron")
    ions = picmi.Species(name="ions", particle_type="proton")
    positive = picmi.FilteredSpecies(
        species=electrons,
        functor=picmi.ParticleFilter(name="positive", functor=lambda p: p.get("momentum")[0] > 0),
    )
    diagnostics = [diagnostic(electrons), diagnostic(ions, picongpu_extension="h5")]
    options = options_by_species(render_cfg(make_simulation(diagnostics).get_as_pypicongpu()))
    assert options["e"]["ext"] == []
    assert options["ions"]["ext"] == ["h5"]
    diagnostics.append(diagnostic(positive, picongpu_extension="bp"))
    with pytest.raises(ValidationError, match="species 'e'.*omitted extension"):
        make_simulation(diagnostics).get_as_pypicongpu()
    diagnostics[0] = diagnostic(electrons, picongpu_extension="h5")
    options = options_by_species(render_cfg(make_simulation(diagnostics).get_as_pypicongpu()))
    assert options["e"]["ext"] == ["h5", "bp"]
    assert options["e"]["filter"] == ["all", "positive"]
    assert options["ions"]["ext"] == ["h5"]


def test_seven_reference_phase_spaces_generate(tmp_path):
    species = picmi.Species(
        name="e", particle_type="electron", initial_distribution=picmi.UniformDistribution(density=1e25)
    )
    rows = [
        ("x", "px", -20, 20),
        ("x", "pz", -20, 20),
        ("y", "px", -20, 20),
        ("y", "pz", -20, 20),
        ("y", "py", -50, 2000),
        ("x", "py", -50, 2000),
        ("z", "py", -50, 2000),
    ]
    mc = species.picongpu_get_mass_si() * constants.c
    sim = make_simulation(
        [
            diagnostic(
                species,
                spatial_coordinate=axis,
                momentum_coordinate=momentum,
                min_momentum=lower * mc,
                max_momentum=upper * mc,
                picongpu_extension="bp",
            )
            for axis, momentum, lower, upper in rows
        ]
    )
    output = tmp_path / "setup"
    sim.write_input_file(
        output, cmake="-DPARAM_OVERWRITES:LIST='-DPARAM_FIELD_BACKGROUND=0;-DPARAM_COMPONENTWISE=1'"
    )
    cfg = (output / "etc/picongpu/N.cfg").read_text()
    options = options_by_species(cfg)["e"]
    assert options["space"] == [r[0] for r in rows]
    assert options["momentum"] == [r[1] for r in rows]
    assert list(map(float, options["min"])) == pytest.approx([r[2] for r in rows])
    assert list(map(float, options["max"])) == pytest.approx([r[3] for r in rows])
    assert options["filter"] == ["all"] * 7
    assert options["ext"] == ["bp"] * 7
    assert options["period"] == ["0:-1:812"] * 7
    assert "!TBG_plugins" in cfg.split('TBG_programParams="', 1)[1]
    context = json.loads((output / "metadata/pypicongpu_rendering_context.json").read_text())
    assert context["time_steps"] == 1000
    assert context["grid"]["cell_cnt"] == dict(x=3584, y=3584, z=1792)
    assert context["grid"]["gpu_cnt"] == dict(x=8, y=16, z=8)
    assert len([o for o in context["output"] if o.get("type_phasespace")]) == 7
    assert not (output / ".build").exists()
