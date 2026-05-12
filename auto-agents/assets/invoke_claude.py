"""Subprocess wrapper for the `claude` (Claude Code) CLI.

Known-good invocation pattern: `claude -p "<prompt>"`. Override with
AUTO_AGENTS_CLAUDE_CMD if your install differs (the env value is shell-split
and the prompt is appended as the last positional argument).

Does NOT try alternate flags on failure — per integrity rule #5 (no CLI flag
fabrication). Raw stdout/stderr/exit_code are returned; the caller decides
what to do with errors.
"""
from __future__ import annotations

import os
import shlex
import subprocess
import time
from pathlib import Path

DEFAULT_CMD = "claude -p"
DEFAULT_TIMEOUT_SEC = 600  # 10 min cap per call; dispatcher can override
VERSION_TIMEOUT_SEC = 10


def _resolved_cmd() -> list[str]:
    raw = os.environ.get("AUTO_AGENTS_CLAUDE_CMD", DEFAULT_CMD)
    return shlex.split(raw)


def version_check() -> tuple[bool, str]:
    """Run `claude --version`. Returns (ok, detail)."""
    cmd_head = _resolved_cmd()[0]
    try:
        out = subprocess.run(
            [cmd_head, "--version"],
            capture_output=True, text=True,
            timeout=VERSION_TIMEOUT_SEC,
        )
        if out.returncode == 0:
            return True, (out.stdout or out.stderr).strip().splitlines()[0]
        return False, f"exit={out.returncode} stderr={out.stderr[:200]}"
    except FileNotFoundError:
        return False, "binary-missing"
    except subprocess.TimeoutExpired:
        return False, "version-timeout"


def invoke(prompt: str, *, env_overrides: dict | None = None,
           timeout_sec: int = DEFAULT_TIMEOUT_SEC) -> dict:
    """Run claude with the prompt. Returns a result dict with:
        exit_code, stdout, stderr, duration_s, cmd, ts_started, ts_ended.
    Caller is responsible for writing files and parsing/cost-accounting.
    """
    argv = _resolved_cmd() + [prompt]
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    started = time.time()
    ts_started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started))
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True,
            timeout=timeout_sec, env=env,
        )
        exit_code = proc.returncode
        stdout, stderr = proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as e:
        exit_code = 124  # conventional timeout exit
        stdout = e.stdout.decode("utf-8", "replace") if e.stdout else ""
        stderr = (e.stderr.decode("utf-8", "replace") if e.stderr else "") + \
                 f"\n[auto-agents] killed after {timeout_sec}s"
    ended = time.time()
    return {
        "agent": "claude",
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "duration_s": round(ended - started, 3),
        "cmd": " ".join(shlex.quote(a) for a in argv[:-1]) + " <prompt>",
        "ts_started_utc": ts_started,
        "ts_ended_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ended)),
    }


def extract_answer(stdout: str) -> str:
    """Claude `-p` prints the assistant text directly. Trim trailing blanks."""
    return stdout.rstrip() + "\n"
