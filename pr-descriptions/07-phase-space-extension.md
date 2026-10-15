# Select PhaseSpace output filename extensions through PICMI

## Problem and behavior

The PIConGPU PhaseSpace plugin has a per-instance filename-extension CLI
option, but the PICMI diagnostic could not set it. Add the PIConGPU extension
`PhaseSpace.picongpu_extension` for a bare output suffix such as `"bp"` or
`"h5"`. Omission retains the plugin default.

Multiple PhaseSpace instances for one species share indexed CLI options. The
backend rejects a default extension followed by an explicit one for that
species, because omitting an earlier CLI value would shift the later value to
the wrong instance. Filtered species are included in this check.

This is a PIConGPU-specific PhaseSpace option, not a PICMI-standard diagnostic
parameter or a change to the general openPMD backend configuration.

## Validation

From the repository root with Python test dependencies installed:

```bash
PIC_RC=/tmp/picmi-rebundle-no-config.toml \
MPLCONFIGDIR=/tmp/picmi-rebundle-matplotlib \
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/lib/python" \
python -m pytest -q -p no:cacheprovider \
  lib/python/test/picongpu/quick/picmi/diagnostics/test_phase_space_extensions.py \
  lib/python/test/picongpu/quick/picmi/diagnostics/test_phase_space.py --tb=short
```

Result: **45 passed**. Tests check suffix validation, default omission,
per-instance CLI order, filtered species and generated input files. No
PIConGPU compilation or simulation was performed.
