from . import ionization
from .collision import Collision, CollisionalPhysicsSetup, ConstLogCollision, DynamicLogCollision
from .synchrotron import Synchrotron

Interaction = ionization.IonizationModel | Synchrotron | Collision | CollisionalPhysicsSetup

__all__ = [
    "Interaction",
    "ionization",
    "Synchrotron",
    "Collision",
    "ConstLogCollision",
    "DynamicLogCollision",
    "CollisionalPhysicsSetup",
]
