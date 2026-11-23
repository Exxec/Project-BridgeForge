"""After a probe-group run: per-member verdicts, recording and the startup smoke (split from probe_group.py, 96.5 A6).

- `group_report`: attributes each probe FAIL line to the member whose content id it names, and each crash to the member
  whose jar threw (log-triage attribution), giving one verdict per member; `accepted_probe_findings` hides the lines the
  owner accepted.
- `record_group`: records LIVE_VALIDATED for the members that passed, and archives them with `--archive`.
- `smoke_group`: a startup-only boot of an installed group.
probe_group.py plans and installs the groups.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from bridgeforge.live.live_content_parity import apply_acceptances as apply_parity_acceptances
from bridgeforge.live.live_content_parity import parity_failure_lines, parity_findings
from bridgeforge.probe.probe_config import _refuse_non_rig
from bridgeforge.scan.scanner import _load_lenient_json_file

from .probe_group import SCHEMA_VERSION, ProbeGroupError, _mod_info

# The owner's standing reason for local-only revivals (owner decision 2026-09-27); defined in release.py since 96.6, where `archive`
# applies it too.
from bridgeforge.release import OWNER_STANDING_REASON  # noqa: F401

_PROBE_LINE = re.compile(r"BF-PROBE\|(?P<version>[^|]*)\|(?P<check>[^|]*)\|(?P<status>[^|]*)\|(?P<subject>[^|]*)\|(?P<detail>.*)$")
ACCEPTED_PROBE_FILE = Path("reports") / "probe_accepted.json"


def accepted_probe_findings(queue: Path, mods_dir: Path | None = None) -> dict[str, list[dict]]:
    """{mod id: [{"check", "subject", "reason"}]} from each tested workspace's working/reports/probe_accepted.json: probe FAIL
    lines the owner accepted, each with its reason (Magellan's hidden magellan_startigers faction builds no patrol and nothing in
    the mod spawns its fleets, GRP5C-20261006). An entry hides exactly one `check|subject` line; the verdict still lists it.
    A content-parity entry names one missing id as `"subject": "<kind>:<id>"` (live_content_parity.apply_acceptances)."""
    found: dict[str, list[dict]] = {}
    for mod_id, workspace in _workspaces_by_mod_id(queue, mods_dir).items():
        path = workspace / "working" / ACCEPTED_PROBE_FILE if workspace is not None else None
        if path is None or not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        entries = [item for item in data.get("accepted", []) if isinstance(item, dict) and item.get("check") and item.get("subject") and item.get("reason")]
        if entries:
            found[mod_id] = entries
    return found


# Library packages a mod's optional integration classes extend: a NoClassDefFoundError naming one of these, while that library is not
# enabled in the rig, means the integration is simply inactive. Only well-known libraries are listed; anything else stays a FAIL.
OPTIONAL_LIBRARY_PACKAGES = {"org/lazywizard/console/": "lw_console", "lunalib/": "lunalib", "org/magiclib/": "MagicLib",
                             "org/lazywizard/lazylib/": "lw_lazylib", "org/lazywizard/radar/": "lw_radar",
                             "exerelin/": "nexerelin", "second_in_command/": "second_in_command",
                             "data/scripts/campaign/bases/VayraRaiderBaseBarEvent": "vayrasector"}  # last three: REG-20261012 SEEKER, Nightcross, Kadur Remnant


_NO_CLASS_DEF = re.compile(r"NoClassDefFoundError: (\S+)")


# Probe-loader artefacts: the class sweep loads jar classes through the script loader, whose sandbox refuses reflection and file access
# (fast_engine_rendering's org.joml classes, REG-20261012 group 4), and module-info.class is not a class at all.
_SWEEP_ARTEFACT = re.compile(r"not allowed to scripts|module-info is not a class")


# A ship AI's own debug prints, logged at ERROR level by the mod; every one of 7 group-13 members read UNCLEAR because of them.
_DEBUG_CHATTER = re.compile(r"^Cloak AI: (?:Running|No valid Target\.)\s*$")


def _enabled_mod_ids(mods_dir: Path | None) -> set[str] | None:
    """Mod ids in the rig's enabled_mods.json, or None when it cannot be read (then nothing is treated as optional)."""
    try:
        data = json.loads((Path(mods_dir) / "enabled_mods.json").read_text(encoding="utf-8")) if mods_dir is not None else None
    except (OSError, ValueError):
        return None
    ids = data.get("enabledMods") if isinstance(data, dict) else None
    return {i for i in ids if isinstance(i, str)} if isinstance(ids, list) else None


