"""The `gene` command (ROADMAP-3 94.G1): `gene describe MOD KIND:ID` writes one feature's gene manifest."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bridgeforge.vendor_plan import KINDS, VendorPlanError

from .gene import GeneError, describe, dumps


def add_parser(subcommands) -> None:
    gene = subcommands.add_parser("gene", help="feature genome (94.G1): describe one feature of a mod as a gene manifest (gene.json); read-only")
    gene_sub = gene.add_subparsers(dest="gene_command", required=True)
    describe_cmd = gene_sub.add_parser("describe", help="write the gene manifest of one content piece: its members with hashes, needs, licence, "
                                                        "phenotype obligations and a content-hash identity")
    describe_cmd.add_argument("mod", type=Path, help="mod folder or workspace (working/ is used)")
    describe_cmd.add_argument("anchor", help=f"kind:id, kind one of {', '.join(KINDS)}")
    describe_cmd.add_argument("--vanilla-core", type=Path, help="starsector-core, so parts vanilla provides are listed as needs, not missing")
    describe_cmd.add_argument("--write", type=Path, help="write the manifest to this file instead of printing it")
    contract_cmd = gene_sub.add_parser("contract", help="the gene.json contract sister repositories pin (GR-1): check the committed "
                                                        "docs/contracts/gene/ folder, or write it, and print CONTRACT.json's SHA-256")
    contract_cmd.add_argument("--folder", type=Path, help="contract folder (default: docs/contracts/gene in the checkout)")
    contract_cmd.add_argument("--write", action="store_true", help="write the folder instead of checking it")


def run_cli(args: argparse.Namespace) -> int:
    if args.command != "gene":
        return 2
    if args.gene_command == "contract":
        return _run_contract(args)
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
