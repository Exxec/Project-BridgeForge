"""The gene bank (94.G3 slice 1, docs/GENE_BANK_DESIGN.md): a rebuildable, content-addressed index of gene manifests and
the bytes their members and donor needs were hashed from.

Keys (advisor 2026-11-23):
- A manifest is stored under the SHA-256 of its canonical bytes (`gene.dumps`). Needs are not part of a gene's identity, so
  identity alone cannot tell a manifest made under older rules from a newer one.
- A record is filed under (manifest, source, build): the same manifest from two releases keeps two records. It carries the
  describer stamp (BridgeForge version, gene-contract pin) and the core build it was described against.
- A blob is the exact bytes a member's `sha256` was taken over: normalised text for a text file, raw bytes otherwise, the
  canonical JSON of a json-entry value or a csv-row's cells, a jar class's bytes. So `verify` can re-hash every one.

What is current (review 2026-11-23): `entries.json` holds, for each entry of `sources.json`, the records its last put
produced. A record no entry holds is history: kept, verified, never deleted, and outside the ROOT. The ROOT covers
entries.json, the current records and the manifests and blobs they name, so it depends only on the sources, the core and
the code, never on what the bank held before: a rebuild in place and a rebuild into an empty folder on another machine
give the same ROOT. Nothing here deletes anything.

The bank lives under `data_root()/Genes/`, never in this repository. Records hold no machine paths and no timestamps.
"""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

BANK_DIR = "Genes"
SOURCES = "sources.json"
ENTRIES = "entries.json"
PUT_CHECKPOINT = "put.partial.jsonl"
REBUILD_CHECKPOINT = "rebuild.partial.jsonl"
FOLDER_KINDS = ("working", "original")
_OWN = {"blobs", "manifests", "records", SOURCES, ENTRIES, "index.json", "ROOT", PUT_CHECKPOINT, REBUILD_CHECKPOINT}
_ENTRY_KEYS = ("path", "folder", "anchor", "build")


class BankError(Exception):
    """Raised when a source cannot be banked or the bank is not as it should be."""


def bank_root(given: Path | None = None) -> Path:
    from bridgeforge.paths import data_root

    return Path(given) if given is not None else data_root() / BANK_DIR


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def member_bytes(root: Path, what: str, path: str) -> bytes:
    """The bytes a member of kind `what` at `path` is hashed from (gene.py's `_file_member`, `_row_member`, `_jar_member`
    and json-entry hashing). JSON is read as describe reads settings and campaign files (`errors="replace"`): a strict read
    refused a stray Latin-1 byte that describe had hashed (review 2026-11-23)."""
    from bridgeforge.genome.closure import _canonical
    from bridgeforge.genome.gene import _TEXT_SUFFIXES, _normalized_text, row_cells
    from bridgeforge.genome.proof import _nested_get, pointer_tokens
    from bridgeforge.scan.scan_json import _parse_json
    from bridgeforge.zipsafe import MAX_CLASS_BYTES, read_limited

    root = Path(root)
    if what == "file":
        data = (root / path).read_bytes()
        return _normalized_text(data) if Path(path).suffix.lower() in _TEXT_SUFFIXES else data
    if what == "csv-row":
        return json.dumps(row_cells(root, path), sort_keys=True).encode("utf-8")
    if what == "jar-class":
        jar, _, entry = path.partition("!")
        with zipfile.ZipFile(root / jar) as archive:
            return read_limited(archive, entry, MAX_CLASS_BYTES)
    if what == "json-entry":
        file, _, ptr = path.partition("#")
        data, _ = _parse_json((root / file).read_text(encoding="utf-8-sig", errors="replace"))
        value = _nested_get(data, pointer_tokens(ptr))
        return _canonical_bytes(_canonical(value))
    raise BankError(f"{path}: no bank form for a member of kind {what!r}")


def record_id(manifest: str, source: dict, build: str | None) -> str:
    """A record's file name: one manifest may come from several sources (the same gene unchanged in two releases), and each
    source keeps its own record."""
    return _sha(json.dumps({"manifest": manifest, "source": source, "build": build}, sort_keys=True).encode("utf-8"))


