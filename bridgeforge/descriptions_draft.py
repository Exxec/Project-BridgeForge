"""`bridgeforge descriptions draft WORKSPACE|QUEUE` (ROADMAP item 73 D1; owner decision 2026-10-14: crafted drafts allowed).

Fills `reports/description-drafts.md` for every hull, weapon and ship system the mod still has no codex description
for, in the table `descriptions.parse_draft` reads, from the first source that has the id:

1. another version of the same mod (a mod root with the same `mod_info.json` id: a sibling workspace's `working/` or
   `original/`, or any folder named with `--version-source`, e.g. `Done/`),
2. a sibling mod of the same queue (`sibling_assets.sibling_roots`; a row only when every sibling row for that id and
   type has the same first text),
3. a crafted draft written by an agent from the mod's own data (skipped with `--no-crafted`).

Every row names its source in a fourth column (`version: <Mod>`, `sibling: <Mod>`, `crafted`). Only `crafted` rows are
listed as crafted in BRIDGEFORGE_CREDITS.txt by `descriptions apply` (text taken from another copy of the mod is the
author's own). Nothing here edits the mod: the owner reviews the sheet, then runs `descriptions apply`.

The agent is a callable `crafter(chunk_file: Path) -> str` that edits the JSON chunk file in place (the same contract as
`translate_batch.agent_translator`); tests inject a stub. Every returned text is checked (filled, one line, two to
four sentences, no CJK, no table pipe) and a rejected one stays listed as unresolved.
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
from .safeio import atomic_write_text

DRAFT_RELATIVE = Path("reports") / "description-drafts.md"
DEFAULT_CHUNK = 25
MIN_SENTENCES, MAX_SENTENCES = 2, 4
_CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯]")
_SENTENCE_END = re.compile(r"[.!?](?:[\"')\]]*)(?:\s|$)")
PROMPT = """You are writing Starsector codex descriptions. Edit ONLY the file {file} in the current folder.
It is JSON with "entries": fill every entries[].text. Each entry has "facts" taken from the mod's own data (kind, name, size,
role, manufacturer, system). Write two to four sentences of plain English in the tone of the mod's other text, using only
those facts and general ship, weapon or system function. Invent no lore names, factions, people, places or events. One
line per text, no vertical bars, no markdown. Do not add, remove or reorder entries or change any other field."""

TYPE_FOR_KIND = {"hull": "SHIP", "weapon": "WEAPON", "ship-system": "SHIP_SYSTEM"}
_FACT_COLUMNS = ("name", "designation", "tech/manufacturer", "size", "type", "system id", "primaryRoleStr", "role")

Crafter = Callable[[Path], str]


def agent_crafter(agent: str, timeout: int = 1500) -> Crafter:
    """A crafter that runs `agent` (e.g. "claude -p --permission-mode acceptEdits") in the chunk's folder with PROMPT on stdin."""
    from .escalation import resolve_agent_command

    command = resolve_agent_command(agent)

    def run(chunk_file: Path) -> str:
        done = subprocess.run(command, shell=True, input=PROMPT.format(file=chunk_file.name), cwd=chunk_file.parent,
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        return (done.stdout or "") + (done.stderr or "")
    return run


def _mod_id(root: Path) -> str | None:
    from .scanner import _load_lenient_json_file

    info = _load_lenient_json_file(root / "mod_info.json") if (root / "mod_info.json").is_file() else None
    return str(info.get("id")) if isinstance(info, dict) and info.get("id") else None


def version_roots(workspace: Path, extra: list[Path] | None = None) -> list[Path]:
    """Other mod roots that carry the same mod id as this workspace: sibling workspaces and the `extra` folders (looked
    through two levels, so `Done/` and a reference rig's `mods/` work)."""
    from .sibling_assets import sibling_roots

    mod_id = _mod_id(Path(workspace) / "working")
    if not mod_id:
        return []
    candidates = list(sibling_roots(workspace))
    for base in extra or []:
        base = Path(base).expanduser()
        if not base.is_dir():
            continue
        candidates += [base] if (base / "mod_info.json").is_file() else []
        for child in sorted(p for p in base.iterdir() if p.is_dir()):
            candidates += [child] if (child / "mod_info.json").is_file() else sorted(p for p in child.iterdir() if (p / "mod_info.json").is_file())
    return [root for root in dict.fromkeys(candidates) if _mod_id(root) == mod_id]


def _owner(root: Path) -> str:
    """The workspace folder name a root belongs to (working/, original/<Mod>/ or a folder named directly)."""
    parts = root.parts
    for marker in ("working", "original", "extracted"):
        if marker in parts:
            index = len(parts) - 1 - parts[::-1].index(marker)
            return parts[index - 1] if index else root.name
    return root.name


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("|", "/")).strip()


