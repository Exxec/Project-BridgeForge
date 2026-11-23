"""94.G3 slice 2a: the allele denominator (docs/GENE_BANK_DESIGN.md, "Slice 2").

"The bank holds every allele of the pilots in the corpus" needs a denominator: every copy of a mod in the corpus that
defines one of the banked anchors. `gene bank alleles CORPUS --out PLAN` writes it and puts nothing (advisor 2026-11-23: a
`sources.json` line is never removed, so the first pass only plans).

- **Roots.** Every folder under the corpus holding `mod_info.json`. In a workspace (a folder with `working/`) only `working/`
  and the mod roots under `original/` count: its `genes/`, `scratch/` and `reports/` hold BridgeForge's own copies (proof
  carriers), not alleles. `_replaced-*` archives and `original/` copies are kept: they are the likeliest alleles. A zip is
  read only for its `mod_info.json` (through zipsafe) and listed, never extracted or described.
- **Defines.** The describer's own tables: `vendor_plan._Index.defines` for the content kinds, the `.faction` files for a
  faction, settings.json's `plugins` map for a combat plugin, customStarts.json's `starts` for a custom start, and the
  generator classes for a star system. A copy describe would refuse (two starts in one file, two generators) still defines
  the id: its refusal is recorded later, with the reason.
- **Mentions.** Misses are the dangerous error, so every text file and jar class of each root is also searched for each id
  as a whole word; a root naming an id it does not define is listed as "mention only", and what could not be read is
  listed too.

The plan names mod folders, so it stays on the machine that made it (Eridani Combine is LOCAL_ONLY); the roadmap records
counts only.
"""
from __future__ import annotations

import json
import os
import re
import time
import zipfile
from pathlib import Path

PLAN_SCHEMA = "bridgeforge-gene-alleles"
PLAN_VERSION = 1
MOD_INFO = "mod_info.json"
UNREAD_ARCHIVES = (".7z", ".rar", ".tar", ".gz", ".bz2", ".xz")
_TEXT = {".csv", ".json", ".ship", ".skin", ".variant", ".wpn", ".proj", ".system", ".faction", ".java", ".txt", ".kt"}
_MAX_TEXT = 16 * 1024 * 1024
_MAX_INFO = 256 * 1024
DEFINED_KINDS = ("hull", "weapon", "wing", "hullmod", "shipsystem", "variant", "faction", "combat-plugin", "custom-start",
                 "star-system")


class AllelesError(ValueError):
    """Raised for a corpus or bank that cannot be planned from."""


def _is_workspace(folder: Path) -> bool:
    return (folder / "working").is_dir()


