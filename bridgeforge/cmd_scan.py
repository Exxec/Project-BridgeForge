"""Scan and static-check commands: scan, compile-check, preset-check, layout and docs checks (ROADMAP 70 H2.1)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .baseline import finding_baseline_key, load_baseline_keys, split_by_baseline
from .build_inputs import build_input_manifest, write_build_input_manifest
from .copy_drift import compare_copies
from .integration_scenarios import suggest_integration_scenarios
from .models import TargetProfile
from .report import write_artifacts
from .safeio import atomic_write_text
from .scanner import scan_mod
from .working_tree import analyze_working_tree, write_source_authority_selection


def add_parser(subcommands) -> None:
    scan = subcommands.add_parser("scan", help="scan a mod directory without modifying it")
    scan.add_argument("mod_directory", type=Path)
    scan.add_argument("--output", type=Path, default=Path("bridgeforge-artifacts"), help="output FOLDER (created if missing) for MODERNIZATION_REPORT.md and bridgeforge.compat.json; not a file name")
    scan.add_argument("--target-starsector", default="0.98.x")
    scan.add_argument("--target-java", type=int, default=17)
    scan.add_argument("--vanilla-core", type=Path, help="path to a read-only starsector-core directory, used for vanilla-row/faction/path exemptions")
    scan.add_argument("--baseline", type=Path, help="only report findings not present in this baseline file, plus a count of previously accepted findings that are now resolved")
    scan.add_argument("--write-baseline", type=Path, help="write the current scan's finding keys to this file as an accepted baseline")
    scan.add_argument("--compile-check", action="store_true", help="also javac-compile loose scripts against RC8 (needs --vanilla-core); opt-in, off by default so scans stay fast and hermetic")
    scan.add_argument("--providers", type=Path, action="append", default=[], help="with --compile-check: mods folder, mod folder or In operation tree to search for declared dependencies; repeatable (default: <repo>/In operation and its rig's mods, same as the standalone compile-check command)")
    scan.add_argument("--removed-content", type=Path, help="catalogue from `content-diff`: report unresolved ids that the older vanilla defined (content-reference-removed-in-vanilla), with same-named RC8 candidates")
    compile_check_cmd = subcommands.add_parser("compile-check", help="compile a mod's loose scripts against RC8 with javac and report every error (javac, not the game's runtime Janino compiler)")
    compile_check_cmd.add_argument("mod", type=Path, help="mod working copy")
    compile_check_cmd.add_argument("--vanilla-core", type=Path, help="read-only starsector-core, put on the compile classpath")
    compile_check_cmd.add_argument("--jdk", type=Path, help="JDK home (default: this repo's rig JDK, else JAVA_HOME, else PATH)")
    compile_check_cmd.add_argument("--providers", type=Path, action="append", default=[], help="mods folder, mod folder or In operation tree to search for declared dependencies; repeatable (default: <repo>/In operation and its rig's mods)")
    compile_check_cmd.add_argument("--api-diff", type=Path, help="catalogue written by `api-diff`: attach removed/moved-API leads to matching javac errors")
    compile_check_cmd.add_argument("--json", action="store_true")
    preset_cmd = subcommands.add_parser("preset-check", help="check bf-test.ps1 presets against the rig's installed mods: own mod and declared dependencies enabled, enabled ids installed, no undeclared libraries")
    preset_cmd.add_argument("script", type=Path, help="path to bf-test.ps1")
    preset_cmd.add_argument("--rig-mods", type=Path, help="rig mods folder (default: <script folder>/_rig/mods)")
    preset_cmd.add_argument("--json", action="store_true")
    ci_cmd = subcommands.add_parser("check-impact", help="rescan the mods whose escalation packets hold FINDING_ID and report which are now cleared, reduced or unchanged (--all: also find newly flagged mods)")
    ci_cmd.add_argument("finding")
    ci_cmd.add_argument("queue", type=Path)
    ci_cmd.add_argument("--vanilla-core", type=Path)
    ci_cmd.add_argument("--all", action="store_true", help="scan every workspace, not just those with packets for the finding")
    ci_cmd.add_argument("--quiet", action="store_true", help="no per-workspace progress lines on stderr")
    ci_cmd.add_argument("--json", action="store_true")
    revenantlib_cmd = subcommands.add_parser("revenantlib-check", help="check a RevenantLib jar provides every bf.* method BridgeForge's fixers rewrite calls to, and (given the mod folder) that no source file lacks a compiled class")
    revenantlib_cmd.add_argument("path", type=Path, help="RevenantLib.jar, the RevenantLib mod folder, or a repo root holding working/")
    revenantlib_cmd.add_argument("--snapshot", type=Path, help="an archived copy (e.g. Done/RevenantLib/RevenantLib): report whether it still matches the checked mod folder")
    revenantlib_cmd.add_argument("--json", action="store_true")
    layout = subcommands.add_parser("working-tree-layout", help="classify generated, backup, and source/content candidates without changing a mod")
    layout.add_argument("mod_directory", type=Path)
    layout.add_argument("--output", type=Path)
    authority = subcommands.add_parser("source-authority", help="record an explicit selected source root for a working tree")
    authority.add_argument("mod_directory", type=Path)
    authority.add_argument("--select-root", required=True)
    authority.add_argument("--output", required=True, type=Path)
    build_inputs = subcommands.add_parser("build-input-manifest", help="record source authority and annotation-processing build evidence")
    build_inputs.add_argument("mod_directory", type=Path)
    build_inputs.add_argument("--source-root")
    build_inputs.add_argument("--output", required=True, type=Path)
    scenarios = subcommands.add_parser("integration-scenarios", help="suggest review-only runtime scenarios from optional integration evidence")
    scenarios.add_argument("mod_directory", type=Path)
    scenarios.add_argument("--target-starsector", default="0.98.x")
    scenarios.add_argument("--target-java", type=int, default=17)
    scenarios.add_argument("--output", type=Path)
    mc_cmd = subcommands.add_parser("mods-compat", help="read-only: hooks only one mod can own (industry plugins, new-game generators, replaced core files, shadowed vanilla scripts) claimed by two or more mods in a real mods folder")
    mc_cmd.add_argument("mods_dir", type=Path)
    mc_cmd.add_argument("--vanilla-core", type=Path, required=True)
    mc_cmd.add_argument("--output", type=Path, default=Path("In operation"), help="where MODS_COMPAT.json/.md go")
    mc_cmd.add_argument("--quiet", action="store_true", help="no per-mod progress lines on stderr")
    mc_cmd.add_argument("--json", action="store_true")
    bs_cmd = subcommands.add_parser("baseline-stats", help="read-only: rank checks by how often their findings were accepted as harmless in workspace baselines (where a check needs refining)")
    bs_cmd.add_argument("queue", type=Path, nargs="?", default=Path("In operation"))
    bs_cmd.add_argument("--top", type=int, default=25)
    bs_cmd.add_argument("--json", action="store_true")
    docs_cmd = subcommands.add_parser("docs-index", help="regenerate docs/CHECKS.md (every finding id: where it's emitted, tests, bug classes; scanner helpers) and docs/COMMANDS.md (every command and argument) from the source")
    docs_cmd.add_argument("--check", action="store_true", help="don't write; exit 1 if either file is stale")
    docs_cmd.add_argument("--stage", action="store_true", help="git add the generated docs that git tracks (only those: a glob over docs/ hits gitignored files and fails, ROADMAP 52)")
    docs_cmd.add_argument("--json", action="store_true")


def run_cli(args: argparse.Namespace) -> int:
    if args.command == "mods-compat":
        from .mods_compat import mods_compat
        result = mods_compat(args.mods_dir, args.vanilla_core, args.output, quiet=args.quiet)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"{result['mods']} mod(s); {len(result['conflicts'])} hook(s) claimed by two or more. See {args.output / 'MODS_COMPAT.md'}")
        return 0
    if args.command == "baseline-stats":
        from .baseline_stats import baseline_stats, render
        result = baseline_stats(args.queue)
        print(json.dumps(result, indent=2) if args.json else render(result, args.top))
        return 0
    if args.command == "docs-index":
        from .checks_index import write_reference_docs
        result = write_reference_docs(check_only=args.check)
        if args.json:
            print(json.dumps(result, indent=2))
        elif result["status"] == "STALE":
            print("Stale (run bridgeforge docs-index): " + ", ".join(result["stale"]))
        else:
            print("Written: " + ", ".join(result["written"]) if result["written"] else "docs/CHECKS.md and docs/COMMANDS.md are up to date")
        if args.stage and result["status"] != "STALE":
            import subprocess

            tracked = subprocess.run(["git", "ls-files", "docs/CHECKS.md", "docs/COMMANDS.md"], capture_output=True, text=True).stdout.split()
            if tracked:
                subprocess.run(["git", "add", "--", *tracked], check=False)
                print("Staged: " + ", ".join(tracked))
        return 1 if result["status"] == "STALE" else 0
    if args.command == "preset-check":
        from .preset_check import check_presets
        result = check_presets(args.script, args.rig_mods)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Preset check: {result['status']} ({len(result['presets'])} presets, rig mods {result['rig_mods']})")
            for preset in result["presets"]:
                if preset["status"] != "PASS":
                    print(f"  {preset['preset']} [{preset['status']}]")
                    for line in preset["errors"]:
                        print(f"    ERROR   {line}")
                    for line in preset["warnings"]:
                        print(f"    WARNING {line}")
        return 1 if result["status"] == "FAIL" else 0
    if args.command == "scan":
        try:
            result = scan_mod(args.mod_directory, TargetProfile(args.target_starsector, args.target_java), args.vanilla_core, compile_check=args.compile_check, provider_roots=args.providers or None)
            if args.removed_content:
                from .content_diff import annotate_removed_content
                annotate_removed_content(result, json.loads(args.removed_content.read_text(encoding="utf-8")))
        except (ValueError, OSError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        try:
            report, manifest = write_artifacts(result, args.output, registry={"vanilla_core": args.vanilla_core, "compile_check": args.compile_check,
                                                                                "provider_roots": args.providers or None, "removed_content": args.removed_content})
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.write_baseline:
            keys = sorted({finding_baseline_key(finding) for finding in result.findings})
            args.write_baseline.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(args.write_baseline, json.dumps({"findings": keys}, indent=2, sort_keys=True) + "\n")
            from .baseline_audit import stamp_baseline

            stamp_baseline(args.write_baseline, args.mod_directory)  # accepted at this version, today (ROADMAP 70 H1.5)
            print(f"Scanned {len(result.files)} files; found {len(result.findings)} findings.")
            print(f"Report: {report}")
            print(f"Manifest: {manifest}")
            print(f"Baseline written: {args.write_baseline} ({len(keys)} accepted finding(s))")
            return 0
        if args.baseline:
            try:
                baseline_keys = load_baseline_keys(args.baseline)
            except (OSError, json.JSONDecodeError) as exc:
                print(f"bridgeforge: could not read baseline file: {exc}", file=sys.stderr)
                return 2
            new_findings, resolved_count = split_by_baseline(result.findings, baseline_keys)
            print(f"Scanned {len(result.files)} files; found {len(new_findings)} new finding(s) not in baseline ({resolved_count} previously accepted finding(s) resolved).")
            print(f"Report: {report}")
            print(f"Manifest: {manifest}")
            return 0
        print(f"Scanned {len(result.files)} files; found {len(result.findings)} findings.")
        print(f"Report: {report}")
        print(f"Manifest: {manifest}")
        return 0
    if args.command == "working-tree-layout":
        try:
            result = analyze_working_tree(args.mod_directory)
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        payload = json.dumps(result, indent=2, sort_keys=True)
        if args.output:
            output = args.output.expanduser().resolve()
            if output.is_relative_to(args.mod_directory.expanduser().resolve()):
                print("bridgeforge: Working-tree layout output must not be inside the input mod directory.", file=sys.stderr)
                return 2
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(payload + "\n", encoding="utf-8")
            print(f"Working-tree layout: {output}")
        else:
            print(payload)
        return 0
    if args.command == "source-authority":
        try:
            output = write_source_authority_selection(args.mod_directory, args.select_root, args.output)
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        print(f"Source authority selection: {output}")
        return 0
    if args.command == "build-input-manifest":
        try:
            manifest = build_input_manifest(args.mod_directory, args.source_root)
            output = write_build_input_manifest(manifest, args.output, args.mod_directory)
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        print(f"Build-input manifest: {output}")
        return 0
    if args.command == "integration-scenarios":
        try:
            result = suggest_integration_scenarios(args.mod_directory, TargetProfile(args.target_starsector, args.target_java))
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        payload = json.dumps(result, indent=2, sort_keys=True)
        if args.output:
            output = args.output.expanduser().resolve()
            if output.is_relative_to(args.mod_directory.expanduser().resolve()):
                print("bridgeforge: Integration scenario output must not be inside the input mod directory.", file=sys.stderr)
                return 2
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(payload + "\n", encoding="utf-8")
            print(f"Integration scenarios: {output}")
        else:
            print(payload)
        return 0
    if args.command == "compile-check":
        from .compile_check import compile_loose_scripts
        try:
            result = compile_loose_scripts(args.mod, vanilla_core=args.vanilla_core, jdk=args.jdk, provider_roots=args.providers)
            if args.api_diff:
                from .api_diff import annotate_errors
                result["api_diff_annotated"] = annotate_errors(result.get("errors", []), json.loads(args.api_diff.read_text(encoding="utf-8")))
        except (ValueError, OSError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"{result['status']}: {args.mod} ({result.get('error_count', 0)} error(s) in {len(result.get('files', []))} loose script(s))")
            if result["status"] == "UNAVAILABLE":
                print(f"  {result['reason']}")
            for kind, count in result.get("error_counts_by_kind", {}).items():
                print(f"  {kind}: {count}")
            missing = (result.get("classpath") or {}).get("dependencies_missing") or []
            if missing:
                print(f"  dependency jars not found: {', '.join(missing)}")
            shadowed = result.get("jar_shadowed_errors") or []
            if shadowed:
                mod_root = Path(args.mod).expanduser().resolve()
                shadowed_files = sorted({str(Path(error["file"]).relative_to(mod_root)).replace("\\", "/") for error in shadowed})
                print(f"  {len(shadowed)} error(s) in {len(shadowed_files)} jar-shadowed loose script(s) not counted above (the game loads the jar's class instead): {', '.join(shadowed_files[:5])}")
            janino = result.get("janino") or {}
            if janino.get("status") in ("PASS", "FAIL"):
                print(f"  Janino (RC8's runtime compiler): {janino['status']} ({janino.get('checked', 0)} script(s) compiled)")
                for rel, message in sorted((janino.get("failures") or {}).items()):
                    print(f"  JANINO FAIL {rel}: {message[:300]}")
            elif janino.get("reason"):
                print(f"  Janino not run: {janino['reason']}")
            for warning in result.get("janino_gap_warnings", [])[:10]:
                print(f"  WARNING javac-vs-Janino gap in {warning['file']}: {', '.join(warning['java8plus_syntax'])}")
            for error in [e for e in result.get("errors", []) if e.get("api_changes")][:20]:
                for hint in error["api_changes"]:
                    leads = hint.get("same_signature_elsewhere") or hint.get("same_name_in_class") or hint.get("same_name_elsewhere") or []
                    print(f"  API CHANGE {Path(str(error['file'])).name}:{error['line']}: {hint.get('removed') or hint.get('removed_class')} removed"
                          + (f"; candidates: {', '.join(leads)}" if leads else "; no same-named candidate"))
        return 0 if result["status"] == "PASS" else 1
    if args.command == "revenantlib-check":
        from .revenantlib_contract import RevenantLibCheckError, check_revenantlib
        import zipfile
        try:
            result = check_revenantlib(args.path)
            if args.snapshot is not None:
                # The checked jar lives at <mod>/jars/RevenantLib.jar; compare that mod folder with the archive.
                drift = compare_copies(Path(result["jar"]).parent.parent, args.snapshot)
                result["snapshot"] = {"path": str(args.snapshot), "status": "CURRENT" if drift["status"] == "PASS" else "STALE",
                                      "drift_count": drift["drift_count"], "different": [d["path"] for d in drift["different"]],
                                      "missing_in_snapshot": drift["missing_in_deployed"], "extra_in_snapshot": drift["extra_in_deployed"]}
        except (RevenantLibCheckError, OSError, zipfile.BadZipFile, ValueError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"{result['status']}: {result['jar']}")
            for entry in result["contract"]:
                print(f"  {entry['status']} {entry['call']}" + (f" -- {entry['detail']}" if entry.get("detail") else ""))
            stale = result["jar_vs_source"]
            if not stale["checked"]:
                print("  jar vs source: not checked (no src/ beside the jar)")
            for name in stale["sources_without_class"]:
                print(f"  FAIL source without a compiled class in the jar: {name}.java")
            for name in stale["classes_without_source"]:
                print(f"  FAIL class in the jar without source: {name}")
            snapshot = result.get("snapshot")
            if snapshot:
                print(f"  snapshot {snapshot['status']}: {snapshot['path']}" + (f" ({snapshot['drift_count']} file(s) differ: {', '.join((snapshot['different'] + snapshot['missing_in_snapshot'] + snapshot['extra_in_snapshot'])[:5])}) - refresh the archive" if snapshot["status"] == "STALE" else ""))
        return 0 if result["status"] == "PASS" else 1
    if args.command == "check-impact":
        from .check_impact import check_impact
        result = check_impact(args.queue, args.finding, vanilla_core=args.vanilla_core, all_workspaces=args.all, quiet=args.quiet)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            for row in result["mods"]:
                if row["verdict"] in ("CLEARED", "REDUCED", "NEW"):
                    print(f"{row['verdict']:9} {row['workspace']} ({row['before']} -> {row['now']})")
            print("Counts: " + ", ".join(f"{k} {v}" for k, v in sorted(result["counts"].items())) + f". Written: {result['result_path']}")
        return 0
    return 2
