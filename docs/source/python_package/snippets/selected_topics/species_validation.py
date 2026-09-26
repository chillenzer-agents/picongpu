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

Shows that a species is checked when it is rendered to the PyPIConGPU
layer: a valid species converts silently, an invalid name is rejected.
"""

from pydantic import ValidationError

from picongpu import picmi

# BEGIN-SPECIES-VALIDATION
# the checks run whenever the species is converted to its PyPIConGPU
# representation (this also happens for every species on
# simulation.write_input_file(...)):
valid = picmi.Species(name="electrons", particle_type="electron")
print("valid species:", valid.get_as_pypicongpu().name)

invalid = picmi.Species(name="not a valid name", particle_type="electron")
try:
    invalid.get_as_pypicongpu()
except ValidationError as error:
    print("rejected:", error.errors()[0]["msg"])
# END-SPECIES-VALIDATION

print("It worked!")
