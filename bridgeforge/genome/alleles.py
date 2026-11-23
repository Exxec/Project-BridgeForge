"""94.G3 slice 2a: the allele denominator (docs/GENE_BANK_DESIGN.md, "Slice 2").

"The bank holds every allele of the pilots in the corpus" needs a denominator: every copy of a mod in the corpus that
defines one of the banked anchors. `gene bank alleles CORPUS --out PLAN` writes it and puts nothing (advisor 2026-11-23: a
`sources.json` line is never removed, so the first pass only plans).

- **Roots.** Every folder under the corpus holding `mod_info.json`, by the layouts BridgeForge writes:
  - an archive (`ARCHIVE_NOTE.md`, written by `archive`): its `<Mod>/` copy is the archived revival (`archive`), the roots
    under `original/` are the author's release (`original`), and `alt-original-descriptions/` is a copy BridgeForge made
    with the author's descriptions, listed as skipped;
  - a workspace (a folder with `working/`): `working/` (`working`, or `archive` in `Done/`) and the roots under
    `original/`; every other copy inside it (`genes/` proof carriers, `scratch/`) is BridgeForge's own, listed as skipped;
  - any other folder holding `mod_info.json` is an author's copy (`original`). `_replaced-*` archives are kept: they are
    the likeliest alleles.
  A zip is read only for its `mod_info.json` (through zipsafe) and listed. It counts as a packaged copy only when its
  `mod_info.json` bytes equal a scanned copy's (review 2026-11-23: a revival keeps the author's id and version).
- **Defines.** The describer's own tables: `vendor_plan._Index.defines` for the content kinds, the `.faction` files for a
  faction, settings.json's `plugins` map for a combat plugin, customStarts.json's `starts` for a custom start, and the
  generator classes for a star system. A copy describe would refuse (two starts in one file, two generators) still defines
  the id: its refusal is recorded later, with the reason.
- **Mentions.** Misses are the dangerous error, so every text file and jar class of each root is also searched for each id
  as a whole word; a root naming an id it does not define is listed as "mention only". In a class file the byte before a
  constant is its length, which may be a letter, so only the end of the id is checked there. What could not be read is
  listed, per file or jar entry.

Nothing is dropped in silence: skipped copies, unread archives and errors are all in the plan. The plan names mod folders,
so it stays on the machine that made it (Eridani Combine is LOCAL_ONLY); the roadmap records counts only.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import zipfile
from pathlib import Path

PLAN_SCHEMA = "bridgeforge-gene-alleles"
PLAN_VERSION = 1
MOD_INFO = "mod_info.json"
ARCHIVE_NOTE = "ARCHIVE_NOTE.md"
ALT_DESCRIPTIONS = "alt-original-descriptions"
UNREAD_ARCHIVES = (".7z", ".rar", ".tar", ".gz", ".bz2", ".xz")
_TEXT = {".csv", ".json", ".ship", ".skin", ".variant", ".wpn", ".proj", ".system", ".faction", ".java", ".txt", ".kt"}
_MAX_TEXT = 16 * 1024 * 1024
_MAX_INFO = 256 * 1024
DEFINED_KINDS = ("hull", "weapon", "wing", "hullmod", "shipsystem", "variant", "faction", "combat-plugin", "custom-start",
                 "star-system")


class AllelesError(ValueError):
    """Raised for a corpus or bank that cannot be planned from."""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _rel(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _is_dir(path: Path) -> bool:
    return path.is_dir() and not path.is_symlink() and not path.is_junction()  # a rig's starsector-core is a junction


class _Walk:
    """The corpus walk of `corpus_roots`: roots, zips, unread archives and folders, and skipped copies with the reason."""

    def __init__(self, corpus: Path, excludes: tuple[str, ...]):
        self.corpus, self.excludes = corpus, excludes
        self.working_kind = "archive" if corpus.name.lower() == "done" else "working"
        self.roots: list[tuple[Path, str]] = []
        self.zips: list[Path] = []
        self.unread: list[Path] = []
        self.skipped: list[tuple[Path, str]] = []

    def children(self, folder: Path) -> list[Path]:
        try:
            return sorted((p for p in folder.iterdir() if not p.name.startswith(".") and p.name != "__pycache__"),
                          key=lambda p: p.name.lower())
        except OSError:
            self.unread.append(folder)
            return []

    def file(self, entry: Path) -> None:
        if entry.suffix.lower() == ".zip":
            self.zips.append(entry)
        elif entry.suffix.lower() in UNREAD_ARCHIVES:
            self.unread.append(entry)

    def skip_copies(self, folder: Path, reason: str) -> None:
        """List every mod copy under `folder` as skipped, so a copy left out is never left out in silence."""
        if (folder / MOD_INFO).is_file():
            self.skipped.append((folder, reason))
            return
        for entry in self.children(folder):
            if _is_dir(entry):
                self.skip_copies(entry, reason)

    def visit(self, folder: Path) -> None:
        if (folder / MOD_INFO).is_file():
            self.roots.append((folder, "original"))
        elif (folder / ARCHIVE_NOTE).is_file():
            self.archive(folder)
        elif (folder / "working").is_dir():
            self.workspace(folder)
        else:
            for entry in self.children(folder):
                if folder == self.corpus and any(Path(entry.name).match(glob) for glob in self.excludes):
                    continue
                if _is_dir(entry):
                    self.visit(entry)
                else:
                    self.file(entry)

    def archive(self, folder: Path) -> None:
        """archive.py's layout: `<Mod>/` the revival, `original/`, `alt-original-descriptions/<Mod>/`, `workspace/` reports."""
        for entry in self.children(folder):
            if not _is_dir(entry):
                self.file(entry)
            elif entry.name == ALT_DESCRIPTIONS:
                self.skip_copies(entry, "a copy BridgeForge made of the revival with the author's descriptions")
            elif (entry / MOD_INFO).is_file():
                self.roots.append((entry, "archive"))
            else:
                self.visit(entry)

    def workspace(self, folder: Path) -> None:
        for entry in self.children(folder):
            if not _is_dir(entry):
                self.file(entry)
            elif entry.name == "working":
                if (entry / MOD_INFO).is_file():
                    self.roots.append((entry, self.working_kind))
                else:
                    self.skipped.append((entry, "a workspace's working/ with no mod_info.json"))
            elif entry.name == "original":
                self.visit(entry)
            else:
                self.skip_copies(entry, f"inside a workspace's {entry.name}/: BridgeForge's own copy (a proof carrier, a scratch copy)")


