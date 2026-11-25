"""94.G3 slice 2b: `gene bank put-plan`, putting the allele plan (docs/GENE_BANK_DESIGN.md, "Slice 2").

`gene bank alleles` (alleles.py) writes the denominator; this puts every pilot copy it names into the bank. describe's
refusal of an anchor becomes a `sources.json` line and an `entries.json` row with no records and the reason, so the bank
records every copy as stored or refused. Any other failure is an error in the report and is never banked.

Nothing here can be undone in the bank (no command removes a `sources.json` line), so a plan is refused before anything is
put when it is not a plan, was made for a bank with other pilots, or is run with a core of another build; a copy whose
`mod_info.json` changed since the plan is an error, not a put (review of slice 2b).
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from bridgeforge.genome.alleles import MOD_INFO, PLAN_SCHEMA, PLAN_VERSION, AllelesError, bank_anchors, write_plan

_PLAN_KEYS = ("corpus", "pilot_anchors", "roots", "zips", "unread_archives", "skipped", "summary")


def plan_items(plan_data: dict) -> list[tuple[str, str, str, str | None]]:
    """(path, folder kind, pilot anchor, mod_info.json hash) for every root of a plan that defines a pilot anchor. Needed-gene
    hits elsewhere are slice 3's lineage input, not puts (advisor 2026-11-23). Every key the report reads is checked
    here, before any put."""
    if not isinstance(plan_data, dict) or plan_data.get("schema") != PLAN_SCHEMA or plan_data.get("schema_version") != PLAN_VERSION:
        raise AllelesError(f"not a {PLAN_SCHEMA} plan of version {PLAN_VERSION}")
    missing = [key for key in _PLAN_KEYS if key not in plan_data]
    if missing or "errors" not in plan_data["summary"]:
        raise AllelesError(f"the plan lacks {', '.join(missing) or 'summary.errors'}: write it again with gene bank alleles")
    pilots = plan_data["pilot_anchors"]
    return [(row["path"], row["folder"], anchor, row.get("mod_info_sha256")) for row in plan_data["roots"]
            for anchor in pilots if anchor in row["defines"]]


def _changed_since_plan(root: Path, planned: str | None) -> bool:
    info = root / MOD_INFO
    return not info.is_file() or hashlib.sha256(info.read_bytes()).hexdigest() != planned


def put_plan(plan_file: Path, vanilla_core: Path, *, bank: Path | None = None, quiet: bool = False,
             base: Path | None = None) -> dict:
    """Put every pilot copy a plan names (`put(..., record_refusal=True)`). Resumable: finished items are kept in the bank's
    `put-plan.partial.jsonl`; an item that failed is not, so a resume tries it again. The CLI deletes the checkpoint only
    when the report holds no error."""
    from bridgeforge.genome.bank import PUT_PLAN_CHECKPOINT, Bank, checked_build
    from bridgeforge.paths import data_root
    from bridgeforge.progress import Checkpoint, report

    raw = Path(plan_file).read_bytes()
    plan_data = json.loads(raw)
    items = plan_items(plan_data)
    target = Bank(bank)
    target.check_folder()
    pilots = bank_anchors(target.root)[0]
    if sorted(plan_data["pilot_anchors"]) != pilots:
        raise AllelesError(f"the plan was made for the pilots {', '.join(plan_data['pilot_anchors'])}; this bank's are "
                           f"{', '.join(pilots)}")
    build = checked_build(target, vanilla_core)
    base = Path(base or data_root())
    head = {"command": "gene bank put-plan", "plan": hashlib.sha256(raw).hexdigest(), "build": build}
    results = []
    with Checkpoint(target.root / PUT_PLAN_CHECKPOINT, head) as checkpoint:
        for number, (path, folder, anchor, planned) in enumerate(items, 1):
            key = f"{path}|{folder}|{anchor}"
            saved, started = checkpoint.get(key), time.monotonic()
            resumed = saved is not None
            if saved is None:
                saved = _put_one(target, base, path, folder, anchor, planned, vanilla_core, build)
                if not saved["error"]:
                    checkpoint.add(key, saved)
            results.append({"path": path, "folder": folder, "anchor": anchor, **saved})
            if not quiet:
                state = saved["error"] or (f"refused: {saved['refused']}" if saved["refused"] else f"{saved['stored']} gene(s)")
                report(number, len(items), f"{anchor} from {path}", state, None if resumed else time.monotonic() - started)
    return plan_report(target, plan_data, results)


def _put_one(target, base: Path, path: str, folder: str, anchor: str, planned: str | None, vanilla_core: Path,
             build: str) -> dict:
    """{stored, refused, error} for one copy. A failure after its `sources.json` line was written says so: the bank then
    holds the line, and a resume or a rebuild completes it."""
    from bridgeforge.genome.bank import put

    if _changed_since_plan(base / path, planned):
        return {"stored": 0, "refused": None, "error": "its mod_info.json changed since the plan: run gene bank alleles again"}
    try:
        result = put(base / path, anchor, Path(vanilla_core), folder=folder, bank=target.root, base=base, record_refusal=True)
    except Exception as exc:  # reported; a resume tries it again
        line = {"path": path, "folder": folder, "anchor": anchor, "build": build}
        state = "partly written (its sources line is in the bank)" if line in target.sources() else "never banked"
        return {"stored": 0, "refused": None, "error": f"{state}: {type(exc).__name__}: {exc}"}
    return {"stored": result["stored"], "refused": result["anchor_refused"], "error": None}


def plan_report(target, plan_data: dict, results: list[dict]) -> dict:
    """Per pilot anchor: the copies the plan named, stored, refused and failed, and the distinct manifests (the alleles)
    and distinct identities among the stored copies and across the whole bank. A manifest also carries the mod's version
    and provenance, so two copies of one feature in two releases are two manifests but one identity (review of slice 2b)."""
    records = target.records()
    current = [records[rid] for rid in target.current_ids() if rid in records]
    anchors = {}
    for anchor in plan_data["pilot_anchors"]:
        rows = [r for r in results if r["anchor"] == anchor]
        paths = {r["path"] for r in rows if r["stored"]}
        mine = [r for r in current if r["anchor"] == anchor]
        stored = [r for r in mine if r["source"]["path"] in paths]
        anchors[anchor] = {"copies": len(rows), "stored": len(paths), "refused": sum(1 for r in rows if r["refused"]),
                           "errors": sum(1 for r in rows if r["error"]),
                           "alleles_from_plan": len({r["manifest"] for r in stored}),
                           "identities_from_plan": len({r["identity"] for r in stored}),
                           "alleles_in_bank": len({r["manifest"] for r in mine}),
                           "identities_in_bank": len({r["identity"] for r in mine})}
    zip_states = [z["state"] for z in plan_data["zips"]]
    return {"plan_corpus": plan_data["corpus"], "items": results, "anchors": anchors,
            "errors": sum(1 for r in results if r["error"]), "refused": sum(1 for r in results if r["refused"]),
            "not_described": {"zips_archive_only": sum(1 for s in zip_states if s.startswith("archive only")),
                              "zips_unreadable": sum(1 for s in zip_states if s.startswith("unreadable")),
                              "zips_no_mod": sum(1 for s in zip_states if s == "no mod"),
                              "unread_archives": len(plan_data["unread_archives"]), "skipped_copies": len(plan_data["skipped"]),
                              "plan_errors": plan_data["summary"]["errors"]},
            "root": target.root_hash()}


def run_put_plan_cli(args) -> int:
    import sys

    from bridgeforge.genome.bank import PUT_PLAN_CHECKPOINT, Bank, BankError

    try:
        result = put_plan(args.plan, args.vanilla_core, bank=args.bank, quiet=args.quiet)
        write_plan(result, args.report)
    except (AllelesError, BankError, OSError, ValueError, KeyError) as exc:
        print(f"bridgeforge: {exc}", file=sys.stderr)
        return 2
    checkpoint = Bank(args.bank).root / PUT_PLAN_CHECKPOINT
    if checkpoint.is_file() and not result["errors"]:
        checkpoint.unlink()  # kept while errors remain, so the next run retries only those
    print(f"{len(result['items'])} copies; {result['refused']} refused, {result['errors']} error(s); ROOT {result['root']}")
    for anchor, row in result["anchors"].items():
        print(f"  {anchor}: {row['stored']} of {row['copies']} stored, {row['refused']} refused, {row['errors']} error(s); "
              f"{row['alleles_from_plan']} allele(s) ({row['identities_from_plan']} identities) among them, "
              f"{row['alleles_in_bank']} ({row['identities_in_bank']}) in the bank")
    return 1 if result["errors"] else 0


__all__ = ["plan_items", "plan_report", "put_plan", "run_put_plan_cli"]
