.. _development-debugging:

Debugging
=========

.. sectionauthor:: Sergei Bastrakov

When investigating the reason of a crashing simulation, it is very helpful to reduce the setup as much as possible while the crash is still happening.
This includes moving to fewer (and ideally to 1) MPI processes, having minimal grid size (ideally 3 supercells), disabling unrelated plugins and simulation stages.
Such a reduction should be done incrementally while checking whether the issue is still observed.
Knowing when the issue disappears could hint to its source.
This process also significantly speeds up and helps to focus a following deeper look.

The following build options can assist the investigation:

* ``PIC_VERBOSE=<N>`` sets log detail level for PIConGPU, highest level is 127.
* ``PMACC_VERBOSE=<N>`` sets log detail level for pmacc, highest level is 127.
* ``PMACC_BLOCKING_KERNEL=ON`` makes each kernel invocation blocking, which helps to narrow a crash down to a particular kernel.
* ``PMACC_ASYNC_QUEUES=OFF`` disables asynchronous alpaka queues, also helps to narrow a crash down to a particular place.
* ``CMAKE_BUILD_TYPE=Debug`` compile in debug mode where all assertions are activated. Compiling in debug mode will slowdown your kernels!

These options can be passed when building, or manually modified via cmake.
An example build command is

.. code:: bash

   pic-build -c "-DPIC_VERBOSE=127 -DPMACC_VERBOSE=127 -DPMACC_BLOCKING_KERNEL=ON -DPMACC_ASYNC_QUEUES=OFF"


If you encounter an error during reading or writing of openPMD files, it can be helpful to run openPMD-api with verbose output.
This can be done by setting the following environment variable either in your environment (e.g. ``picongpu.profile``) or in your submit script ``./tbg/submit.start`` before executing ``picongpu``.

.. code:: bash

   export OPENPMD_VERBOSE=1


Additionally, you can activate IO logging in PIConGPU by adding the login level ``32``.
This can be done via command flags (see above) when using ``pic-build`` or via ``ccmake .`` in the ``.build`` directory.
To debug the performance of openPMD output in PIConGPU, set the CMake variable ``PIC_OPENPMD_TIMETRACE_NUMBER_OF_FILES`` to ``1`` to obtain detailed time information about the I/O steps.

When reporting a crash, it is helpful if you attached the output ``stdout`` and ``stderr`` of such a build.

Log Levels
----------

The verbosity options above combine bit flags.
To activate several levels, add their values.

PIConGPU log levels (``include/picongpu/debug/PIConGPUVerbose.hpp``):

====== ====================
value  level
====== ====================
0      ``NOTHING``
1      ``PHYSICS``
2      ``DOMAINS``
4      ``CRITICAL``
8      ``MEMORY``
16     ``SIMULATION_STATE``
32     ``INPUT_OUTPUT``
====== ====================

pmacc log levels (``include/pmacc/debug/PMaccVerbose.hpp``):

====== ====================
value  level
====== ====================
0      ``NOTHING``
1      ``MEMORY``
2      ``INFO``
4      ``CRITICAL``
8      ``MPI``
16     ``CUDA_RT``
32     ``COMMUNICATION``
64     ``EVENT``
====== ====================

For example, ``-DPIC_VERBOSE=21`` enables ``PHYSICS`` (1), ``CRITICAL`` (4) and
``SIMULATION_STATE`` (16).

Inspecting Resolved Types
-------------------------

A useful tool to find the resolved type of an object that causes a compile-time error is
``PMACC_CASSERT_MSG_TYPE`` from ``include/pmacc/static_assert.hpp``:

.. code:: c++

   PMACC_CASSERT_MSG_TYPE(
       This_is_the_resolved_type_of_MyObjectType,
       MyObjectType,
       1 == 2
   );
   MyObjectType myObject; // this declaration crashed previously
   myObject(arg1, arg2, ...);

The first argument is a message and must be a valid C++ identifier.
The second argument is the type to resolve.
The remaining arguments form a condition; if it is false, the static assert fails and prints the message
and the resolved type.

