#!/usr/bin/env python
# /// script
# requires-python = ">=3.11,<3.14"
# dependencies = [
#   "picongpu @ git+https://github.com/ComputationalRadiationPhysics/picongpu@dev#subdirectory=lib/python"
# ]
# ///
"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+

Generates a PIConGPU setup that carries a LEXIS Workflow Definition
(``workflow.lwd.yaml``) instead of the CWL workflow, and inspects the
submission plan without contacting the platform (dry run).
"""

# BEGIN-EFP-LEXIS-WORKFLOW
from pathlib import Path

from picongpu import picmi, rc_params
from picongpu.pypicongpu.lexis_submit import submit

# Switch the workflow backend from the default CWL pipeline to LEXIS and
# describe the target HPC job and its dataset staging. This is normally done
# in picongpurc.toml (see the TOML snippet); it is set here to keep the
# snippet self-contained.
rc_params["workflow_backend"] = "lexis"
rc_params["lexis"] = {
    "project_shortname": "your-efp-project",
    "command_template_name": "picongpu",
    "location_name": "jupiter",
    "location_resource": "gh200",
    "walltime_limit": 7200,
    "input_dataset": "ddi://~/your-picongpu-setup",
}

sim = picmi.Simulation(
    max_steps=100,
    solver=picmi.ElectromagneticSolver(
        method="Yee",
        cfl=0.95,
        grid=picmi.Cartesian3DGrid(
            number_of_cells=[192, 192, 192],
            lower_bound=[0, 0, 0],
            upper_bound=[0.1772e-6, 0.1772e-6, 0.1772e-6],
            lower_boundary_conditions=["periodic", "periodic", "periodic"],
            upper_boundary_conditions=["periodic", "periodic", "periodic"],
        ),
    ),
)

setup_dir = Path("efp_lexis_setup")
sim.write_input_file(setup_dir)

# With workflow_backend = "lexis" the runner additionally emits the LEXIS
# Workflow Definition next to the usual CWL files.
lwd_path = setup_dir / "workflow" / "workflow.lwd.yaml"
print(lwd_path.read_text())

plan = submit(lwd_path, dry_run=True)
print("submission steps:", [step["action"] for step in plan["plan"]["steps"]])
print("It worked!")
# END-EFP-LEXIS-WORKFLOW
