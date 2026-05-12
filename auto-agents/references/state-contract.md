# State contract — `runs/<task_id>/`

This is the **authoritative** schema. Every read/write under `runs/` must conform. Never invent paths the contract doesn't list. If you need a new path, add it here first, then update the code.

## Task ID

```
task_id = <YYYY-MM-DD>-<HHmm>-<kebab-slug>
```

- Date/time is UTC at task creation.
- `<kebab-slug>` is a 2-6 word, lowercase, hyphen-separated summary of the prompt, set by Stage 0.
- The task ID is **immutable**. A resume reuses the same `task_id`; a fresh task gets a new one.

## Directory layout

```
runs/<task_id>/
├── task.yaml                         # written by Stage 0, never rewritten
├── route.json                        # written by Stage 1, never rewritten (resume re-validates)
├── progress.jsonl                    # append-only micro-step log
├── audit.jsonl                       # append-only per-CLI-call audit (cost + time)
├── .heartbeat                        # current stage / pid / ts_utc (overwritten each step)
├── STOP   (sentinel, optional)       # user creates to request hard stop
├── PAUSE  (sentinel, optional)       # user creates to request pause-at-next-microstep
├── wait_until.txt (optional)         # ISO-8601 UTC; resume sleeps until this time
│
├── agents/
│   ├── claude/                       # one folder per agent that was dispatched
│   │   ├── invocation.md             # the exact prompt + flags handed to the worker
│   │   ├── stdout.log                # full raw stdout (never truncated)
│   │   ├── stderr.log                # full raw stderr
│   │   ├── result.md                 # extracted assistant text (cleaned, no chrome)
│   │   ├── meta.json                 # status, exit_code, ts_started/ended, tokens, cost_est_usd, cost_actual_usd
│   │   └── attempts/                 # optional: prior failed attempts kept for audit
│   │       └── 1/                    # same shape as parent, frozen
│   ├── codex/...                     # same structure
│   └── opencode/...
│
├── synthesis/
│   ├── method.md                     # which synthesis path: vote | debate | meta-synth | inline
│   ├── intermediate/                 # synthesis-method-specific scratch
│   │   ├── debate-round-1.md         # for debate: round-1 positions (always written)
│   │   ├── debate-round-2.md         # for debate: round-2 rebuttals (v2 — round-2 dispatch not yet wired)
│   │   ├── vote-tally.json           # for vote: labels + tally + winner
│   │   ├── meta-synth-input.md       # for meta-synth: concatenated worker outputs
│   │   └── host-instructions.md      # for meta-synth: how the host should write final.md
│   └── final.md                      # the one answer that gets returned
│
└── hand_off.md                       # 3-paragraph user-facing summary
```

## File schemas

### `task.yaml` (Stage 0 writes; never rewritten)

```yaml
task_id: 2026-05-12-1640-fix-cache-invalidation
created_utc: 2026-05-12T16:40:00Z
host: claude                         # detected by host_detect.py — one of: claude | codex | opencode
host_detection: env-var:CLAUDECODE   # how it was detected; for audit
prompt: |
  <verbatim user prompt>
mode: auto                           # auto | multi | single:<agent> | dry-run
per_call_cap_usd: 0.50
total_cap_usd: 2.00
deadline_utc: null                   # optional ISO-8601
workers_available:                   # filled by Stage 0 auth_check
  claude: true
  codex: true
  opencode: false                    # e.g. binary missing or no auth
workers_detail:                      # human-readable reason per worker
  claude: "host (inline)"
  codex: "codex-cli 0.130.0"
  opencode: "binary-missing"
workers_auth_checked:                # honesty about what we actually verified
  claude: "n/a"                      # host doesn't need check
  codex: "binary-ok-auth-deferred"   # --version succeeded; credentials NOT verified
  opencode: "binary-failed"          # binary missing or --version exit ≠ 0
```