def _missing_optional_library(detail: str, enabled: set[str]) -> str | None:
    found = _NO_CLASS_DEF.search(detail)
    if not found:
        return None
    for prefix, library in OPTIONAL_LIBRARY_PACKAGES.items():
        if found.group(1).startswith(prefix) and library not in enabled:
            return library
    return None


_ROUND_OR_COMBAT_START = re.compile(r"BF-PROBE\|[^|]*\|(?:combat-round\|INFO\|round (?P<round>\d+) of (?P<total>\d+)\|hulls (?P<hulls>\d+-\d+)"
                                    r"|probe\|INFO\|combat\|START)")


def combat_rounds(log_text: str) -> dict:
    """Which slices of the probe's combat plan started a battle: the round the game defined last before each `combat START`.
    Probe 0.3.2 and earlier advanced the round on every definition of the mission, and the game defines it again after each
    battle, so with two rounds the second battle fought round 1 again and round 2 never fought (G1-LIVE3, G2,
    G2B-LIVE-0985a-20261117); a restart click that starts nothing leaves its round out too (UAF, SR3-LIVE-0985a-20261117)."""
    planned, started, last, hulls = 0, [], None, {}
    for match in _ROUND_OR_COMBAT_START.finditer(log_text):
        if match["round"]:
            last, planned = int(match["round"]), max(planned, int(match["total"]))
            hulls[last] = match["hulls"]
        elif last is not None:
            started.append(last)
    missing = [number for number in range(1, planned + 1) if number not in started]
    # Probe 0.3.4 (96.13): why each battle ended and who was left; "side-wiped" and "engine-ended" are battles won early.
    ended = [{"reason": m["reason"], "detail": m["detail"]} for m in _COMBAT_END.finditer(log_text)]
    # A round the game never defined (a run stopped in an earlier round) has no hull range in the log.
    return {"planned": planned, "started": started, "missing": missing, "missing_hulls": [hulls.get(number, "?") for number in missing],
            "ended": ended}


_COMBAT_END = re.compile(r"BF-PROBE\|[^|]*\|combat-end\|[A-Z]+\|(?P<reason>[a-z-]+)\|(?P<detail>[^\r\n]*)")


# Greedy to the line's last `]`: a folder name may hold one (review of 93.65, 2026-11-20).
_MOD_LOAD_ERROR = re.compile(r"ModManager\s+-\s+Error loading mod from \[(?P<path>.+)\]\s*$")


def mod_load_failures(log_text: str, mods_dir: Path | None) -> list[dict]:
    """[{folder, mod_id (None when unknown), reason}] for each mod the game could not load. RC7 logs
    `ModManager - Error loading mod from [..\\mods\\<folder>]` and the reason on the next line, then plays on without it:
    P1B-CAR-20261120's gene carrier lacked `description` and the run, vanilla plus the probe, read PASS (2026-11-20). A mod
    that is not enabled is left out: RC7 reads every folder's mod_info, and LOBSTER-SUB-20261120 logged the disabled old
    carrier's failure too."""
    from bridgeforge.mod_files import read_mod_info

    lines, found = log_text.splitlines(), []
    enabled = _enabled_mod_ids(mods_dir)
    for i, line in enumerate(lines):
        match = _MOD_LOAD_ERROR.search(line)
        if not match:
            continue
        folder = re.split(r"[\\/]", match["path"].rstrip("\\/"))[-1]
        reason = lines[i + 1].split(" - ", 1)[-1].strip() if i + 1 < len(lines) else ""
        info = read_mod_info(Path(mods_dir) / folder) if mods_dir is not None and (Path(mods_dir) / folder).is_dir() else None
        mod_id = info.get("id") if isinstance(info, dict) and isinstance(info.get("id"), str) else None
        if mod_id is not None and enabled is not None and mod_id not in enabled:
            continue  # the game reads every folder's mod_info; a broken one it was not asked to enable changes nothing
        entry = {"folder": folder, "mod_id": mod_id, "reason": reason[:200]}
        if entry not in found:  # the launcher and the game may log the same failure twice
            found.append(entry)
    return found