def _row_text(row: dict[str, str]) -> str:
    return _clean_text(row.get("text1", ""))


def _from_roots(cid: str, kind: str, roots: list[Path]) -> tuple[str, str] | None:
    """(text, owner) when every root that has this id/type agrees on a non-empty text1, else None."""
    from .sibling_assets import DESCRIPTIONS_RELATIVE, _read_rows

    found: dict[str, str] = {}
    for root in roots:
        for row in _read_rows(root / DESCRIPTIONS_RELATIVE):
            if row.get("id") == cid and row.get("type", "").upper() == kind and _row_text(row):
                found.setdefault(_row_text(row), _owner(root))
    return next(iter(found.items())) if len(found) == 1 else None


def _facts(working: Path, mod_info: dict) -> Callable[[str, str], dict]:
    from .descriptions import _index

    sources = {"hull": _index(working / "data" / "hulls" / "ship_data.csv"), "weapon": _index(working / "data" / "weapons" / "weapon_data.csv"),
               "ship-system": _index(working / "data" / "shipsystems" / "ship_systems.csv")}

    def facts(cid: str, kind: str) -> dict:
        row = sources.get(kind, {}).get(cid) or {}
        found = {column: row[column].strip() for column in _FACT_COLUMNS if row.get(column, "").strip()}
        return {"kind": kind, "mod": mod_info.get("name") or "", **found}
    return facts


def check_crafted(text: str) -> str | None:
    """Why a crafted text cannot go in the draft (None when it can)."""
    if not text or not text.strip():
        return "blank"
    if "\n" in text or "|" in text:
        return "not a single line without vertical bars"
    if _CJK.search(text):
        return "CJK left"
    sentences = len(_SENTENCE_END.findall(text.strip() + " "))
    if not MIN_SENTENCES <= sentences <= MAX_SENTENCES:
        return f"{sentences} sentence(s), want {MIN_SENTENCES} to {MAX_SENTENCES}"
    return None


def craft(entries: list[dict], crafter: Crafter, work_dir: Path, *, chunk: int = DEFAULT_CHUNK) -> tuple[dict[str, str], dict[str, str]]:
    """Run `crafter` over `entries` ({"id", "type", "facts"}); returns (texts by "id|TYPE", rejected reason by "id|TYPE")."""
    work_dir.mkdir(parents=True, exist_ok=True)
    texts: dict[str, str] = {}
    rejected: dict[str, str] = {}
    for number, start in enumerate(range(0, len(entries), chunk), 1):
        part = entries[start:start + chunk]
        chunk_file = work_dir / f"craft{number:03d}.json"
        payload = {"instructions": PROMPT.format(file=chunk_file.name),
                   "entries": [{"id": e["id"], "type": e["type"], "facts": e["facts"], "text": ""} for e in part]}
        chunk_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        output = crafter(chunk_file)
        (work_dir / f"craft{number:03d}.agent.txt").write_text(output or "", encoding="utf-8")
        try:
            returned = json.loads(chunk_file.read_text(encoding="utf-8")).get("entries") or []
        except (OSError, ValueError) as exc:
            rejected.update({f"{e['id']}|{e['type']}": f"unreadable chunk file: {exc}" for e in part})
            continue
        by_key = {f"{r.get('id')}|{r.get('type')}": r for r in returned if isinstance(r, dict)}
        for entry in part:
            key = f"{entry['id']}|{entry['type']}"
            text = _clean_text(str((by_key.get(key) or {}).get("text") or ""))
            problem = check_crafted(text) if key in by_key else "entry missing from the returned chunk"
            if problem:
                rejected[key] = problem
            else:
                texts[key] = text
    return texts, rejected


def _render(workspace: Path, rows: list[dict], unresolved: list[dict]) -> str:
    lines = [f"# Description drafts: {workspace.name}", "",
             "Review each row, edit the text, delete rows you do not want, then run `bridgeforge descriptions apply`.",
             "Source: `version` = copied from another version of this mod, `sibling` = copied from a sibling mod,",
             "`crafted` = written by an agent from this mod's data (credited as crafted, never the author's text).", "",
             "| ID | Type | Text | Source |", "| --- | --- | --- | --- |"]
    lines += [f"| `{r['id']}` | {r['type']} | {r['text']} | {r['source']} |" for r in rows]
    if unresolved:
        lines += ["", "## Unresolved", ""] + [f"- `{u['id']}` {u['type']}: {u['reason']}" for u in unresolved]
    return "\n".join(lines) + "\n"


