# TASK-14: Response to review (TASK-14-REVIEW.md)

Verdict received: REQUEST CHANGES (0 critical / 4 major / 4 minor / 5
nits). Every finding was re-verified against the codebase at commit
`b4e4ca5b2` before amending the design document. No finding is rejected
outright; n3 is accepted in substance, with a correction to the
review's specific spacing figure (see below). All changes are new
commits on top of the review commit `b77071d2e`; no history was
rewritten and no file outside the worktree was modified.

## Per-finding disposition

| Finding | Disposition | Commit  | What changed |
|---------|-------------|---------|--------------|
| M1      | accepted - fixed | `57cd1c18f` | `submit_simulation` rewritten: a checked-in wrapper in a disposable subprocess runs the PICMI script and calls `sim.picongpu_run(setup_dir, run_dir, **flags)` exactly once (generate+run; never `write_input_file` first, which double-`generate()`s and hits the assert at `runner.py:408-411`); the server consumes only the wrapper's JSON. Added section 6.5 (LLM code execution). |
| M2      | accepted - fixed | `838eff599` | section 2.3 regex made padding-aware (`setw(8)`) and given real capture groups for walltime/avg_per_step; example line corrected to the actual `TimeInterval::printTime` format. Verified by emulating `SimulationHelper.cpp:100-106` + `TimeInterval.hpp:72-102` for 1-9 digit steps and msec-to-hour timescales. |
| M3      | accepted - fixed | `3511ab1ec` | `cancel` row corrected: graceful = `scancel --signal=USR2 --batch`, hard = `scancel --signal=KILL` with a torn-output warning; added a "Cancel semantics" note that plain `scancel` == graceful under `handleSlurmSignals.sh`-wrapped templates. |
| M4      | accepted - fixed | `e3ffb6a08` | `hello` redesigned: `message` is written to an absolute server-generated path (safe charset) and the job runs `sbatch --wrap="cat '<path>'"`; the message never reaches a shell. Added the "no payload-to-shell concatenation" rule to 6.4. |
| m1      | accepted - fixed | `57cd1c18f` | Stated in 1.4/4.1/8.1(M2) that `run_submit_system` defaults to `"bash"` (local, no SLURM job) [workflow.cwl:62-66; runner.py:141-145] and a real submission must pass `"sbatch"`; non-SLURM submit systems are rejected or emit `simulation.submitted_locally`. |
| m2      | accepted - fixed | `ef4df0d3f` | section 7.1 interim-fallback description corrected: the external wrapper yields only workflow-level events (it cannot delimit steps, since `submission_information.txt` is visible in the run dir only as the last step's output); M2 step events require the hook or option (i). |
| m3      | accepted - fixed | `20c730b7e` | `seq` is now per `(sim, sender_role)`; dedup key is `(sim, sender_role, seq, type)`; both clients backfill the timeline on (re)connect. |
| m4      | accepted - fixed | `ef4df0d3f` | Added an "Alternatives considered" paragraph in 1.1 weighing a direct local channel / bare `sbatch` tool against Matrix for the PoC, with an optional direct-echo M1 variant. |
| n1      | accepted - fixed | `20c730b7e` | In mcp 2.1.1 the decorator is the `server.tool()` instance method (`mcp/server/mcpserver/server.py:654`), not a module-level `mcp.tool()`; `MCPServer` is at `server.py:153`. Fixed section 4 and Appendix A2. |
| n2      | accepted - fixed | `20c730b7e` | `simulation.checkpoint_written` re-anchored to the openPMD dir watch / `Checkpointing.hpp:148` (`dump`); `TaskSignal.hpp:133` (`addCheckpoint`) noted as registration only. |
| n3      | accepted - fixed (with correction) | `838eff599` | Example line corrected to the actual format. See the pushback note below on the specific spacing figure. |
| n4      | accepted - fixed | `e3ffb6a08` | M1 wait specified: poll `scontrol show job <id>` until DONE/FAILED (5 s interval, 60 s timeout), read the `--output` file; on timeout ack with `job_id` and `cluster_output: null`. |
| n5      | accepted - fixed | `20c730b7e` | `sim_id` is now 8 hex chars (32 bits) instead of 6 (24 bits), plus a uniqueness check against the local registry before reuse. |

## Pushback / corrections to the review

### n3 - the elapsed-time field is not `0:01:02:345`

The review's n3 (and the M2 worked examples) treat the elapsed-time
field as an 11-character string of the form `0:01:02:345` and derive
"14 leading spaces" from `setw(25)` on that. PIConGPU does not print
that form: `pmacc::TimeInterval::printTime`
(`include/pmacc/simulationControl/TimeInterval.hpp:72-102`) emits
`Hh Mmin Ssec mmm msec` with zero-valued components omitted (e.g.
`345msec`, `2sec 345msec`, `1min 2sec 345msec`,
`25h 1min 1sec 0msec`). The substantive point of n3 (the example
spacing was wrong) is correct and is fixed, but the specific
11-char/14-space figure does not apply because the interval is not
`0:01:02:345`. The example line and the regex were corrected to the
actual format, which subsumes the spacing fix.

Two verification notes that go beyond the review's evidence:

- The review's *suggested* regex
  (`... \| time elapsed: +(\S+) \| avg time per step: +(\S+)`) is
  itself insufficient: `(\S+)` captures only the first
  whitespace-delimited token of a multi-component time (e.g. `1min`
  from `1min 2sec 345msec`), so it fails to match most real lines. The
  adopted regex captures the whole time token up to the next ` | `
  delimiter.
- The adopted regex was verified against an exact emulation of
  `SimulationHelper.cpp:100-106` + `TimeInterval::printTime` for step
  counts of 1-9 digits and msec-to-hour timescales: all representative
  lines match and the captured fields equal the source values, whereas
  the previous document's `= (\d+)` matched only step counts of 8
  digits or more.

## Gate result

- `pre-commit run --files TASK-14-MCP-DESIGN.md TASK-14-RESPONSE.md`:
  all applicable hooks pass (require-ascii / Check file encoding,
  No-tabs, CRLF, trailing whitespace, end-of-file, etc.).
- `pre-commit run --all-files`: every hook passes except
  `require-ascii` (Check file encoding), which fails only on the
  pre-existing `TASK-14-REVIEW.md` (committed by the review team at
  `b77071d2e` and explicitly out of scope to modify here). No file
  changed by this rework fails any hook; the require-ascii failure is
  inherited from the review commit, not introduced by it.
- No Python code was changed (the rework is doc-only: 2 Markdown
  files), so the `lib/python/test/picongpu quick/` pytest gate is not
  applicable to this branch.
