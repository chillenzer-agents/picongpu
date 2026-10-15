# Preserve axis positions in openPMD range serialization

## Problem and behavior

An unrestricted `RangeSpec` axis previously serialized as an empty component.
The downstream range parser skips empty comma-separated entries, so a request
to restrict only y could be interpreted as an x restriction. Serialize an
unrestricted axis as `:` to retain its position. Also accept an existing
`RangeSpec` instance directly instead of attempting to wrap it as raw data.

This corrects existing PIConGPU openPMD range handling. It adds no new
PICMI-standard parameter and does not change backend configuration schemas.

## Validation

From the repository root with Python test dependencies installed:

```bash
PIC_RC=/tmp/picmi-rebundle-no-config.toml \
MPLCONFIGDIR=/tmp/picmi-rebundle-matplotlib \
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/lib/python" \
python -m pytest -q -p no:cacheprovider \
  lib/python/test/picongpu/quick/picmi/diagnostics/test_field_dump.py --tb=short
```

Result: **11 passed**. Tests cover unrestricted, x-, y- and z-restricted
ranges, both as raw entries and existing `RangeSpec` objects. Python tests
only; no PIConGPU compilation or simulation was performed.
