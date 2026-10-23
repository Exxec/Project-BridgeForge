"""`bridgeforge atlas migrations OLD NEW | --pairs-from QUEUE` (ROADMAP-3 81.2): API replacements mined from mod version pairs.

Per pair of mod folders, each class present in both (matched by class name) yields the API symbols referenced only in OLD
and only in NEW. Replacements are clustered across pairs: an old symbol is paired with a new one when they share the owning
class (1:1 inside that class), share a method/field/class simple name, or (with `--old-api/--new-api`) api-diff lists the
new one as a same-name/same-signature candidate. Output is PROPOSALS ONLY, labelled STATIC (constant pools and import
regexes, nothing is run); a rule seen in >= 3 independent mods is R4-eligible, which still needs an owner ruling.
Independent = distinct mod ids, with mods whose mod_info author matches counted as one family.
"""
from __future__ import annotations

import json
import tempfile
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import NamedTuple

from .atlas import discover_mods, mod_identity
from .atlas_census import API_PREFIX, dotted, member_symbol, qualified_uses, read_jar_classes, read_loose
from ..safeio import atomic_write_text
from ..scanner import _load_lenient_json_file, _loaded_mod_jars
from ..zipsafe import read_limited

R4_MIN_MODS = 3
EXAMPLES = 3
EXTRACT_SUFFIXES = (".java", ".jar", "mod_info.json")
Symbol = tuple[str, str]  # (kind, dotted symbol)


class Pair(NamedTuple):
    label: str
    old: Path
    new: Path
    old_version: str = ""
    new_version: str = ""


def class_symbols(root: Path) -> dict[str, dict[Symbol, str]]:
    """class name (dotted) -> {(kind, API symbol): first place seen}, from a mod's loaded jars and loose Java."""
    out: dict[str, dict[Symbol, str]] = defaultdict(dict)
    for jar in _loaded_mod_jars(root):
        for entry in read_jar_classes(root, jar, frozenset()):
            target = out[dotted(entry.name)]
            for ref in entry.refs:
                if ref.owner.startswith(API_PREFIX) and ref.name not in ("<init>", "<clinit>"):
                    target.setdefault((ref.kind, member_symbol(ref)), entry.rel)
    for item in read_loose(root):
        target = out[(item.package + "." if item.package else "") + item.rel.rsplit("/", 1)[-1].removesuffix(".java")]
        for simple, full in item.imports.items():
            if full.startswith("com.fs."):
                target.setdefault(("class", full), item.rel)
                for kind, name in qualified_uses(item, simple):
                    target.setdefault((kind, f"{full}.{name}"), item.rel)
    return out


def _split(symbol: Symbol) -> tuple[str, str]:
    """(owner, member name); a class has an empty member name."""
    kind, text = symbol
    if kind == "class":
        return text, ""
    owner, _, name = text.rpartition(".")
    return owner, name


def _simple(text: str) -> str:
    return text.rsplit(".", 1)[-1]


def _signature_compatible(entry: dict, cand_owner: str, cand_name: str) -> bool:
    from .atlas_census_report import _owner_of

    return any(_owner_of(text) == (cand_owner, cand_name) for text in entry.get("elsewhere", []))


def api_removal(catalogue: dict | None, symbol: Symbol) -> tuple[bool, set[Symbol], set[Symbol]]:
    """(removed in the new API?, all api-diff candidates, signature-compatible candidates) for an old symbol."""
    from .atlas_census_report import removed_entries

    if not catalogue:
        return True, set(), set()
    owner, member = _split(symbol)
    entries = removed_entries(catalogue, owner, member)
    candidates: set[Symbol] = set()
    compatible: set[Symbol] = set()
    for entry in entries:
        for cand_owner, cand_name in entry["candidates"]:
            candidate = (symbol[0], cand_owner if symbol[0] == "class" else f"{cand_owner}.{cand_name}")
            candidates.add(candidate)
            if symbol[0] == "class" or _signature_compatible(entry, cand_owner, cand_name):
                compatible.add(candidate)
    return bool(entries), candidates, compatible


