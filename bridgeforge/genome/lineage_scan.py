"""`gene bank lineage-scan PLAN --out OUT --vanilla-core CORE`: lineage beyond the bank (94.G3 slice 3b, docs/GENE_BANK_DESIGN.md).

Slice 3a found no member blob that two mod ids' banked records share, and the 2a plan over `Done/` found no root outside the
pilot families defining a banked anchor. So lineage has to look at a wider corpus: the owner chose Test1's `In operation/`
(2026-11-27, "that sounds fine"; White_Legion's mod folder too if needed).

For every root of an alleles plan (`gene bank alleles CORPUS --out PLAN`) that defines one of the bank's anchors under a mod
id the bank does not hold that anchor for, this describes the gene in memory (`gene_set.walk`, as `put` does) and intersects
its member hashes with the bank's member blobs. Nothing is put, and the bank is not written: the report goes through slice
3a's `write_report`, which refuses a path inside the bank. Hashes carry no direction, so a match is "shared by", never
"copied from".

Counted apart rather than reported as shared, as in 3a:
- `donor_side`: the bank holds the blob only as a donor need, not as a member;
- `trivial_value`: a JSON number, boolean, null, empty value or short string;
- `vanilla_file`: a blob equal to a file of the core's `data/`;
- `same_mod`: every bank holder of the blob is the candidate's own mod id (an allele, not lineage).

The report names mods and members, so it stays on the machine; the roadmap records counts only.
"""
from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path

from bridgeforge.genome.bank import Bank, BankError, checked_build
from bridgeforge.genome.bank_reports import (_PARSE_LIMIT_BYTES, REPORT_SCHEMA_VERSION, _blob_bytes, _current_records, _holder,
                                             _mod_key, _root_text, is_trivial_value, vanilla_hashes)



def load_plan(plan_file: Path) -> dict:
    """The alleles plan, checked as put-plan checks it."""
    from bridgeforge.genome.bank_plan import plan_items

    try:
        plan_data = json.loads(Path(plan_file).read_bytes())
    except (OSError, ValueError) as exc:
        raise BankError(f"cannot read the plan {plan_file}: {exc}") from exc
    plan_items(plan_data)  # raises AllelesError (a ValueError) for anything that is not a complete plan
    return plan_data


def bank_side(bank: Bank) -> tuple[dict[str, set[str]], dict[str, list[dict]], set[str], int]:
    """({anchor: mod keys whose current records hold it}, {member blob: holders}, donor-only blobs, unreadable records)."""
    records, unreadable = _current_records(bank)
    anchor_mods: dict[str, set[str]] = defaultdict(set)
    members: dict[str, list[dict]] = defaultdict(list)
    donor: set[str] = set()
    for rid, record in records.items():
        anchor_mods[record.get("anchor")].add(_mod_key(rid, record))
        for path, digest in sorted((record.get("members") or {}).items()):
            members[digest].append(_holder(rid, record, path))
        donor.update((record.get("donor") or {}).values())
    return dict(anchor_mods), dict(members), donor - set(members), len(unreadable)


def candidates(plan_data: dict, anchor_mods: dict[str, set[str]]) -> list[tuple[dict, str]]:
    """(plan row, anchor) for each banked anchor a root defines under a mod id the bank does not hold it for. A root with no
    mod id is always a candidate: it is no banked mod."""
    found = []
    for row in plan_data["roots"]:
        for anchor in row.get("defines") or []:
            holders = anchor_mods.get(anchor)
            if holders is not None and (not row.get("mod_id") or row["mod_id"] not in holders):
                found.append((row, anchor))
    return found


def _describe(base: Path, row: dict, anchor: str, vanilla_core: Path) -> tuple[dict[str, dict], str | None, str | None]:
    """({gene anchor: manifest}, the anchor's refusal, an error) for one candidate, described in memory."""
    from bridgeforge.genome.alleles import MOD_INFO, _sha
    from bridgeforge.genome.gene_set import walk

    root = base / row["path"]
    info = root / MOD_INFO
    if not info.is_file():
        return {}, None, "the root is gone since the plan"
    if row.get("mod_info_sha256") and _sha(info.read_bytes()) != row["mod_info_sha256"]:
        return {}, None, "the root changed since the plan (its mod_info.json differs): write the plan again"
    try:
        genes, refused = walk(root, anchor, Path(vanilla_core), checkpoint_path=None, quiet=True)
    except Exception as exc:  # recorded per candidate and counted; the scan goes on
        return {}, None, f"{type(exc).__name__}: {exc}"[:300]
    return genes, refused.get(anchor), None


def _compare(bank: Bank, genes: dict[str, dict], mod_id: str | None, members: dict[str, list[dict]], donor: set[str],
             vanilla: set[str], excluded: dict[str, int]) -> list[dict]:
    """The candidate's member blobs the bank also holds as members of another mod id, each once; the rest counted apart."""
    shared, seen = [], set()
    for gene_anchor, gene in sorted(genes.items()):
        for member in gene.get("members") or []:
            digest = member.get("sha256")
            if not digest or digest in seen:
                continue
            seen.add(digest)
            holders = members.get(digest)
            if not holders:
                if digest in donor:
                    excluded["donor_side"] += 1
                continue
            data = _blob_bytes(bank, digest, limit=_PARSE_LIMIT_BYTES)
            if data is not None and is_trivial_value(data):
                excluded["trivial_value"] += 1
                continue
            if digest in vanilla:
                excluded["vanilla_file"] += 1
                continue
            others = [holder for holder in holders if holder["mod_id"] != mod_id]
            if not others:
                excluded["same_mod"] += 1
                continue
            shared.append({"sha256": digest, "gene": gene_anchor, "path": member.get("path"), "bank_holders": others})
    return shared


