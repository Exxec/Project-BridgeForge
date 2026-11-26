"""Read-only reports over the gene bank's current records (94.G3 slice 3a, docs/GENE_BANK_DESIGN.md "Slice 3").

- `lineage`: member blobs that the current records of two or more distinct mod ids hold, each as a member. Hashes carry no
  direction, so a group is "shared by", never "copied from". The same mod id in two releases or folders is an allele and is
  counted apart. Three kinds of coincidence are excluded and counted: a blob only a donor need holds on one side, a trivial
  JSON value, and (with a core) a blob equal to one of the core's data files. The count over Test1's bank on 2026-11-26 found
  4 shared blobs, all one-byte JSON numbers held as a member on one side and a donor need on the other.
- `licences`: each current record's banked decision with its manifest's reason, mod decision and local-only members; the
  genes narrowed to LOCAL_ONLY by a local-only path; and drift, where today's ledger (licence_ledger) answers otherwise.
  Drift is only flagged: correcting it is a re-put, which gives a new ROOT.

Neither report writes into the bank: `write_report` refuses an output path inside the bank folder, since `put` and
`rebuild` refuse a bank holding any foreign entry. Both reports name mods and members, so they stay on the machine.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from bridgeforge.genome.bank import Bank, BankError, member_bytes

REPORT_SCHEMA_VERSION = 1
TRIVIAL_STRING_CHARS = 32  # an id or a label; a longer string, such as a pasted description, is evidence of a copy
_PARSE_LIMIT_BYTES = 4096  # a trivial value is far smaller; larger blobs are never parsed


def _root_text(bank: Bank) -> str | None:
    path = bank.root / "ROOT"
    return path.read_text(encoding="utf-8").strip() if path.is_file() else None


def _current_records(bank: Bank) -> tuple[dict[str, dict], list[str]]:
    """The current records, and the current record ids whose file is missing or unreadable (counted, never dropped silently)."""
    records = bank.records()
    current = bank.current_ids()
    return ({rid: records[rid] for rid in sorted(current & set(records))}, sorted(current - set(records)))


def _source(record: dict) -> dict:
    source = record.get("source")
    return source if isinstance(source, dict) else {}


def _mod_key(rid: str, record: dict) -> str:
    """The mod a record belongs to: its id, or for a source without one, its path, so two id-less mods stay two."""
    source = _source(record)
    mod_id = source.get("mod_id")
    if isinstance(mod_id, str) and mod_id:
        return mod_id
    return f"(no mod id: {source.get('path') or rid})"


def _blob_bytes(bank: Bank, digest: str, limit: int | None = None) -> bytes | None:
    """A blob's bytes, or None when `limit` is given and the blob is larger. A missing blob is a bank problem `verify` names."""
    path = bank.root / "blobs" / digest[:2] / digest
    try:
        if limit is not None and path.stat().st_size > limit:
            return None
        return path.read_bytes()
    except OSError as exc:
        raise BankError(f"blob {digest[:12]} of a current record cannot be read ({exc}); run `gene bank verify`") from exc


def is_trivial_value(data: bytes) -> bool:
    """Empty, a JSON number, boolean or null, an empty string, list or object, or a string of at most TRIVIAL_STRING_CHARS."""
    if not data.strip():
        return True
    if len(data) > _PARSE_LIMIT_BYTES:
        return False
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return False
    if value is None or isinstance(value, (bool, int, float)):
        return True
    if isinstance(value, (list, dict)):
        return not value
    return isinstance(value, str) and len(value) <= TRIVIAL_STRING_CHARS


def vanilla_hashes(vanilla_core: Path) -> set[str]:
    """The hash of every file under the core's data/, taken the way a file member's blob is (member_bytes)."""
    import hashlib

    data = Path(vanilla_core) / "data"
    if not data.is_dir():
        raise BankError(f"{vanilla_core} has no data folder: name a starsector-core")
    return {hashlib.sha256(member_bytes(Path(vanilla_core), "file", path.relative_to(vanilla_core).as_posix())).hexdigest()
            for path in sorted(data.rglob("*")) if path.is_file()}


