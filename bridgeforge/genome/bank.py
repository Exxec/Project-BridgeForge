"""The gene bank (94.G3 slice 1, docs/GENE_BANK_DESIGN.md): a rebuildable, content-addressed index of gene manifests and
the bytes their members and donor needs were hashed from.

Keys (advisor 2026-11-23):
- A manifest is stored under the SHA-256 of its canonical bytes (`gene.dumps`), and an index maps each identity to its
  manifests. Needs are not part of the identity, so identity alone cannot tell a manifest made under older rules from a
  newer one.
- Every record carries a describer stamp (BridgeForge version, gene-contract pin) and the core build it was described
  against (the version the core reports). A re-described gene whose manifest changed supersedes the old record; it never
  overwrites it.
- A blob is the exact bytes a member's `sha256` was taken over: normalised text for a text file, raw bytes otherwise, the
  canonical JSON of a json-entry value or a csv-row's cells, a jar class's bytes. So `verify` can re-hash every one.

The bank lives under `data_root()/Genes/`, never in this repository. Records hold no machine paths and no timestamps, so a
rebuild from the same sources gives the same ROOT on any machine.
"""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

BANK_DIR = "Genes"
SOURCES = "sources.json"
FOLDER_KINDS = ("working", "original")


class BankError(Exception):
    """Raised when a source cannot be banked or the bank is not as it should be."""


def bank_root(given: Path | None = None) -> Path:
    from bridgeforge.paths import data_root

    return Path(given) if given is not None else data_root() / BANK_DIR


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def member_bytes(root: Path, what: str, path: str) -> bytes:
    """The bytes a member of kind `what` at `path` is hashed from (gene.py's `_file_member`, `_row_member`, `_jar_member`
    and json-entry hashing)."""
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
        data, _ = _parse_json((root / file).read_text(encoding="utf-8-sig"))
        value = _nested_get(data, pointer_tokens(ptr))
        return json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    raise BankError(f"{path}: no bank form for a member of kind {what!r}")


def record_id(manifest: str, source: dict, build: str | None) -> str:
    """A record's file name: one manifest may come from several sources (the same gene unchanged in two releases), and each
    source keeps its own record."""
    return _sha(json.dumps({"manifest": manifest, "source": source, "build": build}, sort_keys=True).encode("utf-8"))


def _donor_kind(path: str) -> str:
    from bridgeforge.licence_ledger import member_file

    return "json-entry" if member_file(path) != path else "file"