def _rel(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def corpus_roots(corpus: Path, excludes: tuple[str, ...] = ()) -> tuple[list[tuple[Path, str]], list[Path], list[Path]]:
    """([(mod root, "working" | "archive" | "original")], zips, unread archives) under `corpus`. A workspace's working copy is
    "archive" when the corpus is an archive folder (`Done/`), else "working"; every other root is "original". Top-level
    folders matching an `excludes` glob are skipped (a rig's `mods/` holds installed copies, not alleles)."""
    corpus = Path(corpus)
    working_kind = "archive" if corpus.name.lower() == "done" else "working"
    roots: list[tuple[Path, str]] = []
    zips: list[Path] = []
    unread: list[Path] = []

    def visit(folder: Path) -> None:
        if (folder / MOD_INFO).is_file():
            roots.append((folder, "original"))
            return
        if _is_workspace(folder):
            if (folder / "working" / MOD_INFO).is_file():
                roots.append((folder / "working", working_kind))
            if (folder / "original").is_dir():
                visit(folder / "original")
            return
        try:
            entries = sorted(folder.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            unread.append(folder)
            return
        for entry in entries:
            if entry.name.startswith(".") or entry.name == "__pycache__":
                continue
            if folder == corpus and any(Path(entry.name).match(glob) for glob in excludes):
                continue
            if entry.is_dir() and not entry.is_symlink() and not entry.is_junction():  # a rig's starsector-core is a junction
                visit(entry)
            elif entry.suffix.lower() == ".zip":
                zips.append(entry)
            elif entry.suffix.lower() in UNREAD_ARCHIVES:
                unread.append(entry)

    visit(corpus)
    return roots, zips, unread


def zip_mod_infos(path: Path) -> list[dict]:
    """The `mod_info.json` files a zip holds at its root or one or two folders down: [{entry, id, version}]."""
    from bridgeforge.genome.gene import _version_text
    from bridgeforge.scan.scan_json import _parse_json
    from bridgeforge.zipsafe import read_limited

    found = []
    with zipfile.ZipFile(path) as archive:
        for name in sorted(archive.namelist()):
            if name.rsplit("/", 1)[-1].lower() != MOD_INFO or name.count("/") > 2:
                continue
            try:
                data, _ = _parse_json(read_limited(archive, name, _MAX_INFO).decode("utf-8-sig", errors="replace"))
            except ValueError:
                data = None
            info = data if isinstance(data, dict) else {}
            found.append({"entry": name, "id": info.get("id"), "version": _version_text(info.get("version"))})
    return found


class RootIndex:
    """What one mod root defines for the kinds the bank holds, built once per root by the describer's own tables."""

    def __init__(self, root: Path, kinds: set[str]):
        from bridgeforge.vendor_plan import _Index

        self.root = root
        content = kinds & {"hull", "weapon", "wing", "hullmod", "shipsystem", "variant"}
        self.content = _Index(root) if content else None
        self.factions: set[str] = set()
        if "faction" in kinds:
            from bridgeforge.genome.campaign import _CampaignIndex

            self.factions = set(_CampaignIndex(root).factions)
        self.plugins: set[str] = set()
        if "combat-plugin" in kinds:
            from bridgeforge.genome.closure import _settings

            plugins = _settings(root).get("plugins")
            self.plugins = {k for k, v in plugins.items() if isinstance(v, str) and v.strip()} if isinstance(plugins, dict) else set()
        self.starts: set[str] = set()
        if "custom-start" in kinds:
            self.starts = _custom_start_ids(root)
        self.systems: set[str] = set()
        if "star-system" in kinds:
            from bridgeforge.genome.campaign import star_system_generators

            self.systems = {name for name in star_system_generators(root) if name}

    def defines(self, anchor: str) -> bool:
        kind, _, ident = anchor.partition(":")
        if kind in ("hull", "weapon", "wing", "hullmod", "shipsystem", "variant"):
            return self.content is not None and self.content.defines(kind, ident)
        return ident in {"faction": self.factions, "combat-plugin": self.plugins, "custom-start": self.starts,
                         "star-system": self.systems}.get(kind, set())


def _custom_start_ids(root: Path) -> set[str]:
    """Every start id customStarts.json lists, however many: describe refuses a file of several, which is a refusal to
    record, not an absence."""
    from bridgeforge.genome.gene import CUSTOM_STARTS_FILE
    from bridgeforge.scan.scanner import _load_lenient_json_file

    path = root / CUSTOM_STARTS_FILE
    data = _load_lenient_json_file(path) if path.is_file() else None
    starts = data.get("starts") if isinstance(data, dict) else None
    return {s["id"] for s in starts or [] if isinstance(s, dict) and isinstance(s.get("id"), str)} if isinstance(starts, list) else set()


def _id_pattern(anchors: list[str]) -> re.Pattern[bytes]:
    idents = sorted({a.partition(":")[2] for a in anchors}, key=lambda s: (-len(s), s))
    return re.compile(rb"(?<![A-Za-z0-9_])(" + b"|".join(re.escape(i.encode("utf-8")) for i in idents) + rb")(?![A-Za-z0-9_])")


def mentioned_ids(root: Path, pattern: re.Pattern[bytes]) -> tuple[set[str], list[str]]:
    """(ids named as a whole word in any text file or jar class under `root`, what could not be read)."""
    from bridgeforge.zipsafe import MAX_CLASS_BYTES, read_limited

    found: set[str] = set()
    unread: list[str] = []
    for folder, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d != "__pycache__")
        for name in sorted(files):
            path = Path(folder) / name
            suffix = path.suffix.lower()
            try:
                if suffix in _TEXT:
                    if path.stat().st_size > _MAX_TEXT:
                        unread.append(_rel(path, root) + " (too large)")
                        continue
                    found.update(m.decode("utf-8") for m in pattern.findall(path.read_bytes()))
                elif suffix == ".jar":
                    with zipfile.ZipFile(path) as jar:
                        for entry in jar.namelist():
                            if entry.endswith(".class") or Path(entry).suffix.lower() in _TEXT:
                                found.update(m.decode("utf-8") for m in pattern.findall(read_limited(jar, entry, MAX_CLASS_BYTES)))
            except (OSError, ValueError, zipfile.BadZipFile) as exc:
                unread.append(f"{_rel(path, root)} ({type(exc).__name__})")
    return found, unread


def scan_root(root: Path, anchors: list[str], pattern: re.Pattern[bytes]) -> dict:
    """{defines, mentions, unreadable, error} of one root. Anything other than an unreadable file is an `error`: the
    acceptance needs none left unexplained (advisor 2026-11-23)."""
    kinds = {a.partition(":")[0] for a in anchors}
    try:
        index = RootIndex(root, kinds)
        defines = [a for a in anchors if index.defines(a)]
        named, unreadable = mentioned_ids(root, pattern)
    except Exception as exc:  # recorded per root and counted; the walk goes on
        return {"defines": [], "mentions": [], "unreadable": [], "error": f"{type(exc).__name__}: {exc}"}
    mentions = [a for a in anchors if a.partition(":")[2] in named and a not in defines]
    return {"defines": defines, "mentions": mentions, "unreadable": unreadable, "error": None}


def bank_anchors(bank: Path | None = None) -> tuple[list[str], list[str]]:
    """(pilot anchors: the bank's sources.json lines, every anchor of a current record), each sorted."""
    from bridgeforge.genome.bank import Bank

    target = Bank(bank)
    records = target.records()
    pilots = sorted({s["anchor"] for s in target.sources()})
    if not pilots:
        raise AllelesError(f"{target.root} holds no sources: bank the pilots first")
    anchors = sorted({records[rid]["anchor"] for rid in target.current_ids() if rid in records} | set(pilots))
    unknown = sorted({a.partition(":")[0] for a in anchors} - set(DEFINED_KINDS))
    if unknown:
        raise AllelesError(f"no corpus test for anchor kind(s) {', '.join(unknown)}")
    return pilots, anchors


def _zip_rows(zips: list[Path], folders: set[tuple[str, str]], base: Path) -> list[dict]:
    rows = []
    for path in zips:
        try:
            infos = zip_mod_infos(path)
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            rows.append({"path": _rel(path, base), "mods": [], "state": f"unreadable ({type(exc).__name__})"})
            continue
        keys = [(str(i["id"]).lower(), i["version"] or "") for i in infos if i["id"]]
        state = ("packaged copy of a folder row" if keys and all(k in folders for k in keys)
                 else "archive only, not described" if infos else "no mod")
        rows.append({"path": _rel(path, base), "mods": infos, "state": state})
    return rows


def plan(corpus: Path, *, bank: Path | None = None, excludes: tuple[str, ...] = (), checkpoint_path: Path | None = None,
         quiet: bool = False, base: Path | None = None) -> dict:
    """The denominator over `corpus`: per root, the banked anchors it defines and mentions; per anchor, the roots."""
    from bridgeforge.genome.gene import _version_text
    from bridgeforge.mod_files import read_mod_info
    from bridgeforge.paths import data_root
    from bridgeforge.progress import Checkpoint, report

    base = Path(base or data_root())
    if not Path(corpus).is_dir():
        raise AllelesError(f"{corpus} is not a folder")
    if not Path(corpus).resolve().is_relative_to(base.resolve()):
        raise AllelesError(f"{corpus} is not under the data root, so its copies could not be banked by relative path")
    pilots, anchors = bank_anchors(bank)
    pattern = _id_pattern(anchors)
    roots, zips, unread = corpus_roots(Path(corpus), excludes)
    head = {"command": "gene bank alleles", "corpus": _rel(Path(corpus), base), "anchors": anchors, "excludes": list(excludes),
            "roots": [_rel(root, base) for root, _ in roots]}
    rows = []
    with Checkpoint(checkpoint_path, head) as checkpoint:
        for number, (root, folder) in enumerate(roots, 1):
            key = _rel(root, base)
            saved, started = checkpoint.get(key), time.monotonic()
            if saved is None:
                info = read_mod_info(root) or {}
                saved = {"path": key, "folder": folder, "mod_id": info.get("id"), "mod_version": _version_text(info.get("version")),
                         **scan_root(root, anchors, pattern)}
                checkpoint.add(key, saved)
            rows.append(saved)
            if not quiet:
                detail = f"error: {saved['error']}" if saved["error"] else f"defines {len(saved['defines'])}, mentions {len(saved['mentions'])}"
                report(number, len(roots), key, detail, time.monotonic() - started)
        folders = {(str(r["mod_id"]).lower(), r["mod_version"] or "") for r in rows if r["mod_id"]}
        result = {"schema": PLAN_SCHEMA, "schema_version": PLAN_VERSION, **{k: head[k] for k in ("corpus", "excludes")},
                  "pilot_anchors": pilots, "anchors": anchors, "roots": rows, "zips": _zip_rows(zips, folders, base),
                  "unread_archives": [_rel(p, base) for p in unread], "summary": summarize(rows, pilots, anchors)}
    return result


def summarize(rows: list[dict], pilots: list[str], anchors: list[str]) -> dict:
    """Per anchor: defining roots, distinct (mod id, version) among them, mention-only roots; plus totals."""
    per_anchor = {}
    for anchor in anchors:
        defining = [r for r in rows if anchor in r["defines"]]
        per_anchor[anchor] = {"roots": len(defining), "mod_versions": len({(r["mod_id"], r["mod_version"]) for r in defining}),
                              "mod_ids": len({r["mod_id"] for r in defining}),
                              "mention_only": sum(1 for r in rows if anchor in r["mentions"]), "pilot": anchor in pilots}
    return {"roots": len(rows), "errors": sum(1 for r in rows if r["error"]),
            "unreadable_files": sum(len(r["unreadable"]) for r in rows),
            "roots_defining_a_pilot": sum(1 for r in rows if set(r["defines"]) & set(pilots)),
            "roots_defining_any": sum(1 for r in rows if r["defines"]), "anchors": per_anchor}


def write_plan(result: dict, out: Path) -> None:
    from bridgeforge.safeio import atomic_write_text

    Path(out).parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out, json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n", newline="")


def run_alleles_cli(args) -> int:
    import sys

    out = Path(args.out)
    checkpoint = out.with_name(out.name + ".partial.jsonl")
    try:
        result = plan(args.corpus, bank=args.bank, excludes=tuple(args.exclude or ()), checkpoint_path=checkpoint, quiet=args.quiet)
    except (AllelesError, OSError, ValueError) as exc:
        print(f"bridgeforge: {exc}", file=sys.stderr)
        return 2
    write_plan(result, out)
    if checkpoint.is_file():
        checkpoint.unlink()  # the checkpoint goes only once the full plan is on disk
    summary = result["summary"]
    print(f"{summary['roots']} root(s); {summary['roots_defining_a_pilot']} define a pilot anchor, {summary['roots_defining_any']} "
          f"any banked anchor; {summary['errors']} error(s), {summary['unreadable_files']} unreadable file(s); "
          f"{len(result['zips'])} zip(s), {len(result['unread_archives'])} unread archive(s)")
    for anchor in result["pilot_anchors"]:
        row = summary["anchors"][anchor]
        print(f"  {anchor}: {row['roots']} root(s), {row['mod_versions']} mod version(s), {row['mention_only']} mention only")
    return 1 if summary["errors"] else 0


__all__ = ["AllelesError", "DEFINED_KINDS", "RootIndex", "bank_anchors", "corpus_roots", "mentioned_ids", "plan",
           "run_alleles_cli", "scan_root", "summarize", "zip_mod_infos"]
