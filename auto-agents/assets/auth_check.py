"""Stage 0 — detect host, verify worker CLIs, write task.yaml + workers_available.

Usage (from inside the host CLI):
    python -m auth_check --run-dir <runs/<task_id>> --prompt-file <path>

Or programmatic:
    from auth_check import run_stage0
    run_stage0(run_dir=..., prompt=..., mode="auto", per_call_cap_usd=0.50,
               total_cap_usd=2.00, deadline_utc=None)

Reads ../references/host-cli-modes.md for the algorithm.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import host_detect
import invoke_claude
import invoke_codex
import invoke_opencode
import progress as P

WORKERS = {
    "claude":   invoke_claude,
    "codex":    invoke_codex,
    "opencode": invoke_opencode,
}


def _yaml_dump_task(task: dict) -> str:
    """Minimal YAML writer; we keep the file plain-text so users can edit it."""
    lines = []
    for k, v in task.items():
        if isinstance(v, dict):
            lines.append(f"{k}:")
            for sk, sv in v.items():
                lines.append(f"  {sk}: {json.dumps(sv) if not isinstance(sv, (int, float, bool)) and sv is not None else sv}")
        elif isinstance(v, str) and ("\n" in v or len(v) > 100):
            lines.append(f"{k}: |")
            for line in v.splitlines():
                lines.append(f"  {line}")
        else:
            lines.append(f"{k}: {json.dumps(v) if isinstance(v, str) else v}")
    return "\n".join(lines) + "\n"


def run_stage0(run_dir: Path, prompt: str, *, mode: str = "auto",
               per_call_cap_usd: float = 0.50, total_cap_usd: float = 2.00,
               deadline_utc: str | None = None,
               host_override: str | None = None) -> dict:
    run_dir.mkdir(parents=True, exist_ok=True)
    P.check_sentinels(run_dir)
    P.write_heartbeat(run_dir, stage=0, step="host_detect")

    # --- host detection ------------------------------------------------------
    det = host_detect.detect()
    if det.get("refused"):
        P.append_progress(run_dir, stage=0, step="host_detect",
                          status="refused", detail=det.get("reason", ""))
        raise SystemExit(3)
    host = host_override or det.get("host")
    detection = "manual-override" if host_override else det.get("detection")
    if host is None:
        P.append_progress(run_dir, stage=0, step="host_detect",
                          status="needs-user", detail=json.dumps(det))
        # Caller (the host CLI's tool-using agent) must ask the user and re-invoke.
        raise SystemExit(2)
    P.append_progress(run_dir, stage=0, step="host_detect",
                      status="ok", detail=f"host={host} via {detection}")

    # --- worker auth check ---------------------------------------------------
    P.write_heartbeat(run_dir, stage=0, step="auth_check")
    workers_available: dict[str, bool] = {}
    workers_detail: dict[str, str] = {}
    for name, mod in WORKERS.items():
        if name == host:
            workers_available[name] = True
            workers_detail[name] = "host (inline)"
            continue
        ok, detail = mod.version_check()
        workers_available[name] = ok
        workers_detail[name] = detail
    P.append_progress(
        run_dir, stage=0, step="auth_check", status="ok",
        detail=" ".join(f"{k}:{'ok' if v else 'unavailable'}"
                        for k, v in workers_available.items()),
    )

    # --- write task.yaml -----------------------------------------------------
    task = {
        "task_id": run_dir.name,
        "created_utc": P.utc_now_iso(),
        "host": host,
        "host_detection": detection,
        "prompt": prompt,
        "mode": mode,
        "per_call_cap_usd": per_call_cap_usd,
        "total_cap_usd": total_cap_usd,
        "deadline_utc": deadline_utc,
        "workers_available": workers_available,
        "workers_detail": workers_detail,
    }
    P.atomic_write_text(run_dir / "task.yaml", _yaml_dump_task(task))
    P.append_progress(run_dir, stage=0, step="write_task_yaml", status="ok")
    return task


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True, type=Path)
    ap.add_argument("--prompt-file", required=True, type=Path)
    ap.add_argument("--mode", default="auto")
    ap.add_argument("--per-call-cap-usd", type=float, default=0.50)
    ap.add_argument("--total-cap-usd", type=float, default=2.00)
    ap.add_argument("--deadline-utc", default=None)
    ap.add_argument("--host-override", default=None,
                    choices=[None, "claude", "codex", "opencode"])
    args = ap.parse_args(argv)
    prompt = args.prompt_file.read_text(encoding="utf-8")
    task = run_stage0(
        run_dir=args.run_dir,
        prompt=prompt,
        mode=args.mode,
        per_call_cap_usd=args.per_call_cap_usd,
        total_cap_usd=args.total_cap_usd,
        deadline_utc=args.deadline_utc,
        host_override=args.host_override,
    )
    print(json.dumps(task, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
