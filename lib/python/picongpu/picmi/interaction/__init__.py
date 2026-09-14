from . import ionization as ionization
from .collision import Collision as Collision
from .collision import CollisionalPhysicsSetup as CollisionalPhysicsSetup
from .collision import ConstLogCollision as ConstLogCollision
from .collision import DynamicLogCollision as DynamicLogCollision
from .synchrotron import Synchrotron as Synchrotron

Interaction = ionization.IonizationModel | Synchrotron | Collision | CollisionalPhysicsSetup
