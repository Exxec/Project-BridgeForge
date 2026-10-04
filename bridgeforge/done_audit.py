"""`bridgeforge done-audit`: re-scan every archived revival in Done/ (owner request 2026-10-04).

Two crashes in the owner's game that day came from Done/: RogueSynth's hull mod tooltip (NoSuchMethodError on
TooltipMakerAPI.addImageWithText(F)V, already relinked in the queue but never re-archived: Done/ held +bf.1 while the
working copy was +bf.2, as for Arkgneisis, Megastructures Tab and Slightly Better Tech Mining), and DNEEP's load
(an unguarded getStarSystem(name) that no check saw). Per archived mod this reports:

- STALE: the queue workspace's shipped files differ from the archived copy (a fix that never reached Done/).
- crash-class findings in the archived copy, scanned with the vanilla core and the queue's provider sources, that
  the mod's baseline does not accept: the ids in CRASH_CLASS plus every MANUAL / UNKNOWN finding.

Read-only. Writes Done/DONE_AUDIT.json and .md; progress per mod and a checkpoint (DONE_AUDIT.partial.jsonl).
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path

from .progress import Checkpoint, report

CRASH_CLASS = frozenset({
    "jar-linkage-unresolved", "campaign-lookup-dereferenced-unguarded", "loose-script-compile-error",
    "nexerelin-corvus-mode-import", "json-missing-comma", "content-reference-unresolved", "builtin-wing-is-hullmod",
    "hard-coded-campaign-system-reference", "hard-coded-campaign-entity-reference", "personality-id-unknown",
    "spawned-ship-captain-personality-risk", "removed-api-call", "procgen-call-argument-suspect", "settings-key-missing", "faction-known-tag-unmatched",
})
RESULT_JSON, RESULT_MD, CHECKPOINT = "DONE_AUDIT.json", "DONE_AUDIT.md", "DONE_AUDIT.partial.jsonl"


def archived_root(folder: Path) -> Path | None:
    """The mod folder inside Done/<Mod>/ (beside original/ and workspace/)."""
    candidates = [p for p in Path(folder).iterdir() if p.is_dir() and p.name not in ("original", "workspace")
                  and (p / "mod_info.json").is_file()]
    return candidates[0] if len(candidates) == 1 else None


def _casefold_hash(root: Path) -> str:
    """shipped_hash with paths compared as Windows (and RC8 on Windows) resolves them: case-insensitively. Faction
    Relationships Uniquified's queue copy keeps `Data/campaign/rules.csv`, its archive `data/...`: the same file, not
    a stale archive (2026-10-04)."""
    import hashlib

    from .live_trust import _sha256, shipped_files

    digest = hashlib.sha256()
    for relative, path in sorted(shipped_files(root).items(), key=lambda kv: kv[0].casefold()):
        digest.update(f"{relative.casefold()}\0{_sha256(path)}\n".encode("utf-8"))
    return digest.hexdigest()


def packaging_problems(folder: Path, root: Path) -> list[str]:
    """The archive's zips against its mod folder (owner question 2026-10-04): the mod's zip (named
    <folder>-<version>.zip by `archive`; backups and other zips are not judged) must exist, hold no entry twice
    (Faction Relationships Uniquified's held Data/ and data/), name the version its mod_info.json declares (Zorg18's
    first V18+bf.5 zip still said V18+bf.7 inside), and hold the same files as the folder."""
    import hashlib
    import zipfile

    from .live_trust import _mod_info, _sha256, shipped_files

    from .archive import _version_text

    problems = []
    # A {"major", "minor", "patch"} version is named as text (Anex Weapons 0.2.4), as `archive` names the zip.
    version = _version_text(_mod_info(root).get("version"))
    zips = sorted(p for p in Path(folder).glob("*.zip") if "backup" not in p.name.lower())
    if not zips:
        return ["no zip beside the mod folder"]
    expected = f"{folder.name}-{version}".replace(" ", "_")
    main = [z for z in zips if z.stem.replace(" ", "_") == expected]
    if not main:
        return [f"no zip named for mod_info version {version!r} (found: {', '.join(z.name for z in zips)})"]
    folder_files = {k.casefold(): _sha256(v) for k, v in shipped_files(root).items()}
    with zipfile.ZipFile(main[0]) as archive:
        names = [i.filename for i in archive.infolist() if not i.is_dir()]
        prefix = root.name + "/"
        inside = [n for n in names if n.startswith(prefix)]
        seen: dict[str, int] = {}
        for name in inside:
            seen[name.casefold()] = seen.get(name.casefold(), 0) + 1
        twice = sorted(n for n, c in seen.items() if c > 1)
        if twice:
            problems.append(f"{len(twice)} entr{'y' if len(twice) == 1 else 'ies'} twice (case-insensitive): {', '.join(twice[:3])}")
        info = archive.read(prefix + "mod_info.json").decode("utf-8-sig", "replace") if prefix + "mod_info.json" in names else ""
        from .scanner import _parse_json

        try:
            zipped_version = _version_text((_parse_json(info)[0] or {}).get("version")) if info else ""
        except ValueError:
            zipped_version = ""
        if version and zipped_version != version:
            problems.append(f"the zip's mod_info.json declares {zipped_version or 'no version'!r}, not {version!r}")
        zipped = {n[len(prefix):].casefold(): hashlib.sha256(archive.read(n)).hexdigest() for n in inside}
    missing = sorted(set(folder_files) - set(zipped))
    extra = sorted(set(zipped) - set(folder_files))
    differ = sorted(k for k in set(folder_files) & set(zipped) if folder_files[k] != zipped[k])
    if missing or differ:
        problems.append(f"zip differs from the folder: {len(missing)} missing, {len(differ)} changed"
                        + (f" (e.g. {(missing + differ)[0]})" if missing or differ else ""))
    if extra:
        problems.append(f"zip has {len(extra)} file(s) the folder does not ship (e.g. {extra[0]})")
    return problems


def audit_one(folder: Path, queue: Path, vanilla_core: Path | None, provider_roots: list[Path]) -> dict:
    try:
        return _audit_one(folder, queue, vanilla_core, provider_roots)
    except OSError as exc:  # a folder another process holds open (Windows 'Access is denied'): report, go on
        return {"mod": folder.name, "status": "ERROR", "stale": None, "findings": [], "error": str(exc)[:300]}


def _audit_one(folder: Path, queue: Path, vanilla_core: Path | None, provider_roots: list[Path]) -> dict:
    from .baseline import finding_dict_baseline_key, mod_baseline_keys
    from .scanner import scan_mod

    root = archived_root(folder)
    if root is None:
        return {"mod": folder.name, "status": "NO_MOD_ROOT", "stale": None, "findings": []}
    working = Path(queue) / folder.name / "working"
    stale = None
    if working.is_dir():
        stale = _casefold_hash(working) != _casefold_hash(root)
    accepted = mod_baseline_keys(root) | (mod_baseline_keys(working) if working.is_dir() else set())
    hits = []
    for finding in scan_mod(root, vanilla_core=vanilla_core, provider_roots=provider_roots or None).findings:
        data = asdict(finding)
        if finding_dict_baseline_key(data) in accepted:
            continue
        if data["id"] in CRASH_CLASS or data["classification"] in ("MANUAL", "UNKNOWN"):
            hits.append({"id": data["id"], "classification": data["classification"], "file": data.get("file"),
                         "evidence": (data.get("evidence") or [])[:3]})
    packaging = packaging_problems(folder, root)
    status = "STALE" if stale else ("PACKAGING" if packaging else ("FINDINGS" if hits else "CLEAN"))
    return {"mod": folder.name, "status": status, "stale": stale, "packaging": packaging, "findings": hits}


def done_audit(done: Path, queue: Path, vanilla_core: Path | None = None, quiet: bool = False) -> dict:
    from .revive import outside_provider_sources

    done, queue = Path(done).resolve(), Path(queue).resolve()
    providers = [p for p in (queue / "_rig" / "mods", queue, *outside_provider_sources(queue)) if p.is_dir()]
    folders = sorted(p for p in done.iterdir() if p.is_dir() and not p.name.startswith("_"))
    header = {"done": str(done), "queue": str(queue), "vanilla_core": str(vanilla_core) if vanilla_core else None}
    records = []
    with Checkpoint(done / CHECKPOINT, header) as checkpoint:
        for number, folder in enumerate(folders, 1):
            cached = checkpoint.get(folder.name)
            started = time.perf_counter()
            record = cached if cached is not None else audit_one(folder, queue, vanilla_core, providers)
            if cached is None:
                checkpoint.add(folder.name, record)
            records.append(record)
            if not quiet:
                detail = record["status"] + (f" ({len(record['findings'])} finding(s))" if record["findings"] else "")
                report(number, len(folders), folder.name, detail, None if cached is not None else time.perf_counter() - started)
        counts: dict[str, int] = {}
        for record in records:
            counts[record["status"]] = counts.get(record["status"], 0) + 1
        result = {"schema_version": 1, "mode": "DONE_AUDIT", "done": str(done), "counts": counts, "mods": records}
        (done / RESULT_JSON).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        lines = ["# Done/ audit", "", "Counts: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())), ""]
        for record in records:
            if record["status"] == "CLEAN":
                continue
            lines.append(f"## {record['mod']}: {record['status']}")
            if record["stale"]:
                lines.append("- the queue's working copy differs from the archive: re-archive it (fixes never reached Done/)")
            for problem in record.get("packaging") or []:
                lines.append(f"- packaging: {problem}")
            for hit in record["findings"]:
                lines.append(f"- `{hit['id']}` ({hit['classification']}) {hit['file'] or ''}: {'; '.join(map(str, hit['evidence']))}")
            lines.append("")
        (done / RESULT_MD).write_text("\n".join(lines), encoding="utf-8")
        checkpoint.finish()
    return result
