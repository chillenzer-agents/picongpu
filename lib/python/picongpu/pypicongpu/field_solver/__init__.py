from .Lehe import LeheSolver as LeheSolver
from .Yee import YeeSolver as YeeSolver

AnySolver = YeeSolver | LeheSolver
