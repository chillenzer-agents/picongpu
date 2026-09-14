#!/usr/bin/env bash
#
# Copyright 2017-2024 Axel Huebl
#
# This file is part of PIConGPU.
#
# PIConGPU is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# PIConGPU is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with PIConGPU.
# If not, see <http://www.gnu.org/licenses/>.
#

# This file is a maintainer tool to bump the versions inside PIConGPU's
# source directory at all places where necessary.
#
# Usage:
#   src/tools/bin/newVersion.sh [ -n | --dry-run ]
#
# The tool reads the version (MAJOR.MINOR.PATCH[SUFFIX]) interactively and
# updates all three locations that carry the version triple:
#   - include/picongpu/version.hpp                 (single source of truth)
#   - docs/source/conf.py                          (Sphinx / RTD)
#   - lib/python/pyproject.toml                    (Python package, PEP-440)
#
# With `-n`/`--dry-run` the modifications are printed as a git-style diff
# without touching the working tree, which makes it safe to exercise.

set -euo pipefail

DRY_RUN=0

case "${1:-}" in
    -n|--dry-run)
        DRY_RUN=1
        ;;
    -h|--help)
        echo "usage: $0 [-n|--dry-run]" >&2
        echo "  -n, --dry-run   print the diff that would be applied without" >&2
        echo "                  modifying any files in the working tree" >&2
        exit 0
        ;;
    "")
        ;;
    *)
        echo "error: unknown option '$1'" >&2
        echo "usage: $0 [-n|--dry-run]" >&2
        exit 1
        ;;
esac

echo "Hi there, this is a PIConGPU maintainer tool to update the source"
echo "code of PIConGPU to a new version number on all places where"
echo "necessary."
echo "For it to work, you need write access on the source directory and"
echo "you should be working in a clean git branch without ongoing"
echo "rebase/merge/conflict resolves and without unstaged changes."
echo

# check source dir
REPO_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)
echo
echo "Your current source directory is: $REPO_DIR"
echo

read -p "Are you sure you want to continue? [y/N] " -r
echo

if [[ ! $REPLY =~ ^[Yy]$ ]]
then
    echo "You did not confirm with 'y', aborting."
    exit 1
fi

echo "We will now run a few sed commands on your source directory."
echo "Please answer the following questions about the version number"
echo "you want to set first:"
echo

read -p "MAJOR version? (e.g. 1) " -r
MAJOR=$REPLY
echo
read -p "MINOR version? (e.g. 2) " -r
MINOR=$REPLY
echo
read -p "PATCH version? (e.g. 3) " -r
PATCH=$REPLY
echo
read -p "SUFFIX? (e.g. rc2, dev, ... or empty) " -r
SUFFIX=$REPLY
echo

if [[ ! $MAJOR =~ ^[0-9]+$ || ! $MINOR =~ ^[0-9]+$ || ! $PATCH =~ ^[0-9]+$ ]]
then
    echo "error: MAJOR, MINOR and PATCH must be integer numbers." >&2
    exit 1
fi

# The SUFFIX is injected into sed replacement strings unescaped, so restrict it
# to characters that cannot break the `s/.../.../` editor. This must be checked
# *before* any file is modified.
if [[ -n "$SUFFIX" && ! "$SUFFIX" =~ ^[A-Za-z0-9._-]+$ ]]
then
    echo "error: SUFFIX may only contain alphanumerics and '.', '_', '-' (got '$SUFFIX')." >&2
    exit 1
fi

SUFFIX_STR=""
if [[ -n "$SUFFIX" ]]
then
    SUFFIX_STR="-$SUFFIX"
fi

VERSION_STR="$MAJOR.$MINOR.$PATCH$SUFFIX_STR"
# PEP-440 (lib/python/pyproject.toml) uses a dot instead of a dash: 0.9.0.dev
PYPROJECT_VERSION="$MAJOR.$MINOR.$PATCH${SUFFIX:+.$SUFFIX}"

echo
echo "Your new version is: $VERSION_STR"
echo

if [[ $DRY_RUN -eq 1 ]]
then
    echo "Dry-run mode (-n): no files will be modified."
fi

read -p "Is this information correct? Will now start updating! [y/N] " -r
echo

if [[ ! $REPLY =~ ^[Yy]$ ]]
then
    echo "You did not confirm with 'y', aborting."
    exit 1
