"""Cost gate + audit reconciliation.

Sums actual costs from audit.jsonl, compares against the caps in task.yaml,
returns a decision dict the caller (route.py / dispatch.py) consumes before
making a worker call.

Cost is reported in agents' meta.json — *if* the CLI prints token counts the
wrapper can parse. Most wrappers don't (yet); the actual numbers may be None.
That means budget gating is best-effort on *estimates* and only catches real
overruns post-hoc when actuals exist.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _read_yaml_floats(task_path: Path) -> tuple[float, float]:
    """Extract per_call_cap_usd and total_cap_usd from task.yaml."""
    per_call = 0.50
    total = 2.00
    for line in task_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("per_call_cap_usd:"):
            try:
                per_call = float(line.split(":", 1)[1].strip())
            except (ValueError, IndexError):
                pass
        elif line.startswith("total_cap_usd:"):
            try:
                total = float(line.split(":", 1)[1].strip())
            except (ValueError, IndexError):
                pass
    return per_call, total


def total_spent(run_dir: Path) -> float:
    """Sum cost_actual_usd from audit.jsonl.
    Tolerates missing file, malformed JSON rows, null/non-numeric values
    (all silently skipped) — the audit log is append-only and may contain
    partial rows from interrupted writes."""
    audit = run_dir / "audit.jsonl"
    if not audit.exists():
        return 0.0
    total = 0.0
    for line in audit.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        v = row.get("cost_actual_usd")
        if v is None:
            continue
        try:
            total += float(v)
        except (TypeError, ValueError):
            continue
    return total


def gate(run_dir: Path, *, estimated_next_call_usd: float) -> dict:
    per_call, total_cap = _read_yaml_floats(run_dir / "task.yaml")
    spent = total_spent(run_dir)
    decision = {
        "spent_so_far_usd": round(spent, 4),
        "estimated_next_call_usd": round(estimated_next_call_usd, 4),
        "per_call_cap_usd": per_call,
        "total_cap_usd": total_cap,
        "ok": True,
        "reasons": [],
    }
    if estimated_next_call_usd > per_call:
        decision["ok"] = False
        decision["reasons"].append(
            f"estimated ${estimated_next_call_usd:.2f} > per-call cap ${per_call:.2f}"
        )
    if spent + estimated_next_call_usd > total_cap:
        decision["ok"] = False
        decision["reasons"].append(
            f"spent ${spent:.2f} + est ${estimated_next_call_usd:.2f} > total cap ${total_cap:.2f}"
        )
    return decision


def reconcile(run_dir: Path) -> dict:
    """Compare per-agent estimates (cost_est_usd in meta.json) against actuals
    in audit.jsonl. Returns a summary; flags agents whose actuals exceed
    estimate by >2× as 'estimate-stale' and appends a progress.jsonl warning
    row when any are stale (so the orchestrator can decide to pause)."""
    import progress as _P  # local import to avoid cycle
    agents_dir = run_dir / "agents"
    if not agents_dir.exists():
        return {"agents": {}, "stale": []}
    summary: dict[str, dict] = {}
    stale: list[str] = []
    for sub in agents_dir.iterdir():
        if not sub.is_dir():
            continue
        meta_p = sub / "meta.json"
        if not meta_p.exists():
            continue
        try:
            meta = json.loads(meta_p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        est = meta.get("cost_est_usd")
        act = meta.get("cost_actual_usd")
        summary[sub.name] = {"est": est, "actual": act}
        try:
            if est is not None and act is not None and float(act) > 2 * float(est):
                stale.append(sub.name)
        except (TypeError, ValueError):
            continue
    if stale:
        _P.append_progress(
            run_dir, stage=2, step="budget_reconcile", status="warning",
            detail=f"estimate-stale agents (actual > 2× est): {stale}",
        )
    return {"agents": summary, "stale": stale}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True, type=Path)
    ap.add_argument("--estimated-next-call-usd", type=float, default=0.0)
    ap.add_argument("--reconcile", action="store_true")
    args = ap.parse_args(argv)
    if args.reconcile:
        print(json.dumps(reconcile(args.run_dir), indent=2))
    else:
        decision = gate(args.run_dir, estimated_next_call_usd=args.estimated_next_call_usd)
        print(json.dumps(decision, indent=2))
        return 0 if decision["ok"] else 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
