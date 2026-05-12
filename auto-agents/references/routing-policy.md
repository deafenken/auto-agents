# Routing policy

This file says how `assets/route.py` picks agents from a task description. Read `agent-matrix.md` first — this file is the algorithm, that one is the data.

## Inputs

- `task.yaml: prompt` — the user's free-form task
- `task.yaml: host` — detected host CLI
- `task.yaml: workers_available` — which workers passed the auth check
- `task.yaml: mode` — `auto` | `multi` | `single:<agent>` | `dry-run`
- `task.yaml: per_call_cap_usd`, `total_cap_usd`

## Outputs

`runs/<task_id>/route.json` (schema in `state-contract.md`).

## Algorithm

```
1. If mode == "single:<agent>":
     agents = [<agent>]
     synthesis_method = "inline"
     If <agent> == host:           agent_modes = {<agent>: "inline"}
     Elif workers_available[<agent>] == False:
         escalate("user requested <agent> but it's unavailable")
     Else:
         agent_modes = {<agent>: "subprocess"}
     return.

2. Classify task_class from prompt using rules in agent-matrix.md §"Classification heuristics".

3. Look up default agents for task_class from the matrix.

4. Filter against host:
     - If task_class is "idea" or "debate":
         Use all three regardless of host. The host's own contribution is "inline".
         Other two are "subprocess".
     - Else:
         Take the matrix's priority list.
         If the host is the highest-priority agent → host answers inline, others not called.
         Else → call the highest-priority available worker as subprocess.

5. Filter against availability:
     Remove any agent whose workers_available[<name>] == False (unless it's the host — host is always available).
     If the *primary* agent for this task_class is unavailable AND mode == "auto":
         escalate("primary agent <X> unavailable, secondary <Y> would be used — confirm?")
     Do NOT silently substitute.

6. Apply mode == "multi":
     Force agents to all three available (host inline, workers subprocess), regardless of task_class.

7. Set synthesis_method from matrix default. If only 1 agent in final list → "inline".

8. Cost estimate:
     Sum per-call estimates from agent-matrix.md.
     If estimate > per_call_cap_usd for any single agent → escalate.
     If estimate > total_cap_usd → escalate.

9. Write route.json. Append progress.jsonl row {"step":"select_agents", ...}.
```

## Escalation rules

When the router escalates, it does NOT auto-decide. It writes the question to `progress.jsonl` and waits for the user. Possible escalations:

- "Primary agent for class=`code-review` is `codex`, but codex auth check failed. Use `claude` instead? (y/n/cancel)"
- "Estimated cost $1.20 exceeds per_call_cap_usd $0.50. Proceed? Or raise the cap to $1.50 just for this call?"
- "Task class is ambiguous (matched both `code-review` and `code-write`). Pick: review | write | both"

The skill prompt itself surfaces these to the user; do not proceed past an unanswered escalation.

## Classifier extension points

If you add a new task class:

1. Add a row to the matrix.
2. Add a keyword rule to the heuristics list **after** the existing rules so first-match-wins ordering is stable.
3. Add a test case to `assets/route_test_cases.md` (one bullet per representative prompt → expected class).
4. The router stays code-free for the data side — only the rule list and the matrix change.

## What the router never does

- Never picks an unavailable agent.
- Never silently swaps when the primary is unavailable.
- Never picks an agent the user explicitly excluded via `--exclude=<name>` (future flag).
- Never picks the host as a "subprocess" — host is always `"inline"`.
- Never reorders the priority list to save cost — cost only triggers escalation, not silent downgrade.

## Test cases (used to keep the heuristics honest)

These live in `assets/route_test_cases.md` (will be added in the second commit) so a CI-like check can re-run them after any matrix change. Example shape:

```
"audit this auth middleware for token-leak risk" → code-review → primary: codex
"prove that sorted-merge is O(n log n)"            → math         → primary: opencode
"brainstorm three approaches to streaming JSON"    → idea         → all three, meta-synth
"who first proved Cook-Levin?"                     → research     → claude only
"write a Python function that flattens a dict"     → code-write   → primary: claude
```
