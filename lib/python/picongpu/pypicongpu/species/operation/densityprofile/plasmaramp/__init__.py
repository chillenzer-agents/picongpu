from .exponential import Exponential
from .none import None_

AllPlasmaRamps = Exponential | None_
__all__ = ["AllPlasmaRamps", "Exponential", "None_"]
