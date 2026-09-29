"""`bridgeforge supersession`: which queued mods already have a newer release by their author (2026-09-27).

The owner's live session found eleven queued mods (Kazeron Navarchy 1.8 in the real install, astroid,
Fleet-Action-History, Flux-Reticle, HexShields, Hugin, Neutrino, prv-Path, SCVE, UAF-Skills, Variants-Lib)
whose author had since released an RC8 version: reviving the old copy was wasted work. This indexes every mod in
the reference folders (the real install's mods/, a modpack) by mod id and compares versions with each
workspace's original download. Read-only: it reports and never changes a workspace's status.

Verdicts: SUPERSEDED (a reference copy targets 0.98 with a newer version), SAME_RELEASE (the same version already
targets 0.98 there: nothing newer, but a working copy exists), NEWER_ELSEWHERE (a newer copy exists but targets an
older game), NOT_SUPERSEDED (a reference copy exists but is older), NO_MATCH. Both mod names are recorded: a
shared id with a different name (Cryosleeper 2 in AoTD - Dreams of Past) needs a look.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from .archive import _version_text
from .progress import Checkpoint, report
from .scanner import _load_lenient_json_file

SCHEMA_VERSION = 1
RESULT_FILE = "SUPERSESSION.json"
CHECKPOINT_FILE = "SUPERSESSION.partial.jsonl"
_BF_SUFFIX = re.compile(r"\+bf[.\w]*$", re.IGNORECASE)


def version_key(version: str) -> tuple[int, ...]:
    """"1.8.2a" -> (1, 8, 2); "V18+bf.4" -> (18,): numbers only, BridgeForge's +bf suffix dropped."""
    return tuple(int(n) for n in re.findall(r"\d+", _BF_SUFFIX.sub("", str(version))))


def _mod_infos(folder: Path) -> list[Path]:
    """mod_info.json files at depth 1 or 2 below a reference folder (a mod, or a mod nested in a download folder)."""
    found = []
    for child in sorted(p for p in Path(folder).iterdir() if p.is_dir()):
        if (child / "mod_info.json").is_file():
            found.append(child / "mod_info.json")
            continue
        found.extend(sorted(grand / "mod_info.json" for grand in child.iterdir() if grand.is_dir() and (grand / "mod_info.json").is_file()))
    return found


def reference_index(references: list[Path]) -> dict[str, list[dict]]:
    index: dict[str, list[dict]] = {}
    for folder in references:
        if not Path(folder).is_dir():
            continue
        for info_path in _mod_infos(Path(folder)):
            info = _load_lenient_json_file(info_path) or {}
            mod_id = info.get("id")
            if isinstance(mod_id, str) and mod_id:
                index.setdefault(mod_id.lower(), []).append({
                    "path": str(info_path.parent), "name": str(info.get("name") or ""), "version": _version_text(info.get("version")),
                    "game_version": str(info.get("gameVersion") or "")})
    return index


def corpus_reference_index(db: Path) -> dict[str, list[dict]]:
    """Every mod_info.json the corpus index lists (loose, or inside .zip/.jar/.7z under its root), by mod id
    (ROADMAP P15 31.11: compare the queue with the owner's Downloads archive, not only the installed mods)."""
    import sqlite3
    import zipfile

    from .scanner import _parse_json

    index: dict[str, list[dict]] = {}
    connection = sqlite3.connect(str(db))
    try:
        root = Path(dict(connection.execute("SELECT key, value FROM meta").fetchall()).get("root") or ".")
        rows = connection.execute("SELECT source, location FROM files WHERE location LIKE '%mod_info.json'").fetchall()
    finally:
        connection.close()  # a `with` block commits but does not close; the file stays locked on Windows
    archives: dict[str, object] = {}
    for source, location in rows:
        text = None
        try:
            if source == location:
                text = (root / source).read_text(encoding="utf-8-sig", errors="replace")
            else:
                inner = location.split("!", 1)[1]
                if source.lower().endswith((".zip", ".jar")):
                    handle = archives.get(source) or archives.setdefault(source, zipfile.ZipFile(root / source))
                    text = handle.read(inner).decode("utf-8-sig", errors="replace")
                elif source.lower().endswith(".7z"):
                    try:
                        import py7zr
                    except ImportError:
                        continue  # the optional [archives] extra is not installed
                    try:
                        with py7zr.SevenZipFile(root / source) as seven:
                            reader = getattr(seven, "read", None)
                            if reader is None:
                                continue  # this py7zr version cannot read single members; skip the archive
                            text = next(iter(reader([inner]).values())).read().decode("utf-8-sig", errors="replace")
                    except Exception:  # noqa: BLE001 - an unreadable .7z is skipped, never fatal
                        continue
        except (OSError, KeyError, ValueError, zipfile.BadZipFile, StopIteration):
            continue
        try:
            info = _parse_json(text)[0] if text else None
        except ValueError:
            continue  # a mod_info.json even the lenient reader cannot parse
        mod_id = info.get("id") if isinstance(info, dict) else None
        if isinstance(mod_id, str) and mod_id:
            index.setdefault(mod_id.lower(), []).append({"path": f"{root / source}" + (f"!{location.split('!', 1)[1]}" if source != location else ""),
                                                         "name": str(info.get("name") or ""), "version": _version_text(info.get("version")),
                                                         "game_version": str(info.get("gameVersion") or "")})
    for handle in archives.values():
        handle.close()
    return index


