#!/bin/bash
# BEGIN-PICONGPU-SHELL
# drop into an interactive shell with the generated default profile sourced
picongpu shell

# ... or with the picongpu.profile of a setup directory or run directory
picongpu shell --from my_run

# run a single command in that environment instead of an interactive shell
picongpu shell --from my_run run pic-build
# END-PICONGPU-SHELL