def _group_by_owner(symbols) -> dict[str, list[Symbol]]:
    groups: dict[str, list[Symbol]] = defaultdict(list)
    for symbol in symbols:
        if symbol[0] != "class":
            groups[_split(symbol)[0]].append(symbol)
    return groups


def class_replacements(only_old: dict[Symbol, str], only_new: dict[Symbol, str], catalogue: dict | None) -> list[tuple]:
    """(old, new, kind, reason, replacement class, old example, new example) for one class's differing API references."""
    removed = {s: api_removal(catalogue, s) for s in only_old}
    olds = [s for s in only_old if removed[s][0]]
    owners_old, owners_new = _group_by_owner(olds), _group_by_owner(only_new)
    found = []
    for old in olds:
        _removed, candidates, compatible = removed[old]
        for new in only_new:
            if new[0] != old[0] or new[1] == old[1]:
                continue
            same_name = _simple(old[1]) == _simple(new[1])
            owner = _split(old)[0]
            same_owner = (old[0] != "class" and owner == _split(new)[0]
                          and len(owners_old[owner]) == 1 and len(owners_new[owner]) == 1)
            listed = new in candidates
            if not (same_name or same_owner or listed):
                continue
            reason = "api-diff" if listed else "same-name" if same_name else "same-owner"
            kind = ("pure-rename" if new in compatible else "needs-code-change") if catalogue else "unknown (no api-diff)"
            found.append((old[1], new[1], old[0], reason, kind, only_old[old], only_new[new]))
    return found


def pair_replacements(old_root: Path, new_root: Path, catalogue: dict | None) -> list[tuple]:
    old_classes, new_classes = class_symbols(old_root), class_symbols(new_root)
    found = []
    for name in sorted(old_classes.keys() & new_classes.keys()):
        old, new = old_classes[name], new_classes[name]
        only_old = {s: e for s, e in old.items() if s not in new}
        only_new = {s: e for s, e in new.items() if s not in old}
        if only_old and only_new:
            found += [(*row, name) for row in class_replacements(only_old, only_new, catalogue)]
    return found


def _identity(old: Path, new: Path) -> tuple[str, str]:
    """(mod id, author family key) of a pair; the family is the author text, or the id when none is given."""
    ident = mod_identity(new) or mod_identity(old)
    mod_id = ident[0] if ident else new.name
    for root in (new, old):
        info = _load_lenient_json_file(root / "mod_info.json")
        author = info.get("author") if isinstance(info, dict) else None
        if isinstance(author, str) and author.strip():
            return mod_id, "author:" + " ".join(author.lower().split())
    return mod_id, "id:" + mod_id


def mine(pairs: list[Pair], catalogue: dict | None = None, progress=None) -> dict:
    rules: dict[tuple[str, str], dict] = {}
    scanned = []
    for index, pair in enumerate(pairs, 1):
        mod_id, family = _identity(pair.old, pair.new)
        rows = pair_replacements(pair.old, pair.new, catalogue)
        scanned.append({"pair": pair.label, "mod": mod_id, "replacements": len(rows),
                        "old_version": pair.old_version, "new_version": pair.new_version})
        if progress:
            progress(f"[{index}/{len(pairs)}] {pair.label}: {len(rows)} replacement(s)")
        for old, new, symbol_kind, reason, compat, old_example, new_example, cls in rows:
            rule = rules.setdefault((old, new), {"old": old, "new": new, "symbol_kind": symbol_kind, "reason": reason,
                                                 "kind": compat, "mods": {}, "old_examples": [], "new_examples": []})
            rule["mods"].setdefault(mod_id, family)
            for key, example in (("old_examples", old_example), ("new_examples", new_example)):
                text = f"{mod_id}: {example} ({cls})"
                if len(rule[key]) < EXAMPLES and text not in rule[key]:
                    rule[key].append(text)
    out = []
    for rule in rules.values():
        independent = len(set(rule["mods"].values()))
        out.append({**{k: rule[k] for k in ("old", "new", "symbol_kind", "reason", "kind", "old_examples", "new_examples")},
                    "mods": sorted(rule["mods"]), "independent_mods": independent, "r4_eligible": independent >= R4_MIN_MODS})
    out.sort(key=lambda r: (-r["independent_mods"], -len(r["mods"]), r["old"], r["new"]))
    return {"label": "STATIC", "status": "PROPOSALS ONLY (never applied)", "api_diff": bool(catalogue), "pairs": scanned,
            "rules": out, "r4_eligible": sum(r["r4_eligible"] for r in out), "r4_min_mods": R4_MIN_MODS}


