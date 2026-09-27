cwlVersion: v1.2
class: CommandLineTool
label: "Install PIConGPU dependencies (DRAFT)"
doc: |
  DRAFT - not wired into workflow.cwl yet (see TASK-12-FINDINGS.md).

  Installs the compiled C++ dependencies of PIConGPU (PNGwriter, FFTW3,
  openPMD-api, ...) into a shared, toolchain-keyed cache by running
  picongpu-deps.sh (etc/picongpu/dependencies/). The install is
  idempotent: a warm cache makes this step a no-op.

  The install script is staged into the work directory and executed with
  `bash`, so the input File does not need the executable bit.

  The resulting prefix is handed to the build step either by sourcing
  <prefix>/current.env in the generated build.sh (what the runner does
  today when [dependencies].enabled = true) or, in a future iteration,
  by exporting CMAKE_PREFIX_PATH / *_ROOT here via an
  EnvironmentVariableRequirement.

requirements:
  InitialWorkDirRequirement:
    listing:
      - entryname: install.sh
        entry: $(inputs.script)
  EnvVarRequirement:
    envDef:
      - envName: PICONGPU_RUNNING_AS_CWL
        envValue: "1"

baseCommand: bash

inputs:
  script:
    type: File
    label: "Install script"
    doc: "Shell script that runs picongpu-deps.sh with the configured DEPS_* variables"
    inputBinding:
      position: 1
  jobs:
    type: int?
    label: "Number of parallel jobs"
    doc: "Forwarded to picongpu-deps.sh as --jobs=N"
    default: 4
    inputBinding:
      prefix: "--jobs="
      position: 2

outputs:
  deps_directory:
    type: Directory
    outputBinding:
      glob: "deps"
    label: "Installed dependency prefixes"
    doc: "Only non-empty when the install script sets DEPS_INSTALL_ROOT=./deps (inside the work directory); the default install root lives outside the work directory, in which case this output is empty."
