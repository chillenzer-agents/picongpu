from .ArbitraryOrderFDTD import ArbitraryOrderFDTDSolver as ArbitraryOrderFDTDSolver
from .CKC import CKCSolver as CKCSolver
from .Lehe import LeheSolver as LeheSolver
from .NoneSolver import NoneSolver as NoneSolver
from .Yee import YeeSolver as YeeSolver

# every union member must have a rendering template fragment (see test_union_templates.py)
AnySolver = YeeSolver | LeheSolver | CKCSolver | ArbitraryOrderFDTDSolver | NoneSolver