# ---------------------------------------------------------------- pair discovery

def _extract_zip(archive: Path, target: Path) -> None:
    root = target.resolve()
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            if info.is_dir() or not info.filename.lower().endswith(EXTRACT_SUFFIXES):
                continue
            dest = (target / info.filename).resolve()
            if root not in dest.parents:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(read_limited(z, info))


def _first_mod(folder: Path) -> Path | None:
    found = discover_mods(folder) if folder.is_dir() else []
    return found[0] if found else None


def queue_pairs(queue: Path, scratch: Path) -> list[Pair]:
    """Each workspace's original/ vs working/, and each Done/ original vs its shipped zip (extracted under `scratch`)."""
    pairs = []
    for folder in sorted(p for p in queue.iterdir() if p.is_dir() and not p.name.startswith("_")):
        old, new = _first_mod(folder / "original"), folder / "working"
        if old and (new / "mod_info.json").is_file():
            pairs.append(Pair(f"{folder.name} (original vs working)", old, new))
    done = queue.parent / "Done"
    for folder in sorted(p for p in done.iterdir() if p.is_dir()) if done.is_dir() else []:
        original = folder / "original"
        old = _first_mod(original / "extracted") or _first_mod(original)
        zips = sorted(z for z in folder.glob("*.zip") if "with-readme" not in z.name)
        if not old or not zips:
            continue
        target = scratch / folder.name
        try:
            _extract_zip(zips[-1], target)
        except (zipfile.BadZipFile, OSError):
            continue
        new = _first_mod(target)
        if new:
            pairs.append(Pair(f"{folder.name} (Done original vs shipped zip)", old, new))
    return pairs


