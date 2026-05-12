# Host CLI modes — detection, recursion guard, auth check

The skill runs inside one of `claude` / `codex` / `opencode`. That parent is the **host**. The other two are candidate **workers**. This file is the single source of truth for: how to detect the host, how to verify worker auth, and how to prevent recursion.

## Three-tier host detection

Implemented in `assets/host_detect.py`. Run **once** at Stage 0 and write the result to `task.yaml: host`. Algorithm:

### Tier 1 — environment variable

Each host CLI is expected to set a distinctive env var when it spawns a subprocess (the skill's helper scripts). Known candidates as of this writing:

| Host       | Env var(s) tried (first match wins)             |
|------------|-------------------------------------------------|
| `claude`   | `CLAUDECODE`, `CLAUDE_CODE`, `CLAUDE_CODE_*`    |
| `codex`    | `CODEX_CLI`, `CODEX_*`                          |
| `opencode` | `OPENCODE`, `OPENCODE_*`                        |

The detector reads `os.environ`, counts how many of the three families match:

- **Exactly one family matches** → host is that one. Record `host_detection: "env-var:<NAME>"`.
- **Zero matches** → fall through to Tier 2.
- **≥2 families match** → suspicious (possible nested invocation or leaked env). Check `AUTO_AGENTS_DEPTH`: if ≥1, we are nested → refuse the skill (recursion guard). Otherwise fall through to Tier 2 and let process-chain disambiguate.

### Tier 2 — parent process chain

Walk up `$PPID` using `ps -o comm= -p <pid>` (or `/proc/<pid>/comm` on Linux) until pid=1 or a depth cap (default 8). Collect process names along the way.

- If exactly one of `{claude, codex, opencode}` appears in the chain → that's the host. Record `host_detection: "ps-chain:<NAME>"`.
- If none appear → fall through to Tier 3.
- If more than one appears → that's a real nested-invocation case. Pick the **closest** (smallest depth) as host but log a `progress.jsonl` warning row.

Implementation note (macOS vs Linux):

```sh
# macOS / BSD ps
ps -o comm= -p "$PPID"

# Linux
cat /proc/$PPID/comm
```

Both return the process basename. Be defensive: shells like `zsh` or wrappers like `script` may sit between the CLI and the skill helper; that's why we walk the chain rather than reading only `$PPID`.

### Tier 3 — cached answer + interactive ask

If both tiers above are inconclusive:

1. Read `~/.config/auto-agents/host.yaml` if it exists. Schema:
   ```yaml
   host: claude
   confirmed_utc: 2026-05-12T16:40:00Z
   confirmed_by: env-var:CLAUDECODE
   ```
   If the cache is < 30 days old, use the cached host and record `host_detection: "cache"`.
2. Otherwise: prompt the user (via the host's AskUserQuestion or equivalent) with the question "Which CLI are you running this from? (claude / codex / opencode)" and write the answer to both `task.yaml` and `~/.config/auto-agents/host.yaml`.

### Override (always honored)

If the env var `AUTO_AGENTS_HOST` is set to one of `claude|codex|opencode`, that wins over all three tiers. Record `host_detection: "env-override:AUTO_AGENTS_HOST"`.

This is the escape hatch for CI / scripted runs and for users whose CLI doesn't set any of the known env vars.

## Recursion guard

Before doing anything else, Stage 0 reads `AUTO_AGENTS_DEPTH`. Defaults to `0`. If `≥ 1`, the skill refuses immediately and writes:

```
{"status":"refused","reason":"AUTO_AGENTS_DEPTH=1 (already inside auto-agents)"}
```

When dispatching a worker, the dispatcher sets `AUTO_AGENTS_DEPTH = <current+1>` in the subprocess env. This makes the guard *transitive* — a worker that itself invokes auto-agents will refuse.

The host never spawns itself as a worker. The router enforces this: if the matrix says the best agent for task class X is the host, `route.json: agent_modes` records `"<host>": "inline"` and Stage 2 skips subprocess dispatch for that agent.

## Worker auth check

Stage 0 verifies each candidate worker before letting the router pick it. For each of `claude` / `codex` / `opencode` that is **not** the host:

1. **Binary present?** Run `which <cli>` (or `command -v`). If missing → `workers_available[<name>] = false`, reason `"binary-missing"`.
2. **Version handshake?** Run `<cli> --version` with a 10s timeout. If exit ≠ 0 → `false`, reason `"version-failed"`.
3. **Auth handshake?** Run a no-op prompt against the CLI with `--dry-run` flag if it supports it, else a 1-token cheap echo. If exit ≠ 0 with a clear auth error → `false`, reason `"auth-failed:<class>"`. Skip this step if the CLI lacks a `--dry-run` and a real call would cost money — record `auth_checked: "deferred"` in that case and let the first real call surface the error.

Record results in `task.yaml: workers_available` and `progress.jsonl`.

**If a worker the router wanted is unavailable, escalate — do NOT silently route to another agent.** Per integrity rule "no silent agent swap": the skill stops and asks the user "claude is unavailable; proceed with codex+opencode only? Or stop?"

## Inline-host execution

When the router selects the host (e.g. host=claude, task=code-write), Stage 2 does **not** spawn a subprocess. Instead:

1. The skill helper writes `agents/<host>/invocation.md` with the prompt.
2. The host (the agent reading SKILL.md) answers the prompt itself, in the same conversation.
3. The skill helper captures that answer to `agents/<host>/result.md` via a follow-up write.

This is the only path that does not produce `stdout.log` / `stderr.log` — set `meta.json: invocation_cmd = "inline"` and `tokens_*: null`.

## Why three tiers, not one

The user asked: can the skill auto-detect host? Yes — env-var Tier 1 will hit cleanly when the CLI cooperates. Tier 2 catches CLIs that don't set env vars but do show up in `ps` (most do). Tier 3 is the truthful fallback for esoteric setups — *one* prompt, cached for 30 days. No silent guessing: every detection records `host_detection` in `task.yaml` so the user can audit.
