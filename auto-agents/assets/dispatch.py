"""Stage 2 — fan out workers per route.json.

Each subprocess worker gets AUTO_AGENTS_DEPTH = parent+1 in its env so any
recursive auto-agents invocation will refuse at Stage 0 (recursion guard).

The host agent (route.agent_modes[host] == "inline") does NOT get spawned
here. The two-pass flow:

  Pass 1: invocation.md is written and meta.json is created with
          status="pending". run_stage2 returns status="pending-inline".
  Pass 2: after the host model fills agents/<host>/result.md, re-running
          dispatch detects the non-empty result.md, atomically flips
          meta.json{status=ok}, and appends an audit row. run_stage2 then
          returns status="ok" and synthesis can proceed.

Subprocess workers go through _dispatch_subprocess: budget.gate refuses
before spending, a provisional meta.json{status=running} closes the
crash-mid-call window, then the call runs and meta.json is rewritten with
the final status + audit row appended. Resume of an interrupted call
archives the prior attempt under agents/<name>/attempts/<N>/ and re-tries.

Dry-run mode (task.yaml: mode == "dry-run"): subprocess agents get
invocation.md + meta.json{status="dry-run"} but are NOT spawned.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import budget
import invoke_claude
import invoke_codex
import invoke_opencode
import progress as P
import yaml_io

# Mirrors route.COST_ESTIMATE_USD — kept here to break the import cycle.
COST_ESTIMATE_USD = {"claude": 0.20, "codex": 0.12, "opencode": 0.05}

WORKERS = {
    "claude":   invoke_claude,
    "codex":    invoke_codex,
    "opencode": invoke_opencode,
}


def _read_route(run_dir: Path) -> dict:
    return json.loads((run_dir / "route.json").read_text(encoding="utf-8"))


def _read_prompt(run_dir: Path) -> str:
    return yaml_io.load_path(run_dir / "task.yaml").get("prompt", "")


def _archive_prior_attempt(agent_dir: Path) -> None:
    """If agent_dir has artifacts from a prior failed/crashed attempt, move
    them under attempts/<N>/ so the next run produces a fresh result.
    Picks the smallest N where attempts/<N>/ doesn't exist — survives
    crashes that left a half-formed directory."""
    meta = agent_dir / "meta.json"
    if not meta.exists():
        return
    attempts_dir = agent_dir / "attempts"
    attempts_dir.mkdir(exist_ok=True)
    n = 1
    while (attempts_dir / str(n)).exists():
        n += 1
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

    # Budget gate (per-call + total) — refuse before spending.
    est = COST_ESTIMATE_USD.get(agent, 0.0) * 2.0  # ×2 headroom per integrity rule
    decision = budget.gate(run_dir, estimated_next_call_usd=est)
    if not decision["ok"]:
        P.append_progress(
            run_dir, stage=2, step=f"dispatch:{agent}", status="blocked-budget",
            detail=" | ".join(decision["reasons"]),
        )
        return {
            "agent": agent, "status": "blocked",
            "reason": "budget gate refused",
            "decision": decision,
        }

    # invocation.md — reproducible record
    inv = (
        f"# Invocation for `{agent}`\n\n"
        f"Cmd: `{os.environ.get(f'AUTO_AGENTS_{agent.upper()}_CMD', mod.DEFAULT_CMD)}` "
        f"<prompt>\n\n"
        f"## Prompt\n\n```\n{prompt}\n```\n"
    )
    P.atomic_write_text(agent_dir / "invocation.md", inv)

    # Provisional meta.json BEFORE the call — closes the crash window.
    provisional = {
        "agent": agent, "status": "running",
        "exit_code": None, "ts_started_utc": P.utc_now_iso(),
        "ts_ended_utc": None, "duration_s": None,
        "tokens_in": None, "tokens_out": None,
        "cost_est_usd": est, "cost_actual_usd": None,
        "invocation_cmd": (os.environ.get(f"AUTO_AGENTS_{agent.upper()}_CMD",
                                          mod.DEFAULT_CMD) + " <prompt>"),
        "attempts": 1,
    }
    P.atomic_write_json(agent_dir / "meta.json", provisional)

    P.append_progress(run_dir, stage=2, step=f"dispatch:{agent}", status="started",
                      detail=f"budget ok (est=${est:.4f})")
    P.write_heartbeat(run_dir, stage=2, step=f"dispatch:{agent}")
    depth = int(os.environ.get("AUTO_AGENTS_DEPTH", "0") or "0")
    env_overrides = {"AUTO_AGENTS_DEPTH": str(depth + 1)}
    result = mod.invoke(prompt, env_overrides=env_overrides)

    # write raw streams + extracted result (atomic per integrity rule #7)
    P.atomic_write_text(agent_dir / "stdout.log", result["stdout"])
    P.atomic_write_text(agent_dir / "stderr.log", result["stderr"])
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
    """Inline-host two-pass:
       Pass 1: no result.md yet → write invocation.md + meta.json{status=pending}.
       Pass 2 (re-run after host writes result.md): if result.md is non-empty,
               flip meta.json{status=ok}, write audit row, return.
    The host model is expected to fill result.md between pass 1 and pass 2."""
    agent_dir = run_dir / "agents" / host
    agent_dir.mkdir(parents=True, exist_ok=True)
    result_path = agent_dir / "result.md"
    meta_path = agent_dir / "meta.json"

    # Pass 2: host has filled in result.md → complete the record.
    if result_path.exists() and result_path.read_text(encoding="utf-8").strip():
        # Read existing meta to preserve ts_started_utc
        prior = json.loads(meta_path.read_text(encoding="utf-8")) \
                if meta_path.exists() else {}
        meta = {
            "agent": host, "status": "ok",
            "exit_code": 0,
            "ts_started_utc": prior.get("ts_started_utc", P.utc_now_iso()),
            "ts_ended_utc": P.utc_now_iso(),
            "duration_s": None, "tokens_in": None, "tokens_out": None,
            "cost_est_usd": 0.0, "cost_actual_usd": 0.0,
            "invocation_cmd": "inline", "attempts": prior.get("attempts", 1),
        }
        P.atomic_write_json(meta_path, meta)
        P.append_audit(run_dir, agent=host, attempt=meta["attempts"],
                       exit_code=0, duration_s=0.0, tokens_in=None,
                       tokens_out=None, cost_actual_usd=0.0)
        P.append_progress(run_dir, stage=2, step=f"dispatch:{host}",
                          status="ok",
                          detail="inline host result.md present; flipped to ok")
        return meta

    # Pass 1: stage the invocation, leave status=pending.
    inv = (
        f"# Inline invocation for host `{host}`\n\n"
        f"The host agent should write its answer to `result.md` in this folder.\n"
        f"After result.md is written, re-run dispatch.py — the script will flip\n"
        f"meta.json status to `ok` automatically.\n\n"
        f"## Prompt\n\n```\n{prompt}\n```\n"
    )
    P.atomic_write_text(agent_dir / "invocation.md", inv)
    meta = {
        "agent": host, "status": "pending",
        "exit_code": None, "ts_started_utc": P.utc_now_iso(),
        "ts_ended_utc": None, "duration_s": None,
        "tokens_in": None, "tokens_out": None,
        "cost_est_usd": 0.0, "cost_actual_usd": None,
        "invocation_cmd": "inline", "attempts": 1,
    }
    P.atomic_write_json(meta_path, meta)
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

    task = yaml_io.load_path(run_dir / "task.yaml")
    dry_run = task.get("mode") == "dry-run"
    if dry_run:
        P.append_progress(run_dir, stage=2, step="dry-run",
                          status="ok",
                          detail="writing invocations only; no subprocess spawn")

    for agent, mode in route["agent_modes"].items():
        agent_dir = run_dir / "agents" / agent

        # resume: skip if already ok AND result.md is present and non-empty.
        # ('ok' meta.json without result.md means a partial earlier write —
        # re-dispatch rather than trusting the bogus status.)
        prior = _meta_status(agent_dir)
        result_md = agent_dir / "result.md"
        result_present = result_md.exists() and result_md.read_text(
            encoding="utf-8").strip() != ""
        if prior == "ok" and result_present:
            P.append_progress(run_dir, stage=2, step=f"dispatch:{agent}",
                              status="skipped", detail="already ok + result.md present")
            results[agent] = {"status": "ok", "skipped": True}
            continue
        if prior == "ok" and not result_present:
            P.append_progress(
                run_dir, stage=2, step=f"dispatch:{agent}",
                status="warning",
                detail="meta.json ok but result.md missing/empty — re-dispatching",
            )
            _archive_prior_attempt(agent_dir)

        # resume: archive prior failed / interrupted attempt
        # 'running' means we crashed mid-call — could be already charged; we
        # still retry, but flag it loudly in progress.jsonl so the user can
        # check audit.jsonl for a double-charge.
        if prior in ("failed", "timed-out", "running"):
            if prior == "running":
                P.append_progress(
                    run_dir, stage=2, step=f"dispatch:{agent}",
                    status="resumed-after-crash",
                    detail="prior attempt status=running; possible mid-call "
                           "crash — check audit.jsonl for double charge",
                )
            _archive_prior_attempt(agent_dir)

        if mode == "inline":
            results[agent] = _stage_inline_host(run_dir, agent, prompt)
        elif dry_run:
            # dry-run: write invocation.md but do NOT spawn. Mark as
            # 'dry-run' so synthesize.py knows there is nothing to merge.
            agent_dir.mkdir(parents=True, exist_ok=True)
            inv = (
                f"# DRY-RUN invocation for `{agent}` (not spawned)\n\n"
                f"Cmd would be: `{os.environ.get(f'AUTO_AGENTS_{agent.upper()}_CMD', WORKERS[agent].DEFAULT_CMD)}` <prompt>\n\n"
                f"## Prompt\n\n```\n{prompt}\n```\n"
            )
            P.atomic_write_text(agent_dir / "invocation.md", inv)
            P.atomic_write_json(agent_dir / "meta.json",
                                {"agent": agent, "status": "dry-run",
                                 "invocation_cmd": "dry-run", "attempts": 0})
            P.append_progress(run_dir, stage=2, step=f"dispatch:{agent}",
                              status="dry-run",
                              detail="invocation.md written; no subprocess")
            results[agent] = {"agent": agent, "status": "dry-run"}
        else:
            results[agent] = _dispatch_subprocess(run_dir, agent, prompt)

    # If any agent (inline or subprocess) is still pending, Stage 3 must wait.
    statuses = [r.get("status") for r in results.values()]
    if "pending" in statuses:
        return {"status": "pending-inline", "results": results,
                "reason": "host must write result.md, then re-run dispatch"}
    return {"status": "ok", "results": results}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True, type=Path)
    args = ap.parse_args(argv)
    try:
        out = run_stage2(args.run_dir)
    except P.StopRequested as e:
        P.append_progress(args.run_dir, stage=2, step="stop_sentinel",
                          status="stopped-by-user", detail=str(e))
        return 2
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if out.get("status") in ("ok", "pending-inline") else 1


if __name__ == "__main__":
    sys.exit(main())
