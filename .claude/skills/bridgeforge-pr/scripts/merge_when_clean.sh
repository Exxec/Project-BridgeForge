#!/usr/bin/env bash
# Wait for a pull request's CI to settle, then merge it only when GitHub says CLEAN, by the head commit CI saw.
# Usage: merge_when_clean.sh PR [--no-merge] [--timeout SECONDS]
#   --no-merge   only wait and report (exit 0 when CLEAN)
# The head SHA is read again on every poll, so a push during the wait restarts the wait for the new head instead of
# merging (or reporting) a stale one. UNSTABLE means a red check: it is never merged (#185 was, by mistake, 2026-11-19).
# Exit: 0 merged (or CLEAN with --no-merge); 1 settled but not CLEAN; 124 timeout; 2 usage.
set -euo pipefail
PR="${1:?PR number}"; shift
[[ "$PR" =~ ^[0-9]+$ ]] || { echo "PR must be a number" >&2; exit 2; }
MERGE=1; TIMEOUT=5400
while [ $# -gt 0 ]; do
    case "$1" in
        --no-merge) MERGE=0 ;;
        --timeout) TIMEOUT="${2:?seconds}"; shift ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
    shift
done
POLL=30; waited=0; head=""
# gh prints a multi-line "hint: ... gh event listen" on stderr at every call (seen 2026-11-20, PR #194: ten copies). Keep
# stderr out of the log and show it only when a call fails.
errors="$(mktemp)"; trap 'rm -f "$errors"' EXIT
gh() { command gh "$@" 2>"$errors" || { cat "$errors" >&2; return 1; }; }
sleep 15  # checks register a few seconds after a push; an empty list must not read as "settled"
while [ "$waited" -lt "$TIMEOUT" ]; do
    now="$(gh pr view "$PR" --json headRefOid,mergeStateStatus,state -q '.headRefOid + " " + .mergeStateStatus + " " + .state')"
    read -r sha status state <<<"$now"
    if [ "$state" = "MERGED" ]; then echo "PR #$PR is already merged"; exit 0; fi
    if [ "$state" != "OPEN" ]; then echo "PR #$PR is $state" >&2; exit 1; fi
    if [ -n "$head" ] && [ "$sha" != "$head" ]; then echo "head moved $head -> $sha: waiting for the new head's CI"; fi
    head="$sha"
    checks="$(gh pr checks "$PR" 2>/dev/null || true)"
    total="$(printf '%s\n' "$checks" | grep -c . || true)"
    pending="$(printf '%s\n' "$checks" | grep -c -E $'\t(pending|queued|in_progress)\t' || true)"
    if [ "$total" -gt 0 ] && [ "$pending" -eq 0 ] && [ "$status" != "UNKNOWN" ] && [ "$status" != "BLOCKED" ]; then
        printf '%s\n' "$checks" | grep -v -E $'\t(pass|skipping)\t' || true
        echo "STATUS $status $head"
        if [ "$status" != "CLEAN" ]; then echo "not CLEAN: not merging" >&2; exit 1; fi
        [ "$MERGE" -eq 0 ] && exit 0
        gh pr merge "$PR" --merge --match-head-commit "$head"
        gh pr view "$PR" --json state -q .state
        exit 0
    fi
    sleep "$POLL"; waited=$((waited + POLL))
done
echo "TIMEOUT after ${TIMEOUT}s; last status ${status:-?} at ${head:-?}" >&2
exit 124