def corpus_roots(corpus: Path, excludes: tuple[str, ...] = ()) -> tuple[list[tuple[Path, str]], list[Path], list[Path],
                                                                        list[tuple[Path, str]]]:
    """([(mod root, "working" | "archive" | "original")], zips, unread archives and folders, [(skipped copy, why)]) under
    `corpus`. Top-level folders matching an `excludes` glob (by name) are skipped: a rig's `mods/` holds installed copies."""
    walk = _Walk(Path(corpus), excludes)
    walk.visit(Path(corpus))
    return walk.roots, walk.zips, walk.unread, walk.skipped


def zip_mod_infos(path: Path) -> list[dict]:
    """The `mod_info.json` files a zip holds at its root or one or two folders down: [{entry, id, version, sha256}]."""
    from bridgeforge.genome.gene import _version_text
    from bridgeforge.scan.scan_json import _parse_json
    from bridgeforge.zipsafe import read_limited

    found = []
    with zipfile.ZipFile(path) as archive:
        for name in sorted(archive.namelist()):
            if name.rsplit("/", 1)[-1].lower() != MOD_INFO or name.count("/") > 2:
                continue
            raw = read_limited(archive, name, _MAX_INFO)
            try:
                data, _ = _parse_json(raw.decode("utf-8-sig", errors="replace"))
            except ValueError:
                data = None
            info = data if isinstance(data, dict) else {}
            found.append({"entry": name, "id": info.get("id"), "version": _version_text(info.get("version")), "sha256": _sha(raw)})
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


def id_patterns(anchors: list[str]) -> tuple[re.Pattern[bytes], re.Pattern[bytes]]:
    """(text pattern: the id as a whole word; class pattern: the id not followed by a word character). A class file's
    constant is preceded by its two-byte length, whose low byte may be a letter (review 2026-11-23)."""
    idents = sorted({a.partition(":")[2] for a in anchors}, key=lambda s: (-len(s), s))
    body = rb"(" + b"|".join(re.escape(i.encode("utf-8")) for i in idents) + rb")(?![A-Za-z0-9_])"
    return re.compile(rb"(?<![A-Za-z0-9_])" + body), re.compile(body)


