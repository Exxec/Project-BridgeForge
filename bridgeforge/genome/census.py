"""94.G1 GR-2: a gene census of the corpus before 94.G2 (docs/FEATURE_GENOME_ROADMAP.md section 13).

G2 extends closure to campaign features and slices registration statements out of a mod's plugin. Its size depends on
two numbers no one had measured: how often each feature kind occurs, and how many features one plugin hook sets up
together (a hook with many is "monolithic": slicing has to separate them, or refuse). This counts both, per mod.

**Kinds.** The six content kinds from their tables (`vendor_plan._TABLES`, variants as files); the campaign kinds from
their data files (factions, industries, market conditions, abilities, rules.csv rows); and the code-only ones (star
systems, markets) as calls in the mod's own jars, labelled `code:`.

**Hooks.** The plugin is the class `mod_info.json`'s `modPlugin` names. For each lifecycle hook it declares, the census
follows the calls into the plugin's own methods (transitively, recording the depth) and keeps three raw counts and the
callee list, so the measure can be re-scored without walking the corpus again (advisor review 2026-11-19):
- `registration_calls`: calls to `behavior_discovery.REGISTRATION_CALLS` (addScript, addListener, ...);
- `mod_classes`: distinct classes of the mod's own jars that are constructed or called (each is roughly one feature:
  a system generator, a faction setup);
- `api_mutations`: distinct game-API methods that change state (`add*`, `set*`, `create*`, `register*`, `spawn*` on
  `com/fs/` owners), the features a hook sets up inline (Eridani's faction relations and bounty entry);
- `invokes`: every call, as context.
A plugin with no bytecode (a loose `.java` script) is `source-only` and not measured; the summary counts those.

Calibration (2026-11-19, by hand against the source): Eridani Combine's `onNewGame` reaches `generate` at depth 1, one mod
class (the star system's generator) and two API mutations (`addParticipatingFaction`, `setRelationship`): three features, multi.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from bridgeforge.atlas.atlas_classfile import ClassFormatError, parse_class
from bridgeforge.behavior_discovery import LIFECYCLE_HOOKS, REGISTRATION_CALLS
from bridgeforge.mod_files import read_mod_info
from bridgeforge.scan.scan_classfile import _loaded_mod_jars, iter_class_files_in_jars
from bridgeforge.vendor_plan import _TABLES, _rows

CAMPAIGN_TABLES = {
    "industry": "data/campaign/industries.csv",
    "condition": "data/campaign/market_conditions.csv",
    "ability": "data/campaign/abilities.csv",
    "rule": "data/campaign/rules.csv",
}
_MUTATION = re.compile(r"^(add|set|create|register|spawn)[A-Z]")
CODE_KINDS = {"code:star-system": "createStarSystem", "code:market": "addMarketplace"}
MAX_DEPTH = 8


def _count_files(root: Path, folder: str, suffix: str) -> int:
    base = root / folder
    return sum(1 for path in base.rglob(f"*{suffix}") if path.is_file()) if base.is_dir() else 0


def kind_counts(root: Path, classes: dict) -> dict[str, int]:
    """{kind: count} for the content, campaign and code-only kinds the mod has."""
    counts = {kind: len(_rows(root, table)) for kind, table in _TABLES.items()}
    counts["variant"] = _count_files(root, "data/variants", ".variant")
    counts["faction"] = _count_files(root, "data/world/factions", ".faction")
    counts.update({kind: len(_rows(root, table)) for kind, table in CAMPAIGN_TABLES.items()})
    for kind, method in CODE_KINDS.items():
        counts[kind] = sum(1 for info in classes.values() for targets in info.method_targets for _, name in targets if name == method)
    return {kind: n for kind, n in sorted(counts.items()) if n}


def _mod_classes(root: Path) -> dict:
    """{internal class name: ClassInfo} for the classes of the mod's loaded jars."""
    classes = {}
    for _jar, member, data in iter_class_files_in_jars(_loaded_mod_jars(root)):
        try:
            info = parse_class(data)
        except ClassFormatError:
            continue
        classes.setdefault(info.name or member[:-6], info)
    return classes


