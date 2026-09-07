.. _development-ci:

Continuous Integration
======================

.. sectionauthor:: René Widera

What is tested?
---------------

The CI is compiling tests with different compilers and boost versions.
We compile examples, tests, and benchmark input sets from ``share/picongpu``.
Unit tests for PMacc from ``include/pmacc/test`` and examples under ``share/pmacc`` will be compiled and executed on the corresponding compute device.
PIConGPU unit test from ``share/picongpu/unit`` will be compiled and executed on the corresponding compute device.
PICMI from ``share/picongpu/pypicongpu`` will be compiled too.

Compiler chains
---------------

The CI is testing different version of

* ``nvcc`` with ``g++`` for NVIDIA CUDA compute devices
* ``clang`` with HIP for AMD ROCm compute devices
* ``clang`` as NVIDIA CUDA compiler for NVIDIA CUDA devices
* ``clang`` and ``g++`` for the serial alpaka accelerator to target x86-CPU compute devices

Test PR
-------

Pull requests will perform all tests described above.
By default PIConGPU input sets will only compile a reduced set of all setups.
Only the first input variation from ``cmakeFlags`` will be compiled
There is no guarantee that each setup is compiled with at least one version of the compiles chains above.
It is guaranteed that each compiler version of all compiler chains is compiling at least one PIConGPU input set.

Test dev branch
---------------

Merged PRs will perform more extensive tests compared to the PR tests.
Each PIConGPU input set is compiled at least with one compiler version of each compiler tool chain.

CI Control via Commit Message
-----------------------------

It is possible to control which compile tests will be executed for the pull request and dev branch.
The last commit of a pull request can contain a command in form of ``ci: <command>`` which will be taken into account by the CI.
A command must be the only text/string on a line, it is not case sensitive and can have spaces before or behind.

commands:

* ``ci: no-compile`` is disabling PIConGPU and PMacc compile and runtime tests
* ``ci: full-compile`` will execute for a PR all tests the CI is performing when PRs get merged to the dev branch.
* ``ci: picongpu`` only PIConGPU compile and runtime tests will be performed
* ``ci: pmacc`` only PMacc compile and runtime tests will be performed
* ``ci: no-python-compile`` disables only the Python-layer compile and end-to-end tests
  (``pypicongpu-compiling-test`` and ``pypicongpu-end-to-end-test``) while keeping the
  C++ compile/runtime matrix and the Python quick tests enabled. This is the
  fine-grained counterpart of ``ci: no-compile`` for contributors touching only
  the Python layer.

In addition to the commit-message commands the GitHub label ``CI:no-compile`` is honoured;
it behaves like ``ci: no-compile``.

All flags are computed by the shared script ``share/ci/ci_flags.sh``, which is the single
source of truth for both the C++ test matrix generator
(``share/ci/generate_reduced_matrix.sh``) and the Python-layer jobs
(``.base_pypicongpu_compile_test``). The Python-layer jobs skip compilation whenever
``CI_NO_COMPILE`` is set, i.e. for ``ci: no-compile``, the ``CI:no-compile`` label and
``ci: no-python-compile``.

The Python quick-test matrix (``pypicongpu-full-matrix``) runs only pure-Python unit and
integration tests and does *not* compile PIConGPU, so it is unaffected by the no-compile
flags. ``ci: picongpu`` keeps the Python-layer tests enabled: for the Python jobs the
PIConGPU layer *is* the Python layer, so there is no independent PMacc counterpart that
could be deselected by ``ci: pmacc``.