def group_report(log: Path, config: dict, mods_dir: Path | None = None, accepted: dict[str, list[dict]] | None = None) -> dict:
    """One verdict per member: probe FAIL lines matched by the content id or faction they name, and crashes
    by the mod whose jar threw (log-triage attribution). Unmatched FAILs are reported for the group. `accepted` moves the
    named FAIL lines of a member to its `accepted` list (see accepted_probe_findings); they no longer fail it."""
    from bridgeforge.log_triage import triage_log

    members = config.get("group_members") or {}
    owner: dict[str, str] = {}
    for mod_id, ids in members.items():
        for kind in ("hulls", "variants", "wings", "items", "factions", "commodities", "missions", "classes"):
            for item in ids.get(kind, []):
                owner.setdefault(item, mod_id)
    verdicts = {mod_id: {"failures": [], "crashes": []} for mod_id in members}
    unattributed, seen_content, filler_sides, optional_integrations, sweep_artefacts = [], False, [], [], []
    enabled = _enabled_mod_ids(mods_dir)
    log_text = Path(log).read_text(encoding="utf-8", errors="replace")
    for line in log_text.splitlines():
        match = _PROBE_LINE.search(line)
        if not match:
            continue
        if match["status"] == "FAIL" and match["check"] == "class-sweep":
            if _SWEEP_ARTEFACT.search(match["detail"]):
                sweep_artefacts.append(match["subject"])
                continue
            library = _missing_optional_library(match["detail"], enabled) if enabled is not None else None
            if library:
                # A class of a mod's optional integration (Console Commands commands, LunaLib refit buttons) that extends a library nobody
                # enabled: the game never loads it, so this is not a defect (REG-20261012-G2, Bionic Alteration).
                optional_integrations.append({"class": match["subject"], "library": library})
                continue
        if match["check"] == "content-ids" and match["subject"] == "all-content":
            seen_content = True
        if match["check"] == "combat-filler" and match["status"] == "INFO":
            if match["subject"] not in filler_sides:
                filler_sides.append(match["subject"])  # ROADMAP P15 31.13: vanilla ships stood in for a side
        if match["check"] in ("content-parity", "campaign-perf"):
            continue  # judged by live_content_parity / campaign_perf below, per mod
        if match["status"] != "FAIL":
            continue
        subject = match["subject"].split(":", 1)[-1].split("/", 1)[0].split("@", 1)[0]  # market-supply names "commodity@industry"
        mod_id = owner.get(subject)
        if (match["check"], match["subject"]) in (("market-supply", "commodities"), ("mission-fleets", "all-missions"), ("class-sweep", "all-classes")):
            continue  # a summary line repeating the per-item FAIL lines above it
        if mod_id is None and match["check"] in ("campaign-layout", "combat-perf", "market-supply") and len(members) == 1:
            mod_id = next(iter(members))  # a sector-layout line names a system, not a content id: with one member it is that member's
        if mod_id is None and match["check"] == "bounty" and subject in members:
            # A MagicLib bounty line names "<mod id>/<bounty id>", not a content id; YunruCore's eight went to the group and its
            # own acceptances could not apply (P962YC-LIVE-0985a-20261119).
            mod_id = subject
        entry = f"{match['check']}|{match['subject']}|{match['detail'].strip()[:200]}"
        if mod_id and any(a["check"] == match["check"] and a["subject"] == match["subject"] for a in (accepted or {}).get(mod_id, [])):
            verdicts[mod_id].setdefault("accepted", []).append(entry)
            continue
        (verdicts[mod_id]["failures"] if mod_id else unattributed).append(entry)
    # A member the game could not load fails, whatever else passed; another mod that did not load is the group's problem.
    for failure in mod_load_failures(log_text, mods_dir):
        entry = f"mod-load|{failure['folder']}|{failure['reason']}"
        (verdicts[failure["mod_id"]]["failures"] if failure["mod_id"] in verdicts else unattributed).append(entry)
    # 77.17: a shortfall between what the working copy defines and what the game loaded fails that member (excess is information).
    parity = parity_findings(log, config)
    for mod_id, lines in apply_parity_acceptances(parity, accepted).items():  # owner-accepted "<kind>:<id>" entries (2026-11-17)
        if mod_id in verdicts:
            verdicts[mod_id].setdefault("accepted", []).extend(lines)
    for mod_id, lines in parity_failure_lines(parity).items():
        if mod_id in verdicts:
            verdicts[mod_id]["failures"].extend(lines)
    from bridgeforge.campaign_perf import campaign_perf_summary

    perf = campaign_perf_summary(log, slow_p95_ms=config.get("campaign_perf_p95_ms") or None)
    triage = triage_log(log, mods_dir=mods_dir) if mods_dir is not None else triage_log(log)
    for event in triage["fatal"] + triage["mod_errors"]:
        # A JVM crash names the mod owning its nearest Java frame (ROADMAP 36.4); a log exception its suspect.
        suspect = event.get("suspect") or event.get("top_mod")
        if _DEBUG_CHATTER.match(str(event.get("message"))):
            continue
        text = f"{event.get('matched_rule') or event.get('level')}: {str(event.get('message'))[:160]}"
        (verdicts[suspect]["crashes"] if suspect in verdicts else unattributed).append(text)
    # combat-perf FAIL (probe 0.2.24): a runaway field in a group of several members belongs to the group, so it is UNCLEAR.
    group_crash = any(not item.startswith(("content-ids", "faction", "planet", "rings", "submarket", "fleet", "setup", "combat", "market-supply"))
                      or item.startswith("combat-perf") for item in unattributed) or (triage["counts"]["FATAL"] and not any(v["crashes"] for v in verdicts.values()))
    for mod_id, verdict in verdicts.items():
        if verdict["failures"] or verdict["crashes"]:
            verdict["verdict"] = "FAIL"
        elif group_crash:
            verdict["verdict"] = "UNCLEAR"  # a crash no member's jar owns: rerun the member alone to clear it
        else:
            verdict["verdict"] = "PASS" if seen_content else "INCOMPLETE"
    return {"schema_version": SCHEMA_VERSION, "mode": "PROBE_GROUP_REPORT", "log": str(log),
            "content_ids_ran": seen_content, "fatal": triage["counts"]["FATAL"], "mod_errors": triage["counts"]["MOD-ERROR"],
            "members": verdicts, "content_parity": parity, "campaign_perf": perf, "unattributed": unattributed, "combat_filler_sides": filler_sides,
            "combat_rounds": combat_rounds(log_text),
            "optional_integration_classes": optional_integrations, "sweep_artefact_classes": sweep_artefacts,
            "note": "INCOMPLETE means the probe's content-ids check never ran (start a New Game and wait one in-game day)."}


