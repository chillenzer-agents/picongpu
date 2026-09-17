"""
This file is part of PIConGPU.
Copyright 2025 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

from .binning import Binning
from .checkpoint import Checkpoint
from .energy_histogram import EnergyHistogram
from .macro_particle_count import MacroParticleCount
from .openpmd_plugin import OpenPMDPlugin
from .particle_energy import ParticleEnergy
from .phase_space import PhaseSpace
from .radiation import RadiationConfiguration, RadiationPlugin, RadiationObserverConfiguration
from .timestepspec import TimeStepSpec

AnyPlugin = (
    Binning
    | Checkpoint
    | EnergyHistogram
    | MacroParticleCount
    | OpenPMDPlugin
    | ParticleEnergy
    | PhaseSpace
    | RadiationPlugin
)

__all__ = [
    "OpenPMDPlugin",
    "AnyPlugin",
    "PhaseSpace",
    "EnergyHistogram",
    "MacroParticleCount",
    "ParticleEnergy",
    "TimeStepSpec",
    "Checkpoint",
    "RadiationPlugin",
    "RadiationObserverConfiguration",
    "RadiationConfiguration",
]
