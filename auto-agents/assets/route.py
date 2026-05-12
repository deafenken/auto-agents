"""Stage 1 — classify task and write route.json.

The data (which agent for which class, which keywords trigger which class) lives
in ../references/agent-matrix.md as the source of truth for editors. This file
is the algorithm that consumes that data. The matrix data is duplicated as
Python constants here for execution, but if you change one update both.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import progress as P
import yaml_io

# --- Matrix data (mirrors agent-matrix.md) ------------------------------------
TASK_CLASSES = {
    "code-write":  {"primary": ["claude", "codex"],                     "synthesis": "inline"},
    "code-review": {"primary": ["codex", "claude"],                     "synthesis": "inline"},
    "math":        {"primary": ["opencode", "claude"],                  "synthesis": "inline"},
    "idea":        {"primary": ["claude", "codex", "opencode"],         "synthesis": "meta-synth"},
    "debate":      {"primary": ["claude", "codex", "opencode"],         "synthesis": "debate"},
    "research":    {"primary": ["claude"],                              "synthesis": "inline"},
    "quick-qa":    {"primary": ["__host__"],                            "synthesis": "inline"},
}

# Rough $/call estimates (mid-range). Reconciled with audit.jsonl actuals.
COST_ESTIMATE_USD = {"claude": 0.20, "codex": 0.12, "opencode": 0.05}

# Classification heuristics; first-match-wins ordering.
KEYWORDS = [
    ("code-review", [r"\baudit\b", r"\breview\b", r"\bbug(s)?\b",
                     r"\bsecurity\b", r"\blint\b", r"correctness check"]),
    ("math",        [r"\bprove\b", r"\bderive\b", r"\btheorem\b", r"\bintegral\b",
                     r"combinatorics", r"step-by-step solve", r"证明", r"推导"]),
    ("idea",        [r"\bbrainstorm\b", r"\bpropose\b", r"\bideas?\b",
                     r"alternatives", r"what could we", r"多个角度", r"头脑风暴"]),
    ("debate",      [r"\bdebate\b", r"\badversarial\b", r"steelman",
                     r"for and against", r"pros and cons", r"辩论"]),
    ("research",    [r"find papers", r"search the web",
                     r"who (first )?(said|wrote|proved|discovered|showed|claimed|invented)",
                     r"\bcite\b", r"references", r"prior work"]),
    ("code-write",  [r"\bwrite\b", r"\bimplement\b", r"\badd\b",
                     r"\brefactor\b", r"fix the function", r"修改", r"实现"]),
]


def classify(prompt: str) -> tuple[str, str]:
    lower = prompt.lower()
    for cls, patterns in KEYWORDS:
        for p in patterns:
            m = re.search(p, lower)
            if m:
                return cls, f"matched /{p}/"
    return "quick-qa", "no keyword matched"


KNOWN_MODES = {"auto", "multi", "dry-run"}


def _select_agents(task_class: str, host: str, available: dict[str, bool],
                   mode: str) -> tuple[list[str], dict[str, str], str, list[str]]:
    """Returns (agents, agent_modes, synthesis_method, escalations)."""
    escalations: list[str] = []
    cls = TASK_CLASSES[task_class]
    primary = cls["primary"]
    synthesis = cls["synthesis"]

    # Validate mode — reject anything we don't recognize (no silent fallback).
    if mode not in KNOWN_MODES and not mode.startswith("single:"):
        escalations.append(
            f"unknown mode '{mode}' — expected one of: "
            f"{sorted(KNOWN_MODES)} or 'single:<agent>'"
        )
        return [], {}, "inline", escalations

    if mode.startswith("single:"):
        only = mode.split(":", 1)[1]
        if only not in available:
            escalations.append(f"unknown agent '{only}'")
            return [], {}, "inline", escalations
        if only != host and not available.get(only, False):
            escalations.append(f"requested agent '{only}' unavailable")
            return [], {}, "inline", escalations
        return ([only],
                {only: "inline" if only == host else "subprocess"},
                "inline",
                escalations)

    if mode == "multi":
        all_three = ("claude", "codex", "opencode")
        agents = [a for a in all_three if available.get(a, False)]
        if len(agents) < 3:
            missing = [a for a in all_three if not available.get(a, False)]
            escalations.append(
                f"mode=multi requested all three agents but missing: {missing} "
                "(integrity rule #1: no silent agent swap)"
            )
        modes = {a: "inline" if a == host else "subprocess" for a in agents}
        return agents, modes, "meta-synth" if len(agents) > 1 else "inline", escalations

    # mode == "auto" or "dry-run": use matrix (dry-run differs only in Stage 2)
    if primary == ["__host__"]:
        return [host], {host: "inline"}, "inline", escalations

    if task_class in ("idea", "debate"):
        agents = [a for a in primary if available.get(a, False)]
        if host not in agents and available.get(host, False):
            agents.insert(0, host)
        missing = [a for a in primary if not available.get(a, False) and a != host]
        if missing:
            escalations.append(
                f"task_class={task_class} wants all three agents but missing: "
                f"{missing} (integrity rule #1)"
            )
        modes = {a: "inline" if a == host else "subprocess" for a in agents}
        return agents, modes, synthesis if len(agents) > 1 else "inline", escalations

    # single-agent classes: pick the highest-priority *available* agent
    chosen = None
    for a in primary:
        if a == host:
            chosen = host
            break
        if available.get(a, False):
            chosen = a
            break
    if chosen is None:
        escalations.append(f"no agent available for class={task_class}")
        return [], {}, "inline", escalations
    if chosen != primary[0]:
        escalations.append(
            f"primary agent '{primary[0]}' unavailable; fallback to '{chosen}' "
            "needs user confirmation (integrity rule #1: no silent agent swap)"
        )
    return ([chosen],
            {chosen: "inline" if chosen == host else "subprocess"},
            "inline",
            escalations)


def run_stage1(run_dir: Path) -> dict:
    P.check_sentinels(run_dir)
    P.write_heartbeat(run_dir, stage=1, step="classify")

    task = yaml_io.load_path(run_dir / "task.yaml")
    prompt = task.get("prompt", "")
    host = task["host"]
    mode = task.get("mode", "auto")
    available = task.get("workers_available", {})
    per_call_cap = float(task.get("per_call_cap_usd", 0.50))

    task_class, reason = classify(prompt)
    P.append_progress(run_dir, stage=1, step="classify", status="ok",
                      detail=f"{task_class} ({reason})")

    P.write_heartbeat(run_dir, stage=1, step="select_agents")
    agents, agent_modes, synthesis, escalations = _select_agents(
        task_class, host, available, mode,
    )

    cost_estimate = sum(
        COST_ESTIMATE_USD.get(a, 0.0)
        for a, m in agent_modes.items() if m == "subprocess"
    )
    if cost_estimate > per_call_cap * len(
        [m for m in agent_modes.values() if m == "subprocess"] or [1]
    ):
        escalations.append(
            f"estimated cost ${cost_estimate:.2f} exceeds per-call cap "
            f"${per_call_cap:.2f}"
        )

    route = {
        "task_class": task_class,
        "classification_reason": reason,
        "agents": agents,
        "agent_modes": agent_modes,
        "synthesis_method": synthesis,
        "cost_estimate_usd": round(cost_estimate, 4),
        "inline_host_used": agent_modes.get(host) == "inline",
        "escalations": escalations,
    }
    P.atomic_write_json(run_dir / "route.json", route)
    P.append_progress(
        run_dir, stage=1, step="select_agents",
        status="needs-user" if escalations else "ok",
        detail=" | ".join(escalations) if escalations
               else f"{agents} synth={synthesis}",
    )
    return route


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True, type=Path)
    args = ap.parse_args(argv)
    route = run_stage1(args.run_dir)
    print(json.dumps(route, indent=2, ensure_ascii=False))
    return 1 if route.get("escalations") else 0


if __name__ == "__main__":
    sys.exit(main())
