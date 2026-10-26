"""`bridgeforge api how OLD_SYMBOL --old-api JAR --new-api JAR`: how did working mods replace a removed API (ROADMAP-3 81.1).

Runs `api-diff` for the symbol, lists its same-name candidates in the new API, and shows which indexed mods (the atlas
census) use each candidate, with an example class or file, so a reviser can see how a working mod already solved it.
STATIC: the usage counts come from constant pools and import/regex reads, not from running anything.
"""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

from .atlas.atlas import DEFAULT_DB, AtlasError, connect


def add_parser(subcommands) -> None:
    api = subcommands.add_parser("api", help="game API questions answered from the Mod Atlas census (`api how`)")
    sub = api.add_subparsers(dest="api_command", required=True)
    how = sub.add_parser("how", help="for a removed API symbol: api-diff's same-name candidates and which indexed mods use each one (needs `atlas build`)")
    how.add_argument("symbol", help="old symbol, e.g. SectorAPI.addMessage or com.fs.starfarer.api.campaign.SectorAPI")
    how.add_argument("--old-api", required=True, type=Path, help="older starfarer.api.jar, or the starsector-core folder holding it")
    how.add_argument("--new-api", required=True, type=Path, help="newer starfarer.api.jar, or the starsector-core folder holding it")
    how.add_argument("--db", type=Path, default=DEFAULT_DB, help=f"atlas file (default: {DEFAULT_DB.as_posix()})")
    how.add_argument("--json", action="store_true")


def run_cli(args) -> int:
    from .api_diff import ApiDiffError, diff_api_jars
    from .atlas.atlas_census_report import api_how, api_how_text

    try:
        catalogue = diff_api_jars(args.old_api, args.new_api)
        conn = connect(args.db)
        try:
            data = api_how(conn, catalogue, args.symbol)
        finally:
            conn.close()
    except (ApiDiffError, AtlasError, OSError, zipfile.BadZipFile) as exc:
        print(f"bridgeforge: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(data, indent=2, ensure_ascii=False) if args.json else api_how_text(data))
    return 0
