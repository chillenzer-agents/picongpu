.. _usage-troubleshooting:

Troubleshooting and FAQ
=======================

.. note::

   This page combines the former *Troubleshooting* and *FAQ* wiki pages.

Common Problems
---------------

``pic-create``, ``pic-build``, ``pic-configure`` or ``tbg`` not found
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The helper tools are not installed system-wide.
Add PIConGPU's ``bin`` and ``src/tools/bin`` directories to your ``PATH``, e.g. by
:ref:`sourcing your profile <install-profile>`:

.. code-block:: bash

   export PATH=$PICSRC/bin:$PICSRC/src/tools/bin:$PATH

``pic-create``, ``pic-build``, ``pic-configure`` and ``pic-edit`` live in ``$PICSRC/bin``;
``tbg`` lives in ``$PICSRC/src/tools/bin``.

PIConGPU does not compile after changing or updating the branch
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Commonly, the input set was created for an older version of PIConGPU and no longer matches the code.
Create a fresh input set from the current source tree and migrate your changes:

.. code-block:: bash

   pic-create $PIC_EXAMPLES/LaserWakefield $HOME/picInputs/myLWFA-fresh

Also remove the ``.build`` directory of the old input set before rebuilding, so that no stale CMake
cache or previously cached default ``.param`` file is reused:

.. code-block:: bash

   cd $HOME/picInputs/myLWFA
   rm -rf .build
   pic-build

.. seealso::

   :ref:`our note on re-compiling <usage-params-rationale>` explains why changed ``.param`` files require a re-compile and why
   the build cache has to be cleaned after adding a new ``.param`` file.

Changed ``.param`` options have no effect
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Make sure that you edit the ``.param`` files of *your* input set and not the defaults in the PIConGPU
source tree, and delete the ``.build`` directory after adding a new ``.param`` file.
See :ref:`our note on re-compiling <usage-params-rationale>`.

A plugin is missing from ``picongpu --help``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Plugins with optional external dependencies are only available if the corresponding library was found
at configure time.
Check :ref:`the dependency chapter <install-dependencies>` for the optional libraries and re-run ``pic-configure`` after making
them available.

Frequently Asked Questions
--------------------------

How can I get help or report a bug?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Please open an `issue on GitHub <https://github.com/ComputationalRadiationPhysics/picongpu/issues/new>`_
instead of contacting the developers and maintainers directly.
Before posting, search the :doc:`manual <../index>` and the
`issue tracker <https://github.com/ComputationalRadiationPhysics/picongpu/issues>`_ for an existing
answer.

What information should a bug report contain?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Please list the basic properties of your environment, such as

- operating system and version (e.g. ``Ubuntu 24.04, 64 bit, x86``)
- compiler and version used (e.g. ``GCC 13.2``)
- CMake and version used
- loaded modules on an HPC system or installed packages on a desktop, including library versions
- the output of the ``pic-configure`` invocation and of ``cmake -L .`` in the ``.build`` directory
- if necessary, your input set (``.param`` files for compile-time options and ``.cfg`` files for
  run-time options)
- the complete ``stdout`` and ``stderr`` of the failing build or run

Why does compilation take so long?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

PIConGPU uses compile-time template specialization to generate exactly the kernels and particle
attributes required by your simulation.
This makes the executed code fast, but shifts work into the compile step.
Due to compiler limitations with header-only libraries, the compile cannot be parallelized well;
best results are achieved with a few fast CPUs, e.g. on a cluster login node.
See :ref:`our note on re-compiling <usage-params-rationale>` for details.

Which version of PIConGPU should I use?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

For production runs, use the newest
`stable release <https://github.com/ComputationalRadiationPhysics/picongpu/releases>`_.
New releases can introduce syntax changes for existing simulations, which are described in the
`changelog <https://github.com/ComputationalRadiationPhysics/picongpu/blob/dev/CHANGELOG.md>`_;
read it before updating.

If you rely on an older version and need an urgent bug fix, open an issue and describe the problem.
We may be able to release a new revision of a previous version that only fixes a small issue
(*backporting*).
New features are usually not backported.

If you plan to contribute code, start from the ``dev`` branch and read
:doc:`developer contribution guide <../dev/CONTRIBUTING>`.
The ``dev`` branch changes quickly and is not recommended for production runs.