def _donor_kind(path: str) -> str:
    from bridgeforge.licence_ledger import member_file

    return "json-entry" if member_file(path) != path else "file"


def _entry_key(entry: dict) -> tuple:
    return tuple(entry[key] for key in _ENTRY_KEYS)


def scrub_paths(text: str, places: list[tuple[str, Path]]) -> str:
    """`text` with each named folder's absolute path replaced by its label. A refusal reason names the mod root, and a
    record must read the same on every machine (review 2026-11-23)."""
    forms = set()
    for label, path in places:
        for form in (Path(path), Path(path).resolve()):
            forms.update({(str(form), label), (form.as_posix(), label)})
    for form, label in sorted(forms, key=lambda pair: (-len(pair[0]), pair[0])):
        text = text.replace(form, label)
    return text


class Bank:
    """One bank folder: blobs/, manifests/, records/, sources.json, entries.json, index.json and ROOT."""

    def __init__(self, root: Path | None = None):
        self.root = bank_root(root)

    def check_folder(self) -> None:
        """Refuse a folder that holds anything a bank does not: `--bank` naming the data root, a workspace or `Done/` must
        never be written into (review 2026-11-23)."""
        if self.root.exists() and not self.root.is_dir():
            raise BankError(f"{self.root} is a file, not a bank folder")
        foreign = sorted(p.name for p in self.root.iterdir() if p.name not in _OWN and not p.name.endswith(".tmp")) \
            if self.root.is_dir() else []
        if foreign:
            raise BankError(f"{self.root} holds {', '.join(foreign[:5])}, which no bank holds: name an empty folder or a bank")

    def _put_bytes(self, folder: str, name: str, data: bytes) -> None:
        from bridgeforge.safeio import atomic_write_bytes

        target = self.root / folder / name[:2] / name
        if not target.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_bytes(target, data)

    def _load_records(self) -> tuple[dict[str, dict], list[str]]:
        folder = self.root / "records"
        records, unreadable = {}, []
        for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                record = None
            if isinstance(record, dict):
                records[path.stem] = record
            else:
                unreadable.append(path.name)
        return records, unreadable

    def records(self) -> dict[str, dict]:
        return self._load_records()[0]

    def _read_list(self, name: str) -> list[dict]:
        path = self.root / name
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []

    def _write_list(self, name: str, items: list[dict]) -> None:
        from bridgeforge.safeio import atomic_write_text

        self.root.mkdir(parents=True, exist_ok=True)
        atomic_write_text(self.root / name, json.dumps(items, indent=2, sort_keys=True) + "\n", newline="")

    def sources(self) -> list[dict]:
        return self._read_list(SOURCES)

    def entries(self) -> list[dict]:
        return self._read_list(ENTRIES)

    def current_ids(self) -> set[str]:
        return {rid for entry in self.entries() for rid in entry.get("records") or []}

    def store(self, gene: dict, source_root: Path, source: dict, build: str | None, refused: dict[str, str]) -> str:
        """Store one manifest, its member and donor-need blobs and its record; return the record id. The record is
        rewritten every time, so it carries the describer that last produced it, as a fresh bank's would."""
        from bridgeforge import __version__
        from bridgeforge.genome.contract import contract_sha256
        from bridgeforge.genome.gene import dumps
        from bridgeforge.safeio import atomic_write_text

        text = dumps(gene).encode("utf-8")
        manifest = _sha(text)
        members = {}
        for member in gene["members"]:
            data = member_bytes(source_root, member["what"], member["path"])
            if _sha(data) != member["sha256"]:
                raise BankError(f"{member['path']}: its bytes do not hash to the manifest's sha256; the source changed after describe")
            self._put_bytes("blobs", member["sha256"], data)
            members[member["path"]] = member["sha256"]
        donor = {}
        for path in gene["needs"].get("donor") or []:
            data = member_bytes(source_root, _donor_kind(path), path)
            donor[path] = _sha(data)
            self._put_bytes("blobs", donor[path], data)
        self._put_bytes("manifests", f"{manifest}.json", text)
        licence = gene.get("licence") if isinstance(gene.get("licence"), dict) else {}
        needs = gene["needs"].get("genes") or []
        record = {"manifest": manifest, "identity": gene["identity"], "kind": gene["kind"], "anchor": gene["anchors"][0],
                  "source": source, "build": build, "describer": {"bridgeforge": __version__, "contract": contract_sha256()},
                  "licence": licence.get("decision"), "members": members, "donor": donor, "needs_genes": sorted(needs),
                  "needs_refused": {need: refused[need] for need in needs if need in refused}}
        rid = record_id(manifest, source, build)
        (self.root / "records").mkdir(parents=True, exist_ok=True)
        atomic_write_text(self.root / "records" / f"{rid}.json", json.dumps(record, indent=2, sort_keys=True) + "\n", newline="")
        return rid

    def set_entry(self, entry: dict, rids: list[str]) -> list[str]:
        """Make `rids` the records of `entry` (one sources.json line); return the record ids that stopped being current."""
        before = self.current_ids()
        row = {**{key: entry[key] for key in _ENTRY_KEYS}, "records": sorted(set(rids))}
        rows = [r for r in self.entries() if _entry_key(r) != _entry_key(entry)] + [row]
        self._write_list(ENTRIES, sorted(rows, key=_entry_key))
        return sorted(before - self.current_ids())

    def finish(self) -> str:
        """Rewrite index.json (over the current records) and ROOT; return the root hash."""
        from bridgeforge.safeio import atomic_write_text

        records, current = self.records(), self.current_ids()
        index: dict[str, dict[str, list[str]]] = {"identity": {}, "anchor": {}, "kind": {}, "build": {}, "licence": {}}
        for rid in sorted(current & set(records)):
            for key in index:
                index[key].setdefault(str(records[rid].get(key)), []).append(rid)
        atomic_write_text(self.root / "index.json", json.dumps(index, indent=2, sort_keys=True) + "\n", newline="")
        root = self.root_hash()
        atomic_write_text(self.root / "ROOT", root + "\n", newline="")
        return root

    def root_hash(self) -> str:
        """SHA-256 over entries.json, each current record's bytes and the manifests and blobs current records name; taken
        from the records, not from a listing of the disk, so history never changes it."""
        records = self.records()
        lines = [f"entries {_sha(_canonical_bytes(self.entries()))}"]
        named = set()
        for rid in sorted(self.current_ids()):
            path = self.root / "records" / f"{rid}.json"
            lines.append(f"record {rid} {_sha(path.read_bytes()) if path.is_file() else 'missing'}")
            record = records.get(rid) or {}
            named.add(f"manifest {record.get('manifest')}")
            named.update(f"blob {digest}" for digest in {**(record.get("members") or {}), **(record.get("donor") or {})}.values())
        return _sha("\n".join(lines + sorted(named)).encode("utf-8"))

    def verify(self) -> list[str]:
        """Every problem the bank has: see `_hash_problems`, `_record_problems`, `_entry_problems`, and a ROOT that does
        not recompute."""
        records, unreadable = self._load_records()
        problems = self._hash_problems() + [f"records/{name} is unreadable" for name in unreadable]
        problems += self._record_problems(records) + self._entry_problems(records)
        stored = (self.root / "ROOT").read_text(encoding="utf-8").strip() if (self.root / "ROOT").is_file() else None
        if stored != self.root_hash():
            problems.append("ROOT does not recompute: run the command that last changed the bank again, or rebuild")
        return problems

    def _hash_problems(self) -> list[str]:
        problems = []
        for folder, suffix in (("blobs", ""), ("manifests", ".json")):
            base = self.root / folder
            for path in sorted(base.rglob("*")) if base.is_dir() else []:
                if path.is_file() and _sha(path.read_bytes()) != path.name.removesuffix(suffix):
                    problems.append(f"{folder}/{path.name} does not hash to its name")
        return problems

    def _record_problems(self, records: dict[str, dict]) -> list[str]:
        """A record not filed under its id, a missing manifest or blob, and a current record's needed gene with no current
        record from the same source and build that is not recorded as refused."""
        problems, current = [], self.current_ids()
        for rid, record in records.items():
            try:
                manifest = record["manifest"]
                if rid != record_id(manifest, record["source"], record["build"]):
                    problems.append(f"record {rid[:12]} is not filed under its manifest, source and build")
                if not (self.root / "manifests" / manifest[:2] / f"{manifest}.json").is_file():
                    problems.append(f"record {rid[:12]}: its manifest is missing")
                for path, digest in {**record["members"], **record["donor"]}.items():
                    if not (self.root / "blobs" / digest[:2] / digest).is_file():
                        problems.append(f"record {rid[:12]}: blob of {path} is missing")
                for need in record["needs_genes"] if rid in current else []:
                    if need not in record["needs_refused"] and not any(
                            records.get(other, {}).get("anchor") == need and records[other].get("source") == record["source"]
                            and records[other].get("build") == record["build"] for other in current):
                        problems.append(f"record {rid[:12]} ({record['anchor']}): needed gene {need} has no current record "
                                        f"from the same source")
            except (KeyError, TypeError, AttributeError):
                problems.append(f"record {rid[:12]} is malformed")
        return problems

    def _entry_problems(self, records: dict[str, dict]) -> list[str]:
        """A sources.json entry with no entries.json row, a row whose records are missing, or a row holding no record of
        its own anchor."""
        problems = []
        rows = {_entry_key(row): row for row in self.entries()}
        for entry in self.sources():
            row = rows.get(_entry_key(entry))
            label = f"{entry['path']} ({entry['folder']}) {entry['anchor']}"
            if row is None:
                problems.append(f"source {label} has no entries row: put it again, or rebuild")
                continue
            missing = [rid for rid in row["records"] if rid not in records]
            if missing:
                problems.append(f"source {label}: {len(missing)} of its records are missing")
            if not any(records.get(rid, {}).get("anchor") == entry["anchor"] for rid in row["records"]):
                problems.append(f"source {label} has no current record of its anchor")
        return problems