class Bank:
    """One bank folder: blobs/, manifests/, records/, sources.json, index.json and ROOT."""

    def __init__(self, root: Path | None = None):
        self.root = bank_root(root)

    def _put_bytes(self, folder: str, name: str, data: bytes) -> None:
        from bridgeforge.safeio import atomic_write_bytes

        target = self.root / folder / name[:2] / name
        if not target.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_bytes(target, data)

    def records(self) -> dict[str, dict]:
        folder = self.root / "records"
        return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("*.json"))} if folder.is_dir() else {}

    def _write_record(self, record: dict) -> None:
        from bridgeforge.safeio import atomic_write_text

        (self.root / "records").mkdir(parents=True, exist_ok=True)
        atomic_write_text(self.root / "records" / f"{record_id(record['manifest'], record['source'], record['build'])}.json",
                          json.dumps(record, indent=2, sort_keys=True) + "\n", newline="")

    def store(self, gene: dict, source_root: Path, source: dict, build: str | None, refused: dict[str, str]) -> str:
        """Store one manifest, its member and donor-need blobs and its record; return the manifest hash."""
        from bridgeforge import __version__
        from bridgeforge.genome.contract import contract_sha256
        from bridgeforge.genome.gene import dumps

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
        record = {"manifest": manifest, "identity": gene["identity"], "kind": gene["kind"], "anchor": gene["anchors"][0],
                  "source": source, "build": build, "describer": {"bridgeforge": __version__, "contract": contract_sha256()},
                  "licence": licence.get("decision"), "members": members, "donor": donor,
                  "needs_genes": sorted(gene["needs"].get("genes") or []),
                  "needs_refused": {need: refused[need] for need in gene["needs"].get("genes") or [] if need in refused},
                  "superseded_by": None}
        new_id = record_id(manifest, source, build)
        for old_id, old in self.records().items():  # same source, anchor and build: the new record supersedes the old one
            if (old_id != new_id and old["superseded_by"] is None and old["source"] == source and old["anchor"] == record["anchor"]
                    and old["build"] == build):
                self._write_record({**old, "superseded_by": new_id})
        existing = self.records().get(new_id)
        self._write_record({**record, "superseded_by": existing["superseded_by"]} if existing else record)
        return manifest

    def finish(self) -> str:
        """Rewrite index.json and ROOT from what is stored; return the root hash."""
        from bridgeforge.safeio import atomic_write_text

        records = self.records()
        index: dict[str, dict[str, list[str]]] = {"identity": {}, "anchor": {}, "kind": {}, "build": {}, "licence": {}}
        for manifest, record in records.items():
            for key in index:
                value = str(record.get(key))
                index[key].setdefault(value, []).append(manifest)
        atomic_write_text(self.root / "index.json", json.dumps(index, indent=2, sort_keys=True) + "\n", newline="")
        root = self.root_hash()
        atomic_write_text(self.root / "ROOT", root + "\n", newline="")
        return root

    def root_hash(self) -> str:
        """SHA-256 over the sorted record digests, manifest names and blob names."""
        lines = [f"record {name} {_sha((self.root / 'records' / f'{name}.json').read_bytes())}" for name in sorted(self.records())]
        for folder in ("manifests", "blobs"):
            base = self.root / folder
            lines += [f"{folder} {p.name}" for p in sorted(base.rglob("*")) if p.is_file()] if base.is_dir() else []
        return _sha("\n".join(lines).encode("utf-8"))

    def verify(self) -> list[str]:
        """Problems: a blob or manifest that does not hash to its name, a record whose manifest or blobs are missing, a needed
        gene with no record from the same source that is not recorded as refused, or a ROOT that does not recompute."""
        problems = []
        for folder, suffix in (("blobs", ""), ("manifests", ".json")):
            base = self.root / folder
            for path in sorted(base.rglob("*")) if base.is_dir() else []:
                if path.is_file() and _sha(path.read_bytes()) != path.name.removesuffix(suffix):
                    problems.append(f"{folder}/{path.name} does not hash to its name")
        records = self.records()
        for rid, record in records.items():
            manifest = record["manifest"]
            if rid != record_id(manifest, record["source"], record["build"]):
                problems.append(f"record {rid[:12]} is not filed under its manifest, source and build")
            if not (self.root / "manifests" / manifest[:2] / f"{manifest}.json").is_file():
                problems.append(f"record {rid[:12]}: its manifest is missing")
            for path, digest in {**record["members"], **record["donor"]}.items():
                if not (self.root / "blobs" / digest[:2] / digest).is_file():
                    problems.append(f"record {rid[:12]}: blob of {path} is missing")
            for need in record["needs_genes"]:
                if need in record["needs_refused"]:
                    continue
                if not any(r["anchor"] == need and r["source"] == record["source"] and r["build"] == record["build"]
                           for r in records.values()):
                    problems.append(f"record {rid[:12]} ({record['anchor']}): needed gene {need} has no record from the same source")
        stored = (self.root / "ROOT").read_text(encoding="utf-8").strip() if (self.root / "ROOT").is_file() else None
        if stored != self.root_hash():
            problems.append("ROOT does not recompute: run the command that last changed the bank again, or rebuild")
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


def put(source: Path, anchor: str, vanilla_core: Path, *, folder: str = "working", bank: Path | None = None,
        quiet: bool = True, base: Path | None = None) -> dict:
    """Describe `anchor` and every gene its needs name from `source` (a mod root) and store them. The source joins the
    bank's sources.json, which `rebuild` replays."""
    from bridgeforge.game_version import core_game_version
    from bridgeforge.genome.gene_set import walk
    from bridgeforge.safeio import atomic_write_text
    from bridgeforge.vendor_plan import _mod_root

    target = Bank(bank)
    source_root = _mod_root(Path(source))
    entry = source_entry(source_root, folder, base)
    build = core_game_version(Path(vanilla_core))
    genes, refused = walk(source_root, anchor, Path(vanilla_core), quiet=quiet)
    if anchor in refused:
        raise BankError(f"{anchor}: {refused[anchor]}")
    stored = [target.store(gene, source_root, entry, build, refused) for gene in genes.values()]
    sources = json.loads((target.root / SOURCES).read_text(encoding="utf-8")) if (target.root / SOURCES).is_file() else []
    wanted = {"path": entry["path"], "folder": folder, "anchor": anchor, "build": build}
    if wanted not in sources:
        sources = sorted([*sources, wanted], key=lambda s: (s["path"], s["folder"], s["anchor"]))
        atomic_write_text(target.root / SOURCES, json.dumps(sources, indent=2) + "\n", newline="")
    return {"anchor": anchor, "build": build, "stored": len(stored), "refused": refused, "root": target.finish()}


