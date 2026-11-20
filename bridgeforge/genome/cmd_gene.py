"""The `gene` command (ROADMAP-3 94.G1): `gene describe MOD KIND:ID` writes one feature's gene manifest."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bridgeforge.vendor_plan import VendorPlanError

from .gene import CLOSABLE_KINDS, GeneError, describe, dumps


def add_parser(subcommands) -> None:
    gene = subcommands.add_parser("gene", help="feature genome (94.G1): describe one feature of a mod as a gene manifest (gene.json); read-only")
    gene_sub = gene.add_subparsers(dest="gene_command", required=True)
    describe_cmd = gene_sub.add_parser("describe", help="write the gene manifest of one content piece: its members with hashes, needs, licence, "
                                                        "phenotype obligations and a content-hash identity")
    describe_cmd.add_argument("mod", type=Path, help="mod folder or workspace (working/ is used)")
    describe_cmd.add_argument("anchor", help=f"kind:id, kind one of {', '.join(CLOSABLE_KINDS)}")
    describe_cmd.add_argument("--vanilla-core", type=Path, help="starsector-core, so parts vanilla provides are listed as needs, not missing")
    describe_cmd.add_argument("--write", type=Path, help="write the manifest to this file instead of printing it")
    contract_cmd = gene_sub.add_parser("contract", help="the gene.json contract sister repositories pin (GR-1): check the committed "
                                                        "docs/contracts/gene/ folder, or write it, and print CONTRACT.json's SHA-256")
    contract_cmd.add_argument("--folder", type=Path, help="contract folder (default: docs/contracts/gene in the checkout)")
    contract_cmd.add_argument("--write", action="store_true", help="write the folder instead of checking it")
    trace_cmd = gene_sub.add_parser("trace", help="what cites a roadmap id (GR-4): commits, the pull requests that merged them, tests and "
                                                  "documents of this checkout; read-only, offline")
    trace_cmd.add_argument("item", help="a roadmap id, e.g. 94.G1 or GR-4")
    trace_cmd.add_argument("--json", action="store_true")
    sisters_cmd = gene_sub.add_parser("sisters", help="the cross-repository check (GR-4): each sister repository's genome entry against "
                                                      "section 12 of docs/FEATURE_GENOME_ROADMAP.md, and its gene contract pin against "
                                                      "this checkout's contract; reads GitHub through gh unless --clone is given")
    sisters_cmd.add_argument("--clone", action="append", default=[], metavar="REPO=DIR",
                             help="read this repository from a local checkout instead of GitHub; repeatable")
    sisters_cmd.add_argument("--json", action="store_true")
    census_cmd = gene_sub.add_parser("census", help="gene census of a corpus (GR-2): feature kinds per mod and, per plugin hook, how many "
                                                    "features it sets up together; read-only, one progress line per mod, resumable")
    census_cmd.add_argument("corpus", type=Path, help="folder of mods or archives, e.g. Done (folders starting with _ are skipped)")
    census_cmd.add_argument("--write", type=Path, required=True, help="the per-mod result (JSON); keep it outside the repository, it "
                                                                     "names third-party mods. A checkpoint sits beside it while running")
    census_cmd.add_argument("--quiet", action="store_true", help="no per-mod progress lines on stderr")
    prove_cmd = gene_sub.add_parser("prove", help="the static halves of a gene's subtraction and isolation proofs (94.G2), written with "
                                                  "gene.json as evidence files into a fresh folder; the boot halves need the test rig")
    prove_cmd.add_argument("mod", type=Path, help="mod folder or workspace (working/ is used)")
    prove_cmd.add_argument("anchor", help=f"kind:id, kind one of {', '.join(CLOSABLE_KINDS)}")
    prove_cmd.add_argument("--out", type=Path, required=True, help="a new or empty folder outside the repository (it holds copies of the mod)")
    prove_cmd.add_argument("--vanilla-core", type=Path, help="starsector-core, for vanilla needs and the scans")
    prove_cmd.add_argument("--provider-root", type=Path, action="append", default=[],
                           help="a mods/ folder holding the libraries the donor's sources import, for cutting a star system's "
                                "registration from its plugin (repeatable)")
    evidence_cmd = gene_sub.add_parser("evidence", help="evidence files about a gene (WP5): check that one carries the common header and is "
                                                        "about this gene as it stands")
    evidence_sub = evidence_cmd.add_subparsers(dest="evidence_command", required=True)
    check_cmd = evidence_sub.add_parser("check", help="check an evidence file's header against a gene manifest and, with --root, "
                                                      "recompute its inputs' SHA-256")
    check_cmd.add_argument("file", type=Path, help="the evidence file (JSON)")
    check_cmd.add_argument("--gene", type=Path, required=True, help="the gene.json the evidence is about")
    check_cmd.add_argument("--root", type=Path, help="the folder the inputs' paths are relative to (a mod or workspace); without it "
                                                     "the inputs are not re-hashed")


def _run_evidence(args: argparse.Namespace) -> int:
    import json

    from .evidence import check

    try:
        made = json.loads(args.file.read_text(encoding="utf-8"))
        gene = json.loads(args.gene.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"bridgeforge: {exc}", file=sys.stderr)
        return 2
    problems = check(made, gene if isinstance(gene, dict) else {}, args.root)
    for problem in problems:
        print(f"PROBLEM {problem}")
    if not problems:
        rehashed = f", {len(made['inputs'])} input(s) re-hashed" if args.root else ", inputs not re-hashed (no --root)"
        print(f"OK {made['kind']} {made['verdict']} about gene {made['gene']['identity'][:16]}{rehashed}")
    return 1 if problems else 0


def _run_census(args: argparse.Namespace) -> int:
    from .census import render_summary, run_census

    if not args.corpus.is_dir():
        print(f"bridgeforge: {args.corpus} is not a folder", file=sys.stderr)
        return 2
    result = run_census(args.corpus, args.write, quiet=args.quiet)
    print(render_summary(result["summary"]))
    print(f"Written: {args.write}")
    return 0


def _run_prove(args: argparse.Namespace) -> int:
    from .proof import ProofError, prove

    try:
        result = prove(args.mod, args.anchor, args.out, vanilla_core=args.vanilla_core, provider_roots=args.provider_root)
    except (ProofError, GeneError, VendorPlanError, OSError) as exc:
        print(f"bridgeforge: {exc}", file=sys.stderr)
        return 2
    for kind, verdict in result["verdicts"].items():
        print(f"{kind}: {verdict} (static half; boot half NOT_RUN)")
    print(f"gene {result['gene'][:16]}; evidence in {result['out']}")
    return 0 if all(v == "PASS" for v in result["verdicts"].values()) else 1


def run_cli(args: argparse.Namespace) -> int:
    if args.command != "gene":
        return 2
    if args.gene_command == "prove":
        return _run_prove(args)
    if args.gene_command == "census":
        return _run_census(args)
    if args.gene_command == "evidence":
        return _run_evidence(args)
    if args.gene_command == "contract":
        return _run_contract(args)
    if args.gene_command == "trace":
        return _run_trace(args)
    if args.gene_command == "sisters":
        return _run_sisters(args)
    try:
        gene = describe(args.mod, args.anchor, vanilla_core=args.vanilla_core)
    except (GeneError, VendorPlanError, OSError) as exc:
        print(f"bridgeforge: {exc}", file=sys.stderr)
        return 2
    if args.write:
        from bridgeforge.safeio import atomic_write_text

        atomic_write_text(args.write, dumps(gene), newline="")
        print(f"Written: {args.write} (identity {gene['identity'][:16]}, {len(gene['members'])} members)", file=sys.stderr)
    else:
        print(dumps(gene), end="")
    return 0


def _run_contract(args: argparse.Namespace) -> int:
    from bridgeforge.paths import checkout_root

    from .contract import CONTRACT_RELATIVE, check_contract, contract_sha256, write_contract

    folder = args.folder or checkout_root() / CONTRACT_RELATIVE
    if args.write:
        print(f"Written: {folder}; pin CONTRACT.json sha256 {write_contract(folder)}")
        return 0
    problems = check_contract(folder)
    for problem in problems:
        print(f"bridgeforge: {problem}", file=sys.stderr)
    if problems:
        print("bridgeforge: run `bridgeforge gene contract --write`, review the diff, and update the sister repositories' pins",
              file=sys.stderr)
        return 1
    print(f"{folder}: current; pin CONTRACT.json sha256 {contract_sha256()}")
    return 0


def _run_trace(args: argparse.Namespace) -> int:
    import json

    from bridgeforge.paths import checkout_root

    from .trace import render, trace

    try:
        result = trace(args.item, checkout_root())
    except RuntimeError as exc:
        print(f"bridgeforge: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2) if args.json else render(result))
    return 0


def _run_sisters(args: argparse.Namespace) -> int:
    import json

    from bridgeforge.paths import checkout_root

    from .contract import contract_sha256
    from .sisters import GENOME_DOC, check_sisters, clone_reader, github_reader, render

    clones = {}
    for spec in args.clone:
        name, sep, folder = spec.partition("=")
        if not sep or not name or not folder:
            print(f"bridgeforge: --clone takes REPO=DIR, got {spec!r}", file=sys.stderr)
            return 2
        clones[name] = Path(folder)
    root = checkout_root()
    read = clone_reader(clones) if clones else github_reader
    try:
        result = check_sisters((root / GENOME_DOC).read_text(encoding="utf-8"), (root / "ROADMAP-3.md").read_text(encoding="utf-8"),
                               read, contract_sha256())
    except (OSError, RuntimeError) as exc:
        print(f"bridgeforge: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2) if args.json else render(result))
    return 0 if result["ok"] else 1
