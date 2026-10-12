"""Save-inspection and save-compatibility commands (ROADMAP 70 H2.1)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .compat_sets import CompatSetError, install_compat_set
from .save_compat import check_save_compat, compare_builds, SaveCompatError
from .save_content_compat import check_save_content, removal_safety
from .save_format_survey import survey_saves
from .save_inspect import audit_scripts, diff_saves, growth_trend, inspect_save, save_provenance
from .save_reader import SaveReadError
from .save_snapshot import SaveSnapshotError, snapshot_list, snapshot_restore, snapshot_tag
from .save_summary import redacted_summary
from .scenarios import list_scenarios, scenario_check, scenario_plan, ScenarioError

# Save-tool statuses that mean "look at this" (non-zero exit).
_SAVE_ATTENTION_STATUSES = {"WILL_FAIL", "DUPLICATES_FOUND", "GROWTH_WARNING", "STALE_BUILD", "UNSAFE"}


def add_parser(subcommands) -> None:
    doctor_cmd = subcommands.add_parser("save-doctor", help="why a save will not load with what is installed, in one read-only pass: missing mods, classes no installed mod provides, NaN/Infinity values, a file cut off mid-write, version changes; each with how recoverable it usually is")
    doctor_cmd.add_argument("save", type=Path, help="save folder (holding campaign.xml and descriptor.xml)")
    doctor_cmd.add_argument("--mods", type=Path, help="the mods folder the save will be loaded with (required except with --break-cycle)")
    doctor_cmd.add_argument("--cycles", action="store_true", help="also look for Memory -> planet -> condition market -> same Memory reference cycles in campaign.xml (the PlanetConditionMarket.readResolve NullPointerException, ROADMAP 60g)")
    doctor_cmd.add_argument("--break-cycle", action="store_true", help="write a repaired COPY (needs --out): replace each inner <memory cl=\"Memory\" ref=N> reference found by --cycles with an empty memory; the save itself is never changed")
    doctor_cmd.add_argument("--out", type=Path, help="with --break-cycle: the new folder for the repaired copy")
    doctor_cmd.add_argument("--vanilla-core", type=Path, help="starsector-core, so the game's own classes resolve")
    doctor_cmd.add_argument("--json", action="store_true")
    rplan_cmd = subcommands.add_parser("save-removal-plan", help="for each object of a missing mod's class in a save: droppable (nothing outside refers to it) or blocked (lists the outside references); read-only, the plan for a fix on a copy")
    rplan_cmd.add_argument("save", type=Path)
    rplan_cmd.add_argument("--mods", type=Path, required=True)
    rplan_cmd.add_argument("--vanilla-core", type=Path)
    rplan_cmd.add_argument("--json", action="store_true")
    save_compat_cmd = subcommands.add_parser("save-compat", help="check whether a save's referenced mod classes exist in the build's loaded jars (read-only)")
    save_compat_cmd.add_argument("save", type=Path, help="save directory or its campaign.xml")
    save_compat_cmd.add_argument("mod_dir", type=Path)
    save_compat_cmd.add_argument("--vanilla-core", type=Path, help="starsector-core directory, to help rule out vanilla-only aliases")
    save_compat_cmd.add_argument("--compare-old", type=Path, help="compare builds instead: old jar or mod dir (requires --compare-new)")
    save_compat_cmd.add_argument("--compare-new", type=Path, help="compare builds: new jar or mod dir (requires --compare-old)")
    save_compat_cmd.add_argument("--json", action="store_true")
    def _save_tool(name: str, help_text: str, *, mod_dir: str | None = None, multi_save: bool = False, second_save: bool = False) -> argparse.ArgumentParser:
        cmd = subcommands.add_parser(name, help=help_text)
        if multi_save:
            cmd.add_argument("saves", nargs="+", type=Path, help="save directories or campaign.xml files, oldest first")
        else:
            cmd.add_argument("save", type=Path, help="save directory or its campaign.xml")
        if second_save:
            cmd.add_argument("save_b", type=Path, help="second save (or campaign.xml.bak) to compare against")
        if mod_dir == "positional":
            cmd.add_argument("mod_dir", type=Path)
        elif mod_dir == "optional":
            cmd.add_argument("--mod-dir", type=Path)
        elif mod_dir == "multi":
            cmd.add_argument("--mod-dir", action="append", default=[], type=Path, required=True, help="mod working copy; repeatable")
        cmd.add_argument("--json", action="store_true")
        return cmd
    for name, help_text, second in (
        ("save-inspect", "stream a save and report tracked mod state, known-list sizes and per-mod object counts (read-only)", False),
        ("save-diff", "compare tracked mod state between two saves, e.g. campaign.xml vs campaign.xml.bak (read-only)", True),
    ):
        cmd = _save_tool(name, help_text, mod_dir="optional", second_save=second)
        cmd.add_argument("--track-class", action="append", default=[], metavar="ALIAS", help="class alias to report scalar fields for; repeatable")
        cmd.add_argument("--track-id", action="append", default=[], metavar="ID", help="entity id to locate; repeatable")
        cmd.add_argument("--vanilla-core", type=Path)
    _save_tool("save-scripts", "count a mod's scripts/listeners per holder in a save and flag duplicates (read-only)", mod_dir="positional").add_argument("--vanilla-core", type=Path)
    growth_cmd = _save_tool("save-growth", "per-mod object counts and file sizes across a save chain, with a growth warning (read-only)", mod_dir="optional", multi_save=True)
    growth_cmd.add_argument("--warn-ratio", type=float, default=2.0, help="growth multiplier between consecutive saves that triggers a warning (default: 2.0)")
    _save_tool("save-provenance", "compare the mod versions/BF build tags a save was made with against current working copies (read-only)", mod_dir="multi")
    _save_tool("save-content", "check the data ids a save stores (hulls, variants, weapons, factions, ...) against the build plus vanilla (read-only)", mod_dir="positional").add_argument("--vanilla-core", type=Path)
    _save_tool("save-removal", "INTERNAL ONLY: everything a save still depends on for one mod; SAFE_TO_REMOVE or UNSAFE (read-only)", mod_dir="positional").add_argument("--vanilla-core", type=Path)
    summary_cmd = _save_tool("save-summary", "write a redacted, shareable save summary with no player data (local file only)", mod_dir="multi")
    summary_cmd.add_argument("--out", required=True, type=Path, help="output JSON path")
    summary_cmd.add_argument("--vanilla-core", type=Path)
    _save_tool("save-format-survey", "survey where saves keep the player fleet's cargo and credits (structure only, no names or quantities; read-only)", multi_save=True)
    snapshot_cmd = subcommands.add_parser("save-snapshot", help="tag, list and restore rig-only save copies (never touches a real install)")
    snapshot_subcommands = snapshot_cmd.add_subparsers(dest="snapshot_command", required=True)
    snapshot_tag_cmd = snapshot_subcommands.add_parser("tag", help="copy <rig>/saves/<save> into <rig>/save_snapshots/<tag>/ with a hash manifest")
    snapshot_tag_cmd.add_argument("runtime_dir", type=Path)
    snapshot_tag_cmd.add_argument("save_name")
    snapshot_tag_cmd.add_argument("tag")
    snapshot_tag_cmd.add_argument("--json", action="store_true")
    snapshot_list_cmd = snapshot_subcommands.add_parser("list", help="list snapshot tags in a rig")
    snapshot_list_cmd.add_argument("runtime_dir", type=Path)
    snapshot_list_cmd.add_argument("--json", action="store_true")
    snapshot_restore_cmd = snapshot_subcommands.add_parser("restore", help="copy a snapshot back into <rig>/saves/ (never overwrites without --replace)")
    snapshot_restore_cmd.add_argument("runtime_dir", type=Path)
    snapshot_restore_cmd.add_argument("tag")
    snapshot_restore_cmd.add_argument("--as-name", help="restore under this save folder name instead of the original")
    snapshot_restore_cmd.add_argument("--replace", action="store_true", help="overwrite an existing save folder of the same name")
    snapshot_restore_cmd.add_argument("--json", action="store_true")
    scenario_cmd = subcommands.add_parser("scenario", help="named test scenarios with expected results (plan is a dry run; check reads a log/save)")
    scenario_subcommands = scenario_cmd.add_subparsers(dest="scenario_command", required=True)
    scenario_list_cmd = scenario_subcommands.add_parser("list", help="list bundled scenarios")
    scenario_list_cmd.add_argument("--json", action="store_true")
    scenario_plan_cmd = scenario_subcommands.add_parser("plan", help="show the mods, probe-config command and snapshot a scenario needs (writes nothing)")
    scenario_plan_cmd.add_argument("name")
    scenario_plan_cmd.add_argument("runtime_dir", type=Path)
    scenario_plan_cmd.add_argument("--mod", action="append", default=[], metavar="ID=PATH", help="source directory for a mod id the scenario uses; repeatable")
    scenario_plan_cmd.add_argument("--json", action="store_true")
    scenario_check_cmd = scenario_subcommands.add_parser("check", help="evaluate a scenario's expected results against a probe log (and optionally a save)")
    scenario_check_cmd.add_argument("name")
    scenario_check_cmd.add_argument("log_path", type=Path)
    scenario_check_cmd.add_argument("--save", type=Path, help="save directory or campaign.xml for save assertions")
    scenario_check_cmd.add_argument("--json", action="store_true")
    compat_set_cmd = subcommands.add_parser("compat-set", help="install a named standard compatibility pack (roadmap P4) into a test rig")
    compat_set_subcommands = compat_set_cmd.add_subparsers(dest="compat_set_command", required=True)
    compat_set_install_cmd = compat_set_subcommands.add_parser("install", help="copy a named compat set's mods from a source mods directory into a rig's mods/")
    compat_set_install_cmd.add_argument("set_name", metavar="SET")
    compat_set_install_cmd.add_argument("--runtime", required=True, type=Path, help="isolated test-rig runtime directory (starsector-core must be a junction/symlink)")
    compat_set_install_cmd.add_argument("--source-mods", required=True, type=Path, help="read-only directory to copy mods FROM (never written to)")
    compat_set_install_cmd.add_argument("--reference-manifest", type=Path, help="allow a registered dedicated historical install whose core is not a junction")
    compat_set_install_cmd.add_argument("--dry-run", action="store_true", help="report the install plan without copying anything")
    compat_set_install_cmd.add_argument("--json", action="store_true")


def run_cli(args: argparse.Namespace) -> int:
    if args.command == "compat-set" and args.compat_set_command == "install":
        try:
            result = install_compat_set(args.set_name, args.runtime, args.source_mods, dry_run=args.dry_run, reference_manifest=args.reference_manifest)
        except CompatSetError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Set: {result['set']} ({len(result['resolved_mod_ids'])} mods)")
            print(f"Rig gameVersion (inferred): {result.get('rig_game_version')}")
            if result["missing"]:
                print(f"Missing from source: {result['missing']}")
            for warning in result["warnings"]:
                print(f"WARN: {warning}")
            if result["dry_run"]:
                for item in result["plan"]:
                    print(f"WOULD COPY {item['id']} ({item['reason']}): {item['source']} -> {item['destination']}")
                print(f"Already identical (skipped): {result['skipped_identical']}")
            else:
                for item in result["installed"]:
                    print(f"COPIED {item['id']}: {len(item['files_copied'])} file(s) -> {item['destination']}")
        return 0
    if args.command == "save-compat":
        try:
            if args.compare_old or args.compare_new:
                if not (args.compare_old and args.compare_new):
                    print("bridgeforge: --compare-old and --compare-new must be given together", file=sys.stderr)
                    return 2
                result = compare_builds(args.save, args.compare_old, args.compare_new)
            else:
                result = check_save_compat(args.save, args.mod_dir, vanilla_core=args.vanilla_core)
        except (SaveCompatError, ValueError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True, default=str))
        else:
            print(f"Status: {result['status']}")
            for entry in result.get("missing", []):
                print(f"MISSING {entry['reference']} (x{entry['occurrences']}) at {entry['sample_path']}")
            for entry in result.get("dropped_in_new", []):
                print(f"DROPPED {entry}")
        return 0 if result["status"] != "WILL_FAIL" else 1
    if args.command == "save-removal-plan":
        from .save_removal_plan import plan_removal
        result = plan_removal(args.save, args.mods, args.vanilla_core)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
            return 0
        print(f"{result['objects']} object(s) of missing classes: {result['droppable']} droppable, {result['blocked']} blocked")
        for row in result["rows"]:
            print(f"  {row['state']:9} {row['class']} (in {row['parent']}, line {row['line']})"
                  + (f"  referenced from {', '.join(row['ref_examples'])}" if row["ref_examples"] else ""))
        return 0
    if args.command == "save-doctor":
        from .save_doctor import diagnose
        if args.break_cycle:
            from .save_cycles import SaveCycleError, break_cycle
            if args.out is None:
                print("bridgeforge: --break-cycle needs --out (a new folder for the repaired copy).", file=sys.stderr)
                return 2
            try:
                result = break_cycle(args.save, args.out)
            except (SaveCycleError, OSError, ValueError) as exc:
                print(f"bridgeforge: {exc}", file=sys.stderr)
                return 2
            print(json.dumps(result, indent=2, ensure_ascii=False) if args.json else
                  f"Copy written: {result['copy']} ({len(result['changed_lines'])} line(s) changed; "
                  f"cycles {result['cycles_before']} -> {result['cycles_after']}). The original is unchanged.")
            return 0 if result["cycles_after"] == 0 else 1
        if args.mods is None:
            print("bridgeforge: save-doctor needs --mods (or --break-cycle).", file=sys.stderr)
            return 2
        result = diagnose(args.save, args.mods, args.vanilla_core, cycles=args.cycles)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
            return 0
        print(f"{result['verdict']}: {result['character']} ({result['game_version']}, {result['enabled_mods']} mods)")
        for problem in result["problems"]:
            detail = problem.get("mod") or problem.get("package") or problem.get("file") or f"{problem.get('lines')} line(s)"
            if problem["class"] == "MEMORY_CYCLE":
                detail = (f"line {problem['line']}: PCMarket z={problem['pcmarket']} refers back to open memory z={problem['memory']}"
                          f" via keys {problem['keys']}")
            print(f"  {problem['class']:16} {detail}" + (f"  e.g. {', '.join(problem['examples'])}" if problem.get("examples") else ""))
        for name, text in result["recovery"].items():
            print(f"  recovery {name}: {text}")
        return 0 if result["verdict"] == "NO_KNOWN_PROBLEM" else 1
    if args.command == "save-format-survey":
        try:
            result = survey_saves(args.saves)
        except (SaveReadError, ValueError, OSError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True, default=str))
        else:
            print(f"Surveyed {result['saves_surveyed']} save(s); {result['saves_with_player_cargo']} with player cargo")
            print(f"  game versions: {result['game_versions']}")
            print(f"  cargo attributes in every save: {result['cargo_attributes_in_every_save']}")
            print(f"  credits value present in every save: {result['credits_value_present_in_every_save']}")
        return 0
    if args.command in {"save-inspect", "save-diff", "save-scripts", "save-growth", "save-provenance", "save-content", "save-removal", "save-summary"}:
        try:
            if args.command == "save-inspect":
                result = inspect_save(args.save, track_classes=args.track_class, track_ids=args.track_id, mod_dir=args.mod_dir, vanilla_core=args.vanilla_core)
            elif args.command == "save-diff":
                result = diff_saves(args.save, args.save_b, track_classes=args.track_class, track_ids=args.track_id, mod_dir=args.mod_dir, vanilla_core=args.vanilla_core)
            elif args.command == "save-scripts":
                result = audit_scripts(args.save, args.mod_dir, vanilla_core=args.vanilla_core)
            elif args.command == "save-growth":
                result = growth_trend(args.saves, mod_dir=args.mod_dir, growth_rate_warning=args.warn_ratio)
            elif args.command == "save-provenance":
                result = save_provenance(args.save, mod_dirs=args.mod_dir)
            elif args.command == "save-content":
                result = check_save_content(args.save, args.mod_dir, vanilla_core=args.vanilla_core)
            elif args.command == "save-removal":
                result = removal_safety(args.save, args.mod_dir, vanilla_core=args.vanilla_core)
            else:
                result = redacted_summary(args.save, args.mod_dir, out_path=args.out, vanilla_core=args.vanilla_core)
        except (SaveReadError, SaveCompatError, ValueError, OSError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        status = result.get("status")
        if args.json or status is None:
            print(json.dumps(result, indent=2, sort_keys=True, default=str))
        else:
            print(f"Status: {status}")
            for key in ("missing", "duplicates", "warnings", "reasons"):
                items = result.get(key) or []
                for item in items[:50] if isinstance(items, list) else []:
                    print(f"  {key.upper().rstrip('S')}: {item if isinstance(item, str) else json.dumps(item, sort_keys=True, default=str)}")
            if args.command == "save-summary":
                print(f"Written: {args.out}")
        return 1 if status in _SAVE_ATTENTION_STATUSES else 0
    if args.command == "save-snapshot":
        try:
            if args.snapshot_command == "tag":
                result = snapshot_tag(args.runtime_dir, args.save_name, args.tag)
            elif args.snapshot_command == "list":
                result = snapshot_list(args.runtime_dir)
            else:
                result = snapshot_restore(args.runtime_dir, args.tag, as_name=args.as_name, replace=args.replace)
        except SaveSnapshotError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        elif args.snapshot_command == "tag":
            print(f"Snapshot {result['tag']}: {result['snapshot_dir']} ({len(result['manifest']['hashes'])} files)")
            for mod, tag in (result["manifest"].get("bf_build_tags") or {}).items():
                print(f"  build tag {mod}: {tag}")
        elif args.snapshot_command == "list":
            if not result:
                print("No snapshots.")
            for entry in result:
                manifest = entry.get("manifest") or {}
                print(f"{entry['tag']}: {manifest.get('source_save', '?')} ({manifest.get('created', '?')})")
        else:
            print(f"Restored {result['tag']} to {result['restored_to']} (replaced: {result['replaced']})")
        return 0
    if args.command == "scenario":
        try:
            if args.scenario_command == "list":
                result = list_scenarios()
            elif args.scenario_command == "plan":
                mod_dirs: dict[str, Path] = {}
                for item in args.mod:
                    mod_id, sep, path = item.partition("=")
                    if not sep or not mod_id or not path:
                        print(f"bridgeforge: --mod expects ID=PATH, got {item!r}", file=sys.stderr)
                        return 2
                    mod_dirs[mod_id] = Path(path)
                result = scenario_plan(args.name, args.runtime_dir, mod_dirs)
            else:
                result = scenario_check(args.name, args.log_path, args.save)
        except ScenarioError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json or args.scenario_command == "plan":
            print(json.dumps(result, indent=2, sort_keys=True, default=str))
        elif args.scenario_command == "list":
            print("\n".join(result) if result else "No scenarios.")
        else:
            print(f"Scenario {result['scenario']}: {result['status']}")
            for entry in result["probe_assertions"] + result["save_assertions"]:
                reasons = entry.get("reasons") or ([entry["reason"]] if entry.get("reason") else [])
                print(f"  {entry['status']} {json.dumps(entry['assertion'], sort_keys=True)}" + (f" - {'; '.join(reasons)}" if reasons else ""))
            if result.get("save_note"):
                print(f"  note: {result['save_note']}")
        if args.scenario_command == "check":
            return 0 if result["status"] == "PASS" else 1
        return 0
    return 2
