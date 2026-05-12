"""Stage 4 — write hand_off.md.

Three short paragraphs intended for a human reader:
  1. What the user asked, in one sentence.
  2. What was done — which agents ran, how they were merged, audit summary.
  3. What's next — verify-checklist, deadlines, any escalations the user
     still needs to resolve.

Idempotent: regenerates hand_off.md from disk every time (no append-only here).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import progress as P
import yaml_io


def _read_route(run_dir: Path) -> dict:
    p = run_dir / "route.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _agent_summary(run_dir: Path, agent: str) -> tuple[str, str]:
    """Returns (status, one-line summary)."""
    meta_p = run_dir / "agents" / agent / "meta.json"
    if not meta_p.exists():
        return "missing", "no meta.json written"
    try:
        meta = json.loads(meta_p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return "malformed", "meta.json could not be parsed"
    status = meta.get("status", "?")
    cost = meta.get("cost_actual_usd")
    dur = meta.get("duration_s")
    bits: list[str] = []
    if status:
        bits.append(f"status={status}")
    if cost is not None:
        bits.append(f"cost=${cost:.4f}")
    if dur is not None:
        bits.append(f"t={dur:.1f}s")
    return status, ", ".join(bits) if bits else "no audit info"


def _audit_totals(run_dir: Path) -> tuple[float, float]:
    audit = run_dir / "audit.jsonl"
    if not audit.exists():
        return 0.0, 0.0
    dur = 0.0
    cost = 0.0
    for line in audit.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        try:
            dur += float(row.get("duration_s") or 0)
        except (TypeError, ValueError):
            pass
        try:
            if row.get("cost_actual_usd") is not None:
                cost += float(row["cost_actual_usd"])
        except (TypeError, ValueError):
            pass
    return dur, cost


def run_stage4(run_dir: Path) -> dict:
    P.check_sentinels(run_dir)
    P.write_heartbeat(run_dir, stage=4, step="handoff")

    task = yaml_io.load_path(run_dir / "task.yaml") \
        if (run_dir / "task.yaml").exists() else {}
    route = _read_route(run_dir)
    prompt = task.get("prompt", "(no prompt found)")
    one_line = prompt.splitlines()[0] if prompt else "(empty)"
    if len(one_line) > 140:
        one_line = one_line[:137] + "…"

    agents = route.get("agents", [])
    method = route.get("synthesis_method", "?")
    final_path = run_dir / "synthesis" / "final.md"
    final_exists = final_path.exists()
    dur, cost = _audit_totals(run_dir)

    agent_lines: list[str] = []
    failures: list[str] = []
    for a in agents:
        status, summary = _agent_summary(run_dir, a)
        agent_lines.append(f"  - **{a}** — {summary}")
        if status not in ("ok", "dry-run", "pending"):
            failures.append(f"{a}({status})")

    escalations = route.get("escalations", []) or []

    next_bits: list[str] = []
    if not final_exists:
        next_bits.append(
            "Synthesis is incomplete — `synthesis/final.md` not yet written. "
            "Re-run dispatch + synthesize (most likely an inline host still "
            "needs to produce result.md)."
        )
    if escalations:
        next_bits.append(
            "There are unresolved router escalations — see `route.json: "
            "escalations` and clear them, then re-run dispatch."
        )
    if failures:
        next_bits.append(
            f"Failed agents: {', '.join(failures)}. Check "
            "`agents/<name>/stderr.log` for the raw error."
        )
    if not next_bits:
        next_bits.append("Read `synthesis/final.md`. Done.")

    body = (
        f"# Hand-off — task {task.get('task_id', run_dir.name)}\n\n"
        f"## What you asked\n\n"
        f"> {one_line}\n\n"
        f"_(host={task.get('host', '?')}, mode={task.get('mode', '?')}, "
        f"task_class={route.get('task_class', '?')})_\n\n"
        f"## What was done\n\n"
        f"Agents involved (synthesis = **{method}**):\n\n"
        + "\n".join(agent_lines) + "\n\n"
        + f"Totals: time {dur:.1f}s, recorded cost ${cost:.4f}. "
        + ("`synthesis/final.md` written." if final_exists
           else "`synthesis/final.md` NOT written.") + "\n\n"
        + "## What's next\n\n"
        + "\n".join(f"- {b}" for b in next_bits) + "\n"
    )
    P.atomic_write_text(run_dir / "hand_off.md", body)
    P.append_progress(run_dir, stage=4, step="handoff", status="ok",
                      detail=f"final_md={'yes' if final_exists else 'no'}")
    return {"status": "ok", "hand_off_path": str(run_dir / "hand_off.md")}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True, type=Path)
    args = ap.parse_args(argv)
    try:
        out = run_stage4(args.run_dir)
    except P.StopRequested as e:
        P.append_progress(args.run_dir, stage=4, step="stop_sentinel",
                          status="stopped-by-user", detail=str(e))
        return 2
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
