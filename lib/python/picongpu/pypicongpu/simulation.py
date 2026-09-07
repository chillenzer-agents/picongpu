"""
This file is part of PIConGPU.
Copyright 2021-2025 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre, Julian Lenz
License: GPLv3+
"""

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_serializer, field_validator, model_validator

from picongpu.pypicongpu.collisions import CollisionalPhysicsSetup
from picongpu.pypicongpu.output.radiation import RadiationPlugin
from picongpu.pypicongpu.output.timestepspec import TimeStepSpec
from picongpu.pypicongpu.particle_functor.particle_functor import ParticleFunctor
from picongpu.pypicongpu.species.constant.synchrotron import SynchrotronParams
from picongpu.pypicongpu.species.operation import AnyOperation
from picongpu.pypicongpu.species.species import Species

from .customuserinput import CustomUserInput
from .field_solver import AnySolver
from .grid import Grid3D
from .laser import AnyLaser
from .movingwindow import MovingWindow
from .output import AnyPlugin, OpenPMDPlugin
from .rendering import RenderedObject
from .validation import validate_huygens_surface_positions
from .walltime import Walltime


class Simulation(RenderedObject, BaseModel):
    """
    Represents all parameters required to build & run a PIConGPU simulation.

    Most of the individual parameters are delegated to other objects held as
    attributes.

    To run a Simulation object pass it to the Runner (for details see there).
    """

    base_density: float
    """value to normalise densities"""

    delta_t_si: float
    """Width of a single timestep, given in seconds."""

    time_steps: int
    """Total number of time steps to be executed."""

    grid: Grid3D
    """Used grid Object"""

    laser: list[AnyLaser] | None
    """List of laser objects to use in the simulation, or None to disable lasers"""

    solver: AnySolver
    """Used Solver"""

    typical_ppc: int
    """
    typical number of macro particles spawned per cell, >=1

    used for normalization of units
    """

    customuserinput: list[CustomUserInput] | None
    """
    object that contains additional user specified input parameters to be used in custom templates

    @attention custom user input is global to the simulation
    """

    moving_window: MovingWindow | None
    """used moving Window, set to None to disable"""

    walltime: Walltime
    """time limit of the simulation run"""

    binomial_current_interpolation: bool
    """switch on a binomial current interpolation"""

    output: list[AnyPlugin] | None
    species: list[Species]
    init_operations: list[AnyOperation]
    synchrotron_params: SynchrotronParams = SynchrotronParams()
    collisional_physics: CollisionalPhysicsSetup = CollisionalPhysicsSetup()
    particle_filters: list[ParticleFunctor] = Field(default_factory=list)

    @field_validator("output", mode="after")
    @classmethod
    def _output_validation(cls, outputs):
        # The radiation plugin expects to always have content in its param file,
        # so we'll always add a RadiationPlugin to make them appear.
        default = [
            RadiationPlugin(
                species=[],
                period=TimeStepSpec([]),
                config={"observer": {"N_observer": 1, "index_to_direction": lambda _: [1, 0, 0]}},
            )
        ]
        if outputs is None:
            return default
        if not any(isinstance(o, RadiationPlugin) for o in outputs):
            return outputs + default
        return outputs

    @field_serializer("customuserinput")
    def _render_custom_user_input_list(self, value) -> dict[str, Any] | None:
        if value is None:
            return None
        custom_rendering_context = {"tags": []}

        for entry in value:
            add_context = entry.get_rendering_context()
            tags = entry.get_tags()

            entry.check_does_not_change_existing_key_values(custom_rendering_context, add_context)
            entry.check_tags(custom_rendering_context["tags"], tags)

            custom_rendering_context.update(add_context)
            custom_rendering_context["tags"].extend(tags)

        return custom_rendering_context

    @model_validator(mode="after")
    def _check_lasers(self):
        if not self.laser:
            return self
        first_positions = self.laser[0].huygens_surface_positions
        for ll in self.laser:
            # a single Huygens POSITION is rendered per simulation (from the first
            # laser), so all lasers must agree on the surface positions
            if ll.huygens_surface_positions != first_positions:
                raise ValueError(
                    "All lasers in a simulation must use the same huygens_surface_positions, "
                    "as a single Huygens surface position is rendered for the whole simulation. "
                    f"You gave {first_positions=} for the first laser and {ll.huygens_surface_positions=} "
                    "for another one."
                )
            validate_huygens_surface_positions(
                ll.huygens_surface_positions,
                cell_cnt=self.grid.cell_cnt,
                moving_window_enabled=self.moving_window is not None,
            )
        return self

    def spread_directory_information(self, setup_dir):
        for plugin in self.output or []:
            if isinstance(plugin, OpenPMDPlugin):
                plugin.setup_dir = Path(setup_dir)
