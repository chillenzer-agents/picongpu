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
"""

# BEGIN-RC-DEPENDENCIES
from pathlib import Path

from picongpu.dependencies import DependenciesConfig

config = DependenciesConfig.from_rc_params(
    {
        "dependencies": {
            "enabled": True,
            "only": ["fftw3", "pngwriter"],
            "jobs": 16,
        }
    }
)

# the config is inactive until both enabled = true and provider = "source"
print("active:", config.active)

# the shell lines the generated build.sh prepends to `pic-build`
for line in config.install_commands(
    Path("etc/picongpu/dependencies/picongpu-deps.sh"),
    Path("setup/deps"),
):
    print(line)
# END-RC-DEPENDENCIES