def lineage_scan(plan_file: Path, vanilla_core: Path, *, bank: Path | None = None, base: Path | None = None,
                 quiet: bool = False, checkpoint_path: Path | None = None) -> dict:
    """The lineage-scan report; see the module docstring. Resumable: each finished candidate goes to the checkpoint."""
    from bridgeforge.paths import data_root
    from bridgeforge.progress import Checkpoint, report

    plan_data = load_plan(plan_file)
    target = Bank(bank)
    target.check_folder()
    build = checked_build(target, Path(vanilla_core))  # describe's closure depends on the core: the bank's own build only
    anchor_mods, members, donor, unreadable = bank_side(target)
    vanilla = vanilla_hashes(Path(vanilla_core))
    base = Path(base or data_root())
    items = candidates(plan_data, anchor_mods)
    excluded = {"donor_side": 0, "trivial_value": 0, "vanilla_file": 0, "same_mod": 0}
    rows = []
    # The plan and the bank go in as digests: a new plan or a changed bank must restart the scan, not resume it.
    head = {"command": "gene bank lineage-scan", "plan": _digest(plan_data), "bank_root": _root_text(target), "build": build}
    with Checkpoint(checkpoint_path, head) as checkpoint:
        for number, (row, anchor) in enumerate(items, 1):
            key = f"{row['path']}|{row.get('mod_info_sha256')}|{anchor}"
            saved, started = checkpoint.get(key), time.monotonic()
            resumed = saved is not None
            if saved is None:
                genes, refused, error = _describe(base, row, anchor, Path(vanilla_core))
                counts = dict.fromkeys(excluded, 0)
                shared = _compare(target, genes, row.get("mod_id"), members, donor, vanilla, counts) if genes else []
                saved = {"path": row["path"], "folder": row.get("folder"), "mod_id": row.get("mod_id"),
                         "mod_version": row.get("mod_version"), "anchor": anchor, "genes": len(genes),
                         "refused": refused, "error": error, "shared": shared, "excluded": counts}
                if not error:
                    checkpoint.add(key, saved)
            for name, count in saved["excluded"].items():
                excluded[name] += count
            rows.append(saved)
            if not quiet:
                state = (f"error: {saved['error']}" if saved["error"] else f"refused: {saved['refused']}" if saved["refused"]
                         else f"{len(saved['shared'])} shared of {saved['genes']} gene(s)")
                report(number, len(items), f"{anchor} in {row['path']}", state, None if resumed else time.monotonic() - started)
    shared_blobs = {blob["sha256"] for row in rows for blob in row["shared"]}
    counts = {"plan_roots": len(plan_data["roots"]), "candidates": len(rows),
              "described": sum(1 for r in rows if not r["error"] and not r["refused"]),
              "refused": sum(1 for r in rows if r["refused"]), "errors": sum(1 for r in rows if r["error"]),
              "unreadable_current_records": unreadable, "shared_blobs": len(shared_blobs),
              "candidates_sharing": sum(1 for r in rows if r["shared"]),
              "mod_ids_sharing": len({r["mod_id"] for r in rows if r["shared"]}), "excluded": excluded}
    return {"schema_version": REPORT_SCHEMA_VERSION, "report": "lineage-scan", "root": _root_text(target), "build": build,
            "plan_corpus": plan_data["corpus"], "counts": counts, "candidates": rows}


def _digest(data: dict) -> str:
    import hashlib

    return hashlib.sha256(json.dumps(data, sort_keys=True).encode("utf-8")).hexdigest()


def run_lineage_scan_cli(args) -> int:
    """`gene bank lineage-scan PLAN --out OUT --vanilla-core CORE`: write the report and print its counts."""
    import sys

    from bridgeforge.genome.alleles import AllelesError
    from bridgeforge.genome.bank_reports import write_report

    target = Bank(args.bank)
    checkpoint = Path(args.out).with_name(Path(args.out).name + ".partial.jsonl")
    try:
        result = lineage_scan(args.plan, args.vanilla_core, bank=args.bank, quiet=args.quiet, checkpoint_path=checkpoint)
        out = write_report(target, args.out, result)
    except (AllelesError, BankError, OSError, ValueError) as exc:
        print(f"bridgeforge: {exc}", file=sys.stderr)
        return 2
    counts = result["counts"]
    if checkpoint.is_file() and not counts["errors"]:
        checkpoint.unlink()  # kept while errors remain, so a resume retries them
    excluded = counts["excluded"]
    print(f"lineage-scan: {counts['shared_blobs']} shared blob(s) in {counts['candidates_sharing']} of {counts['candidates']} "
          f"candidate(s) ({counts['mod_ids_sharing']} mod id(s)); described {counts['described']}, refused {counts['refused']}, "
          f"errors {counts['errors']}; excluded: donor side {excluded['donor_side']}, trivial value {excluded['trivial_value']}, "
          f"vanilla file {excluded['vanilla_file']}, same mod {excluded['same_mod']}; build {result['build']}; ROOT "
          f"{result['root']}; wrote {out}")
    return 1 if counts["errors"] else 0


__all__ = ["bank_side", "candidates", "lineage_scan", "load_plan", "run_lineage_scan_cli"]
