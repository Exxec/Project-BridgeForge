"""Behaviour-discovery commands: archaeology, expected changes, lookup, novelty (ROADMAP 70 H2.1)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .behavior_discovery import add_expected_change, behavior_diff, check_expected_changes, DiscoveryError, evaluate_behavior_release, update_expected_change_status, write_archaeology, write_behavior_model, write_coverage, write_probe_baseline, write_save_baseline, write_synthesized_tests


def add_parser(subcommands) -> None:
    archaeology_cmd = subcommands.add_parser("archaeology", help="build a deterministic static architecture and cross-reference map (read-only)")
    archaeology_cmd.add_argument("mod_directory", type=Path)
    archaeology_cmd.add_argument("--output", required=True, type=Path)
    archaeology_cmd.add_argument("--save-aliases", type=Path, help="optional real-save alias evidence for confirmed persistent classes")
    archaeology_cmd.add_argument("--vanilla-core", type=Path, help="read-only starsector-core, so assets a mod borrows from vanilla are not reported as missing")
    archaeology_cmd.add_argument("--json", action="store_true")
    for command_name, help_text in (
        ("behavior-map", "derive the D1 behavior model, risks, hypotheses and unknowns from archaeology"),
        ("risk-register", "derive the D1 risk register and companion behavior artifacts from archaeology"),
    ):
        command = subcommands.add_parser(command_name, help=help_text)
        command.add_argument("architecture", type=Path)
        command.add_argument("--output", required=True, type=Path)
        command.add_argument("--json", action="store_true")
    hypotheses_cmd = subcommands.add_parser("hypotheses", help="derive D1 artifacts, or synthesize D3 tests with --tests")
    hypotheses_cmd.add_argument("input", type=Path, help="architecture.json, or hypotheses.json with --tests")
    hypotheses_cmd.add_argument("--output", required=True, type=Path)
    hypotheses_cmd.add_argument("--tests", action="store_true", help="synthesize proposed adversarial tests from hypotheses.json")
    hypotheses_cmd.add_argument("--json", action="store_true")
    baseline_cmd = subcommands.add_parser("probe-baseline", help="import captured observations as a no-verdict D2 baseline")
    baseline_cmd.add_argument("input", type=Path)
    baseline_cmd.add_argument("--build", required=True)
    baseline_cmd.add_argument("--scenario", required=True)
    baseline_cmd.add_argument("--reference-kind", choices=["old-game-rig", "build", "partial-original", "static-floor"], default="build")
    baseline_cmd.add_argument("--output", required=True, type=Path)
    baseline_cmd.add_argument("--json", action="store_true")
    save_baseline_cmd = subcommands.add_parser("save-baseline", help="convert a historical Starsector save into a no-verdict D2 baseline (read-only input)")
    save_baseline_cmd.add_argument("save", type=Path, help="save directory or campaign.xml")
    save_baseline_cmd.add_argument("--build", required=True)
    save_baseline_cmd.add_argument("--scenario", required=True)
    save_baseline_cmd.add_argument("--track-class", action="append", default=[])
    save_baseline_cmd.add_argument("--track-id", action="append", default=[])
    save_baseline_cmd.add_argument("--mod-dir", type=Path)
    save_baseline_cmd.add_argument("--output", required=True, type=Path)
    save_baseline_cmd.add_argument("--json", action="store_true")
    expect_cmd = subcommands.add_parser("expect", help="validate D4/D5 expected-change decisions")
    expect_subcommands = expect_cmd.add_subparsers(dest="expect_command", required=True)
    expect_check_cmd = expect_subcommands.add_parser("check", help="validate expected-changes.json and its breadcrumbs")
    expect_check_cmd.add_argument("expected", type=Path)
    expect_check_cmd.add_argument("--artifact", action="append", type=Path, default=[])
    expect_check_cmd.add_argument("--known-build", action="append", default=[])
    expect_check_cmd.add_argument("--output", type=Path)
    expect_check_cmd.add_argument("--json", action="store_true")
    expect_add_cmd = expect_subcommands.add_parser("add", help="add a PROPOSED expected change beside a mod's reports")
    expect_add_cmd.add_argument("expected", type=Path)
    expect_add_cmd.add_argument("--mod-id", required=True)
    expect_add_cmd.add_argument("--id", required=True, dest="change_id")
    expect_add_cmd.add_argument("--build", required=True)
    expect_add_cmd.add_argument("--layer", required=True, choices=["runtime", "save", "static"])
    expect_add_cmd.add_argument("--summary", required=True)
    expect_add_cmd.add_argument("--why", required=True)
    expect_add_cmd.add_argument("--observation", required=True)
    expect_add_cmd.add_argument("--subject", required=True)
    expect_add_cmd.add_argument("--field")
    expect_add_cmd.add_argument("--change", required=True, choices=["from_to", "count", "added", "removed", "renamed", "any"])
    expect_add_cmd.add_argument("--from", dest="from_value")
    expect_add_cmd.add_argument("--to", dest="to_value")
    expect_add_cmd.add_argument("--old")
    expect_add_cmd.add_argument("--new")
    expect_add_cmd.add_argument("--link", action="append", default=[], metavar="KIND=ID", help="risk, hyp, test or bug_class breadcrumb; repeatable")
    expect_add_cmd.add_argument("--proposed-by", default="agent")
    expect_add_cmd.add_argument("--json", action="store_true")
    for action in ("approve", "retire"):
        decision_cmd = expect_subcommands.add_parser(action, help=f"{action} an expected-change decision")
        decision_cmd.add_argument("expected", type=Path)
        decision_cmd.add_argument("id")
        decision_cmd.add_argument("--by", required=True)
        decision_cmd.add_argument("--on", required=action == "approve")
        if action == "retire":
            decision_cmd.add_argument("--why", required=True)
        decision_cmd.add_argument("--json", action="store_true")
    diff_cmd = subcommands.add_parser("behavior-diff", help="compare two D2 baselines and classify every observation delta")
    diff_cmd.add_argument("before", type=Path)
    diff_cmd.add_argument("after", type=Path)
    diff_cmd.add_argument("--expected", type=Path)
    diff_cmd.add_argument("--before-map", type=Path, help="D0 architecture.json for the original/reference")
    diff_cmd.add_argument("--after-map", type=Path, help="D0 architecture.json for the working/revived build")
    diff_cmd.add_argument("--output", required=True, type=Path)
    diff_cmd.add_argument("--json", action="store_true")
    behavior_release_cmd = subcommands.add_parser("release-behavior-evaluate", help="evaluate the D5/D6 behavior release gate")
    behavior_release_cmd.add_argument("diff", type=Path)
    behavior_release_cmd.add_argument("--risks", type=Path)
    behavior_release_cmd.add_argument("--unknowns", type=Path)
    behavior_release_cmd.add_argument("--output", type=Path)
    behavior_release_cmd.add_argument("--json", action="store_true")
    coverage_cmd = subcommands.add_parser("coverage", help="build the D6 counts-only behavior coverage matrix")
    coverage_cmd.add_argument("behavior", type=Path)
    coverage_cmd.add_argument("--baseline", action="append", type=Path, default=[])
    coverage_cmd.add_argument("--diff", type=Path)
    coverage_cmd.add_argument("--tests", type=Path)
    coverage_cmd.add_argument("--unknowns", type=Path)
    coverage_cmd.add_argument("--output", required=True, type=Path)
    coverage_cmd.add_argument("--json", action="store_true")
    decide_cmd = subcommands.add_parser("behavior-decide", help="apply written decisions to D1 risks/unknowns -> risks.decided.json / unknowns.decided.json for the release gate")
    decide_cmd.add_argument("discovery_dir", type=Path, help="folder holding behavior.json, risks.json, unknowns.json")
    decide_cmd.add_argument("decisions", type=Path, help="decisions JSON (schema_version 1; each decision: select, status, why, by, on[, evidence, applies_to])")
    decide_cmd.add_argument("--output", type=Path, help="where the .decided.json files go (default: the discovery folder)")
    decide_cmd.add_argument("--json", action="store_true")
    lookup_cmd = subcommands.add_parser("lookup", help="query a mod's archaeology graph for a class/id/file: definitions, references, related classes, lifecycle, save evidence, source/bytecode status, findings, runtime observations, and an inspection priority")
    lookup_cmd.add_argument("thing", nargs="?", help="class name (full or short), id, file path or symbol; omit with --top for the treasure map")
    lookup_cmd.add_argument("--mod", required=True, type=Path, help="mod working copy")
    lookup_cmd.add_argument("--discovery", type=Path, help="discovery folder (default: <Mod>/reports/discovery/<working folder name>)")
    lookup_cmd.add_argument("--top", type=int, default=0, help="also rank the mod's classes and registrations by inspection priority")
    lookup_cmd.add_argument("--limit", type=int, default=3, help="matches to show in detail (default 3)")
    lookup_cmd.add_argument("--vanilla-core", type=Path, help="read-only starsector-core, used when the graph has to be rebuilt")
    lookup_cmd.add_argument("--json", action="store_true")
    novelty_cmd = subcommands.add_parser("novelty", help="compare a mod's fingerprint (API usage, lifecycle patterns, structures, findings, weak ownership) with the mods already seen")
    novelty_cmd.add_argument("mod", type=Path, help="mod working copy")
    novelty_cmd.add_argument("--discovery", type=Path)
    novelty_cmd.add_argument("--corpus", type=Path, help="fingerprint folder (default: bridgeforge-state/corpus-fingerprints)")
    novelty_cmd.add_argument("--record", action="store_true", help="add or refresh this mod's fingerprint in the corpus")
    novelty_cmd.add_argument("--vanilla-core", type=Path)
    novelty_cmd.add_argument("--json", action="store_true")


def run_cli(args: argparse.Namespace) -> int:
    if args.command == "lookup":
        from .lookup import lookup
        if not args.thing and not args.top:
            print("bridgeforge: give a thing to look up, or --top N", file=sys.stderr)
            return 2
        result = lookup(args.mod, args.thing, discovery_dir=args.discovery, top=args.top, limit=args.limit, vanilla_core=args.vanilla_core)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0 if result.get("status") != "NOT_FOUND" else 1
        print(f"Graph: {result['graph']}; behavior map: {'yes' if result['behavior_map'] else 'no'}; baselines: {result['baselines']}")
        if args.thing:
            if not result["matches"]:
                print(f"No match for {args.thing!r}.")
            for extra in result["matches"][args.limit:]:
                print(f"  also matches: {extra['kind']} {extra['name']}")
            for item in result.get("items", []):
                print(f"\n== {item['kind']} {item['name']}  (inspection priority {item['priority']})")
                for reason in item["priority_reasons"]:
                    print(f"   {reason}")
                sections = [("Defined by", item["definitions"]), ("Source/bytecode", [item["source_bytecode_status"]] if item["source_bytecode_status"] != "-" else []),
                            ("Lifecycle hooks", item["lifecycle_hooks"]), ("Registrations", item["registrations"]), ("Persistent state", item["persistent_state"]),
                            ("Save/probe observations", item["save_and_probe_observations"]), ("Findings", item["findings"]), ("Related", item["related"]),
                            ("Behaviours", [f"{b['id']} {b['lifecycle']} runtime_verified={b['runtime_verified']}" for b in item["behaviors"]]), ("External mods", item["external_mods"])]
                for title, values in sections:
                    if values:
                        print(f"   {title}: " + "; ".join(values[:8]) + (f" (+{len(values) - 8} more)" if len(values) > 8 else ""))
                for direction, table in (("<-", item["references_in"]), ("->", item["references_out"])):
                    for relation, targets in table.items():
                        print(f"   {direction} {relation} ({len(targets)}): " + ", ".join(targets[:5]) + (" ..." if len(targets) > 5 else ""))
        if result.get("treasure_map"):
            print("\nInspection priority (archaeology, not errors):")
            for entry in result["treasure_map"]:
                print(f"  {entry['priority']:>3}  {entry['name']}  [{'; '.join(reason.split(' ', 1)[1] for reason in entry['reasons'])}]")
        return 0 if result.get("status") != "NOT_FOUND" else 1
    if args.command == "novelty":
        from .novelty import novelty
        result = novelty(args.mod, discovery_dir=args.discovery, corpus_dir=args.corpus, record=args.record, vanilla_core=args.vanilla_core)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        print(f"Novelty for {result['mod_id']} against {result['corpus_size']} other mod(s){' (small corpus)' if result['small_corpus'] else ''}:")
        print(f"  {result['patterns_seen']} of {result['patterns_total']} patterns already seen")
        print(f"  {result['unusual_structures']} unusual structures (seen in fewer than 2 other mods)")
        print(f"  {result['new_api_usages']} API usages not seen in previous mods")
        print(f"  {result['new_lifecycle_patterns']} lifecycle patterns not previously observed")
        print(f"  {result['new_finding_kinds']} finding kinds not seen before")
        print(f"  {result['weak_ownership']} IDs/functions with weak ownership or reference evidence")
        for key, values in result["examples"].items():
            if values:
                print(f"  e.g. {key}: " + "; ".join(values[:5]))
        if result.get("recorded"):
            print(f"Recorded: {result['recorded']}")
        return 0
    if args.command == "behavior-decide":
        from .behavior_discovery import write_behavior_decisions
        try:
            result = write_behavior_decisions(args.discovery_dir, args.decisions, args.output)
        except (DiscoveryError, OSError, json.JSONDecodeError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Decided files: {result['risks']} / {result['unknowns']}")
            print(f"Applied: {result['applied']}; unknowns still open: {len(result['unknowns_open'])}; HIGH risks still open: {len(result['high_risks_open'])}")
        return 0 if not result["unknowns_open"] and not result["high_risks_open"] else 1
    if args.command in {"archaeology", "behavior-map", "risk-register", "hypotheses", "probe-baseline", "save-baseline", "expect", "behavior-diff", "release-behavior-evaluate", "coverage"}:
        try:
            if args.command == "archaeology":
                result = write_archaeology(args.mod_directory, args.output, save_aliases=args.save_aliases, vanilla_core=args.vanilla_core)
            elif args.command in {"behavior-map", "risk-register"}:
                result = write_behavior_model(args.architecture, args.output)
            elif args.command == "hypotheses":
                result = {"tests": str(write_synthesized_tests(args.input, args.output))} if args.tests else write_behavior_model(args.input, args.output)
            elif args.command == "probe-baseline":
                result = {"baseline": str(write_probe_baseline(args.input, args.output, build=args.build, scenario=args.scenario, reference_kind=args.reference_kind))}
            elif args.command == "save-baseline":
                result = {"baseline": str(write_save_baseline(args.save, args.output, build=args.build, scenario=args.scenario, track_classes=args.track_class, track_ids=args.track_id, mod_dir=args.mod_dir))}
            elif args.command == "expect":
                if args.expect_command == "check":
                    result = check_expected_changes(args.expected, linked_artifacts=args.artifact, known_builds=args.known_build)
                    if args.output:
                        args.output.parent.mkdir(parents=True, exist_ok=True)
                        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                elif args.expect_command == "add":
                    def scalar(value: str | None) -> object:
                        if value is None:
                            return None
                        try:
                            return json.loads(value)
                        except json.JSONDecodeError:
                            return value
                    match = {"observation": args.observation, "subject": args.subject, "change": args.change}
                    for key, value in (("field", args.field), ("from", args.from_value), ("to", args.to_value), ("old", args.old), ("new", args.new)):
                        if value is not None:
                            match[key] = scalar(value)
                    links: dict[str, list[str]] = {}
                    for item in args.link:
                        kind, separator, linked_id = item.partition("=")
                        if not separator or kind not in {"risk", "hyp", "test", "bug_class"} or not linked_id:
                            raise DiscoveryError(f"--link expects risk|hyp|test|bug_class=ID, got {item!r}")
                        links.setdefault(kind, []).append(linked_id)
                    result = add_expected_change(args.expected, mod_id=args.mod_id, change_id=args.change_id, build=args.build, layer=args.layer, summary=args.summary, why=args.why, match=match, links=links, proposed_by=args.proposed_by)
                else:
                    result = update_expected_change_status(args.expected, args.id, status="APPROVED" if args.expect_command == "approve" else "RETIRED", actor=args.by, on=args.on, why=getattr(args, "why", None))
            elif args.command == "behavior-diff":
                result = behavior_diff(args.before, args.after, expected_path=args.expected, before_map_path=args.before_map, after_map_path=args.after_map)
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            elif args.command == "release-behavior-evaluate":
                result = evaluate_behavior_release(args.diff, risks_path=args.risks, unknowns_path=args.unknowns)
                if args.output:
                    args.output.parent.mkdir(parents=True, exist_ok=True)
                    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            else:
                path = write_coverage(args.behavior, args.output, baselines=args.baseline, diff_path=args.diff, tests_path=args.tests, unknowns_path=args.unknowns)
                result = json.loads(path.read_text(encoding="utf-8"))
                result["output"] = str(path)
        except (DiscoveryError, json.JSONDecodeError, OSError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if getattr(args, "json", False):
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(json.dumps(result, indent=2, sort_keys=True))
        if args.command == "expect" and result.get("status") == "FAIL":
            return 1
        if args.command == "release-behavior-evaluate" and result.get("status") == "FAIL":
            return 1
        return 0
    return 2
