"""`probe-group record --accept`: carry earlier accepted findings into a group acceptance (ROADMAP item 73 G5).

`live_accept.accept_run` refuses a log with probe FAIL lines or caught exceptions unless the owner gives a reason. In a group
run the log holds every member's lines, so the check is group-wide. A finding may be carried without asking again only when an
earlier acceptance covers it for the same mod version:

- a probe FAIL line (`check|subject`) listed in a member's `working/probe_accepted.json` (the standing, owner-written list), or in
  a `reports/live_accepted.jsonl` entry that `accept_run` wrote when it accepted that line for the member's current version;
- caught exceptions, when such an entry of the current version accepted at least as many distinct ones.

Anything not covered stops the group: nothing is recorded, and the report names what is uncovered.
"""
from __future__ import annotations

import json
from pathlib import Path

from bridgeforge.live.live_accept import ACCEPTED_LOG, probe_fail_keys


def _current_version(workspace: Path) -> str:
    from bridgeforge.scan.scanner import _load_lenient_json_file

    info = _load_lenient_json_file(workspace / "working" / "mod_info.json")
    return str(info.get("version") or "") if isinstance(info, dict) else ""


def context_of(manifest: dict | None) -> dict | None:
    """The part of a run's manifest an acceptance waiver depends on: the providers it ran with, the probe config and the launcher files.
    A waiver given in one environment does not carry to another (ROADMAP item 75 R1)."""
    if not manifest:
        return None
    from .run_manifest import summary_for_record

    summary = summary_for_record(manifest)
    return {"dependencies": {k: v["staged_sha256"] for k, v in summary["dependencies"].items()},
            "probe_config_sha256": summary["probe_config_sha256"], "launcher_files": summary["launcher_files"]}


def _earlier_entries(workspace: Path, context: dict | None = None) -> list[dict]:
    """Acceptances that still apply to the workspace: same mod version, plus the standing probe_accepted.json lines."""
    from bridgeforge.probe.probe_group import ACCEPTED_PROBE_FILE

    entries: list[dict] = []
    version = _current_version(workspace)
    log = workspace / "reports" / ACCEPTED_LOG
    if log.is_file():
        for line in log.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
            except ValueError:
                continue
            # An entry without a recorded context (written before R1) never matches: a version alone is not the same circumstances.
            if (isinstance(item, dict) and str(item.get("version")) == version and str(item.get("reason") or "").strip()
                    and context is not None and item.get("context") == context):
                entries.append({"keys": set(item.get("keys") or []), "caught": int(item.get("caught_distinct") or 0),
                                "reason": str(item["reason"]).strip(), "source": f"{workspace.name} {item.get('test_id')}"})
    standing = workspace / "working" / ACCEPTED_PROBE_FILE
    if standing.is_file():
        try:
            data = json.loads(standing.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        for item in data.get("accepted", []) if isinstance(data, dict) else []:
            if isinstance(item, dict) and item.get("check") and item.get("subject") and str(item.get("reason") or "").strip():
                entries.append({"keys": {f"{item['check']}|{item['subject']}"}, "caught": 0, "reason": str(item["reason"]).strip(),
                                "source": f"{workspace.name} probe_accepted.json"})
    return entries


def assess_group(log: Path, workspaces: list[Path], mods_dir: Path | None = None, context: dict | None = None) -> dict:
    """What `accept_run` will ask a reason for in this log, and whether earlier acceptances of the members cover it.

    Returns {"keys", "caught", "uncovered_keys", "uncovered_caught", "reason", "covered_by"}; `reason` is the text to pass as
    accept_findings (None when the log has no findings), and the group may be accepted only when nothing is uncovered."""
    from .log_triage import triage_log

    keys = probe_fail_keys(log)
    caught = int(triage_log(log, mods_dir=mods_dir)["caught_exceptions"].get("distinct") or 0)
    entries = [entry for workspace in workspaces for entry in _earlier_entries(workspace, context)]
    covered = {key for entry in entries for key in entry["keys"]}
    uncovered_keys = [key for key in keys if key not in covered]
    caught_cover = max((entry["caught"] for entry in entries), default=0)
    uncovered_caught = caught > caught_cover
    used = [entry for entry in entries if (entry["keys"] & set(keys)) or (caught and entry["caught"] and not uncovered_caught)]
    reason = None
    if keys or caught:
        reason = "carried from earlier acceptance of the same mod version: " + "; ".join(
            sorted({f"{entry['reason']} ({entry['source']})" for entry in used})) if used else None
    return {"keys": keys, "caught": caught, "uncovered_keys": uncovered_keys, "uncovered_caught": uncovered_caught,
            "reason": reason, "covered_by": sorted({entry["source"] for entry in used})}
