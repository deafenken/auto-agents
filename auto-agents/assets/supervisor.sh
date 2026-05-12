#!/usr/bin/env bash
# supervisor.sh — keep an auto-agents run alive across crashes.
#
# Usage:
#   ./supervisor.sh runs/<task_id> [--stage N] [--max-restarts 50]
#
# The "skill helper" command is whatever you'd normally run after Stage 0
# (e.g. `python -m route && python -m dispatch && python -m synthesize`).
# This wrapper only adds: restart-on-exit, STOP/PAUSE/wait_until honoring,
# and heartbeat-watchdog kill if the inner loop stalls.
#
# Honors $AUTO_AGENTS_DEPTH (refuses if ≥1 — recursion guard).
# Honors STOP / PAUSE sentinels and wait_until.txt under runs/<task_id>/.
# Sets exit codes: 0=clean, 2=stopped-by-user, 3=recursion-refused,
# 4=max-restarts-exceeded.

set -euo pipefail

if [[ "${AUTO_AGENTS_DEPTH:-0}" -ge 1 ]]; then
  echo "[supervisor] refused: AUTO_AGENTS_DEPTH=$AUTO_AGENTS_DEPTH" >&2
  exit 3
fi

RUN_DIR="${1:-}"
if [[ -z "$RUN_DIR" || ! -d "$RUN_DIR" ]]; then
  echo "Usage: $0 <runs/<task_id>> [--max-restarts N]" >&2
  exit 64
fi
shift || true

MAX_RESTARTS=50
HEARTBEAT_STALL_SEC=900   # kill inner if heartbeat hasn't moved in 15 min
INNER_TIMEOUT_SEC=3600    # hard cap per inner pass; restart after

while (( $# > 0 )); do
  case "$1" in
    --max-restarts) MAX_RESTARTS="$2"; shift 2 ;;
    --heartbeat-stall-sec) HEARTBEAT_STALL_SEC="$2"; shift 2 ;;
    --inner-timeout-sec) INNER_TIMEOUT_SEC="$2"; shift 2 ;;
    *) echo "[supervisor] unknown arg: $1" >&2; exit 64 ;;
  esac
done

STOP="$RUN_DIR/STOP"
PAUSE="$RUN_DIR/PAUSE"
WAIT_UNTIL="$RUN_DIR/wait_until.txt"
HEARTBEAT="$RUN_DIR/.heartbeat"

# Where the skill scripts live — derive from this script's location.
SKILL_ASSETS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log() { echo "[supervisor $(date -u +%FT%TZ)] $*"; }

check_sentinels() {
  if [[ -f "$STOP" ]]; then
    log "STOP sentinel present; exiting."
    return 2
  fi
  while [[ -f "$PAUSE" ]]; do
    log "PAUSE sentinel present; sleeping 30s."
    sleep 30
    if [[ -f "$STOP" ]]; then return 2; fi
  done
  if [[ -f "$WAIT_UNTIL" ]]; then
    target=$(cat "$WAIT_UNTIL" | tr -d 'Z' | head -n1)
    # try GNU date first, then BSD
    target_epoch=$(date -u -d "$target" +%s 2>/dev/null \
                   || date -u -j -f "%Y-%m-%dT%H:%M:%S" "$target" +%s 2>/dev/null \
                   || echo "")
    if [[ -n "$target_epoch" ]]; then
      now=$(date -u +%s)
      if (( target_epoch > now )); then
        log "wait_until=$target ; sleeping $((target_epoch - now))s"
        while (( $(date -u +%s) < target_epoch )); do
          if [[ -f "$STOP" ]]; then return 2; fi
          sleep $(( $(date -u +%s) + 60 < target_epoch ? 60 : 5 ))
        done
      fi
      rm -f "$WAIT_UNTIL"
    fi
  fi
  return 0
}

heartbeat_age() {
  if [[ ! -f "$HEARTBEAT" ]]; then echo 0; return; fi
  hb=$(grep '^ts_utc:' "$HEARTBEAT" | head -n1 | sed 's/^ts_utc: *//;s/Z$//')
  if [[ -z "$hb" ]]; then echo 0; return; fi
  hb_epoch=$(date -u -d "$hb" +%s 2>/dev/null \
             || date -u -j -f "%Y-%m-%dT%H:%M:%S" "$hb" +%s 2>/dev/null \
             || echo "")
  if [[ -z "$hb_epoch" ]]; then echo 0; return; fi
  echo $(( $(date -u +%s) - hb_epoch ))
}

restart=0
while (( restart < MAX_RESTARTS )); do
  if ! check_sentinels; then
    rc=$?
    [[ "$rc" == "2" ]] && exit 2
    exit "$rc"
  fi

  log "starting inner pass (restart=$restart)"
  rc=0
  INNER_RC_FILE="$RUN_DIR/.inner.rc"
  rm -f "$INNER_RC_FILE"
  # Inline pipeline inside `bash -c` (shell functions aren't inherited unless
  # exported). Each script is idempotent — a mid-pass crash resumes cleanly.
  (
    timeout "$INNER_TIMEOUT_SEC" bash -c "
      set -e
      cd '$SKILL_ASSETS'
      python3 route.py --run-dir '$RUN_DIR' &&
      python3 dispatch.py --run-dir '$RUN_DIR' &&
      python3 synthesize.py --run-dir '$RUN_DIR' &&
      python3 handoff.py --run-dir '$RUN_DIR'
    "
    echo $? > "$INNER_RC_FILE"
  ) &
  inner_pid=$!

  # Watchdog: poll heartbeat
  while kill -0 "$inner_pid" 2>/dev/null; do
    sleep 30
    if [[ -f "$STOP" ]]; then
      log "STOP during inner; killing pid=$inner_pid"
      kill -TERM "$inner_pid" 2>/dev/null || true
      sleep 2; kill -KILL "$inner_pid" 2>/dev/null || true
      exit 2
    fi
    age=$(heartbeat_age)
    if (( age > HEARTBEAT_STALL_SEC )); then
      log "heartbeat stale (${age}s); killing pid=$inner_pid for restart"
      kill -TERM "$inner_pid" 2>/dev/null || true
      sleep 2; kill -KILL "$inner_pid" 2>/dev/null || true
      break
    fi
  done
  wait "$inner_pid" 2>/dev/null || true
  if [[ -f "$RUN_DIR/.inner.rc" ]]; then
    rc=$(cat "$RUN_DIR/.inner.rc" || echo 1)
    rm -f "$RUN_DIR/.inner.rc"
  fi

  if [[ "$rc" == "0" ]]; then
    log "inner pass succeeded; supervisor done."
    exit 0
  fi
  log "inner pass exit=$rc ; will restart after 5s"
  restart=$((restart + 1))
  sleep 5
done

log "max-restarts ($MAX_RESTARTS) exceeded; giving up."
exit 4