def mentioned_ids(root: Path, patterns: tuple[re.Pattern[bytes], re.Pattern[bytes]]) -> tuple[set[str], list[str]]:
    """(ids named in any text file or jar entry under `root`, what could not be read). Each file and each jar entry is read
    on its own, so one bad entry hides nothing else (review 2026-11-23)."""
    text_pattern, class_pattern = patterns
    found: set[str] = set()
    unread: list[str] = []

    def failed(error: OSError) -> None:
        unread.append(f"{_rel(Path(error.filename or root), root)} (cannot list: {type(error).__name__})")

    for folder, dirs, files in os.walk(root, onerror=failed):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d != "__pycache__")
        for name in sorted(files):
            path = Path(folder) / name
            suffix = path.suffix.lower()
            if suffix in _TEXT:
                try:
                    if path.stat().st_size > _MAX_TEXT:
                        unread.append(_rel(path, root) + " (too large)")
                        continue
                    found.update(m.decode("utf-8") for m in text_pattern.findall(path.read_bytes()))
                except OSError as exc:
                    unread.append(f"{_rel(path, root)} ({type(exc).__name__})")
            elif suffix == ".jar":
                found.update(_jar_mentions(path, root, text_pattern, class_pattern, unread))
    return found, unread


def _jar_mentions(path: Path, root: Path, text_pattern, class_pattern, unread: list[str]) -> set[str]:
    from bridgeforge.zipsafe import MAX_CLASS_BYTES, read_limited

    found: set[str] = set()
    try:
        jar = zipfile.ZipFile(path)
    except Exception as exc:  # a jar Python cannot open at all (BadZipFile, an unsupported method): listed, not fatal
        unread.append(f"{_rel(path, root)} ({type(exc).__name__})")
        return found
    with jar:
        for entry in jar.namelist():
            is_class = entry.endswith(".class")
            if not is_class and Path(entry).suffix.lower() not in _TEXT:
                continue
            try:
                data = read_limited(jar, entry, MAX_CLASS_BYTES)
            except Exception as exc:  # one oversize or unsupported entry: listed, and the rest of the jar is read
                unread.append(f"{_rel(path, root)}!{entry} ({type(exc).__name__})")
                continue
            found.update(m.decode("utf-8") for m in (class_pattern if is_class else text_pattern).findall(data))
    return found


def scan_root(root: Path, anchors: list[str], patterns) -> dict:
    """{defines, mentions, unreadable, error} of one root. A failure other than an unreadable file is an `error`, which the
    acceptance needs explained (advisor 2026-11-23); defines found before a failed mention search are kept."""
    kinds = {a.partition(":")[0] for a in anchors}
    errors, defines, named, unreadable = [], [], set(), []
    try:
        index = RootIndex(root, kinds)
        defines = [a for a in anchors if index.defines(a)]
    except Exception as exc:  # recorded per root and counted; the walk goes on
        errors.append(f"defines: {type(exc).__name__}: {exc}")
    try:
        named, unreadable = mentioned_ids(root, patterns)
    except Exception as exc:  # recorded per root and counted; the walk goes on
        errors.append(f"mentions: {type(exc).__name__}: {exc}")
    mentions = [a for a in anchors if a.partition(":")[2] in named and a not in defines]
    return {"defines": defines, "mentions": mentions, "unreadable": unreadable, "error": "; ".join(errors) or None}


def bank_anchors(bank: Path | None = None) -> tuple[list[str], list[str]]:
    """(pilot anchors: the bank's sources.json lines, every anchor of a current record), each sorted."""
    from bridgeforge.genome.bank import Bank

    target = Bank(bank)
    records = target.records()
    pilots = sorted({s["anchor"] for s in target.sources()})
    if not pilots:
        raise AllelesError(f"{target.root} holds no sources: bank the pilots first")
    current = [records[rid] for rid in target.current_ids() if rid in records]
    if any(not isinstance(record.get("anchor"), str) for record in current):
        raise AllelesError(f"{target.root} has a current record with no anchor: run gene bank verify")
    anchors = sorted({record["anchor"] for record in current} | set(pilots))
    unknown = sorted({a.partition(":")[0] for a in anchors} - set(DEFINED_KINDS))
    if unknown:
        raise AllelesError(f"no corpus test for anchor kind(s) {', '.join(unknown)}")
    return pilots, anchors


def _zip_rows(zips: list[Path], scanned: set[str], base: Path) -> list[dict]:
    """Each zip and its mod_info.json files. A packaged copy is one whose every mod_info.json is byte for byte a scanned
    copy's; any failure to read it is recorded, never fatal (review 2026-11-23: one Deflate64 zip ended the run)."""
    rows = []
    for path in zips:
        try:
            infos = zip_mod_infos(path)
        except Exception as exc:  # listed as unreadable; the plan is still written
            rows.append({"path": _rel(path, base), "mods": [], "state": f"unreadable ({type(exc).__name__})"})
            continue
        state = ("packaged copy of a scanned copy" if infos and all(i["sha256"] in scanned for i in infos)
                 else "archive only, not described" if infos else "no mod")
        rows.append({"path": _rel(path, base), "mods": infos, "state": state})
    return rows


