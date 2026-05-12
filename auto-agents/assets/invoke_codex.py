"""Subprocess wrapper for the `codex` (OpenAI Codex) CLI.

Known-good invocation pattern: `codex exec "<prompt>"`. Override with
AUTO_AGENTS_CODEX_CMD if your install differs (the env value is shell-split
and the prompt is appended as the last positional argument).

Does NOT try alternate flags on failure — per integrity rule #5.
"""
from __future__ import annotations

import os
import shlex
import subprocess
import time

DEFAULT_CMD = "codex exec"
DEFAULT_TIMEOUT_SEC = 600
VERSION_TIMEOUT_SEC = 10


def _resolved_cmd() -> list[str]:
    raw = os.environ.get("AUTO_AGENTS_CODEX_CMD", DEFAULT_CMD)
    return shlex.split(raw)


def version_check() -> tuple[bool, str]:
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
        exit_code = 124
        stdout = e.stdout.decode("utf-8", "replace") if e.stdout else ""
        stderr = (e.stderr.decode("utf-8", "replace") if e.stderr else "") + \
                 f"\n[auto-agents] killed after {timeout_sec}s"
    ended = time.time()
    return {
        "agent": "codex",
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "duration_s": round(ended - started, 3),
        "cmd": " ".join(shlex.quote(a) for a in argv[:-1]) + " <prompt>",
        "ts_started_utc": ts_started,
        "ts_ended_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ended)),
    }


def extract_answer(stdout: str) -> str:
    """`codex exec` prints assistant text to stdout; some versions include a
    leading banner line. Drop a leading line that starts with 'codex'."""
    lines = stdout.splitlines()
    if lines and lines[0].lower().startswith("codex"):
        lines = lines[1:]
    return "\n".join(lines).rstrip() + "\n"
