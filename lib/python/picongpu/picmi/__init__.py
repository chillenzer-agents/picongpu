"""
PICMI for PIConGPU
"""

import sys

import picmistandard

from . import constants, diagnostics
from .distribution import (
    AnalyticDistribution,
    CylindricalDistribution,
    FoilDistribution,
    GaussianDistribution,
    UniformDistribution,
)
from .grid import Cartesian3DGrid
from .interaction import (
    Collision,
    ConstLogCollision,
    DynamicLogCollision,
    Interaction,
    Synchrotron,
)
from .interaction.ionization.electroniccollisionalequilibrium import ThomasFermi
from .interaction.ionization.fieldionization import (
    ADK,
    BSI,
    ADKVariant,
    BSIExtension,
    Keldysh,
)
from .lasers import (
    DispersivePulseLaser,
    FromOpenPMDPulseLaser,
    GaussianLaser,
    PlaneWaveLaser,
    TWTSLaser,
)
from .layout import GriddedLayout, OnePositionLayout, PseudoRandomLayout
from .particle_functor import FilteredSpecies, ParticleFilter, ParticleFunctor
from .simulation import Simulation
from .solver import BinomialSmoother, ElectromagneticSolver
from .species import Species

# friendly error for too-old interpreters; kept although it predates the
# minimum supported version (UP036)
if sys.version_info < (3, 11):  # noqa: UP036
    raise AssertionError("Python 3.11 is required for PIConGPU PICMI")

__all__ = [
    "ADK",
    "BSI",
    "ADKVariant",
    "AnalyticDistribution",
    "BSIExtension",
    "BinomialSmoother",
    "Cartesian3DGrid",
    "Collision",
    "ConstLogCollision",
    "CylindricalDistribution",
    "DispersivePulseLaser",
    "DynamicLogCollision",
    "ElectromagneticSolver",
    "FilteredSpecies",
    "FoilDistribution",
    "FromOpenPMDPulseLaser",
    "GaussianDistribution",
    "GaussianLaser",
    "GriddedLayout",
    "Interaction",
    "Keldysh",
    "OnePositionLayout",
    "ParticleFilter",
    "ParticleFunctor",
    "PlaneWaveLaser",
    "PseudoRandomLayout",
    "Simulation",
    "Species",
    "Synchrotron",
    "TWTSLaser",
    "ThomasFermi",
    "UniformDistribution",
    "constants",
    "diagnostics",
]


codename = "picongpu"
"""
name of this PICMI implementation
required by PICMI interface
"""

picmistandard.register_codename(codename)
picmistandard.register_constants(constants)
