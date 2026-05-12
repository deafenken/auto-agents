"""Stage 3 — merge agent outputs into synthesis/final.md.

Three methods:
  - inline      : 1 successful agent → copy result + contributors block
  - vote        : majority on the first-line label across agents
  - meta-synth  : host-written unified answer with attribution (DEFAULT for idea)
  - debate      : two-round structured (this script writes round 1 + round 2
                  invocations and the moderator template; the host fills in the
                  final synthesis paragraph)

The host model is responsible for the actual *writing* in meta-synth and the
debate moderator pass — this script prepares the inputs (concatenated worker
outputs, prompts), and validates the output. Vote is fully automated.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

import progress as P


def _read_route(run_dir: Path) -> dict:
    return json.loads((run_dir / "route.json").read_text(encoding="utf-8"))


def _read_agent_result(run_dir: Path, agent: str) -> tuple[str | None, str]:
    """Returns (status, result_text). status comes from meta.json."""
    agent_dir = run_dir / "agents" / agent
    meta_path = agent_dir / "meta.json"
    if not meta_path.exists():
        return None, ""
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, ""
    status = meta.get("status")
    result_path = agent_dir / "result.md"
    text = result_path.read_text(encoding="utf-8") if result_path.exists() else ""
    return status, text


def _audit_totals(run_dir: Path) -> tuple[float, float]:
    """Returns (total_duration_s, total_cost_actual_usd) from audit.jsonl."""
    audit = run_dir / "audit.jsonl"
    if not audit.exists():
        return 0.0, 0.0
    dur = 0.0
    cost = 0.0
    for line in audit.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        dur += float(row.get("duration_s") or 0)
        cost += float(row.get("cost_actual_usd") or 0)
    return dur, cost


def _contributors_block(run_dir: Path, agents: list[str]) -> str:
    lines = ["## Contributors", ""]
    for a in agents:
        status, text = _read_agent_result(run_dir, a)
        if status == "ok":
            sample = text.strip().splitlines()[0] if text.strip() else ""
            lines.append(f"- **{a}** — see `agents/{a}/result.md` "
                         f"{'(opening: ' + sample[:80] + '…)' if sample else ''}")
        elif status == "pending":
            lines.append(f"- **{a}** — *pending* (host inline; result.md not yet written)")
        else:
            lines.append(f"- **{a}** — *failed* (status={status})")
    return "\n".join(lines) + "\n"


def _audit_block(run_dir: Path) -> str:
    dur, cost = _audit_totals(run_dir)
    return (
        "## Audit\n\n"
        f"- Total subprocess time: {dur:.1f}s\n"
        f"- Total subprocess cost (recorded): ${cost:.4f}\n"
        "- Per-call breakdown: `audit.jsonl`\n"
    )


def _write_method_md(run_dir: Path, method: str, note: str = "") -> None:
    body = f"# Synthesis method: {method}\n\n{note}\n"
    P.atomic_write_text(run_dir / "synthesis" / "method.md", body)


# --- inline -------------------------------------------------------------------
def synth_inline(run_dir: Path, route: dict) -> str:
    agents = route["agents"]
    assert len(agents) == 1, "inline synthesis expects exactly one agent"
    a = agents[0]
    status, text = _read_agent_result(run_dir, a)
    if status != "ok":
        return ("# Answer\n\n"
                f"_The sole agent `{a}` did not complete successfully "
                f"(status={status}). No answer to report._\n\n"
                + _contributors_block(run_dir, agents)
                + "\n## Synthesis method: inline (failed)\n\n"
                + _audit_block(run_dir))
    return (
        "# Answer\n\n"
        + text.rstrip() + "\n\n---\n\n"
        + _contributors_block(run_dir, agents)
        + "\n## Synthesis method: inline\n\n"
        + f"Single agent `{a}` answered directly; no merge needed.\n\n"
        + _audit_block(run_dir)
    )


# --- vote ---------------------------------------------------------------------
def _normalize_label(s: str) -> str:
    return re.sub(r"[^\w\-]+", "", s.strip().lower())


def synth_vote(run_dir: Path, route: dict) -> tuple[str, dict]:
    """Tally labels (first non-empty line of each result.md). Returns (final_md, tally_dict)."""
    labels: dict[str, str] = {}
    justifs: dict[str, str] = {}
    for a in route["agents"]:
        status, text = _read_agent_result(run_dir, a)
        if status != "ok" or not text.strip():
            labels[a] = "__failed__"
            justifs[a] = ""
            continue
        lines = [ln for ln in text.splitlines() if ln.strip()]
        labels[a] = lines[0].strip() if lines else "__empty__"
        justifs[a] = lines[1].strip() if len(lines) > 1 else ""
    normed = {a: _normalize_label(v) for a, v in labels.items()
              if v not in ("__failed__", "__empty__")}
    tally = Counter(normed.values())
    if not tally:
        return ("# Answer\n\n_All agents failed to produce a labeled answer._\n\n"
                + _contributors_block(run_dir, route["agents"])
                + "\n## Synthesis method: vote (no valid ballots)\n\n"
                + _audit_block(run_dir)), {"tally": {}, "winner": None}
    winner_norm, winner_count = tally.most_common(1)[0]
    n_valid = sum(tally.values())
    majority = winner_count > n_valid // 2
    # find one original-cased label that matches
    winner_label = next(v for a, v in labels.items()
                        if _normalize_label(v) == winner_norm)
    final = (
        "# Answer\n\n"
        f"**{winner_label}**"
        + (" *(majority)*" if majority else " *(plurality — NO majority — see escalation)*")
        + "\n\n## Justifications\n\n"
        + "\n".join(f"- **{a}** → {labels[a]!r}: {justifs[a] or '(none provided)'}"
                    for a in route["agents"])
        + "\n\n---\n\n"
        + _contributors_block(run_dir, route["agents"])
        + "\n## Synthesis method: vote\n\n"
        + f"Tally: {dict(tally)}; winner={winner_label!r}; majority={majority}.\n\n"
        + _audit_block(run_dir)
    )
    return final, {"labels": labels, "tally": dict(tally),
                   "winner": winner_label, "majority": majority}


# --- meta-synth ---------------------------------------------------------------
META_SYNTH_HOST_INSTRUCTIONS = """\
# Host instructions: meta-synth

