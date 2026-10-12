"""Workspace migration commands: workspace, plan, apply, rollback, build, validate, pipeline, runtime (ROADMAP 70 H2.1)."""
from __future__ import annotations

import argparse
import json
import sys

from pathlib import Path

from .build import compile_feedback, create_build_profile, package_compiled_jar, preview_shell_command, run_compile
from .conflicts import detect_conflicts
from .doctor import doctor
from .interface import export_patch, inspect_workspace
from .library_registry import load_library_registry
from .migrate import apply_plan, build_plan
from .models import TargetProfile
from .opportunities import analyze_opportunities
from .pack_candidate import create_migration_pack_candidate
from .packs import discover_packs, resolve_pack_rule_paths
from .pipeline import run_pipeline
from .provenance import write_provenance
from .review import create_review_bundle
from .runtime import create_runtime_profile, run_runtime_smoke
from .save_risk import analyze_save_risk
from .validate import validate_workspace
from .workspace import create_workspace, rollback


def add_parser(subcommands) -> None:
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


def run_cli(args: argparse.Namespace) -> int:
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
    return 2
