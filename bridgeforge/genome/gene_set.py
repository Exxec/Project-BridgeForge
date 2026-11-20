"""94.G2 slice 11: a gene set's carrier and its static isolation proof (2026-11-20).

P3's star system (`star-system:Pantheon`) needs `faction:EridaniCombine`, and the faction needs 54 of Eridani's content genes.
A carrier holding only the system cannot boot, so this builds one carrier from the anchor gene and every gene its
`needs.genes` name, in turn (measured on P3: 56 genes, 183 of 471 shipped files, 26 of 36 jar classes).

- **The walk.** Each needed gene is described once, breadth first. A need `describe` refuses (a kind not closable, an id the
  mod lacks) is recorded as refused, not dropped, and the proof FAILs. Each finished gene goes to a checkpoint beside
  `--out`, so an interrupted walk resumes (CLAUDE.md, long-running commands); a checkpoint made before the mod or the core
  changed (a fingerprint of paths, sizes and times) is not resumed.
- **Members.** A path two genes hold is written once. The same path with another hash is refused, never last-wins
  (advisor 2026-11-20); a jar entry is therefore written once. A file one gene holds whole and another in part (a row, a
  JSON entry, a class) is refused too.
- **The carrier.** It is built by `proof.build_carrier`, so a single gene's carrier is unchanged. Its id comes from the sorted
  identities of the carried genes. Only a star system's registration is made (the generated plugin). Every other recorded
  registration, such as the faction's `getFaction` call, is listed as not made.
- **Isolation.** What the carrier's scan finds unresolved may name only the set's `provides` and its vanilla needs. The
  single-gene allowance for `needs.genes` is dropped. An unresolved reference naming a set id means a gene's closure misses
  a member: that is a finding, not something to tune away.
- **Resolution (slice 12).** The scan alone was blind: P3's set still passed with a weapon, a hull or the faction knocked
  out, since the scanner checks neither faction lists nor a faction's presence. So every anchor a carried gene provides or
  needs must also be defined in the built carrier (a table row or spec, a listed .faction, a star system's generator, a
  registered combat plugin's class, a campaign row or key); one that is not FAILs the set.
- **Suspects** are bucketed by file. The ids they mention that the set does not provide and no carried gene lists as a
  vanilla need are listed as `not_carried`, so a boot Fatal can be explained later.

The proof is one evidence file, `set-isolation-proof.json`, with the anchor gene's header (the header allows added fields):
`carried` names each gene's anchor and identity, and every carried member file is an input. Static half only: `gene boot`
is not built.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

from bridgeforge.genome.carrier_plugin import CarrierPluginRefused
from bridgeforge.genome.evidence import header
from bridgeforge.genome.gene import GeneError, describe, dumps
from bridgeforge.genome.proof import ProofError, build_carrier, classify_isolation
from bridgeforge.licence_ledger import member_file
from bridgeforge.progress import Checkpoint, report
from bridgeforge.safeio import atomic_write_text

SET_PROOF = "set-isolation-proof"


def fingerprint(folder: Path | None) -> str | None:
    """A digest of every file's relative path, size and modification time under `folder`: a checkpoint made before the mod
    or the core changed is not resumed (review 2026-11-20: it would replay old manifests)."""
    if folder is None or not Path(folder).is_dir():
        return None
    digest = hashlib.sha256()
    for path in sorted(p for p in Path(folder).rglob("*") if p.is_file()):
        stat = path.stat()
        digest.update(f"{path.relative_to(folder).as_posix()}\0{stat.st_size}\0{stat.st_mtime_ns}\n".encode("utf-8", "replace"))
    return digest.hexdigest()


def walk(mod: Path, anchor: str, vanilla_core: Path | None, *, checkpoint_path: Path | None = None,
         quiet: bool = False) -> tuple[dict[str, dict], dict[str, str]]:
    """({anchor: manifest}, {anchor: why describe refused it}) for `anchor` and every gene its needs.genes name, in turn."""
    head = {"command": "gene prove-set", "mod": str(Path(mod).resolve()), "anchor": anchor,
            "vanilla_core": str(Path(vanilla_core).resolve()) if vanilla_core else None}
    if checkpoint_path is not None:
        from bridgeforge.vendor_plan import VendorPlanError, _mod_root

        try:
            content = _mod_root(Path(mod))  # working/, not the workspace: the checkpoint itself may sit in the workspace
        except VendorPlanError:
            content = Path(mod)
        head["fingerprint"] = [fingerprint(content), fingerprint(Path(vanilla_core) if vanilla_core else None)]
    genes: dict[str, dict] = {}
    refused: dict[str, str] = {}
    queue, seen = [anchor], {anchor}
    with Checkpoint(checkpoint_path, head) as checkpoint:
        while queue:
            current = queue.pop(0)
            saved = checkpoint.get(current)
            resumed, started = saved is not None, time.monotonic()
            if saved is None:
                try:
                    saved = {"gene": describe(mod, current, vanilla_core=vanilla_core)}
                except GeneError as exc:
                    saved = {"refused": str(exc)}
                checkpoint.add(current, saved)
            if "gene" in saved:
                genes[current] = saved["gene"]
                fresh = [need for need in dict.fromkeys(saved["gene"]["needs"].get("genes") or []) if need not in seen]
                seen.update(fresh)
                queue += fresh
                detail = f"{len(saved['gene']['members'])} member(s), {len(fresh)} new gene need(s)"
            else:
                refused[current] = saved["refused"]
                detail = f"refused: {saved['refused']}"
            if not quiet:
                report(len(genes) + len(refused), len(seen), current, detail, None if resumed else time.monotonic() - started)
    return genes, refused


def merge_members(genes: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    """(each member path once, conflicts). A path two genes hold with different hashes is a conflict, and so is a file one
    gene holds whole while another holds part of it (a row, a JSON entry, a jar class): the carrier would write the file
    twice over (review 2026-11-20)."""
    merged: dict[tuple[str, str], dict] = {}
    owner: dict[tuple[str, str], str] = {}
    conflicts = []
    for anchor in sorted(genes):
        for member in genes[anchor]["members"]:
            key = (member["what"], member["path"])
            if key not in merged:
                merged[key], owner[key] = member, anchor
            elif merged[key]["sha256"] != member["sha256"]:
                conflicts.append({"path": member["path"], "genes": [owner[key], anchor]})
    whole = {path: owner[(what, path)] for what, path in merged if what == "file"}
    for what, path in sorted(merged):
        if what != "file" and member_file(path) in whole:
            conflicts.append({"path": path, "genes": [whole[member_file(path)], owner[(what, path)]]})
    return [merged[key] for key in sorted(merged)], conflicts


def set_identity(genes: dict[str, dict]) -> str:
    """The carried set's digest, from the sorted identities of its genes (order and anchors do not change it)."""
    return hashlib.sha256("\n".join(sorted(g["identity"] for g in genes.values())).encode("ascii")).hexdigest()


