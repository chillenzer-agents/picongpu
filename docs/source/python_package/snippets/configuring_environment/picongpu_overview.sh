#!/bin/bash
# BEGIN-PICONGPU-OVERVIEW
picongpu rc build                # interactive .picongpurc.toml configuration builder
picongpu rc print                # print the full resolved rc_params content
picongpu dependencies install    # build the preset's compile-time dependencies
picongpu dependencies check      # verify the preset's dependency directories
picongpu shell                   # interactive shell with a picongpu.profile sourced
picongpu shell run pic-build     # run a single command in that environment
# END-PICONGPU-OVERVIEW
