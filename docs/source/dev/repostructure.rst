.. _development-repostructure:

Repository Structure
====================

.. sectionauthor:: Axel Huebl

Branches
--------

* ``dev``: the development branch where all features start from and are merged to
* ``release-X.Y.Z``: release candiate for version ``X.Y.Z`` with an upcoming release, receives updates for bug fixes and documentation such as change logs but usually no new features

Directory Structure
-------------------

* ``include/``

  * C++ header *and* source files
  * set ``-I`` here
  * prefixed with project name

* ``lib/``

    * pre-compiled libraries
    * ``python/``

      * python modules
      * install piconpgu package as in :ref:`usage-python-utils` 
      * ``extra/``

        * modules, e.g. for RT interfaces, pre* & post-processing

      * ``picmi/``

        * user-facing python interface

      * ``pypicongpu/``

        * internal interface for ``.param`` & ``.cfg``-file generation
        * used by PICMI implementation

* ``etc/``

  * (runtime) configuration files
  * ``picongpu/``

    * ``tbg`` templates (as long as PIConGPU specific, later on to ``share/tbg/``)
    * network configurations (e.g. infiniband)

* ``share/``

  * examples, documentation
  * ``picongpu/``

    * ``benchmarks/``: setups used for benchmarking
    * ``completions/``: bash completions
    * ``examples/``: each with same structure as ``/``
    * ``pypicongpu/``: required files for code generation

      * ``schema/``: code generation JSON schemas
      * ``template/``: base template for code generation

    * ``tests/``: self-validating examples for different scenarios
    * ``unit/``: small (hopefully expanding) selection of unit tests

* ``bin/``

  * core tools for the "PIConGPU framework"
  * set ``PATH`` here

* ``docs/``

  * currently for the documentation files
  * might move, e.g. to ``lib/picongpu/docs/`` and its build artifacts to ``share/{doc,man}/``, 

File Endings
------------

PIConGPU and pmacc use the following file types.
Endings marked as *special* are not standard C++ or configuration file types and are interpreted by our
build and tooling.

======================== ================== ===============================================================
ending                   usage              description
======================== ================== ===============================================================
``.cpp``                 source code        C++ source
``.hpp``                 source code        C++ header
``.def``                 source code        C++ header with definitions only (special)
``.tpp``                 source code        C++ template implementation
``.kernel``              source code        kernel implementation (special)
``.param``               configuration      user compile-time configuration (special)
``.unitless``            configuration      unit and trait definitions for attributes (special)
``.cfg``                 configuration      TBG run-time configuration
``.tpl``                 configuration      TBG batch-system template
``.toml``                configuration      runtime configuration, e.g. for the openPMD plugin
``.py``                  source code        Python
``.sh``                  source code        shell script
``.cwl``                 workflow           Common Workflow Language description
``.mustache``            template           code-generation template for pypicongpu (special)
``.md``                  documentation      Markdown
``.rst``                 documentation      reStructuredText
``.txt``                 build system       CMake build configuration
``.json``                configuration      schema or input for code generation
======================== ================== ===============================================================