def registrations_not_made(genes: dict[str, dict], made_by: str | None) -> list[dict]:
    """Every registration a carried gene records that the carrier does not make: only `made_by`'s (the star system the
    generated plugin calls) is made."""
    return [{"gene": anchor, **element} for anchor in sorted(genes) if anchor != made_by
            for element in genes[anchor].get("registrations") or []]


def _ids(anchors: set[str]) -> set[str]:
    return {a.split(":", 1)[1] for a in anchors if ":" in a}


def suspect_buckets(genes: dict[str, dict]) -> tuple[dict[str, list[dict]], list[dict]]:
    """({file: [suspect with its gene]}, [{file, id}] mentioned ids the set does not provide and no carried gene lists as a
    vanilla need). A suspect without a file path (a gene's own anchor) is bucketed under that path. An id the core has but
    no gene lists still counts: suspect mentions are untyped, so they cannot be looked up in the core."""
    provided = _ids({p for g in genes.values() for p in g["provides"]})
    vanilla = _ids({v for g in genes.values() for v in g["needs"]["vanilla"]})
    buckets: dict[str, list[dict]] = {}
    absent: set[tuple[str, str]] = set()
    for anchor in sorted(genes):
        for suspect in genes[anchor]["unknowns"]["suspects"]:
            path = suspect.get("path") or ""
            file = path.split("#", 1)[0].split("!", 1)[0]
            buckets.setdefault(file, []).append({"gene": anchor, **suspect})
            absent |= {(file, m) for m in suspect.get("mentions") or [] if m not in provided and m not in vanilla}
    return {f: buckets[f] for f in sorted(buckets)}, [{"file": f, "id": i} for f, i in sorted(absent)]


