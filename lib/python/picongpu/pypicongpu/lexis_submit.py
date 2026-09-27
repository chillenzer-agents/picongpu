"""
Submit a PIConGPU LEXIS workflow via Py4Lexis (task 11 proof-of-concept).

This is the **submission counterpart** to :mod:`pypicongpu.lexis_workflow`
(which *generates* the LWD). It drives the LEXIS platform through Py4Lexis:

1. **create** the workflow (DAG) from the LWD (*requires the Py4Lexis patch*,
   ``patches/py4lexis-create-workflow.diff``);
2. **execute** the workflow (start a dag run);
3. **poll** the run state until it reaches a terminal state.

Py4Lexis is an **optional** dependency, installed from the IT4I package index
with the ``[efp]`` extra so the session points at the EFP::

    pip install "py4lexis[efp]" --index-url \\
        https://opencode.it4i.eu/api/v4/projects/107/packages/pypi/simple
    pip apply patches/py4lexis-create-workflow.diff   # add create_workflow

In ``dry_run`` mode (the default) **no network call is made**: the submission
plan is built and returned, which is what the quick tests exercise. Live
submission requires an EFP login (``B2Access``/``MyAccessID``) and the patch.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def build_submission_plan(lwd: dict[str, Any], project: str | None = None) -> dict[str, Any]:
    """Build the ordered submission steps for an LWD (pure, no network)."""
    project_shortname = project or lwd.get("project_shortname")
    return {
        "workflow_id": lwd.get("id"),
        "project_shortname": project_shortname,
        "jobs": list(lwd.get("jobs", {})),
        "steps": [
            {"action": "create_workflow", "project": project_shortname},
            {"action": "execute_workflow", "workflow_id": "{dag_id}"},
            {"action": "poll_state", "workflow_id": "{dag_id}"},
        ],
    }


def submit(
    lwd_path,
    *,
    dry_run: bool = True,
    project: str | None = None,
    session=None,
) -> dict[str, Any]:
    """Submit the LWD at ``lwd_path`` to LEXIS.

    Parameters
    ----------
    lwd_path : str | Path
        Path to the ``workflow.lwd.yaml`` produced by the runner.
    dry_run : bool
        If True (default), build and return the submission plan without any
        network call. If False, use a Py4Lexis session to create/execute/poll.
    project : str | None
        Optional LEXIS project short-name override.
    session : py4lexis session | None
        A logged-in Py4Lexis ``LexisSession`` (required only when ``dry_run``
        is False).
    """
    from .lexis_workflow import lwd_from_yaml

    lwd = lwd_from_yaml(Path(lwd_path).read_text())
    plan = build_submission_plan(lwd, project=project)

    if dry_run:
        return {"dry_run": True, "plan": plan, "lwd": lwd}

    if session is None:
        raise RuntimeError(
            "live lexis submission requires a logged-in Py4Lexis session "
            "(see the module docstring for installation / EFP login)."
        )
    # Live path: needs the patched Py4Lexis + EFP access. Imports are deferred
    # so py4lexis stays an optional dependency (not imported in dry_run mode).
    from py4lexis import Airflow  # type: ignore[import-not-found]

    airflow = Airflow(session)
    created: dict[str, Any] = airflow.create_workflow(lwd, project=project)
    dag_id = created.get("dag_id") or created.get("id") or plan["workflow_id"]
    run: dict[str, Any] = airflow.execute_workflow(dag_id, workflow_parameters={})
    return {
        "dry_run": False,
        "plan": plan,
        "created": created,
        "dag_id": dag_id,
        "run": run,
    }


def wait_for_completion(session, workflow_id: str, *, interval_s: float = 30.0, timeout_s: float = 6 * 3600):
    """Poll a workflow run until it reaches a terminal state (live path)."""
    import time

    from py4lexis import Airflow  # type: ignore[import-not-found]

    airflow = Airflow(session)
    terminal = {"success", "failed", "error"}
    deadline = time.monotonic() + timeout_s
    state: str | None = None
    while time.monotonic() < deadline:
        runs = airflow.get_workflow_states(workflow_id)
        if runs:
            state = runs[0].get("state") if isinstance(runs[0], dict) else None
            if state in terminal:
                return {"workflow_id": workflow_id, "state": state}
        time.sleep(interval_s)
    return {"workflow_id": workflow_id, "state": state, "timed_out": True}
