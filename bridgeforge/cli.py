from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .models import TargetProfile
from .report import write_artifacts
from .scanner import scan_mod
from .migrate import apply_plan, build_plan
from .workspace import create_workspace, rollback
from .build import create_build_profile, preview_shell_command
from .build import compile_feedback, package_compiled_jar, run_compile
from .library_registry import load_library_registry
from .review import create_review_bundle
from .validate import validate_workspace
from .save_risk import analyze_save_risk
from .pipeline import run_pipeline
from .packs import discover_packs, resolve_pack_rule_paths
from .runtime import create_runtime_profile, run_runtime_smoke
from .interface import export_patch, inspect_workspace
from .opportunities import analyze_opportunities
from .doctor import doctor
from .conflicts import detect_conflicts
from .provenance import write_provenance
from .corpus import compare_corpus
from .corpus_audit import audit_directories, write_corpus_audit
from .cross_mod import analyze_mod_set
from .identity_registry import build_campaign_identity_inventory, check_campaign_identity_references, load_campaign_identity_inventory
from .decompiler import create_decompiler_review, run_decompiler_review
from .lineage import analyze_release_lineage
from .library_api import check_dependency_apis, inventory_library_api, match_library_imports
from .archive_intake import inspect_zip_archive, stage_zip_archive
from .evaluation import evaluate_releases
from .bytecode import BytecodeUnavailable, inspect_bytecode
from .bytecode_diff import diff_bytecode
from .bytecode_rules import apply_bytecode_class, apply_bytecode_jar, plan_bytecode
from .pack_candidate import create_migration_pack_candidate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bridgeforge", description="Safe, explainable legacy Starsector mod analysis and migration.")
    subcommands = parser.add_subparsers(dest="command", required=True)
    scan = subcommands.add_parser("scan", help="scan a mod directory without modifying it")
    scan.add_argument("mod_directory", type=Path)
    scan.add_argument("--output", type=Path, default=Path("bridgeforge-artifacts"))
    scan.add_argument("--target-starsector", default="0.98.x")
    scan.add_argument("--target-java", type=int, default=17)
    bytecode = subcommands.add_parser("bytecode-inspect", help="inspect class/JAR symbolic references without rewriting")
    bytecode.add_argument("input", type=Path, nargs="+")
    bytecode.add_argument("--output", type=Path)
    bytecode_diff = subcommands.add_parser("bytecode-diff", help="compare class/JAR symbolic and structural inventories")
    bytecode_diff.add_argument("before", type=Path, nargs="+")
    bytecode_diff.add_argument("--after", required=True, type=Path, nargs="+")
    bytecode_diff.add_argument("--output", type=Path)
    bytecode_plan = subcommands.add_parser("bytecode-plan", help="produce review-only exact bytecode remap candidates")
    bytecode_plan.add_argument("input", type=Path, nargs="+")
    bytecode_plan.add_argument("--rules", required=True, type=Path)
    bytecode_plan.add_argument("--output", type=Path)
    bytecode_apply = subcommands.add_parser("bytecode-apply", help="apply exact approved bytecode remaps to an output .class copy")
    bytecode_apply.add_argument("input", type=Path)
    bytecode_apply.add_argument("--rules", required=True, type=Path)
    bytecode_apply.add_argument("--approve", required=True, action="append")
    bytecode_apply.add_argument("--output", required=True, type=Path)
    workspace = subcommands.add_parser("workspace", help="create an immutable-reference workspace and working copy")
    workspace.add_argument("mod_directory", type=Path)
    workspace.add_argument("--output", required=True, type=Path)
    plan = subcommands.add_parser("plan", help="produce an explicit migration plan for a workspace")
    plan.add_argument("workspace", type=Path)
    plan.add_argument("--target-starsector", default="0.98.x")
    plan.add_argument("--target-java", type=int, default=17)
    plan.add_argument("--rules", type=Path, action="append", default=[], metavar="PACK_JSON", help="additional migration-rule pack (repeatable)")
    plan.add_argument("--pack", action="append", default=[], metavar="PACK_ID", help="bundled migration pack to use (repeatable)")
    apply = subcommands.add_parser("apply", help="apply only explicitly approved planned rules")
    apply.add_argument("workspace", type=Path)
    apply.add_argument("--approve", action="append", default=[], metavar="RULE_ID")
    apply.add_argument("--safe", action="store_true", help="apply all SAFE planned rules; REVIEW rules still need --approve")
    restore = subcommands.add_parser("rollback", help="restore a working copy from a checkpoint")
    restore.add_argument("workspace", type=Path)
    restore.add_argument("checkpoint")
    build = subcommands.add_parser("build-plan", help="model a compile environment without running javac")
    build.add_argument("workspace", type=Path)
    build.add_argument("--target-starsector", default="0.98.x")
    build.add_argument("--target-java", type=int, default=17)
    build.add_argument("--jdk", type=Path)
    build.add_argument("--api-jar", type=Path, action="append", default=[])
    build.add_argument("--starsector-install", type=Path, help="explicit local Starsector install; hash-record its core compile classpath")
    build.add_argument("--dependency-jar", type=Path, action="append", default=[])
    build.add_argument("--library-registry", type=Path, help="local dependency-id -> jar-path map (never bundled or committed)")
    compile_command = subcommands.add_parser("compile", help="run the explicit workspace build profile")
    compile_command.add_argument("workspace", type=Path)
    package = subcommands.add_parser("package-jar", help="package successful workspace classes into a reviewable JAR output copy")
    package.add_argument("workspace", type=Path)
    package.add_argument("input_jar")
    package.add_argument("--output-name")
    feedback = subcommands.add_parser("compile-feedback", help="link compiler evidence to planned migration candidates")
    feedback.add_argument("workspace", type=Path)
    review = subcommands.add_parser("review-bundle", help="create a bounded human/agent review handoff")
    review.add_argument("workspace", type=Path)
    validate = subcommands.add_parser("validate", help="run workspace-integrity and structural validation")
    validate.add_argument("workspace", type=Path)
    validate.add_argument("--target-starsector", default="0.98.x")
    validate.add_argument("--target-java", type=int, default=17)
    save_risk = subcommands.add_parser("save-risk", help="flag changed persistent-identifier-shaped fields")
    save_risk.add_argument("workspace", type=Path)
    pipeline = subcommands.add_parser("pipeline", help="run the auditable Bridgeforge modernization pipeline")
    pipeline.add_argument("workspace", type=Path)
    pipeline.add_argument("--target-starsector", default="0.98.x")
    pipeline.add_argument("--target-java", type=int, default=17)
    pipeline.add_argument("--rules", type=Path, action="append", default=[])
    pipeline.add_argument("--pack", action="append", default=[])
    pipeline.add_argument("--approve", action="append", default=[])
    pipeline.add_argument("--safe", action="store_true")
    pipeline.add_argument("--jdk", type=Path)
    pipeline.add_argument("--api-jar", type=Path, action="append", default=[])
    pipeline.add_argument("--starsector-install", type=Path, help="explicit local Starsector install; hash-record its core compile classpath")
    pipeline.add_argument("--dependency-jar", type=Path, action="append", default=[])
    pipeline.add_argument("--library-registry", type=Path, help="local dependency-id -> jar-path map (never bundled or committed)")
    pipeline.add_argument("--compile", action="store_true")
    pipeline.add_argument("--bytecode-file")
    pipeline.add_argument("--bytecode-rules", type=Path)
    pipeline.add_argument("--bytecode-approve", action="append", default=[])
    packs = subcommands.add_parser("packs", help="list bundled migration packs")
    packs.add_argument("--root", type=Path)
    candidate = subcommands.add_parser("migration-pack-candidate", help="create a non-applying evidence contract for a proposed library mapping")
    candidate.add_argument("--library-id", required=True)
    candidate.add_argument("--mapping-id", required=True)
    candidate.add_argument("--from-symbol", required=True)
    candidate.add_argument("--to-symbol", required=True)
    candidate.add_argument("--output", required=True, type=Path)
    runtime = subcommands.add_parser("runtime-profile", help="record an explicit opt-in runtime launch profile")
    runtime.add_argument("workspace", type=Path)
    runtime.add_argument("--executable", required=True, type=Path)
    runtime.add_argument("--argument", action="append", default=[])
    runtime.add_argument("--working-directory", required=True, type=Path)
    runtime.add_argument("--timeout", type=int, default=60)
    runtime.add_argument("--log-file")
    runtime.add_argument("--expect-log", action="append", default=[])
    runtime.add_argument("--scenario", action="append", choices=["campaign-load", "mission-launch", "custom-ui"], default=[])
    runtime.add_argument("--scenario-expect", action="append", default=[], metavar="SCENARIO=LOG_MARKER", help="require a log marker for one selected scenario; repeatable")
    smoke = subcommands.add_parser("runtime-smoke", help="inspect or explicitly run a runtime profile")
    smoke.add_argument("workspace", type=Path)
    smoke.add_argument("--execute", action="store_true")
    inspect = subcommands.add_parser("inspect", help="show workspace plans, diffs, and checkpoints")
    inspect.add_argument("workspace", type=Path)
    export = subcommands.add_parser("export-patch", help="export a patch-only package")
    export.add_argument("workspace", type=Path)
    export.add_argument("--output", required=True, type=Path)
    opportunities = subcommands.add_parser("opportunities", help="report non-applying library-adoption opportunities")
    opportunities.add_argument("workspace", type=Path)
    doctor_command = subcommands.add_parser("doctor", help="check local tooling, packs, and optional workspace integrity")
    doctor_command.add_argument("--workspace", type=Path)
    doctor_command.add_argument("--json", action="store_true")
    conflict_command = subcommands.add_parser("conflicts", help="detect planned-edit and duplicate-class conflicts")
    conflict_command.add_argument("workspace", type=Path)
    provenance_command = subcommands.add_parser("provenance", help="write deterministic workspace and artifact hashes")
    provenance_command.add_argument("workspace", type=Path)
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
    decompiler = subcommands.add_parser("decompiler-review", help="record or explicitly run a user-supplied decompiler as untrusted review evidence")
    decompiler.add_argument("input", type=Path)
    decompiler.add_argument("--adapter", type=Path, required=True)
    decompiler.add_argument("--adapter-argument", action="append", default=[], help="adapter argument; include {input} and {output} placeholders")
    decompiler.add_argument("--output", required=True, type=Path)
    decompiler.add_argument("--execute", action="store_true")
    lineage = subcommands.add_parser("release-lineage", help="compare an explicitly ordered sequence of mod releases without modifying them")
    lineage.add_argument("release_directories", type=Path, nargs="+")
    lineage.add_argument("--target-starsector", default="0.98.x")
    lineage.add_argument("--target-java", type=int, default=17)
    lineage.add_argument("--output", type=Path)
    archive_preflight = subcommands.add_parser("archive-preflight", help="inspect a ZIP archive without extracting it")
    archive_preflight.add_argument("archive", type=Path)
    archive_preflight.add_argument("--output", type=Path)
    archive_stage = subcommands.add_parser("archive-stage", help="extract a preflight-safe ZIP into a new explicit destination")
    archive_stage.add_argument("archive", type=Path)
    archive_stage.add_argument("--output", required=True, type=Path)
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
    evaluation = subcommands.add_parser("release-evaluate", help="compare two release directories without modifying either")
    evaluation.add_argument("before_directory", type=Path)
    evaluation.add_argument("after_directory", type=Path)
    evaluation.add_argument("--target-starsector", default="0.98.x")
    evaluation.add_argument("--target-java", type=int, default=17)
    evaluation.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "scan":
        try:
            result = scan_mod(args.mod_directory, TargetProfile(args.target_starsector, args.target_java))
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        try:
            report, manifest = write_artifacts(result, args.output)
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        print(f"Scanned {len(result.files)} files; found {len(result.findings)} findings.")
        print(f"Report: {report}")
        print(f"Manifest: {manifest}")
        return 0
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
            result = analyze_mod_set(args.mod_directories, TargetProfile(args.target_starsector, args.target_java), aliases)
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
    if args.command == "decompiler-review":
        try:
            output = args.output.expanduser().resolve()
            if (output / "decompiler-review-plan.json").is_file():
                result = run_decompiler_review(output, args.execute)
            else:
                plan = create_decompiler_review(args.input, output, args.adapter, args.adapter_argument)
                result = {"status": "NOT_EXECUTED", "plan": plan}
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        print(f"Decompiler review status: {result['status']}")
        return 0 if result["status"] in {"PASS", "NOT_EXECUTED"} else 1
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
    if args.command == "archive-preflight":
        try:
            result = inspect_zip_archive(args.archive)
            archive = args.archive.expanduser().resolve()
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        payload = json.dumps(result, indent=2, sort_keys=True)
        if args.output:
            output = args.output.expanduser().resolve()
            if output == archive:
                print("bridgeforge: Archive preflight output must not replace the input archive.", file=sys.stderr)
                return 2
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(payload + "\n", encoding="utf-8")
            print(f"Archive preflight: {output}")
        else:
            print(payload)
        return 0
    if args.command == "archive-stage":
        try:
            destination = stage_zip_archive(args.archive, args.output)
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        print(f"Staged archive to: {destination}")
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
    if args.command == "bytecode-inspect":
        try:
            result = inspect_bytecode(args.input)
        except (ValueError, BytecodeUnavailable) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        payload = json.dumps(result, indent=2, sort_keys=True)
        if args.output:
            output = args.output.expanduser().resolve()
            output.write_text(payload + "\n", encoding="utf-8")
            print(f"Inspected {len(result['classes'])} class(es): {output}")
        else:
            print(payload)
        return 0
    if args.command == "bytecode-plan":
        try:
            result = plan_bytecode(args.input, args.rules)
        except (ValueError, BytecodeUnavailable) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        payload = json.dumps(result, indent=2, sort_keys=True)
        if args.output:
            output = args.output.expanduser().resolve()
            output.write_text(payload + "\n", encoding="utf-8")
            print(f"Planned {len(result['planned'])} review-only bytecode remap(s): {output}")
        else:
            print(payload)
        return 0
    if args.command == "bytecode-diff":
        try:
            result = diff_bytecode(args.before, args.after)
        except (ValueError, BytecodeUnavailable) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        payload = json.dumps(result, indent=2, sort_keys=True)
        if args.output:
            output = args.output.expanduser().resolve()
            output.write_text(payload + "\n", encoding="utf-8")
            print(f"Compared {len(result['changed_classes'])} changed class(es): {output}")
        else:
            print(payload)
        return 0
    if args.command == "bytecode-apply":
        try:
            result = (apply_bytecode_jar if args.input.suffix.lower() == ".jar" else apply_bytecode_class)(args.input, args.output, args.rules, set(args.approve))
        except (ValueError, BytecodeUnavailable) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.command == "workspace":
        try:
            created = create_workspace(args.mod_directory, args.output)
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        print(f"Created workspace: {created}")
        return 0
    if args.command == "plan":
        try:
            selected = [*resolve_pack_rule_paths(args.pack), *args.rules]
            plan = build_plan(args.workspace, TargetProfile(args.target_starsector, args.target_java), selected if (args.pack or args.rules) else None)
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        print(f"Planned {len(plan['migrations'])} migration(s): {Path(args.workspace).resolve() / 'migration-plan.json'}")
        return 0
    if args.command == "apply":
        try:
            manifest = apply_plan(args.workspace, set(args.approve), args.safe)
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        print(f"Applied {len(manifest['applied'])} migration(s).")
        return 0
    if args.command == "rollback":
        try:
            rollback(args.workspace, args.checkpoint)
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        print(f"Restored working copy from checkpoint: {args.checkpoint}")
        return 0
    if args.command == "build-plan":
        try:
            registry = load_library_registry(args.library_registry) if args.library_registry else None
            profile = create_build_profile(args.workspace, TargetProfile(args.target_starsector, args.target_java), args.jdk, args.api_jar, args.dependency_jar, registry, args.starsector_install)
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        print(f"Build profile: {Path(args.workspace).resolve() / 'build-profile.json'}")
        if profile.compile_validation["status"] == "UNAVAILABLE":
            print(f"Compile validation unavailable: {len(profile.compile_validation['findings'])} requested JAR(s) could not be verified.")
            for finding in profile.compile_validation["findings"]:
                print(f"- {finding['explanation']}")
        print(preview_shell_command(profile))
        return 0
    if args.command == "compile":
        try:
            result = run_compile(args.workspace)
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if result.get("status") == "UNAVAILABLE":
            print(f"Compile validation unavailable; findings: {len(result['findings'])}")
            for finding in result["findings"]:
                print(f"- {finding['explanation']}")
            return 0
        print(f"Compile {'passed' if result['success'] else 'failed'}; diagnostics: {len(result['diagnostics'])}")
        return 0 if result["success"] else 1
    if args.command == "package-jar":
        try:
            result = package_compiled_jar(args.workspace, args.input_jar, args.output_name)
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.command == "compile-feedback":
        try:
            feedback = compile_feedback(args.workspace)
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        print(f"Generated compile feedback with {len(feedback['findings'])} finding(s).")
        return 0
    if args.command == "review-bundle":
        try:
            bundle = create_review_bundle(args.workspace)
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        print(f"Created review bundle: {bundle}")
        return 0
    if args.command == "validate":
        try:
            result = validate_workspace(args.workspace, TargetProfile(args.target_starsector, args.target_java))
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        print(f"Validation: reference {result['reference_integrity']['status']}; structural {result['structural_validation']['status']}; runtime {result['runtime_validation']['status']}")
        return 0
    if args.command == "save-risk":
        try:
            result = analyze_save_risk(args.workspace)
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        print(f"Save compatibility risk: {result['risk']} ({len(result['findings'])} finding(s))")
        return 0
    if args.command == "pipeline":
        try:
            selected = [*resolve_pack_rule_paths(args.pack), *args.rules]
            registry = load_library_registry(args.library_registry) if args.library_registry else None
            result = run_pipeline(args.workspace, TargetProfile(args.target_starsector, args.target_java), selected if (args.pack or args.rules) else None, set(args.approve), args.safe, args.jdk, args.api_jar, args.dependency_jar, args.compile, args.bytecode_file, args.bytecode_rules, set(args.bytecode_approve), registry, args.starsector_install)
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        print(f"Pipeline complete: {Path(args.workspace).resolve() / 'MODERNIZATION_REPORT.md'} ({result['apply']['applied_count']} applied migration(s))")
        return 0
    if args.command == "packs":
        try:
            for pack in discover_packs(args.root):
                print(f"{pack.id}\t{pack.status}\t{pack.scope}")
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        return 0
    if args.command == "migration-pack-candidate":
        try:
            output = create_migration_pack_candidate(args.library_id, args.mapping_id, args.from_symbol, args.to_symbol, args.output)
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        print(f"Migration-pack research candidate: {output}")
        return 0
    if args.command == "runtime-profile":
        try:
            scenario_markers = {}
            for item in args.scenario_expect:
                scenario, separator, marker = item.partition("=")
                if not separator or not scenario or not marker:
                    raise ValueError("Each --scenario-expect must be SCENARIO=LOG_MARKER.")
                scenario_markers.setdefault(scenario, []).append(marker)
            create_runtime_profile(args.workspace, args.executable, args.argument, args.working_directory, args.timeout, args.log_file, args.expect_log, args.scenario, scenario_markers)
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        print("Recorded runtime profile; it will not execute without `runtime-smoke --execute`.")
        return 0
    if args.command == "runtime-smoke":
        try:
            result = run_runtime_smoke(args.workspace, args.execute)
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        print(f"Runtime smoke status: {result['status']}")
        return 0 if result["status"] in {"PASS", "NOT_EXECUTED"} else 1
    if args.command == "inspect":
        try:
            result = inspect_workspace(args.workspace)
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(result, indent=2))
        return 0
    if args.command == "export-patch":
        try:
            output = export_patch(args.workspace, args.output)
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        print(f"Patch package: {output}")
        return 0
    if args.command == "opportunities":
        try:
            result = analyze_opportunities(args.workspace)
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        print(f"Modernization opportunities: {len(result['findings'])}")
        return 0
    if args.command == "doctor":
        result = doctor(args.workspace)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            for check in result["checks"]:
                print(f"{check['status']}\t{check['id']}")
        return 0 if result["status"] == "PASS" else 1
    if args.command == "conflicts":
        try:
            result = detect_conflicts(args.workspace)
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(result, indent=2))
        return 0 if result["status"] == "PASS" else 1
    if args.command == "provenance":
        try:
            result = write_provenance(args.workspace)
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(result, indent=2))
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
    return 2
