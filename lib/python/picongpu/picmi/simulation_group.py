"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

import json
import logging
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Union
from uuid import uuid4

import yaml
from cwltool.context import RuntimeContext
from cwltool.factory import Factory as WorkflowFactory
from pydantic import BaseModel, BeforeValidator, model_validator
from rocrate.model import SoftwareApplication
from rocrate.rocrate import ROCrate

from picongpu._rc_params import SoftwareReference
from picongpu.picmi.simulation import Simulation

_GROUP_MAIN_ENTITY = "workflow/group_workflow.cwl"
_GROUP_LICENSE = "https://spdx.org/licenses/GPL-3.0-or-later"
_CONTENT_SECTION_TERM = {"hasContentSection": "https://schema.org/hasContentSection"}

# The per-leaf-simulation outputs exposed by a group workflow, keyed by the
# suffix appended to the simulation path; maps to (CWL type, human label).
# Ordered so each simulation's `input_directory` precedes its `submission_information`.
_GROUP_OUTPUT_DEFS = {
    "input_directory": ("Directory", "input directory"),
    "submission_information": ("File", "submission information"),
}


def _default_name() -> str:
    return f"sim_{uuid4().hex[:8]}"


def _coerce_simulations(items):
    """Allow the list shortcut ``[sim, ...]`` as sugar for ``{<default name>: sim}``."""
    if isinstance(items, Sequence) and not isinstance(items, (str, bytes)):
        return {_default_name(): entry for entry in items}
    return items


def _iter_leaf_simulations(items, parent=""):
    """Yield ``(relative path, simulation)`` for every leaf :class:`Simulation`, depth-first."""
    for name, entry in items.items():
        if not name:
            raise ValueError("Simulation names must be non-empty.")
        if name.startswith("."):
            raise ValueError(f"Simulation names must not start with '.'. Got {name=}.")
        if "/" in name:
            raise ValueError(f"Simulation names must not contain '/'. Got {name=}.")
        path = f"{parent}/{name}" if parent else name
        if isinstance(entry, SimulationGroup):
            yield from _iter_leaf_simulations(entry.simulations, path)
        elif isinstance(entry, dict):
            yield from _iter_leaf_simulations(entry, path)
        elif isinstance(entry, Simulation):
            yield path, entry
        else:
            raise ValueError(f"Invalid group entry at {path}: expected a Simulation, group or dict, got {entry!r}.")


