"""`gene bank lineage-scan PLAN --out OUT --vanilla-core CORE`: lineage beyond the bank (94.G3 slice 3b, docs/GENE_BANK_DESIGN.md).

Slice 3a found no member blob that two mod ids' banked records share, and the 2a plan over `Done/` found no root outside the
pilot families defining a banked anchor. So lineage has to look at a wider corpus: the owner chose Test1's `In operation/`
(2026-11-27, "that sounds fine"; White_Legion's mod folder too if needed).

A candidate is a root of an alleles plan (`gene bank alleles CORPUS --out PLAN`) that defines one or more of the bank's anchors
under a mod the bank does not hold them for; a root with no mod id is keyed by its path, as slice 3a keys an id-less source.
Each candidate root is described in memory once, walking each of its candidate anchors with the walk `put` uses
(`gene_set.walk`), and the member hashes of every gene the walks reach are compared with the bank's member blobs. Nothing is
put, and nothing is written into the bank: the CLI refuses an output or checkpoint inside the bank before it starts, and the
report goes through slice 3a's `write_report`. Hashes carry no direction, so a match is "shared by", never "copied from".

Each blob a candidate's genes hold as a member is classified once, in this order:
- `donor_side`: the bank holds it only as a donor need, not as a member (the candidate's own donor needs are not compared);
- `same_mod`: every bank holder is the candidate's own mod (an allele, or another banked gene of that mod);
- `trivial_value`: a JSON number, boolean, null, empty value or short string;
- `vanilla_file`: a blob equal to a whole file of the core's `data/` (so a CSV row or JSON entry never matches, as in 3a);
- shared: the rest, with the bank's holders of other mods.
Counts are of distinct blobs across the scan, so a root reached by several candidates, or a resumed row, counts once.

The report names mods and members, so it stays on the machine; the roadmap records counts only.
"""
from __future__ import annotations

import hashlib
import json
import time
from collections import defaultdict
from pathlib import Path

from bridgeforge.genome.bank import Bank, BankError, checked_build
from bridgeforge.genome.bank_reports import (_PARSE_LIMIT_BYTES, REPORT_SCHEMA_VERSION, _blob_bytes, _current_records, _holder,
                                             _mod_key, _root_text, is_inside, is_trivial_value, vanilla_hashes)

BUCKETS = ("donor_side", "same_mod", "trivial_value", "vanilla_file")


def load_plan(plan_file: Path) -> dict:
    """The alleles plan, checked as put-plan checks it."""
    from bridgeforge.genome.bank_plan import plan_items

    try:
        plan_data = json.loads(Path(plan_file).read_bytes())
    except (OSError, ValueError) as exc:
        raise BankError(f"cannot read the plan {plan_file}: {exc}") from exc
    plan_items(plan_data)  # raises AllelesError (a ValueError) for anything that is not a complete plan
    if not isinstance(plan_data.get("anchors"), list):
        raise BankError(f"{plan_file} lists no anchors: write it again with gene bank alleles")
    return plan_data


def bank_side(bank: Bank) -> tuple[dict[str, set[str]], dict[str, list[dict]], set[str], int, set[str]]:
    """({anchor: mod keys whose current records hold it}, {member blob: holders}, donor-only blobs, unreadable records,
    the builds the current records were described against)."""
    records, unreadable = _current_records(bank)
    anchor_mods: dict[str, set[str]] = defaultdict(set)
    members: dict[str, list[dict]] = defaultdict(list)
    donor: set[str] = set()
    for rid, record in records.items():
        anchor_mods[record.get("anchor")].add(_mod_key(rid, record))
        for path, digest in sorted((record.get("members") or {}).items()):
            members[digest].append(_holder(rid, record, path))
        donor.update((record.get("donor") or {}).values())
    builds = {str(record.get("build")) for record in records.values()}
    return dict(anchor_mods), dict(members), donor - set(members), len(unreadable), builds


def row_mod(row: dict) -> str:
    """A plan row's mod key, made as slice 3a makes a record's: its id, or for a root without one, its path."""
    mod_id = row.get("mod_id")
    return mod_id if isinstance(mod_id, str) and mod_id else f"(no mod id: {row['path']})"


def candidates(plan_data: dict, anchor_mods: dict[str, set[str]]) -> list[tuple[dict, list[str]]]:
    """(plan row, its candidate anchors) for each root defining banked anchors under a mod the bank does not hold them for."""
    found = []
    for row in plan_data["roots"]:
        mod = row_mod(row)
        anchors = [a for a in row.get("defines") or [] if a in anchor_mods and mod not in anchor_mods[a]]
        if anchors:
            found.append((row, anchors))
    return found