def hook_profile(plugin, hook: str, own: set[str]) -> dict:
    """The raw counts for one hook: its body and, transitively, the plugin's own methods it calls."""
    bodies: dict[str, list] = {}
    for name, targets in zip(plugin.code_methods, plugin.method_targets):
        bodies.setdefault(name, []).extend(targets)
    seen, frontier, depth, calls = {hook}, [hook], 0, []
    while frontier and depth <= MAX_DEPTH:
        following = []
        for method in frontier:
            for owner, name in bodies.get(method, []):
                calls.append((owner, name))
                if owner == plugin.name and name in bodies and name not in seen:
                    seen.add(name)
                    following.append(name)
        if following:
            depth += 1
        frontier = following
    outside = [(owner, name) for owner, name in calls if owner != plugin.name]
    return {
        "depth": depth,
        "registration_calls": sum(1 for _, name in outside if name in REGISTRATION_CALLS),
        "mod_classes": sorted({owner for owner, _ in outside if owner in own}),
        # A registration call (addScript, addListener, ...) is counted once, above, not again as a mutation.
        "api_mutations": sorted({f"{owner}.{name}" for owner, name in outside
                                 if owner.startswith("com/fs/") and _MUTATION.match(name) and name not in REGISTRATION_CALLS}),
        "invokes": len(calls),
        "callees": sorted({f"{owner}.{name}" for owner, name in outside}),
    }


def census_mod(root: Path) -> dict:
    """One mod's row: identity, kind counts and its plugin hooks' profiles."""
    root = Path(root)
    info = read_mod_info(root) or {}
    classes = _mod_classes(root)
    row = {"id": info.get("id"), "name": info.get("name"), "kinds": kind_counts(root, classes), "plugin": None}
    plugin_name = info.get("modPlugin")
    if not isinstance(plugin_name, str) or not plugin_name.strip():
        row["plugin"] = {"status": "none"}
        return row
    internal = plugin_name.strip().replace(".", "/")
    plugin = classes.get(internal)
    if plugin is None:
        loose = root / (internal + ".java")
        row["plugin"] = {"class": plugin_name, "status": "source-only" if loose.is_file() else "not-found"}
        return row
    hooks = {hook: hook_profile(plugin, hook, set(classes) - {internal}) for hook in LIFECYCLE_HOOKS if hook in plugin.methods}
    row["plugin"] = {"class": plugin_name, "status": "measured", "hooks": hooks}
    return row


def features(profile: dict) -> int:
    """A first score of a hook: mod classes plus API mutation kinds plus registration calls. The raw counts are kept."""
    return len(profile["mod_classes"]) + len(profile["api_mutations"]) + profile["registration_calls"]


BUCKETS = ((0, "0"), (1, "1"), (2, "2-3"), (4, "4-7"), (8, "8+"))


def _bucket(n: int) -> str:
    return [label for low, label in BUCKETS if n >= low][-1]


def summarize(rows: list[dict]) -> dict:
    """Corpus aggregates: mods per kind, items per kind, plugin statuses and the per-mod busiest-hook histogram."""
    mods_with, totals = Counter(), Counter()
    for row in rows:
        for kind, n in row["kinds"].items():
            mods_with[kind] += 1
            totals[kind] += n
    statuses = Counter((row["plugin"] or {}).get("status", "none") for row in rows)
    histogram, monolithic = Counter(), 0
    for row in rows:
        hooks = (row["plugin"] or {}).get("hooks")
        if not hooks:
            continue
        busiest = max(features(p) for p in hooks.values())
        histogram[_bucket(busiest)] += 1
        monolithic += busiest >= 2
    return {"mods": len(rows), "kinds": {k: {"mods": mods_with[k], "items": totals[k]} for k in sorted(mods_with, key=lambda k: -mods_with[k])},
            "plugins": dict(statuses), "busiest_hook_features": {label: histogram[label] for _, label in BUCKETS},
            "monolithic_plugins": monolithic}


