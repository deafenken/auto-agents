Reading additional input from stdin...
OpenAI Codex v0.130.0
--------
workdir: /Volumes/ORICO/code/code6/auto-agents
model: gpt-5.5
provider: newapi
approval: never
sandbox: read-only
reasoning effort: xhigh
reasoning summaries: none
session id: 019e1b72-8247-74e2-85a5-f4a4f9feef13
--------
user
# Audit request: deafenken/auto-agents skill skeleton

This is a single-skill Claude Code / Codex / OpenCode skill that routes a task
across multiple coding CLIs. You sit on top of three CLIs (the "host" is
whichever invoked the skill; the other two are "workers"). The skill classifies
the task, picks one or more agents from a capability matrix, dispatches workers
as subprocesses with budget caps, and synthesizes one final answer.

Repo root: /Volumes/ORICO/code/code6/auto-agents
GitHub: https://github.com/deafenken/auto-agents (commit 02193d9)

## What I want from you

A focused review along these axes — list concrete findings, not prose:

1. **Integrity rules violations** — read auto-agents/references/integrity-rules.md.
   Then audit every assets/*.py against the eight rules. Flag any code path
   that could violate one. Be specific (file:line + rule #).

2. **State contract drift** — read auto-agents/references/state-contract.md.
   Then audit every read/write under runs/<task_id>/ in the assets. Any file
   path or schema field that the code uses but the contract doesn't list (or
   vice-versa) is a finding.

3. **Resume / idempotency bugs** — for each stage script (auth_check, route,
   dispatch, synthesize), trace what happens on a re-run after a crash at each
   internal step. Anything that double-writes, double-charges, or skips a step
   that should re-run is a bug.

4. **Cross-script consistency** — host_detect → auth_check → route →
   dispatch → synthesize is a pipeline. Any contract mismatch between adjacent
   stages (field name typo, wrong type, default-not-handled) is a finding.

5. **CLI invocation correctness** — invoke_{claude,codex,opencode}.py each
   hold ONE known-good command line. If you know any of these has changed
   flags since your training cutoff, flag it. Do not guess.

6. **Recursion guard correctness** — host_detect.py reads AUTO_AGENTS_DEPTH;
   dispatch.py sets it on child env. Trace whether a host that itself is
   invoked from another host (e.g. nested claude→codex→auto-agents) is caught.

7. **Cost gate edge cases** — budget.py reads audit.jsonl and task.yaml.
   What happens if audit.jsonl is malformed, missing, or has rows with
   cost_actual_usd=null?

## Severity scale

- **Critical**: would brick the skill on first real run.
- **Important**: silent wrong behavior under realistic input.
- **Minor**: cosmetic, edge, or harmless drift.

## Constraints

- Don't propose feature additions. Audit what's there.
- Don't rewrite the code yourself — just list findings the maintainer can act on.
- Cite file:line for each finding.
- If a finding is uncertain ("might be a bug under condition X"), say so.
- Report under 2000 words total. Tables / bullets are fine.

## Files to read (all under /Volumes/ORICO/code/code6/auto-agents/)

- auto-agents/SKILL.md
- auto-agents/references/*.md (six files)
- auto-agents/assets/*.py (eleven files)
- auto-agents/assets/supervisor.sh
- CLAUDE.md
codex
I’ll read the skill docs, contracts, and asset scripts first, then trace the pipeline and rerun behavior against the written contracts. Since this is an audit-only request, I’ll keep the work read-only.
exec
/bin/zsh -lc "find auto-agents/references -maxdepth 1 -type f -name '*.md' -print | sort" in /Volumes/ORICO/code/code6/auto-agents
 succeeded in 0ms:
auto-agents/references/agent-matrix.md
auto-agents/references/host-cli-modes.md
auto-agents/references/integrity-rules.md
auto-agents/references/routing-policy.md
auto-agents/references/state-contract.md
auto-agents/references/synthesis-methods.md

exec
/bin/zsh -lc 'rg --files auto-agents CLAUDE.md' in /Volumes/ORICO/code/code6/auto-agents
 succeeded in 0ms:
CLAUDE.md
auto-agents/SKILL.md
auto-agents/agents/openai.yaml
auto-agents/references/integrity-rules.md
auto-agents/references/synthesis-methods.md
auto-agents/references/routing-policy.md
auto-agents/references/host-cli-modes.md
auto-agents/references/state-contract.md
auto-agents/references/agent-matrix.md
auto-agents/assets/supervisor.sh
auto-agents/assets/synthesize.py
auto-agents/assets/budget.py
auto-agents/assets/dispatch.py
auto-agents/assets/yaml_io.py
auto-agents/assets/invoke_opencode.py
auto-agents/assets/auth_check.py
auto-agents/assets/route.py
auto-agents/assets/invoke_claude.py
auto-agents/assets/progress.py
auto-agents/assets/host_detect.py
auto-agents/assets/invoke_codex.py

exec
/bin/zsh -lc 'find auto-agents/assets -maxdepth 1 -type f -print | sort' in /Volumes/ORICO/code/code6/auto-agents
 succeeded in 0ms:
auto-agents/assets/auth_check.py
auto-agents/assets/budget.py
auto-agents/assets/dispatch.py
auto-agents/assets/host_detect.py
auto-agents/assets/invoke_claude.py
auto-agents/assets/invoke_codex.py
auto-agents/assets/invoke_opencode.py
auto-agents/assets/progress.py
auto-agents/assets/route.py
auto-agents/assets/supervisor.sh
auto-agents/assets/synthesize.py
auto-agents/assets/yaml_io.py

codex
I found the expected skill tree: six reference docs, eleven Python assets, and the shell supervisor. Next I’m reading the contracts with line numbers so each finding can be tied back to both code and spec.
exec
/bin/zsh -lc 'nl -ba auto-agents/references/integrity-rules.md' in /Volumes/ORICO/code/code6/auto-agents
 succeeded in 0ms:
     1	# Integrity rules — non-negotiable
     2	
     3	Eight rules. Every code path in this skill must satisfy them, or escalate to the user under them. Loosening these to "make the workflow easier" is a bug.
     4	
     5	## 1. No silent agent swap
     6	
     7	If the router's chosen agent is unavailable (missing binary, auth failure, exceeded budget), the skill **stops and asks the user**. It never silently routes to a different agent.
     8	
     9	- Allowed: "claude is unavailable; use codex instead? (y/n)"
    10	- Forbidden: writing `route.json` with `["codex"]` when the user's prompt implied claude was wanted, without surfacing the swap.
    11	
    12	## 2. Attribution mandatory in `final.md`
    13	
    14	Every sentence (or paragraph) in `synthesis/final.md` that is materially derived from a specific agent's output names that agent. Verbatim quotes are fenced and attributed.
    15	
    16	- Allowed: "Claude proposed using a Bloom filter (agents/claude/result.md §2); codex agreed and added a size estimate (agents/codex/result.md §3)."
    17	- Forbidden: paraphrasing one agent's solution as if it were the synthesizer's own.
    18	
    19	Why: when the user reads `final.md`, they must be able to trace any claim back to a single source agent's raw output.
    20	
    21	## 3. Budget gate — per-call and per-task
    22	
    23	Two caps in `task.yaml`: `per_call_cap_usd` (default $0.50) and `total_cap_usd` (default $2.00).
    24	
    25	Before any subprocess dispatch:
    26	
    27	1. Use the matrix's per-agent estimate × 2 (worst-case headroom) → if > per_call_cap_usd, escalate.
    28	2. Sum prior `audit.jsonl` actuals + this call's estimate → if > total_cap_usd, escalate.
    29	
    30	The estimates in `agent-matrix.md` are rough — `budget.py` reconciles with `audit.jsonl` actuals so subsequent estimates drift toward reality.
    31	
    32	If a call exceeds its estimate by >2× post-hoc, write a warning row to `progress.jsonl`. Three such warnings in one task → escalate "estimates are unreliable, pause?"
    33	
    34	## 4. Auth check upfront
    35	
    36	`auth_check.py` runs in Stage 0 against every candidate worker. If a worker's `--version` or `--help` fails, the worker is marked unavailable and the router cannot pick it.
    37	
    38	Forbidden: spawning a worker without an upfront auth check. We are not "discovering" auth failure mid-task by burning money on a doomed call.
    39	
    40	Edge: some CLIs don't have a free `--version`. For those, record `auth_checked: "deferred"`. The first real call surfaces auth — at most one wasted call.
    41	
    42	## 5. No CLI flag fabrication
    43	
    44	`assets/invoke_*.py` hold known-good invocation patterns. If those patterns fail on a user's machine, the wrapper surfaces the raw error — it does **not** try alternate flags it has not been told about.
    45	
    46	Forbidden:
    47	
    48	```python
    49	# DO NOT do this
    50	try:
    51	    subprocess.run(["codex", "exec", prompt])
    52	except:
    53	    subprocess.run(["codex", "-p", prompt])   # guessing!
    54	```
    55	
    56	Allowed: read `AUTO_AGENTS_CODEX_CMD` env override, then use exactly one default command. If both fail, escalate to the user with the raw stderr.
    57	
    58	## 6. Recursion guard
    59	
    60	`AUTO_AGENTS_DEPTH` is the source of truth:
    61	
    62	- Stage 0 reads it. If ≥ 1, refuse the skill.
    63	- Stage 2 sets it to `current+1` in every worker subprocess env.
    64	
    65	A worker that itself triggers auto-agents will refuse via Stage 0 check, even if the env var ladder is wrong elsewhere.
    66	
    67	The host **never** spawns itself as a worker. `route.json: agent_modes[host] == "inline"` always.
    68	
    69	## 7. Idempotent micro-steps
    70	
    71	Every step in `progress.jsonl` must be re-runnable. Re-running the skill after a crash:
    72	
    73	- Re-reads `task.yaml` (immutable, safe).
    74	- Skips workers with `meta.json: status == "ok"`.
    75	- Re-dispatches workers with `status` ∈ `{pending, failed, timed-out}` (the old `result.md` is moved to `agents/<name>/attempts/<N>/` first).
    76	- Rewrites `synthesis/final.md` atomically if all worker results changed.
    77	
    78	A step that mutates state without writing a `progress.jsonl` row is a bug. A step that rewrites an append-only file is a bug.
    79	
    80	## 8. All state on disk
    81	
    82	No information needed for resume lives in agent memory. After Stage 2 finishes:
    83	
    84	- The host model can crash, the parent shell can die, the laptop can reboot.
    85	- A fresh skill invocation reads `runs/<task_id>/` and proceeds from the last completed micro-step.
    86	
    87	Specifically: every decision, every cost number, every agent assignment is on disk before the next micro-step starts. If you find yourself wanting to "remember" something in the host's context window for the next stage, it goes on disk instead.
    88	
    89	---
    90	
    91	## Enforcement
    92	
    93	These rules are enforced *by the skill author*, not at runtime. There is no validator binary; the SKILL.md prompt makes them part of the contract. If a future PR introduces a code path that violates one of these, that PR is the bug — the skill is the spec.

exec
/bin/zsh -lc 'nl -ba CLAUDE.md' in /Volumes/ORICO/code/code6/auto-agents
exec
/bin/zsh -lc 'nl -ba auto-agents/references/state-contract.md' in /Volumes/ORICO/code/code6/auto-agents
exec
/bin/zsh -lc 'nl -ba auto-agents/SKILL.md' in /Volumes/ORICO/code/code6/auto-agents
 succeeded in 0ms:
     1	# CLAUDE.md
     2	
     3	This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.
     4	
     5	## What this repo is
     6	
     7	A single portable skill package — **auto-agents** — for Claude Code, Codex CLI, and OpenCode. It sits *above* those three coding agents and orchestrates them: the CLI that invokes it is the **host**, the other two are **workers**. Given one prompt, the skill classifies the task, picks the right agent(s) from a capability matrix, dispatches workers as subprocesses with budget caps, captures every stdout/stderr/meta to disk, and synthesizes one final answer (vote / debate / meta-synth).
     8	
     9	It is *not* a runnable application — there is no top-level build, no test suite, no `requirements.txt`. The deliverables are markdown + YAML + Python helper scripts + a shell supervisor that get copied into `~/.claude/skills/` (or `<project>/.claude/skills/`) and executed by an agent at runtime.
    10	
    11	Implication for editing: the "code" here is prompts, workflow contracts, and the dispatch helpers. Changes are validated by reading them and tracing the contract — not by running the helpers inside this checkout. Real runs happen on the user's machine, where the three CLIs are installed.
    12	
    13	## Layout
    14	
    15	This repo is a **single-skill** package (unlike auto-research and auto-kaggle which ship a family of skills):
    16	
    17	```
    18	auto-agents/                          ← the only skill folder
    19	├── SKILL.md                          frontmatter + workflow
    20	├── agents/openai.yaml                Codex-side UI metadata
    21	├── references/*.md                   load-on-demand reference docs
    22	└── assets/*.py + supervisor.sh       host_detect / route / dispatch / synthesize / wrappers
    23	README.md  README.zh-CN.md            bilingual top-level (English is GitHub default)
    24	docs/                                 hero image (cosmetic, optional)
    25	```
    26	
    27	If you ever split this into multiple skills (e.g. `auto-agents-route` + `auto-agents-synth`), mirror the auto-research / auto-kaggle convention: one folder per skill, all siblings at the repo root, top-level README is English, `README.zh-CN.md` mirrors.
    28	
    29	## State contract — do not invent paths
    30	
    31	All per-task state lives under `runs/<task_id>/`, where `task_id = YYYY-MM-DD-HHmm-<kebab-slug>`. The full file schema is in `auto-agents/references/state-contract.md` — treat that file as authoritative. When editing any helper that reads or writes task artifacts, cross-check it against `state-contract.md`.
    32	
    33	Files every stage reads first:
    34	
    35	- `runs/<task_id>/task.yaml` — host CLI, original prompt, budget caps, mode
    36	- `runs/<task_id>/.heartbeat` — current stage/step/ts_utc/pid
    37	- `runs/<task_id>/progress.jsonl` — append-only micro-step log; resume reads its tail
    38	- `runs/<task_id>/route.json` — Stage 1 output, Stage 2+ inputs
    39	
    40	`runs/` is gitignored — never commit task output back into this repo.
    41	
    42	## The host-CLI rule overrides everything
    43	
    44	The host CLI is **always** detected first (`assets/host_detect.py` — three-tier: env var → parent process chain → cached/asked + override via `AUTO_AGENTS_HOST`). The host never spawns itself as a worker. Every subprocess gets `AUTO_AGENTS_DEPTH = parent+1`; a Stage 0 check refuses any depth ≥1 (recursion guard).
    45	
    46	The full algorithm and rationale is in `auto-agents/references/host-cli-modes.md`. Every edit that touches host detection, auth check, or worker spawning must update this file too.
    47	
    48	## The integrity rules override everything else
    49	
    50	`auto-agents/references/integrity-rules.md` defines the eight non-negotiable rules (no silent agent swap, attribution mandatory in `final.md`, budget gate per-call + per-task, auth check upfront, no CLI flag fabrication, recursion guard, idempotent micro-steps, all state on disk). When editing any helper:
    51	
    52	- Do not loosen these rules to make a workflow easier.
    53	- A new code path must say how it satisfies (or escalates under) these rules.
    54	- The "stop and ask the human" escalations listed in SKILL.md and `references/routing-policy.md` are part of the contract — preserve them.
    55	
    56	## Conventions when editing
    57	
    58	- Keep `SKILL.md` frontmatter `description` within Claude Code's 1024-char limit and unambiguous about when to trigger.
    59	- Examples in references use absolute UTC timestamps. Never write "today" or "yesterday" — those rot.
    60	- The repo intentionally has both English (`README.md` — GitHub's default render) and Chinese (`README.zh-CN.md`) READMEs; if you change one substantively, mirror the change in the other.
    61	- Helper scripts read/write paths defined in `state-contract.md`. Do not invent new paths.
    62	- CLI invocation patterns (`assets/invoke_*.py`) hold ONE known-good command line each. **Never** try alternate flags on failure — that's CLI flag fabrication (integrity rule #5). Honor env overrides `AUTO_AGENTS_{CLAUDE,CODEX,OPENCODE}_CMD` and surface raw errors otherwise.
    63	- `.gitignore` includes `runs/`, `__pycache__/`, `._*`, `.DS_Store`. Verify before committing — `._*` files appear on macOS+ExFAT volumes and must not be staged.
    64	
    65	## Working in this environment
    66	
    67	This machine is shared and resource-constrained — it is for *editing the skill and committing*, not for executing it. Do not attempt to run `python dispatch.py` here to test it: actual runs (spawning real `claude` / `codex` / `opencode` subprocesses) belong on the user's machine. When the user wants to validate a change, list the commands they should run there rather than running them here.

 succeeded in 0ms:
     1	# State contract — `runs/<task_id>/`
     2	
     3	This is the **authoritative** schema. Every read/write under `runs/` must conform. Never invent paths the contract doesn't list. If you need a new path, add it here first, then update the code.
     4	
     5	## Task ID
     6	
     7	```
     8	task_id = <YYYY-MM-DD>-<HHmm>-<kebab-slug>
     9	```
    10	
    11	- Date/time is UTC at task creation.
    12	- `<kebab-slug>` is a 2-6 word, lowercase, hyphen-separated summary of the prompt, set by Stage 0.
    13	- The task ID is **immutable**. A resume reuses the same `task_id`; a fresh task gets a new one.
    14	
    15	## Directory layout
    16	
    17	```
    18	runs/<task_id>/
    19	├── task.yaml                         # written by Stage 0, never rewritten
    20	├── route.json                        # written by Stage 1, never rewritten (resume re-validates)
    21	├── progress.jsonl                    # append-only micro-step log
    22	├── audit.jsonl                       # append-only per-CLI-call audit (cost + time)
    23	├── .heartbeat                        # current stage / pid / ts_utc (overwritten each step)
    24	├── STOP   (sentinel, optional)       # user creates to request hard stop
    25	├── PAUSE  (sentinel, optional)       # user creates to request pause-at-next-microstep
    26	├── wait_until.txt (optional)         # ISO-8601 UTC; resume sleeps until this time
    27	│
    28	├── agents/
    29	│   ├── claude/                       # one folder per agent that was dispatched
    30	│   │   ├── invocation.md             # the exact prompt + flags handed to the worker
    31	│   │   ├── stdout.log                # full raw stdout (never truncated)
    32	│   │   ├── stderr.log                # full raw stderr
    33	│   │   ├── result.md                 # extracted assistant text (cleaned, no chrome)
    34	│   │   ├── meta.json                 # status, exit_code, ts_started/ended, tokens, cost_est_usd, cost_actual_usd
    35	│   │   └── attempts/                 # optional: prior failed attempts kept for audit
    36	│   │       └── 1/                    # same shape as parent, frozen
    37	│   ├── codex/...                     # same structure
    38	│   └── opencode/...
    39	│
    40	├── synthesis/
    41	│   ├── method.md                     # which synthesis path: vote | debate | meta-synth | inline
    42	│   ├── intermediate/                 # synthesis-method-specific scratch
    43	│   │   ├── debate-round-1.md         # for debate: per-round positions
    44	│   │   ├── debate-round-2.md
    45	│   │   ├── vote-tally.json           # for vote: agent → answer label
    46	│   │   └── meta-synth-input.md       # for meta-synth: concatenated worker outputs
    47	│   └── final.md                      # the one answer that gets returned
    48	│
    49	└── hand_off.md                       # 3-paragraph user-facing summary
    50	```
    51	
    52	## File schemas
    53	
    54	### `task.yaml` (Stage 0 writes; never rewritten)
    55	
    56	```yaml
    57	task_id: 2026-05-12-1640-fix-cache-invalidation
    58	created_utc: 2026-05-12T16:40:00Z
    59	host: claude                         # detected by host_detect.py — one of: claude | codex | opencode
    60	host_detection: env-var:CLAUDECODE   # how it was detected; for audit
    61	prompt: |
    62	  <verbatim user prompt>
    63	mode: auto                           # auto | multi | single:<agent> | dry-run
    64	per_call_cap_usd: 0.50
    65	total_cap_usd: 2.00
    66	deadline_utc: null                   # optional ISO-8601
    67	workers_available:                   # filled by Stage 0 auth_check
    68	  claude: true
    69	  codex: true
    70	  opencode: false                    # e.g. binary missing or no auth
    71	```
    72	
    73	### `route.json` (Stage 1 writes)
    74	
    75	```json
    76	{
    77	  "task_class": "idea",
    78	  "classification_reason": "matched keyword 'brainstorm' (rule 3)",
    79	  "agents": ["claude", "codex", "opencode"],
    80	  "agent_modes": {"claude": "subprocess", "codex": "subprocess", "opencode": "subprocess"},
    81	  "synthesis_method": "meta-synth",
    82	  "cost_estimate_usd": 0.45,
    83	  "inline_host_used": false
    84	}
    85	```
    86	
    87	When the host answers inline:
    88	
    89	```json
    90	{
    91	  "task_class": "code-write",
    92	  "agents": ["claude"],
    93	  "agent_modes": {"claude": "inline"},
    94	  "synthesis_method": "inline",
    95	  "cost_estimate_usd": 0.0,
    96	  "inline_host_used": true
    97	}
    98	```
    99	
   100	### `progress.jsonl` (append-only, one JSON per line)
   101	
   102	```json
   103	{"ts_utc":"2026-05-12T16:40:01Z","stage":0,"step":"host_detect","status":"ok","detail":"host=claude via CLAUDECODE"}
   104	{"ts_utc":"2026-05-12T16:40:02Z","stage":0,"step":"auth_check","status":"ok","detail":"claude:ok codex:ok opencode:missing-binary"}
   105	{"ts_utc":"2026-05-12T16:40:02Z","stage":1,"step":"classify","status":"ok","detail":"idea"}
   106	{"ts_utc":"2026-05-12T16:40:02Z","stage":1,"step":"select_agents","status":"ok","detail":"claude+codex (opencode unavailable)"}
   107	{"ts_utc":"2026-05-12T16:40:03Z","stage":2,"step":"dispatch:claude","status":"started"}
   108	{"ts_utc":"2026-05-12T16:40:31Z","stage":2,"step":"dispatch:claude","status":"ok","detail":"exit=0 cost=$0.18"}
   109	```
   110	
   111	Never rewrite. Resume reads tail.
   112	
   113	### `audit.jsonl` (append-only)
   114	
   115	One row per CLI call (successful or failed):
   116	
   117	```json
   118	{"ts_utc":"2026-05-12T16:40:31Z","agent":"claude","attempt":1,"exit_code":0,"duration_s":28.4,"tokens_in":3210,"tokens_out":1402,"cost_actual_usd":0.18}
   119	```
   120	
   121	### `.heartbeat` (overwritten each micro-step)
   122	
   123	```yaml
   124	stage: 2
   125	step: dispatch:codex
   126	pid: 48211
   127	ts_utc: 2026-05-12T16:40:45Z
   128	```
   129	
   130	The user can `cat runs/<task_id>/.heartbeat` to peek. The supervisor watches its `ts_utc` to detect stalls.
   131	
   132	### `agents/<name>/meta.json`
   133	
   134	```json
   135	{
   136	  "agent": "claude",
   137	  "status": "ok",
   138	  "exit_code": 0,
   139	  "ts_started_utc": "2026-05-12T16:40:03Z",
   140	  "ts_ended_utc": "2026-05-12T16:40:31Z",
   141	  "duration_s": 28.4,
   142	  "tokens_in": 3210,
   143	  "tokens_out": 1402,
   144	  "cost_est_usd": 0.30,
   145	  "cost_actual_usd": 0.18,
   146	  "invocation_cmd": "claude -p ${prompt}",
   147	  "attempts": 1
   148	}
   149	```
   150	
   151	`status` ∈ `{pending, ok, failed, timed-out}`. Resume re-dispatches anything not `ok`.
   152	
   153	### `synthesis/final.md`
   154	
   155	Mandatory sections:
   156	
   157	```markdown
   158	# Answer
   159	
   160	<the actual final answer>
   161	
   162	---
   163	
   164	## Contributors
   165	
   166	- **claude** — wrote the primary draft (sections 1-3). [agents/claude/result.md]
   167	- **codex** — supplied the alternative interpretation in §2. [agents/codex/result.md]
   168	- **opencode** — *unavailable* (no auth on this host).
   169	
   170	## Synthesis method: meta-synth
   171	
   172	The host (claude) read both worker outputs and merged. No conflicts on §1; in §2
   173	both agents agreed; in §3 only claude had a substantive answer.
   174	
   175	## Audit
   176	
   177	- Total cost: $0.31
   178	- Total time: 47s
   179	- See `audit.jsonl` for per-call breakdown.
   180	```
   181	
   182	### `hand_off.md`
   183	
   184	Three paragraphs, written for the human:
   185	
   186	1. **What you asked, in one sentence.**
   187	2. **What was done** — which agents ran, how they were merged.
   188	3. **What's next** — does the user need to verify, run something, or pick between alternatives?
   189	
   190	## Atomicity
   191	
   192	Every file write that is not append-only must use `.tmp + rename`:
   193	
   194	```python
   195	def atomic_write(path, content):
   196	    tmp = path + ".tmp"
   197	    with open(tmp, "w") as f:
   198	        f.write(content)
   199	    os.replace(tmp, path)
   200	```
   201	
   202	Append-only files (`progress.jsonl`, `audit.jsonl`) use a single `open(..., "a")` write per row — POSIX guarantees a single small write does not interleave.
   203	
   204	## Sentinels
   205	
   206	- `runs/<task_id>/STOP` — at the top of every micro-step, check; if present, write `progress.jsonl` row `{"status":"stopped-by-user"}` and exit.
   207	- `runs/<task_id>/PAUSE` — same check; if present, sleep 30s and re-check (do not advance state).
   208	- `runs/<task_id>/wait_until.txt` — ISO-8601 UTC; if file exists and now < timestamp, sleep until then.
   209	
   210	These three are part of the long-running protocol — never bypass them.

 succeeded in 0ms:
     1	---
     2	name: auto-agents
     3	description: Multi-agent CLI orchestrator. Activate when the user wants one task answered by routing or fanning out across multiple coding CLIs (claude, codex, opencode) instead of a single agent. Detects which CLI is the host, classifies the task (code-write / code-review / math / idea / research / QA), picks the best worker(s) per the agent-matrix, dispatches them as subprocesses with budget caps, captures stdout/stderr/meta to disk under runs/<task_id>/, and synthesizes a single answer (vote / debate / meta-synth). All state is on disk, micro-steps are idempotent, resume-by-default. Do NOT trigger for single-CLI tasks where the host can answer directly without fan-out — those should stay inline.
     4	---
     5	
     6	# auto-agents — multi-CLI router & synthesizer
     7	
     8	You sit on top of three coding CLIs (`claude`, `codex`, `opencode`) and route one task across them. The CLI that invokes *you* is the **host**; the other two are **workers**. You never spawn the host as a worker (recursion guard).
     9	
    10	## When to trigger
    11	
    12	YES, run this skill when:
    13	
    14	- User asks "give me <X> using the best CLI for this" and the host might not be best.
    15	- User asks for multi-perspective answers ("get ideas from all three / brainstorm with multiple agents / which CLI is right for this").
    16	- User asks for adversarial review ("have <other CLI> audit this") — even with one named worker.
    17	
    18	NO, do not run this skill when:
    19	
    20	- The host can clearly handle the task and the user did not ask for fan-out (writing one function in Claude Code, debugging one bug in Codex). The router will just route everything back to the host, wasting setup.
    21	- `AUTO_AGENTS_DEPTH` ≥ 1 in the environment (you are already inside an auto-agents call — refuse).
    22	
    23	## Stage map
    24	
    25	```
    26	Stage 0 — Setup        (assets/auth_check.py)   detect host, verify worker CLIs+auth, write task.yaml
    27	Stage 1 — Route        (assets/route.py)        classify task, select agents, write route.json
    28	Stage 2 — Dispatch     (assets/dispatch.py)     spawn worker subprocesses, capture to agents/<name>/
    29	Stage 3 — Synthesize   (assets/synthesize.py)   vote / debate / meta-synth → synthesis/final.md
    30	Stage 4 — Hand-off     (inline)                 write hand_off.md, print summary, exit cleanly
    31	```
    32	
    33	Each stage writes a `progress.jsonl` row at start and at completion. Re-running the skill re-reads disk and continues from the last completed micro-step.
    34	
    35	## State contract — do not invent paths
    36	
    37	Every task gets `runs/<task_id>/` where `task_id = YYYY-MM-DD-HHmm-<kebab-slug>`. The full schema is in `references/state-contract.md`. **Never invent a directory the contract doesn't list.**
    38	
    39	Files every stage reads first:
    40	
    41	- `runs/<task_id>/task.yaml` — host CLI, original prompt, budget cap, deadline, mode flags
    42	- `runs/<task_id>/.heartbeat` — stage / pid / ts_utc (user can `cat` to peek)
    43	- `runs/<task_id>/progress.jsonl` — append-only micro-step log; resume reads its tail
    44	- `runs/<task_id>/route.json` — written by Stage 1, consumed by Stage 2+
    45	
    46	`runs/` is gitignored. Never commit task output back into the repo.
    47	
    48	## The host-CLI rule overrides everything
    49	
    50	The host CLI is whichever of `claude` / `codex` / `opencode` invoked this skill. Read `references/host-cli-modes.md` once at Stage 0. Key invariants:
    51	
    52	1. The host **never** spawns itself as a worker. If the router picks the host's best-fit task class, the host answers inline and `route.json` records `agents: [<host>]` with `mode: inline`.
    53	2. Each worker subprocess runs with `AUTO_AGENTS_DEPTH = <current+1>`. If a worker tries to recursively invoke auto-agents, it refuses (see "When to trigger").
    54	3. Worker auth is checked in Stage 0 by running each worker's `--version` (or equivalent). If a worker has no credentials, escalate — do NOT silently route to a different agent.
    55	
    56	## Integrity rules — non-negotiable
    57	
    58	Read `references/integrity-rules.md`. Eight rules: no silent agent swap, attribution mandatory in `final.md`, budget gate per-call + per-task, auth check upfront, no CLI flag fabrication, recursion guard, idempotent micro-steps, all state on disk.
    59	
    60	The orchestrator's "stop and ask the human" checkpoints:
    61	
    62	- Before any single call estimated to cost > `task.yaml: per_call_cap_usd` (default $0.50)
    63	- Before total task spend would exceed `task.yaml: total_cap_usd` (default $2.00)
    64	- When a chosen worker's `--version` check fails (auth or missing binary)
    65	- When debate or vote synthesis cannot reach a conclusion after the configured rounds
    66	
    67	## When to load which reference
    68	
    69	| If you are… | Load |
    70	|---|---|
    71	| classifying a task & picking agents | `references/agent-matrix.md`, `references/routing-policy.md` |
    72	| spawning a worker CLI | `references/host-cli-modes.md` (for the recursion + auth rule) |
    73	| merging outputs | `references/synthesis-methods.md` |
    74	| writing files under `runs/` | `references/state-contract.md` |
    75	| about to take any irreversible action (cost > cap, silent fallback) | `references/integrity-rules.md` |
    76	
    77	Default behavior: load `state-contract.md` and `integrity-rules.md` early; load the others on demand per the table.
    78	
    79	## Idempotency contract
    80	
    81	A re-run after a crash:
    82	
    83	1. Reads `runs/<task_id>/.heartbeat` to find the last stage.
    84	2. Reads `runs/<task_id>/progress.jsonl` tail to find the last completed micro-step.
    85	3. For each worker in `route.json`: if `agents/<name>/meta.json` shows `status: ok`, skip; if `status: pending` or missing, re-dispatch.
    86	4. Synthesis re-reads all `agents/*/result.md` and rewrites `synthesis/final.md` atomically (`.tmp` + rename).
    87	
    88	Append-only files (`progress.jsonl`, `audit.jsonl`) are never rewritten — resume just appends a `resumed` row.
    89	
    90	## Modes
    91	
    92	`task.yaml: mode` controls behavior:
    93	
    94	- `auto` (default): router decides agents and synthesis method.
    95	- `multi`: force all three agents (router still chooses synthesis method).
    96	- `single:<agent>`: skip router, dispatch only the named agent.
    97	- `dry-run`: write `route.json` and per-agent `invocation.md`, but do NOT spawn subprocesses. Print the planned calls.
    98	
    99	## What you must not do
   100	
   101	- Do not call a worker CLI that the user did not authorize on this machine. Read `references/host-cli-modes.md` for the auth-check protocol.
   102	- Do not fabricate CLI flags. The wrappers (`assets/invoke_*.py`) hold known-good invocation patterns; if those fail, surface the error — do NOT guess flags.
   103	- Do not pretend a worker answered when it crashed. `synthesis/final.md` must list every agent that *successfully* contributed and every agent that failed (with the error class).
   104	- Do not auto-pick a final answer when synthesis is split. Escalate.

codex
The state contract says every non-append write must use temp+rename, while append logs are single-row appends. I’m now reading every asset with line numbers and the routing/host references needed to check adjacent stage contracts.
exec
/bin/zsh -lc 'nl -ba auto-agents/assets/host_detect.py' in /Volumes/ORICO/code/code6/auto-agents
exec
/bin/zsh -lc 'nl -ba auto-agents/assets/auth_check.py' in /Volumes/ORICO/code/code6/auto-agents
 succeeded in 0ms:
     1	"""Stage 0 — detect host, verify worker CLIs, write task.yaml + workers_available.
     2	
     3	Usage (from inside the host CLI):
     4	    python -m auth_check --run-dir <runs/<task_id>> --prompt-file <path>
     5	
     6	Or programmatic:
     7	    from auth_check import run_stage0
     8	    run_stage0(run_dir=..., prompt=..., mode="auto", per_call_cap_usd=0.50,
     9	               total_cap_usd=2.00, deadline_utc=None)
    10	
    11	Reads ../references/host-cli-modes.md for the algorithm.
    12	"""
    13	from __future__ import annotations
    14	
    15	import argparse
    16	import json
    17	import sys
    18	from pathlib import Path
    19	
    20	import host_detect
    21	import invoke_claude
    22	import invoke_codex
    23	import invoke_opencode
    24	import progress as P
    25	import yaml_io
    26	
    27	WORKERS = {
    28	    "claude":   invoke_claude,
    29	    "codex":    invoke_codex,
    30	    "opencode": invoke_opencode,
    31	}
    32	
    33	
    34	def run_stage0(run_dir: Path, prompt: str, *, mode: str = "auto",
    35	               per_call_cap_usd: float = 0.50, total_cap_usd: float = 2.00,
    36	               deadline_utc: str | None = None,
    37	               host_override: str | None = None) -> dict:
    38	    run_dir.mkdir(parents=True, exist_ok=True)
    39	    P.check_sentinels(run_dir)
    40	    P.write_heartbeat(run_dir, stage=0, step="host_detect")
    41	
    42	    # --- host detection ------------------------------------------------------
    43	    det = host_detect.detect()
    44	    if det.get("refused"):
    45	        P.append_progress(run_dir, stage=0, step="host_detect",
    46	                          status="refused", detail=det.get("reason", ""))
    47	        raise SystemExit(3)
    48	    host = host_override or det.get("host")
    49	    detection = "manual-override" if host_override else det.get("detection")
    50	    if host is None:
    51	        P.append_progress(run_dir, stage=0, step="host_detect",
    52	                          status="needs-user", detail=json.dumps(det))
    53	        # Caller (the host CLI's tool-using agent) must ask the user and re-invoke.
    54	        raise SystemExit(2)
    55	    P.append_progress(run_dir, stage=0, step="host_detect",
    56	                      status="ok", detail=f"host={host} via {detection}")
    57	
    58	    # --- worker auth check ---------------------------------------------------
    59	    P.write_heartbeat(run_dir, stage=0, step="auth_check")
    60	    workers_available: dict[str, bool] = {}
    61	    workers_detail: dict[str, str] = {}
    62	    for name, mod in WORKERS.items():
    63	        if name == host:
    64	            workers_available[name] = True
    65	            workers_detail[name] = "host (inline)"
    66	            continue
    67	        ok, detail = mod.version_check()
    68	        workers_available[name] = ok
    69	        workers_detail[name] = detail
    70	    P.append_progress(
    71	        run_dir, stage=0, step="auth_check", status="ok",
    72	        detail=" ".join(f"{k}:{'ok' if v else 'unavailable'}"
    73	                        for k, v in workers_available.items()),
    74	    )
    75	
    76	    # --- write task.yaml -----------------------------------------------------
    77	    task = {
    78	        "task_id": run_dir.name,
    79	        "created_utc": P.utc_now_iso(),
    80	        "host": host,
    81	        "host_detection": detection,
    82	        "prompt": prompt,
    83	        "mode": mode,
    84	        "per_call_cap_usd": per_call_cap_usd,
    85	        "total_cap_usd": total_cap_usd,
    86	        "deadline_utc": deadline_utc,
    87	        "workers_available": workers_available,
    88	        "workers_detail": workers_detail,
    89	    }
    90	    P.atomic_write_text(run_dir / "task.yaml", yaml_io.dump(task))
    91	    P.append_progress(run_dir, stage=0, step="write_task_yaml", status="ok")
    92	    return task
    93	
    94	
    95	def main(argv: list[str] | None = None) -> int:
    96	    ap = argparse.ArgumentParser()
    97	    ap.add_argument("--run-dir", required=True, type=Path)
    98	    ap.add_argument("--prompt-file", required=True, type=Path)
    99	    ap.add_argument("--mode", default="auto")
   100	    ap.add_argument("--per-call-cap-usd", type=float, default=0.50)
   101	    ap.add_argument("--total-cap-usd", type=float, default=2.00)
   102	    ap.add_argument("--deadline-utc", default=None)
   103	    ap.add_argument("--host-override", default=None,
   104	                    choices=[None, "claude", "codex", "opencode"])
   105	    args = ap.parse_args(argv)
   106	    prompt = args.prompt_file.read_text(encoding="utf-8")
   107	    task = run_stage0(
   108	        run_dir=args.run_dir,
   109	        prompt=prompt,
   110	        mode=args.mode,
   111	        per_call_cap_usd=args.per_call_cap_usd,
   112	        total_cap_usd=args.total_cap_usd,
   113	        deadline_utc=args.deadline_utc,
   114	        host_override=args.host_override,
   115	    )
   116	    print(json.dumps(task, indent=2, ensure_ascii=False))
   117	    return 0
   118	
   119	
   120	if __name__ == "__main__":
   121	    sys.exit(main())

 succeeded in 0ms:
     1	"""Detect which of {claude, codex, opencode} is the host CLI.
     2	
     3	Three-tier algorithm. See ../references/host-cli-modes.md for the contract.
     4	
     5	Result is a dict with keys:
     6	    host:        one of "claude" | "codex" | "opencode" | None
     7	    detection:   one of "env-override" | "env-var:<NAME>" | "ps-chain:<NAME>"
     8	                 | "cache" | "user-asked" | None
     9	    candidates:  list of candidates discovered (for audit)
    10	    refused:     bool — True iff AUTO_AGENTS_DEPTH >= 1 (recursion guard)
    11	
    12	When host is None and refused is False, the caller (auth_check.py / Stage 0)
    13	must prompt the user; this module never blocks on stdin.
    14	"""
    15	from __future__ import annotations
    16	
    17	import json
    18	import os
    19	import subprocess
    20	import sys
    21	import time
    22	from pathlib import Path
    23	
    24	# --- Env-var families ---------------------------------------------------------
    25	ENV_FAMILIES = {
    26	    "claude":   ("CLAUDECODE", "CLAUDE_CODE", "CLAUDE_CODE_ENTRYPOINT"),
    27	    "codex":    ("CODEX_CLI", "CODEX_ENV", "CODEX_HOME"),
    28	    "opencode": ("OPENCODE", "OPENCODE_ENV", "OPENCODE_HOME"),
    29	}
    30	
    31	CACHE_PATH = Path.home() / ".config" / "auto-agents" / "host.yaml"
    32	CACHE_MAX_AGE_SEC = 30 * 24 * 3600  # 30 days
    33	PS_CHAIN_DEPTH_CAP = 8
    34	PS_TIMEOUT_SEC = 2
    35	
    36	
    37	def _env_tier() -> tuple[str | None, list[str], str | None]:
    38	    """Returns (host_if_unique, all_matched_families, matched_env_var)."""
    39	    matches: dict[str, str] = {}
    40	    for fam, vars_ in ENV_FAMILIES.items():
    41	        for v in vars_:
    42	            if v in os.environ and os.environ[v].strip():
    43	                matches[fam] = v
    44	                break
    45	    if len(matches) == 1:
    46	        ((fam, var),) = matches.items()
    47	        return fam, [fam], var
    48	    return None, sorted(matches.keys()), None
    49	
    50	
    51	def _parent_pid(pid: int) -> int | None:
    52	    try:
    53	        out = subprocess.run(
    54	            ["ps", "-o", "ppid=", "-p", str(pid)],
    55	            capture_output=True, text=True, timeout=PS_TIMEOUT_SEC,
    56	        )
    57	        if out.returncode != 0:
    58	            return None
    59	        ppid = out.stdout.strip()
    60	        return int(ppid) if ppid.isdigit() else None
    61	    except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
    62	        return None
    63	
    64	
    65	def _proc_name(pid: int) -> str | None:
    66	    try:
    67	        out = subprocess.run(
    68	            ["ps", "-o", "comm=", "-p", str(pid)],
    69	            capture_output=True, text=True, timeout=PS_TIMEOUT_SEC,
    70	        )
    71	        if out.returncode != 0:
    72	            return None
    73	        name = out.stdout.strip()
    74	        return os.path.basename(name) if name else None
    75	    except (subprocess.TimeoutExpired, FileNotFoundError):
    76	        return None
    77	
    78	
    79	def _ps_chain_tier() -> tuple[str | None, list[tuple[int, str]]]:
    80	    """Walk parent chain; return (host_if_found, chain_for_audit)."""
    81	    targets = set(ENV_FAMILIES)
    82	    chain: list[tuple[int, str]] = []
    83	    pid = os.getppid()
    84	    for _ in range(PS_CHAIN_DEPTH_CAP):
    85	        if pid is None or pid <= 1:
    86	            break
    87	        name = _proc_name(pid) or ""
    88	        chain.append((pid, name))
    89	        # match: process basename contains one of the target names
    90	        hits = [t for t in targets if t in name.lower()]
    91	        if len(hits) >= 1:
    92	            # closest match (first hit on the way up) wins
    93	            return hits[0], chain
    94	        pid = _parent_pid(pid)
    95	    return None, chain
    96	
    97	
    98	def _cache_tier() -> tuple[str | None, str | None]:
    99	    """Read ~/.config/auto-agents/host.yaml; return (host, prior_detection)."""
   100	    if not CACHE_PATH.exists():
   101	        return None, None
   102	    try:
   103	        text = CACHE_PATH.read_text()
   104	        # tiny YAML subset: host: <name> / confirmed_utc: <iso> / confirmed_by: <s>
   105	        data: dict[str, str] = {}
   106	        for line in text.splitlines():
   107	            if ":" in line:
   108	                k, _, v = line.partition(":")
   109	                data[k.strip()] = v.strip()
   110	        host = data.get("host")
   111	        confirmed = data.get("confirmed_utc", "")
   112	        if host not in ENV_FAMILIES:
   113	            return None, None
   114	        # age check (best-effort; if parse fails, treat as expired)
   115	        try:
   116	            # parse "2026-05-12T16:40:00Z" → epoch
   117	            t = time.strptime(confirmed.rstrip("Z"), "%Y-%m-%dT%H:%M:%S")
   118	            age = time.time() - (time.mktime(t) - time.timezone)
   119	            if age > CACHE_MAX_AGE_SEC:
   120	                return None, None
   121	        except ValueError:
   122	            return None, None
   123	        return host, data.get("confirmed_by")
   124	    except OSError:
   125	        return None, None
   126	
   127	
   128	def write_cache(host: str, detection: str) -> None:
   129	    """Persist confirmed host. Caller invokes this only after Tier 3 (user ask)."""
   130	    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
   131	    iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
   132	    body = (
   133	        f"host: {host}\n"
   134	        f"confirmed_utc: {iso}\n"
   135	        f"confirmed_by: {detection}\n"
   136	    )
   137	    tmp = CACHE_PATH.with_suffix(".yaml.tmp")
   138	    tmp.write_text(body)
   139	    os.replace(tmp, CACHE_PATH)
   140	
   141	
   142	def detect() -> dict:
   143	    depth = int(os.environ.get("AUTO_AGENTS_DEPTH", "0") or "0")
   144	    if depth >= 1:
   145	        return {
   146	            "host": None, "detection": None, "candidates": [],
   147	            "refused": True, "reason": f"AUTO_AGENTS_DEPTH={depth}",
   148	        }
   149	
   150	    # Override env var wins over everything.
   151	    override = os.environ.get("AUTO_AGENTS_HOST", "").strip().lower()
   152	    if override in ENV_FAMILIES:
   153	        return {
   154	            "host": override, "detection": "env-override",
   155	            "candidates": [override], "refused": False,
   156	        }
   157	
   158	    # Tier 1 — env-var families
   159	    host, candidates, var = _env_tier()
   160	    if host is not None:
   161	        return {
   162	            "host": host, "detection": f"env-var:{var}",
   163	            "candidates": candidates, "refused": False,
   164	        }
   165	
   166	    # Tier 2 — parent process chain
   167	    host, chain = _ps_chain_tier()
   168	    if host is not None:
   169	        return {
   170	            "host": host, "detection": f"ps-chain:{host}",
   171	            "candidates": [name for _, name in chain], "refused": False,
   172	        }
   173	
   174	    # Tier 3a — cache
   175	    host, prior = _cache_tier()
   176	    if host is not None:
   177	        return {
   178	            "host": host, "detection": "cache",
   179	            "candidates": [], "refused": False,
   180	            "prior_detection": prior,
   181	        }
   182	
   183	    # Tier 3b — must ask the user (caller's job)
   184	    return {
   185	        "host": None, "detection": None, "candidates": candidates,
   186	        "ps_chain": chain, "refused": False,
   187	        "needs_user_input": True,
   188	    }
   189	
   190	
   191	if __name__ == "__main__":
   192	    result = detect()
   193	    print(json.dumps(result, indent=2))
   194	    # exit code 0 if we know the host, 2 if we need to ask, 3 if refused
   195	    if result.get("refused"):
   196	        sys.exit(3)
   197	    sys.exit(0 if result.get("host") else 2)

exec
/bin/zsh -lc 'nl -ba auto-agents/assets/dispatch.py' in /Volumes/ORICO/code/code6/auto-agents
exec
/bin/zsh -lc 'nl -ba auto-agents/assets/route.py' in /Volumes/ORICO/code/code6/auto-agents
 succeeded in 0ms:
     1	"""Stage 2 — fan out workers per route.json.
     2	
     3	Each subprocess worker gets AUTO_AGENTS_DEPTH = parent+1 in its env so any
     4	recursive auto-agents invocation will refuse at Stage 0 (recursion guard).
     5	
     6	The host agent (route.agent_modes[host] == "inline") does NOT get spawned
     7	here. Instead its `agents/<host>/invocation.md` is written and a placeholder
     8	`meta.json` is written with status="pending". The SKILL.md prompt instructs
     9	the host to fill `agents/<host>/result.md` itself, then re-invoke dispatch.py
    10	which will mark host status="ok" once result.md is non-empty.
    11	"""
    12	from __future__ import annotations
    13	
    14	import argparse
    15	import json
    16	import os
    17	import sys
    18	from pathlib import Path
    19	
    20	import invoke_claude
    21	import invoke_codex
    22	import invoke_opencode
    23	import progress as P
    24	import yaml_io
    25	
    26	WORKERS = {
    27	    "claude":   invoke_claude,
    28	    "codex":    invoke_codex,
    29	    "opencode": invoke_opencode,
    30	}
    31	
    32	
    33	def _read_route(run_dir: Path) -> dict:
    34	    return json.loads((run_dir / "route.json").read_text(encoding="utf-8"))
    35	
    36	
    37	def _read_prompt(run_dir: Path) -> str:
    38	    return yaml_io.load_path(run_dir / "task.yaml").get("prompt", "")
    39	
    40	
    41	def _archive_prior_attempt(agent_dir: Path) -> None:
    42	    """If agent_dir has a result.md from a prior failed attempt, move it under
    43	    attempts/<N>/ so resume produces a fresh result."""
    44	    meta = agent_dir / "meta.json"
    45	    if not meta.exists():
    46	        return
    47	    attempts_dir = agent_dir / "attempts"
    48	    attempts_dir.mkdir(exist_ok=True)
    49	    n = len(list(attempts_dir.iterdir())) + 1
    50	    target = attempts_dir / str(n)
    51	    target.mkdir()
    52	    for name in ("invocation.md", "stdout.log", "stderr.log",
    53	                 "result.md", "meta.json"):
    54	        src = agent_dir / name
    55	        if src.exists():
    56	            os.replace(src, target / name)
    57	
    58	
    59	def _meta_status(agent_dir: Path) -> str | None:
    60	    meta = agent_dir / "meta.json"
    61	    if not meta.exists():
    62	        return None
    63	    try:
    64	        return json.loads(meta.read_text(encoding="utf-8")).get("status")
    65	    except (json.JSONDecodeError, OSError):
    66	        return None
    67	
    68	
    69	def _dispatch_subprocess(run_dir: Path, agent: str, prompt: str) -> dict:
    70	    mod = WORKERS[agent]
    71	    agent_dir = run_dir / "agents" / agent
    72	    agent_dir.mkdir(parents=True, exist_ok=True)
    73	
    74	    # invocation.md — reproducible record
    75	    inv = (
    76	        f"# Invocation for `{agent}`\n\n"
    77	        f"Cmd: `{os.environ.get(f'AUTO_AGENTS_{agent.upper()}_CMD', mod.DEFAULT_CMD)}` "
    78	        f"<prompt>\n\n"
    79	        f"## Prompt\n\n```\n{prompt}\n```\n"
    80	    )
    81	    P.atomic_write_text(agent_dir / "invocation.md", inv)
    82	
    83	    # spawn
    84	    P.append_progress(run_dir, stage=2, step=f"dispatch:{agent}", status="started")
    85	    P.write_heartbeat(run_dir, stage=2, step=f"dispatch:{agent}")
    86	    depth = int(os.environ.get("AUTO_AGENTS_DEPTH", "0") or "0")
    87	    env_overrides = {"AUTO_AGENTS_DEPTH": str(depth + 1)}
    88	    result = mod.invoke(prompt, env_overrides=env_overrides)
    89	
    90	    # write raw streams + extracted result
    91	    (agent_dir / "stdout.log").write_text(result["stdout"], encoding="utf-8")
    92	    (agent_dir / "stderr.log").write_text(result["stderr"], encoding="utf-8")
    93	    answer = mod.extract_answer(result["stdout"]) if result["exit_code"] == 0 else ""
    94	    P.atomic_write_text(agent_dir / "result.md", answer)
    95	
    96	    status = "ok" if result["exit_code"] == 0 else \
    97	             ("timed-out" if result["exit_code"] == 124 else "failed")
    98	    meta = {
    99	        "agent": agent,
   100	        "status": status,
   101	        "exit_code": result["exit_code"],
   102	        "ts_started_utc": result["ts_started_utc"],
   103	        "ts_ended_utc": result["ts_ended_utc"],
   104	        "duration_s": result["duration_s"],
   105	        "tokens_in": None,
   106	        "tokens_out": None,
   107	        "cost_est_usd": None,
   108	        "cost_actual_usd": None,
   109	        "invocation_cmd": result["cmd"],
   110	        "attempts": 1,
   111	    }
   112	    P.atomic_write_json(agent_dir / "meta.json", meta)
   113	    P.append_audit(
   114	        run_dir, agent=agent, attempt=1, exit_code=result["exit_code"],
   115	        duration_s=result["duration_s"], tokens_in=None, tokens_out=None,
   116	        cost_actual_usd=None,
   117	    )
   118	    P.append_progress(run_dir, stage=2, step=f"dispatch:{agent}", status=status,
   119	                      detail=f"exit={result['exit_code']} t={result['duration_s']:.1f}s")
   120	    return meta
   121	
   122	
   123	def _stage_inline_host(run_dir: Path, host: str, prompt: str) -> dict:
   124	    """Write the invocation but leave result.md to be filled by the host model."""
   125	    agent_dir = run_dir / "agents" / host
   126	    agent_dir.mkdir(parents=True, exist_ok=True)
   127	    inv = (
   128	        f"# Inline invocation for host `{host}`\n\n"
   129	        f"The host agent should write its answer to `result.md` in this folder,\n"
   130	        f"then update `meta.json: status` to `ok` and re-run dispatch.py.\n\n"
   131	        f"## Prompt\n\n```\n{prompt}\n```\n"
   132	    )
   133	    P.atomic_write_text(agent_dir / "invocation.md", inv)
   134	    meta = {
   135	        "agent": host, "status": "pending",
   136	        "exit_code": None, "ts_started_utc": P.utc_now_iso(),
   137	        "ts_ended_utc": None, "duration_s": None,
   138	        "tokens_in": None, "tokens_out": None,
   139	        "cost_est_usd": None, "cost_actual_usd": None,
   140	        "invocation_cmd": "inline", "attempts": 1,
   141	    }
   142	    P.atomic_write_json(agent_dir / "meta.json", meta)
   143	    P.append_progress(run_dir, stage=2, step=f"dispatch:{host}",
   144	                      status="pending-inline",
   145	                      detail="host writes result.md, then re-run dispatch")
   146	    return meta
   147	
   148	
   149	def run_stage2(run_dir: Path) -> dict:
   150	    P.check_sentinels(run_dir)
   151	    route = _read_route(run_dir)
   152	    if route.get("escalations"):
   153	        P.append_progress(run_dir, stage=2, step="check_route",
   154	                          status="blocked",
   155	                          detail="route has unresolved escalations")
   156	        return {"status": "blocked", "reason": "route escalations unresolved"}
   157	
   158	    prompt = _read_prompt(run_dir)
   159	    results: dict[str, dict] = {}
   160	
   161	    for agent, mode in route["agent_modes"].items():
   162	        agent_dir = run_dir / "agents" / agent
   163	
   164	        # resume: skip if already ok
   165	        prior = _meta_status(agent_dir)
   166	        if prior == "ok":
   167	            P.append_progress(run_dir, stage=2, step=f"dispatch:{agent}",
   168	                              status="skipped", detail="already ok")
   169	            results[agent] = {"status": "ok", "skipped": True}
   170	            continue
   171	
   172	        # resume: archive prior failed attempt
   173	        if prior in ("failed", "timed-out"):
   174	            _archive_prior_attempt(agent_dir)
   175	
   176	        if mode == "inline":
   177	            results[agent] = _stage_inline_host(run_dir, agent, prompt)
   178	        else:
   179	            results[agent] = _dispatch_subprocess(run_dir, agent, prompt)
   180	
   181	    return {"status": "ok", "results": results}
   182	
   183	
   184	def main(argv: list[str] | None = None) -> int:
   185	    ap = argparse.ArgumentParser()
   186	    ap.add_argument("--run-dir", required=True, type=Path)
   187	    args = ap.parse_args(argv)
   188	    out = run_stage2(args.run_dir)
   189	    print(json.dumps(out, indent=2, ensure_ascii=False))
   190	    return 0 if out.get("status") == "ok" else 1
   191	
   192	
   193	if __name__ == "__main__":
   194	    sys.exit(main())

 succeeded in 0ms:
     1	"""Stage 1 — classify task and write route.json.
     2	
     3	The data (which agent for which class, which keywords trigger which class) lives
     4	in ../references/agent-matrix.md as the source of truth for editors. This file
     5	is the algorithm that consumes that data. The matrix data is duplicated as
     6	Python constants here for execution, but if you change one update both.
     7	"""
     8	from __future__ import annotations
     9	
    10	import argparse
    11	import json
    12	import re
    13	import sys
    14	from pathlib import Path
    15	
    16	import progress as P
    17	import yaml_io
    18	
    19	# --- Matrix data (mirrors agent-matrix.md) ------------------------------------
    20	TASK_CLASSES = {
    21	    "code-write":  {"primary": ["claude", "codex"],                     "synthesis": "inline"},
    22	    "code-review": {"primary": ["codex", "claude"],                     "synthesis": "inline"},
    23	    "math":        {"primary": ["opencode", "claude"],                  "synthesis": "inline"},
    24	    "idea":        {"primary": ["claude", "codex", "opencode"],         "synthesis": "meta-synth"},
    25	    "debate":      {"primary": ["claude", "codex", "opencode"],         "synthesis": "debate"},
    26	    "research":    {"primary": ["claude"],                              "synthesis": "inline"},
    27	    "quick-qa":    {"primary": ["__host__"],                            "synthesis": "inline"},
    28	}
    29	
    30	# Rough $/call estimates (mid-range). Reconciled with audit.jsonl actuals.
    31	COST_ESTIMATE_USD = {"claude": 0.20, "codex": 0.12, "opencode": 0.05}
    32	
    33	# Classification heuristics; first-match-wins ordering.
    34	KEYWORDS = [
    35	    ("code-review", [r"\baudit\b", r"\breview\b", r"\bbug(s)?\b",
    36	                     r"\bsecurity\b", r"\blint\b", r"correctness check"]),
    37	    ("math",        [r"\bprove\b", r"\bderive\b", r"\btheorem\b", r"\bintegral\b",
    38	                     r"combinatorics", r"step-by-step solve", r"证明", r"推导"]),
    39	    ("idea",        [r"\bbrainstorm\b", r"\bpropose\b", r"\bideas?\b",
    40	                     r"alternatives", r"what could we", r"多个角度", r"头脑风暴"]),
    41	    ("debate",      [r"\bdebate\b", r"\badversarial\b", r"steelman",
    42	                     r"for and against", r"pros and cons", r"辩论"]),
    43	    ("research",    [r"find papers", r"search the web",
    44	                     r"who (first )?(said|wrote|proved|discovered|showed|claimed|invented)",
    45	                     r"\bcite\b", r"references", r"prior work"]),
    46	    ("code-write",  [r"\bwrite\b", r"\bimplement\b", r"\badd\b",
    47	                     r"\brefactor\b", r"fix the function", r"修改", r"实现"]),
    48	]
    49	
    50	
    51	def classify(prompt: str) -> tuple[str, str]:
    52	    lower = prompt.lower()
    53	    for cls, patterns in KEYWORDS:
    54	        for p in patterns:
    55	            m = re.search(p, lower)
    56	            if m:
    57	                return cls, f"matched /{p}/"
    58	    return "quick-qa", "no keyword matched"
    59	
    60	
    61	def _select_agents(task_class: str, host: str, available: dict[str, bool],
    62	                   mode: str) -> tuple[list[str], dict[str, str], str, list[str]]:
    63	    """Returns (agents, agent_modes, synthesis_method, escalations)."""
    64	    escalations: list[str] = []
    65	    cls = TASK_CLASSES[task_class]
    66	    primary = cls["primary"]
    67	    synthesis = cls["synthesis"]
    68	
    69	    if mode.startswith("single:"):
    70	        only = mode.split(":", 1)[1]
    71	        if only not in available:
    72	            escalations.append(f"unknown agent '{only}'")
    73	            return [], {}, "inline", escalations
    74	        if only != host and not available.get(only, False):
    75	            escalations.append(f"requested agent '{only}' unavailable")
    76	            return [], {}, "inline", escalations
    77	        return ([only],
    78	                {only: "inline" if only == host else "subprocess"},
    79	                "inline",
    80	                escalations)
    81	
    82	    if mode == "multi":
    83	        agents = [a for a in ("claude", "codex", "opencode") if available.get(a, False)]
    84	        modes = {a: "inline" if a == host else "subprocess" for a in agents}
    85	        return agents, modes, "meta-synth" if len(agents) > 1 else "inline", escalations
    86	
    87	    # mode == "auto" (or anything else): use matrix
    88	    if primary == ["__host__"]:
    89	        return [host], {host: "inline"}, "inline", escalations
    90	
    91	    if task_class in ("idea", "debate"):
    92	        # fan out to all three available
    93	        agents = [a for a in primary if available.get(a, False)]
    94	        if host not in agents and available.get(host, False):
    95	            agents.insert(0, host)
    96	        modes = {a: "inline" if a == host else "subprocess" for a in agents}
    97	        return agents, modes, synthesis if len(agents) > 1 else "inline", escalations
    98	
    99	    # single-agent classes: pick the highest-priority *available* agent
   100	    chosen = None
   101	    for a in primary:
   102	        if a == host:
   103	            chosen = host
   104	            break
   105	        if available.get(a, False):
   106	            chosen = a
   107	            break
   108	    if chosen is None:
   109	        escalations.append(f"no agent available for class={task_class}")
   110	        return [], {}, "inline", escalations
   111	    if chosen != primary[0]:
   112	        escalations.append(
   113	            f"primary agent '{primary[0]}' unavailable; fallback to '{chosen}' "
   114	            "needs user confirmation (integrity rule #1: no silent agent swap)"
   115	        )
   116	    return ([chosen],
   117	            {chosen: "inline" if chosen == host else "subprocess"},
   118	            "inline",
   119	            escalations)
   120	
   121	
   122	def run_stage1(run_dir: Path) -> dict:
   123	    P.check_sentinels(run_dir)
   124	    P.write_heartbeat(run_dir, stage=1, step="classify")
   125	
   126	    task = yaml_io.load_path(run_dir / "task.yaml")
   127	    prompt = task.get("prompt", "")
   128	    host = task["host"]
   129	    mode = task.get("mode", "auto")
   130	    available = task.get("workers_available", {})
   131	    per_call_cap = float(task.get("per_call_cap_usd", 0.50))
   132	
   133	    task_class, reason = classify(prompt)
   134	    P.append_progress(run_dir, stage=1, step="classify", status="ok",
   135	                      detail=f"{task_class} ({reason})")
   136	
   137	    P.write_heartbeat(run_dir, stage=1, step="select_agents")
   138	    agents, agent_modes, synthesis, escalations = _select_agents(
   139	        task_class, host, available, mode,
   140	    )
   141	
   142	    cost_estimate = sum(
   143	        COST_ESTIMATE_USD.get(a, 0.0)
   144	        for a, m in agent_modes.items() if m == "subprocess"
   145	    )
   146	    if cost_estimate > per_call_cap * len(
   147	        [m for m in agent_modes.values() if m == "subprocess"] or [1]
   148	    ):
   149	        escalations.append(
   150	            f"estimated cost ${cost_estimate:.2f} exceeds per-call cap "
   151	            f"${per_call_cap:.2f}"
   152	        )
   153	
   154	    route = {
   155	        "task_class": task_class,
   156	        "classification_reason": reason,
   157	        "agents": agents,
   158	        "agent_modes": agent_modes,
   159	        "synthesis_method": synthesis,
   160	        "cost_estimate_usd": round(cost_estimate, 4),
   161	        "inline_host_used": agent_modes.get(host) == "inline",
   162	        "escalations": escalations,
   163	    }
   164	    P.atomic_write_json(run_dir / "route.json", route)
   165	    P.append_progress(
   166	        run_dir, stage=1, step="select_agents",
   167	        status="needs-user" if escalations else "ok",
   168	        detail=" | ".join(escalations) if escalations
   169	               else f"{agents} synth={synthesis}",
   170	    )
   171	    return route
   172	
   173	
   174	def main(argv: list[str] | None = None) -> int:
   175	    ap = argparse.ArgumentParser()
   176	    ap.add_argument("--run-dir", required=True, type=Path)
   177	    args = ap.parse_args(argv)
   178	    route = run_stage1(args.run_dir)
   179	    print(json.dumps(route, indent=2, ensure_ascii=False))
   180	    return 1 if route.get("escalations") else 0
   181	
   182	
   183	if __name__ == "__main__":
   184	    sys.exit(main())

exec
/bin/zsh -lc 'nl -ba auto-agents/assets/synthesize.py' in /Volumes/ORICO/code/code6/auto-agents
 succeeded in 0ms:
     1	"""Stage 3 — merge agent outputs into synthesis/final.md.
     2	
     3	Three methods:
     4	  - inline      : 1 successful agent → copy result + contributors block
     5	  - vote        : majority on the first-line label across agents
     6	  - meta-synth  : host-written unified answer with attribution (DEFAULT for idea)
     7	  - debate      : two-round structured (this script writes round 1 + round 2
     8	                  invocations and the moderator template; the host fills in the
     9	                  final synthesis paragraph)
    10	
    11	The host model is responsible for the actual *writing* in meta-synth and the
    12	debate moderator pass — this script prepares the inputs (concatenated worker
    13	outputs, prompts), and validates the output. Vote is fully automated.
    14	"""
    15	from __future__ import annotations
    16	
    17	import argparse
    18	import json
    19	import re
    20	import sys
    21	from collections import Counter
    22	from pathlib import Path
    23	
    24	import progress as P
    25	
    26	
    27	def _read_route(run_dir: Path) -> dict:
    28	    return json.loads((run_dir / "route.json").read_text(encoding="utf-8"))
    29	
    30	
    31	def _read_agent_result(run_dir: Path, agent: str) -> tuple[str | None, str]:
    32	    """Returns (status, result_text). status comes from meta.json."""
    33	    agent_dir = run_dir / "agents" / agent
    34	    meta_path = agent_dir / "meta.json"
    35	    if not meta_path.exists():
    36	        return None, ""
    37	    try:
    38	        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    39	    except json.JSONDecodeError:
    40	        return None, ""
    41	    status = meta.get("status")
    42	    result_path = agent_dir / "result.md"
    43	    text = result_path.read_text(encoding="utf-8") if result_path.exists() else ""
    44	    return status, text
    45	
    46	
    47	def _audit_totals(run_dir: Path) -> tuple[float, float]:
    48	    """Returns (total_duration_s, total_cost_actual_usd) from audit.jsonl."""
    49	    audit = run_dir / "audit.jsonl"
    50	    if not audit.exists():
    51	        return 0.0, 0.0
    52	    dur = 0.0
    53	    cost = 0.0
    54	    for line in audit.read_text(encoding="utf-8").splitlines():
    55	        try:
    56	            row = json.loads(line)
    57	        except json.JSONDecodeError:
    58	            continue
    59	        dur += float(row.get("duration_s") or 0)
    60	        cost += float(row.get("cost_actual_usd") or 0)
    61	    return dur, cost
    62	
    63	
    64	def _contributors_block(run_dir: Path, agents: list[str]) -> str:
    65	    lines = ["## Contributors", ""]
    66	    for a in agents:
    67	        status, text = _read_agent_result(run_dir, a)
    68	        if status == "ok":
    69	            sample = text.strip().splitlines()[0] if text.strip() else ""
    70	            lines.append(f"- **{a}** — see `agents/{a}/result.md` "
    71	                         f"{'(opening: ' + sample[:80] + '…)' if sample else ''}")
    72	        elif status == "pending":
    73	            lines.append(f"- **{a}** — *pending* (host inline; result.md not yet written)")
    74	        else:
    75	            lines.append(f"- **{a}** — *failed* (status={status})")
    76	    return "\n".join(lines) + "\n"
    77	
    78	
    79	def _audit_block(run_dir: Path) -> str:
    80	    dur, cost = _audit_totals(run_dir)
    81	    return (
    82	        "## Audit\n\n"
    83	        f"- Total subprocess time: {dur:.1f}s\n"
    84	        f"- Total subprocess cost (recorded): ${cost:.4f}\n"
    85	        "- Per-call breakdown: `audit.jsonl`\n"
    86	    )
    87	
    88	
    89	def _write_method_md(run_dir: Path, method: str, note: str = "") -> None:
    90	    body = f"# Synthesis method: {method}\n\n{note}\n"
    91	    P.atomic_write_text(run_dir / "synthesis" / "method.md", body)
    92	
    93	
    94	# --- inline -------------------------------------------------------------------
    95	def synth_inline(run_dir: Path, route: dict) -> str:
    96	    agents = route["agents"]
    97	    assert len(agents) == 1, "inline synthesis expects exactly one agent"
    98	    a = agents[0]
    99	    status, text = _read_agent_result(run_dir, a)
   100	    if status != "ok":
   101	        return ("# Answer\n\n"
   102	                f"_The sole agent `{a}` did not complete successfully "
   103	                f"(status={status}). No answer to report._\n\n"
   104	                + _contributors_block(run_dir, agents)
   105	                + "\n## Synthesis method: inline (failed)\n\n"
   106	                + _audit_block(run_dir))
   107	    return (
   108	        "# Answer\n\n"
   109	        + text.rstrip() + "\n\n---\n\n"
   110	        + _contributors_block(run_dir, agents)
   111	        + "\n## Synthesis method: inline\n\n"
   112	        + f"Single agent `{a}` answered directly; no merge needed.\n\n"
   113	        + _audit_block(run_dir)
   114	    )
   115	
   116	
   117	# --- vote ---------------------------------------------------------------------
   118	def _normalize_label(s: str) -> str:
   119	    return re.sub(r"[^\w\-]+", "", s.strip().lower())
   120	
   121	
   122	def synth_vote(run_dir: Path, route: dict) -> tuple[str, dict]:
   123	    """Tally labels (first non-empty line of each result.md). Returns (final_md, tally_dict)."""
   124	    labels: dict[str, str] = {}
   125	    justifs: dict[str, str] = {}
   126	    for a in route["agents"]:
   127	        status, text = _read_agent_result(run_dir, a)
   128	        if status != "ok" or not text.strip():
   129	            labels[a] = "__failed__"
   130	            justifs[a] = ""
   131	            continue
   132	        lines = [ln for ln in text.splitlines() if ln.strip()]
   133	        labels[a] = lines[0].strip() if lines else "__empty__"
   134	        justifs[a] = lines[1].strip() if len(lines) > 1 else ""
   135	    normed = {a: _normalize_label(v) for a, v in labels.items()
   136	              if v not in ("__failed__", "__empty__")}
   137	    tally = Counter(normed.values())
   138	    if not tally:
   139	        return ("# Answer\n\n_All agents failed to produce a labeled answer._\n\n"
   140	                + _contributors_block(run_dir, route["agents"])
   141	                + "\n## Synthesis method: vote (no valid ballots)\n\n"
   142	                + _audit_block(run_dir)), {"tally": {}, "winner": None}
   143	    winner_norm, winner_count = tally.most_common(1)[0]
   144	    n_valid = sum(tally.values())
   145	    majority = winner_count > n_valid // 2
   146	    # find one original-cased label that matches
   147	    winner_label = next(v for a, v in labels.items()
   148	                        if _normalize_label(v) == winner_norm)
   149	    final = (
   150	        "# Answer\n\n"
   151	        f"**{winner_label}**"
   152	        + (" *(majority)*" if majority else " *(plurality — NO majority — see escalation)*")
   153	        + "\n\n## Justifications\n\n"
   154	        + "\n".join(f"- **{a}** → {labels[a]!r}: {justifs[a] or '(none provided)'}"
   155	                    for a in route["agents"])
   156	        + "\n\n---\n\n"
   157	        + _contributors_block(run_dir, route["agents"])
   158	        + "\n## Synthesis method: vote\n\n"
   159	        + f"Tally: {dict(tally)}; winner={winner_label!r}; majority={majority}.\n\n"
   160	        + _audit_block(run_dir)
   161	    )
   162	    return final, {"labels": labels, "tally": dict(tally),
   163	                   "winner": winner_label, "majority": majority}
   164	
   165	
   166	# --- meta-synth ---------------------------------------------------------------
   167	META_SYNTH_HOST_INSTRUCTIONS = """\
   168	# Host instructions: meta-synth
   169	
   170	The file `synthesis/intermediate/meta-synth-input.md` contains every worker
   171	output, separated by `--- <agent> ---` markers.
   172	
   173	Write `synthesis/final.md` with this structure:
   174	
   175	  # Answer
   176	  <one unified answer that weaves together the workers' ideas.>
   177	  <Inline-attribute: when a sentence comes from one agent specifically,
   178	   name that agent in the sentence or in a trailing parenthetical.>
   179	
   180	  ---
   181	
   182	  ## Contributors
   183	  - one bullet per agent naming what they contributed
   184	  - mark any failed agent as failed
   185	
   186	  ## Synthesis method: meta-synth
   187	  <one paragraph: what overlapped, what conflicted, how you resolved>
   188	
   189	  ## Audit
   190	  (will be auto-appended; you can leave a placeholder)
   191	
   192	Do NOT paraphrase an agent's output as your own. Do NOT include claims that
   193	no worker output backs.
   194	"""
   195	
   196	
   197	def synth_meta_prepare(run_dir: Path, route: dict) -> str:
   198	    """Build meta-synth-input.md and write host instructions. Returns the inputs
   199	    path so the host can read it. The host then writes final.md itself."""
   200	    inter = run_dir / "synthesis" / "intermediate"
   201	    inter.mkdir(parents=True, exist_ok=True)
   202	    parts: list[str] = []
   203	    for a in route["agents"]:
   204	        status, text = _read_agent_result(run_dir, a)
   205	        if status == "ok" and text.strip():
   206	            parts.append(f"--- {a} ---\n{text.rstrip()}\n")
   207	        else:
   208	            parts.append(f"--- {a} ---\n(no output; status={status})\n")
   209	    P.atomic_write_text(inter / "meta-synth-input.md", "\n".join(parts))
   210	    P.atomic_write_text(inter / "host-instructions.md",
   211	                        META_SYNTH_HOST_INSTRUCTIONS)
   212	    return str(inter / "meta-synth-input.md")
   213	
   214	
   215	# --- debate -------------------------------------------------------------------
   216	DEBATE_ROUND1_SUFFIX = (
   217	    "\n\n---\nState your position in ≤300 words. "
   218	    "Lead with a one-sentence claim. Cite your reasoning explicitly. Do not hedge."
   219	)
   220	DEBATE_ROUND2_PREFIX = (
   221	    "Here are the opening positions from the other agents:\n\n"
   222	)
   223	DEBATE_ROUND2_SUFFIX = (
   224	    "\n\nCritique their reasoning. Restate or revise your own position in ≤300 words. "
   225	    "Lead with 'I agree with <X> on <Y>, but disagree on <Z>' if applicable; "
   226	    "otherwise lead with a one-sentence revised claim."
   227	)
   228	
   229	
   230	def synth_debate_prepare(run_dir: Path, route: dict) -> dict:
   231	    """Materialize round-1 inputs and round-2 prompts. The dispatch loop must
   232	    re-run dispatch.py twice for debate (one per round). This script's job is
   233	    only to *prepare* and *validate*."""
   234	    inter = run_dir / "synthesis" / "intermediate"
   235	    inter.mkdir(parents=True, exist_ok=True)
   236	    round1_concat = []
   237	    for a in route["agents"]:
   238	        status, text = _read_agent_result(run_dir, a)
   239	        if status == "ok" and text.strip():
   240	            round1_concat.append(f"--- {a} ---\n{text.rstrip()}\n")
   241	        else:
   242	            round1_concat.append(f"--- {a} ---\n(no output; status={status})\n")
   243	    P.atomic_write_text(inter / "debate-round-1.md", "\n".join(round1_concat))
   244	    return {
   245	        "round1_concat_path": str(inter / "debate-round-1.md"),
   246	        "round1_suffix": DEBATE_ROUND1_SUFFIX,
   247	        "round2_prefix": DEBATE_ROUND2_PREFIX,
   248	        "round2_suffix": DEBATE_ROUND2_SUFFIX,
   249	        "next_step": "host runs dispatch.py round 2 with augmented prompts, "
   250	                     "then re-invokes synthesize.py",
   251	    }
   252	
   253	
   254	# --- top-level ----------------------------------------------------------------
   255	def run_stage3(run_dir: Path) -> dict:
   256	    P.check_sentinels(run_dir)
   257	    route = _read_route(run_dir)
   258	    method = route.get("synthesis_method", "inline")
   259	    (run_dir / "synthesis").mkdir(parents=True, exist_ok=True)
   260	    P.write_heartbeat(run_dir, stage=3, step=f"synth:{method}")
   261	
   262	    if method == "inline":
   263	        final = synth_inline(run_dir, route)
   264	        _write_method_md(run_dir, "inline", "Single agent; no merge.")
   265	        P.atomic_write_text(run_dir / "synthesis" / "final.md", final)
   266	        P.append_progress(run_dir, stage=3, step="synth:inline", status="ok")
   267	        return {"status": "ok", "method": "inline"}
   268	
   269	    if method == "vote":
   270	        final, tally = synth_vote(run_dir, route)
   271	        _write_method_md(run_dir, "vote",
   272	                         f"Tally: `synthesis/intermediate/vote-tally.json`")
   273	        P.atomic_write_json(run_dir / "synthesis" / "intermediate" /
   274	                            "vote-tally.json", tally)
   275	        P.atomic_write_text(run_dir / "synthesis" / "final.md", final)
   276	        P.append_progress(run_dir, stage=3, step="synth:vote",
   277	                          status="ok" if tally.get("majority") else "needs-user",
   278	                          detail=f"winner={tally.get('winner')}")
   279	        return {"status": "ok", "method": "vote", "tally": tally}
   280	
   281	    if method == "meta-synth":
   282	        input_path = synth_meta_prepare(run_dir, route)
   283	        _write_method_md(run_dir, "meta-synth",
   284	                         f"Host should read `{input_path}` and write final.md.")
   285	        P.append_progress(run_dir, stage=3, step="synth:meta-synth",
   286	                          status="pending-host",
   287	                          detail="meta-synth-input.md ready; host writes final.md")
   288	        return {"status": "pending-host", "method": "meta-synth",
   289	                "input_path": input_path}
   290	
   291	    if method == "debate":
   292	        prep = synth_debate_prepare(run_dir, route)
   293	        _write_method_md(run_dir, "debate",
   294	                         "Round-2 prompts prepared; re-run dispatch then synthesize.")
   295	        P.append_progress(run_dir, stage=3, step="synth:debate",
   296	                          status="pending-round2", detail=prep["next_step"])
   297	        return {"status": "pending-round2", "method": "debate", **prep}
   298	
   299	    P.append_progress(run_dir, stage=3, step=f"synth:{method}",
   300	                      status="failed", detail="unknown synthesis method")
   301	    return {"status": "failed", "method": method, "reason": "unknown method"}
   302	
   303	
   304	def main(argv: list[str] | None = None) -> int:
   305	    ap = argparse.ArgumentParser()
   306	    ap.add_argument("--run-dir", required=True, type=Path)
   307	    args = ap.parse_args(argv)
   308	    out = run_stage3(args.run_dir)
   309	    print(json.dumps(out, indent=2, ensure_ascii=False))
   310	    return 0 if out.get("status") in ("ok", "pending-host", "pending-round2") else 1
   311	
   312	
   313	if __name__ == "__main__":
   314	    sys.exit(main())

exec
/bin/zsh -lc 'nl -ba auto-agents/assets/budget.py' in /Volumes/ORICO/code/code6/auto-agents
 succeeded in 0ms:
     1	"""Cost gate + audit reconciliation.
     2	
     3	Sums actual costs from audit.jsonl, compares against the caps in task.yaml,
     4	returns a decision dict the caller (route.py / dispatch.py) consumes before
     5	making a worker call.
     6	
     7	Cost is reported in agents' meta.json — *if* the CLI prints token counts the
     8	wrapper can parse. Most wrappers don't (yet); the actual numbers may be None.
     9	That means budget gating is best-effort on *estimates* and only catches real
    10	overruns post-hoc when actuals exist.
    11	"""
    12	from __future__ import annotations
    13	
    14	import argparse
    15	import json
    16	import sys
    17	from pathlib import Path
    18	
    19	
    20	def _read_yaml_floats(task_path: Path) -> tuple[float, float]:
    21	    """Extract per_call_cap_usd and total_cap_usd from task.yaml."""
    22	    per_call = 0.50
    23	    total = 2.00
    24	    for line in task_path.read_text(encoding="utf-8").splitlines():
    25	        if line.startswith("per_call_cap_usd:"):
    26	            try:
    27	                per_call = float(line.split(":", 1)[1].strip())
    28	            except (ValueError, IndexError):
    29	                pass
    30	        elif line.startswith("total_cap_usd:"):
    31	            try:
    32	                total = float(line.split(":", 1)[1].strip())
    33	            except (ValueError, IndexError):
    34	                pass
    35	    return per_call, total
    36	
    37	
    38	def total_spent(run_dir: Path) -> float:
    39	    audit = run_dir / "audit.jsonl"
    40	    if not audit.exists():
    41	        return 0.0
    42	    total = 0.0
    43	    for line in audit.read_text(encoding="utf-8").splitlines():
    44	        try:
    45	            row = json.loads(line)
    46	        except json.JSONDecodeError:
    47	            continue
    48	        v = row.get("cost_actual_usd")
    49	        if v is not None:
    50	            total += float(v)
    51	    return total
    52	
    53	
    54	def gate(run_dir: Path, *, estimated_next_call_usd: float) -> dict:
    55	    per_call, total_cap = _read_yaml_floats(run_dir / "task.yaml")
    56	    spent = total_spent(run_dir)
    57	    decision = {
    58	        "spent_so_far_usd": round(spent, 4),
    59	        "estimated_next_call_usd": round(estimated_next_call_usd, 4),
    60	        "per_call_cap_usd": per_call,
    61	        "total_cap_usd": total_cap,
    62	        "ok": True,
    63	        "reasons": [],
    64	    }
    65	    if estimated_next_call_usd > per_call:
    66	        decision["ok"] = False
    67	        decision["reasons"].append(
    68	            f"estimated ${estimated_next_call_usd:.2f} > per-call cap ${per_call:.2f}"
    69	        )
    70	    if spent + estimated_next_call_usd > total_cap:
    71	        decision["ok"] = False
    72	        decision["reasons"].append(
    73	            f"spent ${spent:.2f} + est ${estimated_next_call_usd:.2f} > total cap ${total_cap:.2f}"
    74	        )
    75	    return decision
    76	
    77	
    78	def reconcile(run_dir: Path) -> dict:
    79	    """Compare per-agent estimates (cost_est_usd in meta.json) against actuals
    80	    in audit.jsonl. Returns a summary; flags agents whose actuals exceed
    81	    estimate by >2× as 'estimate-stale'."""
    82	    agents_dir = run_dir / "agents"
    83	    if not agents_dir.exists():
    84	        return {"agents": {}, "stale": []}
    85	    summary: dict[str, dict] = {}
    86	    stale: list[str] = []
    87	    for sub in agents_dir.iterdir():
    88	        if not sub.is_dir():
    89	            continue
    90	        meta_p = sub / "meta.json"
    91	        if not meta_p.exists():
    92	            continue
    93	        try:
    94	            meta = json.loads(meta_p.read_text(encoding="utf-8"))
    95	        except json.JSONDecodeError:
    96	            continue
    97	        est = meta.get("cost_est_usd")
    98	        act = meta.get("cost_actual_usd")
    99	        summary[sub.name] = {"est": est, "actual": act}
   100	        if est and act and act > 2 * est:
   101	            stale.append(sub.name)
   102	    return {"agents": summary, "stale": stale}
   103	
   104	
   105	def main(argv: list[str] | None = None) -> int:
   106	    ap = argparse.ArgumentParser()
   107	    ap.add_argument("--run-dir", required=True, type=Path)
   108	    ap.add_argument("--estimated-next-call-usd", type=float, default=0.0)
   109	    ap.add_argument("--reconcile", action="store_true")
   110	    args = ap.parse_args(argv)
   111	    if args.reconcile:
   112	        print(json.dumps(reconcile(args.run_dir), indent=2))
   113	    else:
   114	        decision = gate(args.run_dir, estimated_next_call_usd=args.estimated_next_call_usd)
   115	        print(json.dumps(decision, indent=2))
   116	        return 0 if decision["ok"] else 2
   117	    return 0
   118	
   119	
   120	if __name__ == "__main__":
   121	    sys.exit(main())

exec
/bin/zsh -lc 'nl -ba auto-agents/assets/progress.py' in /Volumes/ORICO/code/code6/auto-agents
exec
/bin/zsh -lc 'nl -ba auto-agents/assets/yaml_io.py' in /Volumes/ORICO/code/code6/auto-agents
 succeeded in 0ms:
     1	"""Minimal YAML dump/load for the flat task.yaml schema.
     2	
     3	Supports exactly what state-contract.md uses:
     4	  - scalar key: value pairs at top level (str / int / float / bool / null)
     5	  - nested dict (one level) with two-space indent
     6	  - block scalar `key: |` followed by ≥2-space-indented lines
     7	
     8	Not a general YAML parser. Round-trip with our own dump → load is the contract.
     9	"""
    10	from __future__ import annotations
    11	
    12	import json
    13	import re
    14	from pathlib import Path
    15	
    16	
    17	def _dump_scalar(v) -> str:
    18	    if v is None:
    19	        return "null"
    20	    if isinstance(v, bool):
    21	        return "true" if v else "false"
    22	    if isinstance(v, (int, float)):
    23	        return str(v)
    24	    if isinstance(v, str):
    25	        return json.dumps(v, ensure_ascii=False)
    26	    raise TypeError(f"unsupported scalar: {type(v).__name__}")
    27	
    28	
    29	def dump(d: dict) -> str:
    30	    """Serialize a flat dict (one level of nested dict allowed) into our YAML
    31	    subset. Block-scalar (|) is used for multi-line strings or strings > 100
    32	    chars."""
    33	    lines: list[str] = []
    34	    for k, v in d.items():
    35	        if isinstance(v, dict):
    36	            lines.append(f"{k}:")
    37	            for sk, sv in v.items():
    38	                lines.append(f"  {sk}: {_dump_scalar(sv)}")
    39	        elif isinstance(v, str) and ("\n" in v or len(v) > 100):
    40	            lines.append(f"{k}: |")
    41	            for line in v.splitlines():
    42	                lines.append(f"  {line}")
    43	        else:
    44	            lines.append(f"{k}: {_dump_scalar(v)}")
    45	    return "\n".join(lines) + "\n"
    46	
    47	
    48	def _parse_scalar(s: str):
    49	    s = s.strip()
    50	    if s == "" or s == "~" or s == "null":
    51	        return None
    52	    low = s.lower()
    53	    if low == "true":
    54	        return True
    55	    if low == "false":
    56	        return False
    57	    # JSON handles quoted strings, ints, floats, true/false (lowercase)
    58	    try:
    59	        return json.loads(s)
    60	    except (json.JSONDecodeError, ValueError):
    61	        return s  # unquoted string
    62	
    63	
    64	def load(text: str) -> dict:
    65	    """Parse our YAML subset. Round-trips with dump()."""
    66	    data: dict = {}
    67	    current_dict_key: str | None = None
    68	    block_key: str | None = None
    69	    block_lines: list[str] = []
    70	    block_indent: int | None = None
    71	
    72	    def _flush_block():
    73	        nonlocal block_key, block_lines, block_indent
    74	        if block_key is not None:
    75	            data[block_key] = "\n".join(block_lines).rstrip("\n")
    76	            block_key = None
    77	            block_lines = []
    78	            block_indent = None
    79	
    80	    for raw in text.splitlines():
    81	        # block-scalar accumulation
    82	        if block_key is not None:
    83	            if raw.strip() == "":
    84	                block_lines.append("")
    85	                continue
    86	            indent = len(raw) - len(raw.lstrip(" "))
    87	            if block_indent is None:
    88	                # first non-empty line establishes indent
    89	                block_indent = indent
    90	            if indent >= block_indent and indent > 0:
    91	                block_lines.append(raw[block_indent:])
    92	                continue
    93	            else:
    94	                _flush_block()
    95	                # fall through to process this line as a fresh key
    96	
    97	        if not raw.strip() or raw.lstrip().startswith("#"):
    98	            continue
    99	
   100	        # nested dict entry?
   101	        if raw.startswith("  ") and current_dict_key is not None:
   102	            sk, _, sv = raw.strip().partition(":")
   103	            data[current_dict_key][sk.strip()] = _parse_scalar(sv)
   104	            continue
   105	
   106	        # top-level entry
   107	        k, _, v = raw.partition(":")
   108	        k = k.strip()
   109	        v = v.strip()
   110	        if v == "|":
   111	            block_key = k
   112	            block_lines = []
   113	            block_indent = None
   114	            current_dict_key = None
   115	            continue
   116	        if v == "":
   117	            data[k] = {}
   118	            current_dict_key = k
   119	            continue
   120	        current_dict_key = None
   121	        data[k] = _parse_scalar(v)
   122	
   123	    _flush_block()
   124	    return data
   125	
   126	
   127	# Convenience wrappers
   128	def dump_path(path: Path, d: dict) -> None:
   129	    path.write_text(dump(d), encoding="utf-8")
   130	
   131	
   132	def load_path(path: Path) -> dict:
   133	    return load(path.read_text(encoding="utf-8"))

 succeeded in 0ms:
     1	"""Append-only progress + audit logging, atomic state writes, sentinel checks.
     2	
     3	Every helper in this skill imports from here. The schema is in
     4	../references/state-contract.md — keep that file in sync if you change keys.
     5	"""
     6	from __future__ import annotations
     7	
     8	import json
     9	import os
    10	import time
    11	from pathlib import Path
    12	
    13	
    14	def utc_now_iso() -> str:
    15	    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    16	
    17	
    18	# --- Append-only logs ---------------------------------------------------------
    19	def append_progress(run_dir: Path, *, stage: int, step: str, status: str,
    20	                    detail: str = "") -> None:
    21	    row = {
    22	        "ts_utc": utc_now_iso(),
    23	        "stage": stage,
    24	        "step": step,
    25	        "status": status,
    26	    }
    27	    if detail:
    28	        row["detail"] = detail
    29	    line = json.dumps(row, ensure_ascii=False) + "\n"
    30	    with open(run_dir / "progress.jsonl", "a", encoding="utf-8") as f:
    31	        f.write(line)
    32	
    33	
    34	def append_audit(run_dir: Path, *, agent: str, attempt: int, exit_code: int,
    35	                 duration_s: float, tokens_in: int | None,
    36	                 tokens_out: int | None, cost_actual_usd: float | None) -> None:
    37	    row = {
    38	        "ts_utc": utc_now_iso(),
    39	        "agent": agent,
    40	        "attempt": attempt,
    41	        "exit_code": exit_code,
    42	        "duration_s": round(duration_s, 3),
    43	        "tokens_in": tokens_in,
    44	        "tokens_out": tokens_out,
    45	        "cost_actual_usd": cost_actual_usd,
    46	    }
    47	    line = json.dumps(row, ensure_ascii=False) + "\n"
    48	    with open(run_dir / "audit.jsonl", "a", encoding="utf-8") as f:
    49	        f.write(line)
    50	
    51	
    52	# --- Atomic writes ------------------------------------------------------------
    53	def atomic_write_text(path: Path, content: str) -> None:
    54	    tmp = path.with_suffix(path.suffix + ".tmp")
    55	    tmp.write_text(content, encoding="utf-8")
    56	    os.replace(tmp, path)
    57	
    58	
    59	def atomic_write_json(path: Path, obj) -> None:
    60	    atomic_write_text(path, json.dumps(obj, ensure_ascii=False, indent=2))
    61	
    62	
    63	def write_heartbeat(run_dir: Path, *, stage: int, step: str) -> None:
    64	    body = (
    65	        f"stage: {stage}\n"
    66	        f"step: {step}\n"
    67	        f"pid: {os.getpid()}\n"
    68	        f"ts_utc: {utc_now_iso()}\n"
    69	    )
    70	    atomic_write_text(run_dir / ".heartbeat", body)
    71	
    72	
    73	# --- Sentinel checks ----------------------------------------------------------
    74	class StopRequested(Exception):
    75	    """Raised when runs/<task_id>/STOP is found at micro-step boundary."""
    76	
    77	
    78	def check_sentinels(run_dir: Path) -> None:
    79	    """Raise StopRequested if STOP is present; sleep-and-retry on PAUSE;
    80	    sleep until wait_until.txt timestamp if present. Called at the top of
    81	    every micro-step."""
    82	    stop = run_dir / "STOP"
    83	    if stop.exists():
    84	        raise StopRequested(f"STOP sentinel at {stop}")
    85	    pause = run_dir / "PAUSE"
    86	    while pause.exists():
    87	        time.sleep(30)
    88	    wait = run_dir / "wait_until.txt"
    89	    if wait.exists():
    90	        try:
    91	            target = wait.read_text().strip().rstrip("Z")
    92	            t = time.strptime(target, "%Y-%m-%dT%H:%M:%S")
    93	            target_epoch = time.mktime(t) - time.timezone
    94	            now = time.time()
    95	            if target_epoch > now:
    96	                # Sleep in 60s chunks so STOP can still interrupt.
    97	                while time.time() < target_epoch:
    98	                    if stop.exists():
    99	                        raise StopRequested(f"STOP during wait_until at {stop}")
   100	                    time.sleep(min(60, max(1, target_epoch - time.time())))
   101	            # one-shot: remove the wait file after the wait elapses
   102	            try:
   103	                wait.unlink()
   104	            except OSError:
   105	                pass
   106	        except ValueError:
   107	            # malformed wait_until — ignore (log left to caller)
   108	            pass
   109	
   110	
   111	# --- Resume helpers -----------------------------------------------------------
   112	def progress_tail(run_dir: Path, n: int = 50) -> list[dict]:
   113	    p = run_dir / "progress.jsonl"
   114	    if not p.exists():
   115	        return []
   116	    lines = p.read_text(encoding="utf-8").splitlines()[-n:]
   117	    out = []
   118	    for line in lines:
   119	        try:
   120	            out.append(json.loads(line))
   121	        except json.JSONDecodeError:
   122	            continue
   123	    return out
   124	
   125	
   126	def last_completed_step(run_dir: Path) -> tuple[int, str] | None:
   127	    """Return (stage, step) of the last 'ok' row, or None."""
   128	    for row in reversed(progress_tail(run_dir, n=500)):
   129	        if row.get("status") == "ok":
   130	            return row.get("stage", 0), row.get("step", "")
   131	    return None

exec
/bin/zsh -lc 'nl -ba auto-agents/assets/invoke_codex.py' in /Volumes/ORICO/code/code6/auto-agents
exec
/bin/zsh -lc 'nl -ba auto-agents/assets/invoke_opencode.py' in /Volumes/ORICO/code/code6/auto-agents
 succeeded in 0ms:
     1	"""Subprocess wrapper for the `codex` (OpenAI Codex) CLI.
     2	
     3	Known-good invocation pattern: `codex exec "<prompt>"`. Override with
     4	AUTO_AGENTS_CODEX_CMD if your install differs (the env value is shell-split
     5	and the prompt is appended as the last positional argument).
     6	
     7	Does NOT try alternate flags on failure — per integrity rule #5.
     8	"""
     9	from __future__ import annotations
    10	
    11	import os
    12	import shlex
    13	import subprocess
    14	import time
    15	
    16	DEFAULT_CMD = "codex exec"
    17	DEFAULT_TIMEOUT_SEC = 600
    18	VERSION_TIMEOUT_SEC = 10
    19	
    20	
    21	def _resolved_cmd() -> list[str]:
    22	    raw = os.environ.get("AUTO_AGENTS_CODEX_CMD", DEFAULT_CMD)
    23	    return shlex.split(raw)
    24	
    25	
    26	def version_check() -> tuple[bool, str]:
    27	    cmd_head = _resolved_cmd()[0]
    28	    try:
    29	        out = subprocess.run(
    30	            [cmd_head, "--version"],
    31	            capture_output=True, text=True,
    32	            timeout=VERSION_TIMEOUT_SEC,
    33	        )
    34	        if out.returncode == 0:
    35	            return True, (out.stdout or out.stderr).strip().splitlines()[0]
    36	        return False, f"exit={out.returncode} stderr={out.stderr[:200]}"
    37	    except FileNotFoundError:
    38	        return False, "binary-missing"
    39	    except subprocess.TimeoutExpired:
    40	        return False, "version-timeout"
    41	
    42	
    43	def invoke(prompt: str, *, env_overrides: dict | None = None,
    44	           timeout_sec: int = DEFAULT_TIMEOUT_SEC) -> dict:
    45	    argv = _resolved_cmd() + [prompt]
    46	    env = os.environ.copy()
    47	    if env_overrides:
    48	        env.update(env_overrides)
    49	    started = time.time()
    50	    ts_started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started))
    51	    try:
    52	        proc = subprocess.run(
    53	            argv, capture_output=True, text=True,
    54	            timeout=timeout_sec, env=env,
    55	        )
    56	        exit_code = proc.returncode
    57	        stdout, stderr = proc.stdout, proc.stderr
    58	    except subprocess.TimeoutExpired as e:
    59	        exit_code = 124
    60	        stdout = e.stdout.decode("utf-8", "replace") if e.stdout else ""
    61	        stderr = (e.stderr.decode("utf-8", "replace") if e.stderr else "") + \
    62	                 f"\n[auto-agents] killed after {timeout_sec}s"
    63	    ended = time.time()
    64	    return {
    65	        "agent": "codex",
    66	        "exit_code": exit_code,
    67	        "stdout": stdout,
    68	        "stderr": stderr,
    69	        "duration_s": round(ended - started, 3),
    70	        "cmd": " ".join(shlex.quote(a) for a in argv[:-1]) + " <prompt>",
    71	        "ts_started_utc": ts_started,
    72	        "ts_ended_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ended)),
    73	    }
    74	
    75	
    76	def extract_answer(stdout: str) -> str:
    77	    """`codex exec` prints assistant text to stdout; some versions include a
    78	    leading banner line. Drop a leading line that starts with 'codex'."""
    79	    lines = stdout.splitlines()
    80	    if lines and lines[0].lower().startswith("codex"):
    81	        lines = lines[1:]
    82	    return "\n".join(lines).rstrip() + "\n"

 succeeded in 0ms:
     1	"""Subprocess wrapper for the `opencode` (sst/opencode) CLI.
     2	
     3	Known-good invocation pattern: `opencode run "<prompt>"`. Override with
     4	AUTO_AGENTS_OPENCODE_CMD if your install differs (the env value is shell-split
     5	and the prompt is appended as the last positional argument).
     6	
     7	Does NOT try alternate flags on failure — per integrity rule #5.
     8	"""
     9	from __future__ import annotations
    10	
    11	import os
    12	import shlex
    13	import subprocess
    14	import time
    15	
    16	DEFAULT_CMD = "opencode run"
    17	DEFAULT_TIMEOUT_SEC = 600
    18	VERSION_TIMEOUT_SEC = 10
    19	
    20	
    21	def _resolved_cmd() -> list[str]:
    22	    raw = os.environ.get("AUTO_AGENTS_OPENCODE_CMD", DEFAULT_CMD)
    23	    return shlex.split(raw)
    24	
    25	
    26	def version_check() -> tuple[bool, str]:
    27	    cmd_head = _resolved_cmd()[0]
    28	    try:
    29	        out = subprocess.run(
    30	            [cmd_head, "--version"],
    31	            capture_output=True, text=True,
    32	            timeout=VERSION_TIMEOUT_SEC,
    33	        )
    34	        if out.returncode == 0:
    35	            return True, (out.stdout or out.stderr).strip().splitlines()[0]
    36	        return False, f"exit={out.returncode} stderr={out.stderr[:200]}"
    37	    except FileNotFoundError:
    38	        return False, "binary-missing"
    39	    except subprocess.TimeoutExpired:
    40	        return False, "version-timeout"
    41	
    42	
    43	def invoke(prompt: str, *, env_overrides: dict | None = None,
    44	           timeout_sec: int = DEFAULT_TIMEOUT_SEC) -> dict:
    45	    argv = _resolved_cmd() + [prompt]
    46	    env = os.environ.copy()
    47	    if env_overrides:
    48	        env.update(env_overrides)
    49	    started = time.time()
    50	    ts_started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started))
    51	    try:
    52	        proc = subprocess.run(
    53	            argv, capture_output=True, text=True,
    54	            timeout=timeout_sec, env=env,
    55	        )
    56	        exit_code = proc.returncode
    57	        stdout, stderr = proc.stdout, proc.stderr
    58	    except subprocess.TimeoutExpired as e:
    59	        exit_code = 124
    60	        stdout = e.stdout.decode("utf-8", "replace") if e.stdout else ""
    61	        stderr = (e.stderr.decode("utf-8", "replace") if e.stderr else "") + \
    62	                 f"\n[auto-agents] killed after {timeout_sec}s"
    63	    ended = time.time()
    64	    return {
    65	        "agent": "opencode",
    66	        "exit_code": exit_code,
    67	        "stdout": stdout,
    68	        "stderr": stderr,
    69	        "duration_s": round(ended - started, 3),
    70	        "cmd": " ".join(shlex.quote(a) for a in argv[:-1]) + " <prompt>",
    71	        "ts_started_utc": ts_started,
    72	        "ts_ended_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ended)),
    73	    }
    74	
    75	
    76	def extract_answer(stdout: str) -> str:
    77	    """`opencode run` prints assistant text directly. Trim trailing blanks."""
    78	    return stdout.rstrip() + "\n"

exec
/bin/zsh -lc 'nl -ba auto-agents/assets/invoke_claude.py' in /Volumes/ORICO/code/code6/auto-agents
exec
/bin/zsh -lc 'nl -ba auto-agents/assets/supervisor.sh' in /Volumes/ORICO/code/code6/auto-agents
 succeeded in 0ms:
     1	"""Subprocess wrapper for the `claude` (Claude Code) CLI.
     2	
     3	Known-good invocation pattern: `claude -p "<prompt>"`. Override with
     4	AUTO_AGENTS_CLAUDE_CMD if your install differs (the env value is shell-split
     5	and the prompt is appended as the last positional argument).
     6	
     7	Does NOT try alternate flags on failure — per integrity rule #5 (no CLI flag
     8	fabrication). Raw stdout/stderr/exit_code are returned; the caller decides
     9	what to do with errors.
    10	"""
    11	from __future__ import annotations
    12	
    13	import os
    14	import shlex
    15	import subprocess
    16	import time
    17	from pathlib import Path
    18	
    19	DEFAULT_CMD = "claude -p"
    20	DEFAULT_TIMEOUT_SEC = 600  # 10 min cap per call; dispatcher can override
    21	VERSION_TIMEOUT_SEC = 10
    22	
    23	
    24	def _resolved_cmd() -> list[str]:
    25	    raw = os.environ.get("AUTO_AGENTS_CLAUDE_CMD", DEFAULT_CMD)
    26	    return shlex.split(raw)
    27	
    28	
    29	def version_check() -> tuple[bool, str]:
    30	    """Run `claude --version`. Returns (ok, detail)."""
    31	    cmd_head = _resolved_cmd()[0]
    32	    try:
    33	        out = subprocess.run(
    34	            [cmd_head, "--version"],
    35	            capture_output=True, text=True,
    36	            timeout=VERSION_TIMEOUT_SEC,
    37	        )
    38	        if out.returncode == 0:
    39	            return True, (out.stdout or out.stderr).strip().splitlines()[0]
    40	        return False, f"exit={out.returncode} stderr={out.stderr[:200]}"
    41	    except FileNotFoundError:
    42	        return False, "binary-missing"
    43	    except subprocess.TimeoutExpired:
    44	        return False, "version-timeout"
    45	
    46	
    47	def invoke(prompt: str, *, env_overrides: dict | None = None,
    48	           timeout_sec: int = DEFAULT_TIMEOUT_SEC) -> dict:
    49	    """Run claude with the prompt. Returns a result dict with:
    50	        exit_code, stdout, stderr, duration_s, cmd, ts_started, ts_ended.
    51	    Caller is responsible for writing files and parsing/cost-accounting.
    52	    """
    53	    argv = _resolved_cmd() + [prompt]
    54	    env = os.environ.copy()
    55	    if env_overrides:
    56	        env.update(env_overrides)
    57	    started = time.time()
    58	    ts_started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started))
    59	    try:
    60	        proc = subprocess.run(
    61	            argv, capture_output=True, text=True,
    62	            timeout=timeout_sec, env=env,
    63	        )
    64	        exit_code = proc.returncode
    65	        stdout, stderr = proc.stdout, proc.stderr
    66	    except subprocess.TimeoutExpired as e:
    67	        exit_code = 124  # conventional timeout exit
    68	        stdout = e.stdout.decode("utf-8", "replace") if e.stdout else ""
    69	        stderr = (e.stderr.decode("utf-8", "replace") if e.stderr else "") + \
    70	                 f"\n[auto-agents] killed after {timeout_sec}s"
    71	    ended = time.time()
    72	    return {
    73	        "agent": "claude",
    74	        "exit_code": exit_code,
    75	        "stdout": stdout,
    76	        "stderr": stderr,
    77	        "duration_s": round(ended - started, 3),
    78	        "cmd": " ".join(shlex.quote(a) for a in argv[:-1]) + " <prompt>",
    79	        "ts_started_utc": ts_started,
    80	        "ts_ended_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ended)),
    81	    }
    82	
    83	
    84	def extract_answer(stdout: str) -> str:
    85	    """Claude `-p` prints the assistant text directly. Trim trailing blanks."""
    86	    return stdout.rstrip() + "\n"

 succeeded in 0ms:
     1	#!/usr/bin/env bash
     2	# supervisor.sh — keep an auto-agents run alive across crashes.
     3	#
     4	# Usage:
     5	#   ./supervisor.sh runs/<task_id> [--stage N] [--max-restarts 50]
     6	#
     7	# The "skill helper" command is whatever you'd normally run after Stage 0
     8	# (e.g. `python -m route && python -m dispatch && python -m synthesize`).
     9	# This wrapper only adds: restart-on-exit, STOP/PAUSE/wait_until honoring,
    10	# and heartbeat-watchdog kill if the inner loop stalls.
    11	#
    12	# Honors $AUTO_AGENTS_DEPTH (refuses if ≥1 — recursion guard).
    13	# Honors STOP / PAUSE sentinels and wait_until.txt under runs/<task_id>/.
    14	# Sets exit codes: 0=clean, 2=stopped-by-user, 3=recursion-refused,
    15	# 4=max-restarts-exceeded.
    16	
    17	set -euo pipefail
    18	
    19	if [[ "${AUTO_AGENTS_DEPTH:-0}" -ge 1 ]]; then
    20	  echo "[supervisor] refused: AUTO_AGENTS_DEPTH=$AUTO_AGENTS_DEPTH" >&2
    21	  exit 3
    22	fi
    23	
    24	RUN_DIR="${1:-}"
    25	if [[ -z "$RUN_DIR" || ! -d "$RUN_DIR" ]]; then
    26	  echo "Usage: $0 <runs/<task_id>> [--max-restarts N]" >&2
    27	  exit 64
    28	fi
    29	shift || true
    30	
    31	MAX_RESTARTS=50
    32	HEARTBEAT_STALL_SEC=900   # kill inner if heartbeat hasn't moved in 15 min
    33	INNER_TIMEOUT_SEC=3600    # hard cap per inner pass; restart after
    34	
    35	while (( $# > 0 )); do
    36	  case "$1" in
    37	    --max-restarts) MAX_RESTARTS="$2"; shift 2 ;;
    38	    --heartbeat-stall-sec) HEARTBEAT_STALL_SEC="$2"; shift 2 ;;
    39	    --inner-timeout-sec) INNER_TIMEOUT_SEC="$2"; shift 2 ;;
    40	    *) echo "[supervisor] unknown arg: $1" >&2; exit 64 ;;
    41	  esac
    42	done
    43	
    44	STOP="$RUN_DIR/STOP"
    45	PAUSE="$RUN_DIR/PAUSE"
    46	WAIT_UNTIL="$RUN_DIR/wait_until.txt"
    47	HEARTBEAT="$RUN_DIR/.heartbeat"
    48	
    49	# Where the skill scripts live — derive from this script's location.
    50	SKILL_ASSETS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    51	
    52	log() { echo "[supervisor $(date -u +%FT%TZ)] $*"; }
    53	
    54	check_sentinels() {
    55	  if [[ -f "$STOP" ]]; then
    56	    log "STOP sentinel present; exiting."
    57	    return 2
    58	  fi
    59	  while [[ -f "$PAUSE" ]]; do
    60	    log "PAUSE sentinel present; sleeping 30s."
    61	    sleep 30
    62	    if [[ -f "$STOP" ]]; then return 2; fi
    63	  done
    64	  if [[ -f "$WAIT_UNTIL" ]]; then
    65	    target=$(cat "$WAIT_UNTIL" | tr -d 'Z' | head -n1)
    66	    # try GNU date first, then BSD
    67	    target_epoch=$(date -u -d "$target" +%s 2>/dev/null \
    68	                   || date -u -j -f "%Y-%m-%dT%H:%M:%S" "$target" +%s 2>/dev/null \
    69	                   || echo "")
    70	    if [[ -n "$target_epoch" ]]; then
    71	      now=$(date -u +%s)
    72	      if (( target_epoch > now )); then
    73	        log "wait_until=$target ; sleeping $((target_epoch - now))s"
    74	        while (( $(date -u +%s) < target_epoch )); do
    75	          if [[ -f "$STOP" ]]; then return 2; fi
    76	          sleep $(( $(date -u +%s) + 60 < target_epoch ? 60 : 5 ))
    77	        done
    78	      fi
    79	      rm -f "$WAIT_UNTIL"
    80	    fi
    81	  fi
    82	  return 0
    83	}
    84	
    85	heartbeat_age() {
    86	  if [[ ! -f "$HEARTBEAT" ]]; then echo 0; return; fi
    87	  hb=$(grep '^ts_utc:' "$HEARTBEAT" | head -n1 | sed 's/^ts_utc: *//;s/Z$//')
    88	  if [[ -z "$hb" ]]; then echo 0; return; fi
    89	  hb_epoch=$(date -u -d "$hb" +%s 2>/dev/null \
    90	             || date -u -j -f "%Y-%m-%dT%H:%M:%S" "$hb" +%s 2>/dev/null \
    91	             || echo "")
    92	  if [[ -z "$hb_epoch" ]]; then echo 0; return; fi
    93	  echo $(( $(date -u +%s) - hb_epoch ))
    94	}
    95	
    96	run_inner_once() {
    97	  # Run route → dispatch → synthesize in sequence. Each script is idempotent
    98	  # and reads disk state, so a crash mid-pass is recoverable on the next pass.
    99	  cd "$SKILL_ASSETS"
   100	  python3 route.py --run-dir "$RUN_DIR" || return $?
   101	  python3 dispatch.py --run-dir "$RUN_DIR" || return $?
   102	  python3 synthesize.py --run-dir "$RUN_DIR" || return $?
   103	  return 0
   104	}
   105	
   106	restart=0
   107	while (( restart < MAX_RESTARTS )); do
   108	  if ! check_sentinels; then
   109	    rc=$?
   110	    [[ "$rc" == "2" ]] && exit 2
   111	    exit "$rc"
   112	  fi
   113	
   114	  log "starting inner pass (restart=$restart)"
   115	  rc=0
   116	  ( timeout "$INNER_TIMEOUT_SEC" bash -c 'run_inner_once; echo $? > "$0".rc' \
   117	      "$RUN_DIR/.inner" ) &
   118	  inner_pid=$!
   119	
   120	  # Watchdog: poll heartbeat
   121	  while kill -0 "$inner_pid" 2>/dev/null; do
   122	    sleep 30
   123	    if [[ -f "$STOP" ]]; then
   124	      log "STOP during inner; killing pid=$inner_pid"
   125	      kill -TERM "$inner_pid" 2>/dev/null || true
   126	      sleep 2; kill -KILL "$inner_pid" 2>/dev/null || true
   127	      exit 2
   128	    fi
   129	    age=$(heartbeat_age)
   130	    if (( age > HEARTBEAT_STALL_SEC )); then
   131	      log "heartbeat stale (${age}s); killing pid=$inner_pid for restart"
   132	      kill -TERM "$inner_pid" 2>/dev/null || true
   133	      sleep 2; kill -KILL "$inner_pid" 2>/dev/null || true
   134	      break
   135	    fi
   136	  done
   137	  wait "$inner_pid" 2>/dev/null || true
   138	  if [[ -f "$RUN_DIR/.inner.rc" ]]; then
   139	    rc=$(cat "$RUN_DIR/.inner.rc" || echo 1)
   140	    rm -f "$RUN_DIR/.inner.rc"
   141	  fi
   142	
   143	  if [[ "$rc" == "0" ]]; then
   144	    log "inner pass succeeded; supervisor done."
   145	    exit 0
   146	  fi
   147	  log "inner pass exit=$rc ; will restart after 5s"
   148	  restart=$((restart + 1))
   149	  sleep 5
   150	done
   151	
   152	log "max-restarts ($MAX_RESTARTS) exceeded; giving up."
   153	exit 4

codex
A first pass shows several likely contract drifts: route writes extra fields, dispatch writes raw logs non-atomically, and synthesis has prepared-host states that aren’t in the state contract. I’m checking the remaining references before finalizing severity and avoiding speculative findings.
exec
/bin/zsh -lc 'nl -ba auto-agents/references/host-cli-modes.md' in /Volumes/ORICO/code/code6/auto-agents
 succeeded in 0ms:
     1	# Host CLI modes — detection, recursion guard, auth check
     2	
     3	The skill runs inside one of `claude` / `codex` / `opencode`. That parent is the **host**. The other two are candidate **workers**. This file is the single source of truth for: how to detect the host, how to verify worker auth, and how to prevent recursion.
     4	
     5	## Three-tier host detection
     6	
     7	Implemented in `assets/host_detect.py`. Run **once** at Stage 0 and write the result to `task.yaml: host`. Algorithm:
     8	
     9	### Tier 1 — environment variable
    10	
    11	Each host CLI is expected to set a distinctive env var when it spawns a subprocess (the skill's helper scripts). Known candidates as of this writing:
    12	
    13	| Host       | Env var(s) tried (first match wins)             |
    14	|------------|-------------------------------------------------|
    15	| `claude`   | `CLAUDECODE`, `CLAUDE_CODE`, `CLAUDE_CODE_*`    |
    16	| `codex`    | `CODEX_CLI`, `CODEX_*`                          |
    17	| `opencode` | `OPENCODE`, `OPENCODE_*`                        |
    18	
    19	The detector reads `os.environ`, counts how many of the three families match:
    20	
    21	- **Exactly one family matches** → host is that one. Record `host_detection: "env-var:<NAME>"`.
    22	- **Zero matches** → fall through to Tier 2.
    23	- **≥2 families match** → suspicious (possible nested invocation or leaked env). Check `AUTO_AGENTS_DEPTH`: if ≥1, we are nested → refuse the skill (recursion guard). Otherwise fall through to Tier 2 and let process-chain disambiguate.
    24	
    25	### Tier 2 — parent process chain
    26	
    27	Walk up `$PPID` using `ps -o comm= -p <pid>` (or `/proc/<pid>/comm` on Linux) until pid=1 or a depth cap (default 8). Collect process names along the way.
    28	
    29	- If exactly one of `{claude, codex, opencode}` appears in the chain → that's the host. Record `host_detection: "ps-chain:<NAME>"`.
    30	- If none appear → fall through to Tier 3.
    31	- If more than one appears → that's a real nested-invocation case. Pick the **closest** (smallest depth) as host but log a `progress.jsonl` warning row.
    32	
    33	Implementation note (macOS vs Linux):
    34	
    35	```sh
    36	# macOS / BSD ps
    37	ps -o comm= -p "$PPID"
    38	
    39	# Linux
    40	cat /proc/$PPID/comm
    41	```
    42	
    43	Both return the process basename. Be defensive: shells like `zsh` or wrappers like `script` may sit between the CLI and the skill helper; that's why we walk the chain rather than reading only `$PPID`.
    44	
    45	### Tier 3 — cached answer + interactive ask
    46	
    47	If both tiers above are inconclusive:
    48	
    49	1. Read `~/.config/auto-agents/host.yaml` if it exists. Schema:
    50	   ```yaml
    51	   host: claude
    52	   confirmed_utc: 2026-05-12T16:40:00Z
    53	   confirmed_by: env-var:CLAUDECODE
    54	   ```
    55	   If the cache is < 30 days old, use the cached host and record `host_detection: "cache"`.
    56	2. Otherwise: prompt the user (via the host's AskUserQuestion or equivalent) with the question "Which CLI are you running this from? (claude / codex / opencode)" and write the answer to both `task.yaml` and `~/.config/auto-agents/host.yaml`.
    57	
    58	### Override (always honored)
    59	
    60	If the env var `AUTO_AGENTS_HOST` is set to one of `claude|codex|opencode`, that wins over all three tiers. Record `host_detection: "env-override:AUTO_AGENTS_HOST"`.
    61	
    62	This is the escape hatch for CI / scripted runs and for users whose CLI doesn't set any of the known env vars.
    63	
    64	## Recursion guard
    65	
    66	Before doing anything else, Stage 0 reads `AUTO_AGENTS_DEPTH`. Defaults to `0`. If `≥ 1`, the skill refuses immediately and writes:
    67	
    68	```
    69	{"status":"refused","reason":"AUTO_AGENTS_DEPTH=1 (already inside auto-agents)"}
    70	```
    71	
    72	When dispatching a worker, the dispatcher sets `AUTO_AGENTS_DEPTH = <current+1>` in the subprocess env. This makes the guard *transitive* — a worker that itself invokes auto-agents will refuse.
    73	
    74	The host never spawns itself as a worker. The router enforces this: if the matrix says the best agent for task class X is the host, `route.json: agent_modes` records `"<host>": "inline"` and Stage 2 skips subprocess dispatch for that agent.
    75	
    76	## Worker auth check
    77	
    78	Stage 0 verifies each candidate worker before letting the router pick it. For each of `claude` / `codex` / `opencode` that is **not** the host:
    79	
    80	1. **Binary present?** Run `which <cli>` (or `command -v`). If missing → `workers_available[<name>] = false`, reason `"binary-missing"`.
    81	2. **Version handshake?** Run `<cli> --version` with a 10s timeout. If exit ≠ 0 → `false`, reason `"version-failed"`.
    82	3. **Auth handshake?** Run a no-op prompt against the CLI with `--dry-run` flag if it supports it, else a 1-token cheap echo. If exit ≠ 0 with a clear auth error → `false`, reason `"auth-failed:<class>"`. Skip this step if the CLI lacks a `--dry-run` and a real call would cost money — record `auth_checked: "deferred"` in that case and let the first real call surface the error.
    83	
    84	Record results in `task.yaml: workers_available` and `progress.jsonl`.
    85	
    86	**If a worker the router wanted is unavailable, escalate — do NOT silently route to another agent.** Per integrity rule "no silent agent swap": the skill stops and asks the user "claude is unavailable; proceed with codex+opencode only? Or stop?"
    87	
    88	## Inline-host execution
    89	
    90	When the router selects the host (e.g. host=claude, task=code-write), Stage 2 does **not** spawn a subprocess. Instead:
    91	
    92	1. The skill helper writes `agents/<host>/invocation.md` with the prompt.
    93	2. The host (the agent reading SKILL.md) answers the prompt itself, in the same conversation.
    94	3. The skill helper captures that answer to `agents/<host>/result.md` via a follow-up write.
    95	
    96	This is the only path that does not produce `stdout.log` / `stderr.log` — set `meta.json: invocation_cmd = "inline"` and `tokens_*: null`.
    97	
    98	## Why three tiers, not one
    99	
   100	The user asked: can the skill auto-detect host? Yes — env-var Tier 1 will hit cleanly when the CLI cooperates. Tier 2 catches CLIs that don't set env vars but do show up in `ps` (most do). Tier 3 is the truthful fallback for esoteric setups — *one* prompt, cached for 30 days. No silent guessing: every detection records `host_detection` in `task.yaml` so the user can audit.

exec
/bin/zsh -lc 'nl -ba auto-agents/references/routing-policy.md' in /Volumes/ORICO/code/code6/auto-agents
 succeeded in 0ms:
     1	# Routing policy
     2	
     3	This file says how `assets/route.py` picks agents from a task description. Read `agent-matrix.md` first — this file is the algorithm, that one is the data.
     4	
     5	## Inputs
     6	
     7	- `task.yaml: prompt` — the user's free-form task
     8	- `task.yaml: host` — detected host CLI
     9	- `task.yaml: workers_available` — which workers passed the auth check
    10	- `task.yaml: mode` — `auto` | `multi` | `single:<agent>` | `dry-run`
    11	- `task.yaml: per_call_cap_usd`, `total_cap_usd`
    12	
    13	## Outputs
    14	
    15	`runs/<task_id>/route.json` (schema in `state-contract.md`).
    16	
    17	## Algorithm
    18	
    19	```
    20	1. If mode == "single:<agent>":
    21	     agents = [<agent>]
    22	     synthesis_method = "inline"
    23	     If <agent> == host:           agent_modes = {<agent>: "inline"}
    24	     Elif workers_available[<agent>] == False:
    25	         escalate("user requested <agent> but it's unavailable")
    26	     Else:
    27	         agent_modes = {<agent>: "subprocess"}
    28	     return.
    29	
    30	2. Classify task_class from prompt using rules in agent-matrix.md §"Classification heuristics".
    31	
    32	3. Look up default agents for task_class from the matrix.
    33	
    34	4. Filter against host:
    35	     - If task_class is "idea" or "debate":
    36	         Use all three regardless of host. The host's own contribution is "inline".
    37	         Other two are "subprocess".
    38	     - Else:
    39	         Take the matrix's priority list.
    40	         If the host is the highest-priority agent → host answers inline, others not called.
    41	         Else → call the highest-priority available worker as subprocess.
    42	
    43	5. Filter against availability:
    44	     Remove any agent whose workers_available[<name>] == False (unless it's the host — host is always available).
    45	     If the *primary* agent for this task_class is unavailable AND mode == "auto":
    46	         escalate("primary agent <X> unavailable, secondary <Y> would be used — confirm?")
    47	     Do NOT silently substitute.
    48	
    49	6. Apply mode == "multi":
    50	     Force agents to all three available (host inline, workers subprocess), regardless of task_class.
    51	
    52	7. Set synthesis_method from matrix default. If only 1 agent in final list → "inline".
    53	
    54	8. Cost estimate:
    55	     Sum per-call estimates from agent-matrix.md.
    56	     If estimate > per_call_cap_usd for any single agent → escalate.
    57	     If estimate > total_cap_usd → escalate.
    58	
    59	9. Write route.json. Append progress.jsonl row {"step":"select_agents", ...}.
    60	```
    61	
    62	## Escalation rules
    63	
    64	When the router escalates, it does NOT auto-decide. It writes the question to `progress.jsonl` and waits for the user. Possible escalations:
    65	
    66	- "Primary agent for class=`code-review` is `codex`, but codex auth check failed. Use `claude` instead? (y/n/cancel)"
    67	- "Estimated cost $1.20 exceeds per_call_cap_usd $0.50. Proceed? Or raise the cap to $1.50 just for this call?"
    68	- "Task class is ambiguous (matched both `code-review` and `code-write`). Pick: review | write | both"
    69	
    70	The skill prompt itself surfaces these to the user; do not proceed past an unanswered escalation.
    71	
    72	## Classifier extension points
    73	
    74	If you add a new task class:
    75	
    76	1. Add a row to the matrix.
    77	2. Add a keyword rule to the heuristics list **after** the existing rules so first-match-wins ordering is stable.
    78	3. Add a test case to `assets/route_test_cases.md` (one bullet per representative prompt → expected class).
    79	4. The router stays code-free for the data side — only the rule list and the matrix change.
    80	
    81	## What the router never does
    82	
    83	- Never picks an unavailable agent.
    84	- Never silently swaps when the primary is unavailable.
    85	- Never picks an agent the user explicitly excluded via `--exclude=<name>` (future flag).
    86	- Never picks the host as a "subprocess" — host is always `"inline"`.
    87	- Never reorders the priority list to save cost — cost only triggers escalation, not silent downgrade.
    88	
    89	## Test cases (used to keep the heuristics honest)
    90	
    91	These live in `assets/route_test_cases.md` (will be added in the second commit) so a CI-like check can re-run them after any matrix change. Example shape:
    92	
    93	```
    94	"audit this auth middleware for token-leak risk" → code-review → primary: codex
    95	"prove that sorted-merge is O(n log n)"            → math         → primary: opencode
    96	"brainstorm three approaches to streaming JSON"    → idea         → all three, meta-synth
    97	"who first proved Cook-Levin?"                     → research     → claude only
    98	"write a Python function that flattens a dict"     → code-write   → primary: claude
    99	```

exec
/bin/zsh -lc 'nl -ba auto-agents/references/agent-matrix.md' in /Volumes/ORICO/code/code6/auto-agents
 succeeded in 0ms:
     1	# Agent capability matrix
     2	
     3	This file says *what each CLI is best at*, *what flags to call it with*, and *which env var holds its credentials*. The router (`assets/route.py`) consumes this. Update here, not in the router code.
     4	
     5	## Task classes
     6	
     7	| Class           | Description                                                  | Default agents (priority order) | Default synthesis |
     8	|-----------------|--------------------------------------------------------------|---------------------------------|-------------------|
     9	| `code-write`    | "write a function / file / patch / refactor"                 | claude, codex                   | inline (1 agent)  |
    10	| `code-review`   | "audit this code / find bugs / security review"              | codex, claude                   | inline (1 agent)  |
    11	| `math`          | "prove / derive / step-by-step calculation / theorem check"  | opencode, claude                | inline (1 agent)  |
    12	| `idea`          | "brainstorm / propose / generate alternatives"               | claude, codex, opencode (all)   | meta-synth        |
    13	| `debate`        | "argue both sides / adversarial / steelman"                  | claude, codex, opencode (all)   | debate            |
    14	| `research`      | "literature / web / collect sources / who said X"            | claude (has WebSearch+WebFetch) | inline (1 agent)  |
    15	| `quick-qa`      | trivial single-shot Q&A                                      | host CLI                         | inline (host)     |
    16	
    17	Classification heuristics (the router applies these in order, first match wins):
    18	
    19	1. Task contains `audit`, `review`, `bug`, `security`, `lint`, `correctness check` → `code-review`
    20	2. Task contains `prove`, `derive`, `theorem`, `integral`, `combinatorics`, `step-by-step solve` → `math`
    21	3. Task contains `brainstorm`, `propose`, `ideas`, `alternatives`, `what could we`, `多个角度` → `idea`
    22	4. Task contains `debate`, `adversarial`, `steelman`, `for and against`, `pros and cons` → `debate`
    23	5. Task contains `find papers`, `search the web`, `who said`, `cite`, `references` → `research`
    24	6. Task contains `write`, `implement`, `add`, `refactor`, `fix the function` → `code-write`
    25	7. Else: `quick-qa` (host inline)
    26	
    27	When the **host** is one of the listed primaries, it answers inline — no subprocess spawn. E.g. host=claude + class=code-write → inline.
    28	
    29	For `idea` and `debate`, **all three agents are called regardless of host**, because the value is the multi-perspective spread.
    30	
    31	## Per-agent profile
    32	
    33	### `claude` (Claude Code)
    34	
    35	- Strengths: code writing, refactoring, web search/fetch, multi-file edits, long-context reasoning.
    36	- Weaknesses: cost per token if you run unbounded; can be over-cautious on adversarial review.
    37	- One-shot CLI: `claude -p "<prompt>"` (writes assistant text to stdout)
    38	- Structured output: `claude -p "<prompt>" --output-format json` (one JSON object on stdout)
    39	- Auth: `ANTHROPIC_API_KEY` env or `~/.claude/` config; the wrapper checks `claude --version` to confirm the binary is present.
    40	- Cost class: medium-high.
    41	
    42	### `codex` (OpenAI Codex CLI)
    43	
    44	- Strengths: code review / audit, tight diffs, terseness, working in CI-style non-interactive contexts.
    45	- Weaknesses: shorter context than Claude; weaker at open-ended brainstorming.
    46	- One-shot CLI: `codex exec "<prompt>"` (non-interactive)
    47	- Auth: `OPENAI_API_KEY` env or `~/.codex/auth.json`; wrapper checks `codex --version`.
    48	- Cost class: medium.
    49	
    50	### `opencode` (sst/opencode)
    51	
    52	- Strengths: math/logic reasoning, local-model friendly, deterministic when paired with a temperature-0 backend.
    53	- Weaknesses: less tooling for web/file I/O; depends on the underlying model the user has configured.
    54	- One-shot CLI: `opencode run "<prompt>"` (one-shot, prints to stdout)
    55	- Auth: depends on the configured provider (`~/.config/opencode/`). Wrapper checks `opencode --version`.
    56	- Cost class: depends on user's backend (can be free with local models).
    57	
    58	## CLI invocation overrides
    59	
    60	If a user's install uses non-default flags, set env vars and the wrappers will use them:
    61	
    62	- `AUTO_AGENTS_CLAUDE_CMD` (default: `claude -p`)
    63	- `AUTO_AGENTS_CODEX_CMD` (default: `codex exec`)
    64	- `AUTO_AGENTS_OPENCODE_CMD` (default: `opencode run`)
    65	
    66	The wrappers pass the prompt as the last positional arg. They never inject additional flags beyond what the env var defines.
    67	
    68	## Cost estimates (rough, for budget gate)
    69	
    70	| Agent     | $/call (typical 4k-in/2k-out) |
    71	|-----------|------------------------------|
    72	| claude    | ~$0.10–0.30                  |
    73	| codex     | ~$0.05–0.20                  |
    74	| opencode  | $0 (local) – $0.15 (cloud)   |
    75	
    76	These are **rough**. `budget.py` reads actuals from each worker's `meta.json` and updates `audit.jsonl`. The gate is on *estimated* cost before the call, then reconciled with *actual* after.

exec
/bin/zsh -lc 'nl -ba auto-agents/references/synthesis-methods.md' in /Volumes/ORICO/code/code6/auto-agents
 succeeded in 0ms:
     1	# Synthesis methods
     2	
     3	Three ways to merge ≥2 worker outputs into one `synthesis/final.md`. Implemented in `assets/synthesize.py`. Which one is used is recorded in `route.json: synthesis_method` and `synthesis/method.md`.
     4	
     5	## inline (1 agent)
     6	
     7	No actual synthesis. The single agent's `result.md` is copied verbatim into `final.md` and the "Contributors" block lists just that one agent. Used whenever the router picks a single agent.
     8	
     9	## vote
    10	
    11	Used for tasks with discrete answers (e.g. "is this code safe? yes/no", "which of these PRs should we merge: A/B/C", "is statement X true?"). Not used by default — opt-in via `route.json` override or `--synthesis=vote`.
    12	
    13	Algorithm:
    14	
    15	1. For each agent, send the prompt plus a suffix:
    16	   ```
    17	   Reply with EXACTLY two lines:
    18	   Line 1: a one-word or one-phrase label (your answer).
    19	   Line 2: a one-sentence justification.
    20	   ```
    21	2. Parse each `agents/<name>/result.md`: first non-empty line = label, second = justification.
    22	3. Tally labels. Normalize (case-fold, strip punctuation).
    23	4. **Majority** (≥ ⌈n/2⌉+1 agreeing) wins → `final.md` records the winning label, all justifications, and tally.
    24	5. **No majority**: escalate. Either ask the user, or fall back to meta-synth on the same outputs (the synthesizer asks first; default is escalate).
    25	
    26	Write `synthesis/intermediate/vote-tally.json`:
    27	
    28	```json
    29	{
    30	  "labels": {"claude": "yes", "codex": "yes", "opencode": "no"},
    31	  "tally": {"yes": 2, "no": 1},
    32	  "winner": "yes",
    33	  "majority": true
    34	}
    35	```
    36	
    37	## debate (default for task_class = `debate`)
    38	
    39	Two-round structured debate, host-moderated. Used when adversarial perspective is the point.
    40	
    41	Round 1 — **opening positions** (parallel):
    42	
    43	- Each agent receives the original prompt + a suffix:
    44	  ```
    45	  State your position in ≤300 words. Lead with a one-sentence claim.
    46	  Cite your reasoning explicitly. Do not hedge.
    47	  ```
    48	- Outputs land in `agents/<name>/result.md` (round-1 version) and `synthesis/intermediate/debate-round-1.md` (concatenated).
    49	
    50	Round 2 — **rebuttals** (parallel, each agent reads the *other* agents' round-1):
    51	
    52	- For each agent, the prompt is:
    53	  ```
    54	  Here are the opening positions from the other agents:
    55	
    56	  --- <other_1> ---
    57	  <other_1's round-1 text>
    58	  --- <other_2> ---
    59	  <other_2's round-1 text>
    60	
    61	  Critique their reasoning. Restate or revise your own position
    62	  in ≤300 words. Lead with: "I agree with <X> on <Y>, but disagree on <Z>" 
    63	  if applicable; otherwise lead with a one-sentence revised claim.
    64	  ```
    65	- Outputs into `synthesis/intermediate/debate-round-2.md`.
    66	
    67	Final synthesis — **moderator pass** (host inline):
    68	
    69	- The host (whichever CLI is reading this) reads both rounds and writes `final.md`:
    70	  - One-paragraph "consensus or split?" summary.
    71	  - Bullet list of points that all agents agreed on (after round 2).
    72	  - Bullet list of points that remained contested + which agent took which side.
    73	  - One-sentence "moderator's read" of the strongest argument *(label it as the host's opinion, not as ground truth)*.
    74	- Contributors block lists each agent's round-1 and round-2 contribution paths.
    75	
    76	Escalation: if any agent fails round 1 → proceed with the remaining agents but record the dropout in `final.md`. If any agent fails round 2 → use its round-1 position as its final stance.
    77	
    78	## meta-synth (default for task_class = `idea`)
    79	
    80	The host reads all worker outputs and writes one unified answer with attribution.
    81	
    82	Algorithm:
    83	
    84	1. Verify all agents in `route.json: agents` have `meta.json: status == "ok"`. If any failed, list them in `final.md` "Contributors" as failed and proceed with the rest.
    85	2. Concatenate `agents/<name>/result.md` for each successful agent into `synthesis/intermediate/meta-synth-input.md`, prefixed by `--- <name> ---` separators.
    86	3. The host writes `final.md` directly, following the structure in `state-contract.md §"synthesis/final.md"`:
    87	   - **# Answer** — the unified answer, written by the host. Inline-cite contributing agents where their wording or idea is the source.
    88	   - **## Contributors** — one bullet per agent, naming what they brought.
    89	   - **## Synthesis method: meta-synth** — one paragraph: what overlapped, what conflicted, how the host resolved conflicts.
    90	   - **## Audit** — total cost / time, link to `audit.jsonl`.
    91	
    92	The host does not paraphrase agent outputs unless one is clearly wrong; instead it weaves their contributions into one coherent answer. If two agents say similar things, the synthesis credits both and picks the clearer phrasing.
    93	
    94	**Attribution is mandatory.** If a sentence in `final.md` is materially based on one specific agent's output, that sentence (or its paragraph) names the agent. Verbatim quotes get a code-block fence and attribution. Failing this is a violation of integrity rule "attribution mandatory".
    95	
    96	## When synthesis cannot proceed
    97	
    98	- All workers failed → write `final.md` with body "All agents failed. See `agents/*/meta.json` for errors. No synthesis produced." and exit with non-zero.
    99	- One worker succeeded → degrade to `inline` and note the dropouts in Contributors.
   100	- Vote tied with no majority and user said "no fallback" → escalate without producing `final.md`.
   101	
   102	Never fabricate a synthesis. Never write "<agent> said X" if `<agent>/result.md` does not contain X.

web search: 
web search: Claude Code CLI reference -p print prompt command docs Anthropic Claude Code -p --print
web search: 
web search: site:developers.openai.com/codex codex exec CLI reference
web search: 
web search: https://github.com/openai/codex/blob/main/README.md
web search: 
web search: https://developers.openai.com/codex/noninteractive
web search: 
web search: 'codex exec' in https://developers.openai.com/codex/noninteractive
codex
I checked current primary CLI docs for the three wrapper defaults rather than inferring flag drift. The default one-shot commands still match the published patterns I found, so I’ll only flag wrapper behavior that conflicts with the local contracts.
exec
/bin/zsh -lc "rg -n \"run_dir|runs/|task\\.yaml|route\\.json|progress\\.jsonl|audit\\.jsonl|heartbeat|agents|synthesis|hand_off|attempts|wait_until|STOP|PAUSE|write_text|atomic_write|append_audit|append_progress|meta\\.json|result\\.md|stdout\\.log|stderr\\.log|invocation\\.md\" auto-agents/assets/*.py" in /Volumes/ORICO/code/code6/auto-agents
exec
/bin/zsh -lc "rg -n \"budget|gate\\(|reconcile|estimated|cost_|per_call|total_cap|audit\" auto-agents/assets/*.py auto-agents/references/*.md" in /Volumes/ORICO/code/code6/auto-agents
 succeeded in 0ms:
auto-agents/assets/host_detect.py:9:    candidates:  list of candidates discovered (for audit)
auto-agents/assets/host_detect.py:80:    """Walk parent chain; return (host_if_found, chain_for_audit)."""
auto-agents/assets/auth_check.py:8:    run_stage0(run_dir=..., prompt=..., mode="auto", per_call_cap_usd=0.50,
auto-agents/assets/auth_check.py:9:               total_cap_usd=2.00, deadline_utc=None)
auto-agents/assets/auth_check.py:35:               per_call_cap_usd: float = 0.50, total_cap_usd: float = 2.00,
auto-agents/assets/auth_check.py:84:        "per_call_cap_usd": per_call_cap_usd,
auto-agents/assets/auth_check.py:85:        "total_cap_usd": total_cap_usd,
auto-agents/assets/auth_check.py:111:        per_call_cap_usd=args.per_call_cap_usd,
auto-agents/assets/auth_check.py:112:        total_cap_usd=args.total_cap_usd,
auto-agents/assets/budget.py:1:"""Cost gate + audit reconciliation.
auto-agents/assets/budget.py:3:Sums actual costs from audit.jsonl, compares against the caps in task.yaml,
auto-agents/assets/budget.py:9:That means budget gating is best-effort on *estimates* and only catches real
auto-agents/assets/budget.py:21:    """Extract per_call_cap_usd and total_cap_usd from task.yaml."""
auto-agents/assets/budget.py:22:    per_call = 0.50
auto-agents/assets/budget.py:25:        if line.startswith("per_call_cap_usd:"):
auto-agents/assets/budget.py:27:                per_call = float(line.split(":", 1)[1].strip())
auto-agents/assets/budget.py:30:        elif line.startswith("total_cap_usd:"):
auto-agents/assets/budget.py:35:    return per_call, total
auto-agents/assets/budget.py:39:    audit = run_dir / "audit.jsonl"
auto-agents/assets/budget.py:40:    if not audit.exists():
auto-agents/assets/budget.py:43:    for line in audit.read_text(encoding="utf-8").splitlines():
auto-agents/assets/budget.py:48:        v = row.get("cost_actual_usd")
auto-agents/assets/budget.py:54:def gate(run_dir: Path, *, estimated_next_call_usd: float) -> dict:
auto-agents/assets/budget.py:55:    per_call, total_cap = _read_yaml_floats(run_dir / "task.yaml")
auto-agents/assets/budget.py:59:        "estimated_next_call_usd": round(estimated_next_call_usd, 4),
auto-agents/assets/budget.py:60:        "per_call_cap_usd": per_call,
auto-agents/assets/budget.py:61:        "total_cap_usd": total_cap,
auto-agents/assets/budget.py:65:    if estimated_next_call_usd > per_call:
auto-agents/assets/budget.py:68:            f"estimated ${estimated_next_call_usd:.2f} > per-call cap ${per_call:.2f}"
auto-agents/assets/budget.py:70:    if spent + estimated_next_call_usd > total_cap:
auto-agents/assets/budget.py:73:            f"spent ${spent:.2f} + est ${estimated_next_call_usd:.2f} > total cap ${total_cap:.2f}"
auto-agents/assets/budget.py:78:def reconcile(run_dir: Path) -> dict:
auto-agents/assets/budget.py:79:    """Compare per-agent estimates (cost_est_usd in meta.json) against actuals
auto-agents/assets/budget.py:80:    in audit.jsonl. Returns a summary; flags agents whose actuals exceed
auto-agents/assets/budget.py:97:        est = meta.get("cost_est_usd")
auto-agents/assets/budget.py:98:        act = meta.get("cost_actual_usd")
auto-agents/assets/budget.py:108:    ap.add_argument("--estimated-next-call-usd", type=float, default=0.0)
auto-agents/assets/budget.py:109:    ap.add_argument("--reconcile", action="store_true")
auto-agents/assets/budget.py:111:    if args.reconcile:
auto-agents/assets/budget.py:112:        print(json.dumps(reconcile(args.run_dir), indent=2))
auto-agents/assets/budget.py:114:        decision = gate(args.run_dir, estimated_next_call_usd=args.estimated_next_call_usd)
auto-agents/assets/route.py:30:# Rough $/call estimates (mid-range). Reconciled with audit.jsonl actuals.
auto-agents/assets/route.py:35:    ("code-review", [r"\baudit\b", r"\breview\b", r"\bbug(s)?\b",
auto-agents/assets/route.py:131:    per_call_cap = float(task.get("per_call_cap_usd", 0.50))
auto-agents/assets/route.py:142:    cost_estimate = sum(
auto-agents/assets/route.py:146:    if cost_estimate > per_call_cap * len(
auto-agents/assets/route.py:150:            f"estimated cost ${cost_estimate:.2f} exceeds per-call cap "
auto-agents/assets/route.py:151:            f"${per_call_cap:.2f}"
auto-agents/assets/route.py:160:        "cost_estimate_usd": round(cost_estimate, 4),
auto-agents/assets/dispatch.py:107:        "cost_est_usd": None,
auto-agents/assets/dispatch.py:108:        "cost_actual_usd": None,
auto-agents/assets/dispatch.py:113:    P.append_audit(
auto-agents/assets/dispatch.py:116:        cost_actual_usd=None,
auto-agents/assets/dispatch.py:139:        "cost_est_usd": None, "cost_actual_usd": None,
auto-agents/assets/synthesize.py:47:def _audit_totals(run_dir: Path) -> tuple[float, float]:
auto-agents/assets/synthesize.py:48:    """Returns (total_duration_s, total_cost_actual_usd) from audit.jsonl."""
auto-agents/assets/synthesize.py:49:    audit = run_dir / "audit.jsonl"
auto-agents/assets/synthesize.py:50:    if not audit.exists():
auto-agents/assets/synthesize.py:54:    for line in audit.read_text(encoding="utf-8").splitlines():
auto-agents/assets/synthesize.py:60:        cost += float(row.get("cost_actual_usd") or 0)
auto-agents/assets/synthesize.py:79:def _audit_block(run_dir: Path) -> str:
auto-agents/assets/synthesize.py:80:    dur, cost = _audit_totals(run_dir)
auto-agents/assets/synthesize.py:85:        "- Per-call breakdown: `audit.jsonl`\n"
auto-agents/assets/synthesize.py:106:                + _audit_block(run_dir))
auto-agents/assets/synthesize.py:113:        + _audit_block(run_dir)
auto-agents/assets/synthesize.py:142:                + _audit_block(run_dir)), {"tally": {}, "winner": None}
auto-agents/assets/synthesize.py:160:        + _audit_block(run_dir)
auto-agents/assets/progress.py:1:"""Append-only progress + audit logging, atomic state writes, sentinel checks.
auto-agents/assets/progress.py:34:def append_audit(run_dir: Path, *, agent: str, attempt: int, exit_code: int,
auto-agents/assets/progress.py:36:                 tokens_out: int | None, cost_actual_usd: float | None) -> None:
auto-agents/assets/progress.py:45:        "cost_actual_usd": cost_actual_usd,
auto-agents/assets/progress.py:48:    with open(run_dir / "audit.jsonl", "a", encoding="utf-8") as f:
auto-agents/references/integrity-rules.md:7:If the router's chosen agent is unavailable (missing binary, auth failure, exceeded budget), the skill **stops and asks the user**. It never silently routes to a different agent.
auto-agents/references/integrity-rules.md:23:Two caps in `task.yaml`: `per_call_cap_usd` (default $0.50) and `total_cap_usd` (default $2.00).
auto-agents/references/integrity-rules.md:27:1. Use the matrix's per-agent estimate × 2 (worst-case headroom) → if > per_call_cap_usd, escalate.
auto-agents/references/integrity-rules.md:28:2. Sum prior `audit.jsonl` actuals + this call's estimate → if > total_cap_usd, escalate.
auto-agents/references/integrity-rules.md:30:The estimates in `agent-matrix.md` are rough — `budget.py` reconciles with `audit.jsonl` actuals so subsequent estimates drift toward reality.
auto-agents/references/routing-policy.md:11:- `task.yaml: per_call_cap_usd`, `total_cap_usd`
auto-agents/references/routing-policy.md:56:     If estimate > per_call_cap_usd for any single agent → escalate.
auto-agents/references/routing-policy.md:57:     If estimate > total_cap_usd → escalate.
auto-agents/references/routing-policy.md:67:- "Estimated cost $1.20 exceeds per_call_cap_usd $0.50. Proceed? Or raise the cap to $1.50 just for this call?"
auto-agents/references/routing-policy.md:94:"audit this auth middleware for token-leak risk" → code-review → primary: codex
auto-agents/references/synthesis-methods.md:90:   - **## Audit** — total cost / time, link to `audit.jsonl`.
auto-agents/references/state-contract.md:22:├── audit.jsonl                       # append-only per-CLI-call audit (cost + time)
auto-agents/references/state-contract.md:34:│   │   ├── meta.json                 # status, exit_code, ts_started/ended, tokens, cost_est_usd, cost_actual_usd
auto-agents/references/state-contract.md:35:│   │   └── attempts/                 # optional: prior failed attempts kept for audit
auto-agents/references/state-contract.md:60:host_detection: env-var:CLAUDECODE   # how it was detected; for audit
auto-agents/references/state-contract.md:64:per_call_cap_usd: 0.50
auto-agents/references/state-contract.md:65:total_cap_usd: 2.00
auto-agents/references/state-contract.md:82:  "cost_estimate_usd": 0.45,
auto-agents/references/state-contract.md:95:  "cost_estimate_usd": 0.0,
auto-agents/references/state-contract.md:113:### `audit.jsonl` (append-only)
auto-agents/references/state-contract.md:118:{"ts_utc":"2026-05-12T16:40:31Z","agent":"claude","attempt":1,"exit_code":0,"duration_s":28.4,"tokens_in":3210,"tokens_out":1402,"cost_actual_usd":0.18}
auto-agents/references/state-contract.md:144:  "cost_est_usd": 0.30,
auto-agents/references/state-contract.md:145:  "cost_actual_usd": 0.18,
auto-agents/references/state-contract.md:179:- See `audit.jsonl` for per-call breakdown.
auto-agents/references/state-contract.md:202:Append-only files (`progress.jsonl`, `audit.jsonl`) use a single `open(..., "a")` write per row — POSIX guarantees a single small write does not interleave.
auto-agents/references/host-cli-modes.md:100:The user asked: can the skill auto-detect host? Yes — env-var Tier 1 will hit cleanly when the CLI cooperates. Tier 2 catches CLIs that don't set env vars but do show up in `ps` (most do). Tier 3 is the truthful fallback for esoteric setups — *one* prompt, cached for 30 days. No silent guessing: every detection records `host_detection` in `task.yaml` so the user can audit.
auto-agents/references/agent-matrix.md:10:| `code-review`   | "audit this code / find bugs / security review"              | codex, claude                   | inline (1 agent)  |
auto-agents/references/agent-matrix.md:19:1. Task contains `audit`, `review`, `bug`, `security`, `lint`, `correctness check` → `code-review`
auto-agents/references/agent-matrix.md:44:- Strengths: code review / audit, tight diffs, terseness, working in CI-style non-interactive contexts.
auto-agents/references/agent-matrix.md:68:## Cost estimates (rough, for budget gate)
auto-agents/references/agent-matrix.md:76:These are **rough**. `budget.py` reads actuals from each worker's `meta.json` and updates `audit.jsonl`. The gate is on *estimated* cost before the call, then reconciled with *actual* after.

 succeeded in 0ms:
auto-agents/assets/invoke_codex.py:62:                 f"\n[auto-agents] killed after {timeout_sec}s"
auto-agents/assets/auth_check.py:1:"""Stage 0 — detect host, verify worker CLIs, write task.yaml + workers_available.
auto-agents/assets/auth_check.py:4:    python -m auth_check --run-dir <runs/<task_id>> --prompt-file <path>
auto-agents/assets/auth_check.py:8:    run_stage0(run_dir=..., prompt=..., mode="auto", per_call_cap_usd=0.50,
auto-agents/assets/auth_check.py:34:def run_stage0(run_dir: Path, prompt: str, *, mode: str = "auto",
auto-agents/assets/auth_check.py:38:    run_dir.mkdir(parents=True, exist_ok=True)
auto-agents/assets/auth_check.py:39:    P.check_sentinels(run_dir)
auto-agents/assets/auth_check.py:40:    P.write_heartbeat(run_dir, stage=0, step="host_detect")
auto-agents/assets/auth_check.py:45:        P.append_progress(run_dir, stage=0, step="host_detect",
auto-agents/assets/auth_check.py:51:        P.append_progress(run_dir, stage=0, step="host_detect",
auto-agents/assets/auth_check.py:55:    P.append_progress(run_dir, stage=0, step="host_detect",
auto-agents/assets/auth_check.py:59:    P.write_heartbeat(run_dir, stage=0, step="auth_check")
auto-agents/assets/auth_check.py:70:    P.append_progress(
auto-agents/assets/auth_check.py:71:        run_dir, stage=0, step="auth_check", status="ok",
auto-agents/assets/auth_check.py:76:    # --- write task.yaml -----------------------------------------------------
auto-agents/assets/auth_check.py:78:        "task_id": run_dir.name,
auto-agents/assets/auth_check.py:90:    P.atomic_write_text(run_dir / "task.yaml", yaml_io.dump(task))
auto-agents/assets/auth_check.py:91:    P.append_progress(run_dir, stage=0, step="write_task_yaml", status="ok")
auto-agents/assets/auth_check.py:108:        run_dir=args.run_dir,
auto-agents/assets/dispatch.py:1:"""Stage 2 — fan out workers per route.json.
auto-agents/assets/dispatch.py:4:recursive auto-agents invocation will refuse at Stage 0 (recursion guard).
auto-agents/assets/dispatch.py:7:here. Instead its `agents/<host>/invocation.md` is written and a placeholder
auto-agents/assets/dispatch.py:8:`meta.json` is written with status="pending". The SKILL.md prompt instructs
auto-agents/assets/dispatch.py:9:the host to fill `agents/<host>/result.md` itself, then re-invoke dispatch.py
auto-agents/assets/dispatch.py:10:which will mark host status="ok" once result.md is non-empty.
auto-agents/assets/dispatch.py:33:def _read_route(run_dir: Path) -> dict:
auto-agents/assets/dispatch.py:34:    return json.loads((run_dir / "route.json").read_text(encoding="utf-8"))
auto-agents/assets/dispatch.py:37:def _read_prompt(run_dir: Path) -> str:
auto-agents/assets/dispatch.py:38:    return yaml_io.load_path(run_dir / "task.yaml").get("prompt", "")
auto-agents/assets/dispatch.py:42:    """If agent_dir has a result.md from a prior failed attempt, move it under
auto-agents/assets/dispatch.py:43:    attempts/<N>/ so resume produces a fresh result."""
auto-agents/assets/dispatch.py:44:    meta = agent_dir / "meta.json"
auto-agents/assets/dispatch.py:47:    attempts_dir = agent_dir / "attempts"
auto-agents/assets/dispatch.py:48:    attempts_dir.mkdir(exist_ok=True)
auto-agents/assets/dispatch.py:49:    n = len(list(attempts_dir.iterdir())) + 1
auto-agents/assets/dispatch.py:50:    target = attempts_dir / str(n)
auto-agents/assets/dispatch.py:52:    for name in ("invocation.md", "stdout.log", "stderr.log",
auto-agents/assets/dispatch.py:53:                 "result.md", "meta.json"):
auto-agents/assets/dispatch.py:60:    meta = agent_dir / "meta.json"
auto-agents/assets/dispatch.py:69:def _dispatch_subprocess(run_dir: Path, agent: str, prompt: str) -> dict:
auto-agents/assets/dispatch.py:71:    agent_dir = run_dir / "agents" / agent
auto-agents/assets/dispatch.py:74:    # invocation.md — reproducible record
auto-agents/assets/dispatch.py:81:    P.atomic_write_text(agent_dir / "invocation.md", inv)
auto-agents/assets/dispatch.py:84:    P.append_progress(run_dir, stage=2, step=f"dispatch:{agent}", status="started")
auto-agents/assets/dispatch.py:85:    P.write_heartbeat(run_dir, stage=2, step=f"dispatch:{agent}")
auto-agents/assets/dispatch.py:91:    (agent_dir / "stdout.log").write_text(result["stdout"], encoding="utf-8")
auto-agents/assets/dispatch.py:92:    (agent_dir / "stderr.log").write_text(result["stderr"], encoding="utf-8")
auto-agents/assets/dispatch.py:94:    P.atomic_write_text(agent_dir / "result.md", answer)
auto-agents/assets/dispatch.py:110:        "attempts": 1,
auto-agents/assets/dispatch.py:112:    P.atomic_write_json(agent_dir / "meta.json", meta)
auto-agents/assets/dispatch.py:113:    P.append_audit(
auto-agents/assets/dispatch.py:114:        run_dir, agent=agent, attempt=1, exit_code=result["exit_code"],
auto-agents/assets/dispatch.py:118:    P.append_progress(run_dir, stage=2, step=f"dispatch:{agent}", status=status,
auto-agents/assets/dispatch.py:123:def _stage_inline_host(run_dir: Path, host: str, prompt: str) -> dict:
auto-agents/assets/dispatch.py:124:    """Write the invocation but leave result.md to be filled by the host model."""
auto-agents/assets/dispatch.py:125:    agent_dir = run_dir / "agents" / host
auto-agents/assets/dispatch.py:129:        f"The host agent should write its answer to `result.md` in this folder,\n"
auto-agents/assets/dispatch.py:130:        f"then update `meta.json: status` to `ok` and re-run dispatch.py.\n\n"
auto-agents/assets/dispatch.py:133:    P.atomic_write_text(agent_dir / "invocation.md", inv)
auto-agents/assets/dispatch.py:140:        "invocation_cmd": "inline", "attempts": 1,
auto-agents/assets/dispatch.py:142:    P.atomic_write_json(agent_dir / "meta.json", meta)
auto-agents/assets/dispatch.py:143:    P.append_progress(run_dir, stage=2, step=f"dispatch:{host}",
auto-agents/assets/dispatch.py:145:                      detail="host writes result.md, then re-run dispatch")
auto-agents/assets/dispatch.py:149:def run_stage2(run_dir: Path) -> dict:
auto-agents/assets/dispatch.py:150:    P.check_sentinels(run_dir)
auto-agents/assets/dispatch.py:151:    route = _read_route(run_dir)
auto-agents/assets/dispatch.py:153:        P.append_progress(run_dir, stage=2, step="check_route",
auto-agents/assets/dispatch.py:158:    prompt = _read_prompt(run_dir)
auto-agents/assets/dispatch.py:162:        agent_dir = run_dir / "agents" / agent
auto-agents/assets/dispatch.py:167:            P.append_progress(run_dir, stage=2, step=f"dispatch:{agent}",
auto-agents/assets/dispatch.py:177:            results[agent] = _stage_inline_host(run_dir, agent, prompt)
auto-agents/assets/dispatch.py:179:            results[agent] = _dispatch_subprocess(run_dir, agent, prompt)
auto-agents/assets/dispatch.py:188:    out = run_stage2(args.run_dir)
auto-agents/assets/progress.py:19:def append_progress(run_dir: Path, *, stage: int, step: str, status: str,
auto-agents/assets/progress.py:30:    with open(run_dir / "progress.jsonl", "a", encoding="utf-8") as f:
auto-agents/assets/progress.py:34:def append_audit(run_dir: Path, *, agent: str, attempt: int, exit_code: int,
auto-agents/assets/progress.py:48:    with open(run_dir / "audit.jsonl", "a", encoding="utf-8") as f:
auto-agents/assets/progress.py:53:def atomic_write_text(path: Path, content: str) -> None:
auto-agents/assets/progress.py:55:    tmp.write_text(content, encoding="utf-8")
auto-agents/assets/progress.py:59:def atomic_write_json(path: Path, obj) -> None:
auto-agents/assets/progress.py:60:    atomic_write_text(path, json.dumps(obj, ensure_ascii=False, indent=2))
auto-agents/assets/progress.py:63:def write_heartbeat(run_dir: Path, *, stage: int, step: str) -> None:
auto-agents/assets/progress.py:70:    atomic_write_text(run_dir / ".heartbeat", body)
auto-agents/assets/progress.py:75:    """Raised when runs/<task_id>/STOP is found at micro-step boundary."""
auto-agents/assets/progress.py:78:def check_sentinels(run_dir: Path) -> None:
auto-agents/assets/progress.py:79:    """Raise StopRequested if STOP is present; sleep-and-retry on PAUSE;
auto-agents/assets/progress.py:80:    sleep until wait_until.txt timestamp if present. Called at the top of
auto-agents/assets/progress.py:82:    stop = run_dir / "STOP"
auto-agents/assets/progress.py:84:        raise StopRequested(f"STOP sentinel at {stop}")
auto-agents/assets/progress.py:85:    pause = run_dir / "PAUSE"
auto-agents/assets/progress.py:88:    wait = run_dir / "wait_until.txt"
auto-agents/assets/progress.py:96:                # Sleep in 60s chunks so STOP can still interrupt.
auto-agents/assets/progress.py:99:                        raise StopRequested(f"STOP during wait_until at {stop}")
auto-agents/assets/progress.py:107:            # malformed wait_until — ignore (log left to caller)
auto-agents/assets/progress.py:112:def progress_tail(run_dir: Path, n: int = 50) -> list[dict]:
auto-agents/assets/progress.py:113:    p = run_dir / "progress.jsonl"
auto-agents/assets/progress.py:126:def last_completed_step(run_dir: Path) -> tuple[int, str] | None:
auto-agents/assets/progress.py:128:    for row in reversed(progress_tail(run_dir, n=500)):
auto-agents/assets/invoke_claude.py:70:                 f"\n[auto-agents] killed after {timeout_sec}s"
auto-agents/assets/host_detect.py:31:CACHE_PATH = Path.home() / ".config" / "auto-agents" / "host.yaml"
auto-agents/assets/host_detect.py:99:    """Read ~/.config/auto-agents/host.yaml; return (host, prior_detection)."""
auto-agents/assets/host_detect.py:138:    tmp.write_text(body)
auto-agents/assets/route.py:1:"""Stage 1 — classify task and write route.json.
auto-agents/assets/route.py:21:    "code-write":  {"primary": ["claude", "codex"],                     "synthesis": "inline"},
auto-agents/assets/route.py:22:    "code-review": {"primary": ["codex", "claude"],                     "synthesis": "inline"},
auto-agents/assets/route.py:23:    "math":        {"primary": ["opencode", "claude"],                  "synthesis": "inline"},
auto-agents/assets/route.py:24:    "idea":        {"primary": ["claude", "codex", "opencode"],         "synthesis": "meta-synth"},
auto-agents/assets/route.py:25:    "debate":      {"primary": ["claude", "codex", "opencode"],         "synthesis": "debate"},
auto-agents/assets/route.py:26:    "research":    {"primary": ["claude"],                              "synthesis": "inline"},
auto-agents/assets/route.py:27:    "quick-qa":    {"primary": ["__host__"],                            "synthesis": "inline"},
auto-agents/assets/route.py:30:# Rough $/call estimates (mid-range). Reconciled with audit.jsonl actuals.
auto-agents/assets/route.py:61:def _select_agents(task_class: str, host: str, available: dict[str, bool],
auto-agents/assets/route.py:63:    """Returns (agents, agent_modes, synthesis_method, escalations)."""
auto-agents/assets/route.py:67:    synthesis = cls["synthesis"]
auto-agents/assets/route.py:83:        agents = [a for a in ("claude", "codex", "opencode") if available.get(a, False)]
auto-agents/assets/route.py:84:        modes = {a: "inline" if a == host else "subprocess" for a in agents}
auto-agents/assets/route.py:85:        return agents, modes, "meta-synth" if len(agents) > 1 else "inline", escalations
auto-agents/assets/route.py:93:        agents = [a for a in primary if available.get(a, False)]
auto-agents/assets/route.py:94:        if host not in agents and available.get(host, False):
auto-agents/assets/route.py:95:            agents.insert(0, host)
auto-agents/assets/route.py:96:        modes = {a: "inline" if a == host else "subprocess" for a in agents}
auto-agents/assets/route.py:97:        return agents, modes, synthesis if len(agents) > 1 else "inline", escalations
auto-agents/assets/route.py:122:def run_stage1(run_dir: Path) -> dict:
auto-agents/assets/route.py:123:    P.check_sentinels(run_dir)
auto-agents/assets/route.py:124:    P.write_heartbeat(run_dir, stage=1, step="classify")
auto-agents/assets/route.py:126:    task = yaml_io.load_path(run_dir / "task.yaml")
auto-agents/assets/route.py:134:    P.append_progress(run_dir, stage=1, step="classify", status="ok",
auto-agents/assets/route.py:137:    P.write_heartbeat(run_dir, stage=1, step="select_agents")
auto-agents/assets/route.py:138:    agents, agent_modes, synthesis, escalations = _select_agents(
auto-agents/assets/route.py:157:        "agents": agents,
auto-agents/assets/route.py:159:        "synthesis_method": synthesis,
auto-agents/assets/route.py:164:    P.atomic_write_json(run_dir / "route.json", route)
auto-agents/assets/route.py:165:    P.append_progress(
auto-agents/assets/route.py:166:        run_dir, stage=1, step="select_agents",
auto-agents/assets/route.py:169:               else f"{agents} synth={synthesis}",
auto-agents/assets/route.py:178:    route = run_stage1(args.run_dir)
auto-agents/assets/invoke_opencode.py:62:                 f"\n[auto-agents] killed after {timeout_sec}s"
auto-agents/assets/synthesize.py:1:"""Stage 3 — merge agent outputs into synthesis/final.md.
auto-agents/assets/synthesize.py:5:  - vote        : majority on the first-line label across agents
auto-agents/assets/synthesize.py:9:                  final synthesis paragraph)
auto-agents/assets/synthesize.py:27:def _read_route(run_dir: Path) -> dict:
auto-agents/assets/synthesize.py:28:    return json.loads((run_dir / "route.json").read_text(encoding="utf-8"))
auto-agents/assets/synthesize.py:31:def _read_agent_result(run_dir: Path, agent: str) -> tuple[str | None, str]:
auto-agents/assets/synthesize.py:32:    """Returns (status, result_text). status comes from meta.json."""
auto-agents/assets/synthesize.py:33:    agent_dir = run_dir / "agents" / agent
auto-agents/assets/synthesize.py:34:    meta_path = agent_dir / "meta.json"
auto-agents/assets/synthesize.py:42:    result_path = agent_dir / "result.md"
auto-agents/assets/synthesize.py:47:def _audit_totals(run_dir: Path) -> tuple[float, float]:
auto-agents/assets/synthesize.py:48:    """Returns (total_duration_s, total_cost_actual_usd) from audit.jsonl."""
auto-agents/assets/synthesize.py:49:    audit = run_dir / "audit.jsonl"
auto-agents/assets/synthesize.py:64:def _contributors_block(run_dir: Path, agents: list[str]) -> str:
auto-agents/assets/synthesize.py:66:    for a in agents:
auto-agents/assets/synthesize.py:67:        status, text = _read_agent_result(run_dir, a)
auto-agents/assets/synthesize.py:70:            lines.append(f"- **{a}** — see `agents/{a}/result.md` "
auto-agents/assets/synthesize.py:73:            lines.append(f"- **{a}** — *pending* (host inline; result.md not yet written)")
auto-agents/assets/synthesize.py:79:def _audit_block(run_dir: Path) -> str:
auto-agents/assets/synthesize.py:80:    dur, cost = _audit_totals(run_dir)
auto-agents/assets/synthesize.py:85:        "- Per-call breakdown: `audit.jsonl`\n"
auto-agents/assets/synthesize.py:89:def _write_method_md(run_dir: Path, method: str, note: str = "") -> None:
auto-agents/assets/synthesize.py:91:    P.atomic_write_text(run_dir / "synthesis" / "method.md", body)
auto-agents/assets/synthesize.py:95:def synth_inline(run_dir: Path, route: dict) -> str:
auto-agents/assets/synthesize.py:96:    agents = route["agents"]
auto-agents/assets/synthesize.py:97:    assert len(agents) == 1, "inline synthesis expects exactly one agent"
auto-agents/assets/synthesize.py:98:    a = agents[0]
auto-agents/assets/synthesize.py:99:    status, text = _read_agent_result(run_dir, a)
auto-agents/assets/synthesize.py:104:                + _contributors_block(run_dir, agents)
auto-agents/assets/synthesize.py:106:                + _audit_block(run_dir))
auto-agents/assets/synthesize.py:110:        + _contributors_block(run_dir, agents)
auto-agents/assets/synthesize.py:113:        + _audit_block(run_dir)
auto-agents/assets/synthesize.py:122:def synth_vote(run_dir: Path, route: dict) -> tuple[str, dict]:
auto-agents/assets/synthesize.py:123:    """Tally labels (first non-empty line of each result.md). Returns (final_md, tally_dict)."""
auto-agents/assets/synthesize.py:126:    for a in route["agents"]:
auto-agents/assets/synthesize.py:127:        status, text = _read_agent_result(run_dir, a)
auto-agents/assets/synthesize.py:139:        return ("# Answer\n\n_All agents failed to produce a labeled answer._\n\n"
auto-agents/assets/synthesize.py:140:                + _contributors_block(run_dir, route["agents"])
auto-agents/assets/synthesize.py:142:                + _audit_block(run_dir)), {"tally": {}, "winner": None}
auto-agents/assets/synthesize.py:155:                    for a in route["agents"])
auto-agents/assets/synthesize.py:157:        + _contributors_block(run_dir, route["agents"])
auto-agents/assets/synthesize.py:160:        + _audit_block(run_dir)
auto-agents/assets/synthesize.py:170:The file `synthesis/intermediate/meta-synth-input.md` contains every worker
auto-agents/assets/synthesize.py:173:Write `synthesis/final.md` with this structure:
auto-agents/assets/synthesize.py:197:def synth_meta_prepare(run_dir: Path, route: dict) -> str:
auto-agents/assets/synthesize.py:200:    inter = run_dir / "synthesis" / "intermediate"
auto-agents/assets/synthesize.py:203:    for a in route["agents"]:
auto-agents/assets/synthesize.py:204:        status, text = _read_agent_result(run_dir, a)
auto-agents/assets/synthesize.py:209:    P.atomic_write_text(inter / "meta-synth-input.md", "\n".join(parts))
auto-agents/assets/synthesize.py:210:    P.atomic_write_text(inter / "host-instructions.md",
auto-agents/assets/synthesize.py:221:    "Here are the opening positions from the other agents:\n\n"
auto-agents/assets/synthesize.py:230:def synth_debate_prepare(run_dir: Path, route: dict) -> dict:
auto-agents/assets/synthesize.py:234:    inter = run_dir / "synthesis" / "intermediate"
auto-agents/assets/synthesize.py:237:    for a in route["agents"]:
auto-agents/assets/synthesize.py:238:        status, text = _read_agent_result(run_dir, a)
auto-agents/assets/synthesize.py:243:    P.atomic_write_text(inter / "debate-round-1.md", "\n".join(round1_concat))
auto-agents/assets/synthesize.py:255:def run_stage3(run_dir: Path) -> dict:
auto-agents/assets/synthesize.py:256:    P.check_sentinels(run_dir)
auto-agents/assets/synthesize.py:257:    route = _read_route(run_dir)
auto-agents/assets/synthesize.py:258:    method = route.get("synthesis_method", "inline")
auto-agents/assets/synthesize.py:259:    (run_dir / "synthesis").mkdir(parents=True, exist_ok=True)
auto-agents/assets/synthesize.py:260:    P.write_heartbeat(run_dir, stage=3, step=f"synth:{method}")
auto-agents/assets/synthesize.py:263:        final = synth_inline(run_dir, route)
auto-agents/assets/synthesize.py:264:        _write_method_md(run_dir, "inline", "Single agent; no merge.")
auto-agents/assets/synthesize.py:265:        P.atomic_write_text(run_dir / "synthesis" / "final.md", final)
auto-agents/assets/synthesize.py:266:        P.append_progress(run_dir, stage=3, step="synth:inline", status="ok")
auto-agents/assets/synthesize.py:270:        final, tally = synth_vote(run_dir, route)
auto-agents/assets/synthesize.py:271:        _write_method_md(run_dir, "vote",
auto-agents/assets/synthesize.py:272:                         f"Tally: `synthesis/intermediate/vote-tally.json`")
auto-agents/assets/synthesize.py:273:        P.atomic_write_json(run_dir / "synthesis" / "intermediate" /
auto-agents/assets/synthesize.py:275:        P.atomic_write_text(run_dir / "synthesis" / "final.md", final)
auto-agents/assets/synthesize.py:276:        P.append_progress(run_dir, stage=3, step="synth:vote",
auto-agents/assets/synthesize.py:282:        input_path = synth_meta_prepare(run_dir, route)
auto-agents/assets/synthesize.py:283:        _write_method_md(run_dir, "meta-synth",
auto-agents/assets/synthesize.py:285:        P.append_progress(run_dir, stage=3, step="synth:meta-synth",
auto-agents/assets/synthesize.py:292:        prep = synth_debate_prepare(run_dir, route)
auto-agents/assets/synthesize.py:293:        _write_method_md(run_dir, "debate",
auto-agents/assets/synthesize.py:295:        P.append_progress(run_dir, stage=3, step="synth:debate",
auto-agents/assets/synthesize.py:299:    P.append_progress(run_dir, stage=3, step=f"synth:{method}",
auto-agents/assets/synthesize.py:300:                      status="failed", detail="unknown synthesis method")
auto-agents/assets/synthesize.py:308:    out = run_stage3(args.run_dir)
auto-agents/assets/budget.py:3:Sums actual costs from audit.jsonl, compares against the caps in task.yaml,
auto-agents/assets/budget.py:7:Cost is reported in agents' meta.json — *if* the CLI prints token counts the
auto-agents/assets/budget.py:21:    """Extract per_call_cap_usd and total_cap_usd from task.yaml."""
auto-agents/assets/budget.py:38:def total_spent(run_dir: Path) -> float:
auto-agents/assets/budget.py:39:    audit = run_dir / "audit.jsonl"
auto-agents/assets/budget.py:54:def gate(run_dir: Path, *, estimated_next_call_usd: float) -> dict:
auto-agents/assets/budget.py:55:    per_call, total_cap = _read_yaml_floats(run_dir / "task.yaml")
auto-agents/assets/budget.py:56:    spent = total_spent(run_dir)
auto-agents/assets/budget.py:78:def reconcile(run_dir: Path) -> dict:
auto-agents/assets/budget.py:79:    """Compare per-agent estimates (cost_est_usd in meta.json) against actuals
auto-agents/assets/budget.py:80:    in audit.jsonl. Returns a summary; flags agents whose actuals exceed
auto-agents/assets/budget.py:82:    agents_dir = run_dir / "agents"
auto-agents/assets/budget.py:83:    if not agents_dir.exists():
auto-agents/assets/budget.py:84:        return {"agents": {}, "stale": []}
auto-agents/assets/budget.py:87:    for sub in agents_dir.iterdir():
auto-agents/assets/budget.py:90:        meta_p = sub / "meta.json"
auto-agents/assets/budget.py:102:    return {"agents": summary, "stale": stale}
auto-agents/assets/budget.py:112:        print(json.dumps(reconcile(args.run_dir), indent=2))
auto-agents/assets/budget.py:114:        decision = gate(args.run_dir, estimated_next_call_usd=args.estimated_next_call_usd)
auto-agents/assets/yaml_io.py:1:"""Minimal YAML dump/load for the flat task.yaml schema.
auto-agents/assets/yaml_io.py:129:    path.write_text(dump(d), encoding="utf-8")

exec
/bin/zsh -lc 'rg -n "AUTO_AGENTS_DEPTH|AUTO_AGENTS_HOST|version_check|--version|env_overrides|host" auto-agents/assets/*.py auto-agents/references/*.md' in /Volumes/ORICO/code/code6/auto-agents
 succeeded in 0ms:
auto-agents/assets/invoke_codex.py:26:def version_check() -> tuple[bool, str]:
auto-agents/assets/invoke_codex.py:30:            [cmd_head, "--version"],
auto-agents/assets/invoke_codex.py:43:def invoke(prompt: str, *, env_overrides: dict | None = None,
auto-agents/assets/invoke_codex.py:47:    if env_overrides:
auto-agents/assets/invoke_codex.py:48:        env.update(env_overrides)
auto-agents/assets/invoke_opencode.py:26:def version_check() -> tuple[bool, str]:
auto-agents/assets/invoke_opencode.py:30:            [cmd_head, "--version"],
auto-agents/assets/invoke_opencode.py:43:def invoke(prompt: str, *, env_overrides: dict | None = None,
auto-agents/assets/invoke_opencode.py:47:    if env_overrides:
auto-agents/assets/invoke_opencode.py:48:        env.update(env_overrides)
auto-agents/references/state-contract.md:59:host: claude                         # detected by host_detect.py — one of: claude | codex | opencode
auto-agents/references/state-contract.md:60:host_detection: env-var:CLAUDECODE   # how it was detected; for audit
auto-agents/references/state-contract.md:83:  "inline_host_used": false
auto-agents/references/state-contract.md:87:When the host answers inline:
auto-agents/references/state-contract.md:96:  "inline_host_used": true
auto-agents/references/state-contract.md:103:{"ts_utc":"2026-05-12T16:40:01Z","stage":0,"step":"host_detect","status":"ok","detail":"host=claude via CLAUDECODE"}
auto-agents/references/state-contract.md:168:- **opencode** — *unavailable* (no auth on this host).
auto-agents/references/state-contract.md:172:The host (claude) read both worker outputs and merged. No conflicts on §1; in §2
auto-agents/references/synthesis-methods.md:39:Two-round structured debate, host-moderated. Used when adversarial perspective is the point.
auto-agents/references/synthesis-methods.md:67:Final synthesis — **moderator pass** (host inline):
auto-agents/references/synthesis-methods.md:69:- The host (whichever CLI is reading this) reads both rounds and writes `final.md`:
auto-agents/references/synthesis-methods.md:73:  - One-sentence "moderator's read" of the strongest argument *(label it as the host's opinion, not as ground truth)*.
auto-agents/references/synthesis-methods.md:80:The host reads all worker outputs and writes one unified answer with attribution.
auto-agents/references/synthesis-methods.md:86:3. The host writes `final.md` directly, following the structure in `state-contract.md §"synthesis/final.md"`:
auto-agents/references/synthesis-methods.md:87:   - **# Answer** — the unified answer, written by the host. Inline-cite contributing agents where their wording or idea is the source.
auto-agents/references/synthesis-methods.md:89:   - **## Synthesis method: meta-synth** — one paragraph: what overlapped, what conflicted, how the host resolved conflicts.
auto-agents/references/synthesis-methods.md:92:The host does not paraphrase agent outputs unless one is clearly wrong; instead it weaves their contributions into one coherent answer. If two agents say similar things, the synthesis credits both and picks the clearer phrasing.
auto-agents/assets/route.py:27:    "quick-qa":    {"primary": ["__host__"],                            "synthesis": "inline"},
auto-agents/assets/route.py:61:def _select_agents(task_class: str, host: str, available: dict[str, bool],
auto-agents/assets/route.py:74:        if only != host and not available.get(only, False):
auto-agents/assets/route.py:78:                {only: "inline" if only == host else "subprocess"},
auto-agents/assets/route.py:84:        modes = {a: "inline" if a == host else "subprocess" for a in agents}
auto-agents/assets/route.py:88:    if primary == ["__host__"]:
auto-agents/assets/route.py:89:        return [host], {host: "inline"}, "inline", escalations
auto-agents/assets/route.py:94:        if host not in agents and available.get(host, False):
auto-agents/assets/route.py:95:            agents.insert(0, host)
auto-agents/assets/route.py:96:        modes = {a: "inline" if a == host else "subprocess" for a in agents}
auto-agents/assets/route.py:102:        if a == host:
auto-agents/assets/route.py:103:            chosen = host
auto-agents/assets/route.py:117:            {chosen: "inline" if chosen == host else "subprocess"},
auto-agents/assets/route.py:128:    host = task["host"]
auto-agents/assets/route.py:139:        task_class, host, available, mode,
auto-agents/assets/route.py:161:        "inline_host_used": agent_modes.get(host) == "inline",
auto-agents/references/routing-policy.md:8:- `task.yaml: host` — detected host CLI
auto-agents/references/routing-policy.md:23:     If <agent> == host:           agent_modes = {<agent>: "inline"}
auto-agents/references/routing-policy.md:34:4. Filter against host:
auto-agents/references/routing-policy.md:36:         Use all three regardless of host. The host's own contribution is "inline".
auto-agents/references/routing-policy.md:40:         If the host is the highest-priority agent → host answers inline, others not called.
auto-agents/references/routing-policy.md:44:     Remove any agent whose workers_available[<name>] == False (unless it's the host — host is always available).
auto-agents/references/routing-policy.md:50:     Force agents to all three available (host inline, workers subprocess), regardless of task_class.
auto-agents/references/routing-policy.md:86:- Never picks the host as a "subprocess" — host is always `"inline"`.
auto-agents/assets/invoke_claude.py:29:def version_check() -> tuple[bool, str]:
auto-agents/assets/invoke_claude.py:30:    """Run `claude --version`. Returns (ok, detail)."""
auto-agents/assets/invoke_claude.py:34:            [cmd_head, "--version"],
auto-agents/assets/invoke_claude.py:47:def invoke(prompt: str, *, env_overrides: dict | None = None,
auto-agents/assets/invoke_claude.py:55:    if env_overrides:
auto-agents/assets/invoke_claude.py:56:        env.update(env_overrides)
auto-agents/assets/host_detect.py:1:"""Detect which of {claude, codex, opencode} is the host CLI.
auto-agents/assets/host_detect.py:3:Three-tier algorithm. See ../references/host-cli-modes.md for the contract.
auto-agents/assets/host_detect.py:6:    host:        one of "claude" | "codex" | "opencode" | None
auto-agents/assets/host_detect.py:10:    refused:     bool — True iff AUTO_AGENTS_DEPTH >= 1 (recursion guard)
auto-agents/assets/host_detect.py:12:When host is None and refused is False, the caller (auth_check.py / Stage 0)
auto-agents/assets/host_detect.py:31:CACHE_PATH = Path.home() / ".config" / "auto-agents" / "host.yaml"
auto-agents/assets/host_detect.py:38:    """Returns (host_if_unique, all_matched_families, matched_env_var)."""
auto-agents/assets/host_detect.py:80:    """Walk parent chain; return (host_if_found, chain_for_audit)."""
auto-agents/assets/host_detect.py:99:    """Read ~/.config/auto-agents/host.yaml; return (host, prior_detection)."""
auto-agents/assets/host_detect.py:104:        # tiny YAML subset: host: <name> / confirmed_utc: <iso> / confirmed_by: <s>
auto-agents/assets/host_detect.py:110:        host = data.get("host")
auto-agents/assets/host_detect.py:112:        if host not in ENV_FAMILIES:
auto-agents/assets/host_detect.py:123:        return host, data.get("confirmed_by")
auto-agents/assets/host_detect.py:128:def write_cache(host: str, detection: str) -> None:
auto-agents/assets/host_detect.py:129:    """Persist confirmed host. Caller invokes this only after Tier 3 (user ask)."""
auto-agents/assets/host_detect.py:133:        f"host: {host}\n"
auto-agents/assets/host_detect.py:143:    depth = int(os.environ.get("AUTO_AGENTS_DEPTH", "0") or "0")
auto-agents/assets/host_detect.py:146:            "host": None, "detection": None, "candidates": [],
auto-agents/assets/host_detect.py:147:            "refused": True, "reason": f"AUTO_AGENTS_DEPTH={depth}",
auto-agents/assets/host_detect.py:151:    override = os.environ.get("AUTO_AGENTS_HOST", "").strip().lower()
auto-agents/assets/host_detect.py:154:            "host": override, "detection": "env-override",
auto-agents/assets/host_detect.py:159:    host, candidates, var = _env_tier()
auto-agents/assets/host_detect.py:160:    if host is not None:
auto-agents/assets/host_detect.py:162:            "host": host, "detection": f"env-var:{var}",
auto-agents/assets/host_detect.py:167:    host, chain = _ps_chain_tier()
auto-agents/assets/host_detect.py:168:    if host is not None:
auto-agents/assets/host_detect.py:170:            "host": host, "detection": f"ps-chain:{host}",
auto-agents/assets/host_detect.py:175:    host, prior = _cache_tier()
auto-agents/assets/host_detect.py:176:    if host is not None:
auto-agents/assets/host_detect.py:178:            "host": host, "detection": "cache",
auto-agents/assets/host_detect.py:185:        "host": None, "detection": None, "candidates": candidates,
auto-agents/assets/host_detect.py:194:    # exit code 0 if we know the host, 2 if we need to ask, 3 if refused
auto-agents/assets/host_detect.py:197:    sys.exit(0 if result.get("host") else 2)
auto-agents/assets/dispatch.py:3:Each subprocess worker gets AUTO_AGENTS_DEPTH = parent+1 in its env so any
auto-agents/assets/dispatch.py:6:The host agent (route.agent_modes[host] == "inline") does NOT get spawned
auto-agents/assets/dispatch.py:7:here. Instead its `agents/<host>/invocation.md` is written and a placeholder
auto-agents/assets/dispatch.py:9:the host to fill `agents/<host>/result.md` itself, then re-invoke dispatch.py
auto-agents/assets/dispatch.py:10:which will mark host status="ok" once result.md is non-empty.
auto-agents/assets/dispatch.py:86:    depth = int(os.environ.get("AUTO_AGENTS_DEPTH", "0") or "0")
auto-agents/assets/dispatch.py:87:    env_overrides = {"AUTO_AGENTS_DEPTH": str(depth + 1)}
auto-agents/assets/dispatch.py:88:    result = mod.invoke(prompt, env_overrides=env_overrides)
auto-agents/assets/dispatch.py:123:def _stage_inline_host(run_dir: Path, host: str, prompt: str) -> dict:
auto-agents/assets/dispatch.py:124:    """Write the invocation but leave result.md to be filled by the host model."""
auto-agents/assets/dispatch.py:125:    agent_dir = run_dir / "agents" / host
auto-agents/assets/dispatch.py:128:        f"# Inline invocation for host `{host}`\n\n"
auto-agents/assets/dispatch.py:129:        f"The host agent should write its answer to `result.md` in this folder,\n"
auto-agents/assets/dispatch.py:135:        "agent": host, "status": "pending",
auto-agents/assets/dispatch.py:143:    P.append_progress(run_dir, stage=2, step=f"dispatch:{host}",
auto-agents/assets/dispatch.py:145:                      detail="host writes result.md, then re-run dispatch")
auto-agents/assets/dispatch.py:177:            results[agent] = _stage_inline_host(run_dir, agent, prompt)
auto-agents/assets/auth_check.py:1:"""Stage 0 — detect host, verify worker CLIs, write task.yaml + workers_available.
auto-agents/assets/auth_check.py:3:Usage (from inside the host CLI):
auto-agents/assets/auth_check.py:11:Reads ../references/host-cli-modes.md for the algorithm.
auto-agents/assets/auth_check.py:20:import host_detect
auto-agents/assets/auth_check.py:37:               host_override: str | None = None) -> dict:
auto-agents/assets/auth_check.py:40:    P.write_heartbeat(run_dir, stage=0, step="host_detect")
auto-agents/assets/auth_check.py:42:    # --- host detection ------------------------------------------------------
auto-agents/assets/auth_check.py:43:    det = host_detect.detect()
auto-agents/assets/auth_check.py:45:        P.append_progress(run_dir, stage=0, step="host_detect",
auto-agents/assets/auth_check.py:48:    host = host_override or det.get("host")
auto-agents/assets/auth_check.py:49:    detection = "manual-override" if host_override else det.get("detection")
auto-agents/assets/auth_check.py:50:    if host is None:
auto-agents/assets/auth_check.py:51:        P.append_progress(run_dir, stage=0, step="host_detect",
auto-agents/assets/auth_check.py:53:        # Caller (the host CLI's tool-using agent) must ask the user and re-invoke.
auto-agents/assets/auth_check.py:55:    P.append_progress(run_dir, stage=0, step="host_detect",
auto-agents/assets/auth_check.py:56:                      status="ok", detail=f"host={host} via {detection}")
auto-agents/assets/auth_check.py:63:        if name == host:
auto-agents/assets/auth_check.py:65:            workers_detail[name] = "host (inline)"
auto-agents/assets/auth_check.py:67:        ok, detail = mod.version_check()
auto-agents/assets/auth_check.py:80:        "host": host,
auto-agents/assets/auth_check.py:81:        "host_detection": detection,
auto-agents/assets/auth_check.py:103:    ap.add_argument("--host-override", default=None,
auto-agents/assets/auth_check.py:114:        host_override=args.host_override,
auto-agents/references/host-cli-modes.md:3:The skill runs inside one of `claude` / `codex` / `opencode`. That parent is the **host**. The other two are candidate **workers**. This file is the single source of truth for: how to detect the host, how to verify worker auth, and how to prevent recursion.
auto-agents/references/host-cli-modes.md:5:## Three-tier host detection
auto-agents/references/host-cli-modes.md:7:Implemented in `assets/host_detect.py`. Run **once** at Stage 0 and write the result to `task.yaml: host`. Algorithm:
auto-agents/references/host-cli-modes.md:11:Each host CLI is expected to set a distinctive env var when it spawns a subprocess (the skill's helper scripts). Known candidates as of this writing:
auto-agents/references/host-cli-modes.md:21:- **Exactly one family matches** → host is that one. Record `host_detection: "env-var:<NAME>"`.
auto-agents/references/host-cli-modes.md:23:- **≥2 families match** → suspicious (possible nested invocation or leaked env). Check `AUTO_AGENTS_DEPTH`: if ≥1, we are nested → refuse the skill (recursion guard). Otherwise fall through to Tier 2 and let process-chain disambiguate.
auto-agents/references/host-cli-modes.md:29:- If exactly one of `{claude, codex, opencode}` appears in the chain → that's the host. Record `host_detection: "ps-chain:<NAME>"`.
auto-agents/references/host-cli-modes.md:31:- If more than one appears → that's a real nested-invocation case. Pick the **closest** (smallest depth) as host but log a `progress.jsonl` warning row.
auto-agents/references/host-cli-modes.md:49:1. Read `~/.config/auto-agents/host.yaml` if it exists. Schema:
auto-agents/references/host-cli-modes.md:51:   host: claude
auto-agents/references/host-cli-modes.md:55:   If the cache is < 30 days old, use the cached host and record `host_detection: "cache"`.
auto-agents/references/host-cli-modes.md:56:2. Otherwise: prompt the user (via the host's AskUserQuestion or equivalent) with the question "Which CLI are you running this from? (claude / codex / opencode)" and write the answer to both `task.yaml` and `~/.config/auto-agents/host.yaml`.
auto-agents/references/host-cli-modes.md:60:If the env var `AUTO_AGENTS_HOST` is set to one of `claude|codex|opencode`, that wins over all three tiers. Record `host_detection: "env-override:AUTO_AGENTS_HOST"`.
auto-agents/references/host-cli-modes.md:66:Before doing anything else, Stage 0 reads `AUTO_AGENTS_DEPTH`. Defaults to `0`. If `≥ 1`, the skill refuses immediately and writes:
auto-agents/references/host-cli-modes.md:69:{"status":"refused","reason":"AUTO_AGENTS_DEPTH=1 (already inside auto-agents)"}
auto-agents/references/host-cli-modes.md:72:When dispatching a worker, the dispatcher sets `AUTO_AGENTS_DEPTH = <current+1>` in the subprocess env. This makes the guard *transitive* — a worker that itself invokes auto-agents will refuse.
auto-agents/references/host-cli-modes.md:74:The host never spawns itself as a worker. The router enforces this: if the matrix says the best agent for task class X is the host, `route.json: agent_modes` records `"<host>": "inline"` and Stage 2 skips subprocess dispatch for that agent.
auto-agents/references/host-cli-modes.md:78:Stage 0 verifies each candidate worker before letting the router pick it. For each of `claude` / `codex` / `opencode` that is **not** the host:
auto-agents/references/host-cli-modes.md:81:2. **Version handshake?** Run `<cli> --version` with a 10s timeout. If exit ≠ 0 → `false`, reason `"version-failed"`.
auto-agents/references/host-cli-modes.md:88:## Inline-host execution
auto-agents/references/host-cli-modes.md:90:When the router selects the host (e.g. host=claude, task=code-write), Stage 2 does **not** spawn a subprocess. Instead:
auto-agents/references/host-cli-modes.md:92:1. The skill helper writes `agents/<host>/invocation.md` with the prompt.
auto-agents/references/host-cli-modes.md:93:2. The host (the agent reading SKILL.md) answers the prompt itself, in the same conversation.
auto-agents/references/host-cli-modes.md:94:3. The skill helper captures that answer to `agents/<host>/result.md` via a follow-up write.
auto-agents/references/host-cli-modes.md:100:The user asked: can the skill auto-detect host? Yes — env-var Tier 1 will hit cleanly when the CLI cooperates. Tier 2 catches CLIs that don't set env vars but do show up in `ps` (most do). Tier 3 is the truthful fallback for esoteric setups — *one* prompt, cached for 30 days. No silent guessing: every detection records `host_detection` in `task.yaml` so the user can audit.
auto-agents/assets/synthesize.py:6:  - meta-synth  : host-written unified answer with attribution (DEFAULT for idea)
auto-agents/assets/synthesize.py:8:                  invocations and the moderator template; the host fills in the
auto-agents/assets/synthesize.py:11:The host model is responsible for the actual *writing* in meta-synth and the
auto-agents/assets/synthesize.py:73:            lines.append(f"- **{a}** — *pending* (host inline; result.md not yet written)")
auto-agents/assets/synthesize.py:198:    """Build meta-synth-input.md and write host instructions. Returns the inputs
auto-agents/assets/synthesize.py:199:    path so the host can read it. The host then writes final.md itself."""
auto-agents/assets/synthesize.py:210:    P.atomic_write_text(inter / "host-instructions.md",
auto-agents/assets/synthesize.py:249:        "next_step": "host runs dispatch.py round 2 with augmented prompts, "
auto-agents/assets/synthesize.py:286:                          status="pending-host",
auto-agents/assets/synthesize.py:287:                          detail="meta-synth-input.md ready; host writes final.md")
auto-agents/assets/synthesize.py:288:        return {"status": "pending-host", "method": "meta-synth",
auto-agents/assets/synthesize.py:310:    return 0 if out.get("status") in ("ok", "pending-host", "pending-round2") else 1
auto-agents/references/integrity-rules.md:36:`auth_check.py` runs in Stage 0 against every candidate worker. If a worker's `--version` or `--help` fails, the worker is marked unavailable and the router cannot pick it.
auto-agents/references/integrity-rules.md:40:Edge: some CLIs don't have a free `--version`. For those, record `auth_checked: "deferred"`. The first real call surfaces auth — at most one wasted call.
auto-agents/references/integrity-rules.md:60:`AUTO_AGENTS_DEPTH` is the source of truth:
auto-agents/references/integrity-rules.md:67:The host **never** spawns itself as a worker. `route.json: agent_modes[host] == "inline"` always.
auto-agents/references/integrity-rules.md:84:- The host model can crash, the parent shell can die, the laptop can reboot.
auto-agents/references/integrity-rules.md:87:Specifically: every decision, every cost number, every agent assignment is on disk before the next micro-step starts. If you find yourself wanting to "remember" something in the host's context window for the next stage, it goes on disk instead.
auto-agents/references/agent-matrix.md:15:| `quick-qa`      | trivial single-shot Q&A                                      | host CLI                         | inline (host)     |
auto-agents/references/agent-matrix.md:25:7. Else: `quick-qa` (host inline)
auto-agents/references/agent-matrix.md:27:When the **host** is one of the listed primaries, it answers inline — no subprocess spawn. E.g. host=claude + class=code-write → inline.
auto-agents/references/agent-matrix.md:29:For `idea` and `debate`, **all three agents are called regardless of host**, because the value is the multi-perspective spread.
auto-agents/references/agent-matrix.md:39:- Auth: `ANTHROPIC_API_KEY` env or `~/.claude/` config; the wrapper checks `claude --version` to confirm the binary is present.
auto-agents/references/agent-matrix.md:47:- Auth: `OPENAI_API_KEY` env or `~/.codex/auth.json`; wrapper checks `codex --version`.
auto-agents/references/agent-matrix.md:55:- Auth: depends on the configured provider (`~/.config/opencode/`). Wrapper checks `opencode --version`.

web search: 
web search: Claude Code CLI reference print mode -p official docs
web search: 
web search: site:developers.openai.com/codex/noninteractive "codex exec"
web search: 
web search: https://github.com/openai/codex/blob/main/codex-rs/README.md
web search: 
web search: https://developers.openai.com/codex/noninteractive
web search: 
web search: 'codex exec' in https://developers.openai.com/codex/noninteractive
codex
**Integrity Rules**

- Critical - Rule #7/#8: [dispatch.py:123](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/dispatch.py:123) stages inline host as `pending`, but no code ever marks it `ok`; [synthesize.py:99](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/synthesize.py:99) then emits a “No answer” final for common host-inline routes.
- Critical - Rule #3: [dispatch.py:88](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/dispatch.py:88) invokes workers without calling `budget.gate`; per-call/total caps are not enforced before paid subprocesses.
- Important - Rule #1: [route.py:91](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/route.py:91) silently drops unavailable `idea`/`debate` agents instead of escalating, despite those classes requiring all three.
- Important - Rule #1: [route.py:82](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/route.py:82) `mode=multi` silently filters to available agents; if the user asked all three, missing workers are not surfaced.
- Important - Rule #3: [route.py:142](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/route.py:142) checks aggregate estimate against `per_call_cap * n`, not each agent estimate ×2; [route.py:131](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/route.py:131) never reads `total_cap_usd` or prior audit actuals.
- Important - Rule #3: [budget.py:65](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/budget.py:65) also omits the required ×2 headroom; [budget.py:78](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/budget.py:78) returns stale agents but writes no `progress.jsonl` warning/escalation.
- Important - Rule #4: [auth_check.py:67](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/auth_check.py:67) only runs wrapper `--version`; there is no auth handshake, so auth failure is discovered mid-task.
- Important - Rule #2: [synthesize.py:107](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/synthesize.py:107) copies inline agent text into `# Answer` without per-sentence/paragraph attribution.
- Important - Rule #7: [dispatch.py:91](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/dispatch.py:91) writes `stdout.log`/`stderr.log` non-atomically, violating the non-append write rule.
- Important - Rule #7: [dispatch.py:83](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/dispatch.py:83) records only `started` before the paid call; crash after subprocess success but before `meta.json`/`audit.jsonl` causes re-dispatch and double charge.
- Important - Rule #7: [progress.py:83](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/progress.py:83) raises on `STOP`, but callers do not catch it or append the required `stopped-by-user` row.

**State Contract Drift**

- Important: [auth_check.py:88](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/auth_check.py:88) writes `task.yaml: workers_detail`, not listed in `state-contract.md`.
- Important: [route.py:162](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/route.py:162) writes `route.json: escalations`, not listed in the route schema.
- Important: [dispatch.py:107](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/dispatch.py:107) writes `meta.json.cost_est_usd = null`; schema shows a numeric cost estimate.
- Important: [progress.py:45](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/progress.py:45) allows `audit.jsonl.cost_actual_usd = null`; schema shows a numeric actual.
- Minor: [synthesize.py:210](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/synthesize.py:210) writes `synthesis/intermediate/host-instructions.md`, not listed.
- Important: `synthesis/intermediate/debate-round-2.md` is listed in the contract but no asset writes it.
- Important: `hand_off.md` is listed in the contract but no asset writes it.

**Resume / Idempotency**

- Important: [auth_check.py:90](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/auth_check.py:90) rewrites immutable `task.yaml` on rerun, including new `created_utc`.
- Important: [route.py:164](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/route.py:164) rewrites immutable `route.json` on rerun.
- Important: [dispatch.py:49](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/dispatch.py:49) chooses attempt dir by count; crash after `target.mkdir()` makes the next rerun fail on the existing dir.
- Important: [dispatch.py:166](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/dispatch.py:166) skips `status=ok` without verifying `result.md` exists or that `audit.jsonl` has the call row.
- Important: [synthesize.py:281](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/synthesize.py:281) meta-synth reruns only prepare inputs and append `pending-host`; existing `final.md` is not validated or used.
- Minor: [synthesize.py:273](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/synthesize.py:273) vote writes into `synthesis/intermediate` without ensuring that directory exists.

**Cross-Script Consistency**

- Critical: [route.py:87](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/route.py:87) treats unknown modes, including `dry-run`, as `auto`; [dispatch.py:179](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/dispatch.py:179) will spawn subprocesses.
- Critical: [supervisor.sh:116](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/supervisor.sh:116) calls shell function `run_inner_once` inside `bash -c` without exporting it; supervisor will loop/restart instead of running the pipeline.
- Important: [dispatch.py:7](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/dispatch.py:7) says rerun marks inline host `ok`; implementation at [dispatch.py:176](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/dispatch.py:176) restages `pending`.
- Important: [synthesize.py:291](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/synthesize.py:291) debate only prepares round 1 after dispatch; dispatch has no round-1 suffix or round-2 dispatch path.

**CLI Invocation**

- No known flag drift found for defaults: `claude -p`, `codex exec`, and `opencode run` match current docs checked: [Claude CLI](https://code.claude.com/docs/en/cli-reference), [Codex non-interactive](https://developers.openai.com/codex/noninteractive), [OpenCode CLI](https://opencode.ai/docs/cli/).

**Recursion Guard**

- Important: auto-agents child recursion is caught when dispatch sets [dispatch.py:87](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/dispatch.py:87). But nested host chains without `AUTO_AGENTS_DEPTH` are not detected: [host_detect.py:90](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/host_detect.py:90) returns the first matching process instead of detecting multiple hosts/logging a warning.
- Minor: [host_detect.py:143](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/host_detect.py:143) crashes on non-integer `AUTO_AGENTS_DEPTH`.

**Cost Gate Edge Cases**

- Important: missing `audit.jsonl` returns `$0` spent: [budget.py:40](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/budget.py:40).
- Important: malformed JSON audit rows are silently ignored: [budget.py:46](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/budget.py:46).
- Important: `cost_actual_usd: null` is ignored: [budget.py:48](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/budget.py:48). Since dispatch always writes null at [dispatch.py:116](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/dispatch.py:116), actual spend never accumulates.
- Minor: non-numeric non-null `cost_actual_usd` raises uncaught `ValueError` at [budget.py:50](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/budget.py:50).
tokens used
151,417
**Integrity Rules**

- Critical - Rule #7/#8: [dispatch.py:123](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/dispatch.py:123) stages inline host as `pending`, but no code ever marks it `ok`; [synthesize.py:99](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/synthesize.py:99) then emits a “No answer” final for common host-inline routes.
- Critical - Rule #3: [dispatch.py:88](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/dispatch.py:88) invokes workers without calling `budget.gate`; per-call/total caps are not enforced before paid subprocesses.
- Important - Rule #1: [route.py:91](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/route.py:91) silently drops unavailable `idea`/`debate` agents instead of escalating, despite those classes requiring all three.
- Important - Rule #1: [route.py:82](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/route.py:82) `mode=multi` silently filters to available agents; if the user asked all three, missing workers are not surfaced.
- Important - Rule #3: [route.py:142](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/route.py:142) checks aggregate estimate against `per_call_cap * n`, not each agent estimate ×2; [route.py:131](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/route.py:131) never reads `total_cap_usd` or prior audit actuals.
- Important - Rule #3: [budget.py:65](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/budget.py:65) also omits the required ×2 headroom; [budget.py:78](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/budget.py:78) returns stale agents but writes no `progress.jsonl` warning/escalation.
- Important - Rule #4: [auth_check.py:67](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/auth_check.py:67) only runs wrapper `--version`; there is no auth handshake, so auth failure is discovered mid-task.
- Important - Rule #2: [synthesize.py:107](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/synthesize.py:107) copies inline agent text into `# Answer` without per-sentence/paragraph attribution.
- Important - Rule #7: [dispatch.py:91](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/dispatch.py:91) writes `stdout.log`/`stderr.log` non-atomically, violating the non-append write rule.
- Important - Rule #7: [dispatch.py:83](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/dispatch.py:83) records only `started` before the paid call; crash after subprocess success but before `meta.json`/`audit.jsonl` causes re-dispatch and double charge.
- Important - Rule #7: [progress.py:83](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/progress.py:83) raises on `STOP`, but callers do not catch it or append the required `stopped-by-user` row.

**State Contract Drift**

- Important: [auth_check.py:88](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/auth_check.py:88) writes `task.yaml: workers_detail`, not listed in `state-contract.md`.
- Important: [route.py:162](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/route.py:162) writes `route.json: escalations`, not listed in the route schema.
- Important: [dispatch.py:107](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/dispatch.py:107) writes `meta.json.cost_est_usd = null`; schema shows a numeric cost estimate.
- Important: [progress.py:45](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/progress.py:45) allows `audit.jsonl.cost_actual_usd = null`; schema shows a numeric actual.
- Minor: [synthesize.py:210](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/synthesize.py:210) writes `synthesis/intermediate/host-instructions.md`, not listed.
- Important: `synthesis/intermediate/debate-round-2.md` is listed in the contract but no asset writes it.
- Important: `hand_off.md` is listed in the contract but no asset writes it.

**Resume / Idempotency**

- Important: [auth_check.py:90](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/auth_check.py:90) rewrites immutable `task.yaml` on rerun, including new `created_utc`.
- Important: [route.py:164](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/route.py:164) rewrites immutable `route.json` on rerun.
- Important: [dispatch.py:49](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/dispatch.py:49) chooses attempt dir by count; crash after `target.mkdir()` makes the next rerun fail on the existing dir.
- Important: [dispatch.py:166](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/dispatch.py:166) skips `status=ok` without verifying `result.md` exists or that `audit.jsonl` has the call row.
- Important: [synthesize.py:281](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/synthesize.py:281) meta-synth reruns only prepare inputs and append `pending-host`; existing `final.md` is not validated or used.
- Minor: [synthesize.py:273](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/synthesize.py:273) vote writes into `synthesis/intermediate` without ensuring that directory exists.

**Cross-Script Consistency**

- Critical: [route.py:87](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/route.py:87) treats unknown modes, including `dry-run`, as `auto`; [dispatch.py:179](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/dispatch.py:179) will spawn subprocesses.
- Critical: [supervisor.sh:116](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/supervisor.sh:116) calls shell function `run_inner_once` inside `bash -c` without exporting it; supervisor will loop/restart instead of running the pipeline.
- Important: [dispatch.py:7](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/dispatch.py:7) says rerun marks inline host `ok`; implementation at [dispatch.py:176](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/dispatch.py:176) restages `pending`.
- Important: [synthesize.py:291](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/synthesize.py:291) debate only prepares round 1 after dispatch; dispatch has no round-1 suffix or round-2 dispatch path.

**CLI Invocation**

- No known flag drift found for defaults: `claude -p`, `codex exec`, and `opencode run` match current docs checked: [Claude CLI](https://code.claude.com/docs/en/cli-reference), [Codex non-interactive](https://developers.openai.com/codex/noninteractive), [OpenCode CLI](https://opencode.ai/docs/cli/).

**Recursion Guard**

- Important: auto-agents child recursion is caught when dispatch sets [dispatch.py:87](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/dispatch.py:87). But nested host chains without `AUTO_AGENTS_DEPTH` are not detected: [host_detect.py:90](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/host_detect.py:90) returns the first matching process instead of detecting multiple hosts/logging a warning.
- Minor: [host_detect.py:143](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/host_detect.py:143) crashes on non-integer `AUTO_AGENTS_DEPTH`.

**Cost Gate Edge Cases**

- Important: missing `audit.jsonl` returns `$0` spent: [budget.py:40](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/budget.py:40).
- Important: malformed JSON audit rows are silently ignored: [budget.py:46](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/budget.py:46).
- Important: `cost_actual_usd: null` is ignored: [budget.py:48](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/budget.py:48). Since dispatch always writes null at [dispatch.py:116](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/dispatch.py:116), actual spend never accumulates.
- Minor: non-numeric non-null `cost_actual_usd` raises uncaught `ValueError` at [budget.py:50](/Volumes/ORICO/code/code6/auto-agents/auto-agents/assets/budget.py:50).