def source_entry(source_root: Path, folder: str, base: Path | None = None) -> dict:
    """The machine-independent source key of a describe root: the mod's id and version, the folder kind and the root's
    path relative to the data root (Test1 and White_Legion keep `In operation/` at the same place under it)."""
    from bridgeforge.genome.gene import _version_text
    from bridgeforge.mod_files import read_mod_info
    from bridgeforge.paths import data_root

    if folder not in FOLDER_KINDS:
        raise BankError(f"folder kind {folder!r} is not one of {', '.join(FOLDER_KINDS)}")
    info = read_mod_info(source_root) or {}
    try:
        relative = Path(source_root).resolve().relative_to(Path(base or data_root()).resolve()).as_posix()
    except ValueError as exc:
        raise BankError(f"{source_root} is not under the data root, so a rebuild could not find it on another machine") from exc
    return {"mod_id": info.get("id"), "mod_version": _version_text(info.get("version")), "folder": folder, "path": relative}


def _source_root(source: Path, folder: str) -> Path:
    """The mod root `put` describes. A workspace resolves to its working/ copy, which must not be banked as `original`
    (review 2026-11-23)."""
    from bridgeforge.vendor_plan import _mod_root

    root = _mod_root(Path(source))
    if folder != "working" and root == Path(source).resolve() / "working":
        raise BankError(f"{source} is a workspace: its working/ copy is not the {folder}; name the {folder} mod folder itself")
    return root