def _describe(base: Path, row: dict, anchors: list[str], vanilla_core: Path) -> tuple[dict[str, dict], dict[str, str], str | None]:
    """({gene anchor: manifest} over every candidate anchor's walk, {need: why describe refused it}, an error) for one root,
    described in memory. An anchor an earlier walk of the root already reached is not walked again."""
    from bridgeforge.genome.alleles import MOD_INFO, _sha
    from bridgeforge.genome.gene_set import walk

    root = base / row["path"]
    genes: dict[str, dict] = {}
    refused: dict[str, str] = {}
    try:
        info = root / MOD_INFO
        if not info.is_file():
            return {}, {}, "the root is gone since the plan"
        if row.get("mod_info_sha256") and _sha(info.read_bytes()) != row["mod_info_sha256"]:
            return {}, {}, "the root changed since the plan (its mod_info.json differs): write the plan again"
        for anchor in anchors:
            if anchor in genes or anchor in refused:
                continue
            found, why = walk(root, anchor, Path(vanilla_core), checkpoint_path=None, quiet=True)
            genes.update(found)
            refused.update(why)
    except Exception as exc:  # recorded per root and counted; the scan goes on
        return {}, {}, f"{type(exc).__name__}: {exc}"[:300]
    return genes, refused, None


def _classify(bank: Bank, genes: dict[str, dict], mod: str, members: dict[str, list[dict]], donor: set[str],
              vanilla: set[str]) -> tuple[list[dict], dict[str, list[str]]]:
    """(the shared blobs with their bank holders of other mods, {bucket: digests counted apart}); each digest once."""
    shared, buckets, seen = [], {name: [] for name in BUCKETS}, set()
    for gene_anchor, gene in sorted(genes.items()):
        for member in gene.get("members") or []:
            digest = member.get("sha256")
            if not digest or digest in seen:
                continue
            seen.add(digest)
            holders = members.get(digest)
            if not holders:
                if digest in donor:
                    buckets["donor_side"].append(digest)
                continue
            others = [holder for holder in holders if holder["mod_id"] != mod]
            if not others:
                buckets["same_mod"].append(digest)
                continue
            data = _blob_bytes(bank, digest, limit=_PARSE_LIMIT_BYTES)
            if data is not None and is_trivial_value(data):
                buckets["trivial_value"].append(digest)
                continue
            if digest in vanilla:
                buckets["vanilla_file"].append(digest)
                continue
            shared.append({"sha256": digest, "gene": gene_anchor, "path": member.get("path"), "bank_holders": others})
    return shared, buckets


def _check_inputs(plan_data: dict, base: Path, anchor_mods: dict[str, set[str]], builds: set[str], build: str) -> None:
    """Refuse what would make a quiet, wrong report (review of slice 3b)."""
    corpus = base / plan_data["corpus"]
    if not corpus.is_dir():
        raise BankError(f"the plan's corpus {plan_data['corpus']} is not under {base}: run the scan where the plan was made")
    unplanned = sorted(set(anchor_mods) - set(plan_data["anchors"]))
    if unplanned:
        raise BankError(f"the bank now holds {len(unplanned)} anchor(s) the plan did not look for (such as {unplanned[0]}): "
                        "write the plan again with gene bank alleles")
    other = sorted(builds - {build})
    if other:
        raise BankError(f"the core reports {build}, but current records were described against {', '.join(other)}")


def lineage_scan(plan_file: Path, vanilla_core: Path, *, bank: Path | None = None, base: Path | None = None,
                 quiet: bool = False, checkpoint_path: Path | None = None) -> dict:
    """The lineage-scan report; see the module docstring. Resumable: each finished root goes to the checkpoint."""
    from bridgeforge.paths import data_root
    from bridgeforge.progress import Checkpoint, report

    plan_data = load_plan(plan_file)
    target = Bank(bank)
    target.check_folder()
    build = checked_build(target, Path(vanilla_core))  # describe's closure depends on the core: the bank's own build only
    anchor_mods, members, donor, unreadable, builds = bank_side(target)
    base = Path(base or data_root())
    _check_inputs(plan_data, base, anchor_mods, builds, build)
    vanilla = vanilla_hashes(Path(vanilla_core))
    items = candidates(plan_data, anchor_mods)
    rows = []
    # The plan, the bank and the core's data go in as digests: any change must restart the scan, not resume it.
    head = {"command": "gene bank lineage-scan", "plan": _digest(plan_data), "bank_root": _root_text(target), "build": build,
            "vanilla": _digest(sorted(vanilla))}
    with Checkpoint(checkpoint_path, head) as checkpoint:
        for number, (row, anchors) in enumerate(items, 1):
            key = f"{row['path']}|{row.get('mod_info_sha256')}|{','.join(anchors)}"
            saved, started = checkpoint.get(key), time.monotonic()
            resumed = saved is not None
            if saved is None:
                genes, refused, error = _describe(base, row, anchors, Path(vanilla_core))
                shared, buckets = _classify(target, genes, row_mod(row), members, donor, vanilla) if genes else ([], {})
                saved = {"path": row["path"], "folder": row.get("folder"), "mod_id": row.get("mod_id"),
                         "mod_version": row.get("mod_version"), "anchors": anchors, "genes": len(genes),
                         "anchors_refused": {a: refused[a] for a in anchors if a in refused},
                         "needs_refused": {need: why for need, why in refused.items() if need not in anchors},
                         "error": error, "shared": shared, "counted_apart": buckets}
                if not error:
                    checkpoint.add(key, saved)
            rows.append(saved)
            if not quiet:
                state = (f"error: {saved['error']}" if saved["error"] else
                         f"{len(saved['shared'])} shared of {saved['genes']} gene(s)"
                         + (f", {len(saved['anchors_refused'])} anchor(s) refused" if saved["anchors_refused"] else ""))
                report(number, len(items), f"{len(anchors)} anchor(s) in {row['path']}", state,
                       None if resumed else time.monotonic() - started)
    return {"schema_version": REPORT_SCHEMA_VERSION, "report": "lineage-scan", "root": _root_text(target), "build": build,
            "plan_corpus": plan_data["corpus"], "counts": _counts(plan_data, rows, unreadable), "candidates": rows}


