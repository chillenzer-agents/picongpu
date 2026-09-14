from .Yee import YeeSolver as YeeSolver
from .Lehe import LeheSolver as LeheSolver

# every union member must have a rendering template fragment (see test_union_templates.py)
AnySolver = YeeSolver | LeheSolver
