#!/bin/bash
set -euxo pipefail

INPUT_DIRECTORY="$1"
BIN_DIRECTORY="$2"
TBG_DIRECTORY="$3"
SUBMISSION_INFORMATION="$4"
LINK_RESULTS_SCRIPT="$5"

cp -r "$BIN_DIRECTORY" "$INPUT_DIRECTORY/bin"

cp -r "$TBG_DIRECTORY" tbg
cp "$SUBMISSION_INFORMATION" submission_information.txt
cp "$LINK_RESULTS_SCRIPT" link_results.sh