def draft_workspace(workspace: Path, *, vanilla_core: Path | None = None, crafter: Crafter | None = None,
                    version_sources: list[Path] | None = None, work_dir: Path | None = None, chunk: int = DEFAULT_CHUNK) -> dict:
    """Write the workspace's draft sheet; `crafter=None` is `--no-crafted`. Returns counts per source and the unresolved list."""
    from .scanner import _load_lenient_json_file
    from .sibling_assets import _plan_findings, sibling_roots

    workspace = Path(workspace).expanduser().resolve()
    working = workspace / "working"
    mod_info = _load_lenient_json_file(working / "mod_info.json") if (working / "mod_info.json").is_file() else None
    if not isinstance(mod_info, dict):
        raise ValueError(f"{workspace} has no readable working/mod_info.json.")
    _, missing = _plan_findings(working, vanilla_core)
    same_mod = version_roots(workspace, version_sources)
    same_mod_set = set(same_mod)
    siblings = [r for r in sibling_roots(workspace) if r not in same_mod_set]
    kinds = {v: k for k, v in TYPE_FOR_KIND.items()}
    rows: list[dict] = []
    todo: list[dict] = []
    facts = _facts(working, mod_info)
    for cid, kind in missing:
        label = kinds.get(kind, kind.lower())
        hit = _from_roots(cid, kind, same_mod)
        if hit:
            rows.append({"id": cid, "type": kind, "text": hit[0], "source": f"version: {hit[1]}"})
            continue
        hit = _from_roots(cid, kind, siblings)
        if hit:
            rows.append({"id": cid, "type": kind, "text": hit[0], "source": f"sibling: {hit[1]}"})
            continue
        todo.append({"id": cid, "type": kind, "facts": facts(cid, label)})
    unresolved: list[dict] = []
    if todo and crafter is not None:
        texts, rejected = craft(todo, crafter, work_dir or workspace / "scratch" / "description-craft", chunk=chunk)
        for entry in todo:
            key = f"{entry['id']}|{entry['type']}"
            if key in texts:
                rows.append({"id": entry["id"], "type": entry["type"], "text": texts[key], "source": "crafted"})
            else:
                unresolved.append({"id": entry["id"], "type": entry["type"], "reason": f"crafted text rejected: {rejected.get(key, 'none returned')}"})
    else:
        unresolved = [{"id": e["id"], "type": e["type"], "reason": "no other version or sibling has it; crafting skipped" if crafter is None
                       else "no source"} for e in todo]
    path = workspace / DRAFT_RELATIVE
    if rows or unresolved:
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, _render(workspace, rows, unresolved))
    counts = {"version": 0, "sibling": 0, "crafted": 0}
    for row in rows:
        counts[row["source"].split(":")[0]] += 1
    return {"workspace": workspace.name, "missing": len(missing), "rows": len(rows), "by_source": counts, "unresolved": unresolved,
            "path": str(path) if rows or unresolved else None}


def _workspaces(target: Path) -> list[Path]:
    target = Path(target).expanduser().resolve()
    if (target / "working" / "mod_info.json").is_file():
        return [target]
    return sorted(p for p in target.iterdir() if p.is_dir() and not p.name.startswith("_") and (p / "working" / "mod_info.json").is_file())


def draft_descriptions(target: Path, *, vanilla_core: Path | None = None, crafter: Crafter | None = None,
                       version_sources: list[Path] | None = None, checkpoint_path: Path | None = None, quiet: bool = False) -> dict:
    """`descriptions draft` over one workspace or a whole queue; a queue run resumes from `checkpoint_path`."""
    from .report_status import report_status

    workspaces = _workspaces(target)
    header = {"target": str(Path(target).expanduser().resolve()), "crafted": crafter is not None, "workspaces": [w.name for w in workspaces],
              "sources": hashlib.sha256(json.dumps([str(p) for p in version_sources or []]).encode("utf-8")).hexdigest()}
    results = []
    with Checkpoint(checkpoint_path, header) as checkpoint:
        for number, workspace in enumerate(workspaces, 1):
            cached = checkpoint.get(workspace.name)
            started = time.perf_counter()
            if cached is not None:
                results.append(cached)
                if not quiet:
                    report(number, len(workspaces), workspace.name, f"{cached['rows']} row(s)", None)
                continue
            if report_status(workspace / "working" / "reports" / "REVIVAL_REPORT.md") == "SUPERSEDED":
                continue
            result = draft_workspace(workspace, vanilla_core=vanilla_core, crafter=crafter, version_sources=version_sources)
            checkpoint.add(workspace.name, result)
            results.append(result)
            if not quiet:
                report(number, len(workspaces), workspace.name,
                       f"{result['rows']} row(s) of {result['missing']} ({result['by_source']}), {len(result['unresolved'])} unresolved",
                       time.perf_counter() - started)
        checkpoint.finish()
    totals = {k: sum(r["by_source"][k] for r in results) for k in ("version", "sibling", "crafted")}
    return {"mods": len(results), "missing": sum(r["missing"] for r in results), "rows": sum(r["rows"] for r in results),
            "by_source": totals, "unresolved": sum(len(r["unresolved"]) for r in results), "results": results}