def carried_order(anchor: str, genes: dict[str, dict]) -> list[str]:
    """The anchor first, then the others sorted."""
    return [anchor] + sorted(a for a in genes if a != anchor)


def _class_present(index, dotted: str) -> bool:
    return dotted in index.jar_classes or dotted in index.sources


def _anchor_missing(carrier: Path, anchor: str, index, campaign) -> str | None:
    """Why the built carrier does not define `anchor`, or None when it does."""
    from bridgeforge.genome.campaign import CAMPAIGN_CSV, CAMPAIGN_JSON, resolve_star_system
    from bridgeforge.genome.closure import _settings
    from bridgeforge.genome.faction import FACTIONS_CSV
    from bridgeforge.genome.gene import keyed_rows
    from bridgeforge.vendor_plan import KINDS

    kind, _, ident = anchor.partition(":")
    if kind in KINDS:
        return None if index.defines(kind, ident) else f"no {kind} definition of {ident} in the carrier"
    if kind == "faction":
        path = campaign.factions.get(ident)
        if path is None:
            return "no .faction file with that id in the carrier"
        return None if path in keyed_rows(carrier, FACTIONS_CSV) else f"the carrier's {FACTIONS_CSV} does not list {path}"
    if kind == "star-system":
        try:
            resolve_star_system(carrier, ident)
        except GeneError as exc:
            return str(exc)
        return None
    if kind == "combat-plugin":
        plugins = _settings(carrier).get("plugins")
        plugin_class = plugins.get(ident) if isinstance(plugins, dict) else None
        if not isinstance(plugin_class, str):
            return "the carrier's settings.json registers no plugin under that key"
        return None if _class_present(index, plugin_class.strip()) else f"the carrier holds no class {plugin_class.strip()}"
    if kind in CAMPAIGN_CSV:
        return None if ident in campaign.rows.get(kind, {}) else f"no {CAMPAIGN_CSV[kind]} row {ident} in the carrier"
    if kind in CAMPAIGN_JSON:
        return None if ident in campaign.keys.get(kind, {}) else f"no {CAMPAIGN_JSON[kind]} key {ident} in the carrier"
    return f"kind {kind} is not checked in a carrier"


def unresolved_in_carrier(carrier: Path, genes: dict[str, dict]) -> list[dict]:
    """Each anchor a carried gene provides or needs (`needs.genes`) that the built carrier does not define, with the genes
    naming it. A knock-out of P3's closure (2026-11-20) passed the scan-based isolation with a weapon, a hull or even the
    faction removed: the scanner checks neither faction lists nor a faction's presence. This check sees each of them."""
    from bridgeforge.genome.campaign import _CampaignIndex
    from bridgeforge.vendor_plan import _Index

    named: dict[str, set[str]] = {}
    for anchor, gene in genes.items():
        for wanted in [*gene["provides"], *(gene["needs"].get("genes") or [])]:
            named.setdefault(wanted, set()).add(anchor)
    index, campaign = _Index(Path(carrier)), _CampaignIndex(Path(carrier))
    result = []
    for wanted in sorted(named):
        why = _anchor_missing(Path(carrier), wanted, index, campaign)
        if why:
            result.append({"anchor": wanted, "named_by": sorted(named[wanted]), "why": why})
    return result


def _manifest_name(number: int, anchor: str) -> str:
    kind, _, ident = anchor.partition(":")
    return f"{number:03d}-{kind}-{re.sub(r'[^A-Za-z0-9_.-]', '_', ident)[:80]}.json"