def mod_roots(corpus: Path) -> list[tuple[str, Path, str]]:
    """(folder name, mod root, "archive" or "raw") per top-level folder of `corpus` that holds a mod. An archive's working
    copy is what G2 extracts from; a raw folder is the mod itself, or the one folder below it that has mod_info.json.
    Folders starting with `_` (replaced copies, rigs) are skipped."""
    found = []
    for folder in sorted(p for p in Path(corpus).iterdir() if p.is_dir() and not p.name.startswith("_")):
        for candidate, source in ((folder / "workspace" / "working", "archive"), (folder / "working", "archive"), (folder, "raw")):
            if (candidate / "mod_info.json").is_file():
                found.append((folder.name, candidate, source))
                break
        else:
            nested = sorted(p.parent for p in folder.glob("*/mod_info.json") if p.parent.name not in ("original", "workspace"))
            if nested:
                found.append((folder.name, nested[0], "raw"))
    return found


def _identity_key(root: Path) -> tuple[str, str] | None:
    from bridgeforge.corpus.corpus_releases import version_text

    info = read_mod_info(root) or {}
    if not info.get("id"):
        return None
    return str(info["id"]).lower(), version_text(info.get("version")) or ""


def run_census(corpus: Path, write: Path | None = None, quiet: bool = False) -> dict:
    """Census every mod of `corpus` once (by id and version; an archive's working copy wins over a raw copy). With `write`,
    the result goes there and a checkpoint beside it (`<write>.partial.jsonl`) lets an interrupted run resume."""
    checkpoint_path = Path(write).with_name(Path(write).name + ".partial.jsonl") if write is not None else None
    import time

    from bridgeforge.progress import Checkpoint, report

    chosen: dict[tuple[str, str], tuple[str, Path, str]] = {}
    duplicates = []
    for folder, root, source in mod_roots(corpus):
        key = _identity_key(root)
        if key is None:
            continue
        if key in chosen:
            keep = chosen[key] if chosen[key][2] == "archive" or source == "raw" else (folder, root, source)
            duplicates.append(folder if keep is chosen[key] else chosen[key][0])
            chosen[key] = keep
        else:
            chosen[key] = (folder, root, source)
    items = sorted(chosen.values(), key=lambda item: item[0].lower())
    rows = []
    with Checkpoint(checkpoint_path, {"command": "gene census", "corpus": str(Path(corpus).resolve()),
                                      "items": [folder for folder, _, _ in items]}) as checkpoint:
        for number, (folder, root, source) in enumerate(items, 1):
            saved = checkpoint.get(folder)
            resumed, started = saved is not None, time.monotonic()
            if saved is None:
                try:
                    saved = {**census_mod(root), "folder": folder, "source": source}
                except (OSError, ValueError) as exc:
                    saved = {"id": None, "name": None, "kinds": {}, "plugin": {"status": "error", "error": str(exc)},
                             "folder": folder, "source": source}
                checkpoint.add(folder, saved)
            rows.append(saved)
            if not quiet:
                status = (saved["plugin"] or {}).get("status")
                report(number, len(items), folder, f"{sum(saved['kinds'].values())} item(s), plugin {status}",
                       None if resumed else time.monotonic() - started)
        result = {"corpus": str(Path(corpus).resolve()), "summary": summarize(rows), "duplicates_skipped": sorted(duplicates), "mods": rows}
        if write is not None:  # the checkpoint goes only once the full result is on disk
            import json

            from bridgeforge.safeio import atomic_write_text

            atomic_write_text(write, json.dumps(result, indent=2, ensure_ascii=False) + "\n", newline="")
            checkpoint.finish()
    return result


def render_summary(summary: dict) -> str:
    lines = [f"Gene census: {summary['mods']} mod(s)", "", "Kinds (mods with it / items):"]
    lines += [f"  {kind}: {row['mods']} / {row['items']}" for kind, row in summary["kinds"].items()]
    lines += ["", "Plugins: " + ", ".join(f"{status} {n}" for status, n in sorted(summary["plugins"].items())),
              "Busiest hook, features per mod (mod classes + API mutation kinds + registration calls):"]
    lines += [f"  {label}: {n}" for label, n in summary["busiest_hook_features"].items()]
    lines.append(f"Monolithic (busiest hook sets up 2 or more features): {summary['monolithic_plugins']}")
    return "\n".join(lines)


__all__ = ["CAMPAIGN_TABLES", "CODE_KINDS", "census_mod", "features", "hook_profile", "kind_counts", "mod_roots", "render_summary",
           "run_census", "summarize"]
