"""
internal representation of params to generate PIConGPU input files
"""

from . import customuserinput, grid, laser, output, rendering, species, util
from .field_solver.ArbitraryOrderFDTD import ArbitraryOrderFDTDSolver
from .field_solver.CKC import CKCSolver
from .field_solver.Lehe import LeheSolver
from .field_solver.NoneSolver import NoneSolver
from .field_solver.Yee import YeeSolver
from .output.checkpoint import Checkpoint
from .output.energy_histogram import EnergyHistogram
from .output.field_energy_monitor import FieldEnergyMonitor
from .output.macro_particle_count import MacroParticleCount
from .output.phase_space import PhaseSpace
from .runner import Runner
from .simulation import Simulation

__all__ = [
    "ArbitraryOrderFDTDSolver",
    "CKCSolver",
    "Checkpoint",
    "EnergyHistogram",
    "FieldEnergyMonitor",
    "LeheSolver",
    "MacroParticleCount",
    "NoneSolver",
    "PhaseSpace",
    "Runner",
    "Simulation",
    "YeeSolver",
    "customuserinput",
    "grid",
    "laser",
    "output",
    "rendering",
    "species",
    "util",
]

# note: put down here b/c linter complains if imports are not at top
import sys

# friendly error for too-old interpreters; kept although it predates the
# minimum supported version (UP036)
if sys.version_info < (3, 9):  # noqa: UP036
    raise AssertionError("Python 3.9 is required for PIConGPU")