Parallel Debugging
------------------

This section collects hints for debugging a hybrid (MPI + accelerator) application.
The device-side tools below apply to the CUDA backend.
Consider at least the build options listed above, in particular ``CMAKE_BUILD_TYPE=Debug`` and
``PMACC_BLOCKING_KERNEL=ON``, when using them.

MPI + Valgrind
^^^^^^^^^^^^^^

Use the `OpenMPI suppressions list <https://www.open-mpi.org/faq/?category=debugging#valgrind_clean>`_:

.. code:: bash

   mpiexec <mpi flags> valgrind --suppressions=$MPI_ROOT/share/openmpi/openmpi-valgrind.supp picongpu ...

See also the `Valgrind manual on debugging MPI parallel programs <http://valgrind.org/docs/manual/mc-manual.html#mc-manual.mpiwrap>`_.

Workflow to create suppression files
""""""""""""""""""""""""""""""""""""

Suppression files for MPI, network layers and I/O libraries are often out of date or do not exist.
To suppress the background noise, first run the program in the configuration that works and collect
suppressions, then run it again with the feature under investigation enabled.

.. code:: bash

   # 1. run PIConGPU without the feature under test ("train" the suppression file)
   valgrind --leak-check=full --show-reachable=yes --error-limit=no --gen-suppressions=all \
       --log-file=picongpu_all.log ./bin/picongpu -d 1 1 1 -g 12 80 12 --periodic 1 1 1 -s 10
   cat picongpu_all.log | ./parse_valgrind_suppressions.sh > picongpu_all.supp

   # 2. run again with the feature enabled, e.g. the openPMD plugin
   valgrind --leak-check=full --show-reachable=yes --error-limit=no \
       --suppressions=./picongpu_all.supp --log-file=picongpu_io.log \
       ./bin/picongpu -d 1 1 1 -g 12 80 12 --periodic 1 1 1 -s 10 --openPMD.period 10 --openPMD.file simData

This only helps if the memory violation is triggered at run time and is not already present in the
first run.
The `parse_valgrind_suppressions.sh <https://github.com/ComputationalRadiationPhysics/picongpu/files/2629353/parse_valgrind_suppressions.sh.txt>`_
script was originally taken from the `wxWidgets wiki <https://wiki.wxwidgets.org/Parse_valgrind_suppressions.sh>`_.

MPI + GDB
^^^^^^^^^

For multi-node host-side debugging, log into an interactive shell or batch session with X forwarding
(``ssh -X``) and launch PIConGPU with ``gdb``, triggering start and backtrace automatically:

.. code:: bash

   mpiexec <mpi flags> xterm -e gdb -ex r -ex bt --args picongpu ...

For non-interactive use, use ``gdb --batch -ex r -ex bt ...``.

MPI + CUDA-MEMCHECK
^^^^^^^^^^^^^^^^^^^

.. code:: bash

   mpiexec <mpi flags> cuda-memcheck --tool <memcheck|racecheck> picongpu ...

CUDA-GDB
^^^^^^^^

For single-node device-side debugging, see the `CUDA-GDB manual <http://docs.nvidia.com/cuda/cuda-gdb/>`_.
Compile with device debug symbols (``-g -G``) if you want to set device-side breakpoints.
Note that this usually disables code optimization and can alter the behavior of race conditions.

.. code:: bash

   cd <path>/simOutput
   cuda-gdb --args <path2picongpu> -d 1 1 1 -g <...> -s 100 <...>

Inside ``cuda-gdb``:

.. code:: text

   # breakpoints before running the code (if the code line was not optimized out)
   b <FileName>:<LineNumber>
   # run program
   r
   # print a variable when the code stopped or crashed
   print <var>
   # backtrace: where is the current line of code in the program
   bt
   # surrounding code lines
   list

For non-interactive use, use ``cuda-gdb --batch -ex r -ex bt ...``.