def _workspaces_by_mod_id(queue: Path, mods_dir: Path | None = None) -> dict[str, Path | None]:
    """{mod id: the workspace that was tested}. `install` copies a member to <rig>/mods/<workspace name>, so a rig
    folder with that id and a same-named workspace decides. Otherwise one workspace per id; two or more is None
    (ambiguous). SEEKER-SOLO2-20260928 recorded and archived the old `SEEKER` workspace, not the tested SEEKER-0.6,
    because the first workspace by name won."""
    candidates: dict[str, list[Path]] = {}
    for workspace in sorted(p for p in Path(queue).iterdir() if p.is_dir() and not p.name.startswith("_")):
        mod_id = _mod_info(workspace / "working").get("id")
        if isinstance(mod_id, str) and mod_id:
            candidates.setdefault(mod_id, []).append(workspace)
    in_rig: dict[str, set[str]] = {}
    if mods_dir is not None and Path(mods_dir).is_dir():
        for folder in Path(mods_dir).iterdir():
            mod_id = _mod_info(folder).get("id") if folder.is_dir() else None
            if isinstance(mod_id, str):
                in_rig.setdefault(mod_id, set()).add(folder.name)
    found: dict[str, Path | None] = {}
    for mod_id, workspaces in candidates.items():
        tested = [w for w in workspaces if w.name in in_rig.get(mod_id, set())]
        found[mod_id] = tested[0] if len(tested) == 1 else workspaces[0] if len(workspaces) == 1 else None
    return found


