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

import yaml
from cwltool.context import RuntimeContext
from cwltool.factory import Factory, WorkflowStatus
from picongpu.picmi import Cartesian3DGrid, ElectromagneticSolver, Simulation, SimulationGroup
from picongpu.picmi import simulation_group as _simulation_group
from pydantic import ValidationError
from pytest import fixture, mark, raises
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
def flat_group(simulations):
    """A deterministic, single-level group used for layout / RO-Crate assertions."""
    return SimulationGroup(simulations={"alpha": simulations[0], "beta": simulations[1]})


@fixture
def group_dir(flat_group):
    with TemporaryDirectory() as d:
        flat_group.write_input_file(d, exist_ok=True)
        yield Path(d)


@fixture
def standalone_baseline():
    """A single, standalone simulation crate to use as the validation baseline."""
    with TemporaryDirectory() as d:
        _make_sim().write_input_file(d, exist_ok=True)
        yield Path(d)


def test_list_shortcut_generates_unique_default_names(simulations):
    group = SimulationGroup(simulations=simulations)
    names = [path for path, _ in group.simulations_by_path]
    assert len(names) == 2
    # Default names are unique hashed folder names (``sim_<8-hex>``).
    assert all(re.fullmatch(r"sim_[0-9a-f]{8}", name) for name in names)
    # Two independent groups get independent (non-colliding) default names.
    other = SimulationGroup(simulations=simulations)
    assert not (set(names) & set([path for path, _ in other.simulations_by_path]))


def test_dict_interface_keeps_explicit_names(simulations):
    group = SimulationGroup(simulations={"alpha": simulations[0], "beta": simulations[1]})
    assert [path for path, _ in group.simulations_by_path] == ["alpha", "beta"]


def test_single_simulation_group():
    sim = _make_sim()
    group = SimulationGroup(simulations={"solo": sim})
    assert group.simulations_by_path == [("solo", sim)]


def test_empty_group_rejected():
    with raises(ValidationError):
        SimulationGroup(simulations={})
    with raises(ValidationError):
        SimulationGroup(simulations=[])


@mark.parametrize("bad_name", ["with/slash", ".hidden", ""])
def test_invalid_names_rejected(bad_name):
    with raises(ValidationError):
        SimulationGroup(simulations={bad_name: _make_sim()})


def test_write_input_file_produces_group_layout(group_dir):
    for name in ("alpha", "beta"):
        assert (group_dir / name / "workflow" / "workflow.cwl").is_file()
        assert (group_dir / name / "ro-crate-metadata.json").is_file()
    assert (group_dir / "workflow" / "group_workflow.cwl").is_file()
    assert (group_dir / "ro-crate-metadata.json").is_file()


def test_nested_dict_interface_produces_nested_layout(simulations):
    # The nested-dict interface: each entry may be a Simulation or a (nested) dict.
    group = SimulationGroup(
        simulations={
            "my_folder": {"name_of_sim_1": simulations[0], "name_of_sim_2": simulations[1]},
            "solo": _make_sim(),
        }
    )
    with TemporaryDirectory() as d:
        d = Path(d)
        group.write_input_file(d, exist_ok=True)
        for rel in ("my_folder/name_of_sim_1", "my_folder/name_of_sim_2", "solo"):
            assert (d / rel / "workflow" / "workflow.cwl").is_file()
            assert (d / rel / "ro-crate-metadata.json").is_file()
        # The nested folder is itself a self-contained sub-group.
        assert (d / "my_folder" / "workflow" / "group_workflow.cwl").is_file()
        assert (d / "my_folder" / "ro-crate-metadata.json").is_file()
        # The root references its top-level entries only.
        assert _as_id_list(_root_dataset(d)["hasContentSection"]) == ["my_folder/", "solo/"]


def test_root_rocrate_main_entity_is_the_group_workflow(group_dir):
    assert _main_entity_id(_root_dataset(group_dir)) == "workflow/group_workflow.cwl"


def test_root_rocrate_points_at_each_top_level_entry(group_dir):
    assert _as_id_list(_root_dataset(group_dir)["hasContentSection"]) == ["alpha/", "beta/"]


def test_each_subcrate_keeps_its_own_main_entity(group_dir):
    for name in ("alpha", "beta"):
        assert _main_entity_id(_root_dataset(group_dir / name)) == "workflow/workflow.cwl"


def test_group_workflow_steps_read_sub_sim_input_yaml(group_dir):
    # The group workflow must not re-derive sub-simulation inputs; it re-uses the
    # self-contained inputs recorded in each sub-simulation's `workflow/input.yaml`.
    workflow = yaml.safe_load((group_dir / "workflow" / "group_workflow.cwl").read_text())
    step = workflow["steps"]["alpha_step"]
    assert step["run"] == "../alpha/workflow/workflow.cwl"
    for key, cwl_class in (
        ("build_include_directory", "Directory"),
        ("build_script", "File"),
        ("run_etc_directory", "Directory"),
        ("run_project_path", "Directory"),
    ):
        assert step["in"][key]["default"]["class"] == cwl_class
    # Scalar run/build flags are forwarded as step defaults too.
    assert "build_jobs" in step["in"]
    assert "run_cfg_file" in step["in"]


def test_group_workflow_steps_propagate_user_flags():
    # Runtime flags passed to write_input_file must reach each sub-simulation and be
    # re-used as the nested step defaults (single source of truth: input.yaml).
    with TemporaryDirectory() as d:
        d = Path(d)
        group = SimulationGroup(simulations={"alpha": _make_sim(), "beta": _make_sim()})
        group.write_input_file(d, exist_ok=True, jobs=7, cmake="-DPIC_VERBOSE=21")
        for name in ("alpha", "beta"):
            job = json.loads((d / name / "workflow" / "input.yaml").read_text())
            assert job["build_jobs"] == 7
            assert job["build_cmake"] == "-DPIC_VERBOSE=21"
        workflow = yaml.safe_load((d / "workflow" / "group_workflow.cwl").read_text())
        for name in ("alpha", "beta"):
            step = workflow["steps"][f"{name}_step"]
            assert step["in"]["build_jobs"] == {"default": 7}
            assert step["in"]["build_cmake"] == {"default": "-DPIC_VERBOSE=21"}


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
        SimulationGroup(simulations=simulations).run(d, exist_ok=True)
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
    for name in ("alpha", "beta"):
        assert _issue_signatures(group_dir / name) == baseline
