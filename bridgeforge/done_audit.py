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
    "spawned-ship-captain-personality-risk", "removed-api-call", "procgen-call-argument-suspect",
})
RESULT_JSON, RESULT_MD, CHECKPOINT = "DONE_AUDIT.json", "DONE_AUDIT.md", "DONE_AUDIT.partial.jsonl"


def archived_root(folder: Path) -> Path | None:
    """The mod folder inside Done/<Mod>/ (beside original/ and workspace/)."""
    candidates = [p for p in Path(folder).iterdir() if p.is_dir() and p.name not in ("original", "workspace")
                  and (p / "mod_info.json").is_file()]
    return candidates[0] if len(candidates) == 1 else None


def audit_one(folder: Path, queue: Path, vanilla_core: Path | None, provider_roots: list[Path]) -> dict:
    from .baseline import finding_dict_baseline_key, mod_baseline_keys
    from .live_trust import shipped_hash
    from .scanner import scan_mod

    root = archived_root(folder)
    if root is None:
        return {"mod": folder.name, "status": "NO_MOD_ROOT", "stale": None, "findings": []}
    working = Path(queue) / folder.name / "working"
    stale = None
    if working.is_dir():
        stale = shipped_hash(working) != shipped_hash(root)
    accepted = mod_baseline_keys(root) | (mod_baseline_keys(working) if working.is_dir() else set())
    hits = []
    for finding in scan_mod(root, vanilla_core=vanilla_core, provider_roots=provider_roots or None).findings:
        data = asdict(finding)
        if finding_dict_baseline_key(data) in accepted:
            continue
        if data["id"] in CRASH_CLASS or data["classification"] in ("MANUAL", "UNKNOWN"):
            hits.append({"id": data["id"], "classification": data["classification"], "file": data.get("file"),
                         "evidence": (data.get("evidence") or [])[:3]})
    status = "STALE" if stale else ("FINDINGS" if hits else "CLEAN")
    return {"mod": folder.name, "status": status, "stale": stale, "findings": hits}


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
            for hit in record["findings"]:
                lines.append(f"- `{hit['id']}` ({hit['classification']}) {hit['file'] or ''}: {'; '.join(map(str, hit['evidence']))}")
            lines.append("")
        (done / RESULT_MD).write_text("\n".join(lines), encoding="utf-8")
        checkpoint.finish()
    return result
