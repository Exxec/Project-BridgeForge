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


def run_cli(args: argparse.Namespace) -> int:
    if args.command != "gene":
        return 2
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