# "CampaignGameManager  - Saving to ..\saves/save_LewisVerdun_4976405174046756277..." (0.98.5a-RC7 log, G3-LIVE-0985a-20261117).
_SAVING_TO = re.compile(r"CampaignGameManager\s+-\s+Saving to (?P<path>.+?)\.\.\.\s*$", re.MULTILINE)


def run_save_made_with(rig: Path, log_text: str, reader) -> dict | None:
    """What the run's own save records: the last folder its log says the game saved to, read with `reader`. None when the run
    saved nothing. The rig's newest save was read before, so a group recorded after a later run described that run's save:
    G3-LIVE-0985a-20261117 (KoC) listed Tania's mods (ROADMAP-3 item 93.38, 2026-11-17). Only the path's last part is looked
    up, and only as a `save_*` folder of the rig's own saves/, so a path in the log never leads outside the rig."""
    names = [re.split(r"[\\/]", match.group("path").strip())[-1] for match in _SAVING_TO.finditer(log_text)]
    names = [name for name in names if re.fullmatch(r"save_[^\\/]+", name)]
    folder = Path(rig) / "saves" / names[-1] if names else None
    return reader(folder) if folder is not None and folder.is_dir() else None


def evaluate_member_scenarios(log: Path, workspaces: dict[str, Path]) -> dict[str, dict]:
    """{mod id: scenario block} for every tested workspace whose working copy has a PROBE_SCENARIO.json, judged against the game log.
    An invalid scenario file is recorded as an ERROR block (verdict INCOMPLETE) rather than hiding the run."""
    from bridgeforge.probe.probe_scenario import ScenarioError, evaluate_expectations, load_for_working

    text = Path(log).read_text(encoding="utf-8", errors="replace")
    blocks: dict[str, dict] = {}
    for mod_id, workspace in workspaces.items():
        try:
            scenario = load_for_working(workspace / "working")
        except ScenarioError as exc:
            blocks[mod_id] = {"verdict": "INCOMPLETE", "required": ["scenario-file"], "failed": [], "not_observed": ["scenario-file"],
                              "expectations": {}, "error": str(exc)}
            continue
        if scenario is not None:
            blocks[mod_id] = {**evaluate_expectations(text, scenario), "settings_staged": sorted(scenario["settings"])}
    return blocks


