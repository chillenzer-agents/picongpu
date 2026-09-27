"""Quick tests for the LEXIS Workflow Definition (LWD) generator (task 11).

Pure-Python: no network, no EFP login. Verifies the LWD structure, the
YAML round-trip, the two-node (build -> run) variant, and parsing of the
``[lexis]`` config from ``picongpurc.toml`` (nested + flat forms).
"""

from picongpu import rc_params
from picongpu._rc_params import RCParams
from picongpu.picmi import Cartesian3DGrid, ElectromagneticSolver, Simulation
from picongpu.pypicongpu.lexis_submit import build_submission_plan, submit
from picongpu.pypicongpu.lexis_workflow import (
    LexisJobSpec,
    LexisWorkflowSpec,
    lwd_from_yaml,
    parse_lexis_config,
)
from pytest import fixture


def _run_job():
    return LexisJobSpec(
        command_template_name="picongpu",
        location_name="jupiter",
        location_resource="gh200",
        walltime_limit=3600,
        max_cores=64,
    )


def test_single_node_lwd_structure():
    spec = LexisWorkflowSpec(
        project_shortname="picongpu",
        run=_run_job(),
        input_dataset="ddi://~/setup",
    )
    lwd = spec.build_lwd(workflow_id="wf1")
    assert lwd["id"] == "wf1"
    assert lwd["project_shortname"] == "picongpu"
    assert set(lwd["jobs"]) == {"picongpu"}
    job = lwd["jobs"]["picongpu"]
    req = job["requirements"]
    assert req["command_template_name"] == "picongpu"
    assert req["locations"] == [{"location_name": "jupiter", "location_resource": "gh200"}]
    assert req["walltime_limit"] == 3600
    assert req["max_cores"] == 64
    assert job["data_inputs"] == [{"source": "ddi://~/setup", "target": "input/"}]
    out = job["data_outputs"][0]
    assert out["target"] == "ddi://~"
    assert out["metadata"]["$name"] == "picongpu_output"
    assert out["metadata"]["access"] == "project"


def test_two_node_lwd_shares_build_output():
    spec = LexisWorkflowSpec(
        project_shortname="picongpu",
        run=_run_job(),
        build=_run_job(),
        input_dataset="ddi://~/setup",
    )
    lwd = spec.build_lwd(workflow_id="wf2")
    assert set(lwd["jobs"]) == {"build", "run"}
    run_inputs = lwd["jobs"]["run"]["data_inputs"]
    assert {"source": "job://build/picongpu_bin", "target": "bin/"} in run_inputs
    assert lwd["jobs"]["build"]["data_outputs"] == [{"source": "bin/", "metadata": {"$name": "picongpu_bin"}}]


def test_yaml_round_trip():
    spec = LexisWorkflowSpec(project_shortname="p", run=_run_job(), input_dataset="ddi://~/s")
    text = spec.to_yaml(workflow_id="wf3")
    parsed = lwd_from_yaml(text)
    assert parsed == spec.build_lwd(workflow_id="wf3")


def test_location_resource_optional():
    no_res = LexisJobSpec(command_template_name="t", location_name="c").as_lwd()["locations"][0]
    assert "location_resource" not in no_res
    with_res = LexisJobSpec(command_template_name="t", location_name="c", location_resource="rocm").as_lwd()[
        "locations"
    ][0]
    assert with_res["location_resource"] == "rocm"


def _write_rc(tmp_path, toml_text):
    p = tmp_path / "picongpurc.toml"
    p.write_text(toml_text)
    return p


def test_parse_lexis_config_nested(tmp_path):
    rc = RCParams(
        picongpurc_path=_write_rc(
            tmp_path,
            """
workflow_backend = "lexis"

[lexis]
project_shortname = "picongpu"
input_dataset = "ddi://~/setup"

[lexis.run]
command_template_name = "picongpu"
location_name = "jupiter"
location_resource = "gh200"
walltime_limit = 3600
""",
        )
    )
    assert rc["workflow_backend"] == "lexis"
    spec = parse_lexis_config(rc)
    assert spec.project_shortname == "picongpu"
    assert spec.run.location_name == "jupiter"
    assert spec.run.location_resource == "gh200"
    assert spec.build is None