The file `synthesis/intermediate/meta-synth-input.md` contains every worker
output, separated by `--- <agent> ---` markers.

Write `synthesis/final.md` with this structure:

  # Answer
  <one unified answer that weaves together the workers' ideas.>
  <Inline-attribute: when a sentence comes from one agent specifically,
   name that agent in the sentence or in a trailing parenthetical.>

  ---

  ## Contributors
  - one bullet per agent naming what they contributed
  - mark any failed agent as failed

  ## Synthesis method: meta-synth
  <one paragraph: what overlapped, what conflicted, how you resolved>

  ## Audit
  (will be auto-appended; you can leave a placeholder)

Do NOT paraphrase an agent's output as your own. Do NOT include claims that
no worker output backs.
"""


def synth_meta_prepare(run_dir: Path, route: dict) -> str:
    """Build meta-synth-input.md and write host instructions. Returns the inputs
    path so the host can read it. The host then writes final.md itself."""
    inter = run_dir / "synthesis" / "intermediate"
    inter.mkdir(parents=True, exist_ok=True)
    parts: list[str] = []
    for a in route["agents"]:
        status, text = _read_agent_result(run_dir, a)
        if status == "ok" and text.strip():
            parts.append(f"--- {a} ---\n{text.rstrip()}\n")
        else:
            parts.append(f"--- {a} ---\n(no output; status={status})\n")
    P.atomic_write_text(inter / "meta-synth-input.md", "\n".join(parts))
    P.atomic_write_text(inter / "host-instructions.md",
                        META_SYNTH_HOST_INSTRUCTIONS)
    return str(inter / "meta-synth-input.md")


# --- debate -------------------------------------------------------------------
DEBATE_ROUND1_SUFFIX = (
    "\n\n---\nState your position in ≤300 words. "
    "Lead with a one-sentence claim. Cite your reasoning explicitly. Do not hedge."
)
DEBATE_ROUND2_PREFIX = (
    "Here are the opening positions from the other agents:\n\n"
)
DEBATE_ROUND2_SUFFIX = (
    "\n\nCritique their reasoning. Restate or revise your own position in ≤300 words. "
    "Lead with 'I agree with <X> on <Y>, but disagree on <Z>' if applicable; "
    "otherwise lead with a one-sentence revised claim."
)


def synth_debate_prepare(run_dir: Path, route: dict) -> dict:
    """Materialize round-1 inputs and round-2 prompts. The dispatch loop must
    re-run dispatch.py twice for debate (one per round). This script's job is
    only to *prepare* and *validate*."""
    inter = run_dir / "synthesis" / "intermediate"
    inter.mkdir(parents=True, exist_ok=True)
    round1_concat = []
    for a in route["agents"]:
        status, text = _read_agent_result(run_dir, a)
        if status == "ok" and text.strip():
            round1_concat.append(f"--- {a} ---\n{text.rstrip()}\n")
        else:
            round1_concat.append(f"--- {a} ---\n(no output; status={status})\n")
    P.atomic_write_text(inter / "debate-round-1.md", "\n".join(round1_concat))
    return {
        "round1_concat_path": str(inter / "debate-round-1.md"),
        "round1_suffix": DEBATE_ROUND1_SUFFIX,
        "round2_prefix": DEBATE_ROUND2_PREFIX,
        "round2_suffix": DEBATE_ROUND2_SUFFIX,
        "next_step": "host runs dispatch.py round 2 with augmented prompts, "
                     "then re-invokes synthesize.py",
    }


# --- top-level ----------------------------------------------------------------
def run_stage3(run_dir: Path) -> dict:
    P.check_sentinels(run_dir)
    route = _read_route(run_dir)
    method = route.get("synthesis_method", "inline")
    (run_dir / "synthesis").mkdir(parents=True, exist_ok=True)
    P.write_heartbeat(run_dir, stage=3, step=f"synth:{method}")

    if method == "inline":
        final = synth_inline(run_dir, route)
        _write_method_md(run_dir, "inline", "Single agent; no merge.")
        P.atomic_write_text(run_dir / "synthesis" / "final.md", final)
        P.append_progress(run_dir, stage=3, step="synth:inline", status="ok")
        return {"status": "ok", "method": "inline"}

    if method == "vote":
        final, tally = synth_vote(run_dir, route)
        _write_method_md(run_dir, "vote",
                         f"Tally: `synthesis/intermediate/vote-tally.json`")
        P.atomic_write_json(run_dir / "synthesis" / "intermediate" /
                            "vote-tally.json", tally)
        P.atomic_write_text(run_dir / "synthesis" / "final.md", final)
        P.append_progress(run_dir, stage=3, step="synth:vote",
                          status="ok" if tally.get("majority") else "needs-user",
                          detail=f"winner={tally.get('winner')}")
        return {"status": "ok", "method": "vote", "tally": tally}

    if method == "meta-synth":
        input_path = synth_meta_prepare(run_dir, route)
        _write_method_md(run_dir, "meta-synth",
                         f"Host should read `{input_path}` and write final.md.")
        P.append_progress(run_dir, stage=3, step="synth:meta-synth",
                          status="pending-host",
                          detail="meta-synth-input.md ready; host writes final.md")
        return {"status": "pending-host", "method": "meta-synth",
                "input_path": input_path}

    if method == "debate":
        prep = synth_debate_prepare(run_dir, route)
        _write_method_md(run_dir, "debate",
                         "Round-2 prompts prepared; re-run dispatch then synthesize.")
        P.append_progress(run_dir, stage=3, step="synth:debate",
                          status="pending-round2", detail=prep["next_step"])
        return {"status": "pending-round2", "method": "debate", **prep}

    P.append_progress(run_dir, stage=3, step=f"synth:{method}",
                      status="failed", detail="unknown synthesis method")
    return {"status": "failed", "method": method, "reason": "unknown method"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True, type=Path)
    args = ap.parse_args(argv)
    try:
        out = run_stage3(args.run_dir)
    except P.StopRequested as e:
        P.append_progress(args.run_dir, stage=3, step="stop_sentinel",
                          status="stopped-by-user", detail=str(e))
        return 2
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if out.get("status") in ("ok", "pending-host", "pending-round2") else 1


if __name__ == "__main__":
    sys.exit(main())