def record_group(log: Path, config: dict, queue: Path, rig: Path, *, test_id: str, archive: bool = False,
                 done_dir: Path | None = None, policy_path: Path | None = None, today: str | None = None,
                 refresh: bool = False, accept: bool = False, note: str | None = None,
                 observe_exit: bool = False) -> dict:
    """After a group run: mark every PASS member LIVE_VALIDATED in its report; with `archive`, record the owner's
    standing local-only licence where none exists, archive it into Done/ and copy its zip to Done/'s top level
    (ROADMAP P15 item 31.1; replaces the session's record_group.py and shell loop)."""
    import re
    import shutil
    from datetime import date

    from bridgeforge.archive import ArchiveError, archive_mod
    from bridgeforge.release import apply_standing_licence

    today = today or date.today().isoformat()
    report = group_report(log, config, mods_dir=Path(rig) / "mods", accepted=accepted_probe_findings(queue, Path(rig) / "mods"))
    text = Path(log).read_text(encoding="utf-8", errors="replace")
    version = (re.search(r"BF-PROBE\|(\d+\.\d+\.\d+)\|", text) or [None, "?"])[1]
    workspaces = _workspaces_by_mod_id(queue, Path(rig) / "mods")
    # ROADMAP 36.6: one run record joining inputs and outputs, written before any archive so the gate (36.11)
    # sees this run's shipped hashes.
    from bridgeforge.live.live_trust import archive_gate, auto_explain_shipped, save_made_with, write_run_record
    from bridgeforge.rig.rig_up import read_rig_state
    from bridgeforge.log_triage import triage_log
    from bridgeforge.rig.rig_doctor import DEFAULT_CORE_BASELINE_RELATIVE, _repo_root

    tested = [workspaces[m] for m in sorted(report["members"]) if workspaces.get(m) is not None]
    scenario_blocks = evaluate_member_scenarios(log, {m: workspaces[m] for m in sorted(report["members"]) if workspaces.get(m) is not None})
    if scenario_blocks:
        from bridgeforge.probe.probe_scenario import apply_to_verdicts

        apply_to_verdicts(report["members"], scenario_blocks)
    exit_observed, exit_code = None, None  # no flag: the record is exactly what it was
    if observe_exit:  # opt-in: the exit `probe-group live --natural-exit` observed; absent file stays UNKNOWN/None
        from bridgeforge.exit_observation import read_exit_observation

        exit_observed, exit_code = read_exit_observation(Path(rig), test_id)
    # R1: the one evidence evaluator, shared with `accept`. No manifest, no bound provenance.
    from bridgeforge.run_manifest import ManifestError, evaluate_run, read_manifest

    try:
        manifest = read_manifest(Path(rig), test_id)
    except ManifestError:
        manifest = None
    evidence = evaluate_run(Path(rig), manifest, Path(log), mods_dir=Path(rig) / "mods",
                            member_verdicts={m: v["verdict"] for m, v in report["members"].items()})
    from bridgeforge.exercised import hollow_mods, hollow_warnings, parse_exercised

    exercised = parse_exercised(text)
    hollow = hollow_mods(exercised, sorted(report["members"]))
    run_record = write_run_record(queue, test_id, tested, triage=triage_log(log, mods_dir=Path(rig) / "mods"),
                                  verdicts={m: v["verdict"] for m, v in report["members"].items()}, probe_config=config,
                                  core_baseline=_repo_root() / DEFAULT_CORE_BASELINE_RELATIVE, today=today,
                                  save_made_with=run_save_made_with(Path(rig), text, save_made_with), rig_state=read_rig_state(Path(rig)),
                                  evidence=evidence, manifest=manifest, campaign_perf=report.get("campaign_perf"),
                                  process_exit_code=exit_code, process_exit_observed=exit_observed,
                                  scenario=scenario_blocks or None, exercised=exercised or None)
    recorded, skipped, archived = [], [], []
    carry, stopped = None, None
    if accept and evidence["status"] != "ACCEPTABLE":
        return {"schema_version": SCHEMA_VERSION, "mode": "PROBE_GROUP_RECORD", "test_id": test_id, "probe_version": version,
                "recorded": [], "archived": [], "skipped": [], "run_record": str(Path(queue) / "_live" / f"{test_id}.json"),
                "stopped": {"why": "the run is not bound to its staged inputs", "evidence_status": evidence["status"], "problems": evidence["problems"]},
                "known_noise": run_record["known_noise"], "snapshot": None}
    if accept:
        # G5: record through live_accept.accept_run, carrying probe FAIL lines an earlier acceptance of the same mod version covers.
        from bridgeforge.group_accept import assess_group, context_of

        if not (note or "").strip():
            raise ProbeGroupError("--accept needs --note: say what was run and seen (it is written into each report).")
        carry = assess_group(log, tested, Path(rig) / "mods", context=context_of(manifest))
        if carry["uncovered_keys"] or carry["uncovered_caught"]:
            stopped = {"why": "findings no earlier acceptance of the same mod version covers",
                       "uncovered_probe_fail": carry["uncovered_keys"], "uncovered_caught_exceptions": carry["uncovered_caught"]}
            return {"schema_version": SCHEMA_VERSION, "mode": "PROBE_GROUP_RECORD", "test_id": test_id, "probe_version": version,
                    "recorded": [], "archived": [], "skipped": [], "stopped": stopped,
                    "run_record": str(Path(queue) / "_live" / f"{test_id}.json"), "known_noise": run_record["known_noise"], "snapshot": None}
    for mod_id, verdict in sorted(report["members"].items()):
        workspace = workspaces.get(mod_id)
        if verdict["verdict"] != "PASS" or workspace is None:
            skipped.append({"mod_id": mod_id, "verdict": verdict["verdict"], "workspace": workspace.name if workspace else None,
                            "archive": "" if workspace else "no single workspace: two or more share this mod id (rig folders too)"})
            continue
        path = workspace / "working" / "reports" / "REVIVAL_REPORT.md"
        body = path.read_text(encoding="utf-8").rstrip() if path.is_file() else f"# Revival report: {workspace.name}"
        if accept:
            from bridgeforge.live.live_accept import AcceptError, accept_run

            try:
                if f"## Live run {test_id}" not in body:
                    accept_run(workspace, log, test_id=test_id, note=note or "", mods_dir=Path(rig) / "mods",
                               accept_findings=carry["reason"] if carry else None, today=today, write_record=False,
                               rig=rig, evidence=evidence, manifest=manifest)
            except AcceptError as exc:  # any other refusal stops the group here; members already recorded stay recorded
                stopped = {"why": str(exc), "workspace": workspace.name}
                skipped.append({"mod_id": mod_id, "verdict": "PASS", "workspace": workspace.name, "archive": f"accept refused: {exc}"})
                break
        elif f"## Live probe run {test_id}" not in body:
            from bridgeforge.game_version import rig_label

            # 96.5 A1: the heading named every rig "RC8 rig", and the body credited the owner with runs the harness played.
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body + f"\n\n## Live probe run {test_id} (group run, {rig_label(rig, core=(manifest or {}).get('rig_core'))})\n\n`bridgeforge probe-group report`: **PASS** "
                            f"(probe {version}: content-ids ran, no FAIL line for this mod; group triage FATAL={report['fatal']}, "
                            f"MOD-ERROR={report['mod_errors']}). The run started a New Game, played one in-game day and the probe combat "
                            "mission.\n\nLIVE_VALIDATED\n",
                            encoding="utf-8")
        recorded.append(workspace.name)
        if not archive:
            continue
        apply_standing_licence(mod_id, _mod_info(workspace / "working").get("name"), live_date=today, policy_path=policy_path)
        done = Path(done_dir or Path(queue).parent / "Done")
        auto_explain_shipped(workspace)
        gate = archive_gate(workspace)
        if not gate["allowed"]:
            skipped.append({"mod_id": mod_id, "verdict": "PASS", "workspace": workspace.name, "archive": "; ".join(gate["problems"])})
            continue
        try:
            # `refresh` replaces an earlier archive of this mod in Done/ (`archive --refresh`): the owner's word each time, because
            # it moves that folder to Done/_replaced-<date>/, never deleting it (Omega Trauma 2026-10-06 and six stale archives 2026-10-11 were refreshed by hand).
            # An existing Done/<Mod> is moved to Done/_replaced-<date>/, never deleted (ROADMAP 60b).
            result = archive_mod(workspace, done, policy_path=policy_path, today=today, refresh=refresh, move_aside=True)
        except ArchiveError as exc:
            skipped.append({"mod_id": mod_id, "verdict": "PASS", "workspace": workspace.name, "archive": str(exc)})
            continue
        shutil.copy2(result["zip"], done / Path(result["zip"]).name)
        archived.append(workspace.name)
    snapshot_note = None
    if archived:
        from bridgeforge.state_snapshot import snapshot_after_archive
        snapshot_note = snapshot_after_archive(done)
    return {"schema_version": SCHEMA_VERSION, "mode": "PROBE_GROUP_RECORD", "test_id": test_id, "probe_version": version,
            "recorded": recorded, "archived": archived, "skipped": skipped, "stopped": stopped,
            "run_record": str(Path(queue) / "_live" / f"{test_id}.json"), "known_noise": run_record["known_noise"], "snapshot": snapshot_note,
            "exercised": exercised, "hollow": hollow, "warnings": hollow_warnings(hollow)}