`workers_auth_checked` records what Stage 0 actually proved. For all three
CLIs `--version` does NOT exercise credentials, so a binary-ok worker is
recorded `auth-deferred` (first real call surfaces an auth error — at most
one wasted call per integrity rule #4).

### `route.json` (Stage 1 writes; immutable after first write)

```json
{
  "task_class": "idea",
  "classification_reason": "matched keyword 'brainstorm' (rule 3)",
  "agents": ["claude", "codex", "opencode"],
  "agent_modes": {"claude": "subprocess", "codex": "subprocess", "opencode": "subprocess"},
  "synthesis_method": "meta-synth",
  "cost_estimate_usd": 0.45,
  "inline_host_used": false,
  "escalations": []
}
```

`escalations` is a list of human-readable strings; if non-empty, Stage 2
refuses to proceed until they are resolved (per integrity rule #1).
Examples: `"per-call cap $0.10 exceeded by: claude(est×2=$0.40)"`,
`"task_class=idea wants all three agents but missing: ['opencode']"`,
`"unknown mode 'foo'"`.

When the host answers inline:

```json
{
  "task_class": "code-write",
  "agents": ["claude"],
  "agent_modes": {"claude": "inline"},
  "synthesis_method": "inline",
  "cost_estimate_usd": 0.0,
  "inline_host_used": true
}
```

### `progress.jsonl` (append-only, one JSON per line)

```json
{"ts_utc":"2026-05-12T16:40:01Z","stage":0,"step":"host_detect","status":"ok","detail":"host=claude via CLAUDECODE"}
{"ts_utc":"2026-05-12T16:40:02Z","stage":0,"step":"auth_check","status":"ok","detail":"claude:ok codex:ok opencode:missing-binary"}
{"ts_utc":"2026-05-12T16:40:02Z","stage":1,"step":"classify","status":"ok","detail":"idea"}
{"ts_utc":"2026-05-12T16:40:02Z","stage":1,"step":"select_agents","status":"ok","detail":"claude+codex (opencode unavailable)"}
{"ts_utc":"2026-05-12T16:40:03Z","stage":2,"step":"dispatch:claude","status":"started"}
{"ts_utc":"2026-05-12T16:40:31Z","stage":2,"step":"dispatch:claude","status":"ok","detail":"exit=0 cost=$0.18"}
```

Never rewrite. Resume reads tail.

### `audit.jsonl` (append-only)

One row per CLI call (successful or failed):

```json
{"ts_utc":"2026-05-12T16:40:31Z","agent":"claude","attempt":1,"exit_code":0,"duration_s":28.4,"tokens_in":3210,"tokens_out":1402,"cost_actual_usd":0.18}
```

`tokens_in` / `tokens_out` / `cost_actual_usd` are `null` when the CLI
wrapper cannot extract the value from stdout. Budget reconciliation treats
null as 0 (does not count). Malformed JSON rows are silently skipped — the
log is append-only and partial rows from interrupted writes are possible.

### `.heartbeat` (overwritten each micro-step)

```yaml
stage: 2
step: dispatch:codex
pid: 48211
ts_utc: 2026-05-12T16:40:45Z
```

The user can `cat runs/<task_id>/.heartbeat` to peek. The supervisor watches its `ts_utc` to detect stalls.

### `agents/<name>/meta.json`

```json
{
  "agent": "claude",
  "status": "ok",
  "exit_code": 0,
  "ts_started_utc": "2026-05-12T16:40:03Z",
  "ts_ended_utc": "2026-05-12T16:40:31Z",
  "duration_s": 28.4,
  "tokens_in": 3210,
  "tokens_out": 1402,
  "cost_est_usd": 0.30,
  "cost_actual_usd": 0.18,
  "invocation_cmd": "claude -p ${prompt}",
  "attempts": 1
}
```

`status` ∈ `{pending, running, ok, failed, timed-out, dry-run, blocked}`.

- `pending` — inline host has not yet written result.md.
- `running` — subprocess started but completion not yet recorded (crash window flag).
- `ok` — completed; result.md present; audit row written.
- `failed` / `timed-out` — completion recorded with non-zero exit.
- `dry-run` — invocation.md written, no subprocess spawned (mode=dry-run).
- `blocked` — budget gate or escalation refused this call.

Resume re-dispatches anything not `ok` or `dry-run` (after archiving the
old artifacts under `agents/<name>/attempts/<N>/`). `running` on resume is
flagged in `progress.jsonl` as a possible mid-call crash; check
`audit.jsonl` for a double-charge.

`cost_est_usd` / `cost_actual_usd` / `tokens_in` / `tokens_out` may be
`null` when the CLI wrapper cannot extract the value. Budget reconciliation
treats null as "skip" (does not count toward spent total).

### `synthesis/final.md`

Mandatory sections:

```markdown
# Answer

<the actual final answer>

---

## Contributors

- **claude** — wrote the primary draft (sections 1-3). [agents/claude/result.md]
- **codex** — supplied the alternative interpretation in §2. [agents/codex/result.md]
- **opencode** — *unavailable* (no auth on this host).

## Synthesis method: meta-synth

The host (claude) read both worker outputs and merged. No conflicts on §1; in §2
both agents agreed; in §3 only claude had a substantive answer.

## Audit

- Total cost: $0.31
- Total time: 47s
- See `audit.jsonl` for per-call breakdown.
```

### `hand_off.md`

Three paragraphs, written for the human:

1. **What you asked, in one sentence.**
2. **What was done** — which agents ran, how they were merged.
3. **What's next** — does the user need to verify, run something, or pick between alternatives?

## Atomicity

Every file write that is not append-only must use `.tmp + rename`:

```python
def atomic_write(path, content):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(content)
    os.replace(tmp, path)
```

Append-only files (`progress.jsonl`, `audit.jsonl`) use a single `open(..., "a")` write per row — POSIX guarantees a single small write does not interleave.

## Sentinels

- `runs/<task_id>/STOP` — at the top of every micro-step, check; if present, write `progress.jsonl` row `{"status":"stopped-by-user"}` and exit.
- `runs/<task_id>/PAUSE` — same check; if present, sleep 30s and re-check (do not advance state).
- `runs/<task_id>/wait_until.txt` — ISO-8601 UTC; if file exists and now < timestamp, sleep until then.

These three are part of the long-running protocol — never bypass them.
