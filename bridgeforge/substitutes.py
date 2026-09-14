"""`bridgeforge dependency-substitutes`: can a missing or discontinued dependency be replaced?

For a mod, it collects what the mod needs from other mods: content ids (hull mods, wings, weapons,
hulls) and `data.*` classes that neither it nor vanilla defines (the scanner's
`content-reference-unresolved` / `source-import-unresolved`), plus declared dependencies that no
visible mod provides. It then ranks every visible mod as a provider:
- EXACT: provides every needed id/class and targets the 0.98a series; only the dependency line changes;
- PARTIAL: provides some; Starsector has no id aliasing, so the rest means editing this mod's data;
- NONE: no visible mod provides anything.
Known renames and splits that coverage can't see come from `dependency_successors.json` (evidence
recorded per entry). The footprint (how many references and files lean on the dependency) and the
dependency's own revival state, when it is a workspace here, drive a recommended strategy:
SWAP, REVIVE_DEPENDENCY, STRIP_FROM_MOD or ESCALATE (see docs/DEPENDENCY_STRATEGY.md).

Read-only: it never edits a mod.
"""

from __future__ import annotations

import csv
import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .scanner import _base_game_version, _load_lenient_json_file

SCHEMA_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parent.parent
SUCCESSORS_PATH = Path(__file__).resolve().parent / "dependency_successors.json"
TARGET_SERIES = "0.98a"
KINDS = ("hullmod", "weapon", "wing", "hull", "class")
REVIVABLE_MANUAL = 15  # a dependency workspace this clean is worth reviving first


@dataclass
class Provider:
    mod_id: str
    name: str
    path: str
    game_version: str
    provides: dict[str, set[str]] = field(default_factory=lambda: {kind: set() for kind in KINDS})
    total_conversion: bool = False


def _csv_ids(path: Path) -> set[str]:
    try:
        with path.open(encoding="utf-8-sig", errors="replace", newline="") as handle:
            return {(row.get("id") or "").strip() for row in csv.DictReader(handle) if (row.get("id") or "").strip() and not (row.get("id") or "").strip().startswith("#")}
    except OSError:
        return set()


