#!/usr/bin/env bash
#
# This file is part of PIConGPU.
# Copyright 2026 PIConGPU contributors
# License: GPLv3+
#
# Release checklist: pre-flight validation before creating a PIConGPU release
# draft from a `release-*.*.*` branch. This implements the maintainer runbook
# described in the "before release"/"release" section of the release email:
#
#   - release branch exists and the working tree is clean
#   - the version triple is consistent across all places of record and has no
#     `-dev`/`.dev` suffix anymore
#   - the changelog contains an entry for the target version
#   - the PICMI `uv` install instructions (PEP 723 pins) point to the main
#     repository (not a fork)
#   - `.zenodo.json` creators roughly match the committers of the release range
#     (informational diff only, human must confirm)
#   - finally, print the `gh release create --draft` command for the human to
#     run (nothing is released by this script)
#
# Usage:
#   share/ci/release_check.sh [--repo <path>] [--previous-tag <git-ref>] [--branch <name>]
#
# Options:
#   --repo <path>       repository root to check (default: current directory)
#   --previous-tag <r>  git ref used as the lower bound of the release range
#                       for the zenodo creator diff (default: `git describe`)
#   --branch <name>     branch name to check (default: current HEAD branch)
#   -h, --help          show this help

set -euo pipefail

REPO_DIR=""
PREVIOUS_TAG=""
BRANCH=""

usage() {
    sed -n '2,40p' "$0" | sed 's/^# \{0,1\}//'
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --repo)
            REPO_DIR="$2"
            shift 2
            ;;
        --previous-tag)
            PREVIOUS_TAG="$2"
            shift 2
            ;;
        --branch)
            BRANCH="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "error: unknown option '$1'" >&2
            usage >&2
            exit 1
            ;;
    esac
done

if [[ -z "$REPO_DIR" ]]; then
    REPO_DIR=$(pwd)
fi
REPO_DIR=$(realpath "$REPO_DIR")

if [[ ! -d "$REPO_DIR/.git" ]]; then
    echo "ERROR: $REPO_DIR is not a git repository." >&2
    exit 1
fi

VERSION_FILE="$REPO_DIR/include/picongpu/version.hpp"
CONF_FILE="$REPO_DIR/docs/source/conf.py"
PYPROJECT_FILE="$REPO_DIR/lib/python/pyproject.toml"
CHANGELOG_FILE="$REPO_DIR/CHANGELOG.md"
ZENODO_FILE="$REPO_DIR/.zenodo.json"
MAIN_REPO="github.com/ComputationalRadiationPhysics/picongpu"

FATAL=0

fatal() {
    echo "FAIL: $1" >&2
    FATAL=1
}

warn() {
    echo "WARN: $1" >&2
}

info() {
    echo "  ~~  $1"
}

indent() {
    awk '{ print "       " $0 }'
}

echo "=================================================================="
echo "PIConGPU release checklist"
echo "=================================================================="
echo

# -- release branch and clean tree ###########################################

if [[ -z "$BRANCH" ]]; then
    BRANCH=$(git -C "$REPO_DIR" symbolic-ref --short HEAD 2>/dev/null || true)
fi

