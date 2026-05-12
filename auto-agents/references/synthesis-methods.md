# Synthesis methods

Three ways to merge ≥2 worker outputs into one `synthesis/final.md`. Implemented in `assets/synthesize.py`. Which one is used is recorded in `route.json: synthesis_method` and `synthesis/method.md`.

## inline (1 agent)

No actual synthesis. The single agent's `result.md` is copied verbatim into `final.md` and the "Contributors" block lists just that one agent. Used whenever the router picks a single agent.

## vote

Used for tasks with discrete answers (e.g. "is this code safe? yes/no", "which of these PRs should we merge: A/B/C", "is statement X true?"). Not used by default — opt-in via `route.json` override or `--synthesis=vote`.

Algorithm:

1. For each agent, send the prompt plus a suffix:
   ```
   Reply with EXACTLY two lines:
   Line 1: a one-word or one-phrase label (your answer).
   Line 2: a one-sentence justification.
   ```
2. Parse each `agents/<name>/result.md`: first non-empty line = label, second = justification.
3. Tally labels. Normalize (case-fold, strip punctuation).
4. **Majority** (≥ ⌈n/2⌉+1 agreeing) wins → `final.md` records the winning label, all justifications, and tally.
5. **No majority**: escalate. Either ask the user, or fall back to meta-synth on the same outputs (the synthesizer asks first; default is escalate).

Write `synthesis/intermediate/vote-tally.json`:

```json
{
  "labels": {"claude": "yes", "codex": "yes", "opencode": "no"},
  "tally": {"yes": 2, "no": 1},
  "winner": "yes",
  "majority": true
}
```

## debate (default for task_class = `debate`)

Two-round structured debate, host-moderated. Used when adversarial perspective is the point.

> **v1 status:** `synthesize.py:synth_debate_prepare` writes
> `synthesis/intermediate/debate-round-1.md` from the workers' first-pass
> outputs and returns round-2 prompt fragments. A driver that actually
> re-dispatches each worker with the round-2 prompt and writes
> `debate-round-2.md` is a **v2 follow-up** — for now the round-2 prompts
> are documented and produced as data, and the orchestrator should escalate
> to the user if a full two-round debate is required.

Round 1 — **opening positions** (parallel):

- Each agent receives the original prompt + a suffix:
  ```
  State your position in ≤300 words. Lead with a one-sentence claim.
  Cite your reasoning explicitly. Do not hedge.
  ```
- Outputs land in `agents/<name>/result.md` (round-1 version) and `synthesis/intermediate/debate-round-1.md` (concatenated).

Round 2 — **rebuttals** (parallel, each agent reads the *other* agents' round-1):

- For each agent, the prompt is:
  ```
  Here are the opening positions from the other agents:

  --- <other_1> ---
  <other_1's round-1 text>
  --- <other_2> ---
  <other_2's round-1 text>

  Critique their reasoning. Restate or revise your own position
  in ≤300 words. Lead with: "I agree with <X> on <Y>, but disagree on <Z>" 
  if applicable; otherwise lead with a one-sentence revised claim.
  ```
- Outputs into `synthesis/intermediate/debate-round-2.md`.

Final synthesis — **moderator pass** (host inline):

- The host (whichever CLI is reading this) reads both rounds and writes `final.md`:
  - One-paragraph "consensus or split?" summary.
  - Bullet list of points that all agents agreed on (after round 2).
  - Bullet list of points that remained contested + which agent took which side.
  - One-sentence "moderator's read" of the strongest argument *(label it as the host's opinion, not as ground truth)*.
- Contributors block lists each agent's round-1 and round-2 contribution paths.

Escalation: if any agent fails round 1 → proceed with the remaining agents but record the dropout in `final.md`. If any agent fails round 2 → use its round-1 position as its final stance.

## meta-synth (default for task_class = `idea`)

The host reads all worker outputs and writes one unified answer with attribution.

Algorithm:

1. Verify all agents in `route.json: agents` have `meta.json: status == "ok"`. If any failed, list them in `final.md` "Contributors" as failed and proceed with the rest.
2. Concatenate `agents/<name>/result.md` for each successful agent into `synthesis/intermediate/meta-synth-input.md`, prefixed by `--- <name> ---` separators.
3. The host writes `final.md` directly, following the structure in `state-contract.md §"synthesis/final.md"`:
   - **# Answer** — the unified answer, written by the host. Inline-cite contributing agents where their wording or idea is the source.
   - **## Contributors** — one bullet per agent, naming what they brought.
   - **## Synthesis method: meta-synth** — one paragraph: what overlapped, what conflicted, how the host resolved conflicts.
   - **## Audit** — total cost / time, link to `audit.jsonl`.

The host does not paraphrase agent outputs unless one is clearly wrong; instead it weaves their contributions into one coherent answer. If two agents say similar things, the synthesis credits both and picks the clearer phrasing.

**Attribution is mandatory.** If a sentence in `final.md` is materially based on one specific agent's output, that sentence (or its paragraph) names the agent. Verbatim quotes get a code-block fence and attribution. Failing this is a violation of integrity rule "attribution mandatory".

## When synthesis cannot proceed

- All workers failed → write `final.md` with body "All agents failed. See `agents/*/meta.json` for errors. No synthesis produced." and exit with non-zero.
- One worker succeeded → degrade to `inline` and note the dropouts in Contributors.
- Vote tied with no majority and user said "no fallback" → escalate without producing `final.md`.

Never fabricate a synthesis. Never write "<agent> said X" if `<agent>/result.md` does not contain X.