def _generate_group_workflow(group_dir: Path, children: dict[str, str]) -> str:
    """
    Build the overarching group workflow as a plain dict and emit it as YAML.

    ``children`` maps each top-level entry name to ``"simulation"`` or ``"group"``.
    A simulation child nests ``../<name>/workflow/workflow.cwl`` and is fed by the
    self-contained inputs recorded in that sub-simulation's generated
    ``workflow/input.yaml`` (so per-simulation build/run flags are honoured). A
    group child nests the (self-contained, input-less) ``../<name>/workflow/group_workflow.cwl``.
    Each child's outputs are re-exposed under the ``<name>_<output>`` prefix.
    """
    steps: dict = {}
    outputs: dict = {}
    for name, kind in children.items():
        if kind == "group":
            child_workflow = f"../{name}/{_GROUP_MAIN_ENTITY}"
            child_doc = f"Nests the sub-group workflow of {name}."
            # The sub-group workflow is self-contained (no inputs) and already
            # re-exposes its leaf results, so it takes no step inputs and we just
            # bubble up the outputs it declares.
            step_in: dict = {}
            child_outputs = yaml.safe_load((group_dir / name / _GROUP_MAIN_ENTITY).read_text())["outputs"]
        else:
            child_workflow = f"../{name}/workflow/workflow.cwl"
            child_doc = f"Nests the self-contained per-simulation workflow of {name}."
            job = json.loads((group_dir / name / "workflow" / "input.yaml").read_text())
            step_in = {key: {"default": value} for key, value in job.items()}
            child_outputs = {
                suffix: {"type": cwl_type, "label": label} for suffix, (cwl_type, label) in _GROUP_OUTPUT_DEFS.items()
            }
        step_id = f"{name}_step"
        steps[step_id] = {
            "id": step_id,
            "label": f"Build and run sub-simulation {name}",
            "doc": child_doc,
            "run": child_workflow,
            "in": step_in,
            "out": list(child_outputs),
        }
        for suffix, props in child_outputs.items():
            outputs[f"{name}_{suffix}"] = {
                "type": props["type"],
                "outputSource": f"{step_id}/{suffix}",
                "label": f"{name} {props.get('label', suffix)}",
            }
    workflow = {
        "cwlVersion": "v1.2",
        "class": "Workflow",
        "label": "PIConGPU Simulation Group Workflow",
        "doc": (
            "Overarching workflow that builds and runs every sub-simulation in the group.\n"
            "Each step nests one self-contained per-simulation (or sub-group) workflow."
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

    ``simulations`` maps each sub-entry name to either a :class:`Simulation`, a
    nested :class:`SimulationGroup`, or a plain dict (equivalent to a
    :class:`SimulationGroup`). A list of :class:`Simulation` is accepted as a
    shortcut for ``{<default name>: sim}``.

    Exposes the same ``write_input_file`` / ``run`` interface as a single
    :class:`~picongpu.picmi.simulation.Simulation`. ``write_input_file`` fans the
    group out recursively into one self-contained PIConGPU setup (with its own CWL
    workflow and RO-Crate) per sub-simulation, then writes an overarching CWL
    ``Workflow`` and a root RO-Crate at each group level. ``run`` generates the
    group and then executes the overarching workflow, thereby building and
    submitting every sub-simulation.
    """

    simulations: Annotated[
        dict[str, Union[Simulation, "SimulationGroup", dict]],
        BeforeValidator(_coerce_simulations),
    ]

    @model_validator(mode="after")
    def _validate_group(self):
        if not list(_iter_leaf_simulations(self.simulations)):
            raise ValueError("A SimulationGroup requires at least one Simulation.")
        return self

    @property
    def simulations_by_path(self) -> list[tuple[str, Simulation]]:
        """The flattened ``(relative path, simulation)`` pairs, depth-first."""
        return list(_iter_leaf_simulations(self.simulations))

    def _group_workflow_path(self, group_dir: Path) -> Path:
        return group_dir / "workflow" / "group_workflow.cwl"

    def write_input_file(self, group_dir: str | Path, exist_ok=False, **flags) -> None:
        """
        Generate a PIConGPU input set for every sub-simulation (recursively) and the
        overarching group workflow + root RO-Crate at this level.

        Each entry of ``simulations`` becomes a sub-directory of ``group_dir``: a
        :class:`Simulation` becomes a self-contained per-simulation setup, while a
        nested group/dict recurses into its own sub-group setup (with its own
        ``group_workflow.cwl`` and root RO-Crate).

        :param group_dir: target directory for the group; each entry is written to
            ``<group_dir>/<name>/``
        :param exist_ok: passed through to each (sub-)simulation's ``write_input_file``
        :param flags: extra flags forwarded to every (sub-)simulation
        """
        group_dir = Path(group_dir)
        group_dir.mkdir(parents=True, exist_ok=True)

        children: dict[str, str] = {}
        for name, entry in self.simulations.items():
            if isinstance(entry, Simulation):
                entry.write_input_file(group_dir / name, exist_ok=exist_ok, **flags)
                children[name] = "simulation"
            else:
                sub_group = entry if isinstance(entry, SimulationGroup) else SimulationGroup(simulations=entry)
                sub_group.write_input_file(group_dir / name, exist_ok=exist_ok, **flags)
                children[name] = "group"

        group_workflow_path = self._group_workflow_path(group_dir)
        group_workflow_path.parent.mkdir(parents=True, exist_ok=True)
        group_workflow_path.write_text(_generate_group_workflow(group_dir, children))

        self._write_rocrate(group_dir)

    def _write_rocrate(self, group_dir: Path) -> None:
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
            "This root RO-Crate groups multiple self-contained PIConGPU simulation setups. "
            "Each entry keeps its own ro-crate-metadata.json and mainEntity and is referenced "
            "via hasContentSection. The overarching group workflow in `workflow/group_workflow.cwl` "
            "nests every (sub-)simulation workflow and builds and submits them all."
        )
        crate.root_dataset["license"] = _GROUP_LICENSE
        crate.root_dataset["datePublished"] = datetime.now(timezone.utc).isoformat()
        crate.root_dataset.append_to("mainEntity", workflow)

        crate.metadata.extra_terms = _CONTENT_SECTION_TERM
        for name in self.simulations:
            crate.root_dataset.append_to("hasContentSection", crate.get(f"{name}/"))

        crate.metadata.write(group_dir)

    def run(self, group_dir: str | Path, exist_ok=False, **flags) -> None:
        """
        Generate the group (see :meth:`write_input_file`) and execute the
        overarching group workflow, building and submitting every
        sub-simulation. Mirrors ``Simulation.run``.

        Runtime ``flags`` (e.g. ``jobs``, ``cmake``) are forwarded to every
        sub-simulation's generated ``input.yaml`` and re-used as the nested
        per-simulation step defaults, so they reach each sub-simulation's
        build/submit just as they would for a standalone simulation.
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
