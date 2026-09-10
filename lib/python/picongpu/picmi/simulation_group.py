"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

import logging
from datetime import datetime, timezone
from os import PathLike
from pathlib import Path
from typing import Sequence
from uuid import uuid4

import yaml
from cwltool.context import RuntimeContext
from cwltool.factory import Factory as WorkflowFactory
from pydantic import BaseModel, ConfigDict, model_validator
from rocrate.model import SoftwareApplication
from rocrate.rocrate import ROCrate

from picongpu._rc_params import SoftwareReference
from picongpu.picmi.simulation import Simulation

_GROUP_MAIN_ENTITY = "workflow/group_workflow.cwl"
_GROUP_LICENSE = "https://spdx.org/licenses/GPL-3.0-or-later"
_CONTENT_SECTION_TERM = {"hasContentSection": "https://schema.org/hasContentSection"}

# The required inputs of a self-contained per-simulation workflow, mapped to the
# self-contained resources that live inside the sub-simulation's setup directory.
# Used as step-level `default` inputs of the overarching group workflow so each
# nested per-sim workflow can be built and submitted without a group-level job.
_REQUIRED_SUB_SIM_INPUTS = {
    "build_include_directory": ("Directory", "include"),
    "build_script": ("File", "workflow/scripts/build.sh"),
    "run_etc_directory": ("Directory", "etc"),
    "prepare_submission_script": ("File", "workflow/scripts/prepare_submission.sh"),
    "submission_script": ("File", "workflow/scripts/submit.sh"),
    "organize_output_script": ("File", "workflow/scripts/organize_output.sh"),
    "run_project_path": ("Directory", "."),
}


def _default_names(count: int) -> list[str]:
    return [f"sim_{uuid4().hex[:8]}" for _ in range(count)]


def _assert_valid_names(names: Sequence[str], count: int) -> None:
    if len(set(names)) != len(names):
        raise ValueError(f"Simulation names must be unique. Got {names=}.")
    for name in names:
        if not name:
            raise ValueError(f"Simulation names must be non-empty. Got {name=}.")
        if name.startswith("."):
            raise ValueError(f"Simulation names must not start with '.'. Got {name=}.")
        if "/" in name:
            raise ValueError(f"Simulation names must not contain '/'. Got {name=}.")
    if len(names) != count:
        raise ValueError(f"Expected {count} names for {count} simulations, got {len(names)}: {names}.")


def _generate_group_workflow(names: Sequence[str]) -> str:
    steps = {}
    outputs = {}
    for name in names:
        steps[f"{name}_step"] = {
            "id": f"{name}_step",
            "label": f"Build and run sub-simulation {name}",
            "doc": f"Nests the self-contained per-simulation workflow of {name}.",
            "run": f"../{name}/workflow/workflow.cwl",
            "in": {
                key: {"default": {"class": cwl_class, "location": f"../{name}/{location}"}}
                for key, (cwl_class, location) in _REQUIRED_SUB_SIM_INPUTS.items()
            },
            "out": ["input_directory", "submission_information"],
        }
        outputs[f"{name}_input_directory"] = {
            "type": "Directory",
            "outputSource": f"{name}_step/input_directory",
            "label": f"{name} input directory",
        }
        outputs[f"{name}_submission_information"] = {
            "type": "File",
            "outputSource": f"{name}_step/submission_information",
            "label": f"{name} submission information",
        }
    workflow = {
        "cwlVersion": "v1.2",
        "class": "Workflow",
        "label": "PIConGPU Simulation Group Workflow",
        "doc": (
            "Overarching workflow that builds and runs every sub-simulation in the group.\n"
            "Each step nests one self-contained per-simulation workflow."
        ),
        "requirements": {"SubworkflowFeatureRequirement": {}},
        "inputs": {},
        "outputs": outputs,
        "steps": steps,
    }
    return yaml.safe_dump(workflow, sort_keys=False, width=120)


