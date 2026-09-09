"""
Data structures to specify and initialize particle species.

Note that the data structure (the classes) here use a different architecure
than both (!) PIConGPU and PICMI.

Please refer to the documentation for a deeper discussion.
"""

from . import attribute, constant, operation
from .species import Species

__all__ = [
    "Species",
    "attribute",
    "constant",
    "operation",
]
