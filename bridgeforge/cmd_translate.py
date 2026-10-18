"""Translation, description, fixer and strip commands (ROADMAP 70 H2.1)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .fixers import apply_fix, compute_fix, FixerError, SUPPORTED_FINDINGS, unified_diff_for_change
from .scanner import scan_mod
from .translation import apply_translation, check_translation, export_project_go_tm, export_translation, prefill_from_record, prefill_from_reference, TranslationError


def add_parser(subcommands) -> None:
    translate_export = subcommands.add_parser("translate-export", help="export every non-English (CJK) player-visible string with a stable id (read-only; handles Starsector's lenient CSV/JSON and jar strings)")
    translate_export.add_argument("mod_dir", type=Path)
    translate_export.add_argument("output", type=Path, help="translation JSON to write (must not be inside the mod)")
    translate_export.add_argument("--record", type=Path, action="append", default=[], help="zh/en record JSON file or folder to prefill from (e.g. a translator's ai/en); repeatable")
    translate_export.add_argument("--reference", type=Path, help="an English copy of the same mod: prefill CSV text by row+column and JSON text by path")
    translate_export.add_argument("--json", action="store_true")
    translate_apply = subcommands.add_parser("translate-apply", help="write a filled translation JSON into a copy of the mod (or an explicit working copy with --in-place)")
    translate_apply.add_argument("mod_dir", type=Path)
    translate_apply.add_argument("translations", type=Path)
    translate_apply_target = translate_apply.add_mutually_exclusive_group(required=True)
    translate_apply_target.add_argument("--out", type=Path, help="new folder for the translated copy")
    translate_apply_target.add_argument("--in-place", action="store_true", help="edit mod_dir itself (use only on a working copy)")
    translate_apply.add_argument("--json", action="store_true")
    translate_tm = subcommands.add_parser("translate-tm", help="write a translation JSON's pairs as Project Go (SSMT) translation memory, for `ssmt tm import <db> json <file>`")
    translate_tm.add_argument("translations", type=Path)
    translate_tm.add_argument("output", type=Path)
    translate_tm.add_argument("--context", default="", help="Project Go TM context (default empty: exact matches ignore context; fuzzy matches filter on it)")
    translate_tm.add_argument("--json", action="store_true")
    translate_check = subcommands.add_parser("translate-check", help="report leftover non-English strings and designTypeColors keys that no tech/manufacturer uses")
    translate_check.add_argument("mod_dir", type=Path)
    translate_check.add_argument("--json", action="store_true")
    tbatch_cmd = subcommands.add_parser("translate-batch", help="a mod's whole translation in one command: export, AI agent per chunk, strict checks (filled, no CJK left, placeholders kept), apply to a complete copy or in place, check (ROADMAP 34.28)")
    tbatch_cmd.add_argument("mod_dir", type=Path)
    tbatch_target = tbatch_cmd.add_mutually_exclusive_group(required=True)
    tbatch_target.add_argument("--out", type=Path, help="new folder for the complete translated copy")
    tbatch_target.add_argument("--in-place", action="store_true", help="edit mod_dir itself (a working copy only)")
    tbatch_cmd.add_argument("--agent", default="claude -p --permission-mode acceptEdits --model claude-sonnet-5", help="the agent command; it gets the prompt on stdin and edits one chunk file")
    tbatch_cmd.add_argument("--work", type=Path, help="folder for chunks and the checkpoint (default: <out or mod>.translate-work beside it)")
    tbatch_cmd.add_argument("--chunk", type=int, default=120, help="entries per agent call (default 120)")
    tbatch_cmd.add_argument("--reference", type=Path, help="an English copy of the same mod to prefill from")
    tbatch_cmd.add_argument("--record", type=Path, action="append", default=[], help="a translator's zh/en record to prefill from; repeatable")
    tbatch_cmd.add_argument("--quiet", action="store_true", help="no per-chunk progress lines")
    tbatch_cmd.add_argument("--json", action="store_true")
    desc_cmd = subcommands.add_parser("descriptions", help="missing codex descriptions: build the queue sheet, or apply a reviewed draft table with credits and an original-descriptions copy")
    desc_sub = desc_cmd.add_subparsers(dest="descriptions_command", required=True)
    desc_sheet = desc_sub.add_parser("sheet", help="write <queue>/DESCRIPTIONS_NEEDED.csv from a live check")
    desc_sheet.add_argument("queue", type=Path)
    desc_sheet.add_argument("--vanilla-core", type=Path)
    desc_apply = desc_sub.add_parser("apply", help="add a draft table's rows to working/data/strings/descriptions.csv; write BRIDGEFORGE_CREDITS.txt and alt-original-descriptions/")
    desc_apply.add_argument("workspace", type=Path)
    desc_apply.add_argument("draft", type=Path, help="markdown with | `id` | TYPE | text | rows")
    renamed_cmd = subcommands.add_parser("renamed-ids", help="was a missing id renamed in a newer copy of its mod? Same name and description is RENAMED; a shared name word is only SIMILAR (read-only)")
    renamed_cmd.add_argument("old_copy", type=Path, help="a mod folder that still defines the ids")
    renamed_cmd.add_argument("new_copy", type=Path, help="the newer copy of the same mod")
    renamed_cmd.add_argument("ids", nargs="+", help="kind:id (hull, weapon, hullmod, wing)")
    renamed_cmd.add_argument("--json", action="store_true")
    fix = subcommands.add_parser("fix", help="apply a SAFE, mechanical fixer for one supported finding id (dry-run diff by default)")
    fix.add_argument("mod_dir", type=Path)
    fix.add_argument("--finding", required=True, metavar="ID", help=f"supported: {', '.join(SUPPORTED_FINDINGS)}")
    fix.add_argument("--apply", action="store_true", help="write the change (default: print a dry-run diff only)")
    fix.add_argument("--json", action="store_true")
    fix.add_argument("--target-game-version", help="required for mod-info-game-version-inexact")
    fix.add_argument("--design-type", help="required for csv-missing-design-type-column")
    fix.add_argument("--id-prefix", action="append", default=[], metavar="PREFIX", help="repeatable; required for csv-missing-design-type-column")
    fix.add_argument("--design-color", metavar="R,G,B", help="required for csv-missing-design-type-column")
    fix.add_argument("--vanilla-core", type=Path, help="required for procgen-*-row-missing and faction-known-lists-missing")
    fix.add_argument("--type-id", help="required for procgen-planet-row-missing/procgen-star-row-missing")
    fix.add_argument("--from-vanilla-id", help="required for procgen-planet-row-missing/procgen-star-row-missing")
    fix.add_argument("--faction-file", type=Path, help="required for faction-known-lists-missing")
    fix.add_argument("--hull-zero-no-evidence", action="store_true", help="carrier-bays-proposal: set 0 bays for every hull that has a hangar value but no LAUNCH_BAY slot and no variant wings (nothing can launch from it)")
    fix.add_argument("--hull", action="append", default=[], metavar="ID=N", help="repeatable; required for carrier-bays-proposal, e.g. --hull my_carrier=4 (0-6, vanilla's own maximum)")
    fix.add_argument("--declare-provider", action="append", default=[], metavar="ID[=NAME]", help="repeatable; undeclared-library-dependency: declare this indexed provider mod (a revive packet's import resolution names it) instead of a known library")
    fix.add_argument("--reference-core", type=Path, help="variant-op-over-budget: trim only variants that fit under this older starsector-core's costs (the ones RC8 pushed over)")
    fix.add_argument("--encoding", action="append", default=[], metavar="FILE=ENC", help="repeatable; for data-file-not-utf8: re-encode FILE (relative to the mod) from ENC (cp1252, mac_roman, shift_jis, gbk, gb18030, latin-1) when a person has read it and named the encoding")
    fix.add_argument("--allow-shadowed-edit", action="store_true", help="override the refusal to edit a loose script one of this mod's own jars, or a declared dependency's jar, already shadows (the edit has no effect unless the jar is also being rebuilt from the patched source)")
    fix.add_argument("--providers", type=Path, action="append", default=[], help="mods folder, mod folder or In operation tree to search for declared dependencies, for the dependency-jar shadow check (default: <repo>/In operation and its rig's mods)")
    strip_plan_cmd = subcommands.add_parser("strip-plan", help="the exact edit list for stripping unresolved content (content-reference-unresolved): every file and field each id sits in, with vanilla weapons that fit an emptied slot; edits nothing")
    strip_plan_cmd.add_argument("mod", type=Path, help="mod working copy")
    strip_plan_cmd.add_argument("--vanilla-core", type=Path, required=True, help="RC8 starsector-core (read-only)")
    strip_plan_cmd.add_argument("--id", dest="only", action="append", help="limit to one id, as kind:id (e.g. weapon:vayra_gun); repeatable")
    strip_plan_cmd.add_argument("--expected", type=Path, help="also add PROPOSED expected changes (static layer) for the files the plan deletes to this expected-changes.json")
    strip_plan_cmd.add_argument("--build", help="build tag the strip lands in (required with --expected), e.g. r3")
    strip_plan_cmd.add_argument("--link", action="append", default=[], help="risk=ID, hyp=ID or test=ID breadcrumb for the expected changes; at least one is required with --expected")
    strip_plan_cmd.add_argument("--json", action="store_true")


def run_cli(args: argparse.Namespace) -> int:
    if args.command == "translate-export":
        output = args.output.expanduser().resolve()
        if Path(args.mod_dir).expanduser().resolve() in output.parents:
            print("bridgeforge: the translation JSON must not be written inside the mod", file=sys.stderr)
            return 2
        try:
            document = export_translation(args.mod_dir)
            prefill: dict[str, object] = {}
            if args.record:
                prefill["record"] = prefill_from_record(document, args.record)
            if args.reference:
                prefill["reference"] = prefill_from_reference(document, args.mod_dir, args.reference)
        except TranslationError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(document, ensure_ascii=False, indent=1), encoding="utf-8")
        blank = sum(1 for entry in document["entries"] if not entry["translation"])
        summary = {"output": str(output), "entries": document["entry_count"], "unique_sources": document["unique_source_count"], "prefill": prefill, "still_blank": blank}
        if args.json:
            print(json.dumps(summary, indent=2, ensure_ascii=False))
        else:
            print(f"Translation export: {output}")
            print(f"Entries: {document['entry_count']} ({document['unique_source_count']} unique sources); still blank: {blank}")
            for source, stats in prefill.items():
                print(f"Prefill from {source}: {stats}")
        return 0
    if args.command == "translate-apply":
        try:
            document = json.loads(args.translations.read_text(encoding="utf-8"))
            result = apply_translation(args.mod_dir, document, out_dir=args.out, in_place=args.in_place)
        except (OSError, json.JSONDecodeError, TranslationError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"Translation apply: {result['status']} -> {result['target']}")
            print(f"Applied: {result['applied']}; leftover non-English units: {result['leftover_cjk_units']}")
            for problem in result["problems"][:20]:
                print(f"  problem: {problem}")
        return 0 if result["status"] == "OK" else 1
    if args.command == "translate-tm":
        try:
            memory = export_project_go_tm(json.loads(args.translations.read_text(encoding="utf-8")), context=args.context)
        except (OSError, json.JSONDecodeError, KeyError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(memory, ensure_ascii=False, indent=1), encoding="utf-8")
        from collections import Counter as _Counter
        by_provenance = dict(_Counter(item["provenance"] for item in memory["entries"]))
        if args.json:
            print(json.dumps({"output": str(args.output), "entries": len(memory["entries"]), "by_provenance": by_provenance}, indent=2))
        else:
            print(f"Project Go translation memory: {args.output} ({len(memory['entries'])} entries; {by_provenance})")
            print("Import with: ssmt tm import <database.sqlite> json <this file>")
        return 0
    if args.command == "translate-check":
        try:
            result = check_translation(args.mod_dir)
        except TranslationError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"Translation check: {result['status']}; leftover non-English units: {result['leftover_count']}")
            for rel, count in list(result["leftover_by_file"].items())[:15]:
                print(f"  {count:5} {rel}")
            if result["design_type_keys_unused"]:
                print(f"designTypeColors keys no tech/manufacturer uses: {result['design_type_keys_unused']}")
        return 0 if result["status"] == "OK" else 1
    if args.command == "fix":
        options = {
            "target_game_version": args.target_game_version,
            "design_type": args.design_type,
            "id_prefixes": args.id_prefix,
            "design_color": args.design_color,
            "vanilla_core": args.vanilla_core,
            "type_id": args.type_id,
            "from_vanilla_id": args.from_vanilla_id,
            "faction_file": args.faction_file,
            "encodings": dict(item.split("=", 1) for item in (args.encoding or [])),
            "reference_core": args.reference_core,
            "hulls": args.hull,
            "declare_providers": [{"id": item.partition("=")[0], "name": item.partition("=")[2] or item.partition("=")[0]} for item in args.declare_provider] or None,
            "hull_zero_no_evidence": args.hull_zero_no_evidence,
            "allow_shadowed_edit": args.allow_shadowed_edit,
            "provider_roots": args.providers or None,
        }
        try:
            plan = compute_fix(args.mod_dir, args.finding, options)
        except FixerError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if not args.apply:
            diffs = {str(change.path): unified_diff_for_change(change) for change in plan.changes}
            if args.json:
                print(json.dumps({"finding_id": plan.finding_id, "dry_run": True, "diffs": diffs}, indent=2, sort_keys=True))
            else:
                for path, diff_text in diffs.items():
                    print(f"--- dry-run diff for {path} ---")
                    print(diff_text or "(no textual diff; binary or empty change)")
            return 0
        applied = apply_fix(plan)
        if plan.finding_id == "data-file-not-utf8" and options["encodings"]:
            from .fixers import record_named_encodings
            recorded = record_named_encodings(plan.mod_root, options["encodings"])
            if recorded is not None and not args.json:
                print(f"Named encodings recorded: {recorded}")
        try:
            rescan = scan_mod(plan.mod_root)
        except ValueError as exc:
            print(f"bridgeforge: fix applied but rescan failed: {exc}", file=sys.stderr)
            return 2
        finding_resolved = not any(finding.id == plan.finding_id for finding in rescan.findings)
        result = {"finding_id": plan.finding_id, "applied": applied, "finding_resolved": finding_resolved}
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            for item in applied:
                print(f"Fixed: {item['path']} (backup: {item['backup']})")
            print(f"Finding '{plan.finding_id}' {'resolved' if finding_resolved else 'STILL PRESENT'} after rescan.")
        return 0 if finding_resolved else 1
    if args.command == "strip-plan":
        from .strip_plan import StripPlanError, strip_plan
        try:
            result = strip_plan(args.mod, args.vanilla_core, args.only)
            if args.expected:
                from .strip_plan import propose_expected_changes
                if not args.build:
                    raise StripPlanError("--expected needs --build")
                links: dict[str, list[str]] = {}
                for item in args.link:
                    kind, separator, linked = item.partition("=")
                    if not separator or kind not in {"risk", "hyp", "test", "bug_class"} or not linked:
                        raise StripPlanError(f"--link expects risk|hyp|test|bug_class=ID, got {item!r}")
                    links.setdefault(kind, []).append(linked)
                result["expected_changes_added"] = propose_expected_changes(result, args.expected, build=args.build, links=links)
        except (StripPlanError, ValueError, OSError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            if not result["edits"]:
                print("Nothing to strip: no unresolved content references" + (" match --id." if args.only else "."))
            for edit in result["edits"]:
                print(f"{edit['file']}: {edit['action']} -- {edit['kind']}:{edit['id']}")
                substitutes = edit.get("substitutes")
                if substitutes and substitutes.get("candidates"):
                    more = substitutes["candidate_count"] - len(substitutes["candidates"])
                    print(f"    vanilla {substitutes['slot']} options: {', '.join(substitutes['candidates'])}" + (f" (+{more} more)" if more > 0 else ""))
                elif substitutes:
                    print(f"    {substitutes.get('note') or 'no vanilla weapon fits ' + str(substitutes['slot'])}")
            if result.get("expected_changes_added") is not None:
                print(f"PROPOSED expected changes added to {args.expected}: {', '.join(result['expected_changes_added']) or 'none (no file deletions)'}")
        return 0
    if args.command == "descriptions":
        from .descriptions import DescriptionsError, apply_draft, build_sheet
        try:
            if args.descriptions_command == "sheet":
                result = build_sheet(args.queue, args.vanilla_core)
                print(f"{result['entries']} missing description(s) in {result['mods']} mod(s). Written: {result['path']}")
            else:
                result = apply_draft(args.workspace, args.draft)
                print(f"Added {len(result['added'])} row(s); already present: {len(result['skipped_existing'])}.")
                print(f"Credits: {result['credits']}")
                print(f"Original-descriptions copy: {result['alternative']}")
        except (DescriptionsError, OSError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        return 0
    if args.command == "translate-batch":
        from .translate_batch import TranslateBatchError, agent_translator, translate_batch
        from .translation import TranslationError as TranslateApplyError
        base = (args.out or args.mod_dir).expanduser().resolve()
        work = args.work or base.with_name(base.name + ".translate-work")
        try:
            result = translate_batch(args.mod_dir, translator=agent_translator(args.agent), work_dir=work, out_dir=args.out,
                                     in_place=args.in_place, chunk=args.chunk, reference=args.reference, records=args.record, quiet=args.quiet)
        except (TranslateBatchError, TranslateApplyError, OSError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        else:
            print(f"Entries {result['entries']}, sent to the agent in {result['chunks']} chunk(s), translated {result['translated']}.")
            if result["stopped"]:
                print(f"Stopped: {result['stopped']}. Rerun the same command to continue from the checkpoint.")
            for number, problems in result["failed_chunks"].items():
                print(f"  chunk {number} rejected twice: {'; '.join(problems[:3])}")
            if result["applied"] is not None:
                print(f"Applied -> {args.out or args.mod_dir}; translate-check {result['check']['status']}, leftover non-English units: {result['check']['leftover_count']}")
            elif not result["stopped"]:
                print(f"Not applied: fix or rerun the rejected chunks (work folder {result['work_dir']}).")
        return 0 if result["applied"] is not None else 1
    if args.command == "renamed-ids":
        from .renamed_ids import find_renamed
        results = find_renamed(args.old_copy, args.new_copy, args.ids)
        if args.json:
            print(json.dumps(results, indent=2, ensure_ascii=False))
        else:
            for r in results:
                extra = (" -> " + ", ".join(r["renamed_to"])) if r.get("renamed_to") else ""
                near = ("; similar: " + ", ".join(f"{s['id']} ({s['name']})" for s in r["similar"])) if r.get("similar") else ""
                print(f"{r['verdict']:<16} {r['id']}{extra}{near}")
        return 0
    return 2
