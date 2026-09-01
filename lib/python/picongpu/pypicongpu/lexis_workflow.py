"""
Generate a LEXIS Workflow Definition (LWD) from a PIConGPU configuration.

This is the **lexis-workflow counterpart** to the CWL workflow that the runner
normally generates (``workflow.cwl``: build -> prepare_submission -> submit ->
organize_output, orchestrated by cwltool on the laptop). A LEXIS workflow is a
YAML document describing one or more **HPC job nodes** that the LEXIS
orchestration service (Apache Airflow + the LEXIS provider) executes across the
EuroHPC Federation Platform (EFP), with input/output **dataset staging** handled
by the LEXIS Distributed Data Infrastructure (DDI).

See the LEXIS Workflow Definition documentation:
https://docs.lexis.tech/user_interfaces/lexis_workflow_definition.html

This module is pure Python (YAML in / YAML out) and is the solid, fully
testable core of the lexis submission proof-of-concept (task 11). It does not
require network access or an EFP login.
"""

from __future__ import annotations

from typing import Any

import yaml

from pydantic import BaseModel, Field


class LexisJobSpec(BaseModel):
    """The ``requirements`` of a single LWD HPC job node (flat, TOML-friendly)."""

    command_template_name: str = Field(description="Name of a command template registered in the LEXIS project")
    location_name: str = Field(description="Target computing cluster")
    location_resource: str | None = Field(default=None, description="Optional specific resource on the cluster")
    walltime_limit: int = Field(7200, description="Max runtime, seconds")
    max_cores: int | None = None
    policy: str = Field("preferred", description="'preferred' or 'required'")
    node_type_name: str | None = None
    template_parameters: dict[str, str] | None = None

    def as_lwd(self) -> dict[str, Any]:
        location: dict[str, str] = {"location_name": self.location_name}
        if self.location_resource is not None:
            location["location_resource"] = self.location_resource
        requirements: dict[str, Any] = {
            "command_template_name": self.command_template_name,
            "locations": [location],
            "walltime_limit": self.walltime_limit,
            "policy": self.policy,
        }
        if self.max_cores is not None:
            requirements["max_cores"] = self.max_cores
        if self.node_type_name is not None:
            requirements["node_type_name"] = self.node_type_name
        if self.template_parameters:
            requirements["template_parameters"] = self.template_parameters
        return requirements


class LexisWorkflowSpec(BaseModel):
    """Everything needed to render a PIConGPU LWD workflow.

    Provided via ``picongpurc.toml`` as a ``[lexis]`` table (plus the top-level
    ``workflow_backend = "lexis"`` toggle). See ``parse_lexis_config``.
    """

    project_shortname: str = Field(description="LEXIS project short name")
    # The (run) job is always present; an optional separate build job enables
    # the two-node (build -> run) mapping of the CWL pipeline.
    run: LexisJobSpec
    build: LexisJobSpec | None = Field(default=None, description="Optional separate build job (two-node variant)")
    # Input: the PIConGPU setup_dir, staged from a DDI dataset into /input.
    input_dataset: str = Field(description="ddi:// source of the staged PIConGPU setup (input dataset)")
    # Output: the simulation output, staged out to a new DDI dataset.
    output_name: str = Field("picongpu_output", description="Internal $name ref")
    output_title: str = "PIConGPU simulation output"
    output_access: str = Field("project", description="'public' | 'project' | 'private'")

    def _output(self) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "$name": self.output_name,
            "title": self.output_title,
            "access": self.output_access,
        }
        return {"source": "output/", "target": "ddi://~", "metadata": metadata}

    def build_lwd(self, *, workflow_id: str, description: str = "PIConGPU simulation") -> dict[str, Any]:
        """Render the LWD as a plain dict (one or two HPC job nodes)."""
        if self.build is None:
            jobs: dict[str, Any] = {
                "picongpu": {
                    "requirements": self.run.as_lwd(),
                    "data_inputs": [{"source": self.input_dataset, "target": "input/"}],
                    "data_outputs": [self._output()],
                }
            }
        else:
            # Two-node mapping of the CWL pipeline: build -> run, sharing the
            # built binary via job-to-job data transfer ($name: picongpu_bin).
            jobs = {
                "build": {
                    "requirements": self.build.as_lwd(),
                    "data_inputs": [{"source": self.input_dataset, "target": "input/"}],
                    "data_outputs": [{"source": "bin/", "metadata": {"$name": "picongpu_bin"}}],
                },
                "run": {
                    "requirements": self.run.as_lwd(),
                    "data_inputs": [
                        {"source": "job://build/picongpu_bin", "target": "bin/"},
                        {"source": self.input_dataset, "target": "input/"},
                    ],
                    "data_outputs": [self._output()],
                },
            }
        return {
            "id": workflow_id,
            "desc": description,
            "project_shortname": self.project_shortname,
            "jobs": jobs,
            "metadata": {"catchup": False},
        }

    def to_yaml(self, *, workflow_id: str, description: str = "PIConGPU simulation") -> str:
        """Render the LWD as a YAML string."""
        return yaml.safe_dump(self.build_lwd(workflow_id=workflow_id, description=description), sort_keys=False)


def parse_lexis_config(rc_params) -> LexisWorkflowSpec:
    """Build a :class:`LexisWorkflowSpec` from ``rc_params``.

    Reads the ``[lexis]`` table (a nested dict under the ``lexis`` key) from
    ``rc_params.model_dump()``. RCParams is a dict-backed model with
    ``extra="allow"``, so a ``[lexis]`` table in ``picongpurc.toml`` passes
    through as a plain dict.

    Two forms are accepted:
      * nested: ``[lexis]`` holds the workflow-level keys plus a ``[lexis.run]``
        (and optional ``[lexis.build]``) sub-table describing the job(s);
      * flat: ``[lexis]`` directly holds the run-job keys (``command_template_name``,
        ``location_name``, ...) alongside the workflow-level keys.
    """
    data = rc_params.model_dump()
    lexis = data.get("lexis") or {}
    if not lexis:
        raise ValueError(
            "workflow_backend is 'lexis' but no [lexis] table was provided in "
            "picongpurc.toml (need at least: project_shortname, command_template_name, "
            "location_name, input_dataset)."
        )
    if "run" not in lexis and "command_template_name" in lexis:
        job_keys = {
            "command_template_name",
            "location_name",
            "location_resource",
            "walltime_limit",
            "max_cores",
            "policy",
            "node_type_name",
            "template_parameters",
        }
        run = {k: lexis[k] for k in job_keys if k in lexis}
        rest = {k: v for k, v in lexis.items() if k not in job_keys and k != "build"}
        lexis = {**rest, "run": run, **({"build": lexis["build"]} if "build" in lexis else {})}
    return LexisWorkflowSpec(**lexis)


def lwd_from_yaml(text: str) -> dict[str, Any]:
    """Parse an LWD YAML document back to a dict (inverse of ``to_yaml``)."""
    return yaml.safe_load(text)
