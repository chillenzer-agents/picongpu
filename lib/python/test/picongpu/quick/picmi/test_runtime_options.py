"""PIConGPU runtime controls: omission, strict validation and explicit False."""

import pytest
from pydantic import ValidationError

from picongpu import picmi, templates
from picongpu.pypicongpu.rendering import Renderer
from picongpu.pypicongpu.simulation import Simulation as BackendSimulation


def simulation(**options):
    grid = picmi.Cartesian3DGrid(
        number_of_cells=[32] * 3,
        lower_bound=[0] * 3,
        upper_bound=[1e-5] * 3,
        lower_boundary_conditions=["periodic"] * 3,
        upper_boundary_conditions=["periodic"] * 3,
    )
    return picmi.Simulation(
        solver=picmi.ElectromagneticSolver(grid=grid, method="Yee"),
        time_step_size=1e-16,
        max_steps=1000,
        **options,
    )


@pytest.mark.parametrize("adjust", [None, False, True])
@pytest.mark.parametrize("percent", [None, 1, 100])
def test_runtime_options_conversion_and_rendering(adjust, percent):
    backend = simulation(picongpu_auto_adjust_grid=adjust, picongpu_progress_percent=percent).get_as_pypicongpu()
    assert backend.auto_adjust_grid is adjust
    assert backend.progress_percent == percent
    cfg = Renderer.get_rendered_template(
        Renderer.get_context_preprocessed(backend.get_rendering_context()),
        (templates.path() / "etc/picongpu/N.cfg.mustache").read_text(),
    )
    if adjust is None:
        assert "--autoAdjustGrid" not in cfg
    else:
        assert f"--autoAdjustGrid {str(adjust).lower()}" in cfg
    if percent is None:
        assert "--percent" not in cfg
    else:
        assert f"--percent {percent}" in cfg


@pytest.mark.parametrize(
    "name, value",
    [
        ("auto_adjust_grid", "false"),
        ("auto_adjust_grid", 0),
        ("auto_adjust_grid", 1),
        ("progress_percent", True),
        ("progress_percent", "1"),
        ("progress_percent", 1.5),
        ("progress_percent", 0),
        ("progress_percent", -1),
        ("progress_percent", 101),
    ],
)
@pytest.mark.parametrize("layer", ["frontend", "backend"])
def test_runtime_options_reject_invalid_values(name, value, layer):
    with pytest.raises(ValidationError, match=name):
        if layer == "frontend":
            simulation(**{f"picongpu_{name}": value})
        else:
            BackendSimulation(**(dict(simulation().get_as_pypicongpu()) | {name: value}))
