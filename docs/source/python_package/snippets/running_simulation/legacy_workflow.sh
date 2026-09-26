#!/bin/bash
# BEGIN-LEGACY-WORKFLOW
cd $RUN_DIR/input
source workflow/scripts/picongpu.profile
pic-build
tbg $TBG_ARGS $RUN_DIR
# END-LEGACY-WORKFLOW
