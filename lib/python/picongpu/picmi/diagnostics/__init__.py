"""
This file is part of PIConGPU.
Copyright 2024 PIConGPU contributors
Authors: Julian Lenz, Masoud Afshari
License: GPLv3+
"""

from .backend_config import BackendConfig, OpenPMDConfig
from .binning import Binning, BinningAxis, BinSpec
from .checkpoint import Checkpoint
from .energy_histogram import EnergyHistogram
from .field_dump import DerivedFieldDump, NativeFieldDump
from .macro_particle_count import MacroParticleCount
from .particle_dump import ParticleDump
from .particle_energy import ParticleEnergy
from .phase_space import PhaseSpace
from .radiation import Radiation
from .timestepspec import TimeStepSpec

AnyDiagnostic = (
    Binning
    | Checkpoint
    | EnergyHistogram
    | DerivedFieldDump
    | NativeFieldDump
    | MacroParticleCount
    | ParticleDump
    | ParticleEnergy
    | PhaseSpace
    | Radiation
)
__all__ = [
    "AnyDiagnostic",
    "BackendConfig",
    "OpenPMDConfig",
    "Binning",
    "BinningAxis",
    "BinSpec",
    "PhaseSpace",
    "EnergyHistogram",
    "MacroParticleCount",
    "ParticleDump",
    "ParticleEnergy",
    "NativeFieldDump",
    "DerivedFieldDump",
    "TimeStepSpec",
    "Checkpoint",
    "Radiation",
]
