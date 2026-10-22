# Prevent overflow in generated memory-size expressions

## Problem and behavior

The generator formats some byte counts as products of unsuffixed C++ integer
literals. A 4 GiB reserve can therefore overflow an `int` intermediate before
the expression is assigned to `size_t`.

Promote large literals with `ULL` before multiplying. Small byte counts retain
their previous readable expressions. This is a generated-code correctness fix
for the existing `MemoryConfig` API; no new PICMI-standard parameter is added.

## Validation

From the repository root with Python test dependencies installed:

```bash
PIC_RC=/tmp/picmi-rebundle-no-config.toml \
MPLCONFIGDIR=/tmp/picmi-rebundle-matplotlib \
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/lib/python" \
python -m pytest -q -p no:cacheprovider \
  lib/python/test/picongpu/quick/pypicongpu/test_memory_config.py --tb=short
```

Result: **26 passed**. Tests cover values around 2 GiB and 4 GiB, MiB/KiB
rendering, a non-aligned large byte count, and existing memory configuration
behavior. The generated C++ text was inspected; no C++ compilation or
simulation was performed.