def _counts(plan_data: dict, rows: list[dict], unreadable: int) -> dict:
    sharing = [r for r in rows if r["shared"]]
    excluded = {name: len({d for r in rows for d in (r.get("counted_apart") or {}).get(name, [])}) for name in BUCKETS}
    return {"plan_roots": len(plan_data["roots"]), "plan_errors": int(plan_data["summary"].get("errors") or 0),
            "candidate_roots": len(rows), "candidate_anchors": sum(len(r["anchors"]) for r in rows),
            "described": sum(1 for r in rows if not r["error"] and len(r["anchors_refused"]) < len(r["anchors"])),
            "anchors_refused": sum(len(r["anchors_refused"]) for r in rows),
            "needs_refused": sum(len(r["needs_refused"]) for r in rows), "errors": sum(1 for r in rows if r["error"]),
            "unreadable_current_records": unreadable,
            "shared_blobs": len({blob["sha256"] for r in rows for blob in r["shared"]}),
            "roots_sharing": len(sharing), "mod_ids_sharing": len({row_mod(r) for r in sharing}), "excluded": excluded}


def _digest(data) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode("utf-8")).hexdigest()


def run_lineage_scan_cli(args) -> int:
    """`gene bank lineage-scan PLAN --out OUT --vanilla-core CORE`: write the report and print its counts."""
    import sys

    from bridgeforge.genome.alleles import AllelesError
    from bridgeforge.genome.bank_reports import write_report

    target = Bank(args.bank)
    out = Path(args.out)
    checkpoint = out.with_name(out.name + ".partial.jsonl")
    # Before anything is written: the checkpoint sits beside the report, and a file inside the bank makes put, rebuild and
    # verify refuse it (review of slice 3b, HIGH).
    if is_inside(out, target.root) or is_inside(checkpoint, target.root):
        print(f"bridgeforge: {out} is inside the bank {target.root}, which must hold only its own files: write it elsewhere",
              file=sys.stderr)
        return 2
    try:
        result = lineage_scan(args.plan, args.vanilla_core, bank=args.bank, quiet=args.quiet, checkpoint_path=checkpoint)
        written = write_report(target, out, result)
    except (AllelesError, BankError, OSError, ValueError) as exc:
        print(f"bridgeforge: {exc}", file=sys.stderr)
        return 2
    counts = result["counts"]
    if checkpoint.is_file() and not counts["errors"]:
        checkpoint.unlink()  # kept while errors remain, so a resume retries them
    excluded = counts["excluded"]
    print(f"lineage-scan: {counts['shared_blobs']} shared blob(s) in {counts['roots_sharing']} of {counts['candidate_roots']} "
          f"candidate root(s) ({counts['mod_ids_sharing']} mod(s); {counts['candidate_anchors']} anchor(s)); described "
          f"{counts['described']}, anchors refused {counts['anchors_refused']}, needs refused {counts['needs_refused']}, errors "
          f"{counts['errors']} (plan errors {counts['plan_errors']}); counted apart: donor side {excluded['donor_side']}, same mod "
          f"{excluded['same_mod']}, trivial value {excluded['trivial_value']}, vanilla file {excluded['vanilla_file']}; build "
          f"{result['build']}; ROOT {result['root']}; wrote {written}")
    return 1 if counts["errors"] else 0


__all__ = ["BUCKETS", "bank_side", "candidates", "lineage_scan", "load_plan", "row_mod", "run_lineage_scan_cli"]
