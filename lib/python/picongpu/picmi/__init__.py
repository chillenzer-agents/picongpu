"""
PICMI for PIConGPU
"""

import sys as _sys

import picmistandard as _picmistandard

from . import constants
from . import diagnostics as diagnostics
from .distribution import AnalyticDistribution as AnalyticDistribution
from .distribution import CylindricalDistribution as CylindricalDistribution
from .distribution import FoilDistribution as FoilDistribution
from .distribution import GaussianDistribution as GaussianDistribution
from .distribution import UniformDistribution as UniformDistribution
from .grid import Cartesian3DGrid as Cartesian3DGrid
from .interaction import Collision as Collision
from .interaction import CollisionalPhysicsSetup as CollisionalPhysicsSetup
from .interaction import ConstLogCollision as ConstLogCollision
from .interaction import DynamicLogCollision as DynamicLogCollision
from .interaction import Interaction as Interaction
from .interaction import Synchrotron as Synchrotron
from .interaction.ionization.electroniccollisionalequilibrium import (
    ThomasFermi as ThomasFermi,
)
from .interaction.ionization.fieldionization import ADK as ADK
from .interaction.ionization.fieldionization import BSI as BSI
from .interaction.ionization.fieldionization import ADKVariant as ADKVariant
from .interaction.ionization.fieldionization import BSIExtension as BSIExtension
from .interaction.ionization.fieldionization import Keldysh as Keldysh
from .lasers import DispersivePulseLaser as DispersivePulseLaser
from .lasers import FromOpenPMDPulseLaser as FromOpenPMDPulseLaser
from .lasers import GaussianLaser as GaussianLaser
from .lasers import PlaneWaveLaser as PlaneWaveLaser
from .lasers import PolarizationType as PolarizationType
from .lasers import TWTSLaser as TWTSLaser
from .layout import GriddedLayout as GriddedLayout
from .layout import OnePositionLayout as OnePositionLayout
from .layout import PseudoRandomLayout as PseudoRandomLayout
from .particle_functor import FilteredSpecies as FilteredSpecies
from .particle_functor import ParticleFilter as ParticleFilter
from .particle_functor import ParticleFunctor as ParticleFunctor
from .simulation import Simulation as Simulation
from .solver import BinomialSmoother as BinomialSmoother
from .solver import ElectromagneticSolver as ElectromagneticSolver
from .species import Species as Species

assert _sys.version_info.major > 3 or _sys.version_info.minor >= 11, "Python 3.11 is required for PIConGPU PICMI"


codename = "picongpu"
"""
name of this PICMI implementation
required by PICMI interface
"""

_picmistandard.register_codename(codename)
_picmistandard.register_constants(constants)
