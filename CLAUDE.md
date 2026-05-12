# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A single portable skill package — **auto-agents** — for Claude Code, Codex CLI, and OpenCode. It sits *above* those three coding agents and orchestrates them: the CLI that invokes it is the **host**, the other two are **workers**. Given one prompt, the skill classifies the task, picks the right agent(s) from a capability matrix, dispatches workers as subprocesses with budget caps, captures every stdout/stderr/meta to disk, and synthesizes one final answer (vote / debate / meta-synth).

It is *not* a runnable application — there is no top-level build, no test suite, no `requirements.txt`. The deliverables are markdown + YAML + Python helper scripts + a shell supervisor that get copied into `~/.claude/skills/` (or `<project>/.claude/skills/`) and executed by an agent at runtime.

Implication for editing: the "code" here is prompts, workflow contracts, and the dispatch helpers. Changes are validated by reading them and tracing the contract — not by running the helpers inside this checkout. Real runs happen on the user's machine, where the three CLIs are installed.

## Layout

This repo is a **single-skill** package (unlike auto-research and auto-kaggle which ship a family of skills):

```
auto-agents/                          ← the only skill folder
├── SKILL.md                          frontmatter + workflow
├── agents/openai.yaml                Codex-side UI metadata
├── references/*.md                   load-on-demand reference docs
└── assets/*.py + supervisor.sh       host_detect / route / dispatch / synthesize / wrappers
README.md  README.zh-CN.md            bilingual top-level (English is GitHub default)
docs/                                 hero image (cosmetic, optional)
```

If you ever split this into multiple skills (e.g. `auto-agents-route` + `auto-agents-synth`), mirror the auto-research / auto-kaggle convention: one folder per skill, all siblings at the repo root, top-level README is English, `README.zh-CN.md` mirrors.

## State contract — do not invent paths

All per-task state lives under `runs/<task_id>/`, where `task_id = YYYY-MM-DD-HHmm-<kebab-slug>`. The full file schema is in `auto-agents/references/state-contract.md` — treat that file as authoritative. When editing any helper that reads or writes task artifacts, cross-check it against `state-contract.md`.

Files every stage reads first:

- `runs/<task_id>/task.yaml` — host CLI, original prompt, budget caps, mode
- `runs/<task_id>/.heartbeat` — current stage/step/ts_utc/pid
- `runs/<task_id>/progress.jsonl` — append-only micro-step log; resume reads its tail
- `runs/<task_id>/route.json` — Stage 1 output, Stage 2+ inputs

`runs/` is gitignored — never commit task output back into this repo.

## The host-CLI rule overrides everything

The host CLI is **always** detected first (`assets/host_detect.py` — three-tier: env var → parent process chain → cached/asked + override via `AUTO_AGENTS_HOST`). The host never spawns itself as a worker. Every subprocess gets `AUTO_AGENTS_DEPTH = parent+1`; a Stage 0 check refuses any depth ≥1 (recursion guard).

The full algorithm and rationale is in `auto-agents/references/host-cli-modes.md`. Every edit that touches host detection, auth check, or worker spawning must update this file too.

## The integrity rules override everything else

`auto-agents/references/integrity-rules.md` defines the eight non-negotiable rules (no silent agent swap, attribution mandatory in `final.md`, budget gate per-call + per-task, auth check upfront, no CLI flag fabrication, recursion guard, idempotent micro-steps, all state on disk). When editing any helper:

- Do not loosen these rules to make a workflow easier.
- A new code path must say how it satisfies (or escalates under) these rules.
- The "stop and ask the human" escalations listed in SKILL.md and `references/routing-policy.md` are part of the contract — preserve them.

## Conventions when editing

- Keep `SKILL.md` frontmatter `description` within Claude Code's 1024-char limit and unambiguous about when to trigger.
- Examples in references use absolute UTC timestamps. Never write "today" or "yesterday" — those rot.
- The repo intentionally has both English (`README.md` — GitHub's default render) and Chinese (`README.zh-CN.md`) READMEs; if you change one substantively, mirror the change in the other.
- Helper scripts read/write paths defined in `state-contract.md`. Do not invent new paths.
- CLI invocation patterns (`assets/invoke_*.py`) hold ONE known-good command line each. **Never** try alternate flags on failure — that's CLI flag fabrication (integrity rule #5). Honor env overrides `AUTO_AGENTS_{CLAUDE,CODEX,OPENCODE}_CMD` and surface raw errors otherwise.
- `.gitignore` includes `runs/`, `__pycache__/`, `._*`, `.DS_Store`. Verify before committing — `._*` files appear on macOS+ExFAT volumes and must not be staged.

## Working in this environment

This machine is shared and resource-constrained — it is for *editing the skill and committing*, not for executing it. Do not attempt to run `python dispatch.py` here to test it: actual runs (spawning real `claude` / `codex` / `opencode` subprocesses) belong on the user's machine. When the user wants to validate a change, list the commands they should run there rather than running them here.