def put(source: Path, anchor: str, vanilla_core: Path, *, folder: str = "working", bank: Path | None = None,
        quiet: bool = True, base: Path | None = None) -> dict:
    """Describe `anchor` and every gene its needs name from `source` (a mod root) and store them. The source joins the
    bank's sources.json, which `rebuild` replays; its entries.json row becomes the records this put produced."""
    from bridgeforge.game_version import core_game_version
    from bridgeforge.genome.gene_set import walk
    from bridgeforge.paths import data_root

    target = Bank(bank)
    target.check_folder()
    source_root = _source_root(source, folder)
    if source_root.resolve() in (target.root.resolve(), *target.root.resolve().parents):
        raise BankError(f"the bank {target.root} sits inside the source {source_root}")
    entry = source_entry(source_root, folder, base)
    build = core_game_version(Path(vanilla_core))
    checkpoint = target.root / PUT_CHECKPOINT
    genes, refused = walk(source_root, anchor, Path(vanilla_core), checkpoint_path=checkpoint, quiet=quiet)
    if anchor in refused:
        raise BankError(f"{anchor}: {refused[anchor]}")
    places = [("<source>", source_root), ("<core>", Path(vanilla_core)), ("<data root>", Path(base or data_root()))]
    refused = {need: scrub_paths(reason, places) for need, reason in refused.items()}
    rids = [target.store(gene, source_root, entry, build, refused) for gene in genes.values()]
    wanted = {"path": entry["path"], "folder": folder, "anchor": anchor, "build": build}
    sources = target.sources()
    if wanted not in sources:
        target._write_list(SOURCES, sorted([*sources, wanted], key=_entry_key))
    retired = target.set_entry(wanted, rids)
    root = target.finish()
    if checkpoint.is_file():
        checkpoint.unlink()  # the walk's checkpoint goes only once the records and the ROOT are on disk
    return {"anchor": anchor, "build": build, "stored": len(rids), "refused": refused, "retired": retired, "root": root}