def _holder(rid: str, record: dict, path: str) -> dict:
    source = _source(record)
    return {"mod_id": _mod_key(rid, record), "mod_version": source.get("mod_version"), "folder": source.get("folder"),
            "anchor": record.get("anchor"), "kind": record.get("kind"), "path": path}


def lineage(bank: Bank, vanilla_core: Path | None = None) -> dict:
    """Shared member blobs across mod ids over the current records; see the module docstring.

    Each blob held by two or more mods in any role is classified once, in this order:
    - `donor_side`: fewer than two of those mods hold it as a member (a donor need on one side, or on both);
    - `trivial_value`, then `vanilla_file`: held as a member by two or more mods, but too small or vanilla's own;
    - shared: the rest, grouped by the full set of mods holding it (a blob three mods hold is one group of three).
    A blob only one mod holds as a member is counted in `across_copies_of_one_mod` when two or more of that mod's copies
    (releases or folder kinds) hold it: an allele, not lineage."""
    records, unreadable = _current_records(bank)
    as_member: dict[str, list[dict]] = defaultdict(list)
    any_role: dict[str, set] = defaultdict(set)
    for rid, record in records.items():
        mod = _mod_key(rid, record)
        for path, digest in sorted((record.get("members") or {}).items()):
            as_member[digest].append(_holder(rid, record, path))
            any_role[digest].add(mod)
        for digest in (record.get("donor") or {}).values():
            any_role[digest].add(mod)
    vanilla = vanilla_hashes(vanilla_core) if vanilla_core is not None else set()
    excluded = {"donor_side": 0, "trivial_value": 0, "vanilla_file": 0}
    across_copies = 0
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for digest in sorted(any_role):
        holders = as_member.get(digest, [])
        member_mods = {holder["mod_id"] for holder in holders}
        if len(member_mods) < 2:
            if len(any_role[digest]) >= 2:
                excluded["donor_side"] += 1
            elif len({(holder["mod_version"], holder["folder"]) for holder in holders}) >= 2:
                across_copies += 1
            continue
        data = _blob_bytes(bank, digest, limit=_PARSE_LIMIT_BYTES)
        if data is not None and is_trivial_value(data):
            excluded["trivial_value"] += 1
            continue
        if digest in vanilla:
            excluded["vanilla_file"] += 1
            continue
        groups[tuple(sorted(member_mods))].append({"sha256": digest, "holders": holders})
    shared = [{"mods": list(mods), "blobs": blobs} for mods, blobs in sorted(groups.items())]
    counts = {"current_records": len(records), "unreadable_current_records": len(unreadable),
              "mod_ids": len({_mod_key(rid, r) for rid, r in records.items()}), "member_blobs": len(as_member),
              "shared_blobs": sum(len(group["blobs"]) for group in shared), "across_copies_of_one_mod": across_copies,
              "excluded": excluded}
    return {"schema_version": REPORT_SCHEMA_VERSION, "report": "lineage", "root": _root_text(bank), "counts": counts,
            "shared": shared}


def _manifest(bank: Bank, record: dict) -> dict:
    digest = record.get("manifest") or ""
    path = bank.root / "manifests" / digest[:2] / f"{digest}.json"
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BankError(f"record of {record.get('anchor')}: its manifest {digest[:12]} cannot be read ({exc})") from exc
    return manifest if isinstance(manifest, dict) else {}


def _ledger_today(manifest: dict, policy_path: Path | None) -> str:
    """The decision describe would give the gene now: the mod's ledger decision, narrowed by a local-only member path."""
    from bridgeforge.licence_ledger import decision, local_only_paths

    provenance = manifest.get("provenance") if isinstance(manifest.get("provenance"), dict) else {}
    mod_id, name = provenance.get("mod_id"), provenance.get("mod_name")
    paths = [m["path"] for m in manifest.get("members") or [] if isinstance(m, dict) and isinstance(m.get("path"), str)]
    if local_only_paths(mod_id, name, paths, policy_path):
        return "LOCAL_ONLY"
    return str(decision(mod_id, name, policy_path)["decision"])


