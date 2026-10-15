# Configure shared TWTS arithmetic precision and envelope cutoff

## Problem and behavior

TWTSTight previously fixed its internal scalar arithmetic to the simulation
precision and its envelope cutoff to six sigmas. Some setups require an
independent internal precision and cutoff for every TWTS pulse. Add the shared
controls `PrecisionConfig(twts=..., twts_num_sigmas=...)` through PICMI and
render them in the existing `precision.param` infrastructure. The library
TWTSTight header consumes the guarded macros, with old setups retaining core
precision and cutoff six.

The controls apply to both incident-field and background-field TWTS pulses.
They change the analytic functor's internal arithmetic and cutoff; returned
field storage, amplitude scaling and switching-window arithmetic remain at
simulation precision. These are PIConGPU-specific numerical controls, not
PICMI-standard laser parameters. There is no additional parameter file.

## Validation

From the repository root with Python test dependencies installed:

```bash
PIC_RC=/tmp/picmi-rebundle-no-config.toml \
MPLCONFIGDIR=/tmp/picmi-rebundle-matplotlib \
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/lib/python" \
python -m pytest -q -p no:cacheprovider \
  lib/python/test/picongpu/quick/pypicongpu/test_memory_config.py --tb=short
```

Result: **59 passed**: 58 original cases plus a focused check that generated
macro names/values are consumed by the shared C++ header. Inputs are checked
for valid precision and positive uint32 cutoff, including their defaults.
This verifies Python conversion and generated text; C++ compilation, device
execution and numerical stability at larger cutoffs remain to be checked
during upstream review.