def test_parse_lexis_config_flat(tmp_path):
    rc = RCParams(
        picongpurc_path=_write_rc(
            tmp_path,
            """
workflow_backend = "lexis"

[lexis]
project_shortname = "picongpu"
command_template_name = "picongpu"
location_name = "jupiter"
input_dataset = "ddi://~/setup"
""",
        )
    )
    spec = parse_lexis_config(rc)
    assert spec.run.command_template_name == "picongpu"
    assert spec.run.location_name == "jupiter"
    assert spec.build is None


def test_workflow_backend_defaults_to_cwl():
    assert RCParams()["workflow_backend"] == "cwl"


def test_parse_lexis_config_requires_table(tmp_path):
    rc = RCParams(picongpurc_path=_write_rc(tmp_path, 'workflow_backend = "lexis"\n'))
    try:
        parse_lexis_config(rc)
    except ValueError as e:
        assert "[lexis]" in str(e)
    else:
        raise AssertionError("expected ValueError for missing [lexis] table")


def test_submission_plan_dry_run(tmp_path):
    spec = LexisWorkflowSpec(project_shortname="picongpu", run=_run_job(), input_dataset="ddi://~/setup")
    lwd_path = tmp_path / "workflow.lwd.yaml"
    lwd_path.write_text(spec.to_yaml(workflow_id="wf-sub"))
    result = submit(lwd_path, dry_run=True)
    assert result["dry_run"] is True
    plan = result["plan"]
    assert plan["workflow_id"] == "wf-sub"
    assert plan["project_shortname"] == "picongpu"
    assert plan["jobs"] == ["picongpu"]
    assert [s["action"] for s in plan["steps"]] == ["create_workflow", "execute_workflow", "poll_state"]


def test_build_submission_plan_project_override():
    lwd = {"id": "wf", "project_shortname": "a", "jobs": {"picongpu": {}}}
    assert build_submission_plan(lwd)["project_shortname"] == "a"
    assert build_submission_plan(lwd, project="b")["project_shortname"] == "b"


def test_submission_live_requires_session(tmp_path):
    spec = LexisWorkflowSpec(project_shortname="picongpu", run=_run_job(), input_dataset="ddi://~/setup")
    lwd_path = tmp_path / "workflow.lwd.yaml"
    lwd_path.write_text(spec.to_yaml(workflow_id="wf-sub2"))
    try:
        submit(lwd_path, dry_run=False, session=None)
    except RuntimeError as e:
        assert "session" in str(e)
    else:
        raise AssertionError("expected RuntimeError for live submit without a session")


@fixture
def lexis_runner(tmp_path):
    """A fully generated runner with ``workflow_backend = "lexis"``.

    Mutates the module-level ``rc_params`` (generate() reads it); the temp toml
    carries ``dirty_reset_policy = "ignore"`` so both the set and the restore
    below do not raise ``DirtyResetError``.
    """
    toml = tmp_path / "picongpurc.toml"
    toml.write_text(
        'workflow_backend = "lexis"\n'
        "\n[lexis]\n"
        'project_shortname = "picongpu"\n'
        'command_template_name = "picongpu"\n'
        'location_name = "jupiter"\n'
        'input_dataset = "ddi://~/setup"\n'
    )
    # Swap the module-level rc_params data directly (bypassing the
    # picongpurc_path setter, which would raise DirtyResetError on the
    # non-default lexis content); restore the original dict on teardown.
    orig_data = dict(rc_params._data)
    rc_params._data = RCParams(picongpurc_path=toml)._data
    try:
        n, cs = 32, 1
        sim = Simulation(
            time_step_size=17,
            max_steps=4,
            solver=ElectromagneticSolver(
                method="Yee",
                grid=Cartesian3DGrid(
                    number_of_cells=[n, n, n],
                    lower_bound=[0, 0, 0],
                    upper_bound=list(map(lambda x: n * x, [cs, cs, cs])),
                    lower_boundary_conditions=["open", "open", "periodic"],
                    upper_boundary_conditions=["open", "open", "periodic"],
                ),
            ),
        )
        runner = sim.picongpu_get_runner()
        runner.generate()
        yield runner
    finally:
        rc_params._data = orig_data


def test_generate_writes_lwd(lexis_runner):
    lwd_path = lexis_runner.workflow_lwd_path
    assert lwd_path.is_file()
    parsed = lwd_from_yaml(lwd_path.read_text())
    assert parsed["project_shortname"] == "picongpu"
    assert set(parsed["jobs"]) == {"picongpu"}
    # the CWL workflow is still generated alongside (non-destructive)
    assert lexis_runner.workflow_definition_path.is_file()
