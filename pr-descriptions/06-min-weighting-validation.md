# Validate minimum macroparticle weighting in the selected precision

## Problem and behavior

PIConGPU already exposes `Simulation.picongpu_min_weighting`, but permissive
numeric coercion accepted booleans and numeric strings. A positive Python
float could also underflow to zero or overflow when emitted as the default
float32 `MIN_WEIGHTING` constant.

Make public and backend input strict, then validate that the value remains
positive and finite in the selected core precision. Omission and explicit
`None` still use upstream's native default of `10.0`; valid explicit values
and float64 use remain supported. This tightens an existing PIConGPU extension
and adds no new PICMI-standard parameter.

## Validation

From the repository root with Python test dependencies installed:

```bash
PIC_RC=/tmp/picmi-rebundle-no-config.toml \
MPLCONFIGDIR=/tmp/picmi-rebundle-matplotlib \
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/lib/python" \
python -m pytest -q -p no:cacheprovider \
  lib/python/test/picongpu/quick/picmi/test_min_weighting.py \
  lib/python/test/picongpu/quick/picmi/test_simulation.py --tb=short
```

Result: **111 passed**. Tests cover omitted/None defaults, invalid types and
values, float32 limits, float64 allowance, generated constants and particle
creation thresholds. No PIConGPU compilation or simulation was performed.
