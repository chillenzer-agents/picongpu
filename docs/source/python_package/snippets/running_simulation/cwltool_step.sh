#!/bin/bash
# BEGIN-CWLTOOL-STEP
cd $RUN_DIR

# either provide the necessary input definitions on the commandline
# (e.g. `build.cwl` requires at least `include_directory` and `script`):
cwltool $CWL_ARGS $RUN_DIR/input/workflow/steps/build.cwl --include_directory $RUN_DIR/input/include --script $RUN_DIR/input/workflow/scripts/build.sh

# or write a custom `my_input.yaml` file with content like:
# include_directory: <RUN_DIR>/input
# script: <RUN_DIR>/input/workflow/scripts/build.sh
cwltool $CWL_ARGS $RUN_DIR/input/workflow/steps/build.cwl my_input.yaml
# END-CWLTOOL-STEP
