"""Translation memory for `translate-batch` (ROADMAP item 73 D2).

The memory is a Project Go (SSMT) translation-memory JSON, the file `translate-tm` writes
(`translation.export_project_go_tm`; a real one is `bridgeforge-state/project-go-tm/roundtrip-export.json`, read
2026-10-14): `{"schemaVersion": 1, "entries": [{"sourceText", "sourceLanguage", "targetLanguage", "translatedText",
"context", "provenance"}]}`. `bridgeforge-state/translations/` held no memory file on that date (only an empty
`mirfak/` folder), so `translate-batch` keeps its own at `bridgeforge-state/translations/memory.json` in the same format;
`ssmt tm import` reads it too.

- Before a chunk goes to the agent, every entry whose exact source text has exactly one stored translation (no CJK left,
  same placeholders as the source) is filled from the memory and marked `provenance: "memory"`; only the rest is sent.
- After every chunk is accepted, the new source -> translation pairs are added (existing pairs and their provenance are
  kept) and the file is written atomically.
"""
from __future__ import annotations

import json
from pathlib import Path

from .safeio import atomic_write_json
from .translation import _AUTHOR_PROVENANCE, _has_cjk, _placeholders

DEFAULT_MEMORY_RELATIVE = Path("bridgeforge-state") / "translations" / "memory.json"
MEMORY_PROVENANCE = "memory"
NEW_PAIR_PROVENANCE = "AI_TRANSLATED"


def load_memory(path: Path | None) -> list[dict]:
    """The memory's entries; empty when there is no file. A file that is not a memory is an error, never overwritten."""
    if path is None or not Path(path).is_file():
        return []
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"translation memory {path} is unreadable: {exc}") from exc
    entries = data.get("entries") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        raise ValueError(f"translation memory {path} has no entries list.")
    return [e for e in entries if isinstance(e, dict)]


def _lookup(entries: list[dict]) -> dict[str, str]:
    """source -> translation for sources with exactly one distinct usable translation."""
    options: dict[str, set[str]] = {}
    for entry in entries:
        if not isinstance(entry.get("sourceText"), str) or not isinstance(entry.get("translatedText"), str):
            continue
        options.setdefault(entry["sourceText"], set()).add(entry["translatedText"])
    return {source: next(iter(values)) for source, values in options.items() if len(values) == 1}


def prefill_from_memory(document: dict, entries: list[dict]) -> dict[str, int]:
    """Fill blank entries from the memory; returns {"reused": n, "skipped": n} (skipped = stored text unusable for the source)."""
    table = _lookup(entries)
    reused = skipped = 0
    for entry in document["entries"]:
        if (entry.get("translation") or "").strip() or entry["source"] not in table:
            continue
        stored = table[entry["source"]]
        if not stored.strip() or _has_cjk(stored) or _placeholders(stored) != _placeholders(entry["source"]):
            skipped += 1
            continue
        entry["translation"] = stored
        entry["provenance"] = MEMORY_PROVENANCE
        reused += 1
    return {"reused": reused, "skipped": skipped}


def update_memory(path: Path, existing: list[dict], document: dict) -> int:
    """Add the document's new source -> translation pairs (translated, not kept unchanged) to the memory file; returns how many."""
    known = {e.get("sourceText") for e in existing}
    added: dict[str, dict] = {}
    for entry in document["entries"]:
        source, value = entry["source"], (entry.get("translation") or "").strip()
        if source in known or source in added or not value or value == source or not _has_cjk(source) or entry.get("provenance") == MEMORY_PROVENANCE:
            continue
        added[source] = {"sourceText": source, "sourceLanguage": document.get("source_language", "zh"),
                         "targetLanguage": document.get("target_language", "en"), "translatedText": value, "context": "",
                         "provenance": "AUTHOR_LOCALIZATION" if entry.get("provenance") in _AUTHOR_PROVENANCE else NEW_PAIR_PROVENANCE}
    if added:
        atomic_write_json(path, {"schemaVersion": 1, "entries": existing + [added[k] for k in sorted(added)]})
    return len(added)
