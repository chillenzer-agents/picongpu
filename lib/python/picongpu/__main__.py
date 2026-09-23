"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+

Allow ``python -m picongpu`` by delegating to the ``picongpu`` CLI dispatcher.
"""

import sys

from picongpu.cli import main

if __name__ == "__main__":
    sys.exit(main())
