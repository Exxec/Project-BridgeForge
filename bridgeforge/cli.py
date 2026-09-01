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
from .library_api import inventory_library_api, match_library_imports
from .evaluation import evaluate_releases
from .bytecode import BytecodeUnavailable, inspect_bytecode
from .bytecode_diff import diff_bytecode
from .bytecode_rules import apply_bytecode_class, apply_bytecode_jar, plan_bytecode


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
    pipeline.add_argument("--dependency-jar", type=Path, action="append", default=[])
    pipeline.add_argument("--library-registry", type=Path, help="local dependency-id -> jar-path map (never bundled or committed)")
    pipeline.add_argument("--compile", action="store_true")
    pipeline.add_argument("--bytecode-file")
    pipeline.add_argument("--bytecode-rules", type=Path)
    pipeline.add_argument("--bytecode-approve", action="append", default=[])
    packs = subcommands.add_parser("packs", help="list bundled migration packs")
    packs.add_argument("--root", type=Path)
    runtime = subcommands.add_parser("runtime-profile", help="record an explicit opt-in runtime launch profile")
    runtime.add_argument("workspace", type=Path)
    runtime.add_argument("--executable", required=True, type=Path)
    runtime.add_argument("--argument", action="append", default=[])
    runtime.add_argument("--working-directory", required=True, type=Path)
    runtime.add_argument("--timeout", type=int, default=60)
    runtime.add_argument("--log-file")
    runtime.add_argument("--expect-log", action="append", default=[])
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
    api_inventory = subcommands.add_parser("library-api-inventory", help="inventory class symbols in a supplied local library JAR")
    api_inventory.add_argument("jar", type=Path)
    api_inventory.add_argument("--output", type=Path)
    api_match = subcommands.add_parser("library-api-match", help="compare a mod's imports with a supplied local library API inventory")
    api_match.add_argument("mod_directory", type=Path)
    api_match.add_argument("inventory", type=Path)
    api_match.add_argument("--target-starsector", default="0.98.x")
    api_match.add_argument("--target-java", type=int, default=17)
    api_match.add_argument("--output", type=Path)
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
            report = audit_directories(args.mod_directories, TargetProfile(args.target_starsector, args.target_java))
            output = write_corpus_audit(report, args.output, args.mod_directories)
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        print(f"Audited {report['mod_count']} mod(s): {output}")
        return 0
    if args.command == "library-api-inventory":
        try:
            result = inventory_library_api(args.jar)
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        payload = json.dumps(result, indent=2, sort_keys=True)
        if args.output:
            args.output.expanduser().resolve().write_text(payload + "\n", encoding="utf-8")
            print(f"Inventoried {result['class_count']} class symbol(s): {args.output.expanduser().resolve()}")
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
            profile = create_build_profile(args.workspace, TargetProfile(args.target_starsector, args.target_java), args.jdk, args.api_jar, args.dependency_jar, registry)
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
            result = run_pipeline(args.workspace, TargetProfile(args.target_starsector, args.target_java), selected if (args.pack or args.rules) else None, set(args.approve), args.safe, args.jdk, args.api_jar, args.dependency_jar, args.compile, args.bytecode_file, args.bytecode_rules, set(args.bytecode_approve), registry)
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
    if args.command == "runtime-profile":
        try:
            create_runtime_profile(args.workspace, args.executable, args.argument, args.working_directory, args.timeout, args.log_file, args.expect_log)
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
