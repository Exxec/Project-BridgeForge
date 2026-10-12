"""`bridgeforge mods-compat`: hooks only one mod can own, across a real mods folder (ROADMAP 50, owner 2026-10-05).

Read-only. For every mod under the folder it records the hooks where the game uses one value and the last mod wins,
silently:

- `industry-plugin`: an RC8 industry's plugin set in industries.csv, or at load (a jar class that calls
  IndustrySpecAPI.setPluginClass and names the industry id; AoTD sets population, heavyindustry, orbitalworks,
  patrolhq, militarybase and highcommand so). The jar side is a byte search, so it is reported as "possible": AoTD
  Toolbox names spaceport while only adding a tag to it (2026-10-05);
- `new-game-plugin`: settings.json plugins.newGameSectorProcGen / newGameCreationEntryPoint (Adjusted Sector,
  Nexerelin, Random Assortment of Things, Wide Horizons);
- `replace`: a mod_info `replace` entry (the core file is swapped whole);
- `script-shadow`: a loose script at a vanilla script's own path (data/...java in RC8's core).

A hook claimed by two or more mods is a conflict. Progress per mod and a checkpoint (MODS_COMPAT.partial.jsonl in the
output folder) as for every corpus walk; the result is MODS_COMPAT.json / .md.
"""
from __future__ import annotations

import csv
import io
import json
import time
import zipfile
from pathlib import Path

from .progress import Checkpoint, report

RESULT_JSON, RESULT_MD, CHECKPOINT = "MODS_COMPAT.json", "MODS_COMPAT.md", "MODS_COMPAT.partial.jsonl"
_NEW_GAME_KEYS = ("newGameSectorProcGen", "newGameCreationEntryPoint")


def _vanilla_industries(core: Path) -> dict[str, str]:
    path = core / "data" / "campaign" / "industries.csv"
    if not path.is_file():
        return {}
    rows = csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig", errors="replace")))
    return {(r.get("id") or "").strip(): (r.get("plugin") or "").strip() for r in rows if (r.get("id") or "").strip()}


def _vanilla_scripts(core: Path) -> set[str]:
    return {p.relative_to(core).as_posix().lower() for p in (core / "data").rglob("*.java")}


def mod_hooks(mod: Path, vanilla_industries: dict[str, str], vanilla_scripts: set[str]) -> dict:
    """The hooks one mod folder claims (see the module docstring)."""
    from .scanner import _load_lenient_json_file, _loaded_mod_jars

    info = _load_lenient_json_file(mod / "mod_info.json") if (mod / "mod_info.json").is_file() else None
    info = info if isinstance(info, dict) else {}
    hooks: list[list[str]] = []
    industries = mod / "data" / "campaign" / "industries.csv"
    if industries.is_file():
        try:
            for row in csv.DictReader(io.StringIO(industries.read_text(encoding="utf-8-sig", errors="replace"))):
                industry, plugin = (row.get("id") or "").strip(), (row.get("plugin") or "").strip()
                if industry in vanilla_industries and plugin and plugin != vanilla_industries[industry]:
                    hooks.append(["industry-plugin", industry, f"industries.csv: {plugin.split('.')[-1]}"])
        except csv.Error:
            pass
    for jar in _loaded_mod_jars(mod):
        try:
            with zipfile.ZipFile(jar) as archive:
                for name in archive.namelist():
                    if not name.endswith(".class"):
                        continue
                    data = archive.read(name)
                    if b"setPluginClass" not in data:
                        continue
                    for industry in vanilla_industries:
                        if industry and industry.encode() in data:
                            hooks.append(["industry-plugin", industry, f"possible: {name} calls setPluginClass and names it"])
        except (OSError, zipfile.BadZipFile):
            continue
    settings = mod / "data" / "config" / "settings.json"
    spec = _load_lenient_json_file(settings) if settings.is_file() else None
    plugins = spec.get("plugins") if isinstance(spec, dict) else None
    for key in _NEW_GAME_KEYS:
        if isinstance(plugins, dict) and isinstance(plugins.get(key), str):
            hooks.append(["new-game-plugin", key, plugins[key]])
    for entry in info.get("replace") or [] if isinstance(info.get("replace"), list) else []:
        if isinstance(entry, str):
            hooks.append(["replace", entry.replace("\\", "/").lower(), entry])
    for source in (mod / "data").rglob("*.java") if (mod / "data").is_dir() else []:
        rel = source.relative_to(mod).as_posix().lower()
        if rel in vanilla_scripts:
            hooks.append(["script-shadow", rel, source.relative_to(mod).as_posix()])
    unique = sorted({tuple(h) for h in hooks})
    return {"mod": mod.name, "id": info.get("id"), "hooks": [list(h) for h in unique]}


def mods_compat(mods_dir: Path, vanilla_core: Path, output: Path, quiet: bool = False) -> dict:
    mods_dir, output = Path(mods_dir).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    folders = sorted(p for p in mods_dir.iterdir() if p.is_dir() and (p / "mod_info.json").is_file())
    vanilla_industries, vanilla_scripts = _vanilla_industries(vanilla_core), _vanilla_scripts(vanilla_core)
    header = {"mods_dir": str(mods_dir), "vanilla_core": str(vanilla_core), "mods": [f.name for f in folders]}
    records = []
    with Checkpoint(output / CHECKPOINT, header) as checkpoint:
        for number, folder in enumerate(folders, 1):
            cached = checkpoint.get(folder.name)
            started = time.perf_counter()
            if cached is None:
                try:
                    cached = mod_hooks(folder, vanilla_industries, vanilla_scripts)
                except OSError as exc:
                    cached = {"mod": folder.name, "id": None, "hooks": [], "error": str(exc)[:200]}
                checkpoint.add(folder.name, cached)
            records.append(cached)
            if not quiet:
                report(number, len(folders), folder.name, f"{len(cached['hooks'])} hook(s)", time.perf_counter() - started)
        claims: dict[tuple[str, str], list[dict]] = {}
        for record in records:
            for kind, key, detail in record["hooks"]:
                claims.setdefault((kind, key), []).append({"mod": record["mod"], "detail": detail})
        conflicts = [{"kind": kind, "key": key, "mods": owners} for (kind, key), owners in sorted(claims.items())
                     if len({o["mod"] for o in owners}) > 1]
        result = {"schema_version": 1, "mode": "MODS_COMPAT", "mods_dir": str(mods_dir), "mods": len(records),
                  "conflicts": conflicts, "records": records}
        (output / RESULT_JSON).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        lines = ["# Mods compatibility: hooks only one mod can own", "",
                 f"{len(records)} mod(s) in {mods_dir}; {len(conflicts)} hook(s) claimed by two or more.", ""]
        for kind in ("industry-plugin", "new-game-plugin", "replace", "script-shadow"):
            rows = [c for c in conflicts if c["kind"] == kind]
            if not rows:
                continue
            lines += [f"## {kind}", ""]
            for conflict in rows:
                owners = "; ".join(f"{o['mod']} ({o['detail']})" for o in conflict["mods"])
                lines.append(f"- `{conflict['key']}`: {owners}")
            lines.append("")
        (output / RESULT_MD).write_text("\n".join(lines), encoding="utf-8")
        checkpoint.finish()
    return result