def json_pairs(path: Path) -> list[Pair]:
    """Pairs listed in a `corpus releases` pairs.json; a pair whose folders are gone or hold no mod_info.json is an error, not skipped."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        rows = data["pairs"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError(f"{path} is not a pairs.json ({exc})") from None
    pairs = []
    for row in rows:
        old, new = Path(row["old"]), Path(row["new"])
        for folder in (old, new):
            if not (folder / "mod_info.json").is_file():
                raise ValueError(f"{path}: {folder} holds no mod_info.json (moved or deleted since the inventory?)")
        pairs.append(Pair(str(row["label"]), old, new, str(row.get("old_version", "")), str(row.get("new_version", ""))))
    return pairs


def queue_originals(queue: Path) -> list[Path]:
    originals = [m for m in (_first_mod(f / "original") for f in sorted(queue.iterdir())
                             if f.is_dir() and not f.name.startswith("_")) if m]
    done = queue.parent / "Done"
    for folder in sorted(p for p in done.iterdir() if p.is_dir()) if done.is_dir() else []:
        old = _first_mod(folder / "original" / "extracted") or _first_mod(folder / "original")
        if old:
            originals.append(old)
    return originals


def installed_pairs(queue: Path, installed: Path) -> list[Pair]:
    """Queue/Done originals paired with the INSTALLED mod of the same id when the version strings differ (upstream evolution)."""
    by_id = {}
    for root in discover_mods(installed):
        ident = mod_identity(root)
        if ident:
            by_id.setdefault(ident[0], (root, ident[1]))
    pairs, seen = [], set()
    for original in queue_originals(queue):
        ident = mod_identity(original)
        found = by_id.get(ident[0]) if ident else None
        if ident and found and found[1] != ident[1] and (ident[0], ident[1]) not in seen:
            seen.add((ident[0], ident[1]))
            pairs.append(Pair(f"{ident[0]} {ident[1]} -> installed {found[1]}", original, found[0], ident[1], found[1]))
    return pairs


# ---------------------------------------------------------------- output

def migrations_text(data: dict, top: int = 25) -> str:
    lines = [f"atlas migrations (STATIC, {data['status']}): {len(data['pairs'])} pair(s), {len(data['rules'])} candidate rule(s), "
             f"{data['r4_eligible']} R4-eligible (>= {data['r4_min_mods']} independent mods)"]
    if not data["api_diff"]:
        lines.append("  no --old-api/--new-api given: every differing symbol is a candidate and pure-rename cannot be judged")
    for rule in data["rules"][:top]:
        flag = " [R4-eligible]" if rule["r4_eligible"] else ""
        lines.append(f"  {rule['old']} -> {rule['new']} [{rule['kind']}, {rule['reason']}]: {rule['independent_mods']} independent mod(s){flag}")
        lines.append(f"      old: {'; '.join(rule['old_examples'])}")
        lines.append(f"      new: {'; '.join(rule['new_examples'])}")
    return "\n".join(lines)


def migrations_markdown(data: dict, top: int = 100) -> str:
    lines = ["# Migration candidates (STATIC, proposals only)", "",
             f"{len(data['pairs'])} pair(s); {len(data['rules'])} candidate rule(s); {data['r4_eligible']} R4-eligible "
             f"(>= {data['r4_min_mods']} independent mods). Nothing here is applied; R4 needs an owner ruling.", "",
             "| old | new | kind | independent mods | R4 | example (old) | example (new) |", "|---|---|---|---|---|---|---|"]
    for rule in data["rules"][:top]:
        old_cell = "<br>".join(e.replace("|", "\\|") for e in rule["old_examples"])
        new_cell = "<br>".join(e.replace("|", "\\|") for e in rule["new_examples"])
        lines.append(f"| `{rule['old']}` | `{rule['new']}` | {rule['kind']} ({rule['reason']}) | {rule['independent_mods']} "
                     f"({', '.join(rule['mods'][:6])}) | {'yes' if rule['r4_eligible'] else 'no'} | {old_cell} | {new_cell} |")
    return "\n".join(lines) + "\n"


NL = chr(10)


def write_outputs(data: dict, folder: Path, stem: str = "MIGRATIONS") -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    md, js = folder / f"{stem}.md", folder / f"{stem}.json"
    atomic_write_text(md, migrations_markdown(data))
    atomic_write_text(js, json.dumps(data, indent=2, ensure_ascii=False) + NL)
    return [md, js]


def run_migrations(args, emit, say) -> int:
    from ..api_diff import diff_api_jars

    if bool(args.old_api) != bool(args.new_api):
        raise ValueError("give both --old-api and --new-api, or neither")
    catalogue = diff_api_jars(args.old_api, args.new_api) if args.old_api else None
    with tempfile.TemporaryDirectory(prefix="bf-migrations-") as scratch:
        pairs = [Pair(f"{args.old.name} -> {args.new.name}", args.old, args.new)] if args.old and args.new else []
        if args.pairs_from:
            pairs += queue_pairs(args.pairs_from, Path(scratch))
        if args.pairs_json:
            pairs += json_pairs(args.pairs_json)
        if args.pairs_installed:
            if not args.installed:
                raise ValueError("--pairs-installed needs --installed MODS_DIR")
            pairs += installed_pairs(args.pairs_installed, args.installed)
        if not pairs:
            raise ValueError("give OLD_DIR NEW_DIR, --pairs-from QUEUE, --pairs-json FILE or --pairs-installed QUEUE (no pairs found)")
        data = mine(pairs, catalogue, None if args.quiet else say)
    if args.write:
        for path in write_outputs(data, args.write, args.stem):
            say(f"wrote {path}")
    emit(args, data, migrations_text(data, args.top))
    return 0
