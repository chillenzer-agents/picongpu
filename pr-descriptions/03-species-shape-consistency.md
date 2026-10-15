# Use each species' particle shape for interpolation and Esirkepov deposition

## Problem and behavior

PICMI already accepted per-species particle shapes, including shapes inherited
from `Simulation`. Generated C++ nevertheless used the global field interpolation
and current solver aliases, so a species could carry a PQS shape flag while
gathering fields or depositing current with the global TSC shape.

Generate a distinct shape alias for each species and use it for the species
flag, `FieldToParticleInterpolation` and the existing Esirkepov current solver.
Default TSC and inherited/explicit species shapes remain supported. Reject the
diagnostic-only Counter shape as a simulation species shape because it cannot
provide field interpolation. NGP remains valid with Esirkepov.

This corrects the behavior of existing PICMI `particle_shape` input. It does
not introduce a new PICMI-standard option or an EmZ selection API.

## Validation

From the repository root with Python test dependencies installed:

```bash
PIC_RC=/tmp/picmi-rebundle-no-config.toml \
MPLCONFIGDIR=/tmp/picmi-rebundle-matplotlib \
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/lib/python" \
python -m pytest -q -p no:cacheprovider \
  lib/python/test/picongpu/quick/picmi/test_species_interpolation.py \
  lib/python/test/picongpu/quick/picmi/test_species.py \
  lib/python/test/picongpu/quick/picmi/test_simulation.py --tb=short
```

Result: **123 passed, 22 subtests passed**. The tests check default and
inherited shapes, mixed species, Counter rejection and generated interpolation
and Esirkepov definitions. They generate Python input only; C++ compilation
and device execution have not been performed.
