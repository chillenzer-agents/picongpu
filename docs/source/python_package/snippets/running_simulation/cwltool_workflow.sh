#!/bin/bash
# BEGIN-CWLTOOL-WORKFLOW
CWL_ARGS="--leave-tmpdir --preserve-entire-environment --cachedir=.cwl_cache"
cd $RUN_DIR
cwltool $CWL_ARGS $RUN_DIR/input/workflow/workflow.cwl $RUN_DIR/input/workflow/input.yaml
./link_results.sh
# END-CWLTOOL-WORKFLOW
