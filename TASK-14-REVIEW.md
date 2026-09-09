# Review - Task 14: MCP server for LLM-driven remote HPC simulations (design draft)

- **Branch:** `task-14-mcp-server-design` (tip `81c4b9e48`, base `dev` / `b4e4ca5b2`)
- **Reviewed:** 2026-08-31 · **Scope:** 1 commit, 1 file, +740/-0 (`TASK-14-MCP-DESIGN.md`, doc-only)
- **Verdict:** REQUEST CHANGES
  (Well-grounded, mostly accurate design with four major flaws in the concrete specs - a broken parser regex, a submit flow that crashes as written, a control command that does not do what it says, and a cluster-side shell-injection vector.)

## 1. Summary

The branch adds a single 740-line design document for an MCP server + Matrix-based RCP layer that lets a local LLM agent submit/manage/analyse PIConGPU runs on a SLURM cluster, with PoC scope "Hello World on the cluster". Overall quality is good: I re-verified ~30 of the doc's `file:line` anchors against the tree and all are accurate; the external claims (mcp 2.1.1 + `MCPServer`, matrix-nio 0.26.0 with all seven cited method line numbers, the live Helmholtz well-known discovery) were re-checked and hold; the "pre-commit green" claim was re-verified (all applicable hooks pass). The four most important issues:

1. The M2 progress-line regex (§2.3) fails to match *any* real progress line with fewer than 8 digits of steps (verified) - it cannot parse typical runs.
2. The `submit_simulation` flow (§4.1) is not implementable as written: `write_input_file()` + `picongpu_run()` on one `Simulation` raises the double-`generate()` assertion (reproduced), "obtaining `picmi.Simulation` from a controlled subprocess" is impossible, and the LLM-code-execution surface is missing from §6.
3. `cancel(mode="hard")` (§2.4) is a graceful stop under the standard templates, because `handleSlurmSignals.sh` traps SIGTERM and forwards USR2 - the design's own §7.2 cites that mapping but §2.4 ignores it.
4. The `hello {message}` RCP command (§2.4) interpolates the LLM-supplied message into `sbatch --wrap="echo '<message>'"` - shell injection on cluster nodes; the M1 spec contradicts the tool surface by hard-coding the string.

## 2. Findings

### 2.1 Critical

None found.

### 2.2 Major

**M1**
- **`TASK-14-MCP-DESIGN.md:376-385`** - the `submit_simulation` mechanism is not implementable as written. The doc says the server "executes it [the PICMI script] in a controlled subprocess, obtains the `picmi.Simulation`, then drives `write_input_file`/`generate` [picmi/simulation.py:339-350] and, if `run_async`, `picongpu_run` [picmi/simulation.py:494-501] in a background task".
  - *Evidence (reproduced):* `picongpu_run()` internally calls `runner.generate()` again (`picmi/simulation.py:500`), and `generate()` asserts the setup dir does not exist (`pypicongpu/runner.py:408-411`). Probe with a valid PICMI sim (8×8×4 grid, venv `task-14`):

    ```
    == A) write_input_file(setupA)
       setupA exists: True
    == B) then picongpu_run()
       picongpu_run: ASSERTION FAILED -> setup directory must not exist before
       generation -- did you call generate() already?
    ```

    So the literal flow (drive `write_input_file`, then "if `run_async`, `picongpu_run`") crashes. Separately, a live `picmi.Simulation` object cannot be "obtained" from a subprocess; if instead the server execs the LLM-supplied script (path **or inline code**, §4.1:364) in its own process, that is arbitrary Python execution inside the MCP server - the single largest blast-radius surface in this design - and §6 (security) does not mention it at all.
  - *Suggested fix:* Pick one of two coherent flows and state it: (a) a subprocess (separate Python process, ideally a fresh interpreter) runs the PICMI script **plus** a small wrapper that itself calls `sim.picongpu_run(setup_dir=..., run_dir=..., **flags)` (generate+run in one call - never `write_input_file` before `picongpu_run`) and prints a JSON result (`sim_id`, `setup_dir`, `job_id`); the MCP server never imports/execs the script and only handles the JSON. Or (b) explicit in-process exec with a sandbox (restricted subprocess is still preferable) - and in either case add a §6 subsection: "PICMI script = arbitrary code on the submission node; confined to the `submit_simulation` confirm tier, executed in a disposable subprocess, no credentials in its environment".

