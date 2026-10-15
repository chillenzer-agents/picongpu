# Expose EmZ/EZ current deposition per species

## Problem and behavior

PICMI could generate only the default Esirkepov current solver, even though
PIConGPU also provides EmZ (called EZ in the related paper). Add the PIConGPU
extension `Species.picongpu_current_deposition`, accepting `"Esirkepov"`
(default), `"EmZ"` or the equivalent spelling `"EZ"`. Each species' resolved
particle shape is used for its selected solver. EmZ with NGP is rejected
because the in-plane current loops would be empty. Smoothing remains an
independent solver choice.

This is a PIConGPU-specific API, not a PICMI-standard declaration. Omission
retains Esirkepov. The backend serializes EZ as the canonical EmZ C++ type.

## Dependency and review base

This branch is intentionally **two commits** on the pinned local `dev`:

1. The exact commit from `pr/picmi-species-shape-consistency`, which fixes the
   shape flag, interpolation and Esirkepov deposition to use one species shape.
2. This EmZ-only commit, including this `PR.md` update.

Review this PR's second commit against PR-03. Submit/merge PR-03 first. If its
commit changes during review, replay only the EmZ commit onto its new tip; once
merged, replay only the EmZ commit onto updated `dev`.

## Validation

From the repository root with Python test dependencies installed:

```bash
PIC_RC=/tmp/picmi-rebundle-no-config.toml \
MPLCONFIGDIR=/tmp/picmi-rebundle-matplotlib \
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/lib/python" \
python -m pytest -q -p no:cacheprovider \
  lib/python/test/picongpu/quick/picmi/test_current_deposition.py \
  lib/python/test/picongpu/quick/picmi/test_species_interpolation.py \
  lib/python/test/picongpu/quick/picmi/test_species.py --tb=short
```

Result: **87 passed, 22 subtests passed**. Coverage includes alias equivalence,
shape inheritance, mixed species, NGP rejection, smoothing independence and
generated definitions. C++ compilation and device execution were not run.
