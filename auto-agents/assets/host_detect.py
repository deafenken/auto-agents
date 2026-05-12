"""Detect which of {claude, codex, opencode} is the host CLI.

Three-tier algorithm. See ../references/host-cli-modes.md for the contract.

Result is a dict with keys:
    host:        one of "claude" | "codex" | "opencode" | None
    detection:   one of "env-override" | "env-var:<NAME>" | "ps-chain:<NAME>"
                 | "cache" | "user-asked" | None
    candidates:  list of candidates discovered (for audit)
    refused:     bool — True iff AUTO_AGENTS_DEPTH >= 1 (recursion guard)

When host is None and refused is False, the caller (auth_check.py / Stage 0)
must prompt the user; this module never blocks on stdin.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

# --- Env-var families ---------------------------------------------------------
ENV_FAMILIES = {
    "claude":   ("CLAUDECODE", "CLAUDE_CODE", "CLAUDE_CODE_ENTRYPOINT"),
    "codex":    ("CODEX_CLI", "CODEX_ENV", "CODEX_HOME"),
    "opencode": ("OPENCODE", "OPENCODE_ENV", "OPENCODE_HOME"),
}

CACHE_PATH = Path.home() / ".config" / "auto-agents" / "host.yaml"
CACHE_MAX_AGE_SEC = 30 * 24 * 3600  # 30 days
PS_CHAIN_DEPTH_CAP = 8
PS_TIMEOUT_SEC = 2


def _env_tier() -> tuple[str | None, list[str], str | None]:
    """Returns (host_if_unique, all_matched_families, matched_env_var)."""
    matches: dict[str, str] = {}
    for fam, vars_ in ENV_FAMILIES.items():
        for v in vars_:
            if v in os.environ and os.environ[v].strip():
                matches[fam] = v
                break
    if len(matches) == 1:
        ((fam, var),) = matches.items()
        return fam, [fam], var
    return None, sorted(matches.keys()), None


def _parent_pid(pid: int) -> int | None:
    try:
        out = subprocess.run(
            ["ps", "-o", "ppid=", "-p", str(pid)],
            capture_output=True, text=True, timeout=PS_TIMEOUT_SEC,
        )
        if out.returncode != 0:
            return None
        ppid = out.stdout.strip()
        return int(ppid) if ppid.isdigit() else None
    except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
        return None


def _proc_name(pid: int) -> str | None:
    try:
        out = subprocess.run(
            ["ps", "-o", "comm=", "-p", str(pid)],
            capture_output=True, text=True, timeout=PS_TIMEOUT_SEC,
        )
        if out.returncode != 0:
            return None
        name = out.stdout.strip()
        return os.path.basename(name) if name else None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def _ps_chain_tier() -> tuple[str | None, list[tuple[int, str]], list[str]]:
    """Walk parent chain; return (closest_host, chain_for_audit, all_hits).
    all_hits has >1 entry only when the chain contains nested host CLIs —
    caller should log a warning in that case (nested invocation)."""
    targets = set(ENV_FAMILIES)
    chain: list[tuple[int, str]] = []
    all_hits: list[str] = []
    closest: str | None = None
    pid = os.getppid()
    for _ in range(PS_CHAIN_DEPTH_CAP):
        if pid is None or pid <= 1:
            break
        name = _proc_name(pid) or ""
        chain.append((pid, name))
        hits = [t for t in targets if t in name.lower()]
        for h in hits:
            if h not in all_hits:
                all_hits.append(h)
        if closest is None and hits:
            closest = hits[0]
        pid = _parent_pid(pid)
    return closest, chain, all_hits


def _cache_tier() -> tuple[str | None, str | None]:
    """Read ~/.config/auto-agents/host.yaml; return (host, prior_detection)."""
    if not CACHE_PATH.exists():
        return None, None
    try:
        text = CACHE_PATH.read_text()
        # tiny YAML subset: host: <name> / confirmed_utc: <iso> / confirmed_by: <s>
        data: dict[str, str] = {}
        for line in text.splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                data[k.strip()] = v.strip()
        host = data.get("host")
        confirmed = data.get("confirmed_utc", "")
        if host not in ENV_FAMILIES:
            return None, None
        # age check (best-effort; if parse fails, treat as expired)
        try:
            # parse "2026-05-12T16:40:00Z" → epoch
            t = time.strptime(confirmed.rstrip("Z"), "%Y-%m-%dT%H:%M:%S")
            age = time.time() - (time.mktime(t) - time.timezone)
            if age > CACHE_MAX_AGE_SEC:
                return None, None
        except ValueError:
            return None, None
        return host, data.get("confirmed_by")
    except OSError:
        return None, None


def write_cache(host: str, detection: str) -> None:
    """Persist confirmed host. Caller invokes this only after Tier 3 (user ask)."""
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    body = (
        f"host: {host}\n"
        f"confirmed_utc: {iso}\n"
        f"confirmed_by: {detection}\n"
    )
    tmp = CACHE_PATH.with_suffix(".yaml.tmp")
    tmp.write_text(body)
    os.replace(tmp, CACHE_PATH)


def detect() -> dict:
    raw_depth = os.environ.get("AUTO_AGENTS_DEPTH", "0") or "0"
    try:
        depth = int(raw_depth)
    except (TypeError, ValueError):
        # Defensive: hostile / corrupted env var → treat as nested to be safe.
        return {
            "host": None, "detection": None, "candidates": [],
            "refused": True,
            "reason": f"AUTO_AGENTS_DEPTH={raw_depth!r} is not an integer",
        }
    if depth >= 1:
        return {
            "host": None, "detection": None, "candidates": [],
            "refused": True, "reason": f"AUTO_AGENTS_DEPTH={depth}",
        }

    # Override env var wins over everything.
    override = os.environ.get("AUTO_AGENTS_HOST", "").strip().lower()
    if override in ENV_FAMILIES:
        return {
            "host": override, "detection": "env-override",
            "candidates": [override], "refused": False,
        }

    # Tier 1 — env-var families
    host, candidates, var = _env_tier()
    if host is not None:
        return {
            "host": host, "detection": f"env-var:{var}",
            "candidates": candidates, "refused": False,
        }

    # Tier 2 — parent process chain
    host, chain, all_hits = _ps_chain_tier()
    if host is not None:
        result = {
            "host": host, "detection": f"ps-chain:{host}",
            "candidates": [name for _, name in chain], "refused": False,
        }
        if len(all_hits) > 1:
            # Nested host CLIs in the chain → suspicious. We pick the closest
            # but flag it so the caller can write a progress.jsonl warning.
            result["warning"] = (
                f"multiple host CLIs in parent chain: {all_hits}; "
                f"using closest={host} but check for nested invocation"
            )
        return result

    # Tier 3a — cache
    host, prior = _cache_tier()
    if host is not None:
        return {
            "host": host, "detection": "cache",
            "candidates": [], "refused": False,
            "prior_detection": prior,
        }

    # Tier 3b — must ask the user (caller's job)
    return {
        "host": None, "detection": None, "candidates": candidates,
        "ps_chain": chain, "refused": False,
        "needs_user_input": True,
    }


if __name__ == "__main__":
    result = detect()
    print(json.dumps(result, indent=2))
    # exit code 0 if we know the host, 2 if we need to ask, 3 if refused
    if result.get("refused"):
        sys.exit(3)
    sys.exit(0 if result.get("host") else 2)