def prove_set(mod: Path, anchor: str, out: Path, *, vanilla_core: Path | None, quiet: bool = False) -> dict:
    """Write the anchor's gene.json, each carried manifest under closure/, the set carrier under work/carrier and
    set-isolation-proof.json into `out` (a new or empty folder outside the repository)."""
    from bridgeforge.models import TargetProfile
    from bridgeforge.scan.scanner import scan_mod
    from bridgeforge.vendor_plan import _mod_root

    out, mod = Path(out), Path(mod)
    if out.exists() and any(out.iterdir()):
        raise ProofError(f"{out} is not empty: proofs go into a fresh folder")
    if vanilla_core is None:
        raise ProofError("give --vanilla-core: a set's needs are judged against the core")
    vanilla_core = Path(vanilla_core)
    checkpoint_path = out.parent / f"{out.name}.closure.partial.jsonl"
    genes, refused = walk(mod, anchor, vanilla_core, checkpoint_path=checkpoint_path, quiet=quiet)
    if anchor in refused:
        raise ProofError(refused[anchor])
    systems = sorted(a for a, g in genes.items() if g["kind"] == "star-system")
    if len(systems) > 1:
        raise ProofError(f"the set holds {len(systems)} star systems ({', '.join(systems)}); the carrier plugin makes one system's "
                         "calls")
    merged, conflicts = merge_members(genes)
    if conflicts:
        raise ProofError("carried genes hold one path with different contents: "
                         + "; ".join(f"{c['path']} ({', '.join(c['genes'])})" for c in conflicts))
    root, digest = _mod_root(mod), set_identity(genes)
    made_by = systems[0] if systems else None
    carrier_gene = {"identity": digest, "anchors": [f"{anchor} and the {len(genes) - 1} genes it needs"], "members": merged,
                    "needs": {"mods": sorted({m for g in genes.values() for m in g["needs"]["mods"]})},
                    "kind": "star-system" if made_by else "set", "registrations": genes[made_by]["registrations"] if made_by else []}
    work = out / "work"
    try:
        plugin = build_carrier(root, carrier_gene, work / "carrier", vanilla_core=vanilla_core, work=work)
    except CarrierPluginRefused as refusal:
        raise ProofError(f"the carrier cannot make the star system's registered call: {refusal}") from refusal
    allowed = {"provides": sorted({p for g in genes.values() for p in g["provides"]}),
               "needs": {"vanilla": sorted({v for g in genes.values() for v in g["needs"]["vanilla"]}), "genes": []}}
    isolation = classify_isolation(scan_mod(root, TargetProfile(), vanilla_core),
                                   scan_mod(work / "carrier", TargetProfile(), vanilla_core), allowed)
    unresolved = unresolved_in_carrier(work / "carrier", genes)
    verdict = "FAIL" if isolation["failures"] or refused or unresolved else "PASS"
    buckets, not_carried = suspect_buckets(genes)
    anchor_gene = genes[anchor]
    atomic_write_text(out / "gene.json", dumps(anchor_gene), newline="")
    order = carried_order(anchor, genes)
    for number, carried in enumerate(order, 1):
        atomic_write_text(out / "closure" / _manifest_name(number, carried), dumps(genes[carried]), newline="")
    inputs = [("member", path) for path in sorted({member_file(m["path"]) for m in merged})]
    proof = {**header(SET_PROOF, anchor_gene, root=root, inputs=inputs, verdict=verdict), "half": "static",
             "carrier": {"id": f"gene_carrier_{digest[:12]}", "set_identity": digest, "members": len(merged),
                         **({"plugin": plugin} if plugin else {})},
             "carried": [{"anchor": a, "identity": genes[a]["identity"]} for a in order],
             "refused": [{"anchor": a, "reason": refused[a]} for a in sorted(refused)],
             "unresolved_in_carrier": unresolved,
             "registrations_not_made": registrations_not_made(genes, made_by),
             **{k: v for k, v in isolation.items() if k != "verdict"}, "verdict": verdict,
             "suspects": buckets, "not_carried": not_carried,
             "boot": "NOT_RUN: needs the test rig; the carrier boots alone, with its needs.mods, in place of the donor"}
    atomic_write_text(out / f"{SET_PROOF}.json", json.dumps(proof, indent=2, ensure_ascii=False) + "\n", newline="")
    if checkpoint_path.is_file():
        checkpoint_path.unlink()  # the checkpoint goes only once the full result is on disk
    return {"gene": anchor_gene["identity"], "carried": len(genes), "refused": len(refused), "failures": len(isolation["failures"]),
            "unresolved": len(unresolved), "verdict": verdict, "out": str(out)}


__all__ = ["SET_PROOF", "merge_members", "prove_set", "registrations_not_made", "set_identity", "suspect_buckets",
           "unresolved_in_carrier", "walk"]
