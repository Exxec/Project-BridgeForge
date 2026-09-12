from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .models import TargetProfile
from .report import write_artifacts
from .scanner import scan_mod
from .baseline import finding_baseline_key, load_baseline_keys, split_by_baseline
from .dossier import DEFAULT_CONTEXT_LINES, DEFAULT_MAX_KB, DossierError, write_dossier
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
from .revival_audit import audit_revival
from .working_tree import analyze_working_tree, write_source_authority_selection
from .build_inputs import build_input_manifest, write_build_input_manifest
from .integration_scenarios import suggest_integration_scenarios
from .bytecode import BytecodeUnavailable, inspect_bytecode
from .bytecode_diff import diff_bytecode
from .bytecode_rules import apply_bytecode_class, apply_bytecode_jar, plan_bytecode
from .pack_candidate import create_migration_pack_candidate
from .log_triage import triage_log
from .copy_drift import compare_copies
from .jar_audit import audit_jar
from .build_tag import apply_build_tag, BuildTagError, DEFAULT_LABEL
from .fixers import SUPPORTED_FINDINGS, FixerError, apply_fix, compute_fix, unified_diff_for_change
from .prepare_test import PrepareTestError, prepare_test
from .probe_config import ProbeConfigError, write_probe_config
from .probe_mod_build import ProbeModBuildError, build_probe_mod, install_release
from .save_compat import SaveCompatError, check_save_compat, compare_builds
from .compat_sets import CompatSetError, install_compat_set
from .save_snapshot import SaveSnapshotError, snapshot_list, snapshot_restore, snapshot_tag
from .scenarios import ScenarioError, list_scenarios, scenario_check, scenario_plan
from .save_reader import SaveReadError
from .save_inspect import audit_scripts, diff_saves, growth_trend, inspect_save, save_provenance
from .save_content_compat import check_save_content, removal_safety
from .save_summary import redacted_summary
from .test_plan import TestPlanError, plan_tests
from .spw_bridge import SpwBridgeError, ingest_spw_report, log_spam, perf_gate
from .release import ReleaseError, release_mod
from .rig_doctor import default_working_copies, rig_doctor
from .locks import who_locks
from .intake import intake_archive
from .project_board import project_board, render_board, write_board
from .promote import promote_mod
from .reference_rigs import ReferenceRigError, write_reference_rig_manifest
from .bootstrap import bootstrap_mods
from .build_tag import record_current_manifest
from .probe_config import load_profile
from .behavior_discovery import (
    DiscoveryError,
    add_expected_change,
    behavior_diff,
    check_expected_changes,
    evaluate_behavior_release,
    write_archaeology,
    write_behavior_model,
    write_coverage,
    write_probe_baseline,
    write_save_baseline,
    write_synthesized_tests,
    update_expected_change_status,
)

