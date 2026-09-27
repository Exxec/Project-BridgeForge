"""`bridgeforge vendor-plan`: trace the closure of one piece of an abandoned mod for RevenantLib (ROADMAP P14 item 4).

When a mod needs one small piece (a hull mod, weapon, wing, hull or ship system) that only a large,
hard-to-revive mod provides, the piece can be copied into RevenantLib instead of reviving the whole
provider (owner decision 2026-09-25: RevenantLib collects content from mods whose authors have
vanished). Copying is only right when the closure is right: RevenantLib's `shields_formshield`
fold found `FormShieldPlugin.java`, a combat plugin that implements the shield's effect, which no
file of the hull mod itself references. A tracer that follows references alone would silently drop
it; one that takes everything nearby would silently add it.

So this only plans. It follows the references the game itself follows (CSV rows, the classes they
name, sprite/sound paths, projectile specs, variant -> hull -> built-ins, ship systems, Java imports
and same-package classes), skips what vanilla provides, and lists every other provider file or class
that mentions one of the closure's ids as SUSPECT, for a person to decide. Nothing is copied.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .scanner import _load_lenient_json_file, _parse_class_file, _read_csv_rows_lenient, iter_class_files_in_jars

SCHEMA_VERSION = 1
KINDS = ("hullmod", "weapon", "wing", "hull", "variant", "shipsystem")
_ASSET = re.compile(r"\.(png|jpg|jpeg|ogg|wav|frag|vert|json)$", re.IGNORECASE)
_CLASS_NAME = re.compile(r"^[A-Za-z_][\w$]*(?:\.[A-Za-z_][\w$]*)+$")
_IMPORT = re.compile(r"^\s*import\s+(?:static\s+)?([\w.]+)\s*;", re.MULTILINE)
_PACKAGE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.MULTILINE)
_COMMENTS = re.compile(r"/\*.*?\*/|//[^\n]*", re.DOTALL)
_TABLES = {
    "hullmod": "data/hullmods/hull_mods.csv",
    "weapon": "data/weapons/weapon_data.csv",
    "wing": "data/hulls/wing_data.csv",
    "hull": "data/hulls/ship_data.csv",
    "shipsystem": "data/shipsystems/ship_systems.csv",
}
# Files that consume ids (fit, field or list them) rather than implement them: a variant fitting the
# hull mod is a user of the piece, not a part of it.
_CONSUMER_SUFFIXES = {".variant", ".ship", ".skin", ".faction"}
_TEXT_SUFFIXES = {".java", ".json", ".csv", ".ship", ".skin", ".variant", ".wpn", ".proj", ".system", ".faction", ".txt"}


class VendorPlanError(ValueError):
    """Raised for a missing provider, a malformed --id, or a target that is not a mod folder."""


def _mod_root(path: Path) -> Path:
    path = Path(path).expanduser().resolve()
    if (path / "working" / "mod_info.json").is_file():
        return path / "working"
    if (path / "mod_info.json").is_file():
        return path
    raise VendorPlanError(f"{path} is not a mod folder (no mod_info.json) or a workspace holding working/.")


def _rows(root: Path, table: str) -> dict[str, dict[str, str]]:
    rows = {}
    for row in _read_csv_rows_lenient(root / table) or []:
        ident = (row.get("id") or "").strip()
        if ident and not ident.startswith("#"):
            rows.setdefault(ident, row)
    return rows


def _specs(root: Path, folder: str, pattern: str, key: str) -> dict[str, Path]:
    found = {}
    base = root / folder
    for path in sorted(base.rglob(pattern)) if base.is_dir() else []:
        data = _load_lenient_json_file(path)
        declared = data.get(key) if isinstance(data, dict) else None
        found.setdefault(declared if isinstance(declared, str) and declared else path.stem, path)
    return found


_FRAME = re.compile(r"^(.*?)(\d+)(\.[A-Za-z]+)$")


def _animation_frames(spec: dict, queue, key: str) -> None:
    """An animated spec names frame 0 (`...generic00.png`) plus `numFrames`; the game loads the rest.

    Evidence: thruster_fighter_sm.wpn has numFrames 5 on f_engine_sm_generic00.png, and RevenantLib's
    hand-traced closure (PROVENANCE.md, 2026-09-14) needed frames 00-04.
    """
    frames = spec.get("numFrames")
    if not isinstance(frames, int) or frames < 2:
        return
    for field, value in spec.items():
        match = _FRAME.match(value.replace("\\", "/")) if isinstance(value, str) and _ASSET.search(value) else None
        if match:
            prefix, digits, suffix = match.groups()
            for frame in range(frames):
                queue(f"{prefix}{frame:0{len(digits)}d}{suffix}", f"{key} {field} frame {frame} of numFrames {frames}")


class _Index:
    """What one mod folder defines, keyed the way the game resolves it."""

    def __init__(self, root: Path | None):
        self.root = root
        present = root is not None and root.is_dir()
        self.rows = {kind: _rows(root, table) for kind, table in _TABLES.items()} if present else {kind: {} for kind in _TABLES}
        self.descriptions = _rows(root, "data/strings/descriptions.csv") if present else {}
        self.wpn = _specs(root, "data/weapons", "*.wpn", "id") if present else {}
        self.proj = _specs(root, "data/weapons", "*.proj", "id") if present else {}
        self.ship = _specs(root, "data/hulls", "*.ship", "hullId") if present else {}
        self.skin = _specs(root, "data/hulls", "*.skin", "skinHullId") if present else {}
        self.variant = _specs(root, "data/variants", "*.variant", "variantId") if present else {}
        self.system = _specs(root, "data/shipsystems", "*.system", "id") if present else {}
        self.sources: dict[str, Path] = {}
        self.jar_classes: dict[str, tuple[str, object]] = {}
        if present:
            # Every .java in the mod: loose scripts under data/ and a jar's own source (commonly src/),
            # so a jar class whose source ships with the mod is vendored as source.
            for source in sorted(root.rglob("*.java")):
                text = _COMMENTS.sub("", source.read_text(encoding="utf-8-sig", errors="replace"))
                package = _PACKAGE.search(text)
                self.sources[f"{package.group(1)}.{source.stem}" if package else source.stem] = source
            for jar, member, data in iter_class_files_in_jars(sorted(root.rglob("*.jar"))):
                info = _parse_class_file(data)
                if info is not None and info.this_class:
                    self.jar_classes.setdefault(info.this_class.replace("/", "."), (f"{Path(jar).name}!{member}", info))

    def defines(self, kind: str, ident: str) -> bool:
        if kind == "variant":
            return ident in self.variant
        if kind == "hull":
            return ident in self.rows["hull"] or ident in self.ship or ident in self.skin
        if kind == "weapon":
            return ident in self.rows["weapon"] or ident in self.wpn
        return ident in self.rows.get(kind, {})

    def has_file(self, relative: str) -> bool:
        return self.root is not None and (self.root / relative).is_file()


def vendor_plan(provider: Path, ids: list[str], *, target: Path | None = None, vanilla_core: Path | None = None,
                policy_path: Path | None = None) -> dict:
    root = _mod_root(provider)
    requested = []
    for item in ids:
        kind, _, ident = item.partition(":")
        if kind not in KINDS or not ident:
            raise VendorPlanError(f"--id expects kind:id with kind one of {', '.join(KINDS)}; got {item!r}")
        requested.append((kind, ident))
    info = _load_lenient_json_file(root / "mod_info.json")
    mod_id = info.get("id") if isinstance(info, dict) else None
    mod_name = info.get("name") if isinstance(info, dict) else None
    source, vanilla = _Index(root), _Index(Path(vanilla_core).expanduser().resolve() if vanilla_core else None)
    target_root = _mod_root(target) if target else None
    destination = _Index(target_root) if target_root else None

    include: dict[str, dict] = {}     # key -> entry
    missing: list[str] = []
    from_vanilla: list[str] = []
    already: list[str] = []
    closure_ids: set[tuple[str, str]] = set()
    queue: list[tuple[str, str, str]] = [("id", f"{kind}:{ident}", "requested") for kind, ident in requested]
    seen: set[tuple[str, str]] = set()

    def add(what: str, path: str, reason: str) -> None:
        include.setdefault(f"{what}:{path}", {"what": what, "path": path, "reason": reason})

    def need_id(kind: str, ident: str, why: str) -> None:
        if isinstance(ident, str) and ident.strip():
            queue.append(("id", f"{kind}:{ident.strip()}", why))

    def need_value(value: object, why: str) -> None:
        """Follow a JSON/CSV value the way the game would: asset paths and class names."""
        if isinstance(value, dict):
            for key, item in value.items():
                need_value(item, f"{why}.{key}")
        elif isinstance(value, list):
            for item in value:
                need_value(item, why)
        elif isinstance(value, str) and value.strip():
            text = value.strip().replace("\\", "/")
            if _ASSET.search(text) and "/" in text:
                queue.append(("file", text, why))
            elif _CLASS_NAME.match(text) and (text in source.sources or text in source.jar_classes):
                queue.append(("class", text, why))

    def row_values(kind: str, row: dict[str, str], why: str) -> None:
        for column, value in row.items():
            if column and value:
                need_value(value, f"{why} column '{column}'")

    while queue:
        what, key, why = queue.pop(0)
        if (what, key) in seen:
            continue
        seen.add((what, key))
        if what == "file":
            if source.has_file(key):
                add("file", key, why)
            elif vanilla.has_file(key):
                from_vanilla.append(f"file {key}")
            else:
                missing.append(f"file {key} ({why})")
            continue
        if what == "class":
            if key in source.sources and key in source.jar_classes:
                member, _info = source.jar_classes[key]
                why = f"{why}; source of {member}"
            if key in source.sources:
                path = source.sources[key]
                add("file", path.relative_to(root).as_posix(), f"class {key} ({why})")
                text = _COMMENTS.sub("", path.read_text(encoding="utf-8-sig", errors="replace"))
                for imported in _IMPORT.findall(text):
                    if imported in source.sources or imported in source.jar_classes:
                        queue.append(("class", imported, f"imported by {key}"))
                package = key.rsplit(".", 1)[0]
                for other in list(source.sources) + list(source.jar_classes):
                    if other != key and other.rsplit(".", 1)[0] == package and re.search(rf"\b{re.escape(other.rsplit('.', 1)[1])}\b", text):
                        queue.append(("class", other, f"same-package use in {key}"))
                for literal in re.findall(r'"([^"\n]+)"', text):
                    need_value(literal, f"string in {key}")
            elif key in source.jar_classes:
                member, class_info = source.jar_classes[key]
                add("jar-class", member, f"class {key} ({why}); compiled only, no loose source in the mod: RevenantLib builds from source, so its source must be found or decompiled")
                # Types named only in field/method descriptors (a field of type Listener) are no
                # CONSTANT_Class entry, so read them from the descriptors too.
                descriptors = [desc for _name, desc, *_rest in list(class_info.methods) + list(class_info.fields or [])]
                named = {match for desc in descriptors for match in re.findall(r"L([\w/$]+);", desc)}
                for referenced in sorted(set(class_info.referenced_classes) | named):
                    dotted = referenced.replace("/", ".")
                    if dotted != key and (dotted in source.sources or dotted in source.jar_classes):
                        queue.append(("class", dotted, f"referenced by {key}"))
                for literal in sorted(class_info.string_constants or ()):
                    need_value(literal, f"string in {key}")
            else:
                missing.append(f"class {key} ({why})")
            continue
        kind, ident = key.split(":", 1)
        if not source.defines(kind, ident):
            if vanilla.defines(kind, ident):
                from_vanilla.append(key)
            else:
                missing.append(f"{key} ({why})")
            continue
        closure_ids.add((kind, ident))
        if destination is not None and destination.defines(kind, ident):
            already.append(key)
        table = _TABLES.get(kind)
        row = source.rows.get(kind, {}).get(ident)
        if row is not None:
            add("csv-row", f"{table} [{ident}]", why)
            row_values(kind, row, f"{key} row")
            if kind == "wing":
                need_id("variant", row.get("variant", ""), f"{key} row column 'variant'")
            if kind == "hull":
                need_id("shipsystem", row.get("system id", ""), f"{key} row column 'system id'")
        if ident in source.descriptions:
            add("csv-row", f"data/strings/descriptions.csv [{ident}]", f"{key} description")
        spec_path = {"weapon": source.wpn, "variant": source.variant, "shipsystem": source.system}.get(kind, {}).get(ident)
        if kind == "hull":
            spec_path = source.ship.get(ident) or source.skin.get(ident)
        if spec_path is not None:
            add("file", spec_path.relative_to(root).as_posix(), why if row is None else f"{key} spec")
            spec = _load_lenient_json_file(spec_path)
            if isinstance(spec, dict):
                need_value(spec, f"{key} spec")
                _animation_frames(spec, lambda path, reason: queue.append(("file", path, reason)), key)
                if kind == "weapon" and isinstance(spec.get("projectileSpecId"), str):
                    proj = source.proj.get(spec["projectileSpecId"])
                    if proj is not None:
                        add("file", proj.relative_to(root).as_posix(), f"{key} projectileSpecId")
                        need_value(_load_lenient_json_file(proj), f"{key} projectile")
                if kind == "hull":
                    need_id("hull", spec.get("baseHullId", ""), f"{key} skin baseHullId")
                    for ident_ in spec.get("builtInMods") or []:
                        need_id("hullmod", ident_, f"{key} builtInMods")
                    for ident_ in (spec.get("builtInWeapons") or {}).values() if isinstance(spec.get("builtInWeapons"), dict) else []:
                        need_id("weapon", ident_, f"{key} builtInWeapons")
                    for ident_ in spec.get("builtInWings") or []:
                        need_id("wing", ident_, f"{key} builtInWings")
                if kind == "variant":
                    need_id("hull", spec.get("hullId", ""), f"{key} hullId")
                    for field in ("hullMods", "permaMods", "sMods"):
                        for ident_ in spec.get(field) or []:
                            need_id("hullmod", ident_, f"{key} {field}")
                    for ident_ in spec.get("wings") or []:
                        need_id("wing", ident_, f"{key} wings")
                    for group in spec.get("weaponGroups") or []:
                        for ident_ in (group.get("weapons") or {}).values() if isinstance(group, dict) and isinstance(group.get("weapons"), dict) else []:
                            need_id("weapon", ident_, f"{key} weaponGroups")
        if row is None and spec_path is None:
            missing.append(f"{key}: defined by a file this tracer does not read ({why})")

    included_files = {entry["path"] for entry in include.values() if entry["what"] == "file"}
    included_classes = {name for name, path in source.sources.items() if path.relative_to(root).as_posix() in included_files}
    included_classes |= {name for name, (member, _) in source.jar_classes.items() if f"jar-class:{member}" in include}
    suspects = []
    used_by = []
    needles = sorted({ident for _kind, ident in closure_ids}, key=len, reverse=True)
    tables = set(_TABLES.values()) | {"data/strings/descriptions.csv"}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if not path.is_file() or path.suffix.lower() not in _TEXT_SUFFIXES or relative in included_files or relative in tables or relative == "mod_info.json":
            continue
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        if path.suffix.lower() == ".java":
            text = _COMMENTS.sub("", text)  # a comment naming the id is not code that uses it
        hits = [needle for needle in needles if needle in text]
        if hits and path.suffix.lower() in _CONSUMER_SUFFIXES:
            used_by.append({"path": relative, "mentions": hits})
        elif hits:
            suspects.append({"path": relative, "mentions": hits, "reason": "mentions a closure id but nothing in the closure references this file: decide whether it is part of the piece (it may implement the piece's effect, as FormShieldPlugin did)"})
    for name, (member, class_info) in sorted(source.jar_classes.items()):
        if name in included_classes:
            continue
        hits = [needle for needle in needles if any(needle in constant for constant in class_info.string_constants or ())]
        if hits:
            suspects.append({"path": member, "mentions": hits, "reason": "compiled class whose string constants mention a closure id; nothing in the closure references it"})

    collisions = []
    if destination is not None and target_root is not None:
        for entry in include.values():
            if entry["what"] == "file" and (target_root / entry["path"]).is_file():
                same = (target_root / entry["path"]).read_bytes() == (root / entry["path"]).read_bytes()
                collisions.append({"path": entry["path"], "identical": same})

    from .substitutes import revival_licence

    return {
        "schema_version": SCHEMA_VERSION, "mode": "VENDOR_PLAN", "provider": str(root), "provider_mod_id": mod_id,
        "requested": [f"{kind}:{ident}" for kind, ident in requested], "target": str(target_root) if target_root else None,
        "closure_ids": sorted(f"{kind}:{ident}" for kind, ident in closure_ids),
        "include": sorted(include.values(), key=lambda entry: (entry["what"], entry["path"])),
        "suspects": suspects, "used_by": used_by, "missing": missing, "provided_by_vanilla": sorted(set(from_vanilla)),
        "already_in_target": sorted(set(already)), "target_collisions": sorted(collisions, key=lambda entry: entry["path"]),
        "licence": revival_licence(mod_id, mod_name, policy_path),
        "note": "A plan only: nothing is copied. Resolve every SUSPECT (part of the piece, or not) and every MISSING entry before folding into RevenantLib; record the decision in its PROVENANCE.md.",
    }


def render(plan: dict) -> str:
    lines = [f"VENDOR_PLAN {', '.join(plan['requested'])} from {plan['provider_mod_id']} ({plan['provider']})",
             f"  licence: {plan['licence']['decision']}" + (f" ({plan['licence']['reason']})" if plan["licence"].get("reason") else "")]
    lines.append(f"  closure ids: {', '.join(plan['closure_ids']) or 'none'}")
    for entry in plan["include"]:
        lines.append(f"  INCLUDE {entry['what']} {entry['path']}  <- {entry['reason']}")
    for entry in plan["suspects"]:
        lines.append(f"  SUSPECT {entry['path']} (mentions {', '.join(entry['mentions'])})")
    for entry in plan.get("used_by", []):
        lines.append(f"  used by {entry['path']} (not part of the piece)")
    for item in plan["missing"]:
        lines.append(f"  MISSING {item}")
    for item in plan["provided_by_vanilla"]:
        lines.append(f"  vanilla provides {item}")
    for item in plan["already_in_target"]:
        lines.append(f"  ALREADY IN TARGET {item}")
    for entry in plan["target_collisions"]:
        lines.append(f"  TARGET HAS {entry['path']} ({'identical' if entry['identical'] else 'DIFFERENT bytes'})")
    return "\n".join(lines)


def dumps(plan: dict) -> str:
    return json.dumps(plan, indent=2, ensure_ascii=False)
