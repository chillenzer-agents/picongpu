"""
internal representation of params to generate PIConGPU input files
"""

import sys

from . import collision as collision
from . import customuserinput as customuserinput
from . import field_solver as field_solver
from . import grid as grid
from . import laser as laser
from . import movingwindow as movingwindow
from . import output as output
from . import particle_functor as particle_functor
from . import rendering as rendering
from . import species as species
from . import util as util
from . import walltime as walltime
from .field_solver.Lehe import LeheSolver as LeheSolver
from .field_solver.Yee import YeeSolver as YeeSolver
from .output.checkpoint import Checkpoint as Checkpoint
from .output.energy_histogram import EnergyHistogram as EnergyHistogram
from .output.macro_particle_count import MacroParticleCount as MacroParticleCount
from .output.phase_space import PhaseSpace as PhaseSpace
from .runner import Runner as Runner
from .simulation import Simulation as Simulation

assert sys.version_info.major > 3 or sys.version_info.minor >= 9, "Python 3.9 is required for PIConGPU"