def licences(bank: Bank, policy_path: Path | None = None) -> dict:
    """Each current record's licence, the genes narrowed by a local-only path, and drift from today's ledger."""
    rows, narrowed, drift = [], [], []
    by_decision: dict[str, int] = defaultdict(int)
    by_mod: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    records, unreadable = _current_records(bank)
    for rid, record in records.items():
        manifest = _manifest(bank, record)
        licence = manifest.get("licence") if isinstance(manifest.get("licence"), dict) else {}
        banked = str(record.get("licence"))
        row = {"record": rid, **_holder(rid, record, ""), "banked": banked, "reason": licence.get("reason"),
               "mod_decision": licence.get("mod_decision"), "local_only_members": list(licence.get("local_only_members") or [])}
        row.pop("path")
        rows.append(row)
        by_decision[banked] += 1
        by_mod[str(row["mod_id"])][banked] += 1
        if banked == "LOCAL_ONLY" and licence.get("mod_decision") not in (None, "LOCAL_ONLY"):
            narrowed.append(row)
        today = _ledger_today(manifest, policy_path)
        if today != banked:
            drift.append({**row, "ledger_today": today})
    counts = {"current_records": len(rows), "unreadable_current_records": len(unreadable),
              "by_decision": dict(sorted(by_decision.items())), "narrowed": len(narrowed), "drift": len(drift)}
    return {"schema_version": REPORT_SCHEMA_VERSION, "report": "licences", "root": _root_text(bank), "counts": counts,
            "by_mod": {mod: dict(sorted(c.items())) for mod, c in sorted(by_mod.items())}, "records": rows,
            "narrowed": narrowed, "drift": drift}


def is_inside(out: Path, root: Path) -> bool:
    """Whether `out` names the bank folder or anything under it. Besides the resolved paths, each existing ancestor is
    compared with the bank by file identity: on Windows `<bank> \\x` (a trailing space) and `\\\\?\\<bank>\\x` name the bank
    but resolve to text that never equals it (review of slice 3a)."""
    import os

    out, root = Path(out), Path(root)
    resolved_out, resolved_root = out.resolve(), root.resolve()
    if resolved_out == resolved_root or resolved_root in resolved_out.parents:
        return True
    if not root.exists():
        return False
    for candidate in (out, *out.parents):
        try:
            if candidate.exists() and os.path.samefile(candidate, root):
                return True
        except OSError:
            continue
    return False


def write_report(bank: Bank, out: Path, report: dict) -> Path:
    """Write `report` to `out`, refusing any path inside the bank folder (put and rebuild refuse a foreign entry there)."""
    from bridgeforge.safeio import atomic_write_json

    if is_inside(out, bank.root):
        raise BankError(f"{out} is inside the bank {bank.root}: a report there would make put and rebuild refuse the bank; "
                        f"write it elsewhere")
    out = Path(out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(out, report)
    return out


def run_report_cli(args) -> int:
    """`gene bank lineage|licences --out OUT`: write the report and print its counts."""
    bank = Bank(args.bank)
    if args.bank_command == "lineage":
        report = lineage(bank, getattr(args, "vanilla_core", None))
        out = write_report(bank, args.out, report)
        counts = report["counts"]
        excluded = counts["excluded"]
        print(f"lineage: {counts['shared_blobs']} shared blob(s) in {len(report['shared'])} group(s) of mod ids, over "
              f"{counts['current_records']} current record(s) of {counts['mod_ids']} mod id(s) "
              f"({counts['unreadable_current_records']} unreadable); across copies of one mod "
              f"{counts['across_copies_of_one_mod']}; excluded: donor side {excluded['donor_side']}, trivial value "
              f"{excluded['trivial_value']}, vanilla file {excluded['vanilla_file']}; ROOT {report['root']}; wrote {out}")
        return 0
    report = licences(bank)
    out = write_report(bank, args.out, report)
    counts = report["counts"]
    decisions = ", ".join(f"{name} {number}" for name, number in counts["by_decision"].items()) or "none"
    print(f"licences: {counts['current_records']} current record(s) ({decisions}; "
          f"{counts['unreadable_current_records']} unreadable); narrowed {counts['narrowed']}; "
          f"drift from today's ledger {counts['drift']}; ROOT {report['root']}; wrote {out}")
    return 0


__all__ = ["REPORT_SCHEMA_VERSION", "TRIVIAL_STRING_CHARS", "is_trivial_value", "licences", "lineage", "run_report_cli",
           "vanilla_hashes", "write_report"]
