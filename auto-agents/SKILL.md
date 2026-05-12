---
name: auto-agents
description: Multi-agent CLI orchestrator. Activate when the user wants one task answered by routing or fanning out across multiple coding CLIs (claude, codex, opencode) instead of a single agent. Detects which CLI is the host, classifies the task (code-write / code-review / math / idea / research / QA), picks the best worker(s) per the agent-matrix, dispatches them as subprocesses with budget caps, captures stdout/stderr/meta to disk under runs/<task_id>/, and synthesizes a single answer (vote / debate / meta-synth). All state is on disk, micro-steps are idempotent, resume-by-default. Do NOT trigger for single-CLI tasks where the host can answer directly without fan-out — those should stay inline.
---

# auto-agents — multi-CLI router & synthesizer

You sit on top of three coding CLIs (`claude`, `codex`, `opencode`) and route one task across them. The CLI that invokes *you* is the **host**; the other two are **workers**. You never spawn the host as a worker (recursion guard).

## When to trigger

YES, run this skill when:

- User asks "give me <X> using the best CLI for this" and the host might not be best.
- User asks for multi-perspective answers ("get ideas from all three / brainstorm with multiple agents / which CLI is right for this").
- User asks for adversarial review ("have <other CLI> audit this") — even with one named worker.

NO, do not run this skill when:

- The host can clearly handle the task and the user did not ask for fan-out (writing one function in Claude Code, debugging one bug in Codex). The router will just route everything back to the host, wasting setup.
- `AUTO_AGENTS_DEPTH` ≥ 1 in the environment (you are already inside an auto-agents call — refuse).

## Stage map

```
Stage 0 — Setup        (assets/auth_check.py)   detect host, verify worker CLIs+auth, write task.yaml
Stage 1 — Route        (assets/route.py)        classify task, select agents, write route.json
Stage 2 — Dispatch     (assets/dispatch.py)     spawn worker subprocesses, capture to agents/<name>/
Stage 3 — Synthesize   (assets/synthesize.py)   vote / debate / meta-synth → synthesis/final.md
Stage 4 — Hand-off     (inline)                 write hand_off.md, print summary, exit cleanly
```

Each stage writes a `progress.jsonl` row at start and at completion. Re-running the skill re-reads disk and continues from the last completed micro-step.

## State contract — do not invent paths

Every task gets `runs/<task_id>/` where `task_id = YYYY-MM-DD-HHmm-<kebab-slug>`. The full schema is in `references/state-contract.md`. **Never invent a directory the contract doesn't list.**

Files every stage reads first:

- `runs/<task_id>/task.yaml` — host CLI, original prompt, budget cap, deadline, mode flags
- `runs/<task_id>/.heartbeat` — stage / pid / ts_utc (user can `cat` to peek)
- `runs/<task_id>/progress.jsonl` — append-only micro-step log; resume reads its tail
- `runs/<task_id>/route.json` — written by Stage 1, consumed by Stage 2+

`runs/` is gitignored. Never commit task output back into the repo.

## The host-CLI rule overrides everything

The host CLI is whichever of `claude` / `codex` / `opencode` invoked this skill. Read `references/host-cli-modes.md` once at Stage 0. Key invariants:

1. The host **never** spawns itself as a worker. If the router picks the host's best-fit task class, the host answers inline and `route.json` records `agents: [<host>]` with `mode: inline`.
2. Each worker subprocess runs with `AUTO_AGENTS_DEPTH = <current+1>`. If a worker tries to recursively invoke auto-agents, it refuses (see "When to trigger").
3. Worker auth is checked in Stage 0 by running each worker's `--version` (or equivalent). If a worker has no credentials, escalate — do NOT silently route to a different agent.

## Integrity rules — non-negotiable

Read `references/integrity-rules.md`. Eight rules: no silent agent swap, attribution mandatory in `final.md`, budget gate per-call + per-task, auth check upfront, no CLI flag fabrication, recursion guard, idempotent micro-steps, all state on disk.

The orchestrator's "stop and ask the human" checkpoints:

- Before any single call estimated to cost > `task.yaml: per_call_cap_usd` (default $0.50)
- Before total task spend would exceed `task.yaml: total_cap_usd` (default $2.00)
- When a chosen worker's `--version` check fails (auth or missing binary)
- When debate or vote synthesis cannot reach a conclusion after the configured rounds

## When to load which reference

| If you are… | Load |
|---|---|
| classifying a task & picking agents | `references/agent-matrix.md`, `references/routing-policy.md` |
| spawning a worker CLI | `references/host-cli-modes.md` (for the recursion + auth rule) |
| merging outputs | `references/synthesis-methods.md` |
| writing files under `runs/` | `references/state-contract.md` |
| about to take any irreversible action (cost > cap, silent fallback) | `references/integrity-rules.md` |

Default behavior: load `state-contract.md` and `integrity-rules.md` early; load the others on demand per the table.

## Idempotency contract

A re-run after a crash:

1. Reads `runs/<task_id>/.heartbeat` to find the last stage.
2. Reads `runs/<task_id>/progress.jsonl` tail to find the last completed micro-step.
3. For each worker in `route.json`: if `agents/<name>/meta.json` shows `status: ok`, skip; if `status: pending` or missing, re-dispatch.
4. Synthesis re-reads all `agents/*/result.md` and rewrites `synthesis/final.md` atomically (`.tmp` + rename).

Append-only files (`progress.jsonl`, `audit.jsonl`) are never rewritten — resume just appends a `resumed` row.

## Modes

`task.yaml: mode` controls behavior:

- `auto` (default): router decides agents and synthesis method.
- `multi`: force all three agents (router still chooses synthesis method).
- `single:<agent>`: skip router, dispatch only the named agent.
- `dry-run`: write `route.json` and per-agent `invocation.md`, but do NOT spawn subprocesses. Print the planned calls.

## What you must not do

- Do not call a worker CLI that the user did not authorize on this machine. Read `references/host-cli-modes.md` for the auth-check protocol.
- Do not fabricate CLI flags. The wrappers (`assets/invoke_*.py`) hold known-good invocation patterns; if those fail, surface the error — do NOT guess flags.
- Do not pretend a worker answered when it crashed. `synthesis/final.md` must list every agent that *successfully* contributed and every agent that failed (with the error class).
- Do not auto-pick a final answer when synthesis is split. Escalate.
