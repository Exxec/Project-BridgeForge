"""`bridgeforge shadow-triage`: three-way view of vanilla-path shadows, and owner approvals to remove old-vanilla copies (ROADMAP 73 D3)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def add_parser(subcommands) -> None:
    cmd = subcommands.add_parser("shadow-triage", help="vanilla-path-shadowing: show old vanilla / mod / RC8 differences per shadowed file; --approve records an owner approval to move a byte-identical old-vanilla copy (the fixer moves it), --revoke ends one (ROADMAP 73 D3)")
    cmd.add_argument("workspace", type=Path, help="a workspace (or its working/ folder)")
    cmd.add_argument("--vanilla-core", type=Path, required=True, help="RC8 starsector-core")
    cmd.add_argument("--reference-core", type=Path, help="starsector-core of the install the mod was made for (default: the registered reference rig for the mod's gameVersion)")
    cmd.add_argument("--approve", action="append", default=[], metavar="PATH", help="data-relative path of a byte-identical old-vanilla copy to approve for removal; repeatable")
    cmd.add_argument("--revoke", action="append", default=[], metavar="PATH", help="end the approval for this path")
    cmd.add_argument("--reason", default="", help="why (required with --approve/--revoke)")
    cmd.add_argument("--rulings", type=Path, help="ruling store (default: ESCALATION_RULINGS.jsonl beside the workspace)")
    cmd.add_argument("--json", action="store_true")


def run_cli(args: argparse.Namespace) -> int:
    from .reference_rigs import reference_core_for_game_version
    from .scan_json import _load_lenient_json_file
    from . import shadow_triage as st

    workspace = args.workspace.expanduser().resolve()
    root = workspace if workspace.name == "working" else workspace / "working"
    if not root.is_dir():
        print(f"bridgeforge: {workspace} has no working/ folder.", file=sys.stderr)
        return 2
    reference = args.reference_core
    if reference is None:
        info = _load_lenient_json_file(root / "mod_info.json") if (root / "mod_info.json").is_file() else None
        reference = reference_core_for_game_version(info.get("gameVersion") if isinstance(info, dict) else None)
    if reference is None:
        print("bridgeforge: no reference core: pass --reference-core (no registered rig matches the mod's gameVersion).", file=sys.stderr)
        return 2
    try:
        recorded = [st.record_ruling(root, args.vanilla_core, reference, rel, reason=args.reason, rulings_file=args.rulings) for rel in args.approve]
        recorded += [st.record_ruling(root, args.vanilla_core, reference, rel, reason=args.reason, revoke=True, rulings_file=args.rulings) for rel in args.revoke]
    except (ValueError, OSError) as exc:
        print(f"bridgeforge: {exc}", file=sys.stderr)
        return 2
    result = st.triage(root, args.vanilla_core, reference, st.read_rulings(args.rulings or st.rulings_path_for(root)))
    if args.json:
        print(json.dumps({**result, "recorded": recorded}, indent=2, ensure_ascii=False))
    else:
        for entry in recorded:
            print(f"Recorded {entry['ruling']}: {entry['file']}")
        print(st.render_report(result, Path(reference)))
    return 0