def _original_info(workspace: Path) -> dict:
    original = workspace / "original"
    if original.is_dir():
        infos = sorted(original.rglob("mod_info.json"), key=lambda p: len(p.parts))
        if infos:
            return _load_lenient_json_file(infos[0]) or {}
    return _load_lenient_json_file(workspace / "working" / "mod_info.json") or {}


def judge(workspace: Path, index: dict[str, list[dict]]) -> dict:
    working = _load_lenient_json_file(workspace / "working" / "mod_info.json") or {}
    original = _original_info(workspace)
    mod_id = str(working.get("id") or original.get("id") or "")
    ours = _version_text(original.get("version") or working.get("version"))
    record = {"workspace": workspace.name, "mod_id": mod_id, "name": str(original.get("name") or working.get("name") or ""),
              "version": ours, "verdict": "NO_MATCH", "reference": None}
    candidates = index.get(mod_id.lower(), [])
    # Ignore a reference that is this workspace's own deployed copy (a rig mods/ folder holding the revival).
    # Our own builds are never a newer release: +bf versions, and earlier BridgeForge revival builds kept in the
    # Downloads archive ("0.2.2-0.98a-revival-r13", Void-Tec, 2026-09-28).
    candidates = [c for c in candidates if _BF_SUFFIX.search(c["version"]) is None and "revival" not in c["version"].lower()]
    if not candidates:
        return record
    best = max(candidates, key=lambda c: (c["game_version"].startswith("0.98"), version_key(c["version"])))
    record["reference"] = best
    theirs, mine, on_098 = version_key(best["version"]), version_key(ours), best["game_version"].startswith("0.98")
    if theirs > mine and on_098:
        record["verdict"] = "SUPERSEDED"
    elif theirs == mine and on_098:
        record["verdict"] = "SAME_RELEASE"
    elif theirs > mine:
        record["verdict"] = "NEWER_ELSEWHERE"
    else:
        record["verdict"] = "NOT_SUPERSEDED"
    return record


def find_superseded(queue: Path, references: list[Path], quiet: bool = False, corpus_index: Path | None = None) -> dict:
    queue = Path(queue).expanduser().resolve()
    references = [Path(r).expanduser().resolve() for r in references]
    workspaces = sorted(p for p in queue.iterdir() if p.is_dir() and not p.name.startswith("_") and (p / "working" / "mod_info.json").is_file())
    index = reference_index(references)
    if corpus_index is not None:
        for mod_id, entries in corpus_reference_index(Path(corpus_index)).items():
            index.setdefault(mod_id, []).extend(entries)
    header = {"schema_version": SCHEMA_VERSION, "queue": str(queue), "references": [str(r) for r in references],
              "corpus_index": str(corpus_index) if corpus_index else None}
    records = []
    with Checkpoint(queue / CHECKPOINT_FILE, header) as checkpoint:
        for number, workspace in enumerate(workspaces, 1):
            cached = checkpoint.get(workspace.name)
            started = time.perf_counter()
            record = cached if cached is not None else judge(workspace, index)
            if cached is None:
                checkpoint.add(workspace.name, record)
            records.append(record)
            if not quiet:
                report(number, len(workspaces), workspace.name, record["verdict"], None if cached is not None else time.perf_counter() - started)
        counts: dict[str, int] = {}
        for record in records:
            counts[record["verdict"]] = counts.get(record["verdict"], 0) + 1
        result = {"schema_version": SCHEMA_VERSION, "mode": "SUPERSESSION", "queue": str(queue), "references": header["references"],
                  "counts": counts, "mods": records, "result_path": str(queue / RESULT_FILE)}
        (queue / RESULT_FILE).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        checkpoint.finish()
    return result
