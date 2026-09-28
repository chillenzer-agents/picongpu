cwlVersion: v1.2
class: CommandLineTool
label: "Run PIConGPU chunk"
doc: |
  Perform a single stepwise chunk [start_step, end_step) of a PIConGPU
  simulation, resuming from the previous chunk's checkpoint.

  This is the reusable per-chunk step used by `Simulation.step()`. It re-uses
  the *once-built* binary (`bin_directory`, produced once by `build.cwl`) and
  the *additive* chunk config (`cfg_file`, written by the Runner as
  `N-step-<start>-<end>.cfg`). The top-level `workflow.cwl` is not re-invoked
  per chunk (that would re-run `build` and the single-shot submission).

  Every chunk writes into the shared `dst_path` (constant `TBG_dstPath`), so the
  `simOutput` accumulates next to earlier chunks' outputs with no per-chunk
  post-merge. `build.cwl` runs exactly once for the whole simulation; this step
  is invoked once per chunk with a different `cfg_file`.

  The directory inputs are passed as absolute *string* paths (not staged
  Directories) on purpose: a stepwise chunk must write into the real, shared
  run directory in place, rather than a cwltool-isolated staging copy.

requirements:
  InitialWorkDirRequirement:
    listing:
      - entryname: run_chunk.sh
        entry: $(inputs.script)
  EnvVarRequirement:
    envDef:
      - envName: PICONGPU_RUNNING_AS_CWL
        envValue: "1"

baseCommand: ./run_chunk.sh

inputs:
  submit_system:
    type: string?
    inputBinding:
      position: 1
    label: "Submit command"
    doc: "Submit command (qsub, sbatch, ...). Default 'bash'."
    default: "bash"
  cfg_file:
    type: string
    inputBinding:
      position: 2
    label: "Chunk configuration file"
    doc: "Path to the additive chunk config, e.g. etc/picongpu/N-step-0-2.cfg"
  project_path:
    type: string
    inputBinding:
      position: 3
    label: "Setup path"
    doc: "Directory with the simulation setup to run (contains etc/ and the chunk config)"
  bin_directory:
    type: string
    inputBinding:
      position: 4
    label: "Compiled executables"
    doc: "Path to the once-built PIConGPU binaries (from build.cwl); reused, never rebuilt per chunk"
  dst_path:
    type: string
    inputBinding:
      position: 5
    label: "Shared run directory"
    doc: "Destination directory shared by all chunks (constant TBG_dstPath); simOutput accumulates here"
  template_file:
    type: string?
    inputBinding:
      position: 6
    label: "TBG template file"
    doc: "TBG template to create the batch file from (the preset's mpiexec/mpirun template)."
    default: ""
  start_step:
    type: int
    label: "First step of the chunk (inclusive)"
    doc: "Restart step; used to name the chunk config and resume. Informational for this step."
  end_step:
    type: int
    label: "Last step of the chunk (exclusive)"
    doc: "Absolute stop step, rendered as TBG_steps in the chunk config. Informational for this step."
  script:
    type: File
    label: "Chunk-run script"
    doc: "Shell script that prepares (tbg) and runs a single chunk in the foreground"

outputs: {}