def rebuild(vanilla_core: Path, *, bank: Path | None = None, quiet: bool = False, base: Path | None = None) -> dict:
    """Put every entry of the bank's sources.json again, from the sources on this machine, into the bank as it is: an empty
    folder holding only sources.json, or a bank whose history is kept. Nothing is deleted. The core must report the build
    each entry was banked under, and every source must be there before anything is written. Resumable."""
    import time

    from bridgeforge.game_version import core_game_version
    from bridgeforge.mod_files import ModRootError, workspace_or_mod_root
    from bridgeforge.paths import data_root
    from bridgeforge.progress import Checkpoint, report

    target = Bank(bank)
    target.check_folder()
    if not (target.root / SOURCES).is_file():
        raise BankError(f"{target.root / SOURCES} is missing: nothing to rebuild from")
    sources, build = target.sources(), core_game_version(Path(vanilla_core))
    wrong = sorted({s["build"] for s in sources} - {build})
    if wrong:
        raise BankError(f"the core reports {build}; the bank's sources were described against {', '.join(wrong)}")
    missing = []
    for entry in sources:
        try:
            workspace_or_mod_root(Path(base or data_root()) / entry["path"])
        except ModRootError:
            missing.append(entry["path"])
    if missing:
        raise BankError(f"{len(missing)} source(s) are not on this machine: {', '.join(sorted(set(missing)))}")
    head = {"command": "gene bank rebuild", "sources": _sha(_canonical_bytes(sources)), "build": build}
    with Checkpoint(target.root / REBUILD_CHECKPOINT, head) as checkpoint:
        for number, entry in enumerate(sources, 1):
            key = "|".join(str(entry[k]) for k in _ENTRY_KEYS)
            if checkpoint.get(key):
                continue
            started = time.monotonic()
            result = put(Path(base or data_root()) / entry["path"], entry["anchor"], Path(vanilla_core), folder=entry["folder"],
                         bank=target.root, quiet=quiet, base=base)
            checkpoint.add(key, {"stored": result["stored"]})
            if not quiet:
                report(number, len(sources), entry["anchor"], f"{result['stored']} gene(s) from {entry['path']}", time.monotonic() - started)
        root = target.finish()
        checkpoint.finish()
    return {"sources": len(sources), "root": root, "problems": target.verify()}


