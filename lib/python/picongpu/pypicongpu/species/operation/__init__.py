from .createdensity import CreateDensity
from .simplemomentum import SimpleMomentum
from .setchargestate import SetChargeState

from . import densityprofile
from . import momentum

# every union member must have a rendering template fragment (see test_union_templates.py)
AnyOperation = CreateDensity | SimpleMomentum | SetChargeState

__all__ = [
    "AnyOperation",
    "CreateDensity",
    "SimpleMomentum",
    "SetChargeState",
    "densityprofile",
    "momentum",
]
