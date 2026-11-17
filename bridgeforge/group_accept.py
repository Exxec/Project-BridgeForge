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


def _parity_entries(log: Path, workspaces: list[Path]) -> list[dict]:
    """Entries for the content-parity FAIL keys (`content-parity|mod=<id>`) that standing per-id acceptances fully cover.

    The probe logs one `content-parity|FAIL|mod=<id>|kind=<kind> missing <have>/<expected>: <ids>` line per kind, so its key never
    equals a `probe_accepted.json` entry's `content-parity|<kind>:<id>` (live_content_parity.apply_acceptances, ROADMAP-3 93.26).
    The key counts as covered only when every id of every such line of that mod is accepted and no list was capped (fewer ids
    listed than missing): Navarchy of Tania's G4B-LIVE-0985a-20261117 stopped here with its accepted Zufalliger Krieg system."""
    from bridgeforge.live.live_content_parity import _MISSING, _PARITY_LINE
    from bridgeforge.probe.probe_group import ACCEPTED_PROBE_FILE
    from bridgeforge.scan.scanner import _load_lenient_json_file

    try:
        text = Path(log).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    rows: dict[str, list[tuple[str, int, list[str]]]] = {}
    for line in text.splitlines():
        match = _PARITY_LINE.search(line)
        if not match or match["status"] != "FAIL":
            continue
        miss = _MISSING.match(match["detail"].strip())
        if not miss:
            rows.setdefault(match["mod"], []).append(("", 1, []))  # unparsed: never covered
            continue
        ids = [ident for ident in miss["ids"].replace(" ...", "").split(",") if ident]
        rows.setdefault(match["mod"], []).append((miss["kind"], int(miss["expected"]) - int(miss["have"]), ids))
    entries: list[dict] = []
    for workspace in workspaces:
        info = _load_lenient_json_file(workspace / "working" / "mod_info.json")
        mod_id = str(info.get("id") or "") if isinstance(info, dict) else ""
        if mod_id not in rows:
            continue
        try:
            data = json.loads((workspace / "working" / ACCEPTED_PROBE_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        accepted = {}
        for item in data.get("accepted", []) if isinstance(data, dict) else []:
            if isinstance(item, dict) and item.get("check") == "content-parity" and str(item.get("reason") or "").strip():
                kind, _, ident = str(item.get("subject") or "").partition(":")
                if kind and ident:
                    accepted[(kind, ident)] = str(item["reason"]).strip()
        if all(kind and missing == len(ids) and all((kind, ident) in accepted for ident in ids) for kind, missing, ids in rows[mod_id]):
            used = sorted({accepted[(kind, ident)] for kind, _, ids in rows[mod_id] for ident in ids})
            entries.append({"keys": {f"content-parity|mod={mod_id}"}, "caught": 0, "reason": "; ".join(used),
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
    entries += _parity_entries(log, workspaces)
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