echo "[branch and tree]"
if [[ "$BRANCH" =~ ^release-[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "  ok:  on release branch '$BRANCH'"
else
    fatal "not on a release-*.*.* branch (got '$BRANCH'); use --branch if you are sure"
fi

if git -C "$REPO_DIR" diff --quiet && git -C "$REPO_DIR" diff --cached --quiet; then
    echo "  ok:  working tree is clean (no staged or unstaged tracked changes)"
else
    fatal "working tree is not clean; commit or stash changes first"
fi

UNTRACKED=$(git -C "$REPO_DIR" ls-files --others --exclude-standard | head -5)
if [[ -n "$UNTRACKED" ]]; then
    warn "untracked files present:"
    echo "$UNTRACKED" | indent
fi
echo

# -- version triple consistency ###############################################

echo "[version]"
if [[ -f "$VERSION_FILE" ]]; then
    MAJOR=$(grep -E '^#define PICONGPU_VERSION_MAJOR' "$VERSION_FILE" | awk '{print $3}')
    MINOR=$(grep -E '^#define PICONGPU_VERSION_MINOR' "$VERSION_FILE" | awk '{print $3}')
    PATCH=$(grep -E '^#define PICONGPU_VERSION_PATCH' "$VERSION_FILE" | awk '{print $3}')
    LABEL=$(grep -E '^#define PICONGPU_VERSION_LABEL' "$VERSION_FILE" | awk '{print $3}' | tr -d '"')
else
    MAJOR=""; MINOR=""; PATCH=""; LABEL=""
fi
VERSION="$MAJOR.$MINOR.$PATCH"

if [[ -n "$LABEL" ]]; then
    fatal "version.hpp still has release label '$LABEL' (must be empty for a release)"
fi

conf_version=""
conf_release=""
if [[ -f "$CONF_FILE" ]]; then
    conf_version=$(sed -n -E "s/^[[:space:]]*version[[:space:]]*=[[:space:]]*[\"']([^\"']+).*/\1/p" "$CONF_FILE" | head -1 || true)
    conf_release=$(sed -n -E "s/^[[:space:]]*release[[:space:]]*=[[:space:]]*[\"']([^\"']+).*/\1/p" "$CONF_FILE" | head -1 || true)
fi

pyproj_version=""
if [[ -f "$PYPROJECT_FILE" ]]; then
    pyproj_version=$(sed -n -E "s/^[[:space:]]*version[[:space:]]*=[[:space:]]*[\"']([^\"']+).*/\1/p" "$PYPROJECT_FILE" | head -1 || true)
fi

echo "  version.hpp:   $VERSION (label: '${LABEL:-empty}')"
echo "  conf.py:       version = '$conf_version', release = '$conf_release'"
echo "  pyproject.toml: version = '$pyproj_version'"

if [[ "$conf_version" != "$VERSION" ]]; then
    fatal "docs/source/conf.py version '$conf_version' != version.hpp '$VERSION'"
fi
if [[ "$conf_release" != "$VERSION" ]]; then
    fatal "docs/source/conf.py release '$conf_release' != version.hpp '$VERSION'"
fi
if [[ "$pyproj_version" != "$VERSION" ]]; then
    fatal "lib/python/pyproject.toml version '$pyproj_version' != version.hpp '$VERSION'"
fi
if [[ -n "$LABEL" || "$conf_release" == *-dev || "$pyproj_version" == *".dev" ]]; then
    fatal "a '-dev'/'.dev' suffix is still present somewhere"
fi
if [[ -z "$VERSION" ]]; then
    fatal "could not determine the version from version.hpp"
fi
echo

# -- changelog ################################################################

echo "[changelog]"
if [[ -f "$CHANGELOG_FILE" ]]; then
    changelog_top=$(grep -E '^[0-9]+\.[0-9]+\.[0-9]+[[:space:]-]*$' "$CHANGELOG_FILE" | head -1 || true)
    if [[ "$changelog_top" == "$VERSION" ]]; then
        echo "  ok:  CHANGELOG.md has an entry for $VERSION"
    else
        fatal "CHANGELOG.md top version entry is '$changelog_top', expected '$VERSION'"
    fi
else
    fatal "$CHANGELOG_FILE not found"
fi
echo

# -- PICMI uv install instructions pin the main repository ####################

echo "[PICMI uv install instructions (PEP 723)]"
uv_files=$(git -C "$REPO_DIR" ls-files \
    'lib/python/examples/**/*.py' \
    'lib/python/picongpu/picrc_builder.py')
if [[ -z "$uv_files" ]]; then
    info "no tracked PICMI example files found; skipping"
else
    bad_pins=0
    for f in $uv_files; do
        while IFS= read -r line; do
            repo_part=${line#*"git+https://github.com/"}
            repo_part=${repo_part%%@*}
            repo_part=${repo_part%%[\"# ]*}
            if [[ "$repo_part" == *"/picongpu"* && "$repo_part" != "ComputationalRadiationPhysics/picongpu" ]]; then
                echo "  FAIL: $f pins a fork: $line"
                bad_pins=1
            fi
        done < <(grep -H 'git+https://github.com/' "$REPO_DIR/$f" 2>/dev/null || true)
    done
    if [[ $bad_pins -eq 0 ]]; then
        echo "  ok:  all PICMI uv pins point to the main repository"
    else
        fatal "PICMI uv pins must point to $MAIN_REPO (not a fork)"
    fi
fi

fork_pins=$(grep -rH 'git+https://github.com/' "$REPO_DIR/lib/python/pyproject.toml" 2>/dev/null \
    | grep -v "$MAIN_REPO" | grep 'chillenzer' || true)
if [[ -n "$fork_pins" ]]; then
    warn "pyproject.toml still references fork repositories (must be upstreamed before a Python release):"
    echo "$fork_pins" | indent
fi
echo

# -- zenodo vs committers (informational) #####################################

echo "[zenodo vs. committers (informational)]"
if [[ -z "$PREVIOUS_TAG" ]]; then
    PREVIOUS_TAG=$(git -C "$REPO_DIR" describe --tags --abbrev=0 2>/dev/null || true)
fi

if [[ -z "$PREVIOUS_TAG" ]]; then
    info "no previous tag found; skipping zenodo vs committers diff"
elif ! command -v jq >/dev/null 2>&1; then
    info "jq not available; skipping zenodo vs committers diff"
elif [[ ! -f "$ZENODO_FILE" ]]; then
    warn "$ZENODO_FILE not found"
else
    committers=$(git -C "$REPO_DIR" log --use-mailmap --format='%an' "$PREVIOUS_TAG..HEAD" 2>/dev/null | sort -u)
    creators=$(jq -r '.creators[].name' "$ZENODO_FILE" 2>/dev/null | sort -u)
    missing_in_zenodo=$(comm -23 <(echo "$committers") <(echo "$creators") || true)
    missing_among_committers=$(comm -13 <(echo "$committers") <(echo "$creators") || true)
    echo "  release range: $PREVIOUS_TAG..HEAD"
    if [[ -n "$missing_in_zenodo" ]]; then
        info "committers without a .zenodo.json creator entry (add them?):"
        echo "$missing_in_zenodo" | indent
    fi
    if [[ -n "$missing_among_committers" ]]; then
        info "creators with no commit in this range (move to contributors?):"
        echo "$missing_among_committers" | indent
    fi
    if [[ -z "$missing_in_zenodo" && -z "$missing_among_committers" ]]; then
        echo "  ok:  creators match the committers of the release range"
    else
        info "please confirm the creators/contributors in .zenodo.json manually"
    fi
fi
echo

# -- final verdict + gh command ###############################################

echo "=================================================================="
if [[ $FATAL -eq 1 ]]; then
    echo "RELEASE CHECKLIST RESULT: FAILED"
    echo "Fix the problems above before creating the release draft."
    exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
    warn "gh CLI not found; the draft release command is printed for reference"
fi

TAG="$VERSION"
echo "RELEASE CHECKLIST RESULT: OK"
echo
echo "Create the draft release with (paste the changelog summary as notes):"
echo
echo "  gh release create $TAG \\"
echo "      --draft \\"
echo "      --target $BRANCH \\"
echo "      --title \"PIConGPU $TAG\" \\"
echo "      --notes-file <changelog-summary>"
echo
exit 0
