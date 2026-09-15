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
that `get_as_pypicongpu` keeps working. `translate` (see `picmi.translate`)
discards every cross-object requirement from the reachable species and re-derives
it from reachability alone, so its output is independent of this switch in either
state: an unadded model is not reachable and contributes nothing, an added model
is re-derived, and any incumbent `__init__` pollution carried into the copy is
stripped before re-derivation.
"""

INIT_MUTATION_ENABLED = True