**M2**
- **`TASK-14-MCP-DESIGN.md:224-226`** - the progress-line regex `^\s{0,3}(\d{1,3}) % = (\d+) \| time elapsed: .+ \| avg time per step:` does not match real output for any step count below 10,000,000. `SimulationHelper.cpp:104` prints `std::setw(8) << currentStep` (right-aligned, space-padded), so for steps < 10^7 there are leading spaces between `= ` and the digits, which `(\d+)` cannot consume. The doc's own example line (`:218`, `  5 % =      500 | ...`) shows the padding - the regex contradicts the doc's own example.
  - *Evidence (reproduced):* tested the doc's regex against lines generated in the exact C++ format (`setw(3)` percent, `setw(8)` step):

    ```
    pct=  5 step=     500 line='  5 % =      500 | time elapsed: ...' match=False
    pct= 50 step=    5000 line=' 50 % =     5000 | ...'                match=False
    pct=100 step=   10000 line='100 % =    10000 | ...'                match=False
    pct=  1 step=       9 line='  1 % =        9 | ...'                match=False
    pct= 25 step=12345678 line=' 25 % = 12345678 | ...'                match=True   (only >=8-digit steps)
    ```

    i.e. every realistic run (thousands-millions of steps) fails. Additionally, the regex captures only `percent` and `step` while the doc claims the payload is `{step, percent, walltime, avg_per_step, eta}` - the remaining fields have no capture groups.
  - *Suggested fix:* `^\s*(\d{1,3}) % = +(\d+) \| time elapsed: +(\S+) \| avg time per step: +(\S+)` (and derive `eta` = `avg_per_step × steps_remaining` on the simclient side). Also fix the example line: `std::setw(25)` on an 11-char interval yields 14 leading spaces after `time elapsed:`, not 9.

