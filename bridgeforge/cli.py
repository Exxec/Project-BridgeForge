from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .models import TargetProfile
from .report import write_artifacts
from .scanner import scan_mod
from .migrate import apply_plan, build_plan
from .workspace import create_workspace, rollback
from .build import create_build_profile, preview_shell_command
from .build import compile_feedback, run_compile
from .review import create_review_bundle
from .validate import validate_workspace
from .save_risk import analyze_save_risk
from .pipeline import run_pipeline
from .packs import discover_packs, resolve_pack_rule_paths
from .runtime import create_runtime_profile, run_runtime_smoke
from .interface import export_patch, inspect_workspace
from .opportunities import analyze_opportunities


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bridgeforge", description="Safe, explainable legacy Starsector mod analysis and migration.")
    subcommands = parser.add_subparsers(dest="command", required=True)
    scan = subcommands.add_parser("scan", help="scan a mod directory without modifying it")
    scan.add_argument("mod_directory", type=Path)
    scan.add_argument("--output", type=Path, default=Path("bridgeforge-artifacts"))
    scan.add_argument("--target-starsector", default="0.98.x")
    scan.add_argument("--target-java", type=int, default=17)
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
    compile_command = subcommands.add_parser("compile", help="run the explicit workspace build profile")
    compile_command.add_argument("workspace", type=Path)
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
    pipeline.add_argument("--compile", action="store_true")
    packs = subcommands.add_parser("packs", help="list bundled migration packs")
    packs.add_argument("--root", type=Path)
    runtime = subcommands.add_parser("runtime-profile", help="record an explicit opt-in runtime launch profile")
    runtime.add_argument("workspace", type=Path)
    runtime.add_argument("--executable", required=True, type=Path)
    runtime.add_argument("--argument", action="append", default=[])
    runtime.add_argument("--working-directory", required=True, type=Path)
    runtime.add_argument("--timeout", type=int, default=60)
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
            plan = build_plan(args.workspace, TargetProfile(args.target_starsector, args.target_java), selected or None)
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
            profile = create_build_profile(args.workspace, TargetProfile(args.target_starsector, args.target_java), args.jdk, args.api_jar, args.dependency_jar)
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        print(f"Build profile: {Path(args.workspace).resolve() / 'build-profile.json'}")
        print(preview_shell_command(profile))
        return 0
    if args.command == "compile":
        try:
            result = run_compile(args.workspace)
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        print(f"Compile {'passed' if result['success'] else 'failed'}; diagnostics: {len(result['diagnostics'])}")
        return 0 if result["success"] else 1
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
            result = run_pipeline(args.workspace, TargetProfile(args.target_starsector, args.target_java), selected or None, set(args.approve), args.safe, args.jdk, args.api_jar, args.dependency_jar, args.compile)
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
            create_runtime_profile(args.workspace, args.executable, args.argument, args.working_directory, args.timeout)
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
    return 2
