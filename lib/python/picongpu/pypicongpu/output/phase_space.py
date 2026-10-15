"""
This file is part of PIConGPU.
Copyright 2021-2025 PIConGPU contributors
Authors: Masoud Afshari, Julian Lenz
License: GPLv3+
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from picongpu.pypicongpu.output.timestepspec import TimeStepSpec
from picongpu.pypicongpu.particle_functor.filtered_species import FilteredSpecies
from picongpu.pypicongpu.species import Species


FileExtension = Annotated[str, Field(strict=True, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")]
"""A bare filename suffix that can be rendered as one CLI token (without a dot)."""


class PhaseSpace(BaseModel):
    species: Species | FilteredSpecies
    period: TimeStepSpec
    spatial_coordinate: Literal["x", "y", "z"]
    momentum_coordinate: Literal["px", "py", "pz"]
    min_momentum: float
    max_momentum: float
    extension: FileExtension | None = None
    """Per-instance openPMD extension; None leaves the C++ plugin default in effect."""

    type_phasespace: Literal[True] = True

    @model_validator(mode="after")
    def check(self):
        if self.min_momentum >= self.max_momentum:
            raise ValueError(
                "PhaseSpace's min_momentum should be smaller than max_momentum. "
                f"You gave: {self.min_momentum=} and {self.max_momentum=}."
            )
        return self


def validate_extension_order(outputs):
    """Prevent omitted CLI entries from shifting extensions to earlier instances.

    multi::Option indexes each option independently, per species (including
    all its filters). Only an explicit prefix followed by defaults is expressible.
    """
    species_with_default = set()
    for output in outputs:
        if not isinstance(output, PhaseSpace):
            continue
        name = output.species.species_name
        if output.extension is None:
            species_with_default.add(name)
        elif name in species_with_default:
            raise ValueError(
                f"Phase-space extension for species '{name}' follows an omitted extension. "
                "The CLI cannot represent a default before an explicit extension for the same species. "
                "Set picongpu_extension on the preceding diagnostics or place explicit extensions first."
            )
