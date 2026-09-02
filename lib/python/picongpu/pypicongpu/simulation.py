"""
This file is part of PIConGPU.
Copyright 2021-2025 PIConGPU contributors
Authors: Hannes Troepgen, Brian Edward Marre, Julian Lenz
License: GPLv3+
"""

import warnings
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, Field, field_serializer, field_validator, model_validator
from typing_extensions import Self

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
from .laser import AnyLaser, PlaneWaveLaser, TWTSLaser
from .movingwindow import MovingWindow
from .output import AnyPlugin, OpenPMDPlugin
from .rendering import RenderedObject
from .walltime import Walltime


class Simulation(RenderedObject, BaseModel):
    """
    Represents all parameters required to build & run a PIConGPU simulation.

    C++ counterpart: include/picongpu/param/simulation.param (and the
    per-subsystem .param/.cfg templates rendered from the respective sub-objects).

    Units policy: all physical quantities are given in SI units;
    dimensionless quantities are marked as such in their docstring.

    Most of the individual parameters are delegated to other objects held as
    attributes.

    To run a Simulation object pass it to the Runner (for details see there).
    """

    base_density: Annotated[float, Field(gt=0.0)]
    """reference number density for normalising density profiles, [m^-3]; must be > 0.
    C++ name: SI::BASE_DENSITY_SI (simulation.param)."""

    delta_t_si: Annotated[float, Field(gt=0.0)]
    """width of a single timestep, [s]; must be > 0.
    C++ name: SI::DELTA_T_SI (simulation.param)."""

    time_steps: Annotated[int, Field(ge=0)]
    """total number of time steps to execute, [dimensionless]; must be >= 0.
    C++ name: TBG_steps (etc/picongpu/N.cfg)."""

    grid: Grid3D
    """used grid object; cell sizes and cell counts in SI/m and cells"""

    laser: list[AnyLaser] | None
    """list of laser objects to use in the simulation, or None to disable lasers"""

    solver: AnySolver
    """used field solver"""

    typical_ppc: Annotated[int, Field(ge=1)]
    """typical number of macro particles per cell, [dimensionless]; must be >= 1.
    Used for normalization of units.
    C++ name: TYPICAL_PARTICLES_PER_CELL (simulation.param)."""

    customuserinput: list[CustomUserInput] | None
    """
    objects containing additional user-specified input parameters to be used in custom templates

    @attention custom user input is global to the simulation
    """

    moving_window: MovingWindow | None
    """used moving window, set to None to disable"""

    walltime: Walltime
    """time limit of the simulation run"""

    binomial_current_interpolation: bool
    """switch on a binomial current interpolation, [dimensionless flag]"""

    output: list[AnyPlugin] | None
    """plugins to write output, or None"""

    species: list[Species]
    """species present in the simulation"""

    init_operations: list[AnyOperation]
    """operations that initialize species attributes"""

    synchrotron_params: SynchrotronParams = SynchrotronParams()
    """parameters for the synchrotron radiation plugin"""

    collisional_physics: CollisionalPhysicsSetup = CollisionalPhysicsSetup()
    """collisional physics setup (collisions, screening species, numerics)"""

    particle_filters: list[ParticleFunctor] = Field(default_factory=list)
    """particle filters made globally available to the simulation"""

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

    @model_validator(mode="after")
    def _check_laser_fits_in_run(self) -> Self:
        # Technical (soft) invariant, hence a warning rather than an error:
        # PIConGPU happily simulates a laser pulse that extends beyond the end
        # of the run (the pulse is simply truncated), but it is usually a
        # sign of inconsistent parameters.
        #
        # This is a heuristic that models the temporal extent of
        # _BaseLaser-style pulses (Gaussian / dispersive) as
        # pulse_duration_si * pulse_init. It is type-specific:
        #   - TWTSLaser's extent is its on/off window, approximated by
        #     windowEnd * delta_t_si (an inactive window keeps the laser on
        #     for the whole run, so nothing is truncated);
        #   - PlaneWaveLaser is a continuous wave, so it is never truncated;
        #   - FromOpenPMDPulseLaser carries its extent in the input file,
        #     which is not known here.
        run_time = self.delta_t_si * self.time_steps
        for laser in self.laser or []:
            if isinstance(laser, TWTSLaser):
                pulse_end = laser.windowEnd * self.delta_t_si
                if pulse_end > run_time:
                    warnings.warn(
                        f"TWTSLaser window end (windowEnd * delta_t_si = {pulse_end} s) "
                        f"exceeds the simulation time {run_time} s (delta_t_si * time_steps). "
                        "The laser will be truncated at the end of the run."
                    )
                continue
            if isinstance(laser, PlaneWaveLaser):
                # continuous wave: present for the whole run, never truncated
                continue
            pulse_length = getattr(laser, "pulse_duration_si", None)
            pulse_length = getattr(laser, "pulse_init", 1.0) * pulse_length if pulse_length is not None else None
            if pulse_length is not None and pulse_length > run_time:
                warnings.warn(
                    f"Laser {type(laser).__name__} pulse length {pulse_length} s "
                    f"(pulse_duration_si * pulse_init) exceeds the simulation time "
                    f"{run_time} s (delta_t_si * time_steps). "
                    "The pulse will be truncated at the end of the run."
                )
        return self

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

    def spread_directory_information(self, setup_dir):
        for plugin in self.output or []:
            if isinstance(plugin, OpenPMDPlugin):
                plugin.setup_dir = Path(setup_dir)
