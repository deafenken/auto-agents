# Integrity rules — non-negotiable

Eight rules. Every code path in this skill must satisfy them, or escalate to the user under them. Loosening these to "make the workflow easier" is a bug.

## 1. No silent agent swap

If the router's chosen agent is unavailable (missing binary, auth failure, exceeded budget), the skill **stops and asks the user**. It never silently routes to a different agent.

- Allowed: "claude is unavailable; use codex instead? (y/n)"
- Forbidden: writing `route.json` with `["codex"]` when the user's prompt implied claude was wanted, without surfacing the swap.

## 2. Attribution mandatory in `final.md`

Every sentence (or paragraph) in `synthesis/final.md` that is materially derived from a specific agent's output names that agent. Verbatim quotes are fenced and attributed.

- Allowed: "Claude proposed using a Bloom filter (agents/claude/result.md §2); codex agreed and added a size estimate (agents/codex/result.md §3)."
- Forbidden: paraphrasing one agent's solution as if it were the synthesizer's own.

Why: when the user reads `final.md`, they must be able to trace any claim back to a single source agent's raw output.

## 3. Budget gate — per-call and per-task

Two caps in `task.yaml`: `per_call_cap_usd` (default $0.50) and `total_cap_usd` (default $2.00).

Before any subprocess dispatch:

1. Use the matrix's per-agent estimate × 2 (worst-case headroom) → if > per_call_cap_usd, escalate.
2. Sum prior `audit.jsonl` actuals + this call's estimate → if > total_cap_usd, escalate.

The estimates in `agent-matrix.md` are rough — `budget.py` reconciles with `audit.jsonl` actuals so subsequent estimates drift toward reality.

If a call exceeds its estimate by >2× post-hoc, write a warning row to `progress.jsonl`. Three such warnings in one task → escalate "estimates are unreliable, pause?"

## 4. Auth check upfront

`auth_check.py` runs in Stage 0 against every candidate worker. If a worker's `--version` or `--help` fails, the worker is marked unavailable and the router cannot pick it.

Forbidden: spawning a worker without an upfront auth check. We are not "discovering" auth failure mid-task by burning money on a doomed call.

Edge: some CLIs don't have a free `--version`. For those, record `auth_checked: "deferred"`. The first real call surfaces auth — at most one wasted call.

## 5. No CLI flag fabrication

`assets/invoke_*.py` hold known-good invocation patterns. If those patterns fail on a user's machine, the wrapper surfaces the raw error — it does **not** try alternate flags it has not been told about.

Forbidden:

```python
# DO NOT do this
try:
    subprocess.run(["codex", "exec", prompt])
except:
    subprocess.run(["codex", "-p", prompt])   # guessing!
```

Allowed: read `AUTO_AGENTS_CODEX_CMD` env override, then use exactly one default command. If both fail, escalate to the user with the raw stderr.

## 6. Recursion guard

`AUTO_AGENTS_DEPTH` is the source of truth:

- Stage 0 reads it. If ≥ 1, refuse the skill.
- Stage 2 sets it to `current+1` in every worker subprocess env.

A worker that itself triggers auto-agents will refuse via Stage 0 check, even if the env var ladder is wrong elsewhere.

The host **never** spawns itself as a worker. `route.json: agent_modes[host] == "inline"` always.

## 7. Idempotent micro-steps

Every step in `progress.jsonl` must be re-runnable. Re-running the skill after a crash:

- Re-reads `task.yaml` (immutable, safe).
- Skips workers with `meta.json: status == "ok"`.
- Re-dispatches workers with `status` ∈ `{pending, failed, timed-out}` (the old `result.md` is moved to `agents/<name>/attempts/<N>/` first).
- Rewrites `synthesis/final.md` atomically if all worker results changed.

A step that mutates state without writing a `progress.jsonl` row is a bug. A step that rewrites an append-only file is a bug.

## 8. All state on disk

No information needed for resume lives in agent memory. After Stage 2 finishes:

- The host model can crash, the parent shell can die, the laptop can reboot.
- A fresh skill invocation reads `runs/<task_id>/` and proceeds from the last completed micro-step.

Specifically: every decision, every cost number, every agent assignment is on disk before the next micro-step starts. If you find yourself wanting to "remember" something in the host's context window for the next stage, it goes on disk instead.

---

## Enforcement

These rules are enforced *by the skill author*, not at runtime. There is no validator binary; the SKILL.md prompt makes them part of the contract. If a future PR introduces a code path that violates one of these, that PR is the bug — the skill is the spec.