def _scan_rows(roots: list[tuple[Path, str]], anchors: list[str], checkpoint, quiet: bool, base: Path) -> list[dict]:
    """One row per root. A row is checkpointed under its path and its mod_info.json hash, so a copy changed in place (an
    `archive --refresh`) is scanned again; a row with an error is not checkpointed, so a resume retries it."""
    from bridgeforge.genome.gene import _version_text
    from bridgeforge.mod_files import read_mod_info
    from bridgeforge.progress import report

    patterns = id_patterns(anchors)
    rows = []
    for number, (root, folder) in enumerate(roots, 1):
        path = _rel(root, base)
        info_sha = _sha((root / MOD_INFO).read_bytes()) if (root / MOD_INFO).is_file() else None
        key = f"{path}|{info_sha}"
        saved, started = checkpoint.get(key), time.monotonic()
        resumed = saved is not None
        if saved is None:
            info = read_mod_info(root) or {}
            saved = {"path": path, "folder": folder, "mod_id": info.get("id"), "mod_version": _version_text(info.get("version")),
                     "mod_info_sha256": info_sha, **scan_root(root, anchors, patterns)}
            if not saved["error"]:
                checkpoint.add(key, saved)
        rows.append(saved)
        if not quiet:
            detail = f"error: {saved['error']}" if saved["error"] else f"defines {len(saved['defines'])}, mentions {len(saved['mentions'])}"
            report(number, len(roots), path, detail, None if resumed else time.monotonic() - started)
    return rows


def plan(corpus: Path, *, bank: Path | None = None, excludes: tuple[str, ...] = (), checkpoint_path: Path | None = None,
         quiet: bool = False, base: Path | None = None) -> dict:
    """The denominator over `corpus`: per root, the banked anchors it defines and mentions; per anchor, the roots."""
    from bridgeforge.paths import data_root
    from bridgeforge.progress import Checkpoint

    base = Path(base or data_root())
    if not Path(corpus).is_dir():
        raise AllelesError(f"{corpus} is not a folder")
    if not Path(corpus).resolve().is_relative_to(base.resolve()):
        raise AllelesError(f"{corpus} is not under the data root, so its copies could not be banked by relative path")
    pilots, anchors = bank_anchors(bank)
    roots, zips, unread, skipped = corpus_roots(Path(corpus), excludes)
    # The anchors and excludes go in as digests, not lists: a longer list must restart the run, not count as grown.
    head = {"command": "gene bank alleles", "corpus": _rel(Path(corpus), base), "anchors": _sha(json.dumps(anchors).encode()),
            "excludes": _sha(json.dumps(list(excludes)).encode()), "roots": [_rel(root, base) for root, _ in roots]}
    with Checkpoint(checkpoint_path, head) as checkpoint:
        rows = _scan_rows(roots, anchors, checkpoint, quiet, base)
    scanned = {r["mod_info_sha256"] for r in rows if r["mod_info_sha256"]}
    return {"schema": PLAN_SCHEMA, "schema_version": PLAN_VERSION, "corpus": head["corpus"], "excludes": list(excludes),
            "pilot_anchors": pilots, "anchors": anchors, "roots": rows, "zips": _zip_rows(zips, scanned, base),
            "unread_archives": [_rel(p, base) for p in unread],
            "skipped": [{"path": _rel(p, base), "reason": why} for p, why in skipped],
            "summary": summarize(rows, pilots, anchors)}


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
        write_plan(result, out)
    except (AllelesError, OSError, ValueError, KeyError) as exc:
        print(f"bridgeforge: {exc}", file=sys.stderr)
        return 2
    if checkpoint.is_file():
        checkpoint.unlink()  # the checkpoint goes only once the full plan is on disk
    summary = result["summary"]
    print(f"{summary['roots']} root(s); {summary['roots_defining_a_pilot']} define a pilot anchor, {summary['roots_defining_any']} "
          f"any banked anchor; {summary['errors']} error(s), {summary['unreadable_files']} unreadable file(s); "
          f"{len(result['zips'])} zip(s), {len(result['unread_archives'])} unread archive(s), {len(result['skipped'])} skipped copies")
    for anchor in result["pilot_anchors"]:
        row = summary["anchors"][anchor]
        print(f"  {anchor}: {row['roots']} root(s), {row['mod_versions']} mod version(s), {row['mention_only']} mention only")
    return 1 if summary["errors"] else 0


__all__ = ["AllelesError", "DEFINED_KINDS", "RootIndex", "bank_anchors", "corpus_roots", "id_patterns", "mentioned_ids", "plan",
           "run_alleles_cli", "scan_root", "summarize", "zip_mod_infos"]
