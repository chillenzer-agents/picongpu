#!/usr/bin/env bash
# Render the self-contained EFP job script for the efp-jupiter-jsc preset
# and stage the environment profile with the input dataset (see the
# HPC Submission Internals page). Syntax-checked only.
set -euo pipefail

# BEGIN-EFP-JOB-SCRIPT
# Select the EFP preset in picongpurc.toml, then generate the setup from the
# PICMI script (sim.write_input_file("setup")). The preset sets TBG_SUBMIT and
# TBG_TPLFILE (etc/picongpu/efp-jupiter-jsc/gh200_efp.tpl).
cd setup

# Render the job script into the run directory; tbg -o overrides per-run
# variables such as the queue and the wall time. Prefer the preset defaults:
tbg -c etc/picongpu/N.cfg -o "TBG_queue=debug TBG_wallTime=01:00:00" "$SCRATCH/efp-run"

# Ship the generated profile with the input dataset so the job script is
# self-contained (it sources input/picongpu.profile when present).
cp workflow/scripts/picongpu.profile "$SCRATCH/efp-run/input/picongpu.profile"
# END-EFP-JOB-SCRIPT
