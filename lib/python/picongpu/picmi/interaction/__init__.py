"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

from picmistandard import PICMI_Interaction as PICMI_Interaction

from . import ionization as ionization
from .collision import Collision as Collision
from .collision import CollisionalPhysicsSetup as CollisionalPhysicsSetup
from .collision import ConstLogCollision as ConstLogCollision
from .collision import DynamicLogCollision as DynamicLogCollision
from .synchrotron import Synchrotron as Synchrotron


# The union of every interaction type that PIConGPU supports. It is used to type
# the ``Simulation.interactions`` field, so that the standard entry point accepts
# both the standard ``picmistandard.PICMI_FieldIonization`` and PIConGPU's own
# interaction classes.
Interaction = ionization.IonizationModel | Synchrotron | Collision | CollisionalPhysicsSetup

# The same set as concrete classes, for isinstance-based rejection of interaction
# types that PIConGPU does not support.
SUPPORTED_INTERACTION_TYPES = (ionization.IonizationModel, Synchrotron, Collision, CollisionalPhysicsSetup)