def rebuild(vanilla_core: Path, *, bank: Path | None = None, quiet: bool = False, base: Path | None = None) -> dict:
    """Wipe the bank and put every entry of its sources.json again, from the sources on this machine. The core must report
    the build each entry was banked under. Resumable: finished entries are kept in a checkpoint beside the bank."""
    import time

    from bridgeforge.game_version import core_game_version
    from bridgeforge.paths import data_root
    from bridgeforge.progress import Checkpoint, report
    from bridgeforge.safeio import atomic_write_text, safe_rmtree

    target = Bank(bank)
    sources_file = target.root / SOURCES
    if not sources_file.is_file():
        raise BankError(f"{sources_file} is missing: nothing to rebuild from")
    sources = json.loads(sources_file.read_text(encoding="utf-8"))
    build = core_game_version(Path(vanilla_core))
    wrong = sorted({s["build"] for s in sources} - {build})
    if wrong:
        raise BankError(f"the core reports {build}; the bank's sources were described against {', '.join(wrong)}")
    head = {"command": "gene bank rebuild", "sources": _sha(json.dumps(sources, sort_keys=True).encode("utf-8")), "build": build}
    checkpoint_path = target.root.parent / f"{target.root.name}.rebuild.partial.jsonl"
    with Checkpoint(checkpoint_path, head) as checkpoint:
        if not any(checkpoint.get(f"{s['path']}|{s['folder']}|{s['anchor']}") for s in sources):  # a fresh run: wipe first
            safe_rmtree(target.root, [target.root.parent])
            target.root.mkdir(parents=True)
            atomic_write_text(target.root / SOURCES, json.dumps(sources, indent=2) + "\n", newline="")
        for number, entry in enumerate(sources, 1):
            key = f"{entry['path']}|{entry['folder']}|{entry['anchor']}"
            if checkpoint.get(key):
                continue
            started = time.monotonic()
            result = put(Path(base or data_root()) / entry["path"], entry["anchor"], Path(vanilla_core), folder=entry["folder"],
                         bank=target.root, base=base)
            checkpoint.add(key, {"stored": result["stored"]})
            if not quiet:
                report(number, len(sources), entry["anchor"], f"{result['stored']} gene(s) from {entry['path']}", time.monotonic() - started)
        root = target.finish()
        checkpoint.finish()
    return {"sources": len(sources), "root": root, "problems": target.verify()}


def add_bank_parser(gene_sub) -> None:
    """`gene bank put|verify|rebuild|list` (94.G3)."""
    bank_cmd = gene_sub.add_parser("bank", help="the gene bank (94.G3): a rebuildable, content-addressed index of gene manifests and "
                                                "their members' bytes, under the data root's Genes/")
    bank_sub = bank_cmd.add_subparsers(dest="bank_command", required=True)
    put_cmd = bank_sub.add_parser("put", help="describe a gene and every gene its needs name from a mod, and store them")
    put_cmd.add_argument("mod", type=Path, help="mod folder or workspace (working/ is used); it must sit under the data root")
    put_cmd.add_argument("anchor", help="kind:id")
    put_cmd.add_argument("--vanilla-core", type=Path, required=True, help="starsector-core; its reported build is recorded")
    put_cmd.add_argument("--folder", choices=FOLDER_KINDS, default="working", help="which copy of the mod this is (default working)")
    verify_cmd = bank_sub.add_parser("verify", help="re-hash every blob and manifest, check every record and needed gene, and the ROOT")
    rebuild_cmd = bank_sub.add_parser("rebuild", help="wipe the bank and put every source of its sources.json again; one progress line "
                                                      "per source, resumable")
    rebuild_cmd.add_argument("--vanilla-core", type=Path, required=True, help="starsector-core reporting the build the sources were banked under")
    rebuild_cmd.add_argument("--quiet", action="store_true", help="no per-source progress lines on stderr")
    list_cmd = bank_sub.add_parser("list", help="the stored records, filtered by the index")
    for key in ("kind", "anchor", "build", "licence"):
        list_cmd.add_argument(f"--{key}", help=f"only records whose {key} is this")
    for command in (put_cmd, verify_cmd, rebuild_cmd, list_cmd):
        command.add_argument("--bank", type=Path, help="the bank folder (default: <data root>/Genes)")


def run_bank_cli(args) -> int:
    import sys

    from bridgeforge.genome.gene import GeneError
    from bridgeforge.vendor_plan import VendorPlanError

    try:
        if args.bank_command == "put":
            result = put(args.mod, args.anchor, args.vanilla_core, folder=args.folder, bank=args.bank)
            print(f"stored {result['stored']} gene(s) under build {result['build']}; refused needs: {len(result['refused'])}; "
                  f"ROOT {result['root']}")
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
            print(f"{target.root}: {len(target.records())} record(s), {len(problems)} problem(s)")
            for problem in problems:
                print(f"  {problem}")
            return 1 if problems else 0
        for _rid, record in sorted(target.records().items(), key=lambda kv: (kv[1]["anchor"], kv[0])):
            if all(getattr(args, key) in (None, str(record.get(key))) for key in ("kind", "anchor", "build", "licence")):
                state = f" superseded by record {record['superseded_by'][:12]}" if record["superseded_by"] else ""
                print(f"{record['manifest'][:12]} {record['anchor']} {record['source']['mod_id']} {record['source']['mod_version']} "
                      f"{record['source']['folder']} {record['build']} {record['licence']}{state}")
        return 0
    except (BankError, GeneError, VendorPlanError, OSError) as exc:
        print(f"bridgeforge: {exc}", file=sys.stderr)
        return 2


__all__ = ["BANK_DIR", "Bank", "BankError", "add_bank_parser", "bank_root", "member_bytes", "put", "rebuild", "run_bank_cli",
           "source_entry"]
