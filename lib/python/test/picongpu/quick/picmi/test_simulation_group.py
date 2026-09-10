"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory

from cwltool.context import RuntimeContext
from cwltool.factory import Factory, WorkflowStatus
from picongpu.picmi import Cartesian3DGrid, ElectromagneticSolver, Simulation, SimulationGroup
from picongpu.picmi import simulation_group as _simulation_group
from pytest import fixture, raises
from rocrate_validator.services import validate


def _make_sim():
    number_of_cells = 32
    cell_size = 1
    return Simulation(
        time_step_size=17,
        max_steps=4,
        solver=ElectromagneticSolver(
            method="Yee",
            grid=Cartesian3DGrid(
                number_of_cells=[number_of_cells, number_of_cells, number_of_cells],
                lower_bound=[0, 0, 0],
                upper_bound=list(map(lambda x: number_of_cells * x, [cell_size, cell_size, cell_size])),
                # required, otherwise won't spawn
                lower_boundary_conditions=["open", "open", "periodic"],
                upper_boundary_conditions=["open", "open", "periodic"],
            ),
        ),
    )


def _issue_signatures(crate_dir):
    """The set of REQUIRED RO-Crate validation issue messages for a crate."""
    return {
        issue.message
        for issue in validate(settings={"rocrate_uri": crate_dir, "requirement_severity": "REQUIRED"}).get_issues()
    }


def _root_dataset(crate_dir):
    data = json.loads((Path(crate_dir) / "ro-crate-metadata.json").read_text())
    return next(entity for entity in data["@graph"] if entity["@id"] == "./")


def _main_entity_id(root):
    main = root["mainEntity"]
    return main[0]["@id"] if isinstance(main, list) else main["@id"]


def _as_id_list(value):
    value = value if isinstance(value, list) else [value]
    return [entry["@id"] for entry in value]


@fixture
def simulations():
    return [_make_sim(), _make_sim()]


@fixture
def group_dir(simulations):
    with TemporaryDirectory() as d:
        # Explicit names: the default names are now unique uuids (see
        # test_default_names_are_unique_hashed); these layout/RO-Crate tests want
        # a deterministic layout to assert against.
        SimulationGroup(simulations, names=["sim_00", "sim_01"]).write_input_file(d, exist_ok=True)
        yield Path(d)


@fixture
def standalone_baseline():
    """A single, standalone simulation crate to use as the validation baseline."""
    with TemporaryDirectory() as d:
        _make_sim().write_input_file(d, exist_ok=True)
        yield Path(d)


def test_default_names_are_unique_hashed(simulations):
    group = SimulationGroup(simulations)
    assert len(group.names) == 2
    # 8-hex-char hash suffix per default name.
    assert all(re.fullmatch(r"sim_[0-9a-f]{8}", name) for name in group.names)
    # Two independent groups get independent (non-colliding) default names.
    other = SimulationGroup(simulations)
    assert not (set(group.names) & set(other.names))


def test_custom_names_are_used(simulations):
    group = SimulationGroup(simulations, names=["a", "b"])
    assert group.names == ["a", "b"]


def test_empty_group_rejected():
    with raises(ValueError):
        SimulationGroup([])


def test_duplicate_names_rejected(simulations):
    with raises(ValueError):
        SimulationGroup(simulations, names=["same", "same"])


def test_write_input_file_produces_group_layout(group_dir):
    for name in ("sim_00", "sim_01"):
        assert (group_dir / name / "workflow" / "workflow.cwl").is_file()
        assert (group_dir / name / "ro-crate-metadata.json").is_file()
    assert (group_dir / "workflow" / "group_workflow.cwl").is_file()
    assert (group_dir / "ro-crate-metadata.json").is_file()


def test_write_input_file_with_custom_names(simulations):
    with TemporaryDirectory() as d:
        d = Path(d)
        SimulationGroup(simulations, names=["alpha", "beta"]).write_input_file(d, exist_ok=True)
        assert (d / "alpha" / "workflow" / "workflow.cwl").is_file()
        assert (d / "beta" / "workflow" / "workflow.cwl").is_file()
        assert not (d / "sim_00").exists()


def test_root_rocrate_main_entity_is_the_group_workflow(group_dir):
    assert _main_entity_id(_root_dataset(group_dir)) == "workflow/group_workflow.cwl"


def test_root_rocrate_points_at_each_subcrate_via_has_content_section(group_dir):
    sections = _root_dataset(group_dir)["hasContentSection"]
    assert _as_id_list(sections) == ["sim_00/", "sim_01/"]


def test_each_subcrate_keeps_its_own_main_entity(group_dir):
    for name in ("sim_00", "sim_01"):
        assert _main_entity_id(_root_dataset(group_dir / name)) == "workflow/workflow.cwl"


def test_run_creates_cwl_cache_dir_before_invoking_cwltool(simulations, monkeypatch):
    # Regression: `run()` must create `<group_dir>/.cwl_cache` before handing it
    # to cwltool as `cachedir`; otherwise cwltool fails to open the per-step job
    # cache lock on a fresh dir (FileNotFoundError -> permanentFail).
    captured = {}

    class _StubFactory:
        def __init__(self, runtime_context):
            captured["cachedir"] = runtime_context.cachedir

        def make(self, _path):
            def _run(*_args, **_kwargs):
                return None

            return _run

    monkeypatch.setattr(_simulation_group, "WorkflowFactory", _StubFactory)
    with TemporaryDirectory() as d:
        d = Path(d)
        SimulationGroup(simulations).run(d, exist_ok=True)
        cache = Path(captured["cachedir"])
        assert cache == d / ".cwl_cache"
        assert cache.is_dir()


def test_group_workflow_passes_cwltool_validate_only(group_dir):
    # `validate_only` signals success by raising WorkflowStatus("Completed ValidationSuccess"),
    # mirroring test_workflow.py.
    with raises(WorkflowStatus, match="Completed ValidationSuccess"):
        Factory(runtime_context=RuntimeContext(kwargs={"validate_only": True})).make(
            str(group_dir / "workflow" / "group_workflow.cwl")
        )()


def test_group_rocrate_introduces_no_new_issues(group_dir, standalone_baseline):
    baseline = _issue_signatures(standalone_baseline)
    # The root group crate must not add any REQUIRED issue beyond what a
    # standalone simulation crate already reports (the group adds the missing
    # license and content-section metadata on top of the per-sim setup).
    assert _issue_signatures(group_dir) <= baseline


def test_each_subcrate_still_validates_like_a_standalone_sim(group_dir, standalone_baseline):
    baseline = _issue_signatures(standalone_baseline)
    # Writing the group must not perturb the self-contained sub-crates.
    for name in ("sim_00", "sim_01"):
        assert _issue_signatures(group_dir / name) == baseline
