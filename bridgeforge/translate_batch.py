"""`bridgeforge translate-batch`: a mod's whole translation in one command (ROADMAP 34.28, 2026-10-04).

The steps run by hand for Gensoukyou and the 2026-10-04 batch, chained: `export_translation` (every non-English
unit of CSV, JSON, Java and jar string constants, with stable ids), optional prefill from an English reference copy
or a translator's record, chunks of `chunk` entries each given to an AI agent that may edit only that chunk file,
a strict check of every returned chunk, then `apply_translation` into a complete translated copy (`out_dir`) or the
working copy (`in_place`), and `check_translation` on the result.

A chunk is accepted only when every entry is filled, no CJK is left, the placeholders (%s, %d, $variables...) match
the source exactly as `apply_translation` counts them, and no entry was added, removed, reordered or had its source
changed. A rejected chunk is retried once, then reported; nothing is applied until every chunk is accepted.
Accepted chunks go to a checkpoint (`<work>/translate-batch.partial.jsonl`), so a rerun redoes only what is missing;
a usage-limit message stops the run at once. Each chunk's glossary is merged and handed to the next, so a name is
translated the same way across files.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Callable

from .progress import Checkpoint, report
from .translation import _has_cjk, _placeholders, apply_translation, check_translation, export_translation, prefill_from_record, prefill_from_reference

DEFAULT_CHUNK = 120
LIMIT_PATTERN = re.compile(r"hit your session limit|usage limit", re.I)
PROMPT = """You are translating text from a Starsector mod into English. Edit ONLY the file {file} in the current folder.
It is JSON with "entries": fill every entries[].translation with natural, concise Starsector English for its "source".
Keep every %s, %d, $variable, {{0}}, \\u0001 marker, id, file path, number and line break exactly; keep leading and
trailing punctuation and brackets. Translate names of factions, ships and places consistently: use the "glossary" object
(source -> English) for terms already decided, and add the terms you decide. A "context" says where the text appears.
Do not add, remove or reorder entries and do not change any other field. Write nothing outside this folder."""


class TranslateBatchError(ValueError):
    pass


def verify_chunk(original: list[dict], returned: list[dict]) -> list[str]:
    """Why a returned chunk cannot be applied (empty when it can)."""
    if [e["id"] for e in returned] != [e["id"] for e in original] or any(a.get("source") != b["source"] for a, b in zip(returned, original)):
        return ["entries were added, removed, reordered or their source changed"]
    problems = []
    for entry in returned:
        value = entry.get("translation") or ""
        if not value.strip():
            problems.append(f"{entry['id']}: blank")
        elif _has_cjk(value):
            problems.append(f"{entry['id']}: CJK left")
        elif _placeholders(value) != _placeholders(entry["source"]):
            problems.append(f"{entry['id']}: placeholders differ")
    return problems


def agent_translator(agent: str, timeout: int = 1500) -> Callable[[Path], str]:
    """A translator that runs `agent` (e.g. "claude -p --permission-mode acceptEdits") in the chunk's folder with the
    prompt on stdin; returns its output for the usage-limit check."""
    from .escalation import resolve_agent_command

    command = resolve_agent_command(agent)

    def run(chunk_file: Path) -> str:
        done = subprocess.run(command, shell=True, input=PROMPT.format(file=chunk_file.name), cwd=chunk_file.parent,
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        return (done.stdout or "") + (done.stderr or "")
    return run


def translate_batch(mod_dir: Path, *, translator: Callable[[Path], str], work_dir: Path, out_dir: Path | None = None,
                    in_place: bool = False, chunk: int = DEFAULT_CHUNK, reference: Path | None = None,
                    records: list[Path] | None = None, quiet: bool = False) -> dict:
    mod_dir = Path(mod_dir).expanduser().resolve()
    if (out_dir is None) == (not in_place):
        raise TranslateBatchError("choose exactly one of --out or --in-place.")
    work_dir = Path(work_dir).expanduser().resolve()
    if work_dir == mod_dir or mod_dir in work_dir.parents:
        raise TranslateBatchError("the work folder must not be inside the mod.")
    work_dir.mkdir(parents=True, exist_ok=True)
    document = export_translation(mod_dir)
    prefilled = {}
    if reference is not None:
        prefilled["reference"] = prefill_from_reference(document, mod_dir, Path(reference))
    if records:
        prefilled["record"] = prefill_from_record(document, [Path(p) for p in records])
    (work_dir / "export.json").write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    todo = [e for e in document["entries"] if not (e.get("translation") or "").strip()]
    chunks = [todo[i:i + chunk] for i in range(0, len(todo), chunk)]
    fingerprint = hashlib.sha256(json.dumps(document["file_hashes"], sort_keys=True).encode("utf-8")).hexdigest()
    header = {"mod": str(mod_dir), "file_hashes": fingerprint, "chunk": chunk}
    glossary = dict(document.get("glossary") or {})
    filled: dict[str, str] = {}
    failed: dict[int, list[str]] = {}
    stopped = None
    with Checkpoint(work_dir / "translate-batch.partial.jsonl", header) as checkpoint:
        for number, entries in enumerate(chunks, 1):
            key = f"chunk{number:04d}"
            cached = checkpoint.get(key)
            started = time.perf_counter()
            if cached is not None:
                filled.update(cached["translations"])
                glossary.update(cached.get("glossary") or {})
                continue
            chunk_file = work_dir / f"{key}.json"
            problems: list[str] = []
            for attempt in (1, 2):
                chunk_file.write_text(json.dumps({"instructions": document.get("instructions"), "glossary": glossary,
                                                  "entries": entries}, ensure_ascii=False, indent=2), encoding="utf-8")
                output = translator(chunk_file)
                (work_dir / f"{key}.agent.txt").write_text(output or "", encoding="utf-8")
                if LIMIT_PATTERN.search(output or ""):
                    stopped = f"usage limit at {key}"
                    break
                try:
                    returned = json.loads(chunk_file.read_text(encoding="utf-8"))
                except (OSError, ValueError) as exc:
                    problems = [f"unreadable chunk file: {exc}"]
                    continue
                problems = verify_chunk(entries, returned.get("entries") or [])
                if not problems:
                    glossary.update({k: v for k, v in (returned.get("glossary") or {}).items() if isinstance(v, str) and v.strip()})
                    translations = {e["id"]: e["translation"] for e in returned["entries"]}
                    filled.update(translations)
                    checkpoint.add(key, {"translations": translations, "glossary": returned.get("glossary") or {}})
                    break
            if stopped:
                break
            if problems:
                failed[number] = problems[:5]
            if not quiet:
                report(number, len(chunks), key, "ACCEPTED" if not problems else f"REJECTED ({len(problems)} problem(s))",
                       time.perf_counter() - started)
        result = {"schema_version": 1, "mode": "TRANSLATE_BATCH", "mod": str(mod_dir), "entries": len(document["entries"]),
                  "prefilled": prefilled, "chunks": len(chunks), "translated": len(filled), "failed_chunks": failed,
                  "stopped": stopped, "applied": None, "check": None, "work_dir": str(work_dir)}
        if stopped or failed:
            return result  # the checkpoint stays: a rerun redoes only the failed or missing chunks
        for entry in document["entries"]:
            if entry["id"] in filled:
                entry["translation"] = filled[entry["id"]]
        document["glossary"] = glossary
        (work_dir / "translations.json").write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
        applied = apply_translation(mod_dir, document, out_dir=Path(out_dir) if out_dir else None, in_place=in_place)
        result["applied"] = applied
        result["check"] = check_translation(Path(out_dir) if out_dir else mod_dir)
        checkpoint.finish()
    return result
