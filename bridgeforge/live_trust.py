"""Live-test trust (ROADMAP item 36, design in docs/LIVE_TEST_TRUST_DESIGN.md, 2026-10-04).

A live result is worth only as much as our certainty about what was tested. This module holds the pieces that
are not a scan check:

- `shipped_hash`: one SHA-256 over the shipped file set of a working copy (copy_drift's set), the identity of a build.
- `write_run_record`: `<queue>/_live/<TESTID>.json` joining a run's inputs (members, versions, shipped hashes, core
  baseline, probe config) and outputs (triage counts, JVM crashes, verdicts), plus one line per member in the
  workspace's `reports/live_runs.jsonl` (36.6).
- `live_status`: CURRENT / STALE / UNKNOWN_BUILD / NOT_TESTED for a workspace (36.7).
- the known-noise budget: a run's KNOWN-NOISE count against the previous run of the same members (36.9).
- `audit_shipped`: every file of the shipped copy that differs from `original/` explained by a recorded change (36.3),
  `explain_shipped` to record a person's explanation.
- `archive_gate`: the archive refuses a stale or unaudited mod unless an explanation is recorded (36.11).
Nothing here edits a mod.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path

LIVE_DIR = "_live"
RUN_LOG = "live_runs.jsonl"
SHIPPED_CHANGES = "SHIPPED_CHANGES.json"
# Files every revival writes on purpose: the report pair, the accepted-findings baseline and the version bump.
DECLARED_GENERATED = ("mod_info.json", "reports/REVIVAL_REPORT.md", "reports/REVIVAL_PLAN.md", "reports/baseline.json")
NOISE_JUMP = (1.5, 20)  # a KNOWN-NOISE count over 1.5x the last run of the same members and 20 more is REVIEW


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def shipped_files(working: Path) -> dict[str, Path]:
    from .copy_drift import _collect

    return dict(sorted(_collect(Path(working)).items()))


def shipped_hash(working: Path) -> str:
    """SHA-256 over `relative path NUL file sha256 LF` for every shipped file, in path order."""
    digest = hashlib.sha256()
    for relative, path in shipped_files(working).items():
        digest.update(f"{relative}\0{_sha256(path)}\n".encode("utf-8"))
    return digest.hexdigest()


def _mod_info(working: Path) -> dict:
    from .scanner import _load_lenient_json_file

    info = _load_lenient_json_file(Path(working) / "mod_info.json") if (Path(working) / "mod_info.json").is_file() else {}
    return info if isinstance(info, dict) else {}


# ---------------------------------------------------------------------------------------------------------------
# 36.6 run record, 36.9 noise budget
# ---------------------------------------------------------------------------------------------------------------

def _previous_noise(live_dir: Path, members: list[str], test_id: str) -> tuple[str, int] | None:
    best = None
    for record_path in sorted(live_dir.glob("*.json")):
        if record_path.stem == test_id:
            continue
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if sorted(m["workspace"] for m in record.get("members") or []) == sorted(members):
            stamp = record.get("recorded_at", "")
            if best is None or stamp >= best[0]:
                best = (stamp, record_path.stem, int((record.get("triage") or {}).get("KNOWN-NOISE", 0)))
    return (best[1], best[2]) if best else None


def write_run_record(queue: Path, test_id: str, workspaces: list[Path], *, triage: dict, verdicts: dict[str, str],
                     probe_config: dict | None = None, core_baseline: Path | None = None, save_made_with: dict | None = None,
                     today: str | None = None) -> dict:
    """Record one live run (36.6) and its noise check (36.9); returns the record."""
    from datetime import datetime, timezone

    queue = Path(queue)
    live_dir = queue / LIVE_DIR
    live_dir.mkdir(parents=True, exist_ok=True)
    members = []
    for workspace in workspaces:
        working = workspace / "working"
        info = _mod_info(working)
        members.append({"workspace": workspace.name, "mod_id": info.get("id"), "version": str(info.get("version") or ""),
                        "shipped_sha256": shipped_hash(working), "verdict": verdicts.get(str(info.get("id")), "UNKNOWN")})
    counts = dict(triage.get("counts") or {})
    noise = counts.get("KNOWN-NOISE", 0)
    previous = _previous_noise(live_dir, [m["workspace"] for m in members], test_id)
    noise_check = {"count": noise, "previous_run": previous[0] if previous else None, "previous_count": previous[1] if previous else None,
                   "status": "NO_PREVIOUS"}
    if previous:
        jump = noise > previous[1] * NOISE_JUMP[0] and noise - previous[1] >= NOISE_JUMP[1]
        noise_check["status"] = "REVIEW" if jump else "OK"
    record = {
        "schema_version": 1, "mode": "LIVE_RUN_RECORD", "test_id": test_id, "date": today or date.today().isoformat(),
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "members": members,
        "core_baseline_sha256": _sha256(core_baseline) if core_baseline and Path(core_baseline).is_file() else None,
        "probe_config_sha256": hashlib.sha256(json.dumps(probe_config, sort_keys=True).encode("utf-8")).hexdigest() if probe_config else None,
        "save_made_with": save_made_with,
        "triage": counts,
        "jvm_crashes": [{k: c.get(k) for k in ("file", "message", "top_mod")} for c in triage.get("jvm_crash_logs") or [] if c.get("during_this_log")],
        "known_noise": noise_check,
    }
    (live_dir / f"{test_id}.json").write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for workspace, member in zip(workspaces, members):
        log = workspace / "reports" / RUN_LOG
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"test_id": test_id, "date": record["date"], "verdict": member["verdict"],
                                     "shipped_sha256": member["shipped_sha256"], "version": member["version"]}) + "\n")
    return record


# ---------------------------------------------------------------------------------------------------------------
# 36.7 stale results
# ---------------------------------------------------------------------------------------------------------------

def live_status(workspace: Path) -> dict:
    """CURRENT: the newest PASS run tested exactly the files shipped now. STALE: something changed since.
    UNKNOWN_BUILD: the report says LIVE_VALIDATED but no run record holds a hash (runs before 2026-10-04).
    NOT_TESTED: neither."""
    workspace = Path(workspace)
    runs = []
    log = workspace / "reports" / RUN_LOG
    if log.is_file():
        for line in log.read_text(encoding="utf-8").splitlines():
            try:
                runs.append(json.loads(line))
            except ValueError:
                continue
    passes = [r for r in runs if r.get("verdict") == "PASS" and r.get("shipped_sha256")]
    if passes:
        last = passes[-1]
        current = shipped_hash(workspace / "working")
        return {"status": "CURRENT" if current == last["shipped_sha256"] else "STALE", "test_id": last["test_id"],
                "tested_version": last.get("version"), "date": last.get("date")}
    report = workspace / "working" / "reports" / "REVIVAL_REPORT.md"
    if report.is_file() and "LIVE_VALIDATED" in report.read_text(encoding="utf-8", errors="replace"):
        return {"status": "UNKNOWN_BUILD", "test_id": None}
    return {"status": "NOT_TESTED", "test_id": None}


# ---------------------------------------------------------------------------------------------------------------
# 36.3 shipped-copy audit
# ---------------------------------------------------------------------------------------------------------------

def original_root(workspace: Path) -> Path | None:
    """`original/` usually nests the mod one folder down (`original/<Mod Name>/`, CLAUDE.md)."""
    original = Path(workspace) / "original"
    if (original / "mod_info.json").is_file():
        return original
    nested = [p for p in original.iterdir() if p.is_dir() and (p / "mod_info.json").is_file()] if original.is_dir() else []
    if len(nested) == 1:
        return nested[0]
    # original/archive/ + original/extracted/<Mod Name>/ (yunruindustries, 2026-10-05)
    extracted_in_original = [p for p in (original / "extracted").iterdir() if p.is_dir() and (p / "mod_info.json").is_file()] \
        if (original / "extracted").is_dir() else []
    if len(extracted_in_original) == 1:
        return extracted_in_original[0]
    # original/ that keeps only the downloaded archives (Arkgneisis) is compared with their extraction in
    # scratch/original-extracted/, which leaves original/ byte-for-byte as received (2026-10-04).
    extracted = sorted(p.parent for p in (Path(workspace) / "scratch" / "original-extracted").rglob("mod_info.json"))
    return extracted[0] if len(extracted) == 1 else None


def _recorded_changes(workspace: Path) -> dict[str, str]:
    """{relative path or jar: how it was changed} from every record BridgeForge keeps."""
    workspace = Path(workspace)
    working = workspace / "working"
    found: dict[str, str] = {}
    for backup in working.rglob("*.pre-bf-fix-*.bak*"):
        relative = backup.relative_to(working).as_posix()
        target, _, rest = relative.partition(".pre-bf-fix-")
        found.setdefault(target, f"fixer {rest.split('.bak', 1)[0]}")
    for record in (workspace / "scratch").glob("jar-patch-*/PATCH-*.json"):
        try:
            data = json.loads(record.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if data.get("jar"):
            found.setdefault(str(data["jar"]).replace("\\", "/"), f"patch-jar-class {record.parent.name}")
    revive = workspace / "reports" / "revive" / "REVIVE.json"
    if revive.is_file():
        try:
            for applied in json.loads(revive.read_text(encoding="utf-8")).get("applied") or []:
                for relative in applied.get("files") or []:
                    found.setdefault(str(relative).replace("\\", "/"), f"revive {applied.get('finding')}")
        except (OSError, ValueError):
            pass
    ledger = workspace / "reports" / "escalations" / "ledger.jsonl"
    if ledger.is_file():
        for line in ledger.read_text(encoding="utf-8").splitlines():
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if entry.get("outcome") == "APPLIED" and entry.get("file"):
                found.setdefault(str(entry["file"]).split("!", 1)[0], f"escalation {entry.get('packet')}")
    manual = workspace / "reports" / SHIPPED_CHANGES
    if manual.is_file():
        try:
            for relative, entry in (json.loads(manual.read_text(encoding="utf-8")).get("files") or {}).items():
                found[relative] = f"explained: {entry.get('reason')}"
        except (OSError, ValueError):
            pass
    return found


def audit_shipped(workspace: Path) -> dict:
    """PASS when every shipped file is identical to original/ or explained; FAIL lists the rest; UNKNOWN without
    original/ (never a pass)."""
    workspace = Path(workspace)
    root = original_root(workspace)
    if root is None:
        return {"status": "UNKNOWN", "reason": "no single original/ mod root to compare with", "unexplained": []}
    shipped = shipped_files(workspace / "working")
    before = shipped_files(root)
    recorded = _recorded_changes(workspace)
    rows, unexplained = [], []
    for relative in sorted(set(shipped) | set(before)):
        if relative in shipped and relative in before:
            if _sha256(shipped[relative]) == _sha256(before[relative]):
                continue
            kind = "changed"
        else:
            kind = "added" if relative in shipped else "removed"
        why = recorded.get(relative) or ("declared generated" if relative in DECLARED_GENERATED else None)
        if why is None and relative.endswith(".jar"):
            why = recorded.get(relative)
        rows.append({"file": relative, "kind": kind, "explained_by": why})
        if why is None:
            unexplained.append(relative)
    return {"status": "FAIL" if unexplained else "PASS", "original_root": str(root), "differences": rows, "unexplained": unexplained}


def explain_shipped(workspace: Path, files: list[str], reason: str, today: str | None = None, live: bool = False) -> Path:
    """Record why shipped files differ from original/ (`audit-explain`), in reports/SHIPPED_CHANGES.json. With
    `live`, record why the mod may be archived without a CURRENT live result (a pre-2026-10-04 validation)."""
    if not reason.strip():
        raise ValueError("an explanation needs a reason.")
    if not files and not live:
        raise ValueError("name the files to explain, or pass live.")
    path = Path(workspace) / "reports" / SHIPPED_CHANGES
    data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"schema_version": 1, "files": {}}
    if live:
        data["live"] = {"reason": reason.strip(), "date": today or date.today().isoformat()}
    for relative in files:
        # strip: a list read from a CRLF file left "\r" on every key, so none matched (SEEKER, 2026-10-05)
        data["files"][relative.strip().replace("\\", "/")] ={"reason": reason.strip(), "date": today or date.today().isoformat()}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path



# ---------------------------------------------------------------------------------------------------------------
# Auto-explain: the shipped-copy differences that can be proven from the files themselves (ROADMAP item 55f)
# ---------------------------------------------------------------------------------------------------------------

_CJK = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
_JSONLIKE = (".json", ".faction", ".ship", ".variant", ".wpn", ".proj", ".skin", ".system")
_UNLOADED_ARCHIVES = (".rar", ".zip", ".7z")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def _same_parsed_json(before: Path, after: Path) -> bool:
    from .scanner import _load_lenient_json_file

    a, b = _load_lenient_json_file(before), _load_lenient_json_file(after)
    return a is not None and a == b


def _only_manufacturer_column_added(before: Path, after: Path) -> bool:
    import csv
    import io

    try:
        old = list(csv.reader(io.StringIO(_text(before))))
        new = list(csv.reader(io.StringIO(_text(after))))
    except csv.Error:
        return False
    if not old or not new or old[0] == new[0]:
        return False
    added = [h for h in new[0] if h not in old[0]]
    if added != ["tech/manufacturer"] or [h for h in old[0] if h not in new[0]]:
        return False
    keep = [new[0].index(h) for h in old[0]]

    def padded(row: list[str], width: int) -> list[str]:
        return [cell.strip() for cell in (row + [""] * width)[:width]]

    old_rows = [padded(row, len(old[0])) for row in old[1:] if row]
    new_rows = [padded(row, len(new[0])) for row in new[1:] if row]
    return old_rows == [[row[i] for i in keep] for row in new_rows]


def auto_explain_shipped(workspace: Path, today: str | None = None) -> dict[str, list[str]]:
    """Record the reason for every unexplained shipped difference whose category the files prove, and return
    {reason: files}. What stays unexplained still fails the audit. Categories:
    - credits: BRIDGEFORGE_CREDITS.txt added;
    - syntax-only JSON: the original and shipped file parse to equal values;
    - manufacturer column: tech/manufacturer added to a CSV, every other cell unchanged;
    - unloaded archive: a .rar/.zip/.7z of the original dropped from the shipped copy and kept under scratch/;
    - translation: the original holds CJK text, the shipped file less of it, and reports/translation/ exists."""
    workspace = Path(workspace)
    audit = audit_shipped(workspace)
    root = original_root(workspace)
    if root is None or not audit.get("unexplained"):
        return {}
    working = workspace / "working"
    scratch = workspace / "scratch"
    kept_names = {p.name for p in scratch.rglob("*") if p.is_file()} if scratch.is_dir() else set()
    translated = (workspace / "reports" / "translation").is_dir() and any((workspace / "reports" / "translation").glob("*.json"))
    groups: dict[str, list[str]] = {}
    for relative in audit["unexplained"]:
        before, after = root / relative, working / relative
        reason = None
        suffix = Path(relative).suffix.lower()
        if relative == "BRIDGEFORGE_CREDITS.txt" and after.is_file() and not before.is_file():
            reason = "revival credits file added by BridgeForge"
        elif before.is_file() and after.is_file():
            if suffix in _JSONLIKE and _same_parsed_json(before, after):
                reason = "JSON syntax made strict for RC8; the parsed values are identical to the original"
            elif suffix == ".csv" and _only_manufacturer_column_added(before, after):
                reason = "RC8 schema: tech/manufacturer column added; every other value is unchanged"
            elif translated and len(_CJK.findall(_text(before))) > len(_CJK.findall(_text(after))):
                reason = "Chinese -> English translation (reports/translation/); the original holds the Chinese text"
        elif before.is_file() and not after.is_file() and suffix in _UNLOADED_ARCHIVES and before.name in kept_names:
            reason = "an archive the author bundled in the mod, never loaded by the game; kept under scratch/"
        if reason:
            groups.setdefault(reason, []).append(relative)
    for reason, files in groups.items():
        explain_shipped(workspace, files, "auto-explained: " + reason, today)
    return groups


# ---------------------------------------------------------------------------------------------------------------
# 36.5 save baselines bound to their mod set
# ---------------------------------------------------------------------------------------------------------------

def save_made_with(save_dir: Path) -> dict | None:
    """The game build and enabled mods (id -> version) a save records in its descriptor.xml. RC8 writes
    `<enabledMods>` of `EnabledModData/spec` (XStream; a spec may be a `ref` to an earlier `z` id) beside
    `<allModsEverEnabled>` (read from a rig save, 2026-10-04). None when there is no descriptor or no list: an
    unknown mod set is never guessed, e.g. from folder names."""
    import xml.etree.ElementTree as ElementTree

    descriptor = Path(save_dir) / "descriptor.xml"
    if not descriptor.is_file():
        return None
    try:
        root = ElementTree.parse(descriptor).getroot()
    except (ElementTree.ParseError, OSError):
        return None
    by_z = {element.get("z"): element for element in root.iter() if element.get("z")}
    enabled = root.find("enabledMods")
    if enabled is None:
        return None
    mods = {}
    for entry in enabled.findall("EnabledModData"):
        spec = entry.find("spec")
        if spec is not None and spec.get("ref"):
            spec = by_z.get(spec.get("ref"))
        if spec is None or not (spec.findtext("id") or "").strip():
            continue
        version = spec.find("versionInfo")
        if version is not None and version.get("ref"):
            version = by_z.get(version.get("ref"))
        text = ""
        if version is not None:
            # A mod_info "version" given as {major, minor, patch} has no <string> (MagicLib 1.5.6 on a rig save).
            text = (version.findtext("string") or "").strip() or ".".join(
                part for part in ((version.findtext(k) or "").strip() for k in ("major", "minor", "patch")) if part)
        mods[spec.findtext("id").strip()] = text
    return {"game_version": (root.findtext("gameVersion") or "").strip() or None, "mods": dict(sorted(mods.items()))}


def compare_made_with(made_with: dict | None, ran_with: dict | None) -> dict:
    """COMPARABLE: same build and mods at the same versions. REVIEW: a version differs. UNKNOWN: a mod set is
    missing, or a mod is missing or extra, so behaviour cannot be compared. Never PASS by default."""
    if not made_with or not ran_with:
        return {"status": "UNKNOWN", "reason": "no mod list for the save or the run"}
    made, ran = made_with.get("mods") or {}, ran_with.get("mods") or {}
    missing, extra = sorted(set(made) - set(ran)), sorted(set(ran) - set(made))
    versions = sorted(m for m in set(made) & set(ran) if made[m] != ran[m])
    build = made_with.get("game_version") != ran_with.get("game_version")
    if missing or extra:
        return {"status": "UNKNOWN", "missing": missing, "extra": extra, "versions": versions}
    if versions or build:
        return {"status": "REVIEW", "versions": versions, "build_differs": build}
    return {"status": "COMPARABLE"}


# ---------------------------------------------------------------------------------------------------------------
# 36.11 archive gate
# ---------------------------------------------------------------------------------------------------------------

def archive_gate(workspace: Path) -> dict:
    """Allow archiving only when the shipped-copy audit passes and the live result is CURRENT (or the result's
    staleness is explained in SHIPPED_CHANGES.json under "live")."""
    audit = audit_shipped(workspace)
    live = live_status(workspace)
    problems = []
    if audit["status"] != "PASS":
        problems.append(f"shipped-copy audit {audit['status']}: " + (", ".join(audit["unexplained"][:10]) or audit.get("reason", "")))
    if live["status"] != "CURRENT":
        manual = Path(workspace) / "reports" / SHIPPED_CHANGES
        waived = manual.is_file() and json.loads(manual.read_text(encoding="utf-8")).get("live")
        if not waived:
            problems.append(f"live result {live['status']}" + (f" (last PASS {live['test_id']})" if live.get("test_id") else ""))
    return {"allowed": not problems, "problems": problems, "audit": audit, "live": live}
