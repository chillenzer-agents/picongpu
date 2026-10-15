# Expose runtime grid adjustment and progress options

## Problem and behavior

The generated run configuration could not express PIConGPU's automatic grid
adjustment and progress interval options. Add
`Simulation.picongpu_auto_adjust_grid` and
`Simulation.picongpu_progress_percent`, pass them through the backend and
render the corresponding command-line options.

`None` leaves each option unset and preserves the C++ default. Explicit
`False` emits `--autoAdjustGrid false`; the progress interval accepts an
integer from 1 to 100. Both names are PIConGPU extensions, not standard PICMI
simulation parameters. Neither changes the declared grid or step count.

## Validation

From the repository root with Python test dependencies installed:

```bash
PIC_RC=/tmp/picmi-rebundle-no-config.toml \
MPLCONFIGDIR=/tmp/picmi-rebundle-matplotlib \
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/lib/python" \
python -m pytest -q -p no:cacheprovider \
  lib/python/test/picongpu/quick/picmi/test_runtime_options.py \
  lib/python/test/picongpu/quick/picmi/test_simulation.py --tb=short
```

Result: **107 passed**. Tests cover omission, explicit `False`, progress
bounds and generated N.cfg options. No PIConGPU compilation or simulation was
performed.