class SimulationGroup(BaseModel):
    """
    A group of multiple :class:`Simulation` instances.

    Exposes the same ``write_input_file`` / ``run`` interface as a single
    :class:`~picongpu.picmi.simulation.Simulation`. ``write_input_file`` fans the
    group out into one self-contained PIConGPU setup (with its own CWL workflow and
    RO-Crate) per sub-simulation and additionally writes an overarching CWL
    ``Workflow`` and a root RO-Crate that references every sub-crate. ``run``
    generates the group and then executes the overarching workflow, thereby
    building and submitting every sub-simulation.
    """

    simulations: list[Simulation]
    names: list[str] | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def __init__(self, simulations: Sequence[Simulation], names: Sequence[str] | None = None):
        super().__init__(simulations=list(simulations), names=list(names) if names is not None else None)

    @model_validator(mode="after")
    def _validate_group(self):
        if not self.simulations:
            raise ValueError("A SimulationGroup requires at least one Simulation.")
        if self.names is None:
            self.names = _default_names(len(self.simulations))
        _assert_valid_names(self.names, len(self.simulations))
        return self

    def _group_workflow_path(self, group_dir: Path) -> Path:
        return group_dir / "workflow" / "group_workflow.cwl"

    def write_input_file(self, group_dir: str | PathLike, exist_ok=False, **flags) -> None:
        """
        Generate a PIConGPU input set for every sub-simulation and the overarching
        group workflow + root RO-Crate.

        :param group_dir: target directory for the group; each sub-simulation is
            written to ``<group_dir>/<name>/``
        :param exist_ok: passed through to each sub-simulation's ``write_input_file``
        :param flags: extra flags forwarded to each sub-simulation
        """
        group_dir = Path(group_dir)
        group_dir.mkdir(parents=True, exist_ok=True)

        for name, simulation in zip(self.names, self.simulations):
            simulation.write_input_file(group_dir / name, exist_ok=exist_ok, **flags)

        group_workflow_path = self._group_workflow_path(group_dir)
        group_workflow_path.parent.mkdir(parents=True, exist_ok=True)
        group_workflow_path.write_text(_generate_group_workflow(self.names))

        self._write_rocrate(group_dir, group_workflow_path)

    def _write_rocrate(self, group_dir: Path, group_workflow_path: Path) -> None:
        crate = ROCrate(group_dir, version="1.2", init=True)

        workflow = crate.get(_GROUP_MAIN_ENTITY)
        workflow._jsonld["@type"] = ["File", "SoftwareSourceCode", "ComputationalWorkflow"]
        workflow["name"] = "Build and run this simulation group"

        software = SoftwareApplication(
            crate,
            SoftwareReference().id_,
            properties=SoftwareReference().model_dump(mode="python"),
        )
        crate.add(software)
        crate.root_dataset.append_to("instrument", software)

        crate.name = f"PIConGPU simulation group autogenerated by PyPIConGPU on {datetime.now(timezone.utc)}"
        crate.description = (
            "This root RO-Crate groups multiple self-contained PIConGPU simulation setups, "
            "one per sub-simulation. Each sub-simulation keeps its own ro-crate-metadata.json "
            "and mainEntity and is referenced via hasContentSection. The overarching "
            "group workflow in `workflow/group_workflow.cwl` nests every sub-simulation "
            "workflow and builds and submits them all."
        )
        crate.root_dataset["license"] = _GROUP_LICENSE
        crate.root_dataset["datePublished"] = datetime.now(timezone.utc).isoformat()
        crate.root_dataset.append_to("mainEntity", workflow)

        crate.metadata.extra_terms = _CONTENT_SECTION_TERM
        for name in self.names:
            crate.root_dataset.append_to("hasContentSection", crate.get(f"{name}/"))

        crate.metadata.write(group_dir)

    def run(self, group_dir: str | PathLike, exist_ok=False, **flags) -> None:
        """
        Generate the group (see :meth:`write_input_file`) and execute the
        overarching group workflow, building and submitting every
        sub-simulation. Mirrors ``Simulation.run``.

        Unlike ``Simulation.run`` (which forwards ``flags`` to the per-simulation
        build/submit cwltool job), the group workflow nests each sub-simulation as
        a self-contained step fed only by its generated setup; runtime ``flags``
        (e.g. ``jobs``, ``cmake``) reach each sub-simulation's generated
        ``input.yaml`` but are not forwarded to the group-level build/submit
        invocation.
        """
        group_dir = Path(group_dir)
        self.write_input_file(group_dir, exist_ok=exist_ok, **flags)
        group_workflow_path = self._group_workflow_path(group_dir)
        cwl_cache_dir = group_dir / ".cwl_cache"
        cwl_cache_dir.mkdir(parents=True, exist_ok=True)
        logging.info("Running group workflow: %s", group_workflow_path)
        return WorkflowFactory(
            runtime_context=RuntimeContext(
                kwargs={
                    "outdir": str(group_dir),
                    "rm_tmpdir": False,
                    "move_outputs": "copy",
                    "cachedir": str(cwl_cache_dir),
                    "preserve_entire_environment": True,
                }
            )
        ).make(str(group_workflow_path))()