SMOKE_BAT = "run-j25-direct.bat"


# Load-time failures the game logs from CombatMain before any menu (saved rig logs, 2026-10-05/06): Metelson's rules.csv
# (GRP1-20261005, BIS4G6), duplicate names/rows (GRP10B, GRP4A), a missing class from a library not enabled.
SMOKE_LOAD_ERRORS = (
    re.compile(r"JSONException: Mismatched quotes"),
    re.compile(r"Missing close quote"),
    re.compile(r"Duplicate key \["),
    re.compile(r"NoClassDefFoundError"),
    re.compile(r"ClassNotFoundException"),
)


def smoke_load_errors(log: Path, limit: int = 8) -> list[str]:
    """Log lines that name a load-time failure, first `limit`, each trimmed; [] for a missing or clean log."""
    try:
        lines = Path(log).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return [line.strip()[:240] for line in lines if any(p.search(line) for p in SMOKE_LOAD_ERRORS)][:limit]


def smoke_group(rig: Path, bat_name: str = SMOKE_BAT, timeout: int = 240, log_name: str | None = None, direct=None) -> dict:
    """Boot the rig with the group `install` just enabled, unattended, and read the startup log (ROADMAP 60a).

    Catches what fails at load time before anyone is asked to play: a `rules.csv` with mismatched quotes, a duplicate
    key, a missing library, a Fatal dialog (Metelson, Free Stars Union, Ironclads, 2026-10-05/06). It starts the game
    with `run-j25-direct.bat` ("direct" means without `starsector.exe`): the bat runs `StarfarerLauncher`, which shows the
    launcher window, so the boot clicks Play (`auto_click=True`), then stops at the main menu (ROADMAP-3 item 93.25). It
    cannot reach New Game generation (Tritachyon's missing industry crashed in onNewGame): the real run is still needed.
    Only java processes under the rig are ever stopped (`boot_test._running_java_under`).
    """
    import time

    from bridgeforge.boot_test import run_boot_test

    rig = Path(rig)
    _refuse_non_rig(rig)
    enabled_path = rig / "mods" / "enabled_mods.json"
    data = _load_lenient_json_file(enabled_path) if enabled_path.is_file() else None
    enabled = [item for item in (data.get("enabledMods") or []) if isinstance(item, str)] if isinstance(data, dict) else []
    if not enabled:
        raise ProbeGroupError(f"{enabled_path} lists no enabled mods: run `probe-group install N` first.")
    boot = run_boot_test(rig, enabled, timeout=timeout, log_name=log_name or f"SMOKE-{int(time.time())}", bat_name=bat_name, auto_click=True,
                         direct=direct)
    counts = (boot.get("triage") or {}).get("counts") or {}
    fatal, errors = int(counts.get("FATAL", 0)), int(counts.get("MOD-ERROR", 0))
    load_errors = smoke_load_errors(Path(boot["log"])) if boot.get("log") else []
    if boot["status"] == "PASS" and fatal == 0 and errors == 0 and not load_errors:
        verdict = "SMOKE_PASS"
    elif boot["status"] == "PASS":
        verdict = "SMOKE_ERRORS"
    else:
        verdict = "SMOKE_FAIL"
    return {"verdict": verdict, "enabled_mods": enabled, "fatal": fatal, "mod_errors": errors, "load_errors": load_errors, "boot": boot}
