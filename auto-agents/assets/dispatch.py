"""Stage 2 — fan out workers per route.json.

Each subprocess worker gets AUTO_AGENTS_DEPTH = parent+1 in its env so any
recursive auto-agents invocation will refuse at Stage 0 (recursion guard).

The host agent (route.agent_modes[host] == "inline") does NOT get spawned
here. Instead its `agents/<host>/invocation.md` is written and a placeholder
`meta.json` is written with status="pending". The SKILL.md prompt instructs
the host to fill `agents/<host>/result.md` itself, then re-invoke dispatch.py
which will mark host status="ok" once result.md is non-empty.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import invoke_claude
import invoke_codex
import invoke_opencode
import progress as P

WORKERS = {
    "claude":   invoke_claude,
    "codex":    invoke_codex,
    "opencode": invoke_opencode,
}


def _read_route(run_dir: Path) -> dict:
    return json.loads((run_dir / "route.json").read_text(encoding="utf-8"))


def _read_prompt(run_dir: Path) -> str:
    # task.yaml stores prompt as a YAML block; cheaply extract.
    text = (run_dir / "task.yaml").read_text(encoding="utf-8")
    out: list[str] = []
    in_prompt = False
    for line in text.splitlines():
        if in_prompt:
            if line.startswith("  "):
                out.append(line[2:])
            elif line.strip() == "":
                out.append("")
            else:
                break
        elif line.startswith("prompt: |"):
            in_prompt = True
    return "\n".join(out).rstrip()


def _archive_prior_attempt(agent_dir: Path) -> None:
    """If agent_dir has a result.md from a prior failed attempt, move it under
    attempts/<N>/ so resume produces a fresh result."""
    meta = agent_dir / "meta.json"
    if not meta.exists():
        return
    attempts_dir = agent_dir / "attempts"
    attempts_dir.mkdir(exist_ok=True)
    n = len(list(attempts_dir.iterdir())) + 1
    target = attempts_dir / str(n)
    target.mkdir()
    for name in ("invocation.md", "stdout.log", "stderr.log",
                 "result.md", "meta.json"):
        src = agent_dir / name
        if src.exists():
            os.replace(src, target / name)


def _meta_status(agent_dir: Path) -> str | None:
    meta = agent_dir / "meta.json"
    if not meta.exists():
        return None
    try:
        return json.loads(meta.read_text(encoding="utf-8")).get("status")
    except (json.JSONDecodeError, OSError):
        return None


def _dispatch_subprocess(run_dir: Path, agent: str, prompt: str) -> dict:
    mod = WORKERS[agent]
    agent_dir = run_dir / "agents" / agent
    agent_dir.mkdir(parents=True, exist_ok=True)

    # invocation.md — reproducible record
    inv = (
        f"# Invocation for `{agent}`\n\n"
        f"Cmd: `{os.environ.get(f'AUTO_AGENTS_{agent.upper()}_CMD', mod.DEFAULT_CMD)}` "
        f"<prompt>\n\n"
        f"## Prompt\n\n```\n{prompt}\n```\n"
    )
    P.atomic_write_text(agent_dir / "invocation.md", inv)

    # spawn
    P.append_progress(run_dir, stage=2, step=f"dispatch:{agent}", status="started")
    P.write_heartbeat(run_dir, stage=2, step=f"dispatch:{agent}")
    depth = int(os.environ.get("AUTO_AGENTS_DEPTH", "0") or "0")
    env_overrides = {"AUTO_AGENTS_DEPTH": str(depth + 1)}
    result = mod.invoke(prompt, env_overrides=env_overrides)

    # write raw streams + extracted result
    (agent_dir / "stdout.log").write_text(result["stdout"], encoding="utf-8")
    (agent_dir / "stderr.log").write_text(result["stderr"], encoding="utf-8")
    answer = mod.extract_answer(result["stdout"]) if result["exit_code"] == 0 else ""
    P.atomic_write_text(agent_dir / "result.md", answer)

    status = "ok" if result["exit_code"] == 0 else \
             ("timed-out" if result["exit_code"] == 124 else "failed")
    meta = {
        "agent": agent,
        "status": status,
        "exit_code": result["exit_code"],
        "ts_started_utc": result["ts_started_utc"],
        "ts_ended_utc": result["ts_ended_utc"],
        "duration_s": result["duration_s"],
        "tokens_in": None,
        "tokens_out": None,
        "cost_est_usd": None,
        "cost_actual_usd": None,
        "invocation_cmd": result["cmd"],
        "attempts": 1,
    }
    P.atomic_write_json(agent_dir / "meta.json", meta)
    P.append_audit(
        run_dir, agent=agent, attempt=1, exit_code=result["exit_code"],
        duration_s=result["duration_s"], tokens_in=None, tokens_out=None,
        cost_actual_usd=None,
    )
    P.append_progress(run_dir, stage=2, step=f"dispatch:{agent}", status=status,
                      detail=f"exit={result['exit_code']} t={result['duration_s']:.1f}s")
    return meta


def _stage_inline_host(run_dir: Path, host: str, prompt: str) -> dict:
    """Write the invocation but leave result.md to be filled by the host model."""
    agent_dir = run_dir / "agents" / host
    agent_dir.mkdir(parents=True, exist_ok=True)
    inv = (
        f"# Inline invocation for host `{host}`\n\n"
        f"The host agent should write its answer to `result.md` in this folder,\n"
        f"then update `meta.json: status` to `ok` and re-run dispatch.py.\n\n"
        f"## Prompt\n\n```\n{prompt}\n```\n"
    )
    P.atomic_write_text(agent_dir / "invocation.md", inv)
    meta = {
        "agent": host, "status": "pending",
        "exit_code": None, "ts_started_utc": P.utc_now_iso(),
        "ts_ended_utc": None, "duration_s": None,
        "tokens_in": None, "tokens_out": None,
        "cost_est_usd": None, "cost_actual_usd": None,
        "invocation_cmd": "inline", "attempts": 1,
    }
    P.atomic_write_json(agent_dir / "meta.json", meta)
    P.append_progress(run_dir, stage=2, step=f"dispatch:{host}",
                      status="pending-inline",
                      detail="host writes result.md, then re-run dispatch")
    return meta


def run_stage2(run_dir: Path) -> dict:
    P.check_sentinels(run_dir)
    route = _read_route(run_dir)
    if route.get("escalations"):
        P.append_progress(run_dir, stage=2, step="check_route",
                          status="blocked",
                          detail="route has unresolved escalations")
        return {"status": "blocked", "reason": "route escalations unresolved"}

    prompt = _read_prompt(run_dir)
    results: dict[str, dict] = {}

    for agent, mode in route["agent_modes"].items():
        agent_dir = run_dir / "agents" / agent

        # resume: skip if already ok
        prior = _meta_status(agent_dir)
        if prior == "ok":
            P.append_progress(run_dir, stage=2, step=f"dispatch:{agent}",
                              status="skipped", detail="already ok")
            results[agent] = {"status": "ok", "skipped": True}
            continue

        # resume: archive prior failed attempt
        if prior in ("failed", "timed-out"):
            _archive_prior_attempt(agent_dir)

        if mode == "inline":
            results[agent] = _stage_inline_host(run_dir, agent, prompt)
        else:
            results[agent] = _dispatch_subprocess(run_dir, agent, prompt)

    return {"status": "ok", "results": results}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True, type=Path)
    args = ap.parse_args(argv)
    out = run_stage2(args.run_dir)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if out.get("status") == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