# Save-tool statuses that mean "look at this" (non-zero exit).
_SAVE_ATTENTION_STATUSES = {"WILL_FAIL", "DUPLICATES_FOUND", "GROWTH_WARNING", "STALE_BUILD", "UNSAFE"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bridgeforge", description="Safe, explainable legacy Starsector mod analysis and migration.")
    subcommands = parser.add_subparsers(dest="command", required=True)
    scan = subcommands.add_parser("scan", help="scan a mod directory without modifying it")
    scan.add_argument("mod_directory", type=Path)
    scan.add_argument("--output", type=Path, default=Path("bridgeforge-artifacts"))
    scan.add_argument("--target-starsector", default="0.98.x")
    scan.add_argument("--target-java", type=int, default=17)
    scan.add_argument("--vanilla-core", type=Path, help="path to a read-only starsector-core directory, used for vanilla-row/faction/path exemptions")
    scan.add_argument("--baseline", type=Path, help="only report findings not present in this baseline file, plus a count of previously accepted findings that are now resolved")
    scan.add_argument("--write-baseline", type=Path, help="write the current scan's finding keys to this file as an accepted baseline")
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
    archive_stage.add_argument("--select-root", help="one preflight candidate mod root when the archive contains multiple")
    archive_stage.add_argument("--manifest-output", type=Path, help="optional manifest path outside the staged directory")
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
    revival_audit = subcommands.add_parser("revival-audit", help="audit final revival evidence and optionally attest its release ZIP")
    revival_audit.add_argument("candidate", type=Path)
    revival_audit.add_argument("--archive", type=Path)
    revival_audit.add_argument("--output", type=Path)
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
    log_triage = subcommands.add_parser("log-triage", help="classify a Starsector log into FATAL / MOD-ERROR / KNOWN-NOISE / OTHER without modifying it")
    log_triage.add_argument("log", type=Path)
    log_triage.add_argument("--mod-prefix", action="append", default=[], metavar="PREFIX", help="additional mod source/package prefix to attribute errors to; repeatable")
    log_triage.add_argument("--mods-dir", type=Path, help="mods folder the log ran with: names the mod whose jar owns each crash frame (suspect/involved)")
    log_triage.add_argument("--all-mods", action="store_true", help="with --mods-dir: index every mod folder, not just enabled_mods.json (e.g. a log from a different mod list)")
    log_triage.add_argument("--json", action="store_true")
    copy_drift = subcommands.add_parser("copy-drift", help="hash-compare a mod working copy against its deployed/test-rig copy")
    copy_drift.add_argument("working_copy", type=Path)
    copy_drift.add_argument("deployed_copy", type=Path)
    copy_drift.add_argument("--json", action="store_true")
    jar_audit = subcommands.add_parser("jar-audit", help="compare a rebuilt mod jar with its original for bundled libraries, removed classes, and reflection use")
    jar_audit.add_argument("rebuilt", type=Path)
    jar_audit.add_argument("--original", required=True, type=Path, help="original .jar file, or a .zip archive containing one")
    jar_audit.add_argument("--json", action="store_true")
    build_tag = subcommands.add_parser("build-tag", help="iterate a visible build tag in a revived mod's mod_info.json name/version, surgically (never re-serializes the file)")
    build_tag.add_argument("mod_dir", type=Path)
    build_tag.add_argument("--label", default=DEFAULT_LABEL, help=f"suffix label used in the name tag, e.g. '[LABEL rN]' (default: {DEFAULT_LABEL})")
    build_tag.add_argument("--set", dest="set_value", type=int, help="force the build number instead of incrementing")
    build_tag.add_argument("--dry-run", action="store_true", help="print the proposed change without writing mod_info.json")
    build_tag.add_argument("--no-manifest", action="store_true", help="don't record the per-tag file hash manifest that test-plan diffs against")
    build_tag.add_argument("--record-only", action="store_true", help="record the manifest for the CURRENT build (r0 if untagged) without bumping or writing mod_info.json")
    build_tag.add_argument("--manifests-dir", type=Path, help="where build manifests go (default: <repo>/bridgeforge-state/build-manifests; never inside the mod)")
    build_tag.add_argument("--json", action="store_true")
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
    prepare_test_cmd = subcommands.add_parser("prepare-test", help="sync a rig test copy from a working copy, and optionally run a boot test")
    prepare_test_cmd.add_argument("working_dir", type=Path)
    prepare_test_cmd.add_argument("rig_mod_dir", type=Path)
    prepare_test_cmd.add_argument("--sync", action="store_true", help="copy drifted/missing working -> rig files (never the reverse, never deletes rig extras)")
    prepare_test_cmd.add_argument("--bump", action="store_true", help="apply_build_tag the working copy before comparing")
    prepare_test_cmd.add_argument("--label", default=DEFAULT_LABEL)
    prepare_test_cmd.add_argument("--no-manifest", action="store_true", help="with --bump: don't record the per-tag build manifest for test-plan")
    prepare_test_cmd.add_argument("--boot", type=Path, metavar="RUNTIME_DIR", help="run a boot test against this runtime after a successful sync")
    prepare_test_cmd.add_argument("--mods", nargs="+", default=[], metavar="ID", help="mod ids to enable for --boot")
    prepare_test_cmd.add_argument("--timeout", type=int, default=240)
    prepare_test_cmd.add_argument("--log-name")
    prepare_test_cmd.add_argument("--keep-mods", action="store_true")
    prepare_test_cmd.add_argument("--json", action="store_true")
    boot_test_cmd = subcommands.add_parser("boot-test", help="run a boot smoke test of a Starsector runtime with explicit mods enabled")
    boot_test_cmd.add_argument("runtime_dir", type=Path)
    boot_test_cmd.add_argument("--mods", nargs="+", required=True, metavar="ID")
    boot_test_cmd.add_argument("--pack", metavar="SET", help="also run a compat-set matrix (roadmap P4): --mods alone with the libs it needs, then --mods plus this whole named set (e.g. 'standard')")
    boot_test_cmd.add_argument("--timeout", type=int, default=240)
    boot_test_cmd.add_argument("--log-name")
    boot_test_cmd.add_argument("--keep-mods", action="store_true")
    boot_test_cmd.add_argument("--json", action="store_true")
    compat_set_cmd = subcommands.add_parser("compat-set", help="install a named standard compatibility pack (roadmap P4) into a test rig")
    compat_set_subcommands = compat_set_cmd.add_subparsers(dest="compat_set_command", required=True)
    compat_set_install_cmd = compat_set_subcommands.add_parser("install", help="copy a named compat set's mods from a source mods directory into a rig's mods/")
    compat_set_install_cmd.add_argument("set_name", metavar="SET")
    compat_set_install_cmd.add_argument("--runtime", required=True, type=Path, help="isolated test-rig runtime directory (starsector-core must be a junction/symlink)")
    compat_set_install_cmd.add_argument("--source-mods", required=True, type=Path, help="read-only directory to copy mods FROM (never written to)")
    compat_set_install_cmd.add_argument("--reference-manifest", type=Path, help="allow a registered dedicated historical install whose core is not a junction")
    compat_set_install_cmd.add_argument("--dry-run", action="store_true", help="report the install plan without copying anything")
    compat_set_install_cmd.add_argument("--json", action="store_true")
    dossier = subcommands.add_parser("dossier", help="build a size-capped agent triage dossier for a mod (index + parts)")
    dossier.add_argument("mod_directory", type=Path)
    dossier.add_argument("--vanilla-core", type=Path)
    dossier.add_argument("--baseline", type=Path, help="only include findings not present in this scan baseline")
    dossier.add_argument("--original-jar", type=Path, help="original .jar (or .zip containing one) for the jar-audit artifact")
    dossier.add_argument("--rig", type=Path, help="deployed/test-rig mod copy for the copy-drift artifact")
    dossier.add_argument("--log", type=Path, help="Starsector stdout log for the log-triage artifact")
    dossier.add_argument("--save", type=Path, help="rig save dir or campaign.xml for a runtime-footprint section (live classes, scripts, factions, markets)")
    dossier.add_argument("--perf", type=Path, help="SPW performance-report.json for a performance section")
    dossier.add_argument("--perf-mod-prefix", action="append", default=[], metavar="PREFIX", help="log-spam prefix for the performance section (needs --log); repeatable")
    dossier.add_argument("--discovery-dir", type=Path, help="directory containing D0-D6 JSON artifacts for dossier presentation")
    dossier.add_argument("--output", type=Path, help="output directory (default: bridgeforge-dossier/<mod-id> under the cwd); never inside In operation/Done")
    dossier.add_argument("--max-kb", type=float, default=DEFAULT_MAX_KB, help=f"per-file (index and each part) size cap in KB (default: {DEFAULT_MAX_KB})")
    dossier.add_argument("--context-lines", type=int, default=DEFAULT_CONTEXT_LINES, help=f"snippet context lines around a flagged line (default: {DEFAULT_CONTEXT_LINES})")
    dossier.add_argument("--json", action="store_true")
    build_probe_mod_cmd = subcommands.add_parser("build-probe-mod", help="compile the bridgeforge-probe in-game probe mod (roadmap P3) and pack it deterministically")
    build_probe_mod_cmd.add_argument("--jdk", required=True, type=Path, help="JDK 17+ home directory (containing bin/javac.exe)")
    build_probe_mod_cmd.add_argument("--core", required=True, type=Path, help="starsector-core directory (for starfarer.api.jar and its sibling jars)")
    build_probe_mod_cmd.add_argument("--install-release", action="store_true", help="also assemble the runtime-only release copy under probe-mod/releases/")
    build_probe_mod_cmd.add_argument("--json", action="store_true")
    probe_config_cmd = subcommands.add_parser("probe-config", help="write bf_probe_config/bf_probe_rig into a test rig's saves/common, and optionally install the probe mod")
    probe_config_cmd.add_argument("mod_dir", type=Path)
    probe_config_cmd.add_argument("--runtime", required=True, type=Path, help="isolated test-rig runtime directory (starsector-core must be a junction/symlink)")
    probe_config_cmd.add_argument("--seconds", type=float, default=60.0, help="combat probe duration in seconds (default: 60)")
    probe_config_cmd.add_argument("--campaign-interval-days", type=float, default=5.0, help="campaign probe re-run interval in in-game days (default: 5)")
    probe_config_cmd.add_argument("--combat-cap", type=int, default=12, help="max hulls per side in the combat probe mission (default: 12)")
    probe_config_cmd.add_argument("--track", action="append", default=[], metavar="ENTITY", help="custom entity id to track position for; repeatable")
    probe_config_cmd.add_argument("--setup", action="append", default=[], metavar="SPEC", help="in-game setup applied once per save via the public API: rep:<faction>=<RepLevel|n>, credits:<N>, ship:<variant>[:<count>], spawn-fleet:<faction>:<fp>, jump:<system>; repeatable")
    probe_config_cmd.add_argument("--profile", metavar="NAME|PATH", help="setup profile (Notepad-friendly .txt): a bundled name (exigency-rep, seeker-betelgeuse, flux-basic) or a path; merged after --setup")
    probe_config_cmd.add_argument("--install", action="store_true", help="also install/refresh the probe mod into <runtime>/mods/bridgeforge-probe/ from the release copy")
    probe_config_cmd.add_argument("--dry-run", action="store_true", help="report what would be written without touching the rig")
    probe_config_cmd.add_argument("--json", action="store_true")
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
    bootstrap_cmd = subcommands.add_parser("bootstrap", help="one-time: write a scan baseline and record the current build manifest for each mod (nothing written inside mods)")
    bootstrap_cmd.add_argument("mod_dirs", nargs="+", type=Path)
    bootstrap_cmd.add_argument("--vanilla-core", required=True, type=Path)
    bootstrap_cmd.add_argument("--baselines-dir", type=Path, help="default: <repo>/bridgeforge-state/baselines")
    bootstrap_cmd.add_argument("--manifests-dir", type=Path, help="default: <repo>/bridgeforge-state/build-manifests")
    bootstrap_cmd.add_argument("--overwrite", action="store_true", help="replace existing baselines (default: keep them)")
    bootstrap_cmd.add_argument("--json", action="store_true")
    locks_cmd = subcommands.add_parser("who-locks", help="read-only process/Restart Manager diagnosis; never stops processes")
    locks_cmd.add_argument("path", type=Path)
    locks_cmd.add_argument("--json", action="store_true")
    intake_cmd = subcommands.add_parser("intake", help="preserve a ZIP and create a fresh convention-layout assessment copy")
    intake_cmd.add_argument("archive", type=Path)
    intake_cmd.add_argument("--repo-root", type=Path, default=Path.cwd())
    intake_cmd.add_argument("--name", help="portable mod folder name (default: sanitized metadata id)")
    intake_cmd.add_argument("--selected-root", help="exact ZIP mod-root candidate when ambiguous")
    intake_cmd.add_argument("--archaeology", action="store_true", help="also collect static D0 discovery evidence")
    intake_cmd.add_argument("--json", action="store_true")
    board_cmd = subcommands.add_parser("board", help="read-only declared-evidence status board; missing evidence remains unknown")
    board_cmd.add_argument("--repo-root", type=Path, default=Path.cwd())
    board_cmd.add_argument("--write", action="store_true", help="write STATUS.generated.json/.md; never replaces manual STATUS.md")
    board_cmd.add_argument("--json", action="store_true")
    promote_cmd = subcommands.add_parser("promote", help="stage/audit a release and retain prior builds; dry-run by default")
    promote_cmd.add_argument("mod", help="folder name under In operation (not a source path)")
    promote_cmd.add_argument("--repo-root", type=Path, default=Path.cwd())
    for option in ("original", "baseline", "behavior-diff", "behavior-risks", "behavior-unknowns"):
        promote_cmd.add_argument("--" + option, required=True, type=Path)
    for option in ("expected-changes", "vanilla-core", "rig", "corpus-dir", "policy"):
        promote_cmd.add_argument("--" + option, type=Path)
    promote_cmd.add_argument("--apply", action="store_true")
    promote_cmd.add_argument("--json", action="store_true")
    rig_doctor_cmd = subcommands.add_parser("rig-doctor", help="pre-flight checks for a test rig: isolation, running game, probe install, enabled mods, working-copy drift, real-install saves untouched")
    rig_doctor_cmd.add_argument("runtime_dir", type=Path)
    rig_doctor_cmd.add_argument("--working", action="append", default=[], metavar="ID=PATH", help="working copy for a mod id (adds to/overrides the defaults); repeatable")
    rig_doctor_cmd.add_argument("--no-default-working", action="store_true", help="don't use the project's known working-copy mapping")
    rig_doctor_cmd.add_argument("--real-install", type=Path, help="real Starsector install, to confirm its saves are untouched (read-only)")
    rig_doctor_cmd.add_argument("--write-saves-baseline", action="store_true", help="record the real install's saves listing as the baseline (the only write)")
    rig_doctor_cmd.add_argument("--reference-manifest", type=Path, help="P10 historical rig manifest; verifies the dedicated install and skips the incompatible RC8 probe check")
    rig_doctor_cmd.add_argument("--json", action="store_true")
    rig_create_cmd = subcommands.add_parser("rig-create", help="register a dedicated historical Starsector install as a P10 reference rig")
    rig_create_cmd.add_argument("--game-version", required=True)
    rig_create_cmd.add_argument("--install", required=True, type=Path, help="dedicated old-game install; never select the player's primary install")
    rig_create_cmd.add_argument("--output", type=Path, help="manifest path (default: bridgeforge-state/reference-rigs/<version>.json)")
    rig_create_cmd.add_argument("--replace", action="store_true", help="replace an existing manifest after re-inventorying the selected install")
    rig_create_cmd.add_argument("--json", action="store_true")
    test_plan_cmd = subcommands.add_parser("test-plan", help="list the minimal live tests and probe assertions for what changed since a build tag (read-only)")
    test_plan_cmd.add_argument("mod_dir", type=Path)
    test_plan_cmd.add_argument("--since", required=True, metavar="TAG", help="build tag to diff against, e.g. r3 or 3")
    test_plan_cmd.add_argument("--manifests-dir", type=Path)
    test_plan_cmd.add_argument("--live-test-instructions", type=Path, help="default: In operation/LIVE_TEST_INSTRUCTIONS.md")
    test_plan_cmd.add_argument("--json", action="store_true")
    perf_gate_cmd = subcommands.add_parser("perf-gate", help="summarise an SPW performance report and log spam; PASS/WARN/FAIL against thresholds (report-only by default)")
    perf_gate_cmd.add_argument("--perf-report", type=Path, help="SPW performance-report.json")
    perf_gate_cmd.add_argument("--log", type=Path, help="Starsector stdout log for spam counts")
    perf_gate_cmd.add_argument("--mod-prefix", action="append", default=[], metavar="PREFIX", help="mod id/package for log-spam counting; repeatable")
    perf_gate_cmd.add_argument("--min-repeats", type=int, default=5)
    perf_gate_cmd.add_argument("--thresholds", type=Path, help='JSON {"metric": {"warn": x, "fail": y}}; omit for report-only')
    perf_gate_cmd.add_argument("--json", action="store_true")
    release_cmd = subcommands.add_parser("release", help="run the release gates and, with --apply and all gates passing, package the mod (dry run by default)")
    release_cmd.add_argument("mod_dir", type=Path)
    release_cmd.add_argument("--original", required=True, type=Path, help="original jar or archive for jar-audit")
    release_cmd.add_argument("--baseline", required=True, type=Path, help="reviewed scan baseline; any new MANUAL finding blocks")
    release_cmd.add_argument("--out-dir", required=True, type=Path)
    release_cmd.add_argument("--vanilla-core", type=Path)
    release_cmd.add_argument("--rig", type=Path, help="rig copy of the mod for the copy-drift gate")
    release_cmd.add_argument("--corpus-dir", type=Path, help="save corpus to re-check (default: In operation/save_corpus/<mod-id>/)")
    release_cmd.add_argument("--policy", type=Path, help="licence policy JSON (default: bundled release_policy.json)")
    release_cmd.add_argument("--behavior-diff", type=Path, help="D5 behavior-diff JSON; required by the D-series release gate")
    release_cmd.add_argument("--behavior-risks", type=Path, help="D1 risks.json consumed by the behavior release gate")
    release_cmd.add_argument("--behavior-unknowns", type=Path, help="D1 unknowns.json consumed by the behavior release gate")
    release_cmd.add_argument("--expected-changes", type=Path, help="D4 expected-changes.json used for validation and release notes")
    release_cmd.add_argument("--apply", action="store_true", help="write the release (only if every gate passes)")
    release_cmd.add_argument("--json", action="store_true")
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
    archaeology_cmd = subcommands.add_parser("archaeology", help="build a deterministic static architecture and cross-reference map (read-only)")
    archaeology_cmd.add_argument("mod_directory", type=Path)
    archaeology_cmd.add_argument("--output", required=True, type=Path)
    archaeology_cmd.add_argument("--save-aliases", type=Path, help="optional real-save alias evidence for confirmed persistent classes")
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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "promote":
        try:
            result = promote_mod(args.mod, args.repo_root, original=args.original, baseline=args.baseline,
                behavior_diff=args.behavior_diff, behavior_risks=args.behavior_risks,
                behavior_unknowns=args.behavior_unknowns, expected_changes=args.expected_changes,
                vanilla_core=args.vanilla_core, rig=args.rig, corpus_dir=args.corpus_dir,
                policy=args.policy, apply=args.apply)
        except (ValueError, OSError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(result, indent=2, sort_keys=True) if args.json else f"{result['status']}: {args.mod}")
        return 1 if result["status"] == "BLOCKED" else 0
    if args.command in {"intake", "board"}:
        try:
            if args.command == "intake":
                result = intake_archive(args.archive, args.repo_root, name=args.name,
                                        selected_root=args.selected_root, archaeology=args.archaeology)
                if args.json:
                    print(json.dumps(result, indent=2, sort_keys=True))
                else:
                    print(f"{result['status']}: {result['destination']}")
                    print("Archive/upstream bytes preserved. Complete and score a revival plan before editing.")
            else:
                result = project_board(args.repo_root)
                if args.write:
                    write_board(result, args.repo_root)
                print(json.dumps(result, indent=2, sort_keys=True) if args.json else render_board(result), end="\n" if args.json else "")
        except (ValueError, OSError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        return 0
    if args.command in {"archaeology", "behavior-map", "risk-register", "hypotheses", "probe-baseline", "save-baseline", "expect", "behavior-diff", "release-behavior-evaluate", "coverage"}:
        try:
            if args.command == "archaeology":
                result = write_archaeology(args.mod_directory, args.output, save_aliases=args.save_aliases)
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
    if args.command == "scan":
        try:
            result = scan_mod(args.mod_directory, TargetProfile(args.target_starsector, args.target_java), args.vanilla_core)
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        try:
            report, manifest = write_artifacts(result, args.output)
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.write_baseline:
            keys = sorted({finding_baseline_key(finding) for finding in result.findings})
            args.write_baseline.parent.mkdir(parents=True, exist_ok=True)
            args.write_baseline.write_text(json.dumps({"findings": keys}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
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
            destination = stage_zip_archive(args.archive, args.output, args.select_root, args.manifest_output)
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
    if args.command == "log-triage":
        try:
            result = triage_log(args.log, args.mod_prefix, mods_dir=args.mods_dir, all_mods=args.all_mods)
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            counts = result["counts"]
            print(f"FATAL={counts['FATAL']} MOD-ERROR={counts['MOD-ERROR']} KNOWN-NOISE={counts['KNOWN-NOISE']} OTHER={counts['OTHER']}")
            milestones = result["milestones"]
            print(f"Main menu reached: {milestones['main_menu_reached']}; campaign loads: {len(milestones['campaign_loads'])}; finished-saving events: {milestones['finished_saving_count']}; mission variant preloads (startup, not play): {len(milestones['mission_variant_preloads'])}")
            for event in result["fatal"]:
                print(f"FATAL line {event['line']} [{event['matched_rule']}]: {event['message']}")
                if event.get("top_mod_frame"):
                    print(f"  top mod frame: {event['top_mod_frame']}")
            for event in result["mod_errors"]:
                print(f"MOD-ERROR line {event['line']}: {event.get('top_mod_frame') or event['message']}")
            for symptom in result["vanilla_shadowing_symptoms"]:
                print(f"Vanilla-shadowing symptom line {symptom['line']}: ship system [{symptom['ship_system']}] from {symptom['csv']}")
            attribution = result.get("attribution")
            if attribution:
                print(f"Crash attribution (mod whose code threw, by exception count): {json.dumps(attribution.get('counts_by_suspect', {}), sort_keys=True)}")
                for event in result["fatal"] + result["mod_errors"]:
                    if event.get("suspect"):
                        print(f"  line {event['line']}: suspect {event['suspect']}; on stack: {', '.join(event.get('involved') or [])}")
            print(result["caveat"])
        return 0 if not result["fatal"] else 1
    if args.command == "copy-drift":
        try:
            result = compare_copies(args.working_copy, args.deployed_copy)
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Working root: {result['working_root']}")
            print(f"Deployed root: {result['deployed_root']}")
            for item in result["missing_in_deployed"]:
                print(f"MISSING-IN-DEPLOYED {item}")
            for item in result["different"]:
                print(f"DIFFERENT {item['path']} (newer: {item['newer_side']})")
            for item in result["extra_in_deployed"]:
                print(f"EXTRA-IN-DEPLOYED {item}")
            print(f"Drift: {result['drift_count']} ({result['status']})")
        return 0 if result["status"] == "PASS" else 1
    if args.command == "jar-audit":
        try:
            result = audit_jar(args.rebuilt, args.original)
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Classes: rebuilt={result['rebuilt_class_count']} original={result['original_class_count']}")
            print(f"Removed: {len(result['removed_classes'])}; changed: {result['changed_class_count']}; unchanged: {result['unchanged_class_count']}")
            for entry in result["bundled_library_packages"]:
                print(f"MANUAL bundled library package: {entry['package']}")
            for entry in result["unexpected_new_packages"]:
                print(f"REVIEW unexpected new package: {entry['package']}")
            for entry in result["reflection_findings"]:
                print(f"MANUAL reflection/File/NIO reference in {entry['class']}: {', '.join(entry['referenced_symbols'])}")
            for entry in result["removed_classes"]:
                print(f"REVIEW removed class: {entry['class']}")
            print(f"Status: {result['status']}")
        return 0 if result["status"] == "PASS" else 1
    if args.command == "build-tag" and args.record_only:
        try:
            manifest = record_current_manifest(args.mod_dir, manifests_dir=args.manifests_dir)
        except BuildTagError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(manifest, indent=2, sort_keys=True, default=str))
        else:
            print(f"Recorded manifest r{manifest['build']} for {manifest['mod_id']}: {manifest['path']} ({manifest['file_count']} files); mod_info.json untouched.")
        return 0
    if args.command == "build-tag":
        try:
            result = apply_build_tag(
                args.mod_dir,
                label=args.label,
                set_value=args.set_value,
                dry_run=args.dry_run,
                manifests_dir=args.manifests_dir,
                record_manifest=not (args.dry_run or args.no_manifest),
            )
        except BuildTagError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"mod_info: {result['mod_info']}")
            print(f"name: {result['old_name']} -> {result['new_name']}")
            if result["version_is_object"]:
                print(f"version: unchanged (an object, not a string): {result['old_version']}")
            else:
                print(f"version: {result['old_version']} -> {result['new_version']}")
            print("Dry run: mod_info.json was not written." if args.dry_run else "mod_info.json updated.")
            if result.get("manifest_path"):
                print(f"Build manifest: {result['manifest_path']} ({result['manifest_file_count']} files)")
        return 0
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
    if args.command == "prepare-test":
        try:
            result = prepare_test(
                args.working_dir,
                args.rig_mod_dir,
                sync=args.sync,
                bump=args.bump,
                label=args.label,
                boot=args.boot,
                mods=args.mods,
                timeout=args.timeout,
                log_name=args.log_name,
                keep_mods=args.keep_mods,
                record_manifest=args.bump and not args.no_manifest,
            )
        except (PrepareTestError, ValueError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Status: {result['status']}")
            if result.get("message"):
                print(result["message"])
            if "drift_before_sync" in result:
                print(f"Drift before sync: {result['drift_before_sync']['drift_count']}")
            if result.get("synced"):
                print(f"Synced {len(result.get('synced_files', []))} file(s).")
                for extra in result.get("extra_in_deployed", []):
                    print(f"EXTRA-IN-DEPLOYED (not touched): {extra}")
            if "bump" in result:
                print(f"Bumped build tag: {result['bump']['old_name']} -> {result['bump']['new_name']}")
            if "boot_test" in result:
                boot_result = result["boot_test"]
                print(f"Boot test: {boot_result.get('status')} {boot_result.get('reason', '')}".rstrip())
        return 0 if result["status"] in {"PASS", "SAME_FOLDER"} else 1
    if args.command == "boot-test":
        try:
            from . import boot_test as boot_test_module
        except ImportError:
            print("bridgeforge: boot-test module unavailable", file=sys.stderr)
            return 2
        if args.pack:
            try:
                result = boot_test_module.run_boot_matrix(args.runtime_dir, args.mods, args.pack, timeout=args.timeout, log_name=args.log_name)
            except (ValueError, CompatSetError) as exc:
                print(f"bridgeforge: {exc}", file=sys.stderr)
                return 2
            if args.json:
                print(json.dumps(result, indent=2, sort_keys=True))
            else:
                print(f"Verdict: {result.get('verdict')}")
                for row in result.get("matrix", []):
                    print(f"  {row['config']}: {row['status']} mods={row['mods']} triage={row['triage']}")
                    if row.get("reason"):
                        print(f"    reason: {row['reason']}")
            return 0 if result.get("verdict") == "PASS" else 1
        try:
            result = boot_test_module.run_boot_test(args.runtime_dir, args.mods, timeout=args.timeout, log_name=args.log_name, keep_mods=args.keep_mods)
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Status: {result.get('status')}")
            if result.get("reason"):
                print(f"Reason: {result['reason']}")
            if result.get("log"):
                print(f"Log: {result['log']}")
            if result.get("triage"):
                print(f"Triage counts: {result['triage'].get('counts')}")
        return 0 if result.get("status") == "PASS" else 1
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
    if args.command == "dossier":
        try:
            result = write_dossier(
                args.mod_directory,
                output=args.output,
                vanilla_core=args.vanilla_core,
                baseline=args.baseline,
                original_jar=args.original_jar,
                rig=args.rig,
                log=args.log,
                save=args.save,
                perf=args.perf,
                perf_mod_prefixes=args.perf_mod_prefix or None,
                discovery_dir=args.discovery_dir,
                max_kb=args.max_kb,
                context_lines=args.context_lines,
            )
        except (DossierError, ValueError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        summary = result["summary"]
        if args.json:
            print(json.dumps({"index_json": str(result["index_json"]), "index_markdown": str(result["index_markdown"]), "summary": summary}, indent=2, sort_keys=True))
        else:
            print(f"Dossier index: {result['index_json']}")
            print(f"Dossier index (Markdown): {result['index_markdown']}")
            print(f"Parts: {summary['part_count']} (sizes KB: {summary['part_sizes_kb']})")
            print(f"Index size: {summary['index_size_kb']} KB")
            print(f"New findings: {summary['new_finding_count']} (baselined: {summary['baselined_count']}, resolved: {summary['resolved_count']})")
            print(f"Open questions: {summary['open_question_count']}")
        return 0
    if args.command == "build-probe-mod":
        repo_root = Path(__file__).resolve().parent.parent
        try:
            result = build_probe_mod(repo_root, args.jdk, args.core)
            if args.install_release:
                result["release"] = install_release(repo_root)
        except ProbeModBuildError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Jar: {result['jar']} ({result['class_count']} classes)")
            print(f"Mission source compiles: {result['mission_compiles']}")
            if result.get("mission_error"):
                print(f"Mission compile error: {result['mission_error']}")
            if "release" in result:
                print(f"Release: {result['release']['release_dir']}")
        return 0 if result["mission_compiles"] else 1
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
    if args.command == "probe-config":
        try:
            result = write_probe_config(
                args.mod_dir,
                args.runtime,
                track_entities=args.track,
                combat_seconds=args.seconds,
                campaign_interval_days=args.campaign_interval_days,
                combat_cap_per_side=args.combat_cap,
                setups=args.setup,
                profile=load_profile(args.profile) if args.profile else None,
                dry_run=args.dry_run,
                install=args.install,
            )
        except ProbeConfigError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            config = result["config"]
            print(f"Target mod: {config['target_mod_id']}")
            print(f"Hulls with a variant: {len(config['hulls'])} (skipped, no variant: {len(config['hulls_skipped_no_variant'])})")
            print(f"Config: {result['config_path']} (written: {result['written']})")
            print(f"Rig marker: {result['marker_path']}")
            if result.get("installed"):
                print(f"Installed probe mod: {result['install']['destination']}")
            for spec in config.get("setups", []) or []:
                print(f"Setup: {spec}")
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
    if args.command == "bootstrap":
        try:
            result = bootstrap_mods(args.mod_dirs, vanilla_core=args.vanilla_core, baselines_dir=args.baselines_dir, manifests_dir=args.manifests_dir, overwrite=args.overwrite)
        except (BuildTagError, ValueError, OSError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True, default=str))
        else:
            for label, entry in result.items():
                kept = " (kept existing)" if entry["baseline_kept_existing"] else ""
                print(f"{label}: baseline {entry['baseline_path']}{kept} - {entry['finding_count']} findings, {entry['manual_finding_count']} MANUAL; manifest r{entry['manifest_build']} ({entry['manifest_file_count']} files)")
        return 0
    if args.command == "rig-create":
        try:
            manifest_path = write_reference_rig_manifest(args.install, game_version=args.game_version, output=args.output, replace=args.replace)
        except (ReferenceRigError, OSError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        result = {"status": "REGISTERED", "game_version": args.game_version, "manifest": str(manifest_path)}
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Reference rig registered: {args.game_version} -> {manifest_path}")
            print("Isolation is an operator assertion; run rig-doctor with --reference-manifest before every session.")
        return 0
    if args.command == "rig-doctor":
        working: dict[str, Path] = {} if args.no_default_working else dict(default_working_copies(Path(__file__).resolve().parent.parent))
        for item in args.working:
            mod_id, sep, path = item.partition("=")
            if not sep or not mod_id or not path:
                print(f"bridgeforge: --working expects ID=PATH, got {item!r}", file=sys.stderr)
                return 2
            working[mod_id] = Path(path)
        try:
            result = rig_doctor(args.runtime_dir, working_copies=working, real_install=args.real_install, write_saves_baseline=args.write_saves_baseline, reference_manifest=args.reference_manifest)
        except (ValueError, OSError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True, default=str))
        else:
            print(f"Rig doctor: {result['status']}")
            for check in result["checks"]:
                print(f"  {check['status']:<8} {check['name']}: {check['detail']}")
        return 1 if result["status"] == "FAIL" else 0
    if args.command == "who-locks":
        try:
            result = who_locks(args.path)
        except (ValueError, OSError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"{result['status']}: {result['target']}")
            for process in result["processes"]:
                print(f"  pid {process['pid']} {process['name']}: {', '.join(process['sources'])}")
            for limitation in result["limitations"]:
                print(f"  limitation: {limitation}")
            print(result["note"])
        return 0
    if args.command == "test-plan":
        try:
            result = plan_tests(args.mod_dir, args.since, manifests_dir=args.manifests_dir, live_test_instructions=args.live_test_instructions)
        except (TestPlanError, ValueError, OSError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True, default=str))
        else:
            print(f"Changed since {result['since_tag']}: {result['changed_file_count']} file(s)")
            print(f"Features to re-test: {', '.join(result['features']) or 'none'}")
            for assertion in result["probe_assertions"]:
                print(f"  probe: {assertion if isinstance(assertion, str) else json.dumps(assertion, sort_keys=True)}")
            print(f"Live-test IDs ({result['live_test_section'] or 'no section for this mod'}): {', '.join(map(str, result['live_test_ids'])) or 'none'}")
            if result["unmatched_files"]:
                print(f"Unmatched files (review by hand): {len(result['unmatched_files'])}")
        return 0
    if args.command == "perf-gate":
        if not args.perf_report and not args.log:
            print("bridgeforge: give --perf-report and/or --log", file=sys.stderr)
            return 2
        try:
            summary: dict[str, object] = {}
            report = ingest_spw_report(args.perf_report) if args.perf_report else None
            spam = log_spam(args.log, args.mod_prefix, min_repeats=args.min_repeats) if args.log else None
            if report:
                startup_ms = (report.get("startup") or {}).get("total_ms")
                if isinstance(startup_ms, (int, float)):
                    summary["startup_ms"] = startup_ms
                shares = [entry.get("cpu_share") for entry in report.get("per_mod", []) if isinstance(entry.get("cpu_share"), (int, float))]
                if shares:
                    summary["cpu_share"] = max(shares)
            if spam:
                summary["spam_count"] = spam["total_spam_lines"]
            thresholds = json.loads(args.thresholds.read_text(encoding="utf-8")) if args.thresholds else None
            gate = perf_gate(summary, thresholds)
        except (SpwBridgeError, ValueError, OSError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        result = {"gate": gate, "summary": summary, "report": report, "spam": spam}
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True, default=str))
        else:
            print(f"Perf gate: {gate['status']}")
            for check in gate["checks"]:
                print(f"  {check['metric']}={check['value']} ({check['result']})")
            for prefix, entries in (spam or {}).get("by_prefix", {}).items():
                for entry in entries[:5]:
                    print(f"  spam [{prefix}] x{entry['count']}: {entry['message'][:160]}")
        return 1 if gate["status"] == "FAIL" else 0
    if args.command == "release":
        try:
            result = release_mod(
                args.mod_dir,
                original=args.original,
                baseline=args.baseline,
                out_dir=args.out_dir,
                vanilla_core=args.vanilla_core,
                rig=args.rig,
                corpus_dir=args.corpus_dir,
                policy_path=args.policy,
                behavior_diff_path=args.behavior_diff,
                behavior_risks_path=args.behavior_risks,
                behavior_unknowns_path=args.behavior_unknowns,
                expected_changes_path=args.expected_changes,
                require_behavior_evidence=True,
                apply=args.apply,
            )
        except (ReleaseError, ValueError, OSError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True, default=str))
        else:
            print(f"Release: {result['status']}")
            for name, gate in result["gates"].items():
                detail = gate.get("reason") or gate.get("error") or ""
                print(f"  {gate['status']:<8} {name}" + (f" - {detail}" if detail else ""))
            for path in result.get("written", []):
                print(f"  wrote {path}")
        return 1 if result["status"] == "BLOCKED" else 0
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
