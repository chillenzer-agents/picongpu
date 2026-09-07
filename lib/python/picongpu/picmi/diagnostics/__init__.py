"""
This file is part of PIConGPU.
Copyright 2024 PIConGPU contributors
Authors: Julian Lenz, Masoud Afshari
License: GPLv3+
"""

from .backend_config import BackendConfig as BackendConfig
from .backend_config import OpenPMDConfig as OpenPMDConfig
from .binning import BinSpec as BinSpec
from .binning import Binning as Binning
from .binning import BinningAxis as BinningAxis
from .binning import BinningFunctor as BinningFunctor
from .checkpoint import Checkpoint as Checkpoint
from .energy_histogram import EnergyHistogram as EnergyHistogram
from .field_dump import DerivedFieldDump as DerivedFieldDump
from .field_dump import NativeFieldDump as NativeFieldDump
from .macro_particle_count import MacroParticleCount as MacroParticleCount
from .particle_dump import ParticleDump as ParticleDump
from .phase_space import PhaseSpace as PhaseSpace
from .radiation import Radiation as Radiation
from .radiation import RadiationObserverConfiguration as RadiationObserverConfiguration
from .timestepspec import TimeStepSpec as TimeStepSpec

AnyDiagnostic = (
    Binning
    | Checkpoint
    | EnergyHistogram
    | DerivedFieldDump
    | NativeFieldDump
    | MacroParticleCount
    | ParticleDump
    | PhaseSpace
    | Radiation
)