fi

# Updates #####################################################################

# include/picongpu/version.hpp is the single source of truth. All other
# version strings are derived from the values entered here.

update_files() {
    local root="$1"

    # PIConGPU version.hpp
    sed -i "s/^[[:blank:]]*#[[:blank:]]*define[[:blank:]]\+PICONGPU_VERSION_MAJOR[[:blank:]]\+.*/#define PICONGPU_VERSION_MAJOR $MAJOR/g" \
        "$root/include/picongpu/version.hpp"
    sed -i "s/^[[:blank:]]*#[[:blank:]]*define[[:blank:]]\+PICONGPU_VERSION_MINOR[[:blank:]]\+.*/#define PICONGPU_VERSION_MINOR $MINOR/g" \
        "$root/include/picongpu/version.hpp"
    sed -i "s/^[[:blank:]]*#[[:blank:]]*define[[:blank:]]\+PICONGPU_VERSION_PATCH[[:blank:]]\+.*/#define PICONGPU_VERSION_PATCH $PATCH/g" \
        "$root/include/picongpu/version.hpp"
    sed -i "s/^[[:blank:]]*#[[:blank:]]*define[[:blank:]]\+PICONGPU_VERSION_LABEL[[:blank:]]\+.*/#define PICONGPU_VERSION_LABEL \"$SUFFIX\"/g" \
        "$root/include/picongpu/version.hpp"

    # sphinx / RTD
    #   docs/source/conf.py (modern quoting: version = "X.Y.Z")
    sed -i "s/^[[:blank:]]*version[[:blank:]]*=[[:blank:]]*[\"'].*/version = \"$MAJOR.$MINOR.$PATCH\"/g" \
        "$root/docs/source/conf.py"
    sed -i "s/^[[:blank:]]*release[[:blank:]]*=[[:blank:]]*[\"'].*/release = \"$VERSION_STR\"/g" \
        "$root/docs/source/conf.py"

    # Python package metadata
    #   lib/python/pyproject.toml (PEP-440: version = "X.Y.Z" or "X.Y.Z.dev")
    sed -i "s/^[[:blank:]]*version[[:blank:]]*=[[:blank:]]*[\"'].*/version = \"$PYPROJECT_VERSION\"/g" \
        "$root/lib/python/pyproject.toml"
}

if [[ $DRY_RUN -eq 1 ]]
then
    TMP_ROOT=$(mktemp -d)
    trap 'rm -rf "$TMP_ROOT"' EXIT
    mkdir -p "$TMP_ROOT/include/picongpu" \
             "$TMP_ROOT/docs/source" \
             "$TMP_ROOT/lib/python"
    cp "$REPO_DIR/include/picongpu/version.hpp"   "$TMP_ROOT/include/picongpu/version.hpp"
    cp "$REPO_DIR/docs/source/conf.py"            "$TMP_ROOT/docs/source/conf.py"
    cp "$REPO_DIR/lib/python/pyproject.toml"      "$TMP_ROOT/lib/python/pyproject.toml"

    update_files "$TMP_ROOT"

    echo
    echo "The following diff would be applied (dry-run):"
    echo
    MODIFIED=0
    for f in include/picongpu/version.hpp docs/source/conf.py lib/python/pyproject.toml
    do
        if ! git diff --no-index --ignore-submodules=all \
                "$REPO_DIR/$f" "$TMP_ROOT/$f" \
                | sed "s|$TMP_ROOT|{tmp}|g; s|$REPO_DIR|{repo}|g"
        then
            MODIFIED=1
        fi
    done

    if [[ $MODIFIED -eq 0 ]]
    then
        echo "No changes would be applied (version already $VERSION_STR?)."
    fi
    exit 0
fi

# Refuse to run on a dirty tree: the tool edits tracked files in place and the
# maintainer is expected to review the result with `git diff` afterwards.
if ! git -C "$REPO_DIR" diff --quiet || ! git -C "$REPO_DIR" diff --cached --quiet
then
    echo "error: your working tree has unstaged or staged changes." >&2
    echo "Please commit or stash them first." >&2
    exit 1
fi

update_files "$REPO_DIR"

# Epilog ######################################################################

echo
echo "Done. Please check your source, e.g. via"
echo "  git diff"
echo "now and commit the changes if no errors occured."
