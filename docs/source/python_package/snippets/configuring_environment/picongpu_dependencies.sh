#!/bin/bash
# BEGIN-PICONGPU-DEPENDENCIES
# build the compile-time dependencies the preset owns (best-effort)
picongpu dependencies install

# verify each dependency directory the preset's script owns
picongpu dependencies check
# END-PICONGPU-DEPENDENCIES
