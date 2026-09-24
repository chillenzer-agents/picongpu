#!/bin/bash

# This file is part of PIConGPU.
# Copyright 2023-2026 PIConGPU contributors
# Authors: Simeon Ehrig, Julian Lenz
# License: GPLv3+

# Compute the CI control flags for the current branch.
#
# The flags are honoured by both the C++ compile/runtime test matrix
# (share/ci/generate_reduced_matrix.sh) and the Python-layer (`pypicongpu-*`)
# jobs. They are computed from two signals:
#   - the last commit message of the branch (a whole-line `ci: <command>`),
#   - the GitHub label `CI:no-compile` (only meaningful for pull requests).
#
# Usage:
#   - source this file to populate the flags in the current shell, e.g.
#       source $CI_PROJECT_DIR/share/ci/ci_flags.sh
#   - or run it standalone for debugging/verification (prints the flags).
#
# Set flags (0 == false, 1 == true):
#   ci_no_compile          -- last commit is `ci: no-compile`
#   ci_full_compile        -- last commit is `ci: full-compile`
#   ci_picongpu            -- last commit is `ci: picongpu`
#   ci_pmacc               -- last commit is `ci: pmacc`
#   ci_no_python_compile   -- last commit is `ci: no-python-compile`
#                             (new: skip only the Python compile/end-to-end jobs)
#   ci_label_no_compile    -- GitHub label `CI:no-compile` is set on the PR
#   CI_NO_COMPILE          -- any no-compile signal applies to the Python layer:
#                             `ci_no_compile` or `ci_label_no_compile`
#                             or `ci_no_python_compile`

set -o pipefail

CI_FLAGS_REPO_DIR="${CI_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
if [ -z "${CI_FLAGS_REPO_DIR}" ] || ! git -C "$CI_FLAGS_REPO_DIR" rev-parse --git-dir >/dev/null 2>&1; then
    echo "ERROR: could not determine the PIConGPU repository directory for ci_flags.sh" >&2
    if [ "${BASH_SOURCE[0]}" == "$0" ]; then
        exit 1
    fi
    return 1
fi

# The flags are derived from `git log -1` (the last commit of the branch) and
# the GitHub label. They are evaluated exactly once per shell: the C++ matrix
# generator sources this file *before* `git_merge.sh` and
# `share/ci/generate_reduced_matrix.sh` sources it again *after* that script
# created a merge commit (a new HEAD whose message would mask the `ci:`
# commands). Evaluating once keeps the pre-merge view (i.e. the pull-request
# head) everywhere, so `ci: no-compile` and friends mean the same thing to both
# the C++ matrix and the Python-layer consumers.
if [ "${CI_FLAGS_COMPUTED:-0}" != "1" ]; then
    CI_FLAGS_COMPUTED=1

    # 0 == false; 1 == true
    ci_no_compile=$(git -C "$CI_FLAGS_REPO_DIR" log -1 | grep -q -i "^[[:blank:]]*ci:[[:blank:]]*no-compile[[:blank:]]*$" && echo "1" || echo "0")
    ci_full_compile=$(git -C "$CI_FLAGS_REPO_DIR" log -1 | grep -q -i "^[[:blank:]]*ci:[[:blank:]]*full-compile[[:blank:]]*$" && echo "1" || echo "0")
    ci_picongpu=$(git -C "$CI_FLAGS_REPO_DIR" log -1 | grep -q -i "^[[:blank:]]*ci:[[:blank:]]*picongpu[[:blank:]]*$" && echo "1" || echo "0")
    ci_pmacc=$(git -C "$CI_FLAGS_REPO_DIR" log -1 | grep -q -i "^[[:blank:]]*ci:[[:blank:]]*pmacc[[:blank:]]*$" && echo "1" || echo "0")
    ci_no_python_compile=$(git -C "$CI_FLAGS_REPO_DIR" log -1 | grep -q -i "^[[:blank:]]*ci:[[:blank:]]*no-python-compile[[:blank:]]*$" && echo "1" || echo "0")

    # GitHub label `CI:no-compile` -- only queried for pull requests in CI.
    # When not in CI (or the label cannot be queried) this stays 0.
    ci_label_no_compile=0
    if [ ! -z ${GITHUB_TOKEN+x} ] && [ ! -z ${CI_COMMIT_REF_NAME+x} ] && echo "$CI_COMMIT_REF_NAME" | grep -q "^pr-" ; then
        if "$CI_FLAGS_REPO_DIR/share/ci/pr_has_label.sh" "CI:no-compile" >/dev/null 2>&1 ; then
            ci_label_no_compile=1
        fi
    fi

    # umbrella flag used by the Python-layer jobs (pypicongpu-compiling-test
    # and pypicongpu-end-to-end-test): any no-compile signal skips compilation.
    CI_NO_COMPILE=0
    if [ "$ci_no_compile" -eq 1 ] || [ "$ci_label_no_compile" -eq 1 ] || [ "$ci_no_python_compile" -eq 1 ] ; then
        CI_NO_COMPILE=1
    fi
fi

# when run standalone (not sourced), print the computed flags
if [ "${CI_FLAGS_SOURCED:-0}" != "1" ] && [ "${BASH_SOURCE[0]}" == "$0" ] ; then
    echo "ci_no_compile=$ci_no_compile"
    echo "ci_full_compile=$ci_full_compile"
    echo "ci_picongpu=$ci_picongpu"
    echo "ci_pmacc=$ci_pmacc"
    echo "ci_no_python_compile=$ci_no_python_compile"
    echo "ci_label_no_compile=$ci_label_no_compile"
    echo "CI_NO_COMPILE=$CI_NO_COMPILE"
fi
