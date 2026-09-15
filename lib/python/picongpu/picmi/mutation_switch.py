"""
This file is part of PIConGPU.
Copyright 2026 PIConGPU contributors
Authors: Julian Lenz
License: GPLv3+
"""

"""
Switch for the `__init__`-level cross-object requirement registration.

The incumbent PICMI path registers requirements onto *shared* species inside
other objects' `__init__` (ionization models onto the ion species, synchrotron
onto the electron species, radiation diagnostics onto their species). This is the
anti-pattern that issue #107 targets, and the root cause of upstream #5727 (an
`IonizationModel` that is constructed but never added to `picongpu_interaction`
still pollutes the ion species).

`INIT_MUTATION_ENABLED` (default `True`) keeps the incumbent behaviour intact so
that `get_as_pypicongpu` keeps working. `translate` (see `picmi.translate`) is
written to work correctly in *both* states: it never relies on `__init__` side
effects, so turning this switch off does not change `translate`'s output.
"""

INIT_MUTATION_ENABLED = True
