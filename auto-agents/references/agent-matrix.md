# Agent capability matrix

This file says *what each CLI is best at*, *what flags to call it with*, and *which env var holds its credentials*. The router (`assets/route.py`) consumes this. Update here, not in the router code.

## Task classes

| Class           | Description                                                  | Default agents (priority order) | Default synthesis |
|-----------------|--------------------------------------------------------------|---------------------------------|-------------------|
| `code-write`    | "write a function / file / patch / refactor"                 | claude, codex                   | inline (1 agent)  |
| `code-review`   | "audit this code / find bugs / security review"              | codex, claude                   | inline (1 agent)  |
| `math`          | "prove / derive / step-by-step calculation / theorem check"  | opencode, claude                | inline (1 agent)  |
| `idea`          | "brainstorm / propose / generate alternatives"               | claude, codex, opencode (all)   | meta-synth        |
| `debate`        | "argue both sides / adversarial / steelman"                  | claude, codex, opencode (all)   | debate            |
| `research`      | "literature / web / collect sources / who said X"            | claude (has WebSearch+WebFetch) | inline (1 agent)  |
| `quick-qa`      | trivial single-shot Q&A                                      | host CLI                         | inline (host)     |

Classification heuristics (the router applies these in order, first match wins):

1. Task contains `audit`, `review`, `bug`, `security`, `lint`, `correctness check` → `code-review`
2. Task contains `prove`, `derive`, `theorem`, `integral`, `combinatorics`, `step-by-step solve` → `math`
3. Task contains `brainstorm`, `propose`, `ideas`, `alternatives`, `what could we`, `多个角度` → `idea`
4. Task contains `debate`, `adversarial`, `steelman`, `for and against`, `pros and cons` → `debate`
5. Task contains `find papers`, `search the web`, `who said`, `cite`, `references` → `research`
6. Task contains `write`, `implement`, `add`, `refactor`, `fix the function` → `code-write`
7. Else: `quick-qa` (host inline)

When the **host** is one of the listed primaries, it answers inline — no subprocess spawn. E.g. host=claude + class=code-write → inline.

For `idea` and `debate`, **all three agents are called regardless of host**, because the value is the multi-perspective spread.

## Per-agent profile

### `claude` (Claude Code)

- Strengths: code writing, refactoring, web search/fetch, multi-file edits, long-context reasoning.
- Weaknesses: cost per token if you run unbounded; can be over-cautious on adversarial review.
- One-shot CLI: `claude -p "<prompt>"` (writes assistant text to stdout)
- Structured output: `claude -p "<prompt>" --output-format json` (one JSON object on stdout)
- Auth: `ANTHROPIC_API_KEY` env or `~/.claude/` config; the wrapper checks `claude --version` to confirm the binary is present.
- Cost class: medium-high.

### `codex` (OpenAI Codex CLI)

- Strengths: code review / audit, tight diffs, terseness, working in CI-style non-interactive contexts.
- Weaknesses: shorter context than Claude; weaker at open-ended brainstorming.
- One-shot CLI: `codex exec "<prompt>"` (non-interactive)
- Auth: `OPENAI_API_KEY` env or `~/.codex/auth.json`; wrapper checks `codex --version`.
- Cost class: medium.

### `opencode` (sst/opencode)

- Strengths: math/logic reasoning, local-model friendly, deterministic when paired with a temperature-0 backend.
- Weaknesses: less tooling for web/file I/O; depends on the underlying model the user has configured.
- One-shot CLI: `opencode run "<prompt>"` (one-shot, prints to stdout)
- Auth: depends on the configured provider (`~/.config/opencode/`). Wrapper checks `opencode --version`.
- Cost class: depends on user's backend (can be free with local models).

## CLI invocation overrides

If a user's install uses non-default flags, set env vars and the wrappers will use them:

- `AUTO_AGENTS_CLAUDE_CMD` (default: `claude -p`)
- `AUTO_AGENTS_CODEX_CMD` (default: `codex exec`)
- `AUTO_AGENTS_OPENCODE_CMD` (default: `opencode run`)

The wrappers pass the prompt as the last positional arg. They never inject additional flags beyond what the env var defines.

## Cost estimates (rough, for budget gate)

| Agent     | $/call (typical 4k-in/2k-out) |
|-----------|------------------------------|
| claude    | ~$0.10–0.30                  |
| codex     | ~$0.05–0.20                  |
| opencode  | $0 (local) – $0.15 (cloud)   |

These are **rough**. `budget.py` reads actuals from each worker's `meta.json` and updates `audit.jsonl`. The gate is on *estimated* cost before the call, then reconciled with *actual* after.