**M3**
- **`TASK-14-MCP-DESIGN.md:251`** - `cancel` "hard: `scancel <jobid>` (SIGTERM -> stop [signal.cpp:66])" does not do what it says under the standard templates. The hemera `gpu.tpl` the doc itself cites runs the app through the signal wrapper: `source $TBG_dstPath/tbg/handleSlurmSignals.sh mpiexec ...` (`etc/picongpu/hemera-hzdr/gpu.tpl:112`), and that wrapper traps SIGTERM and forwards **USR2** to the app (`handleSlurmSignals.sh:46`, mapping comment `:29`). So a plain `scancel <jobid>` on a standard-template job delivers USR2 -> "finish current loop and exit normally" (`signals.rst:23`) - i.e. **identical to the "graceful" mode**. `signal.cpp:66` (the app's own SIGTERM handler) is unreachable because the app is always wrapped. The doc is internally inconsistent: §7.2 (`:561`) cites `handleSlurmSignals.sh:28-34,46-50` as the "SLURM mapping" while §2.4 ignores it.
  - *Evidence:* code-path argument: `scancel` (no `--signal`) -> SIGTERM to the batch script -> trap at `handleSlurmSignals.sh:46` -> `fireSignal SIGUSR2` -> app receives USR2 -> `setStopSimulation` (`signal.cpp:64`) -> clean stop at step boundary. The only untrappable "hard" kill is `scancel --signal=KILL <jobid>` (SIGKILL), which the doc never mentions - and whose blast radius (no clean shutdown, in-flight openPMD writes left incomplete, job recorded as FAILED/CANCELLED) is exactly what a destructive-tier tool must document.
  - *Suggested fix:* Rewrite the `cancel` row: `graceful` = `scancel --signal=USR2 --batch <jobid>` (works today, step-boundary stop); `hard` = `scancel --signal=KILL <jobid>` with an explicit "no clean shutdown / possible torn output" warning; note that plain `scancel` == graceful under `handleSlurmSignals.sh`-wrapped templates (all `etc/picongpu/*/*.tpl` that source it - currently `gpu.tpl:112`, `defq.tpl:104`, `fwkt_v100.tpl:114`).

**M4**
- **`TASK-14-MCP-DESIGN.md:248`** - the RCP `hello {message}` command embeds the LLM-supplied message into a shell command that executes on the cluster: `sbatch --wrap="echo '<message>' <sim_id>"`. `message` is an LLM tool input (§4.1:363 `hello | {message?: str}`), so a message containing `'`, `$(...)` or backticks breaks out of the single quotes -> arbitrary shell execution on a compute node under the user's account. §6.4's HMAC only prevents *forgery by room members*; it says nothing about payload sanitization, and §6.2's human-confirmation tier does not fix it (the human approves "send hello", not the constructed `sbatch` line). The M1 spec (§8.1:584) sidesteps this by hard-coding `echo 'Hello World from <sim_id>'` - which contradicts §4.1's `message?` input (as specified, M1 silently ignores the parameter).
  - *Evidence:* direct code-path: `--wrap` content is executed by the batch shell on the compute node; single-quoting is not shell-safe for arbitrary user strings.
  - *Suggested fix:* Never interpolate tool inputs into shell strings. E.g. the simclient writes the message to a file on the shared FS and runs `sbatch --wrap="cat '<path>'"` (path is server-generated, safe charset), or restrict `message` to `[A-Za-z0-9 _.,-]{1,80}` server-side *and* keep the fixed M1 string; reconcile §4.1/§8.1 by stating explicitly that M1 ignores `message` (or implements it safely). Add a §6.4 rule: "command payloads are never concatenated into shell commands; safe-charsets or out-of-band file transfer only".

### 2.3 Minor

**m1**
- **`TASK-14-MCP-DESIGN.md:381-385`** - the "SLURM for starters" premise is not the workflow's default. `run_submit_system` in `workflow.cwl:62-66` defaults to `"bash"`, which makes `submit.sh` execute the rendered batch script **locally on the submission node** (a bash PID in `submission_information.txt`, no SLURM job at all). The doc never states this default; an M2 implementer who follows the doc literally would get a `simulation.submitted` event with a non-SLURM "job id" and silently failing `scontrol` polling. *Fix:* state in §1.4/§4.1/§8.1(M2) that `submit_simulation` must pass `run_submit_system: sbatch` (or the equivalent `overwrite_vars`), and define behavior for non-SLURM submit systems (reject, or emit a distinct `simulation.submitted_locally` event).

**m2**
- **`TASK-14-MCP-DESIGN.md:543-548`** - the pre-hook fallback ("derives step boundaries by watching the workflow's on-disk effects (`submission_information.txt` appearing ...)") cannot produce per-step boundaries. `submission_information.txt` is only visible in the run directory as an *output of the last step* (`organize_output`, `steps/organize_output.cwl:48-51`); inside the submit step it exists only in cwltool's step workdir (an undocumented tmp dir). So the described watcher can only emit `workflow.started/finished`, `simulation.submitted`, `results.ready` - not the `workflow.step_started/step_finished` that M2's event stream is built on. *Fix:* state that the interim wrapper yields only workflow-level events, and that M2 step events require the hook or option (i) (sequential step invocation) as the doc itself recommends.

**m3**
- **`TASK-14-MCP-DESIGN.md:171-178`** - `seq` is "a per-simulation monotonic counter", but there are **two senders** per sim (simclient + MCP server) and dedup/gap-detection is keyed on `(sim, seq, type)`. If both parties run independent counters, the merged stream has spurious gaps and cross-sender `(sim, seq, type)` collisions. *Fix:* define `seq` as per `(sim, sender_role)` and dedup on `(sim, sender_role, seq, type)` (the envelope already carries `sender_role`).

**m4**
- **`TASK-14-MCP-DESIGN.md:58-61`** - alternatives to Matrix as the control channel are not weighed. Both RCP endpoints (MCP server and simclient) run on the same local machine (the doc's own diagram, §1.2), so the PoC pays the full Matrix operational cost (bot/personal account provisioning, MSC2965 login flow, token lifecycle, homeserver dependency) while federation - a key Matrix benefit - is unused. The task prescribes Matrix for the overall architecture, which is fine, but the doc should argue (a) why M1 specifically needs Matrix instead of a direct local channel or a plain MCP tool that shells out `sbatch` (marginal PoC value: human-readable audit trail, multi-device access), or (b) propose an M1.0 direct-echo variant to de-risk. One short "alternatives considered" paragraph is sufficient.

### 2.4 Nits

**n1**
- **`TASK-14-MCP-DESIGN.md:354-356`** - "`mcp` package, `MCPServer` + `@mcp.tool()`": in the pinned mcp 2.1.1 the decorator is `@server.tool()` on the `MCPServer` instance (`mcp/server/mcpserver/server.py:654`); there is no module-level `mcp.tool()`. `MCPServer` itself (server.py:153), stdio transport, and `ToolAnnotations` are correct.

**n2**
- **`TASK-14-MCP-DESIGN.md:203`** - `simulation.checkpoint_written` ("checkpoint file set complete") is anchored to `TaskSignal.hpp:133`, which is `addCheckpoint()` - i.e. *registration* of the checkpoint, not completion. The real completion signal is the openPMD dir watch (also listed) / `Checkpointing.hpp:148` (`dump`). Re-anchor or rename the event to `checkpoint_registered`.

**n3**
- **`TASK-14-MCP-DESIGN.md:218`** - the example progress line shows 9 spaces after `time elapsed:`; `std::setw(25)` on an 11-character interval yields 14. Cosmetic, but fix together with M2 so the example and the regex agree with the code.

**n4**
- **`TASK-14-MCP-DESIGN.md:583-590`** - M1's `cluster_output` requires the simclient to wait for the trivial job to finish and read its output file, but no wait/timeout is specified. State: poll `scontrol show job <id>` until DONE/FAILED (e.g. 5 s interval, 60 s timeout), then read the `--output` file; on timeout, ack with `job_id` and `cluster_output: null`.

**n5**
- **`TASK-14-MCP-DESIGN.md:182-187`** - a 6-hex (24-bit) `sim_id` has a meaningful birthday-collision probability at a few thousand registered sims, and `sim_id` is used in the room alias `#sim-<sim_id>`. Use 8+ hex chars (or verify uniqueness against the local registry before reuse).

## 3. Requirement traceability

| # | Requirement (from task file) | Status | Where / note |
|---|------------------------------|--------|--------------|
| 1 | Architecture overview: diagram + component list, 4 CWL steps, `run()` hook point, Matrix as transport | met | §1; all anchors verified (`runner.py:450-465`, `workflow.cwl:107-149`, step files) |
| 2 | RCP spec: message format, event taxonomy, command set + implementation locations, pause flagged open | partial | Envelope/acks/auth good (§2.1-2.5); but M2 (regex), M3 (cancel), m3 (seq) |
| 3 | Identity & rooms: account strategies (a assessed, b recommended), room strategies with trade-offs | met | §3; live-verified against Helmholtz well-known (2026-08-31) |
| 4 | MCP tool surface: concrete tool list with inputs/outputs + filtering/condensing | partial | §4.1/4.2; `submit_simulation` flow not implementable as written (M1); `@mcp.tool()` (n1) |
| 5 | Data channel: Jupyter/ADIOS/ParaView evaluated, primary + fallback + exposing tool | met | §5; openPMD/ADIOS2 grounding verified (`openPMD.rst:48-59`, `postprocessing/python.rst:65-71`) |
| 6 | Security & trust: credentials out of LLM context, authz tiers, room ACL, integrity | partial | §6 solid on its stated surfaces; missing: LLM code-execution surface (M1) and payload->shell injection (M4) |
| 7 | Integration points: concrete file:line hooks + observer-hook design | met | §7; ~30 anchors re-verified, all accurate; interim-fallback description wrong (m2) |
| 8 | Milestones M0-M4 + open questions (bot account, pause, concurrency, PoC credentials) | met | §8; all four coordinator open questions covered; M1 buildable (n4, M4 caveats) |
| S1 | Separate repo decision + minimal observer hook (not implemented) | met | §7.1 hook sketch, explicitly not implemented |
| S2 | Doc kept in `/workspace` on a separate branch | met | branch `task-14-mcp-server-design`, single doc commit |
| S3 | Server-agnostic, default Helmholtz | met | §1.1/§3.1/§7; well-known claims verified live |
| S4 | SLURM for starters | partial | assumed throughout, but the workflow default is `bash`/local (m1) |
| S5 | Minimal PoC: "Hello World on the cluster" | met (caveats) | §8.1 M1 has components + acceptance criteria; message handling inconsistent (M4), wait unspecified (n4) |

## 4. Claim verification (author artifact)

| Claim (from TASK-14-MCP-DESIGN.md / author) | Re-verified? | Result / delta |
|---|---|---|
| "doc-only" branch | yes | `git diff --stat dev...branch`: 1 file, +740/-0 - confirmed |
| "pre-commit green" | yes | re-ran `pre-commit 4.3.0` (scratch venv `/tmp/opencode/review-14/venv-pc`) on the file: all applicable hooks Passed (ascii, tabs, CRLF, EOF, shebang, no-conflict); no code in diff, so no Python test-gate impact vs baseline |
| "~30 file:line anchors" (Appendix B: every claim traceable) | yes | re-checked `runner.py` (239, 332-353, 355-393, 395-398, 400-448, 450-465), `workflow.cwl` (103-149, 18-81), `submit.cwl:43-48`, `organize_output.sh:13-15`, `N.cfg.mustache:50-66,146-191`, `gpu.tpl:24-44,40,43,112`, `profile.example:61`, `signal.cpp:56-68`, `TaskSignal.hpp:49,130,139`, `handleSlurmSignals.sh:28-34,46-50`, `signals.rst:10,22-25,33-35,46`, `SimulationHelper.cpp:58-63,100-106,152-157,186-207,229-234,245-248,268`, `checkpoint.py:18,29-33,64-65`, `simulation.py:146,339-350,494-501,503-511`, `_rc_params.py:462-476`, `Checkpointing.hpp:142-148`, `openPMD.rst:48-59`, `postprocessing/python.rst:65-71` - **all accurate**. "Traceable" != "correct", though: 3 grounded claims are wrong (M2, M3, M1) |
| "Timestep progress source (verified against the code that prints it)" (§2.3) | partial | format/line anchors verified; the derived regex is wrong (M2) - the "verified" claim does not hold for the regex |
| mcp SDK: `mcp` 2.1.1 on PyPI (2026-08-25), `MCPServer` + `@mcp.tool()` [A2] | yes | 2.1.1 exists, uploaded 2026-08-25 ok; `class MCPServer` exists (`mcp/server/mcpserver/server.py:153`) ok; decorator is `@server.tool()` (n1) |
| matrix-nio 0.26.0, `login`:1100, `register`:1026, `room_send`:1724, `room_create`:2406, `room_invite`:2577, `join`:2515 [A3] | yes | downloaded the wheel; **all seven line numbers exact** |
| Helmholtz homeserver: `synapse.matrix.helmholtz.cloud`, MSC2965 -> `auth.matrix.helmholtz.cloud`, Ketesa-managed bots (draupnir, hookshot, `_github_*`, `_gitlab_*`, `_jira_*`, `_webhooks_*`) [A9] | yes | live `.well-known/matrix/client` fetched 2026-08-31: matches exactly |
| `signals.rst:25` (TERM->USR1) vs `signal.cpp:66` (TERM->stop) - code treated as truth | yes | discrepancy is real; design §8.2.5 handles it correctly (code = truth); §2.4 cancel row is consistent with the code *but* misses the wrapper mapping (M3) |
| Pause: no existing pause mechanism; handled set HUP/INT/QUIT/ABRT/TERM/USR1/USR2/ALRM; SIGCONT->USR1 in wrapper | yes | `signal.cpp:59-66` and `handleSlurmSignals.sh:46-50` confirm exactly this |
| Wall-time pre-signal `--signal=B:SIGALRM@240` in `gpu.tpl:40` | yes | verified |

## 5. Design discussion

**Matrix as the control channel.** The task prescribes Matrix, and the doc's "Why Matrix" paragraph (§1.1) is directionally right (Helmholtz standard, first-class bots, private rooms, federation, maintained Python clients). The trade-off it doesn't make explicit: in this architecture *both* RCP endpoints live on the same submission machine (§1.2 diagram), so for the PoC Matrix is a detour - it adds account provisioning, an OIDC-login bootstrap, token lifecycle, and an external dependency, while the benefits that actually matter (human-readable room as audit trail, multi-device access, federation to other Helmholtz homeservers) are future-state. A direct channel (plain HTTP/WebSocket between `picongpu-mcp` and `simclient`, or even a local socket) would give the same RCP semantics with zero external infra, and a bare MCP tool shelling out `sbatch` would achieve the M1 acceptance criterion in an afternoon. The defensible position - Matrix buys the audit trail and the path to a federated, multi-user control plane that a bespoke channel would have to re-build - should be written down in one paragraph, and M1 should either justify its Matrix cost or be offered as a direct-echo variant (m4). Note the doc *does* use SLURM-native mechanisms where they are the right tool (`scontrol` polling for job state, `scancel --signal` for control), which is the correct division of labor and worth calling out as intentional.

**Threat model.** §6.4's HMAC ("lets room members (humans) read everything while only the two RCP parties can forge messages") is a coherent, appropriately-scoped threat model for machine-to-machine rooms on a shared homeserver, and the default of unencrypted private rooms + ACLs + HMAC over E2EE (matrix-nio's lack of cross-signing makes bot-device verification manual) is the right call. The gap is scope, not mechanism: the model covers the *room* boundary but not the two local surfaces where the LLM actually has power - executing PICMI code (M1) and composing shell strings for cluster commands (M4). Both are one-paragraph fixes.

**seq/dedup.** With two senders per room, the per-simulation counter needs to be per-sender (m3). Matrix sync itself handles reconnect/replay reasonably (the client resyncs from `next_batch`; room history is readable on demand), so the design's at-least-once + dedup stance is fine; it would be worth one sentence stating that both clients backfill the timeline on (re)connect rather than relying on live delivery only.

**Shared-filesystem dependency.** Correctly flagged as a risk (§8.3). If a cluster does not expose job `stdout`/`simOutput` to the submission node, the fallback is SLURM-native: `sacct`/`scontrol show job` for state and `--open-mode=append` + mail for output. One sentence in §2.3/§5 would close the loop.

**Phasing.** M1->M4 is coherent and correctly ordered (reporting before control, `query_status`/`checkpoint`/`cancel` before the open `pause`). The `pause` analysis (§2.4) is accurate and honest about needing a core feature; M3's "requires sims configured with the checkpoint plugin" caveat is correct (with the plugin disabled, USR1 just prints "Checkpointing is disabled, no checkpoint will be created." - `Checkpointing.hpp:408-410`, which a simclient could in fact detect as a clean rejection).

## 6. Prioritized next steps

1. Fix the §2.3 progress regex (M2) - add the padding-aware pattern, the missing capture groups, and correct the example line's spacing (n3).
2. Rewrite the `submit_simulation` flow (M1): subprocess owns generate+run (single `picongpu_run()` call, or script-side `write_input_file`+`run()`), server consumes JSON only; add the §6 subsection on LLM code execution; state the `run_submit_system` default-`bash` gotcha and the required `sbatch` value (m1).
3. Fix the `cancel` semantics (M3): graceful = USR2, hard = `--signal=KILL` with torn-output warning; note plain `scancel` == graceful under the `handleSlurmSignals.sh`-wrapped templates.
4. De-inject `hello` (M4): no tool-input interpolation into `sbatch --wrap`; reconcile §4.1's `message?` with §8.1's hard-coded string; add the "no payload->shell concatenation" rule to §6.4; specify the M1 job-wait/timeout for `cluster_output` (n4).
5. Specify `seq` per `(sim, sender_role)` with matching dedup key (m3); fix the `checkpoint_written` anchor (n2); `@server.tool()` (n1); `sim_id` length (n5).
6. Add the one-paragraph "alternatives considered / why Matrix for the PoC" (m4) and correct the §7.1 interim-fallback description (m2).
7. Once fixed, the doc is close to sign-off quality; then proceed to M1 implementation per §8.1.

## FYI (inherited from base, not scored here)

- `docs/source/expert/signals.rst:25` genuinely says "TERM (15): Trigger USR1" while `signal.cpp:66` maps SIGTERM to stop - pre-existing doc bug, correctly flagged by the design (§8.2.5); worth a companion PR.
- `workflow.cwl:44-45` - `run_etc_directory` reuses the label/doc "Compile-time parameter header directory" from `build_include_directory` (copy-paste); inherited.
- `handleSlurmSignals.sh:42` logs `send signal $1` (only the first signal in the ALRM pair) to stderr - inherited cosmetic.