def add_bank_parser(gene_sub) -> None:
    """`gene bank put|verify|rebuild|list|alleles` (94.G3)."""
    bank_cmd = gene_sub.add_parser("bank", help="the gene bank (94.G3): a rebuildable, content-addressed index of gene manifests and "
                                                "their members' bytes, under the data root's Genes/")
    bank_sub = bank_cmd.add_subparsers(dest="bank_command", required=True)
    put_cmd = bank_sub.add_parser("put", help="describe a gene and every gene its needs name from a mod, and store them; one progress "
                                              "line per gene, resumable")
    put_cmd.add_argument("mod", type=Path, help="mod folder or workspace (working/ is used); it must sit under the data root")
    put_cmd.add_argument("anchor", help="kind:id")
    put_cmd.add_argument("--vanilla-core", type=Path, required=True, help="starsector-core; its reported build is recorded")
    put_cmd.add_argument("--folder", choices=FOLDER_KINDS, default="working", help="which copy of the mod this is (default working)")
    verify_cmd = bank_sub.add_parser("verify", help="re-hash every blob and manifest, check every record, source and needed gene, and the ROOT")
    rebuild_cmd = bank_sub.add_parser("rebuild", help="put every source of sources.json again, into the bank as it is (nothing is "
                                                      "deleted); one progress line per source, resumable")
    rebuild_cmd.add_argument("--vanilla-core", type=Path, required=True, help="starsector-core reporting the build the sources were banked under")
    for command in (put_cmd, rebuild_cmd):
        command.add_argument("--quiet", action="store_true", help="no progress lines on stderr")
    list_cmd = bank_sub.add_parser("list", help="the current records, filtered by kind, anchor, build or licence")
    for key in ("kind", "anchor", "build", "licence"):
        list_cmd.add_argument(f"--{key}", help=f"only records whose {key} is this")
    list_cmd.add_argument("--history", action="store_true", help="also list records no source holds any more")
    alleles_cmd = bank_sub.add_parser("alleles", help="plan only: every copy of a mod under CORPUS that defines a banked anchor, "
                                                      "what only mentions one, and what could not be read; one progress line per "
                                                      "mod root, resumable; nothing is put (94.G3 slice 2)")
    alleles_cmd.add_argument("corpus", type=Path, help="a folder under the data root, such as Done/")
    alleles_cmd.add_argument("--out", type=Path, required=True, help="the plan JSON to write; it names mod folders, so keep it local")
    alleles_cmd.add_argument("--exclude", action="append", metavar="GLOB",
                             help="skip top-level corpus folders matching this (repeatable), such as a rig's _rig-*")
    alleles_cmd.add_argument("--quiet", action="store_true", help="no progress lines on stderr")
    for command in (put_cmd, verify_cmd, rebuild_cmd, list_cmd, alleles_cmd):
        command.add_argument("--bank", type=Path, help="the bank folder (default: <data root>/Genes)")


def _print_list(target: Bank, args) -> None:
    current = target.current_ids()
    for rid, record in sorted(target.records().items(), key=lambda kv: (kv[1].get("anchor", ""), kv[0])):
        if rid not in current and not args.history:
            continue
        if all(getattr(args, key) in (None, str(record.get(key))) for key in ("kind", "anchor", "build", "licence")):
            state = "" if rid in current else " history"
            print(f"{rid[:12]} {record['anchor']} {record['source']['mod_id']} {record['source']['mod_version']} "
                  f"{record['source']['folder']} {record['build']} {record['licence']}{state}")


def run_bank_cli(args) -> int:
    import sys

    from bridgeforge.genome.gene import GeneError
    from bridgeforge.vendor_plan import VendorPlanError

    if args.bank_command == "alleles":
        from bridgeforge.genome.alleles import run_alleles_cli

        return run_alleles_cli(args)
    try:
        if args.bank_command == "put":
            result = put(args.mod, args.anchor, args.vanilla_core, folder=args.folder, bank=args.bank, quiet=args.quiet)
            print(f"stored {result['stored']} gene(s) under build {result['build']}; refused needs: {len(result['refused'])}; "
                  f"no longer current: {len(result['retired'])}; ROOT {result['root']}")
            return 0
        if args.bank_command == "rebuild":
            result = rebuild(args.vanilla_core, bank=args.bank, quiet=args.quiet)
            print(f"rebuilt {result['sources']} source(s); ROOT {result['root']}; {len(result['problems'])} problem(s)")
            for problem in result["problems"]:
                print(f"  {problem}")
            return 1 if result["problems"] else 0
        target = Bank(args.bank)
        if args.bank_command == "verify":
            problems = target.verify()
            print(f"{target.root}: {len(target.current_ids())} current record(s) of {len(target.records())}, "
                  f"{len(problems)} problem(s)")
            for problem in problems:
                print(f"  {problem}")
            return 1 if problems else 0
        _print_list(target, args)
        return 0
    except (BankError, GeneError, VendorPlanError, OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        print(f"bridgeforge: {exc}", file=sys.stderr)
        return 2


__all__ = ["BANK_DIR", "Bank", "BankError", "add_bank_parser", "bank_root", "member_bytes", "put", "rebuild", "run_bank_cli",
           "scrub_paths", "source_entry"]
