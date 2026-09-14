#!/bin/bash

# This file is part of PIConGPU.
# Copyright 2023-2024 PIConGPU contributors
# Authors: Simeon Ehrig
# License: GPLv3+

# - the script installs a Python environment
# - generates a modified requirements.txt depending of the environment variables for pypicongpu
# - install the dependencies and runs the pytest tests

set -e
set -o pipefail

function script_error {
    echo -e "\e[31mERROR: ${1}\e[0m"
    exit 1
}

export PICSRC=$CI_PROJECT_DIR
export PATH=$PATH:$PICSRC/bin
echo 'preset = "bash"' >/.picongpurc.toml

export PIC_EXAMPLES=$PICSRC/share/picongpu/examples

cd $CI_PROJECT_DIR

# use miniconda as python environment
apt update && apt install -y curl
cd /tmp/
curl -Ls https://github.com/mamba-org/micromamba-releases/releases/download/1.5.9-0/micromamba-linux-64.tar.bz2 | tar -xvj bin/micromamba
export MAMBA_ROOT_PREFIX=/tmp/mamba-forge/
mkdir -p "${MAMBA_ROOT_PREFIX}"
eval "$(./bin/micromamba shell hook -s posix)"
export PATH=$(pwd -P)/bin:$PATH
micromamba --version
micromamba config append channels conda-forge
micromamba config set channel_priority strict

cd $CI_PROJECT_DIR
# generates modified requirements.txt
micromamba create -n pypicongpu python=${PYTHON_VERSION} --ssl-verify false
micromamba activate pypicongpu
python3 --version
# install requirements of pyproject_toml_modifier.txt
pip3 install -r ${CI_PROJECT_DIR}/share/ci/install/pyproject_toml_modifier_requirements.txt
PYPROJECT_TOML_PATH=${CI_PROJECT_DIR}/lib/python/pyproject.toml

python3 $CI_PROJECT_DIR/share/ci/install/pyproject_toml_modifier.py \
    -i $PYPROJECT_TOML_PATH \
    -o $PYPROJECT_TOML_PATH \

# uninstall requirements of pyproject_toml_modifier.txt
pip3 uninstall -y -r ${CI_PROJECT_DIR}/share/ci/install/pyproject_toml_modifier_requirements.txt

echo "modified pyproject.toml: "
cat $PYPROJECT_TOML_PATH
echo ""

# install pypicongpu dependencies (including pytest for testing)
pip3 install -e "${CI_PROJECT_DIR}/lib/python/[test]"

# run quick tests
cd $CI_PROJECT_DIR/lib/python/test/picongpu
python3 -m pytest quick/

# both the compiling- and the end-to-end tests need cmake, boost and a C++ compiler
function setup_compile_environment {
    # setup cmake
    if [ ! -z ${CMAKE_VERSION+x} ]; then
        if agc-manager -e cmake@${CMAKE_VERSION} ; then
            export PATH=$(agc-manager -b cmake@${CMAKE_VERSION})/bin:$PATH
        else
            script_error "No implementation to install cmake ${CMAKE_VERSION}"
        fi
    else
        script_error "CMAKE_VERSION is not defined"
    fi

    # setup boost
    if [ ! -z ${BOOST_VERSION+x} ]; then
        if agc-manager -e boost@${BOOST_VERSION} ; then
            export CMAKE_PREFIX_PATH=$(agc-manager -b boost@${BOOST_VERSION}):$CMAKE_PREFIX_PATH
        else
            script_error "No implementation to install boost ${BOOST_VERSION}"
        fi
    else
        script_error "BOOST_VERSION is not defined"
    fi

    # set C++ compiler
    export CXX=$CXX_VERSION
}

# executing the compiling tests is optional
# for the compiling test we need: cmake, boost and openmpi
# openmpi is available without extra work
if [ ! -z ${PYTHON_COMPILING_TEST+x} ]; then
    export PIC_BACKEND=omp2b
    setup_compile_environment
    # select the compiling suite by marker so that CI always runs exactly the
    # documented set (see lib/python/test/picongpu/README.md):
    # `pytest -m compiling` is equivalent to `pytest compiling/`
    python3 -m pytest -m compiling -v
fi

# executing the end-to-end tests is optional
# they need everything the compiling tests need plus a working MPI launch of the
# compiled simulation (openmpi is available without extra work)
if [ ! -z ${PYTHON_END_TO_END_TEST+x} ]; then
    export PIC_BACKEND=serial
    # the CI job runs as root, but OpenMPI refuses to start as root,
    # so the simulation was aborted by mpiexec before producing any output
    export OMPI_ALLOW_RUN_AS_ROOT=1
    export OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1
    setup_compile_environment
    # boost runtime libs must be findable by the compiled simulation binary
    export LD_LIBRARY_PATH=/opt/boost/${BOOST_VERSION}/lib:$LD_LIBRARY_PATH

    # select the end-to-end suite by marker (see lib/python/test/picongpu/README.md):
    # `pytest -m end_to_end` is equivalent to `pytest end_to_end/`
    set +e
    python3 -m pytest -m end_to_end -v
    end_to_end_returncode=$?
    set -e

    if [ ${end_to_end_returncode} -ne 0 ]; then
        echo "===== end-to-end tests failed (exit code ${end_to_end_returncode}), dumping diagnostics ====="
        echo "--- LD_LIBRARY_PATH ---"
        echo "${LD_LIBRARY_PATH}"
        echo ""
        echo "--- CMAKE_PREFIX_PATH ---"
        echo "${CMAKE_PREFIX_PATH}"
        echo ""
        # The end-to-end tests place the build in the runner's setup dir and
        # the simulation output in the run dir. The runner may create those
        # under /tmp (the pypicongpu-<ts>-{setup,run}-* defaults) or, as the
        # e2e tests do, under ${HOME}/data/NNNNNN/{setup,run}, so probe both.
        # shellcheck disable=SC2206 # deliberate globbing to enumerate the dirs
        setup_dirs=( /tmp/pypicongpu-*setup-* ${HOME}/data/*/setup )
        for setup_dir in "${setup_dirs[@]}"; do
            [ -d "${setup_dir}" ] || continue
            echo "=== setup dir: ${setup_dir} ==="
            binary=""
            for candidate in "${setup_dir}"/input/bin/picongpu "${setup_dir}"/bin/picongpu; do
                if [ -f "${candidate}" ]; then
                    binary="${candidate}"
                    break
                fi
            done
            if [ -n "${binary}" ]; then
                echo "--- unresolved dynamic dependencies of ${binary} ---"
                ldd "${binary}" 2>&1 | grep "not found" || echo "(none)"
            else
                echo "ERROR: simulation binary missing under ${setup_dir}"
            fi
            echo "--- top-level content of the setup dir ---"
            ls -la "${setup_dir}"
            echo ""
        done
        # shellcheck disable=SC2206 # deliberate globbing to enumerate the dirs
        run_dirs=( /tmp/pypicongpu-*run-* ${HOME}/data/*/run )
        for run_dir in "${run_dirs[@]}"; do
            [ -d "${run_dir}" ] || continue
            echo "=== run dir: ${run_dir} ==="
            if [ -f "${run_dir}/simOutput/output" ]; then
                echo "--- simulation output (simOutput/output) ---"
                cat "${run_dir}/simOutput/output"
            else
                echo "ERROR: no simulation output present: ${run_dir}/simOutput/"
            fi
            echo "--- top-level content of the run dir ---"
            ls -la "${run_dir}"
            echo ""
        done
        echo "===== end of diagnostics ====="
    fi

    exit ${end_to_end_returncode}
fi
