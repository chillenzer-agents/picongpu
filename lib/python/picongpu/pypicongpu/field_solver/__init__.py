"""
SPDX-FileCopyrightText: 2025 PIConGPU contributors
SPDX-License-Identifier: GPL-3.0-or-later
"""

from .ArbitraryOrderFDTD import ArbitraryOrderFDTDSolver as ArbitraryOrderFDTDSolver
from .CKC import CKCSolver as CKCSolver
from .Lehe import LeheSolver as LeheSolver
from .NoneSolver import NoneSolver as NoneSolver
from .Yee import YeeSolver as YeeSolver

AnySolver = YeeSolver | LeheSolver | CKCSolver | ArbitraryOrderFDTDSolver | NoneSolver
