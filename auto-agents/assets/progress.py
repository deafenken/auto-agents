"""Append-only progress + audit logging, atomic state writes, sentinel checks.

Every helper in this skill imports from here. The schema is in
../references/state-contract.md — keep that file in sync if you change keys.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path


def utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# --- Append-only logs ---------------------------------------------------------
def append_progress(run_dir: Path, *, stage: int, step: str, status: str,
                    detail: str = "") -> None:
    row = {
        "ts_utc": utc_now_iso(),
        "stage": stage,
        "step": step,
        "status": status,
    }
    if detail:
        row["detail"] = detail
    line = json.dumps(row, ensure_ascii=False) + "\n"
    with open(run_dir / "progress.jsonl", "a", encoding="utf-8") as f:
        f.write(line)


def append_audit(run_dir: Path, *, agent: str, attempt: int, exit_code: int,
                 duration_s: float, tokens_in: int | None,
                 tokens_out: int | None, cost_actual_usd: float | None) -> None:
    row = {
        "ts_utc": utc_now_iso(),
        "agent": agent,
        "attempt": attempt,
        "exit_code": exit_code,
        "duration_s": round(duration_s, 3),
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_actual_usd": cost_actual_usd,
    }
    line = json.dumps(row, ensure_ascii=False) + "\n"
    with open(run_dir / "audit.jsonl", "a", encoding="utf-8") as f:
        f.write(line)


# --- Atomic writes ------------------------------------------------------------
def atomic_write_text(path: Path, content: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def atomic_write_json(path: Path, obj) -> None:
    atomic_write_text(path, json.dumps(obj, ensure_ascii=False, indent=2))


def write_heartbeat(run_dir: Path, *, stage: int, step: str) -> None:
    body = (
        f"stage: {stage}\n"
        f"step: {step}\n"
        f"pid: {os.getpid()}\n"
        f"ts_utc: {utc_now_iso()}\n"
    )
    atomic_write_text(run_dir / ".heartbeat", body)


# --- Sentinel checks ----------------------------------------------------------
class StopRequested(Exception):
    """Raised when runs/<task_id>/STOP is found at micro-step boundary."""


def check_sentinels(run_dir: Path) -> None:
    """Raise StopRequested if STOP is present; sleep-and-retry on PAUSE;
    sleep until wait_until.txt timestamp if present. Called at the top of
    every micro-step."""
    stop = run_dir / "STOP"
    if stop.exists():
        raise StopRequested(f"STOP sentinel at {stop}")
    pause = run_dir / "PAUSE"
    while pause.exists():
        time.sleep(30)
    wait = run_dir / "wait_until.txt"
    if wait.exists():
        try:
            target = wait.read_text().strip().rstrip("Z")
            t = time.strptime(target, "%Y-%m-%dT%H:%M:%S")
            target_epoch = time.mktime(t) - time.timezone
            now = time.time()
            if target_epoch > now:
                # Sleep in 60s chunks so STOP can still interrupt.
                while time.time() < target_epoch:
                    if stop.exists():
                        raise StopRequested(f"STOP during wait_until at {stop}")
                    time.sleep(min(60, max(1, target_epoch - time.time())))
            # one-shot: remove the wait file after the wait elapses
            try:
                wait.unlink()
            except OSError:
                pass
        except ValueError:
            # malformed wait_until — ignore (log left to caller)
            pass


# --- Resume helpers -----------------------------------------------------------
def progress_tail(run_dir: Path, n: int = 50) -> list[dict]:
    p = run_dir / "progress.jsonl"
    if not p.exists():
        return []
    lines = p.read_text(encoding="utf-8").splitlines()[-n:]
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def last_completed_step(run_dir: Path) -> tuple[int, str] | None:
    """Return (stage, step) of the last 'ok' row, or None."""
    for row in reversed(progress_tail(run_dir, n=500)):
        if row.get("status") == "ok":
            return row.get("stage", 0), row.get("step", "")
    return None
