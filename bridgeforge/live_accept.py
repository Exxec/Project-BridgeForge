"""`bridgeforge accept`: record a passing live run of one workspace (ROADMAP item 2 of the 2026-10-06 ideas).

`probe-group record` does this for a group run. A single mod tested by hand (`bf-test launch`) had no equivalent, so its
report status was edited by hand and no run record existed (`live_status` then says UNKNOWN_BUILD). This checks the run
and writes both:

- the log must show the main menu and a campaign load or a save, and no FATAL or MOD-ERROR;
- with `--days`, the soak verdict must not be INCOMPLETE (the probe's campaign-day heartbeat covers enough days);
- probe FAIL lines and caught exceptions are refused unless the owner gives `accept_findings`, a reason that is written
  into the report;
- the report gets a dated section naming the log's milestones, the days covered, what was not exercised, and the owner's
  note, ending in LIVE_VALIDATED; and a run record (`_live/<test id>.json`) is written so the archive gate sees a CURRENT
  live result for exactly the files shipped now.

Refuses a test id already recorded in the report. Never touches the original log or the mod's shipped files.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from .live_trust import write_run_record
from .safeio import atomic_write_text
from .log_triage import triage_log
from .soak_report import soak_report


class AcceptError(ValueError):
    """The run does not qualify, or the report already records this test id."""


def bound_evidence(rig: Path | None, test_id: str, log: Path, mods_dir: Path | None) -> tuple[dict, dict]:
    """(evidence, manifest) from the shared evaluator for a standalone acceptance, or AcceptError: no rig, no manifest, no acceptance."""
    from .run_manifest import ManifestError, evaluate_run, read_manifest

    if rig is None:
        raise AcceptError("not accepted: give --rig; an accepted run must have the pre-launch manifest `run-manifest prepare` (or the "
                          "launchers) wrote in <rig>/logs/<test id>.manifest.json. A run without one stays provenance UNKNOWN.")
    try:
        manifest = read_manifest(Path(rig), test_id)
    except ManifestError as exc:
        raise AcceptError(f"not accepted: {exc}") from exc
    return evaluate_run(Path(rig), manifest, log, mods_dir=mods_dir), manifest


def _mod_id(workspace: Path) -> str | None:
    from .scanner import _load_lenient_json_file

    info = _load_lenient_json_file(workspace / "working" / "mod_info.json")
    return info.get("id") if isinstance(info, dict) else None


def accept_run(workspace: Path | str, log: Path | str, *, test_id: str, note: str, days: float | None = None,
               not_exercised: str | None = None, mods_dir: Path | None = None, accept_findings: str | None = None,
               record_only: bool = False, today: str | None = None, write_record: bool = True,
               rig: Path | None = None, evidence: dict | None = None, manifest: dict | None = None) -> dict[str, object]:
    """Accept one workspace's run. Fails closed (ROADMAP item 75 R1): the run needs its pre-launch manifest, found in
    `<rig>/logs/<test id>.manifest.json`, and `run_manifest.evaluate_run` must show this workspace's mod bound to the run.
    A group caller passes the `evidence` and `manifest` it already evaluated for the whole group."""
    workspace = Path(workspace).expanduser().resolve()
    log = Path(log).expanduser().resolve()
    report_path = workspace / "working" / "reports" / "REVIVAL_REPORT.md"
    if not (workspace / "working" / "mod_info.json").is_file():
        raise AcceptError(f"{workspace} has no working/mod_info.json.")
    if not note.strip():
        raise AcceptError("--note is required: say what the owner did and saw.")
    today = today or date.today().isoformat()

    triage = triage_log(log, mods_dir=mods_dir)
    milestones = triage["milestones"]
    problems: list[str] = []
    if evidence is None:
        evidence, manifest = bound_evidence(rig, test_id, log, mods_dir or (Path(rig) / "mods" if rig else None))
    mine = (evidence.get("members") or {}).get(str(_mod_id(workspace)))
    if evidence.get("status") != "ACCEPTABLE":
        problems.extend(evidence.get("problems") or ["the run is not bound to its staged inputs"])
    if mine is None or not mine.get("ok"):
        problems.append(f"{workspace.name} ({_mod_id(workspace)}) is not a bound, passing target of run {test_id}"
                        + (": " + "; ".join(mine.get("problems") or []) if mine else ""))
    if not milestones["main_menu_reached"]:
        problems.append("the log never reached the main menu")
    if not (milestones["campaign_loads"] or milestones["finished_saving_count"]):
        problems.append("the log shows no campaign load and no save")
    if triage["counts"]["FATAL"]:
        problems.append(f"{triage['counts']['FATAL']} FATAL event(s)")
    if triage["counts"]["MOD-ERROR"]:
        problems.append(f"{triage['counts']['MOD-ERROR']} MOD-ERROR event(s)")
    soak = None
    if days is not None:
        soak = soak_report(log, days, mods_dir=mods_dir)
        if soak["verdict"] == "INCOMPLETE":
            problems.append(f"soak INCOMPLETE: {soak['reason']}")
    findings: list[str] = []
    probe_fail = triage["probe"]["counts_by_status"].get("FAIL", 0)
    if probe_fail:
        findings.append(f"{probe_fail} probe FAIL line(s)")
    caught = triage["caught_exceptions"]
    if caught["distinct"]:
        findings.append(f"{caught['total_events']} caught exception(s), {caught['distinct']} distinct")
    if findings and not (accept_findings or "").strip():
        problems.append("findings need a reason (--accept-findings): " + "; ".join(findings))
    if problems:
        raise AcceptError("not accepted: " + "; ".join(problems))

    heading = f"## Live run {test_id}"
    existing = report_path.read_text(encoding="utf-8").rstrip() if report_path.is_file() else f"# Revival report: {workspace.name}"
    if heading in existing:
        raise AcceptError(f"{report_path.name} already records {test_id}.")

    if not record_only:
        lines = [
            f"{heading} ({today}, RC8 rig)",
            "",
            f"Log milestones: main menu reached, {len(milestones['campaign_loads'])} campaign load(s), "
            f"{milestones['finished_saving_count']} save event(s). Triage: FATAL={triage['counts']['FATAL']}, "
            f"MOD-ERROR={triage['counts']['MOD-ERROR']}, probe FAIL={probe_fail}, caught exceptions={caught['distinct']} distinct.",
        ]
        if soak is not None:
            lines.append(f"Soak: {soak['campaign_days_covered']:g} campaign days covered of the {days:g} asked for ({soak['verdict']}).")
        if findings:
            lines.append(f"Findings accepted by the owner ({'; '.join(findings)}): {accept_findings.strip()}")
        lines.append(f"Owner's account: {note.strip()}")
        lines.append(f"Not exercised: {not_exercised.strip()}" if (not_exercised or "").strip() else "Not exercised: nothing recorded.")
        lines += ["", "LIVE_VALIDATED", ""]
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(existing + "\n\n" + "\n".join(lines), encoding="utf-8")

    mod_id = _mod_id(workspace)
    queue = workspace.parent
    # `write_record=False`: the caller (probe-group record --accept) already wrote one record for the whole group, and a second
    # write per member would replace its members list with just this one.
    record = write_run_record(queue, test_id, [workspace], triage=triage, verdicts={str(mod_id): "PASS"}, today=today,
                              evidence=evidence, manifest=manifest) if write_record else None
    if findings:
        from .group_accept import context_of

        remember_accepted(workspace, test_id, probe_fail_keys(log), caught, accept_findings or "", today, context_of(manifest))
    return {
        "schema_version": 1, "mode": "LIVE_ACCEPT", "workspace": workspace.name, "test_id": test_id,
        "report": None if record_only else str(report_path), "run_record": str(queue / "_live" / f"{test_id}.json"),
        "shipped_sha256": record["members"][0]["shipped_sha256"] if record else None, "soak": soak["verdict"] if soak else None,
        "accepted_findings": findings,
    }


ACCEPTED_LOG = "live_accepted.jsonl"
_PROBE_FAIL = re.compile(r"BF-PROBE\|[^|]*\|(?P<check>[^|]*)\|FAIL\|(?P<subject>[^|]*)\|")


def probe_fail_keys(log: Path | str) -> list[str]:
    """Sorted distinct `check|subject` of the probe FAIL lines in a log."""
    try:
        text = Path(log).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return sorted({f"{m['check']}|{m['subject']}" for m in map(_PROBE_FAIL.search, text.splitlines()) if m})


def remember_accepted(workspace: Path, test_id: str, keys: list[str], caught: dict, reason: str, today: str, context: dict | None = None) -> None:
    """Append what the owner accepted for this mod version, so `probe-group record --accept` can carry it to a later run of the same version."""
    from .scanner import _load_lenient_json_file

    info = _load_lenient_json_file(workspace / "working" / "mod_info.json")
    entry = {"test_id": test_id, "date": today, "version": str(info.get("version") or "") if isinstance(info, dict) else "",
             "keys": keys, "caught_distinct": int(caught.get("distinct") or 0), "reason": reason.strip(), "context": context}
    path = workspace / "reports" / ACCEPTED_LOG
    previous = path.read_text(encoding="utf-8") if path.is_file() else ""
    atomic_write_text(path, previous + json.dumps(entry, ensure_ascii=False) + "\n")
