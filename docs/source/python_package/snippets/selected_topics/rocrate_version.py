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

Generates a simulation setup and inspects the RO-Crate specification version
recorded in its metadata. The version is the ``rocrate.info.version`` rc
parameter and defaults to ``1.3``.
"""

# BEGIN-ROCRATE-VERSION
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from picongpu import picmi, rc_params

grid = picmi.Cartesian3DGrid(
    number_of_cells=[32, 32, 32],
    lower_bound=[0, 0, 0],
    upper_bound=[1e-6, 1e-6, 1e-6],
    lower_boundary_conditions=["periodic", "periodic", "periodic"],
    upper_boundary_conditions=["periodic", "periodic", "periodic"],
)
solver = picmi.ElectromagneticSolver(method="Yee", grid=grid)
sim = picmi.Simulation(time_step_size=17, max_steps=4, solver=solver)

# the RO-Crate specification version is an rc parameter (default "1.3")
print("configured RO-Crate version:", rc_params.rocrate_info.version)

with TemporaryDirectory() as setup_dir:
    sim.write_input_file(setup_dir, exist_ok=True)
    metadata = json.loads((Path(setup_dir) / "ro-crate-metadata.json").read_text())
    print("written RO-Crate context:", metadata["@context"])

# select another supported version via the rc parameter before generating:
rc_params["rocrate"] = {"info": {"version": "1.2"}}
print("overridden RO-Crate version:", rc_params.rocrate_info.version)
# END-ROCRATE-VERSION
