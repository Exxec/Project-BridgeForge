"""Corpus, release and library analysis commands (ROADMAP 70 H2.1)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .corpus.corpus import compare_corpus
from .corpus.corpus_audit import audit_directories, write_corpus_audit
from .cross_mod import analyze_mod_set
from .evaluation import evaluate_releases
from .identity_registry import build_campaign_identity_inventory, check_campaign_identity_references, load_campaign_identity_inventory
from .library_api import check_dependency_apis, inventory_library_api, match_library_imports
from .lineage import analyze_release_lineage
from .models import TargetProfile
from .revival_audit import audit_revival


def add_parser(subcommands) -> None:
    corpus = subcommands.add_parser("corpus-compare", help="compare an explicitly selected local mod to a sanitized baseline")
    corpus.add_argument("mod_directory", type=Path)
    corpus.add_argument("--baseline", required=True, type=Path)
    corpus_audit = subcommands.add_parser("corpus-audit", help="write a read-only aggregate report for explicit mod directories")
    corpus_audit.add_argument("mod_directories", type=Path, nargs="+")
    corpus_audit.add_argument("--output", required=True, type=Path)
    corpus_audit.add_argument("--target-starsector", default="0.98.x")
    corpus_audit.add_argument("--target-java", type=int, default=17)
    corpus_audit.add_argument("--continue-on-error", action="store_true")
    corpus_audit.add_argument("--max-files-per-mod", type=int)
    corpus_audit.add_argument("--max-jars-per-mod", type=int)
    cross_mod = subcommands.add_parser("cross-mod-analyze", help="build a read-only dependency, class, and campaign-ID graph for explicit mod directories")
    cross_mod.add_argument("mod_directories", type=Path, nargs="+")
    cross_mod.add_argument("--target-starsector", default="0.98.x")
    cross_mod.add_argument("--target-java", type=int, default=17)
    cross_mod.add_argument("--output", type=Path)
    cross_mod.add_argument("--alias", action="append", default=[], metavar="DIRECTORY_NAME=MOD_ID", help="explicit identity for a selected non-standard metadata layout; repeatable")
    cross_mod.add_argument("--vanilla-core", type=Path, help="read-only starsector-core; enables vanilla_script_shadow_collisions (two mods shipping a modified copy of the same vanilla script, where load order silently picks a winner)")
    identity_inventory = subcommands.add_parser("campaign-identity-inventory", help="inventory source-defined campaign IDs from explicit mod directories")
    identity_inventory.add_argument("mod_directories", type=Path, nargs="+")
    identity_inventory.add_argument("--target-starsector", default="0.98.x")
    identity_inventory.add_argument("--target-java", type=int, default=17)
    identity_inventory.add_argument("--output", required=True, type=Path)
    identity_check = subcommands.add_parser("campaign-identity-check", help="resolve campaign literal lookups against an explicit identity inventory")
    identity_check.add_argument("mod_directory", type=Path)
    identity_check.add_argument("--inventory", required=True, type=Path)
    identity_check.add_argument("--target-starsector", default="0.98.x")
    identity_check.add_argument("--target-java", type=int, default=17)
    identity_check.add_argument("--output", type=Path)
    lineage = subcommands.add_parser("release-lineage", help="compare an explicitly ordered sequence of mod releases without modifying them")
    lineage.add_argument("release_directories", type=Path, nargs="+")
    lineage.add_argument("--target-starsector", default="0.98.x")
    lineage.add_argument("--target-java", type=int, default=17)
    lineage.add_argument("--output", type=Path)
    evaluation = subcommands.add_parser("release-evaluate", help="compare two release directories without modifying either")
    evaluation.add_argument("before_directory", type=Path)
    evaluation.add_argument("after_directory", type=Path)
    evaluation.add_argument("--target-starsector", default="0.98.x")
    evaluation.add_argument("--target-java", type=int, default=17)
    evaluation.add_argument("--output", type=Path)
    revival_audit = subcommands.add_parser("revival-audit", help="audit final revival evidence and optionally attest its release ZIP")
    revival_audit.add_argument("candidate", type=Path)
    revival_audit.add_argument("--archive", type=Path)
    revival_audit.add_argument("--output", type=Path)
    api_inventory = subcommands.add_parser("library-api-inventory", help="inventory class symbols in a supplied local library JAR")
    api_inventory.add_argument("jar", type=Path)
    api_inventory.add_argument("--output", type=Path)
    api_inventory.add_argument("--library-id")
    api_inventory.add_argument("--library-version")
    api_match = subcommands.add_parser("library-api-match", help="compare a mod's imports with a supplied local library API inventory")
    api_match.add_argument("mod_directory", type=Path)
    api_match.add_argument("inventory", type=Path)
    api_match.add_argument("--target-starsector", default="0.98.x")
    api_match.add_argument("--target-java", type=int, default=17)
    api_match.add_argument("--output", type=Path)
    dependency_api = subcommands.add_parser("dependency-api-check", help="compare direct optional-mod imports with explicit local API inventories")
    dependency_api.add_argument("mod_directory", type=Path)
    dependency_api.add_argument("--inventory", type=Path, action="append", required=True)
    dependency_api.add_argument("--target-starsector", default="0.98.x")
    dependency_api.add_argument("--target-java", type=int, default=17)
    dependency_api.add_argument("--output", type=Path)
    api_diff_cmd = subcommands.add_parser("api-diff", help="compare two game API jars (e.g. an old starfarer.api.jar and RC8's): every public class, method and field removed or changed, with same-name candidates for where it went")
    api_diff_cmd.add_argument("old", type=Path, help="older starfarer.api.jar, or the starsector-core folder holding it")
    api_diff_cmd.add_argument("new", type=Path, help="newer starfarer.api.jar, or the starsector-core folder holding it")
    api_diff_cmd.add_argument("--output", type=Path, help="write the JSON catalogue here (for compile-check --api-diff)")
    api_diff_cmd.add_argument("--json", action="store_true")


def run_cli(args: argparse.Namespace) -> int:
    if args.command == "corpus-audit":
        try:
            report = audit_directories(args.mod_directories, TargetProfile(args.target_starsector, args.target_java), args.continue_on_error, args.max_files_per_mod, args.max_jars_per_mod)
            output = write_corpus_audit(report, args.output, args.mod_directories)
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        print(f"Audited {report['mod_count']} mod(s): {output}")
        return 0
    if args.command == "cross-mod-analyze":
        try:
            aliases = {}
            for item in args.alias:
                directory_name, separator, mod_id = item.partition("=")
                if not separator or not directory_name or not mod_id or directory_name in aliases:
                    raise ValueError("Each --alias must be a unique DIRECTORY_NAME=MOD_ID pair.")
                aliases[directory_name] = mod_id
            result = analyze_mod_set(args.mod_directories, TargetProfile(args.target_starsector, args.target_java), aliases, args.vanilla_core)
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        payload = json.dumps(result, indent=2, sort_keys=True)
        if args.output:
            output = args.output.expanduser().resolve()
            for directory in args.mod_directories:
                try:
                    output.relative_to(directory.expanduser().resolve())
                except ValueError:
                    continue
                print("bridgeforge: Cross-mod analysis output must not be inside an input mod directory.", file=sys.stderr)
                return 2
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(payload + "\n", encoding="utf-8")
            print(f"Cross-mod analysis: {result['mod_count']} mod(s); {output}")
        else:
            print(payload)
        return 0
    if args.command == "campaign-identity-inventory":
        try:
            result = build_campaign_identity_inventory(args.mod_directories, TargetProfile(args.target_starsector, args.target_java))
            output = args.output.expanduser().resolve()
            for directory in args.mod_directories:
                try:
                    output.relative_to(directory.expanduser().resolve())
                except ValueError:
                    continue
                raise ValueError("Campaign identity inventory output must not be inside an input mod directory.")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        print(f"Campaign identity inventory: {len(result['entries'])} entry(s); {output}")
        return 0
    if args.command == "campaign-identity-check":
        try:
            inventory = load_campaign_identity_inventory(args.inventory)
            result = check_campaign_identity_references(args.mod_directory, inventory, TargetProfile(args.target_starsector, args.target_java))
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        payload = json.dumps(result, indent=2, sort_keys=True)
        if args.output:
            output = args.output.expanduser().resolve()
            try:
                output.relative_to(args.mod_directory.expanduser().resolve())
            except ValueError:
                pass
            else:
                print("bridgeforge: Campaign identity check output must not be inside the input mod directory.", file=sys.stderr)
                return 2
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(payload + "\n", encoding="utf-8")
            print(f"Campaign identity checks: {len(result['checks'])}; report: {output}")
        else:
            print(payload)
        return 0
    if args.command == "release-lineage":
        try:
            result = analyze_release_lineage(args.release_directories, TargetProfile(args.target_starsector, args.target_java))
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        payload = json.dumps(result, indent=2, sort_keys=True)
        if args.output:
            output = args.output.expanduser().resolve()
            for directory in args.release_directories:
                try:
                    output.relative_to(directory.expanduser().resolve())
                except ValueError:
                    continue
                print("bridgeforge: Release lineage output must not be inside an input release directory.", file=sys.stderr)
                return 2
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(payload + "\n", encoding="utf-8")
            print(f"Release lineage: {result['release_count']} release(s); {output}")
        else:
            print(payload)
        return 0
    if args.command == "library-api-inventory":
        try:
            result = inventory_library_api(args.jar, args.library_id, args.library_version)
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        payload = json.dumps(result, indent=2, sort_keys=True)
        if args.output:
            output = args.output.expanduser().resolve()
            if output == args.jar.expanduser().resolve():
                print("bridgeforge: Library API inventory output must not replace the input JAR.", file=sys.stderr)
                return 2
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(payload + "\n", encoding="utf-8")
            print(f"Inventoried {result['class_count']} class symbol(s): {output}")
        else:
            print(payload)
        return 0
    if args.command == "library-api-match":
        try:
            inventory = json.loads(args.inventory.expanduser().resolve().read_text(encoding="utf-8"))
            result = match_library_imports(args.mod_directory, inventory, TargetProfile(args.target_starsector, args.target_java))
        except (OSError, ValueError, json.JSONDecodeError, KeyError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        payload = json.dumps(result, indent=2, sort_keys=True)
        if args.output:
            output = args.output.expanduser().resolve()
            try:
                output.relative_to(args.mod_directory.expanduser().resolve())
            except ValueError:
                pass
            else:
                print("bridgeforge: API match output must not be inside the input mod directory.", file=sys.stderr)
                return 2
            output.write_text(payload + "\n", encoding="utf-8")
            print(f"Reported {len(result['migration_candidates'])} research candidate(s): {output}")
        else:
            print(payload)
        return 0
    if args.command == "dependency-api-check":
        try:
            inventories = [json.loads(path.expanduser().resolve().read_text(encoding="utf-8")) for path in args.inventory]
            result = check_dependency_apis(args.mod_directory, inventories, TargetProfile(args.target_starsector, args.target_java))
        except (OSError, ValueError, json.JSONDecodeError, KeyError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        payload = json.dumps(result, indent=2, sort_keys=True)
        if args.output:
            output = args.output.expanduser().resolve()
            try:
                output.relative_to(args.mod_directory.expanduser().resolve())
            except ValueError:
                pass
            else:
                print("bridgeforge: Dependency API check output must not be inside the input mod directory.", file=sys.stderr)
                return 2
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(payload + "\n", encoding="utf-8")
            print(f"Dependency API checks: {len(result['checks'])}; report: {output}")
        else:
            print(payload)
        return 0
    if args.command == "corpus-compare":
        try:
            result = compare_corpus(args.mod_directory, args.baseline)
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(result, indent=2))
        return 0 if result["status"] == "PASS" else 1
    if args.command == "release-evaluate":
        try:
            result = evaluate_releases(args.before_directory, args.after_directory, TargetProfile(args.target_starsector, args.target_java))
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        payload = json.dumps(result, indent=2, sort_keys=True)
        if args.output:
            output = args.output.expanduser().resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(payload + "\n", encoding="utf-8")
            print(f"Release evaluation: {output}")
        else:
            print(payload)
        return 0
    if args.command == "revival-audit":
        try:
            result = audit_revival(args.candidate, args.archive)
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        payload = json.dumps(result, indent=2, sort_keys=True)
        if args.output:
            output = args.output.expanduser().resolve()
            if output.is_relative_to(args.candidate.expanduser().resolve()):
                print("bridgeforge: Revival audit output must not be inside the candidate directory.", file=sys.stderr)
                return 2
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(payload + "\n", encoding="utf-8")
            print(f"Revival audit: {output} ({result['status']})")
        else:
            print(payload)
        return 0 if result["status"] in {"PASS", "REVIEW"} else 1
    if args.command == "api-diff":
        import zipfile
        from .api_diff import ApiDiffError, diff_api_jars
        try:
            result = diff_api_jars(args.old, args.new)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except (ApiDiffError, OSError, zipfile.BadZipFile) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            summary = result["summary"]
            print(f"API_DIFF: {result['old']['classes']} -> {result['new']['classes']} classes; "
                  f"{summary['classes_removed']} removed, {summary['classes_added']} added, {summary['classes_changed']} changed; "
                  f"{summary['methods_removed']} methods and {summary['fields_removed']} fields removed")
            for dotted, entry in list(result["changed_classes"].items())[:40]:
                for method in entry["methods_removed"]:
                    leads = method["same_signature_elsewhere"] or method["same_name_in_class"]
                    print(f"  - {dotted.rsplit('.', 1)[-1]}.{method['signature'].split(' ', 1)[-1]}" + (f"  -> {', '.join(leads)}" if leads else ""))
            if args.output:
                print(f"Written: {args.output}")
        return 0
    return 2
