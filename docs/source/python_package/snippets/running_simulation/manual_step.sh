#!/bin/bash
# BEGIN-MANUAL-STEP
mkdir $RUN_DIR/build_step
cd $RUN_DIR/build_step
ln -s $RUN_DIR/input/include
ln -s $RUN_DIR/input/workflow/scripts/build.sh
./build.sh
# END-MANUAL-STEP