def provider_for(folder: Path) -> Provider | None:
    """What one mod folder defines. Only file listings and small data files are read."""
    info = _load_lenient_json_file(folder / "mod_info.json") if (folder / "mod_info.json").is_file() else None
    if not isinstance(info, dict) or not info.get("id"):
        return None
    provider = Provider(str(info["id"]), str(info.get("name") or info["id"]), str(folder), str(info.get("gameVersion") or ""))
    provider.total_conversion = bool(info.get("totalConversion"))
    data = folder / "data"
    provider.provides["hullmod"] |= _csv_ids(data / "hullmods" / "hull_mods.csv")
    provider.provides["weapon"] |= _csv_ids(data / "weapons" / "weapon_data.csv")
    provider.provides["wing"] |= _csv_ids(data / "hulls" / "wing_data.csv")
    for pattern, kind, key in (("*.wpn", "weapon", "id"), ("*.ship", "hull", "hullId"), ("*.skin", "hull", "skinHullId")):
        for path in data.rglob(pattern) if data.is_dir() else []:
            spec = _load_lenient_json_file(path)
            if isinstance(spec, dict) and isinstance(spec.get(key), str):
                provider.provides[kind].add(spec[key])
    for jar in folder.rglob("*.jar"):
        try:
            with zipfile.ZipFile(jar) as archive:
                provider.provides["class"] |= {name[:-6].replace("/", ".") for name in archive.namelist() if name.endswith(".class")}
        except (OSError, zipfile.BadZipFile):
            continue
    for source in data.rglob("*.java") if data.is_dir() else []:
        try:
            package = re.search(r"(?m)^\s*package\s+([\w.]+)\s*;", source.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        provider.provides["class"].add(f"{package.group(1)}.{source.stem}" if package else source.stem)
    return provider


def provider_index(roots: list[Path], exclude: Path | None = None) -> list[Provider]:
    """Providers from mod folders: each root is a mods folder, a mod folder, or an In operation tree."""
    seen: set[str] = set()
    providers: list[Provider] = []
    for root in roots:
        root = Path(root)
        if not root.is_dir():
            continue
        candidates = [root] if (root / "mod_info.json").is_file() else [p for p in root.iterdir() if p.is_dir()]
        candidates += [p / "working" for p in root.iterdir() if (p / "working" / "mod_info.json").is_file()] if not (root / "mod_info.json").is_file() else []
        for folder in candidates:
            resolved = folder.resolve()
            if str(resolved) in seen or (exclude is not None and resolved == Path(exclude).resolve()):
                continue
            seen.add(str(resolved))
            provider = provider_for(folder)
            if provider is not None:
                providers.append(provider)
    return providers


_EVIDENCE = re.compile(r"^(hullmod|wing|weapon|hull):(\S+) \((\d+) file")


def required_from_scan(result) -> tuple[dict[str, set[str]], dict[str, int]]:
    """({kind: ids needed from other mods}, {id: files referencing it}) from a scan's findings."""
    needed: dict[str, set[str]] = {kind: set() for kind in KINDS}
    files: dict[str, int] = {}
    for finding in result.findings:
        if finding.id == "content-reference-unresolved":
            for item in finding.evidence:
                match = _EVIDENCE.match(item)
                if match:
                    needed[match.group(1)].add(match.group(2))
                    files[match.group(2)] = int(match.group(3))
        elif finding.id == "source-import-unresolved":
            for item in finding.evidence:
                if item.startswith("data.") and " " not in item:
                    needed["class"].add(item)
                    files[item] = files.get(item, 0) + 1
    return needed, files


def load_successors(path: Path = SUCCESSORS_PATH) -> list[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("successors", [])
    except (OSError, json.JSONDecodeError):
        return []


def _covers(provider: Provider, needed: dict[str, set[str]]) -> dict[str, set[str]]:
    covered: dict[str, set[str]] = {}
    for kind, ids in needed.items():
        pool = provider.provides[kind]
        hits = {ident for ident in ids if ident in pool or (kind == "class" and ident.rsplit(".", 1)[0] in pool)}
        if hits:
            covered[kind] = hits
    return covered


def _current(provider: Provider) -> bool:
    return bool(provider.game_version) and _base_game_version(provider.game_version).startswith(TARGET_SERIES)


def _keys(needed: dict[str, set[str]]) -> set[str]:
    return {f"{kind}:{ident}" for kind, ids in needed.items() for ident in ids}


def rank(needed: dict[str, set[str]], providers: list[Provider]) -> list[dict]:
    total = sum(len(ids) for ids in needed.values())
    ranked = []
    for provider in providers:
        covered = _covers(provider, needed)
        count = sum(len(ids) for ids in covered.values())
        if not count:
            continue
        current = _current(provider)
        verdict = "EXACT" if count == total and current else "PARTIAL"
        ranked.append({
            "mod_id": provider.mod_id, "name": provider.name, "path": provider.path, "game_version": provider.game_version,
            "targets_0.98a": current, "covered": count, "total": total, "verdict": verdict,
            "covered_ids": sorted(f"{kind}:{ident}" for kind, ids in covered.items() for ident in ids),
            "missing": sorted(f"{kind}:{ident}" for kind, ids in needed.items() for ident in ids if ident not in covered.get(kind, set()))[:25],
        })
    return sorted(ranked, key=lambda item: (-item["covered"], not item["targets_0.98a"], item["mod_id"]))


def cover(needed: dict[str, set[str]], providers: list[Provider], preferred: set[str] | None = None) -> tuple[list[tuple[Provider, set[str]]], set[str]]:
    """Greedy smallest set of providers covering the needed ids (Rebal needs FX Core + EZ Damage + ...).

    Ties prefer mods that target 0.98a, then mods the dependent already declares.
    """
    preferred = preferred or set()
    remaining = _keys(needed)
    chosen: list[tuple[Provider, set[str]]] = []
    while remaining:
        best: Provider | None = None
        best_hits: set[str] = set()
        for provider in providers:
            covered = _covers(provider, {kind: {key.split(":", 1)[1] for key in remaining if key.startswith(kind + ":")} for kind in KINDS})
            hits = {f"{kind}:{ident}" for kind, ids in covered.items() for ident in ids}
            key = (len(hits), _current(provider), provider.mod_id in preferred)
            if hits and (best is None or key > (len(best_hits), _current(best), best.mod_id in preferred)):
                best, best_hits = provider, hits
        if best is None:
            break
        chosen.append((best, best_hits))
        remaining -= best_hits
    return chosen, remaining


def _workspace_state(ops: Path, mod_id: str) -> dict | None:
    """Revival state of a dependency that is itself a workspace here (REVIVAL_REPORT status, MANUAL count)."""
    for info in list(ops.glob("*/working/mod_info.json")):
        data = _load_lenient_json_file(info)
        if isinstance(data, dict) and data.get("id") == mod_id:
            workspace = info.parent.parent
            report = info.parent / "reports" / "REVIVAL_REPORT.md"
            status = None
            if report.is_file():
                lines = [line.strip("* ") for line in report.read_text(encoding="utf-8").splitlines() if line.strip()]
                status = lines[-1] if lines else None
            scans = sorted((workspace / "reports").glob("scan-*/bridgeforge.compat.json"), key=lambda p: p.stat().st_mtime)
            manual = None
            if scans:
                findings = json.loads(scans[-1].read_text(encoding="utf-8-sig"))
                manual = sum(1 for f in findings.get("findings", findings) if f.get("classification") == "MANUAL")
            return {"workspace": workspace.name, "status": status, "manual_findings": manual}
    return None


def strategy(needed: dict[str, set[str]], files: dict[str, int], chosen: list[dict], uncovered: set[str]) -> tuple[str, str]:
    """Recommended course, with its reason. `chosen` is the provider set cover (each with
    'name', 'targets_0.98a' and optional 'workspace' state); `uncovered` what no provider has."""
    references = sum(len(ids) for ids in needed.values())
    touched = sum(files.values())
    if not chosen:
        if references <= 3 and touched <= 5:
            return "STRIP_FROM_MOD", f"Only {references} id(s)/class(es) in {touched} place(s) lean on it and no visible mod provides any: removing or substituting them is smaller than reviving a dependency (owner approval, behaviour change)."
        return "ESCALATE", f"No visible mod provides any of the {references} needed id(s)/class(es), used in {touched} place(s): revive the dependency (if its licence allows) or rebuild the mod without it. Owner decision."

    def revivable(item: dict) -> bool:
        state = item.get("workspace")
        return bool(state) and state.get("manual_findings") is not None and state["manual_findings"] <= REVIVABLE_MANUAL

    current = [item for item in chosen if item["targets_0.98a"]]
    revive = [item for item in chosen if not item["targets_0.98a"] and revivable(item)]
    heavy = [item for item in chosen if not item["targets_0.98a"] and not revivable(item)]
    # Ids only a heavy (or unscanned, or not-a-workspace) provider has count as unprovided.
    hard = set(uncovered) | {key for item in heavy for key in item.get("covers", [])}
    hard -= {key for item in current + revive for key in item.get("covers", [])}
    hard_places = sum(files.get(key.split(":", 1)[1], 1) for key in hard)

    def describe(items: list[dict]) -> str:
        return "; ".join(
            f"{item['name']} ({item['game_version'] or 'no version'}"
            + (f", workspace {item['workspace']['workspace']}: {item['workspace'].get('manual_findings')} MANUAL" if item.get("workspace") else ", not a workspace here")
            + ")"
            for item in items
        )

    plan = []
    if current:
        plan.append(f"declare {', '.join(item['name'] for item in current)} (0.98a)")
    if revive:
        plan.append(f"revive {describe(revive)} first")
    if not hard:
        if not revive:
            return "SWAP", f"{', '.join(item['name'] for item in current)} provide(s) everything and target 0.98a: declare {'it' if len(current) == 1 else 'them'}; nothing else changes."
        return "REVIVE_DEPENDENCY", f"Every needed id/class has a provider: {'; '.join(plan)}. Then this mod works as it is."
    left = f"{', '.join(sorted(hard)[:4])}{' ...' if len(hard) > 4 else ''}"
    heavy_note = f" (only in {describe(heavy)}, too large to revive for this)" if heavy else " (in no visible mod)"
    if len(hard) <= 3 and hard_places <= 5:
        plan.append(f"strip or substitute {left}{heavy_note}; owner approval, behaviour change")
        return "STRIP_FROM_MOD", f"{'; '.join(plan)}."
    return "ESCALATE", f"{len(hard)} id(s)/class(es) in {hard_places} place(s) have no practical provider: {left}{heavy_note}. Other ids: {'; '.join(plan) or 'none'}. Revive, remap, or rebuild without it. Owner decision."


def dependency_substitutes(mod_dir: Path, provider_roots: list[Path], *, vanilla_core: Path | None = None, ops: Path | None = None) -> dict:
    from .models import TargetProfile
    from .scanner import scan_mod

    mod_dir = Path(mod_dir).expanduser().resolve()
    result = scan_mod(mod_dir, TargetProfile(), vanilla_core)
    needed, files = required_from_scan(result)
    declared = [str(item.get("id")) for item in (result.metadata.get("dependencies") or []) if isinstance(item, dict) and item.get("id")]
    providers = provider_index(provider_roots, exclude=mod_dir)
    provided_ids = {provider.mod_id for provider in providers}
    missing_declared = [dep for dep in declared if dep not in provided_ids]
    # A total conversion can't run beside another mod unless that mod is its add-on (declares it).
    # Vacuum defines thruster_fighter_sm, but Explorer Society and Rebal can't use it.
    excluded_tcs = sorted(p.name for p in providers if p.total_conversion and p.mod_id not in declared)
    providers = [p for p in providers if not p.total_conversion or p.mod_id in declared]
    candidates = rank(needed, providers)
    successors = [entry for entry in load_successors() if entry.get("match") in missing_declared or any(ident.startswith(entry.get("match", "\0")) for ids in needed.values() for ident in ids)]
    ops_dir = Path(ops) if ops else REPO_ROOT / "In operation"
    chosen_providers, uncovered = cover(needed, providers, preferred=set(declared))
    chosen = []
    for provider, hits in chosen_providers:
        item = {"mod_id": provider.mod_id, "name": provider.name, "game_version": provider.game_version, "targets_0.98a": _current(provider), "covers": sorted(hits)}
        if not item["targets_0.98a"]:
            item["workspace"] = _workspace_state(ops_dir, provider.mod_id)
        chosen.append(item)
    if any(needed.values()):
        course, reason = strategy(needed, files, chosen, uncovered)
    elif missing_declared:
        course, reason = "ESCALATE", f"Declared dependencies not found among visible mods: {', '.join(missing_declared)}. Install them or check the ids."
    else:
        course, reason = "NONE_NEEDED", "Everything the mod uses is defined by it, vanilla, or a visible declared dependency."
    return {
        "schema_version": SCHEMA_VERSION, "mode": "DEPENDENCY_SUBSTITUTES", "mod": str(mod_dir), "mod_id": result.metadata.get("id"),
        "providers_indexed": len(providers),
        "total_conversions_excluded": excluded_tcs,
        "needed": {kind: sorted(ids) for kind, ids in needed.items() if ids},
        "declared_dependencies_missing": missing_declared,
        "provider_set": chosen, "uncovered": sorted(uncovered),
        "candidates": candidates[:10],
        "successors": successors,
        "strategy": course, "reason": reason,
    }
