from __future__ import annotations

from .safeio import atomic_write_text

import argparse
import json
import sys
from pathlib import Path

from .dossier import DEFAULT_CONTEXT_LINES, DEFAULT_MAX_KB, DossierError, write_dossier
from .archive_intake import inspect_zip_archive, stage_zip_archive
from .log_triage import triage_log
from .build_tag import apply_build_tag, BuildTagError, DEFAULT_LABEL
from .prepare_test import PrepareTestError, prepare_test
from .probe_config import ProbeConfigError, write_probe_config
from .probe_mod_build import ProbeModBuildError, build_probe_mod, install_release
from .compat_sets import CompatSetError
from .live_accept import AcceptError, accept_run
from .soak_report import soak_report
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bridgeforge", description="Safe, explainable legacy Starsector mod analysis and migration.")
    subcommands = parser.add_subparsers(dest="command", required=True)
    archive_preflight = subcommands.add_parser("archive-preflight", help="inspect a ZIP archive without extracting it")
    archive_preflight.add_argument("archive", type=Path)
    archive_preflight.add_argument("--output", type=Path)
    archive_stage = subcommands.add_parser("archive-stage", help="extract a preflight-safe ZIP into a new explicit destination")
    archive_stage.add_argument("archive", type=Path)
    archive_stage.add_argument("--output", required=True, type=Path)
    archive_stage.add_argument("--select-root", help="one preflight candidate mod root when the archive contains multiple")
    archive_stage.add_argument("--manifest-output", type=Path, help="optional manifest path outside the staged directory")
    log_triage = subcommands.add_parser("log-triage", help="classify a Starsector log into FATAL / MOD-ERROR / KNOWN-NOISE / OTHER without modifying it")
    log_triage.add_argument("log", type=Path)
    log_triage.add_argument("--mod-prefix", action="append", default=[], metavar="PREFIX", help="additional mod source/package prefix to attribute errors to; repeatable")
    log_triage.add_argument("--mods-dir", type=Path, help="mods folder the log ran with: names the mod whose jar owns each crash frame (suspect/involved)")
    log_triage.add_argument("--all-mods", action="store_true", help="with --mods-dir: index every mod folder, not just enabled_mods.json (e.g. a log from a different mod list)")
    log_triage.add_argument("--last-sessions", type=int, metavar="N", help="a rolling starsector.log: triage only its last N game sessions (a relaunch during a test logs only there)")
    log_triage.add_argument("--json", action="store_true")
    build_tag = subcommands.add_parser("build-tag", help="iterate a visible build tag in a revived mod's mod_info.json name/version, surgically (never re-serializes the file)")
    build_tag.add_argument("mod_dir", type=Path)
    build_tag.add_argument("--label", default=DEFAULT_LABEL, help=f"suffix label used in the name tag, e.g. '[LABEL rN]' (default: {DEFAULT_LABEL})")
    build_tag.add_argument("--set", dest="set_value", type=int, help="force the build number instead of incrementing")
    build_tag.add_argument("--dry-run", action="store_true", help="print the proposed change without writing mod_info.json")
    build_tag.add_argument("--no-manifest", action="store_true", help="don't record the per-tag file hash manifest that test-plan diffs against")
    build_tag.add_argument("--record-only", action="store_true", help="record the manifest for the CURRENT build (r0 if untagged) without bumping or writing mod_info.json")
    build_tag.add_argument("--manifests-dir", type=Path, help="where build manifests go (default: <repo>/bridgeforge-state/build-manifests; never inside the mod)")
    build_tag.add_argument("--json", action="store_true")
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
    from .cli_commands import register_all
    register_all(subcommands)
    envc_cmd = subcommands.add_parser("env-check", help="read a launcher .bat (following @argfiles) and report java version, javaagents and their order, Prepatcher last or not, heap, and enabled mods that need Prepatcher the launch lacks; read-only (ROADMAP item 63)")
    envc_cmd.add_argument("launcher", type=Path, help="the launcher .bat")
    envc_cmd.add_argument("--vmparams", type=Path, action="append", default=[], help="extra vmparams / fr.vmparams file to read (repeatable)")
    envc_cmd.add_argument("--mods-dir", type=Path, help="a mods folder with enabled_mods.json: enabled mods that depend on Prepatcher or the Toolbox fork are checked against the launch")
    envc_cmd.add_argument("--json", action="store_true")
    jm_cmd = subcommands.add_parser("java-matrix",help="boot one mod set through every Java version and launcher (direct / Fast Rendering) in a rig; local-only, needs a rig and the game install (ROADMAP item 61)")
    jm_sub = jm_cmd.add_subparsers(dest="java_matrix_command", required=True)
    jm_discover = jm_sub.add_parser("discover", help="list the JDKs found beside the rig's install, in the rig and in the usual install folders")
    jm_discover.add_argument("--rig", type=Path)
    jm_discover.add_argument("--jdk-root", type=Path, action="append", default=[], help="extra folder holding JDKs (repeatable)")
    jm_discover.add_argument("--json", action="store_true")
    jm_setup = jm_sub.add_parser("setup", help="write one run-j<major>-<launcher>.bat per variant into the rig (never touches run-java25.bat)")
    jm_setup.add_argument("rig", type=Path)
    jm_setup.add_argument("--java", type=int, nargs="+", metavar="MAJOR", help="only these Java majors (default: every JDK found)")
    jm_setup.add_argument("--launcher", nargs="+", choices=["direct", "fr", "miko", "miko-noprep"], help="default: both")
    jm_setup.add_argument("--jdk-root", type=Path, action="append", default=[])
    jm_setup.add_argument("--prepatcher", action="store_true", help="also write a -prep twin of each direct/fr variant with the Prepatcher javaagent last (direct + Prepatcher is a recorded KNOWN_FAIL)")
    jm_setup.add_argument("--include-known-fail", action="store_true", help="boot the KNOWN_FAIL variants too instead of only reporting them")
    jm_setup.add_argument("--json", action="store_true")
    jm_run = jm_sub.add_parser("run", help="boot --mods through every variant --repeats times and report a pass rate per variant")
    jm_run.add_argument("rig", type=Path)
    jm_run.add_argument("--mods", nargs="+", required=True, metavar="ID")
    jm_run.add_argument("--java", type=int, nargs="+", metavar="MAJOR")
    jm_run.add_argument("--launcher", nargs="+", choices=["direct", "fr", "miko", "miko-noprep"])
    jm_run.add_argument("--jdk-root", type=Path, action="append", default=[])
    jm_run.add_argument("--prepatcher", action="store_true", help="also run a -prep twin of each direct/fr variant with the Prepatcher javaagent last (direct + Prepatcher is a recorded KNOWN_FAIL, reported not booted)")
    jm_run.add_argument("--include-known-fail", action="store_true", help="boot the KNOWN_FAIL variants too instead of only reporting them")
    jm_run.add_argument("--repeats", type=int, default=3)
    jm_run.add_argument("--timeout", type=int, default=240)
    jm_run.add_argument("--log-name")
    jm_run.add_argument("--parallel", type=int, default=None, metavar="N", help="boot up to N variants at once, 1..3, each in its own instance rig (default 1, the serial reference; 3 with --preset compare)")
    jm_run.add_argument("--preset", choices=["compare", "real"], help="compare = Java 25 and 28, direct and Fast Rendering: vanilla, FR, Java 28, FR + Java 28 (4 variants, 3 at a time); real = the owner's Miko launch on Java 28, with and without Prepatcher")
    jm_run.add_argument("--skip-known", action="store_true", help="reuse a recorded all-pass for the same variant, Java build and mod set instead of booting again (new mod sets always boot)")
    jm_run.add_argument("--ledger", type=Path, default=Path("bridgeforge-state") / "java-matrix-ledger.json")
    jm_run.add_argument("--quiet", action="store_true", help="no per-boot progress lines on stderr")
    jm_run.add_argument("--json", action="store_true")
    jm_mass = jm_sub.add_parser("mass", help="test every archived mod in Done/ (with its dependencies only) through the variants, screening first; reports which mods behave differently by environment (ROADMAP item 62)")
    jm_mass.add_argument("rig", type=Path)
    jm_mass.add_argument("--done-dir", type=Path, default=Path("Done"))
    jm_mass.add_argument("--only", nargs="+", metavar="NAME", help="only these Done/ folders")
    jm_mass.add_argument("--limit", type=int, help="test only the first N mods")
    jm_mass.add_argument("--providers", type=Path, action="append", default=[], help="extra folder of mods that supply dependencies (the rig's mods/ and the install's mods/ are always searched)")
    jm_mass.add_argument("--java", type=int, nargs="+", metavar="MAJOR", default=[25, 28])
    jm_mass.add_argument("--launcher", nargs="+", choices=["direct", "fr", "miko", "miko-noprep"])
    jm_mass.add_argument("--preset", choices=["compare", "real"], help="compare = Java 25 and 28, direct and Fast Rendering (what mass runs by default); real = the owner's Miko launch on Java 28, with and without Prepatcher (2 at a time)")
    jm_mass.add_argument("--jdk-root", type=Path, action="append", default=[])
    jm_mass.add_argument("--no-screen", action="store_true", help="boot every variant for every mod (default: baseline and Fast Rendering on the highest Java first; the rest only on a mismatch)")
    jm_mass.add_argument("--retest-baseline", action="store_true", help="also re-boot the baseline for LIVE_VALIDATED mods (default: assume it passes)")
    jm_mass.add_argument("--bundle", type=int, default=4, metavar="N", help="boot up to N unrelated mods together while screening and split only on a failure (default 4; 1 = one mod per boot). Total conversions and core-replacing mods always boot alone")
    jm_mass.add_argument("--repeats", type=int, default=1)
    jm_mass.add_argument("--parallel", type=int, default=3, metavar="N")
    jm_mass.add_argument("--timeout", type=int, default=240)
    jm_mass.add_argument("--skip-known", action="store_true")
    jm_mass.add_argument("--ledger", type=Path, default=Path("bridgeforge-state") / "java-matrix-ledger.json")
    jm_mass.add_argument("--output", type=Path, default=Path("bridgeforge-state") / "mass-test")
    jm_mass.add_argument("--quiet", action="store_true", help="no per-mod progress lines on stderr")
    jm_mass.add_argument("--json", action="store_true")
    jm_inst = jm_sub.add_parser("instances", help="list the parallel instances of a rig: variant, run, state, whether its java is alive")
    jm_inst.add_argument("rig", type=Path)
    jm_inst.add_argument("--json", action="store_true")
    jm_log = jm_sub.add_parser("describe-log", help="read a tester's starsector.log: Java version and whether Fast Rendering was loaded")
    jm_log.add_argument("log", type=Path)
    jm_log.add_argument("--json", action="store_true")
    boot_test_cmd = subcommands.add_parser("boot-test", help="run a boot smoke test of a Starsector runtime with explicit mods enabled")
    boot_test_cmd.add_argument("runtime_dir", type=Path)
    boot_test_cmd.add_argument("--mods", nargs="+", required=True, metavar="ID")
    boot_test_cmd.add_argument("--pack", metavar="SET", help="also run a compat-set matrix (roadmap P4): --mods alone with the libs it needs, then --mods plus this whole named set (e.g. 'standard')")
    boot_test_cmd.add_argument("--timeout", type=int, default=240)
    boot_test_cmd.add_argument("--log-name")
    boot_test_cmd.add_argument("--keep-mods", action="store_true")
    boot_test_cmd.add_argument("--json", action="store_true")
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
    probe_config_cmd.add_argument("--setup", action="append", default=[], metavar="SPEC", help="in-game setup applied once per save via the public API: rep:<faction>=<RepLevel|n>, credits:<N>, ship:<variant>[:<count>], spawn-fleet:<faction>:<fp>, jump:<system>, swap-industry:<from>:<to>:<count>[:<condition-prefix>]; repeatable")
    probe_config_cmd.add_argument("--profile", metavar="NAME|PATH", help="setup profile (Notepad-friendly .txt): a bundled name (exigency-rep, seeker-betelgeuse, flux-basic) or a path; merged after --setup")
    probe_config_cmd.add_argument("--install", action="store_true", help="also install/refresh the probe mod into <runtime>/mods/bridgeforge-probe/ from the release copy")
    probe_config_cmd.add_argument("--dry-run", action="store_true", help="report what would be written without touching the rig")
    probe_config_cmd.add_argument("--json", action="store_true")
    accept_cmd = subcommands.add_parser("accept", help="record a passing hand-run live test of one workspace: checks the log, writes the dated evidence section and LIVE_VALIDATED to the revival report, and a run record the archive gate reads")
    accept_cmd.add_argument("workspace", type=Path)
    accept_cmd.add_argument("--log", required=True, type=Path, help="the run's stdout log")
    accept_cmd.add_argument("--test-id", required=True)
    accept_cmd.add_argument("--note", required=True, help="what the owner did and saw")
    accept_cmd.add_argument("--not-exercised", help="what the run did not cover (for example: no raid on the station happened)")
    accept_cmd.add_argument("--days", type=float, help="campaign days the run was meant to cover; INCOMPLETE soak is refused")
    accept_cmd.add_argument("--mods-dir", type=Path, help="the rig's mods/ directory, to attribute errors to mods")
    accept_cmd.add_argument("--accept-findings", help="reason to accept probe FAIL lines or caught exceptions; written into the report")
    accept_cmd.add_argument("--record-only", action="store_true", help="write only the run record, not a report section (the report already says it)")
    accept_cmd.add_argument("--json", action="store_true")
    soak_cmd = subcommands.add_parser("soak-report", help="judge a long-run campaign session from its log: days covered, FATAL/MOD-ERROR, probe FAILs and caught exceptions (read-only)")
    soak_cmd.add_argument("log", type=Path)
    soak_cmd.add_argument("--days", type=float, required=True, help="campaign days the run was meant to cover")
    soak_cmd.add_argument("--mods-dir", type=Path, help="the rig's mods/ directory, to attribute caught exceptions to mods")
    soak_cmd.add_argument("--json", action="store_true")

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
    intake_cmd.add_argument("archive", type=Path, help="a mod ZIP, or a raw mod folder (zipped into In operation/_raw-zips/ first, the folder itself is left alone)")
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
    rig_doctor_cmd.add_argument("--core-baseline", type=Path, help="core hash baseline (default bridgeforge-state/rig-core-baseline.json)")
    rig_doctor_cmd.add_argument("--write-core-baseline", action="store_true", help="record the rig starsector-core hashes as the baseline (do this on a known-good RC8 install)")
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
    subs_cmd = subcommands.add_parser("dependency-substitutes", help="rank visible mods that could replace a missing or discontinued dependency (EXACT / PARTIAL / NONE) and recommend SWAP, REVIVE_DEPENDENCY, STRIP_FROM_MOD or ESCALATE")
    subs_cmd.add_argument("mod", type=Path, help="mod working copy")
    subs_cmd.add_argument("--providers", type=Path, action="append", default=[], help="mods folder, mod folder or In operation tree to search; repeatable (default: <repo>/In operation and its rig's mods)")
    subs_cmd.add_argument("--vanilla-core", type=Path, help="read-only starsector-core, so vanilla content isn't counted as missing")
    subs_cmd.add_argument("--policy", type=Path, help="licence policy JSON (default: bundled release_policy.json); flags a REVIVE_DEPENDENCY recommendation as local-only when its licence doesn't allow redistribution")
    subs_cmd.add_argument("--write", action="store_true", help="also record the result in <workspace>/reports/dependencies.json, which `board` shows")
    subs_cmd.add_argument("--provider-index", type=Path, help="saved `provider-index build` output: also consider mods it lists that are not visible live")
    provider_index_cmd = subcommands.add_parser("provider-index", help="save what every visible mod defines (hull mods, weapons, wings, hulls, classes, with game and mod version) as a corpus artefact, so provider lookups work without the mods installed")
    provider_index_sub = provider_index_cmd.add_subparsers(dest="provider_index_command", required=True)
    provider_index_build = provider_index_sub.add_parser("build", help="index the --providers folders")
    provider_index_build.add_argument("--providers", type=Path, action="append", default=[], help="mods folder, mod folder or In operation tree; repeatable (default: <repo>/In operation and its rig's mods)")
    provider_index_build.add_argument("--output", type=Path, default=Path("bridgeforge-state") / "provider-index.json")
    graph_cmd = subcommands.add_parser("dependency-graph", help="across every queued workspace, which non-current mods need reviving and how many queued mods each would unblock (revival order)")
    graph_cmd.add_argument("--queue", type=Path, help="folder of workspaces (<name>/working); default <repo>/In operation")
    graph_cmd.add_argument("--providers", type=Path, action="append", default=[], help="as for dependency-substitutes; repeatable")
    graph_cmd.add_argument("--vanilla-core", type=Path)
    graph_cmd.add_argument("--provider-index", type=Path)
    graph_cmd.add_argument("--write", action="store_true", help="write <queue>/DEPENDENCY_GRAPH.json and .md, and each mod's reports/dependencies.json, all of which `board` shows")
    graph_cmd.add_argument("--restart", action="store_true", help="with --write: ignore an earlier interrupted run's <queue>/DEPENDENCY_GRAPH.partial.jsonl")
    graph_cmd.add_argument("--quiet", action="store_true", help="no per-mod progress lines on stderr")
    graph_cmd.add_argument("--json", action="store_true")
    subs_cmd.add_argument("--json", action="store_true")
    stats_cmd = subcommands.add_parser("finding-stats", help="count findings across workspaces by automation tier: how many mods could be revived unattended, and which finding ids to automate next (roadmap P15 item 1)")
    stats_cmd.add_argument("roots", type=Path, nargs="*", help="queue folders or single workspaces; default <repo>/In operation")
    stats_cmd.add_argument("--scan", action="store_true", help="scan each <ws>/working afresh instead of reading its latest stored scan")
    stats_cmd.add_argument("--vanilla-core", type=Path, help="with --scan: also compile-check loose scripts")
    stats_cmd.add_argument("--write", type=Path, metavar="DIR", help="write FINDING_STATS.json and FINDING_STATS.md into DIR; with --scan, each workspace's result is also appended to DIR/FINDING_STATS.partial.jsonl as it finishes, so an interrupted run resumes")
    stats_cmd.add_argument("--restart", action="store_true", help="with --write: ignore an earlier run's FINDING_STATS.partial.jsonl and scan everything again")
    stats_cmd.add_argument("--quiet", action="store_true", help="no per-workspace progress lines on stderr")
    stats_cmd.add_argument("--json", action="store_true")
    sup_cmd = subcommands.add_parser("supersession", help="find queued mods whose author has released a newer version (in the real install's mods/ or a modpack); read-only")
    sup_cmd.add_argument("queue", type=Path, help="the queue folder (In operation)")
    sup_cmd.add_argument("--against", type=Path, action="append", default=[], metavar="DIR", help="a folder of mods to compare with; repeatable")
    sup_cmd.add_argument("--corpus-index", type=Path, help="also compare with every mod_info.json a corpus-index database lists (the Downloads archive)")
    sup_cmd.add_argument("--quiet", action="store_true", help="no per-workspace progress lines on stderr")
    sup_cmd.add_argument("--json", action="store_true")
    archive_cmd = subcommands.add_parser("archive", help="package a finished revival into Done/<Mod>/: mod folder, zip, original, reports and an archive note (needs a licence decision; never deletes the workspace)")
    archive_cmd.add_argument("workspace", type=Path)
    archive_cmd.add_argument("--done", type=Path, help="default: <repo>/Done")
    archive_cmd.add_argument("--policy", type=Path)
    archive_cmd.add_argument("--refresh", action="store_true", help="replace an existing archive of this mod in Done/ (only a folder holding an ARCHIVE_NOTE.md directly inside Done/)")
    archive_cmd.add_argument("--readme-copy", action="store_true", help="also write <zip>-with-readme.zip and readme.txt for this archive")
    archive_cmd.add_argument("--json", action="store_true")
    audit_cmd = subcommands.add_parser("audit-shipped", help="compare a workspace's shipped copy with original/: every changed, added or removed file must be explained by a recorded change (ROADMAP 36.3); also shows its live status (36.7)")
    audit_cmd.add_argument("workspace", type=Path)
    audit_cmd.add_argument("--json", action="store_true")
    explain_cmd = subcommands.add_parser("audit-explain", help="record why shipped files differ from original/, or (--live) why the mod may be archived without a current live result")
    explain_cmd.add_argument("workspace", type=Path)
    explain_cmd.add_argument("files", nargs="*", help="shipped paths relative to working/")
    explain_cmd.add_argument("--reason", help="why; required unless --auto")
    explain_cmd.add_argument("--auto", action="store_true", help="record every difference whose category the files prove (credits, syntax-only JSON, manufacturer column, unloaded archive, translation); no files or reason needed")
    explain_cmd.add_argument("--live", action="store_true")
    explain_cmd.add_argument("--json", action="store_true")
    relink_cmd = subcommands.add_parser("relink", help="recompile classes whose game calls RC8 changed only by return type (jar-linkage-unresolved), from shipped or decompiled source, unedited; patch only when nothing else changes. A queue folder or one workspace")
    relink_cmd.add_argument("path", type=Path, help="a queue (In operation) or one workspace")
    relink_cmd.add_argument("--vanilla-core", type=Path, required=True)
    relink_cmd.add_argument("--apply", action="store_true", help="install (backups in scratch/jar-patch-<date>/); default: report only")
    relink_cmd.add_argument("--restart", action="store_true", help="ignore an earlier run's checkpoint")
    relink_cmd.add_argument("--quiet", action="store_true", help="no per-workspace progress lines on stderr")
    relink_cmd.add_argument("--json", action="store_true")
    bump_cmd = subcommands.add_parser("bump-version", help="a shipped mod changed after archiving: +bf.N in mod_info, a dated revival-report section ending READY_FOR_LIVE_TEST, and a MOD_CHANGELOG line")
    bump_cmd.add_argument("workspace", type=Path)
    bump_cmd.add_argument("--note", required=True, help="what changed and the evidence (first line goes to the mod changelog)")
    bump_cmd.add_argument("--date")
    declare_cmd = subcommands.add_parser("declare-providers", help="apply a content-reference-unresolved SWAP: declare the visible 0.98 mods that provide every needed id (nothing else changes); any other strategy is left for a person")
    declare_cmd.add_argument("workspace", type=Path, nargs="+")
    declare_cmd.add_argument("--apply", action="store_true")
    close_cmd = subcommands.add_parser("close", help="end revival work on a mod: a dated report section ending SUPERSEDED or NOT_REVIVABLE; queue commands skip it after")
    close_cmd.add_argument("workspace", type=Path)
    close_cmd.add_argument("--status", required=True, choices=["SUPERSEDED", "NOT_REVIVABLE"])
    close_cmd.add_argument("--reason", required=True, help="the evidence: what supersedes it, or what RC8 removed")
    restore_cmd = subcommands.add_parser("restore-from-done", help="rebuild an In operation workspace from a Done/ archive (shipped folder, original, reports and baseline)")
    restore_cmd.add_argument("archive", type=Path, help="Done/<Mod>")
    restore_cmd.add_argument("--queue", type=Path, help="default: <repo>/In operation")
    review_cmd = subcommands.add_parser("revive-review", help="every fix revive applied since a date, as diffs against the first backup, with placement checks (lookup guards, jar-source edits)")
    review_cmd.add_argument("queue", type=Path)
    review_cmd.add_argument("--since", required=True, help="YYYY-MM-DD")
    review_cmd.add_argument("--json", action="store_true")
    modlog_cmd = subcommands.add_parser("mod-changelog", help="MOD_CHANGELOG.md: bigger updates to revived mods by date (archive adds one per archived mod)")
    modlog_sub = modlog_cmd.add_subparsers(dest="modlog_command", required=True)
    modlog_add = modlog_sub.add_parser("add", help="add one line under its date")
    modlog_add.add_argument("mod", help="the mod's display name")
    modlog_add.add_argument("text", help="what changed, one line")
    modlog_add.add_argument("--version")
    modlog_add.add_argument("--date", help="YYYY-MM-DD (default today)")
    modlog_add.add_argument("--file", type=Path, help="default: <repo>/MOD_CHANGELOG.md")
    modlog_seed = modlog_sub.add_parser("seed", help="one 'archived' line per Done/*/ARCHIVE_NOTE.md, under its archive date")
    modlog_seed.add_argument("--done", type=Path, help="default: <repo>/Done")
    modlog_seed.add_argument("--file", type=Path)
    ready_cmd = subcommands.add_parser("ready-list", help="the queue's mods ready for live testing (revival report READY_FOR_LIVE_TEST and latest revive UNATTENDED_DONE), with how to launch them")
    ready_cmd.add_argument("queue", type=Path)
    ready_cmd.add_argument("--json", action="store_true")
    group_cmd = subcommands.add_parser("probe-group", help="probe several finished mods in one live session: plan compatible groups, install one into the rig, report per mod (ROADMAP P15 item 24)")
    group_sub = group_cmd.add_subparsers(dest="probe_group_command", required=True)
    group_plan = group_sub.add_parser("plan", help="group READY_FOR_LIVE_TEST workspaces that share no mod or content id and whose dependencies are in the rig")
    group_plan.add_argument("--queue", type=Path, help="default: <repo>/In operation")
    group_plan.add_argument("--rig", type=Path, help="default: <queue>/_rig")
    group_plan.add_argument("--size", type=int, default=8, help="most mods per group (default 8)")
    group_plan.add_argument("--write", type=Path, help="save the plan as JSON (default: <queue>/PROBE_GROUPS.json)")
    group_plan.add_argument("--exclude", action="append", default=[], metavar="WORKSPACE", help="leave this workspace out; repeatable")
    group_plan.add_argument("--solo", action="append", default=[], metavar="WORKSPACE", help="give this workspace a group of its own; repeatable")
    group_plan.add_argument("--retest", action="append", default=[], metavar="WORKSPACE", help="add an already live-validated workspace as a group of its own to run again, e.g. under another Java or Fast Rendering; its recorded status is not touched until `record`; repeatable")
    group_plan.add_argument("--provider-source", action="append", type=Path, default=None, metavar="MODS_DIR", help="a mods/ folder to copy missing providers from when the queue has none (default: the real install's mods/ and the 0.98 modpack in Downloads, when present); repeatable")
    group_plan.add_argument("--no-auto-solo", action="store_true", help="also group large campaign mods (by default a mod that creates systems and has 60+ content ids runs alone)")
    group_plan.add_argument("--json", action="store_true")
    group_install = group_sub.add_parser("install", help="copy/sync one group's mods into the rig, write the merged probe config, set enabled_mods.json")
    group_install.add_argument("group", type=int)
    group_install.add_argument("--plan", type=Path, help="default: <queue>/PROBE_GROUPS.json")
    group_install.add_argument("--queue", type=Path)
    group_install.add_argument("--rig", type=Path)
    group_install.add_argument("--stage-providers", action="store_true", help="also copy the queue workspaces that provide missing dependencies into the rig, verifying id, version and files (ROADMAP 36.1)")
    group_install.add_argument("--with-lunalib", action="store_true", help="also enable LunaLib whenever GraphicsLib (any version) is enabled without it (RC8-25: GraphicsLib 1.12.1 needs it under Fast Rendering; 1.12.1 gets it automatically)")
    group_install.add_argument("--no-lunalib", action="store_true", help="do not enable LunaLib automatically for GraphicsLib 1.12.1 (to show the dependency gap, RC8-25)")
    group_install.add_argument("--setup", action="append", default=[], metavar="SPEC", help="probe setup applied once per save, as for probe-config --setup; also swap-industry:<from>:<to>:<count>[:<condition-prefix>] (probe 0.2.25); repeatable")
    group_install.add_argument("--also-enable", action="append", default=[], metavar="MOD_OR_SET", help="also enable this mod id (with its dependencies) or named set (aotd: Vaults of Knowledge, Toolbox fork, Prepatcher, BMO, Ashlib); repeatable; every id must be in the rig")
    group_install.add_argument("--save-after-checks", action="store_true", help="the probe saves the game once after the day-1 checks, so the save can be read and reloaded (probe 0.2.26)")
    group_install.add_argument("--expect-supply", action="append", default=[], metavar="COMMODITY@INDUSTRY", help="the probe's market-supply check FAILs unless INDUSTRY supplies COMMODITY in some market (probe 0.2.25); repeatable")
    group_install.add_argument("--json", action="store_true")
    group_bisect = group_sub.add_parser("bisect", help="split a failed group into two new groups at the end of the plan, each dependency-closed (ROADMAP 36.8)")
    group_bisect.add_argument("group", type=int)
    group_bisect.add_argument("--plan", type=Path, help="default: <queue>/PROBE_GROUPS.json")
    group_bisect.add_argument("--queue", type=Path)
    group_bisect.add_argument("--rig", type=Path)
    group_bisect.add_argument("--json", action="store_true")
    group_record = group_sub.add_parser("record", help="after a run: mark PASS members LIVE_VALIDATED; with --archive also record the standing local-only licence, archive into Done/ and copy each zip to Done/'s top")
    group_record.add_argument("test_id", help="the bf-test.ps1 test id; reads <rig>/logs/<TESTID>.stdout.log")
    group_record.add_argument("--archive", action="store_true")
    group_record.add_argument("--refresh", action="store_true", help="with --archive: replace an earlier archive of the same mod in Done/ (deletes that folder; Done/ must hold an ARCHIVE_NOTE.md there)")
    group_record.add_argument("--queue", type=Path)
    group_record.add_argument("--rig", type=Path)
    group_record.add_argument("--json", action="store_true")
    group_smoke = group_sub.add_parser("smoke", help="after `install`: boot the rig unattended to the main menu and triage the startup log (no launcher click, no New Game); catches load-time failures before a person plays")
    group_smoke.add_argument("--bat", default="run-j25-direct.bat", help="rig launcher to start (default: java 25, started directly)")
    group_smoke.add_argument("--timeout", type=int, default=240)
    group_smoke.add_argument("--log-name")
    group_smoke.add_argument("--rig", type=Path)
    group_smoke.add_argument("--queue", type=Path)
    group_smoke.add_argument("--json", action="store_true")
    group_live = group_sub.add_parser("live", help="after `install`: play the group's live run unattended with real mouse clicks (launcher, New Game, the campaign probe's day, the probe combat mission) and confirm each stage from the log; leave the mouse and keyboard alone")
    group_live.add_argument("test_id", help="log name: writes <rig>/logs/<TESTID>.stdout.log, readable by `probe-group report` and `record`")
    group_live.add_argument("--bat", default="run-j25-direct.bat")
    group_live.add_argument("--menu-timeout", type=int, default=240)
    group_live.add_argument("--rig", type=Path)
    group_live.add_argument("--queue", type=Path)
    group_live.add_argument("--json", action="store_true")
    group_regress = group_sub.add_parser("regress", help="unattended regression pass: group every LIVE_VALIDATED workspace, then install, play (`live`) and report each group; never records, writes a summary of what needs a look (ROADMAP 60g)")
    group_regress.add_argument("--bat", default="run-j25-direct.bat")
    group_regress.add_argument("--size", type=int, default=8)
    group_regress.add_argument("--limit", type=int, help="only the first N groups")
    group_regress.add_argument("--only", action="append", default=[], metavar="WORKSPACE", help="only these workspaces; repeatable")
    group_regress.add_argument("--out", type=Path, help="summary JSON (default: <queue>/_regress/regress-<date>.json)")
    group_regress.add_argument("--test-prefix", help="test id prefix (default REG-<date>)")
    group_regress.add_argument("--rejudge", type=Path, metavar="SOURCE", help="no game: judge a finished (or running) pass's saved logs again with the current report; SOURCE is its summary JSON or .partial.jsonl checkpoint")
    group_regress.add_argument("--quiet", action="store_true", help="no per-group progress lines")
    group_regress.add_argument("--rig", type=Path)
    group_regress.add_argument("--queue", type=Path)
    group_regress.add_argument("--json", action="store_true")
    group_duel = group_sub.add_parser("duel", help="after `install` of the mod that owns the hulls: play the rig-only duel missions (SEEKER's Bone-Breaker against Betelgeuse, and two vanilla Onslaughts as the baseline) unattended and report the frame cost of a destruction; leave the mouse and keyboard alone")
    group_duel.add_argument("test_id", help="log name: writes <rig>/logs/<TESTID>.stdout.log")
    group_duel.add_argument("--bat", default="run-j25-direct.bat")
    group_duel.add_argument("--only", action="append", default=[], choices=["seeker", "baseline", "overwhelm"], help="play just this duel (repeatable)")
    group_duel.add_argument("--rig", type=Path)
    group_duel.add_argument("--queue", type=Path)
    group_duel.add_argument("--json", action="store_true")
    group_report_cmd = group_sub.add_parser("report", help="per-mod verdicts for a group's run log")
    group_report_cmd.add_argument("log", type=Path, help="the run's stdout log (bf-test launch) or the rig's starsector.log")
    group_report_cmd.add_argument("--rig", type=Path)
    group_report_cmd.add_argument("--queue", type=Path)
    group_report_cmd.add_argument("--json", action="store_true")
    corpus_recheck_cmd = subcommands.add_parser("corpus-recheck", help="re-scan every mod with real revival work recorded (ROADMAP P14 item 32): finding counts, compile signal and declared status in one roll-up")
    corpus_recheck_cmd.add_argument("--repo-root", type=Path, default=Path("."), help="repo root holding In operation/ (default: cwd)")
    corpus_recheck_cmd.add_argument("--vanilla-core", type=Path, help="read-only starsector-core; without it, most checks return UNKNOWN and no compile signal is produced")
    corpus_recheck_cmd.add_argument("--write-markdown", type=Path, help="also write a roll-up table to this path")
    corpus_recheck_cmd.add_argument("--include-intake", action="store_true", help="also include mods with a working/ copy but no REVIVAL_REPORT.md yet (ROADMAP P14 item 8: the Ironclads intake queue)")
    corpus_recheck_cmd.add_argument("--restart", action="store_true", help="ignore an interrupted run's In operation/CORPUS_RECHECK.partial.jsonl and rescan everything")
    corpus_recheck_cmd.add_argument("--quiet", action="store_true", help="no per-mod progress lines on stderr")
    corpus_recheck_cmd.add_argument("--json", action="store_true")
    sibling_cmd = subcommands.add_parser("sibling-assets", help="fill missing sprites and description rows from sibling mods of the same pack, only when every copy is byte-identical (ROADMAP 60c); dry run unless --apply; copies are recorded for audit-explain --auto")
    sibling_cmd.add_argument("workspace", type=Path, help="a workspace folder (In operation/<Mod>)")
    sibling_cmd.add_argument("--vanilla-core", type=Path, help="read-only starsector-core, so vanilla files are not reported missing")
    sibling_cmd.add_argument("--siblings", type=Path, nargs="*", help="mod roots to search instead of the other workspaces beside this one")
    sibling_cmd.add_argument("--apply", action="store_true", help="write the copies (default: report only)")
    sibling_cmd.add_argument("--json", action="store_true")
    vendor_copy_cmd = subcommands.add_parser("vendor-copy", help="copy a piece of a provider mod into another mod instead of reviving or depending on the whole provider (ROADMAP P14 item 4): one hullmod by id, or with --plan everything a vendor-plan lists (P15 item 7)")
    vendor_copy_cmd.add_argument("kind", nargs="?", choices=["hullmod"], help="only 'hullmod' is supported without --plan (see the command's own help for why)")
    vendor_copy_cmd.add_argument("id", nargs="?", help="the hullmod id to vendor")
    vendor_copy_cmd.add_argument("from_provider", nargs="?", type=Path, help="the mod folder to copy from")
    vendor_copy_cmd.add_argument("to_mod", nargs="?", type=Path, help="the mod folder to copy into")
    vendor_copy_cmd.add_argument("--plan", type=Path, help="a `vendor-plan --json` file: copy its whole closure (files and CSV rows), re-checked against the provider; any kind vendor-plan traces")
    vendor_copy_cmd.add_argument("--to", type=Path, help="with --plan: the mod folder or workspace to copy into")
    vendor_copy_cmd.add_argument("--allow-partial", action="store_true", help="with --plan: copy even though the plan has MISSING/SUSPECT entries or compiled-only classes (they are reported, not copied)")
    vendor_copy_cmd.add_argument("--policy", type=Path, help="licence policy JSON (default: bundled release_policy.json)")
    vendor_copy_cmd.add_argument("--apply", action="store_true", help="actually write the files (default: dry-run plan only)")
    vendor_copy_cmd.add_argument("--json", action="store_true")
    revival_report_draft_cmd = subcommands.add_parser("revival-report-draft", help="draft REVIVAL_REPORT.md/REVIVAL_PLAN.md from real scan+compile evidence for a mod with 0 MANUAL findings and a clean compile (ROADMAP P14 item 35); refuses otherwise")
    revival_report_draft_cmd.add_argument("mod", type=Path, help="mod working copy")
    revival_report_draft_cmd.add_argument("--vanilla-core", type=Path, help="read-only starsector-core; required to establish a compile signal")
    revival_report_draft_cmd.add_argument("--providers", type=Path, action="append", default=[], help="mods folder, mod folder or In operation tree to search for a declared dependency; repeatable")
    revival_report_draft_cmd.add_argument("--apply", action="store_true", help="write reports/REVIVAL_REPORT.md and REVIVAL_PLAN.md (default: print the draft only)")
    revival_report_draft_cmd.add_argument("--force", action="store_true", help="with --apply, overwrite an existing report/plan")
    revival_report_draft_cmd.add_argument("--json", action="store_true")
    diff_data_cmd = subcommands.add_parser("diff-data", help="compare two Starsector data files (JSON dialect or CSV) by value: key/row/column order, comments and formatting never count; exit 1 when they differ")
    diff_data_cmd.add_argument("a", type=Path, help="first file (e.g. the mod's copy)")
    diff_data_cmd.add_argument("b", type=Path, help="second file (e.g. vanilla's or a reference install's)")
    diff_data_cmd.add_argument("--json", action="store_true")
    rebuild_ref_cmd = subcommands.add_parser("rebuild-from-reference", help="port a mod's edited copies of vanilla files (.ship/.wpn/.variant/.skin/.system) to RC8: three-way merge of the reference install's vanilla file, the mod's copy and RC8's file; RC8's changes kept, only the mod's edits applied, overlaps reported as conflicts")
    rebuild_ref_cmd.add_argument("mod", type=Path, help="mod folder (holding data/)")
    rebuild_ref_cmd.add_argument("--reference-core", type=Path, required=True, help="starsector-core of the install the mod was made for (read-only)")
    rebuild_ref_cmd.add_argument("--vanilla-core", type=Path, required=True, help="RC8 starsector-core (read-only)")
    rebuild_ref_cmd.add_argument("--class", dest="file_classes", action="append", help="limit to one file class, e.g. --class wpn; repeatable (default: all), so a large mod can be rebuilt in reviewable stages")
    rebuild_ref_cmd.add_argument("--output", type=Path, help="write MERGED files here, mirroring data/ paths (never into the mod or either core)")
    rebuild_ref_cmd.add_argument("--json", action="store_true")
    corpus_index_cmd = subcommands.add_parser("corpus-index", help="index a large mod archive once (inside .zip files too) and search it like grep in milliseconds; reports what it could not read so \"no hits\" means something")
    corpus_index_sub = corpus_index_cmd.add_subparsers(dest="corpus_index_command", required=True)
    corpus_build_cmd = corpus_index_sub.add_parser("build", help="index (or refresh) every file under ROOT; unchanged files are skipped on re-runs")
    corpus_build_cmd.add_argument("root", type=Path, help="folder to index, e.g. Downloads")
    corpus_build_cmd.add_argument("--db", type=Path, default=Path("bridgeforge-state") / "corpus-index.sqlite", help="index file (default: bridgeforge-state/corpus-index.sqlite)")
    corpus_build_cmd.add_argument("--max-bytes", type=int, default=4 * 1024 * 1024, help="skip (and report) text files larger than this")
    corpus_build_cmd.add_argument("--quiet", action="store_true", help="no per-file progress lines on stderr")
    corpus_build_cmd.add_argument("--json", action="store_true")
    corpus_search_cmd = corpus_index_sub.add_parser("search", help="find files whose content (3+ characters, case-insensitive) or path contains TEXT")
    corpus_search_cmd.add_argument("text")
    corpus_search_cmd.add_argument("--db", type=Path, default=Path("bridgeforge-state") / "corpus-index.sqlite")
    corpus_search_cmd.add_argument("--names", action="store_true", help="match file paths only")
    corpus_search_cmd.add_argument("--limit", type=int, default=50)
    corpus_search_cmd.add_argument("--json", action="store_true")
    content_diff_cmd = subcommands.add_parser("content-diff", help="list hull/variant/weapon/wing/hullmod/shipsystem ids an older install defined that RC8 no longer does, with same-named RC8 candidates; feed the catalogue to `scan --removed-content`")
    content_diff_cmd.add_argument("reference_core", type=Path, help="starsector-core of the older install (read-only)")
    content_diff_cmd.add_argument("vanilla_core", type=Path, help="RC8 starsector-core (read-only)")
    content_diff_cmd.add_argument("--output", type=Path, help="write the JSON catalogue here")
    content_diff_cmd.add_argument("--json", action="store_true")
    verify_shadow_cmd = subcommands.add_parser("verify-shadow", help="does a jar set really compile the class a loose script defines? Parses class files (never a path check); use before dropping or editing a script as 'jar-shadowed'")
    verify_shadow_cmd.add_argument("scripts", type=Path, nargs="+", help="loose .java file(s)")
    verify_shadow_cmd.add_argument("--against", type=Path, action="append", required=True, help="a jar, a mod folder (its declared jars) or any folder (every jar under it, e.g. starsector-core); repeatable")
    verify_shadow_cmd.add_argument("--json", action="store_true")
    vendor_cmd = subcommands.add_parser("vendor-plan", help="trace the closure of one piece of an abandoned mod (hull mod, weapon, wing, hull, variant, ship system) for folding into RevenantLib: files to include, SUSPECT files that mention it but nothing references, what is missing, licence; copies nothing")
    vendor_cmd.add_argument("provider", type=Path, help="the mod that defines the piece (mod folder or workspace)")
    vendor_cmd.add_argument("--id", dest="ids", action="append", required=True, help="kind:id, e.g. hullmod:shields_formshield; repeatable")
    vendor_cmd.add_argument("--target", type=Path, help="RevenantLib folder or workspace, to report ids it already has and file collisions (default: <repo>/In operation/RevenantLib when present)")
    vendor_cmd.add_argument("--vanilla-core", type=Path, help="read-only starsector-core, so references vanilla provides are not traced")
    vendor_cmd.add_argument("--json", action="store_true")
    policy_cmd = subcommands.add_parser("release-policy", help="show or record a mod's publishing decision in release_policy.json (read by the release gate and dependency-substitutes)")
    policy_sub = policy_cmd.add_subparsers(dest="policy_command", required=True)
    policy_show = policy_sub.add_parser("show", help="the recorded decision for a mod id or name")
    policy_show.add_argument("mod")
    policy_set = policy_sub.add_parser("set", help="record a decision (updates an existing entry in place)")
    policy_set.add_argument("mod")
    policy_choice = policy_set.add_mutually_exclusive_group(required=True)
    policy_choice.add_argument("--local-only", action="store_true", help="may be used locally, not published")
    policy_choice.add_argument("--releasable", action="store_true", help="may be published")
    policy_set.add_argument("--reason", required=True, help="the evidence the decision rests on (licence file, forum post, owner decision and date)")
    policy_set.add_argument("--on", help="decision date (default: today)")
    for command in (policy_show, policy_set):
        command.add_argument("--policy", type=Path, help=argparse.SUPPRESS)
    rq_cmd = subcommands.add_parser("revive-queue", help="run revive across a queue: all workspaces, those never revived, or those with a given last status; progress lines, resumable, writes REVIVE_QUEUE.json")
    rq_cmd.add_argument("queue", type=Path)
    rq_cmd.add_argument("--only-status", action="append", default=[], metavar="STATUS", help="only workspaces whose last revive status is this (e.g. ESCALATED); repeatable")
    rq_cmd.add_argument("--never-revived", action="store_true", help="only workspaces with no REVIVE.json yet")
    rq_cmd.add_argument("--apply", action="store_true")
    rq_cmd.add_argument("--draft-report", action="store_true")
    rq_cmd.add_argument("--vanilla-core", type=Path)
    rq_cmd.add_argument("--restart", action="store_true", help="ignore an earlier run's checkpoint")
    rq_cmd.add_argument("--jobs", type=int, default=1, help="workspaces revived side by side (each writes only its own workspace; default 1)")
    rq_cmd.add_argument("--quiet", action="store_true", help="no per-workspace progress lines on stderr")
    rq_cmd.add_argument("--json", action="store_true")
    revive_cmd = subcommands.add_parser("revive", help="run the mechanical part of a revival unattended (scan, permitted fixers, rescan, until nothing changes) and write escalation packets for the rest (roadmap P15 item 2)")
    revive_cmd.add_argument("workspace", type=Path, help="a workspace folder holding working/mod_info.json")
    revive_cmd.add_argument("--apply", action="store_true", help="write fixes into working/ (default: dry run; reports and packets are still written)")
    revive_cmd.add_argument("--approve", action="append", default=[], metavar="FINDING_ID", help="approve this fixer for this run even though its findings are not all SAFE; repeatable")
    revive_cmd.add_argument("--policy", type=Path, help="standing fixer approvals (default: AUTOMATION_POLICY.json in the workspace's parent folder)")
    revive_cmd.add_argument("--vanilla-core", type=Path, help="RC8 starsector-core: enables the loose-script compile check and the fixers that compare against vanilla")
    revive_cmd.add_argument("--target", default="0.98a-RC8", help="target game version for mod_info.json (default: 0.98a-RC8)")
    revive_cmd.add_argument("--max-rounds", type=int, default=5)
    revive_cmd.add_argument("--providers", type=Path, action="append", default=[], help="where to look for mods that provide missing content, for the options in missing-content packets (default: the workspace's queue folder and its _rig/mods); repeatable")
    revive_cmd.add_argument("--provider-index", type=Path, help="saved `provider-index build` output, as for dependency-substitutes")
    revive_cmd.add_argument("--draft-report", action="store_true", help="when the run ends UNATTENDED_DONE, draft REVIVAL_REPORT.md/REVIVAL_PLAN.md with revival-report-draft (written only with --apply, never over an existing report; needs --vanilla-core for its compile check)")
    revive_cmd.add_argument("--json", action="store_true")
    esc_cmd = subcommands.add_parser("escalation", help="list, show, verify or run the escalation packets revive wrote (roadmap P15 item 3)")
    esc_sub = esc_cmd.add_subparsers(dest="escalation_command", required=True)
    esc_list = esc_sub.add_parser("list", help="the workspace's packets")
    esc_show = esc_sub.add_parser("show", help="print a packet as its agent prompt or owner question")
    esc_verify = esc_sub.add_parser("verify", help="rescan and say whether the packet's finding is gone with no new actionable findings")
    esc_verify.add_argument("--working", type=Path, help="check this copy instead of <workspace>/working (an agent's sandbox)")
    esc_run = esc_sub.add_parser("run", help="run an AI agent on a packet in a throwaway copy; only a verified result is kept")
    esc_run.add_argument("--agent", required=True, help='the agent command; it gets the packet on stdin and BF_PACKET/BF_PROMPT/BF_NOTE/BF_WORKING in its environment, e.g. "claude -p --permission-mode acceptEdits"')
    esc_run.add_argument("--apply", action="store_true", help="copy a verified result into working/ (backups kept)")
    esc_run.add_argument("--retries", type=int, default=1, help="re-runs after a failed attempt, with the failure appended (default 1)")
    esc_run.add_argument("--timeout", type=int, default=1800, help="seconds per attempt")
    esc_apply = esc_sub.add_parser("apply", help="copy an attempt already VERIFIED (and reviewed) into working/, without re-running the agent")
    esc_apply.add_argument("--attempt", type=int, help="which attempt (default: the newest VERIFIED one)")
    esc_apply.add_argument("--patch-class", action="store_true", help="the attempt edits jar sources: patch just the edited classes into their jar (patch-jar-class checks) and copy the sources back")
    esc_apply.add_argument("--allow-removed", action="append", default=[], help="with --patch-class: a member whose removal is intended (fields moved to per-ship state); repeatable")
    esc_apply.add_argument("--rebuild-jar", action="store_true", help="the attempt edits jar sources: rebuild the jar from them (refused on any lost class or member) and install it")
    esc_rule = esc_sub.add_parser("rule", help="record one owner ruling for a finding id across the queue: accept it in every escalated mod's baseline, or approve its fixer as a standing approval")
    esc_rule.add_argument("finding")
    esc_rule.add_argument("queue", type=Path)
    esc_rule.add_argument("--accept", action="store_true")
    esc_rule.add_argument("--approve-fixer", action="store_true")
    esc_rule.add_argument("--reason", required=True)
    esc_rule.add_argument("--json", action="store_true")
    esc_accept = esc_sub.add_parser("accept", help="accept one mod's findings as authored: add them to its baseline and the reason (the evidence) to reports/ESCALATION_REVIEW.md")
    esc_accept.add_argument("workspace", type=Path)
    esc_accept.add_argument("selectors", nargs="+", help="FINDING_ID or FINDING_ID:FILE_PART (a substring of the finding's file)")
    esc_accept.add_argument("--reason", required=True, help="why it is right as written, with the evidence")
    esc_accept.add_argument("--json", action="store_true")
    esc_queue = esc_sub.add_parser("queue",help="across a queue: which findings block the ESCALATED mods, and which mods one decision would clear; writes ESCALATIONS_BY_FINDING.md")
    esc_queue.add_argument("queue", type=Path)
    esc_queue.add_argument("--quiet", action="store_true", help="no per-workspace progress lines on stderr")
    esc_queue.add_argument("--json", action="store_true")
    for command in (esc_list, esc_show, esc_verify, esc_run, esc_apply):
        command.add_argument("workspace", type=Path)
        command.add_argument("--json", action="store_true")
    for command in (esc_show, esc_verify, esc_run, esc_apply):
        command.add_argument("packet", nargs="?" if command is esc_run else None, help="packet id (see `escalation list`)")
    esc_run.add_argument("--all", action="store_true", help="run every agent packet in turn")
    esc_run.add_argument("--watch-dir", type=Path, action="append", default=[], help="a directory the agent must not touch (e.g. the session's memory folder); what changed in it is reported after the run; repeatable")
    esc_review = esc_sub.add_parser("review", help="write reports/ESCALATION_REVIEW_SHEET.md: each packet's newest attempt with its diff and flags for changes that need a human (removed hints, Random/save logic, loop rewrites, swallowed exceptions)")
    esc_review.add_argument("workspace", type=Path)
    esc_review.add_argument("--json", action="store_true")
    done_audit_cmd = subcommands.add_parser("done-audit", help="re-scan every archived revival in Done/: STALE when the queue copy changed since archiving, plus crash-class and MANUAL/UNKNOWN findings the baseline does not accept (writes Done/DONE_AUDIT.md)")
    done_audit_cmd.add_argument("--done", type=Path, help="default: <repo>/Done")
    done_audit_cmd.add_argument("--queue", type=Path, help="default: <repo>/In operation")
    done_audit_cmd.add_argument("--vanilla-core", type=Path)
    done_audit_cmd.add_argument("--quiet", action="store_true", help="no per-mod progress lines")
    done_audit_cmd.add_argument("--json", action="store_true")
    fold_cmd = subcommands.add_parser("fold", help="fold a discontinued library-like mod into a RevenantLib-shaped target directory (roadmap P14 item 10): copy it byte-for-byte, keeping its ids and class names, and record provenance plus a dependency_successors.json entry")
    fold_cmd.add_argument("source", type=Path, help="the library mod's own directory (holding mod_info.json), e.g. a working copy")
    fold_cmd.add_argument("target", type=Path, help="the RevenantLib-shaped target directory (holds/gets original/<source name>/ and reports/PROVENANCE.md)")
    fold_cmd.add_argument("--overwrite", action="store_true", help="allow folding into an existing original/<source name>/ (files that differ from the source are still never overwritten -- reported as conflicts instead)")
    fold_cmd.add_argument("--dry-run", action="store_true", help="report what would happen; write nothing")
    fold_cmd.add_argument("--successors-path", type=Path, help="dependency_successors.json to update (default: bridgeforge's own copy)")
    fold_cmd.add_argument("--json", action="store_true")
    return parser


def _reconfigure_streams_for_pipes(streams=None) -> list:
    """Switch stdout/stderr to UTF-8 (errors="replace") when they aren't an interactive console.

    Windows' default piped/redirected-output codepage (cp1252) corrupts the non-ASCII text several
    modules print (`--json` output built with `ensure_ascii=False`, translate-check's CJK strings,
    ...) -- `UnicodeEncodeError` piping `bridgeforge ... --json > out.json` on Windows (task A9).
    An interactive console is left exactly as the user configured it: this only touches a stream
    that exposes `TextIOWrapper.reconfigure` and whose `isatty()` returns false (a pipe or a
    redirected file) -- a real console's own encoding is never overridden. A stream with no
    `isatty` at all (unusual for real stdout/stderr, but true of some test doubles) is treated as
    non-interactive and reconfigured; one whose `isatty()` call itself raises is left untouched,
    since that failure means the stream's state can't be trusted either way. Returns the streams
    actually reconfigured, so this can be asserted on directly in a test.
    """
    reconfigured = []
    for stream in streams if streams is not None else (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        isatty = getattr(stream, "isatty", None)
        if isatty is not None:
            try:
                if isatty():
                    continue
            except (OSError, ValueError):
                continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            continue
        reconfigured.append(stream)
    return reconfigured


def main(argv: list[str] | None = None) -> int:
    if argv and argv[0] == "dependency-graph" and "--repo-root" in argv:
        argv = ["dependency-graph-local", *argv[1:]]
    if argv and argv[0] == "rebuild-from-reference" and "--current-core" in argv:
        argv = ["rebuild-from-reference-local", *argv[1:]]
    _reconfigure_streams_for_pipes()
    args = build_parser().parse_args(argv)
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
    if args.command == "dependency-substitutes":
        from .substitutes import REPO_ROOT, dependency_substitutes
        roots = args.providers or [REPO_ROOT / "In operation", REPO_ROOT / "In operation" / "_rig" / "mods"]
        result = dependency_substitutes(args.mod, roots, vanilla_core=args.vanilla_core, policy_path=args.policy, index_path=args.provider_index)
        if args.write:
            from .substitutes import write_dependency_report
            try:
                print(f"Recorded: {write_dependency_report(result, args.mod)}", file=sys.stderr)
            except ValueError as exc:
                print(f"bridgeforge: {exc}", file=sys.stderr)
                return 2
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        print(f"{result['mod_id']}: {result['strategy']} ({result['providers_indexed']} mods searched)")
        print(f"  {result['reason']}")
        for kind, ids in result["needed"].items():
            print(f"  needs {kind}: {', '.join(ids[:8])}{' ...' if len(ids) > 8 else ''}")
        if result["declared_dependencies_missing"]:
            print(f"  declared but not found: {', '.join(result['declared_dependencies_missing'])}")
        if result.get("total_conversions_excluded"):
            print(f"  not usable as providers (total conversions): {', '.join(result['total_conversions_excluded'])}")
        for item in result["provider_set"]:
            state = item.get("workspace")
            where = f"; workspace {state['workspace']}: {state['status'] or 'no revival report'}, {state['manual_findings'] if state['manual_findings'] is not None else '?'} MANUAL" if state else ""
            print(f"  provides {', '.join(item['covers'])}: {item['name']} ({item['game_version'] or 'no version'}{where})")
        if result["uncovered"]:
            print(f"  in no visible mod: {', '.join(result['uncovered'])}")
        for entry in result["successors"]:
            print(f"  known successor for {entry['match']}: {entry['successor']} [{entry.get('evidence', '')}]")
        for note in result.get("licence_notes") or []:
            print(f"  LICENCE: {note}")
        return 0
    if args.command == "provider-index":
        from .substitutes import REPO_ROOT, provider_index, save_provider_index
        roots = args.providers or [REPO_ROOT / "In operation", REPO_ROOT / "In operation" / "_rig" / "mods"]
        summary = save_provider_index(provider_index(roots), args.output, roots)
        print(f"Provider index: {summary['providers']} mods, {summary['ids']} ids -> {summary['output']}")
        return 0
    if args.command == "audit-shipped":
        from .live_trust import audit_shipped, live_status
        result = {"audit": audit_shipped(args.workspace), "live": live_status(args.workspace)}
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            audit = result["audit"]
            print(f"Shipped-copy audit: {audit['status']}" + (f" ({audit['reason']})" if audit.get("reason") else ""))
            for row in audit.get("differences") or []:
                print(f"  {row['kind']:<8} {row['file']}: {row['explained_by'] or 'UNEXPLAINED'}")
            live = result["live"]
            print(f"Live result: {live['status']}" + (f" (last PASS {live['test_id']}, {live.get('date')})" if live.get("test_id") else ""))
        return 0 if result["audit"]["status"] == "PASS" else 1
    if args.command == "audit-explain":
        from .live_trust import auto_explain_shipped, explain_shipped
        if args.auto:
            groups = auto_explain_shipped(args.workspace)
            if args.json:
                print(json.dumps(groups, indent=2))
            else:
                for reason, files in groups.items():
                    print(f"{len(files)} file(s): {reason}")
                print("Nothing could be proven; explain the rest with --reason." if not groups else "Anything still unexplained needs --reason.")
            return 0
        if not args.reason:
            print("bridgeforge: --reason is required (or pass --auto).", file=sys.stderr)
            return 2
        try:
            path = explain_shipped(args.workspace, args.files, args.reason, live=args.live)
        except (ValueError, OSError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        print(json.dumps({"written": str(path)}) if args.json else f"Recorded in {path}.")
        return 0
    if args.command == "archive":
        from .archive import ArchiveError, archive_mod
        from .substitutes import REPO_ROOT
        from .explain_proofs import prepare_for_audit
        from .live_trust import archive_gate
        prepare_for_audit(args.workspace)  # extract a zip original, copy translation records (copy-only steps, ROADMAP 60b)
        gate = archive_gate(args.workspace)
        if not gate["allowed"]:
            # ROADMAP 36.11: no archive for an unaudited or stale-tested mod unless the owner recorded why.
            print("bridgeforge: archive refused: " + "; ".join(gate["problems"]), file=sys.stderr)
            print(f'  explain with: bridgeforge audit-explain "{args.workspace}" FILE... --reason "..." (or --live --reason for the live result)', file=sys.stderr)
            return 2
        try:
            result = archive_mod(args.workspace, args.done or REPO_ROOT / "Done", policy_path=args.policy, refresh=args.refresh)
            if args.readme_copy:
                from .archive import write_readme_copies
                result["readme_copies"] = write_readme_copies(Path(result["archive"]))
        except (ArchiveError, OSError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"Archived: {result['archive']} ({result['files']} files, {result['licence']}, status {result['status']})")
            print(f"  {len(result['changed'])} file(s) changed, {len(result['added'])} added vs original; jars identical: {result['jars_identical']}")
            print(f"  Note: {result['note']}. The workspace is untouched; remove it yourself once the archive is checked.")
        return 0
    if args.command == "relink":
        from .jar_batch import relink_queue, relink_workspace
        path = args.path.expanduser().resolve()
        if (path / "working" / "mod_info.json").is_file():
            result = relink_workspace(path, args.vanilla_core, apply=args.apply)
            rows = [result]
        else:
            result = relink_queue(path, args.vanilla_core, apply=args.apply, quiet=args.quiet, restart=args.restart)
            rows = result["workspaces"]
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        for row in rows:
            print(f"{row['state']:13} {row['workspace']}" + "".join(f"\n  {j['jar']}: {j['state']} ({j['classes']} class(es))" for j in row.get("jars") or [])
                  + (f"\n  no source: {', '.join(row['missing_source'])}" if row.get("missing_source") else "")
                  + (f"\n  removed in RC8: {', '.join(row['port'])}" if row.get("port") else ""))
        if "counts" in result:
            print("counts: " + ", ".join(f"{k} {v}" for k, v in sorted(result["counts"].items())))
        return 0
    if args.command == "bump-version":
        from .workspace_tools import bump_version
        try:
            result = bump_version(args.workspace, args.note, day=args.date)
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        print(f"{result['old']} -> {result['new']}\n  {result['changelog']}")
        return 0
    if args.command == "declare-providers":
        from .workspace_tools import declare_providers
        for workspace in args.workspace:
            result = declare_providers(workspace, apply=args.apply)
            print(f"{result['state']:16} {result['workspace']}: " + (", ".join(result["declared"]) or str(result.get("strategy") or "")))
        return 0
    if args.command == "close":
        from .workspace_tools import close_workspace
        print(f"{args.status}: {close_workspace(args.workspace, args.status, args.reason)}")
        return 0
    if args.command == "restore-from-done":
        from .workspace_tools import restore_from_done
        try:
            result = restore_from_done(args.archive, args.queue or Path(__file__).resolve().parent.parent / "In operation")
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        print(f"restored {result['workspace']} (reports: {', '.join(result['restored_reports']) or 'none'})" + (f"\n  NOTE: {result['note']}" if result["note"] else ""))
        return 0
    if args.command == "revive-review":
        from .workspace_tools import review_applied
        result = review_applied(args.queue, args.since)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        print(f"{result['applied']} applied fix(es) since {args.since}; {len(result['flagged'])} flagged")
        for row in result["flagged"]:
            print(f"  {row['workspace']}: {row['finding']} {row['file']}: {', '.join(row['flags'])}")
        return 0
    if args.command == "mod-changelog":
        from .mod_changelog import DEFAULT_PATH, add_entry, seed_from_archives
        if args.modlog_command == "add":
            print(add_entry(args.mod, args.text, version=args.version, day=args.date, path=args.file))
        else:
            done_dir = args.done or Path(__file__).resolve().parent.parent / "Done"
            print(f"{seed_from_archives(done_dir, args.file or DEFAULT_PATH)} line(s) added to {args.file or DEFAULT_PATH}")
        return 0
    if args.command == "ready-list":
        # Replaces the hand tally of "how many need live testing" (2026-09-30).
        from .probe_group import ProbeGroupError, ready_workspaces
        try:
            ready = ready_workspaces(args.queue)
        except ProbeGroupError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        rows = []
        for workspace in ready:
            revive_record = workspace / "reports" / "revive" / "REVIVE.json"
            compiled = json.loads(revive_record.read_text(encoding="utf-8")).get("compile_checked") if revive_record.is_file() else None
            rows.append({"workspace": workspace.name, "compile_checked": compiled})
        if args.json:
            print(json.dumps({"ready": rows, "count": len(rows)}, indent=2))
            return 0
        print(f"{len(rows)} mod(s) ready for live testing:")
        for row in rows:
            print(f"  {row['workspace']}" + ("" if row["compile_checked"] else "  (revive did not compile-check it)"))
        if rows:
            print(f'Next: bridgeforge probe-group plan "{args.queue}", then install a group and `.\\tools\\bf-test.ps1 launch <TESTID>`.')
        return 0
    if args.command == "probe-group":
        from .probe_group import ProbeGroupError, group_report, install_group, plan_groups
        from .probe_config import CONFIG_FILE
        from .substitutes import REPO_ROOT
        queue = (args.queue or REPO_ROOT / "In operation").expanduser().resolve()
        rig = (args.rig or queue / "_rig").expanduser().resolve()
        try:
            if args.probe_group_command == "plan":
                from .probe_group import DEFAULT_PROVIDER_SOURCES
                sources = args.provider_source if args.provider_source is not None else [p for p in DEFAULT_PROVIDER_SOURCES if p.is_dir()]
                from .probe_group import ready_workspaces
                retest = [Path(queue) / name for name in args.retest]
                missing = [str(p) for p in retest if not (p / "working" / "mod_info.json").is_file()]
                if missing:
                    raise ProbeGroupError("--retest needs a workspace with working/mod_info.json: " + ", ".join(missing))
                result = plan_groups(queue, rig, size=args.size, exclude=set(args.exclude), solo=set(args.solo) | set(args.retest), auto_solo=not args.no_auto_solo,
                                     extra_sources=sources, workspaces=[*ready_workspaces(queue), *[p for p in retest if p not in ready_workspaces(queue)]])
                target = args.write or queue / "PROBE_GROUPS.json"
                target.write_text(json.dumps(result, indent=2), encoding="utf-8")
                if not args.json:
                    for group in result["groups"]:
                        print(f"Group {group['group']} ({len(group['members'])} mod(s)): " + ", ".join(m["workspace"] for m in group["members"]))
                    for item in result.get("raw_folders") or []:
                        print(f"Not taken in: {item['folder']} is a raw mod folder, no workspace yet. Run: {item['next']}")
                    for item in result["unplaced"]:
                        print(f"Not grouped: {item['workspace']} - {item['reason']}")
                        for problem in item.get("providers") or []:
                            print(f"    {problem}")
                    staging = sorted({f"{p['mod_id']} from {p.get('source') or p['workspace']}" for g in result["groups"] for m in g["members"] for p in m.get("stage_providers") or []})
                    if staging:
                        print("Providers to stage (install those groups with --stage-providers): " + "; ".join(staging))
                    print(f"Plan written: {target}. Next: bridgeforge probe-group install <N>, then bf-test.ps1 launch <TESTID>.")
            elif args.probe_group_command == "install":
                plan = json.loads((args.plan or queue / "PROBE_GROUPS.json").read_text(encoding="utf-8"))
                result = install_group(plan, args.group, queue, rig, stage=args.stage_providers, with_lunalib=args.with_lunalib,
                                       setups=args.setup, expect_supply=args.expect_supply, save_after_checks=args.save_after_checks,
                                       no_lunalib=args.no_lunalib, also_enable=args.also_enable)
                if not args.json:
                    print(f"Group {result['group']} installed: {', '.join(result['members'])}")
                    for item in result["staged_providers"]:
                        print(f"  provider {item['mod_id']} {item['version']} from {item['workspace']}: {item['action']} (id, version and files verified)")
                    for item in result["copied"]:
                        print(f"  {item['workspace']}: {item['action']}")
                    print(f"  enabled_mods.json -> {result['enabled_mods']}")
                    for folder in result.get("probe_mission_added", []):
                        print(f"  added the probe mission to {folder}'s mission list (it replaces the list; RC8 would hide the probe)")
                    for item in result.get("moved_aside", []):
                        print(f"  moved {item['folder']} to mods-disabled-providers: it shares mod id {item['mod_id']} with {item['kept']}")
                    for item in result.get("incomplete_providers", []):
                        print(f"  WARN {item['folder']} lacks {', '.join(item['missing'])} that the real install has; recopy it")
                    for item in result.get("dependency_version_conflicts", []):
                        print(f"  WARN {item['mod_id']} wants {item['dependency']} {item['wanted']}, rig has {item['installed']}: "
                              "RC8 disables a mod whose dependency major differs (RC8-23); fix its mod_info.json")
                    if result.get("lunalib"):
                        print(f"  LunaLib: {result['lunalib']}")
                    if result.get("lunalib_advice"):
                        print(f"  WARN {result['lunalib_advice']}")
                    print(f"  probe will check {result['checked_ids']} content id(s). New Game, wait one in-game day, quit, then probe-group report <log>.")
            elif args.probe_group_command == "live":
                from .live_run import live_run
                print("Starting the live run: leave the mouse and keyboard alone until it finishes (about three minutes after loading).", file=sys.stderr)
                live = live_run(rig, args.test_id, bat_name=args.bat, menu_timeout=args.menu_timeout)
                result = {"verdict": live.verdict, "stage": live.stage, "detail": live.detail, "rounds": live.rounds, "stages": live.stages, "log": live.log}
                if not args.json:
                    print(f"{live.verdict}: stages {', '.join(live.stages) or 'none'}; combat rounds {live.rounds}")
                    if live.verdict != "LIVE_DONE":
                        print(f"  stuck at {live.stage}: {live.detail}")
                    else:
                        print(f"  Next: bridgeforge probe-group report \"{live.log}\", then record --archive.")
                if live.verdict != "LIVE_DONE":
                    if args.json:
                        print(json.dumps(result, indent=2, ensure_ascii=False))
                    return 1
            elif args.probe_group_command == "regress":
                from datetime import date as _date

                from .regress import rejudge, run_regression
                out = args.out or Path(queue) / "_regress" / f"regress-{_date.today():%Y%m%d}.json"
                if args.rejudge:
                    out = args.out or Path(queue) / "_regress" / f"rejudged-{_date.today():%Y%m%d}.json"
                    result = rejudge(queue, rig, args.rejudge, out)
                else:
                    print("Starting the regression pass: leave the mouse and keyboard alone until it finishes (about five minutes a group).", file=sys.stderr)
                    result = run_regression(queue, rig, out, bat=args.bat, size=args.size, limit=args.limit, only=args.only or None,
                                        quiet=args.quiet, test_prefix=args.test_prefix)
                if not args.json:
                    print(f"{len(result['groups'])} group(s); {len(result['attention'])} item(s) need a look; summary {out}")
                    for item in result["attention"]:
                        print(f"  group {item['group']}: {item.get('mod') or item.get('members')}: {item['why']}")
            elif args.probe_group_command == "duel":
                from .duel_run import run_duel
                print("Starting the duel run: leave the mouse and keyboard alone until it finishes (about ten minutes).", file=sys.stderr)
                result = run_duel(rig, args.test_id, bat_name=args.bat, only=tuple(args.only) or None)
                if not args.json:
                    print(f"played: {', '.join(result['played']) or 'none'}" + (f"; PROBLEM: {result['problem']}" if result["problem"] else ""))
                    for label, row in result["summary"].items():
                        print(f"  {label}: fight lasted {row['fight_game_seconds']} game s / {row['fight_real_seconds']} real s before the first kill; avg frame {row['avg_ms_before']} ms before the first destruction, {row['avg_ms_after']} ms after; worst frame {row['worst_frame_ms']} ms "
                              f"(worst in the 4 s after a destruction {row['worst_after_destruction_ms']} ms); peak hulks {row['peak_hulks']}, ships {row['peak_ships']}, projectiles {row['peak_projectiles']}")
                    print(f"  log {result['log']}")
                if result["problem"]:
                    if args.json:
                        print(json.dumps(result, indent=2, ensure_ascii=False))
                    return 1
            elif args.probe_group_command == "smoke":
                from .probe_group import smoke_group
                result = smoke_group(rig, bat_name=args.bat, timeout=args.timeout, log_name=args.log_name)
                if not args.json:
                    boot = result["boot"]
                    print(f"{result['verdict']}: {boot['status']} in {boot['elapsed_seconds'] or 0:.0f}s; FATAL={result['fatal']} MOD-ERROR={result['mod_errors']}; log {boot['log']}")
                    if boot["status"] != "PASS":
                        print(f"  {boot['reason']}")
                    for line in result["load_errors"]:
                        print(f"  load error: {line}")
                    print("  Startup only: New Game generation and combat still need the real run.")
                if result["verdict"] != "SMOKE_PASS":
                    if args.json:
                        print(json.dumps(result, indent=2, ensure_ascii=False))
                    return 1
            elif args.probe_group_command == "bisect":
                from .probe_group import bisect_group
                plan_path = args.plan or queue / "PROBE_GROUPS.json"
                result = bisect_group(json.loads(plan_path.read_text(encoding="utf-8")), args.group)
                atomic_write_text(plan_path, json.dumps(result, indent=2))
                if not args.json:
                    for group in result["groups"][-2:]:
                        print(f"Group {group['group']} ({len(group['members'])} mod(s)): " + ", ".join(m["workspace"] for m in group["members"]))
                    print(f"Plan updated: {plan_path}. Install and run each half.")
            elif args.probe_group_command == "record":
                from .probe_group import record_group
                config = json.loads((rig / "saves" / "common" / CONFIG_FILE).read_text(encoding="utf-8"))
                result = record_group(rig / "logs" / f"{args.test_id}.stdout.log", config, queue, rig, test_id=args.test_id, archive=args.archive, refresh=args.refresh)
                if not args.json:
                    print(f"Recorded LIVE_VALIDATED ({result['probe_version']}): {', '.join(result['recorded']) or 'none'}")
                    if args.archive:
                        print(f"Archived to Done/: {', '.join(result['archived']) or 'none'}")
                    for item in result["skipped"]:
                        print(f"  not recorded: {item['mod_id']} ({item['verdict']}) {item.get('archive', '')}")
            else:
                config = json.loads((rig / "saves" / "common" / CONFIG_FILE).read_text(encoding="utf-8"))
                from .probe_group import accepted_probe_findings
                result = group_report(args.log, config, mods_dir=rig / "mods", accepted=accepted_probe_findings(queue, rig / "mods"))
                if not args.json:
                    print(f"FATAL={result['fatal']} MOD-ERROR={result['mod_errors']}; content-ids ran: {result['content_ids_ran']}")
                    for mod_id, verdict in sorted(result["members"].items()):
                        print(f"  {verdict['verdict']:<10} {mod_id}")
                        for item in verdict["failures"] + verdict["crashes"]:
                            print(f"      {item}")
                        for item in verdict.get("accepted", []):
                            print(f"      (accepted, not a failure) {item}")
                    for item in result["unattributed"]:
                        print(f"  (group) {item}")
                    if result.get("combat_filler_sides"):
                        print(f"  combat: vanilla filler ships stood in for side(s) {', '.join(result['combat_filler_sides'])} (the group had no mod ships there)")
        except (ProbeGroupError, ProbeConfigError, OSError, ValueError, StopIteration) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    if args.command == "supersession":
        from .supersession import find_superseded
        result = find_superseded(args.queue, args.against, quiet=args.quiet, corpus_index=args.corpus_index)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        for record in result["mods"]:
            if record["verdict"] in ("SUPERSEDED", "SAME_RELEASE", "NEWER_ELSEWHERE", "NEWER_DIFFERENT"):
                ref = record["reference"]
                renamed = f" [named '{ref['name']}' there]" if ref.get("name") and ref["name"].strip().lower() != record["name"].strip().lower() else ""
                print(f"{record['verdict']:16} {record['workspace']}: ours {record['version']}, theirs {ref['version']} ({ref['game_version'] or 'no gameVersion'}) at {ref['path']}{renamed}")
                if record["verdict"] == "NEWER_DIFFERENT":
                    print(f"                 {record['note']}")
        print("Counts: " + ", ".join(f"{k} {v}" for k, v in sorted(result["counts"].items())))
        print(f"Written: {result['result_path']}")
        return 0
    if args.command == "finding-stats":
        from .finding_stats import CHECKPOINT_NAME, FindingStatsError, finding_stats, render
        from .substitutes import REPO_ROOT
        checkpoint = args.write / CHECKPOINT_NAME if args.write and args.scan else None
        if checkpoint and args.restart and checkpoint.is_file():
            checkpoint.unlink()

        def progress(done: int, total: int, record: dict, seconds: float, resumed: bool) -> None:
            if "unscanned" in record:
                detail = f"not scanned ({record['unscanned']})"
            else:
                detail = f"{sum(record['tiers'].values())} finding(s), bucket {record['bucket']}"
                if record["blocking"]:
                    detail += f", blocked by {', '.join(record['blocking'][:3])}" + (" ..." if len(record["blocking"]) > 3 else "")
            print(f"[{done}/{total}] {record['workspace']}: {detail}" + (" (from checkpoint)" if resumed else f" ({seconds:.1f}s)"), file=sys.stderr, flush=True)

        try:
            stats = finding_stats(args.roots or [REPO_ROOT / "In operation"], scan=args.scan, vanilla_core=args.vanilla_core,
                                  checkpoint=checkpoint, progress=None if args.quiet else progress)
        except (FindingStatsError, OSError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if checkpoint and checkpoint.is_file():
            checkpoint.unlink()  # the run finished; FINDING_STATS.json now holds every record
        if args.write:
            args.write.mkdir(parents=True, exist_ok=True)
            from .finding_stats import delta, render_delta
            previous_path = args.write / "FINDING_STATS.json"
            try:
                previous = json.loads(previous_path.read_text(encoding="utf-8")) if previous_path.is_file() else None
            except (OSError, json.JSONDecodeError):
                previous = None  # an unreadable earlier run just means no comparison
            if previous is not None:
                previous_path.replace(args.write / "FINDING_STATS.previous.json")
            previous_path.write_text(json.dumps(stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            (args.write / "FINDING_STATS.md").write_text(render(stats) + (render_delta(delta(previous, stats)) if previous else ""), encoding="utf-8")
            print(f"Written: {args.write / 'FINDING_STATS.md'}", file=sys.stderr)
        print(json.dumps(stats, indent=2, ensure_ascii=False) if args.json else render(stats), end="\n" if args.json else "")
        return 0
    if args.command == "dependency-graph":
        from .substitutes import REPO_ROOT, dependency_graph
        queue = args.queue or REPO_ROOT / "In operation"
        roots = args.providers or [REPO_ROOT / "In operation", REPO_ROOT / "In operation" / "_rig" / "mods"]
        try:
            from .progress import report as print_progress
            checkpoint = Path(queue) / "DEPENDENCY_GRAPH.partial.jsonl" if args.write else None
            if checkpoint and args.restart and checkpoint.is_file():
                checkpoint.unlink()

            def graph_progress(done: int, total: int, name: str, report: dict, seconds: float | None) -> None:
                needs = [item["mod_id"] for item in report["provider_set"] if not item["targets_0.98a"]]
                print_progress(done, total, name, f"{report['strategy']}" + (f", needs {', '.join(needs)}" if needs else "")
                               + (f", {len(report['uncovered'])} unprovided" if report["uncovered"] else ""), seconds)

            result = dependency_graph(queue, roots, vanilla_core=args.vanilla_core, index_path=args.provider_index, write_reports=args.write,
                                      checkpoint=checkpoint, progress=None if args.quiet else graph_progress)
            if args.write:
                from .substitutes import write_dependency_graph
                for written in write_dependency_graph(result, queue):
                    print(f"Written: {written}", file=sys.stderr)
                if checkpoint.is_file():
                    checkpoint.unlink()
        except (ValueError, OSError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        print(f"{result['queued_mods']} queued mod(s) in {result['queue']}")
        for rank_number, entry in enumerate(result["revival_order"], 1):
            state = entry.get("workspace") or {}
            licence = (entry.get("licence") or {}).get("decision")
            print(f"{rank_number}. revive {entry['name']} ({entry['game_version'] or 'no version'}"
                  + (f", workspace {state['workspace']}: {state.get('manual_findings')} MANUAL" if state else ", not a workspace here")
                  + (f", licence {licence}" if licence else "") + f"): unblocks {len(entry['unblocks'])}: {', '.join(entry['unblocks'])}")
        for entry in result["unprovided"]:
            print(f"   {entry['workspace']}: no provider for {', '.join(entry['ids'][:6])}{' ...' if len(entry['ids']) > 6 else ''}")
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
                if args.archive.expanduser().is_dir():
                    from .intake import zip_raw_folder
                    args.archive = zip_raw_folder(args.archive, args.repo_root)
                    print(f"Zipped the raw folder to {args.archive}", file=sys.stderr)
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
    if args.command == "corpus-recheck":
        from .corpus_recheck import corpus_recheck, render_markdown
        from .progress import report as print_progress
        checkpoint = args.repo_root.expanduser().resolve() / "In operation" / "CORPUS_RECHECK.partial.jsonl"
        if args.restart and checkpoint.is_file():
            checkpoint.unlink()

        def recheck_progress(done: int, total: int, mod: dict, seconds: float | None) -> None:
            detail = f"ERROR {mod['error']}" if "error" in mod else ", ".join(f"{count} {name}" for name, count in sorted(mod["by_classification"].items())) or "no findings"
            print_progress(done, total, mod["mod"], detail, seconds)

        result = corpus_recheck(args.repo_root, args.vanilla_core, require_report=not args.include_intake,
                                checkpoint=checkpoint if checkpoint.parent.is_dir() else None,
                                progress=None if args.quiet else recheck_progress)
        if checkpoint.is_file():
            checkpoint.unlink()  # the run finished
        if args.write_markdown:
            args.write_markdown.parent.mkdir(parents=True, exist_ok=True)
            args.write_markdown.write_text(render_markdown(result), encoding="utf-8")
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"{result['status']}: {result['mod_count']} mod(s) with real revival work recorded")
            if result["regressions"]:
                print(f"  REGRESSION: {', '.join(result['regressions'])}")
            for mod in result["mods"]:
                if "error" in mod:
                    print(f"  ERROR {mod['mod']}: {mod['error']}")
                    continue
                manual = mod["by_classification"].get("MANUAL", 0)
                if manual:
                    print(f"  {mod['mod']}: {manual} MANUAL ({', '.join(mod['manual_ids'])})")
            if args.write_markdown:
                print(f"Roll-up written: {args.write_markdown}")
        return 1 if result["status"] == "REGRESSION" else 0
    if args.command == "sibling-assets":
        from .sibling_assets import SiblingAssetsError, fix_sibling_assets
        try:
            result = fix_sibling_assets(args.workspace, args.vanilla_core, apply=args.apply, roots=args.siblings or None)
        except (SiblingAssetsError, OSError, ValueError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            verb = "copied" if args.apply else "would copy"
            print(f"Searched {result['siblings_searched']} sibling root(s): {verb} {len(result['files'])} file(s) and {len(result['rows'])} description row(s).")
            for label in ("files_refused", "files_unresolved", "rows_refused", "rows_unresolved"):
                for item in result[label]:
                    print(f"  {label.replace('_', ' ')}: {item.get('path') or item.get('id')}: {item['reason']}")
        return 0
    if args.command == "vendor-copy" and args.plan is not None:
        from .vendor_plan import VendorPlanError, copy_plan
        if args.to is None or any(value is not None for value in (args.kind, args.id, args.from_provider, args.to_mod)):
            print("bridgeforge: with --plan, give only --to (the mod to copy into), no positional arguments", file=sys.stderr)
            return 2
        try:
            result = copy_plan(json.loads(args.plan.read_text(encoding="utf-8")), args.to, apply=args.apply,
                               allow_partial=args.allow_partial, policy_path=args.policy)
        except (VendorPlanError, OSError, json.JSONDecodeError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"{result['status']}" + (f": {result['reason']}" if result.get("reason") else ""))
            for label in ("files", "skipped_identical", "conflicts", "stale", "left_out"):
                for item in result.get(label) or []:
                    print(f"  {label.replace('_', ' ')}: {item}")
            for table, ids in (result.get("rows") or {}).items():
                print(f"  rows: {table} [{', '.join(ids)}]")
            for item in result.get("provenance") or []:
                print(f"  sha256 {item['sha256']}  {item['path']}")
            if result.get("must_stay_local_only"):
                print(f"  LICENCE: {result['licence_note']}")
        return 0 if result["status"] in ("PLANNED", "APPLIED") else 1
    if args.command == "vendor-copy":
        from .strip_plan import vendor_copy
        if None in (args.kind, args.id, args.from_provider, args.to_mod):
            print("bridgeforge: vendor-copy needs KIND ID FROM_PROVIDER TO_MOD, or --plan FILE --to DIR", file=sys.stderr)
            return 2
        result = vendor_copy(args.kind, args.id, args.from_provider, args.to_mod, args.policy, args.apply)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"{result['status']}" + (f": {result['reason']}" if result.get("reason") else ""))
            if result.get("files"):
                print(f"  files: {', '.join(result['files'])}")
            if result.get("note"):
                print(f"  note: {result['note']}")
            if result.get("must_stay_local_only"):
                print(f"  LICENCE: {result['licence_note']}")
        return 0 if result["status"] in ("PLANNED", "APPLIED") else 1
    if args.command == "revival-report-draft":
        from .revival_report_draft import draft_revival_report, write_revival_report_draft
        providers = args.providers or None
        if args.apply:
            result = write_revival_report_draft(args.mod, args.vanilla_core, providers, args.force)
        else:
            result = draft_revival_report(args.mod, args.vanilla_core, providers)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(result["status"])
            if result["status"] == "BLOCKED":
                for reason in result["blocking"]:
                    print(f"  {reason}")
            elif result["status"] == "REFUSED":
                print(f"  {result['reason']}")
                for path in result["existing"]:
                    print(f"  exists: {path}")
            elif result["status"] == "WRITTEN":
                print(f"  {result['report_path']}")
                print(f"  {result['plan_path']}")
            elif result["status"] == "OK":
                print(result["report_text"])
                print(result["plan_text"])
        return 0 if result["status"] in ("OK", "WRITTEN") else 1
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
    if args.command == "accept":
        try:
            result = accept_run(args.workspace, args.log, test_id=args.test_id, note=args.note, days=args.days,
                                not_exercised=args.not_exercised, mods_dir=args.mods_dir,
                                accept_findings=args.accept_findings, record_only=args.record_only)
        except (AcceptError, ValueError, OSError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Accepted {result['test_id']} for {result['workspace']}: run record {result['run_record']}")
            if result["report"]:
                print(f"  report section written: {result['report']}")
            if result["accepted_findings"]:
                print(f"  findings accepted: {'; '.join(result['accepted_findings'])}")
        return 0
    if args.command == "soak-report":
        try:
            result = soak_report(args.log, args.days, mods_dir=args.mods_dir)
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Soak: {result['verdict']}: {result['reason']}")
            for group in result["caught_exceptions"]["groups"][:10]:
                print(f"  x{group['count']} {group['exception']}: {group['first_frame'] or group['message']}")
            print(result["caveat"])
        return 0 if result["verdict"] == "PASS" else 1
    if args.command == "log-triage":
        try:
            result = triage_log(args.log, args.mod_prefix, mods_dir=args.mods_dir, all_mods=args.all_mods, last_sessions=args.last_sessions)
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            counts = result["counts"]
            if result.get("sessions"):
                sessions = result["sessions"]
                print(f"Sessions: last {sessions['found']} of the log, from line {sessions['first_line']} (line numbers below count from there)")
            print(f"FATAL={counts['FATAL']} MOD-ERROR={counts['MOD-ERROR']} KNOWN-NOISE={counts['KNOWN-NOISE']} OTHER={counts['OTHER']}")
            if result.get("rig_fingerprint"):
                fingerprint = result["rig_fingerprint"]
                core = (fingerprint["core_baseline_sha256"] or "none recorded")[:12]
                print(f"Rig: {len(fingerprint['enabled_mods'])} enabled mod(s), core baseline {core}: " + ", ".join(f"{k} {v}" for k, v in fingerprint["enabled_mods"].items())[:600])
            milestones = result["milestones"]
            print(f"Main menu reached: {milestones['main_menu_reached']}; campaign loads: {len(milestones['campaign_loads'])}; finished-saving events: {milestones['finished_saving_count']}; mission variant preloads (startup, not play): {len(milestones['mission_variant_preloads'])}")
            for event in result["fatal"]:
                where = f"line {event['line']}" if event.get("line") is not None else event.get("source", "dialog")
                print(f"FATAL {where} [{event['matched_rule']}]: {event['message']}")
                if event.get("top_mod_frame"):
                    print(f"  top mod frame: {event['top_mod_frame']}")
                if event.get("kind") == "jvm-crash" and event.get("top_mod"):
                    print(f"  nearest mod frame: {event['top_mod']} ({event['mod_frames'][0]['class']})")
            for event in result["mod_errors"]:
                print(f"MOD-ERROR line {event['line']}: {event.get('top_mod_frame') or event['message']}")
            caught = result["caught_exceptions"]
            if caught["distinct"]:
                print(f"Caught exceptions (logged, game carried on): {caught['total_events']} event(s), {caught['distinct']} distinct")
                for group in caught["groups"][:10]:
                    owner = f" [{group['suspect']}]" if group.get("suspect") else ""
                    print(f"  x{group['count']} {group['exception']}{owner} lines {group['first_line']}-{group['last_line']}: {group['first_frame'] or group['message']}")
            for symptom in result["vanilla_shadowing_symptoms"]:
                print(f"Vanilla-shadowing symptom line {symptom['line']}: ship system [{symptom['ship_system']}] from {symptom['csv']}")
            attribution = result.get("attribution")
            if attribution:
                print(f"Crash attribution (mod whose code threw, by exception count): {json.dumps(attribution.get('counts_by_suspect', {}), sort_keys=True)}")
                for event in result["fatal"] + result["mod_errors"]:
                    if event.get("suspect"):
                        print(f"  line {event['line']}: suspect {event['suspect']}; on stack: {', '.join(event.get('involved') or [])}")
                if args.mods_dir is not None and not attribution.get("counts_by_suspect"):
                    # ROADMAP 53: say so when the crashing mod code is in no mod here (the EPTA report's
                    # data.scripts.combat.hydrofoil class was in no installed mod: the log came from another folder).
                    import re

                    from .log_triage import class_owner_index
                    index = class_owner_index(args.mods_dir, enabled_only=not args.all_mods)
                    stack = re.findall(r"\bat\s+((?:data|src|org|com)\.[\w.$]+)\.[\w$<>]+\(", args.log.read_text(encoding="utf-8", errors="replace"))
                    unowned = sorted({c.split("$")[0] for c in stack if not c.startswith(("com.fs.", "org.lwjgl", "org.json", "org.codehaus.", "org.apache.", "com.thoughtworks.", "sun.", "java."))
                                      and c.split("$")[0] not in index})
                    if unowned:
                        print(f"  Not in any mod under {args.mods_dir}: {', '.join(unowned[:5])} -- the log likely came "
                              "from a different mods folder; pass that folder as --mods-dir.")
            print(result["caveat"])
        return 0 if not result["fatal"] else 1
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
    from .cli_commands import dispatch
    registered = dispatch(args)
    if registered is not None:
        return registered
    if args.command == "env-check":
        from . import env_check as envc
        try:
            checked = envc.env_check(args.launcher, args.vmparams, args.mods_dir)
        except OSError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(checked, indent=2) if args.json else envc.render(checked))
        return 1 if checked["findings"] else 0
    if args.command == "java-matrix":
        from . import java_matrix as jm
        try:
            if args.java_matrix_command == "describe-log":
                result = jm.describe_log_java(args.log)
                print(json.dumps(result, indent=2) if args.json else f"Java {result['java_version']}; Fast Rendering: {result['fast_rendering']}; launcher hint: {result['launcher_hint']}")
                return 0
            if args.java_matrix_command == "discover":
                jdks = jm.discover_jdks(args.rig, args.jdk_root)
                print(json.dumps(jdks, indent=2) if args.json else "\n".join(f"Java {j['major']:<3} {j['version']:<14} {j['home']}" for j in jdks) or "no JDKs found")
                return 0 if jdks else 1
            if args.java_matrix_command == "instances":
                found = jm.list_instances(args.rig)
                print(json.dumps(found, indent=2) if args.json else "\n".join(f"{i.get('variant')}: {i.get('state')} run {i.get('run')}/{i.get('of')} status={i.get('status')} java_alive={i['java_alive']}" for i in found) or "no instances")
                return 0
            if args.java_matrix_command == "mass":
                from . import mass_test as mt
                targets = mt.collect_targets(args.done_dir, args.only)
                if not targets:
                    print(f"bridgeforge: no archived mods found under {args.done_dir}", file=sys.stderr)
                    return 2
                if args.preset == "compare":
                    args.java, args.launcher = [25, 28], None
                elif args.preset == "real":
                    args.java, args.launcher = [28], ["miko", "miko-noprep"]
                    args.parallel = min(args.parallel, 2)
                variants = jm.plan_variants(jm.discover_jdks(args.rig, args.jdk_root), args.launcher, args.java)
                if not variants:
                    print("bridgeforge: no JDK matched; try `java-matrix discover` or --jdk-root", file=sys.stderr)
                    return 2
                rig_path = Path(args.rig).expanduser().resolve()
                roots = [*args.providers, rig_path / "mods", (rig_path / "starsector-core").resolve().parent / "mods"]
                providers = mt.index_providers(roots)
                for target in targets:
                    providers.setdefault(target["id"], Path(target["folder"]))
                result = mt.run_mass(args.rig, targets, variants, providers, args.output, screen=not args.no_screen, skip_baseline_validated=not args.retest_baseline, repeats=args.repeats, timeout=args.timeout, parallel=args.parallel, ledger=args.ledger, skip_known=args.skip_known, quiet=args.quiet, limit=args.limit, bundle=args.bundle)
                print(json.dumps(result, indent=2) if args.json else "Mass test: " + ", ".join(f"{k}={v}" for k, v in sorted(result["counts"].items())) + f". See {args.output / 'MASS_TEST.md'}")
                return 0 if not any(k in result["counts"] for k in ("ENVIRONMENT_SENSITIVE", "FLAKY")) else 1
            if getattr(args, "preset", None) == "compare":
                args.java, args.launcher = [25, 28], None
                args.parallel = args.parallel or 3
            elif getattr(args, "preset", None) == "real":
                args.java, args.launcher = [28], ["miko", "miko-noprep"]
                args.parallel = args.parallel or 2
            variants = jm.plan_variants(jm.discover_jdks(args.rig, args.jdk_root), args.launcher, args.java, prepatcher=getattr(args, "prepatcher", False), include_known_fail=getattr(args, "include_known_fail", False))
            if not variants:
                print("bridgeforge: no JDK matched; try `java-matrix discover` or --jdk-root", file=sys.stderr)
                return 2
            if args.java_matrix_command == "setup":
                written = jm.setup_rig(args.rig, variants)
                print(json.dumps({"written": written, "variants": variants}, indent=2) if args.json else "Wrote " + ", ".join(written))
                return 0
            checkpoint = Path(args.rig) / "logs" / "java-matrix.partial.jsonl"
            result = jm.run_java_matrix(args.rig, args.mods, variants, repeats=args.repeats, timeout=args.timeout, checkpoint=checkpoint, quiet=args.quiet, log_name=args.log_name, parallel=args.parallel or 1, ledger=args.ledger, skip_known=args.skip_known)
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(result, indent=2, sort_keys=True) if args.json else jm.render(result))
        return 0 if result["verdict"] == "PASS_ALL" else 1
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
                result["release"] = install_release(repo_root, args.core)
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
        # A historical reference rig holds the ORIGINAL mods on purpose: comparing it with the revived
        # working copies would suggest a `prepare-test --sync` that overwrites the reference. Only
        # explicit --working entries are compared there.
        use_defaults = not (args.no_default_working or args.reference_manifest)
        working: dict[str, Path] = dict(default_working_copies(Path(__file__).resolve().parent.parent)) if use_defaults else {}
        if use_defaults:
            # Defaults cover every project mod, but each rig holds only some (Vacuum has its own rig), so
            # compare only the ones installed in THIS rig. Explicit --working entries are never filtered.
            from .rig_doctor import _mods_by_id
            installed = _mods_by_id(Path(args.runtime_dir) / "mods") if (Path(args.runtime_dir) / "mods").is_dir() else {}
            working = {mod_id: path for mod_id, path in working.items() if mod_id in installed}
        for item in args.working:
            mod_id, sep, path = item.partition("=")
            if not sep or not mod_id or not path:
                print(f"bridgeforge: --working expects ID=PATH, got {item!r}", file=sys.stderr)
                return 2
            working[mod_id] = Path(path)
        try:
            result = rig_doctor(args.runtime_dir, working_copies=working, real_install=args.real_install, write_saves_baseline=args.write_saves_baseline, reference_manifest=args.reference_manifest, core_baseline=args.core_baseline, write_core_baseline=args.write_core_baseline)
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
    if args.command == "diff-data":
        from .data_diff import DataDiffError, diff_data
        try:
            result = diff_data(args.a, args.b)
        except DataDiffError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            if result["identical"]:
                print(f"IDENTICAL ({result['kind']}): no value differences")
            for change in result["changes"]:
                if change["change"] == "added":
                    print(f"+ {change['path']}: {json.dumps(change['b'], ensure_ascii=False)}")
                elif change["change"] == "removed":
                    print(f"- {change['path']}: {json.dumps(change['a'], ensure_ascii=False)}")
                elif change["change"] == "reordered":
                    print(f"^ {change['path']}: same values, other order: {json.dumps(change['a'], ensure_ascii=False)} -> {json.dumps(change['b'], ensure_ascii=False)}")
                else:
                    print(f"~ {change['path']}: {json.dumps(change['a'], ensure_ascii=False)} -> {json.dumps(change['b'], ensure_ascii=False)}")
        return 0 if result["identical"] else 1
    if args.command == "rebuild-from-reference":
        from .rebuild_reference import RebuildReferenceError, rebuild_from_reference
        try:
            result = rebuild_from_reference(args.mod, args.reference_core, args.vanilla_core, args.file_classes, args.output)
        except (RebuildReferenceError, OSError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            counts = ", ".join(f"{status} {count}" for status, count in sorted(result["counts"].items())) or "no shadowed files"
            print(f"REBUILD_FROM_REFERENCE ({', '.join(result['file_classes'])}): {counts}")
            for entry in result["files"]:
                if entry["status"] == "CONFLICT":
                    print(f"  CONFLICT {entry['file']}: " + "; ".join(c["path"] for c in entry["conflicts"][:5])
                          + (f" (+{len(entry['conflicts']) - 5} more)" if len(entry["conflicts"]) > 5 else ""))
                elif entry["status"] == "UNPARSEABLE":
                    print(f"  UNPARSEABLE {entry['file']}")
            for name in result["vanilla_removed_in_rc8"]:
                print(f"  vanilla removed in RC8 (now the mod's own content): {name}")
            if result["output"]:
                print(f"MERGED files written under: {result['output']}")
        return 1 if result["counts"].get("CONFLICT") or result["counts"].get("UNPARSEABLE") else 0
    if args.command == "corpus-index":
        from .corpus_index import CorpusIndexError, build_index, search_index
        try:
            if args.corpus_index_command == "build":
                def corpus_progress(done: int, total: int, source: str, status: str, seconds: float) -> None:
                    if status == "indexed":
                        print(f"[{done}/{total}] indexed {source} ({seconds:.1f}s)", file=sys.stderr, flush=True)
                    elif done % 500 == 0 or done == total:
                        print(f"[{done}/{total}] ... unchanged files skipped", file=sys.stderr, flush=True)

                result = build_index(args.root, args.db, args.max_bytes, progress=None if args.quiet else corpus_progress)
            else:
                result = search_index(args.db, args.text, args.limit, args.names)
        except CorpusIndexError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0 if args.corpus_index_command == "build" or result["content_hits"] or result["name_hits"] else 1
        if args.corpus_index_command == "build":
            print(f"Indexed {result['root']} -> {result['db']}: {result['reindexed']} read, {result['unchanged']} unchanged, {result['forgotten']} gone")
        else:
            for hit in result["content_hits"]:
                print(f"{hit['location']} ({hit['line_count']} matching line(s))")
                for line in hit["lines"]:
                    print(f"    {line}")
            for name in result["name_hits"]:
                print(f"name: {name}")
            if not result["content_hits"] and not result["name_hits"]:
                print(f"No hits for {args.text!r}.")
            if len(result["content_hits"]) >= result["limit"] or len(result["name_hits"]) >= result["limit"]:
                print(f"(stopped at --limit {result['limit']})")
        not_searched = ", ".join(f"{count} {reason}" for reason, count in result["not_searched"].items())
        print(f"Coverage: {result['text_files_searched']} text files searched, {result['files_listed']} files listed by name"
              + (f"; NOT searched: {not_searched}" if not_searched else "; nothing skipped"))
        return 0 if args.corpus_index_command == "build" or result["content_hits"] or result["name_hits"] else 1
    if args.command == "content-diff":
        from .content_diff import ContentDiffError, diff_content
        try:
            result = diff_content(args.reference_core, args.vanilla_core)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except (ContentDiffError, OSError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            for kind, count in result["counts"].items():
                print(f"{kind}: {count['reference']} -> {count['rc8']} ({count['removed']} removed, {count['added']} added)")
            for kind, entries in result["removed"].items():
                for entry in entries[:30]:
                    leads = entry["same_name_in_rc8"]
                    print(f"  - {kind}:{entry['id']}" + (f" ({entry['name']})" if entry.get("name") else "") + (f" -> same name in RC8: {', '.join(leads)}" if leads else ""))
                if len(entries) > 30:
                    print(f"  ... {len(entries) - 30} more {kind} ids (see --output/--json)")
            if args.output:
                print(f"Written: {args.output}")
        return 0
    if args.command == "verify-shadow":
        from .verify_shadow import VerifyShadowError, verify_shadow
        try:
            result = verify_shadow(args.scripts, args.against)
        except (VerifyShadowError, OSError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            for entry in result["results"]:
                print(f"{entry['status']}: {entry['script']} (class {entry['class']}, from {entry['class_from']})")
                for owner in entry["supplied_by"]:
                    print(f"    supplied by {owner}")
            print(f"Checked {result['classes_checked']} classes in {result['jars_checked']} jar(s).")
            for problem in result["unreadable_jars"]:
                print(f"  NOT checked: {problem}")
        return 0
    if args.command == "vendor-plan":
        from .substitutes import REPO_ROOT
        from .vendor_plan import VendorPlanError, dumps, render, vendor_plan
        target = args.target
        if target is None and (REPO_ROOT / "In operation" / "RevenantLib").is_dir():
            target = REPO_ROOT / "In operation" / "RevenantLib"
        try:
            plan = vendor_plan(args.provider, args.ids, target=target, vanilla_core=args.vanilla_core)
        except (VendorPlanError, OSError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        print(dumps(plan) if args.json else render(plan))
        return 0
    if args.command == "revive-queue":
        from .revive_queue import revive_queue
        result = revive_queue(args.queue, only_status=set(args.only_status) or None, never_revived=args.never_revived, apply=args.apply,
                              draft_report=args.draft_report, vanilla_core=args.vanilla_core, quiet=args.quiet, restart=args.restart,
                              jobs=args.jobs)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print("Counts: " + ", ".join(f"{k} {v}" for k, v in sorted(result["counts"].items(), key=lambda kv: str(kv[0]))))
            print(f"Written: {result['result_path']}")
        return 0
    if args.command == "revive":
        from .revive import ReviveError, render as render_revive, revive
        try:
            result = revive(args.workspace, target=args.target, vanilla_core=args.vanilla_core, policy_path=args.policy,
                            approve=args.approve, apply=args.apply, max_rounds=args.max_rounds, draft_report=args.draft_report,
                            providers=args.providers, provider_index=args.provider_index)
        except (ReviveError, OSError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(result, indent=2, ensure_ascii=False) if args.json else render_revive(result), end="\n" if args.json else "")
        return 0
    if args.command == "escalation" and args.escalation_command == "rule":
        from .escalation_queue import rule
        try:
            entry = rule(args.queue, args.finding, accept=args.accept, approve_fixer=args.approve_fixer, reason=args.reason)
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(entry, indent=2, ensure_ascii=False) if args.json else
              f"Ruling recorded ({entry['ruling']}) for {entry['finding']}: {len(entry['mods'])} mod baseline(s) updated. Re-run revive-queue --only-status ESCALATED to apply.")
        return 0
    if args.command == "escalation" and args.escalation_command == "accept":
        from .escalation_queue import accept_in_mod
        try:
            entry = accept_in_mod(args.workspace, args.selectors, args.reason)
        except (ValueError, OSError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(entry, indent=2, ensure_ascii=False) if args.json else
              f"Accepted {len(entry['keys'])} finding(s) as authored in {entry['baseline']}. Re-run revive to apply.")
        return 0
    if args.command == "escalation" and args.escalation_command == "queue":
        from .escalation_queue import summarize_queue
        result = summarize_queue(args.queue, quiet=args.quiet)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            for row in result["findings"][:15]:
                print(f"{len(row['only_blocker']):4} only / {len(row['mods']):4} mods  {row['finding']} ({row['tier']}, {row['kind']})")
            print(f"Escalated mods: {result['escalated']}. Written: {result['result_md']}")
        return 0
    if args.command == "escalation" and args.escalation_command == "review":
        from .escalation_review import review_sheet
        result = review_sheet(args.workspace)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"{len(result['reviews'])} attempt(s) reviewed; flagged: {', '.join(result['flagged']) or 'none'}" + (f"\n  {result['sheet']}" if result["sheet"] else ""))
        return 0
    if args.command == "escalation":
        from .escalation import EscalationError, list_packets, load_packet, run_packet, verify
        from .revive import render_packet
        try:
            if args.escalation_command == "list":
                packets = list_packets(args.workspace)
                if args.json:
                    print(json.dumps(packets, indent=2, ensure_ascii=False))
                for packet in [] if args.json else packets:
                    print(f"{packet['id']}  {packet['kind']:5}  {packet['tier']:10}  {packet.get('file') or '(mod-wide)'}")
                return 0
            if args.escalation_command == "show":
                packet = load_packet(args.workspace, args.packet)
                print(json.dumps(packet, indent=2, ensure_ascii=False) if args.json else render_packet(packet), end="\n" if args.json else "")
                return 0
            if args.escalation_command == "verify":
                packet = load_packet(args.workspace, args.packet)
                working = args.working or Path(packet["workspace"]) / "working"
                result = verify(packet, working.expanduser().resolve())
                print(json.dumps(result, indent=2) if args.json else f"{result['status']}: {args.packet}" + "".join(f"\n  {r}" for r in result["reasons"]))
                return 0 if result["status"] == "PASS" else 1
            if args.escalation_command == "apply":
                from .escalation import apply_verified
                result = apply_verified(args.workspace, args.packet, attempt=args.attempt, rebuild_jar=args.rebuild_jar,
                                        patch_classes=args.patch_class, allow_removed=args.allow_removed)
                if args.json:
                    print(json.dumps(result, indent=2, ensure_ascii=False))
                else:
                    print(f"APPLIED: {result['packet']} attempt {result['attempt']} (verified again first)")
                    for item in result["written"]:
                        print(f"  {item['path']}" + (f" (backup {item['backup']})" if item.get("backup") else ""))
                return 0
            from .escalation import jar_only

            local_only = []
            if args.all:
                # A packet whose only files are jar entries ("x.jar!path/Cls.class") cannot be fixed in an agent sandbox:
                # it has no jar, javap or python (Fast Engine Rendering and Magellan Protectorate agents changed nothing,
                # 2026-09-30). --all leaves them out and lists them for the main session; naming one still runs it.
                agent_packets = [p for p in list_packets(args.workspace) if p["kind"] == "agent"]
                local_only = [p["id"] for p in agent_packets if jar_only(p)]
                names = [p["id"] for p in agent_packets if p["id"] not in local_only]
                for name in local_only:
                    print(f"SKIPPED (jar-only, fix in the main session): {name}", file=sys.stderr)
                if not names and local_only:
                    return 0
            else:
                names = [args.packet]
            if not names or names == [None]:
                raise EscalationError("Name a packet, or pass --all.")
            from .escalation_review import diff_snapshots, review_sheet, snapshot_dir
            watched = {d: snapshot_dir(d) for d in args.watch_dir}
            from .escalation import run_lock
            with run_lock(args.workspace):
                results = [run_packet(args.workspace, name, args.agent, apply=args.apply, retries=args.retries, timeout=args.timeout) for name in names]
            for directory, before in watched.items():
                touched = diff_snapshots(before, snapshot_dir(directory))
                if any(touched.values()):
                    print(f"WARNING: the agent run changed {directory}: {json.dumps(touched)}", file=sys.stderr)
            review = review_sheet(args.workspace)
            if review["flagged"] and not args.json:
                print(f"Review first (flagged): {', '.join(review['flagged'])} -> {review['sheet']}", file=sys.stderr)
        except (EscalationError, OSError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(results, indent=2, ensure_ascii=False))
        for result in [] if args.json else results:
            last = result["attempts"][-1]
            print(f"{result['outcome']}: {result['packet']} after {len(result['attempts'])} attempt(s)" + "".join(f"\n  {r}" for r in last["reasons"]))
        return 0 if all(r["outcome"] in ("VERIFIED", "APPLIED") for r in results) else 1
    if args.command == "release-policy":
        from .release import ReleaseError as PolicyError, record_policy_decision  # alias: a bare ReleaseError here would shadow main()'s
        from .substitutes import revival_licence
        try:
            if args.policy_command == "show":
                decision = revival_licence(args.mod, args.mod, args.policy)
                print(f"{args.mod}: {decision['decision']}" + (f" ({decision['reason']})" if decision.get("reason") else ""))
            else:
                result = record_policy_decision(args.mod, local_only=args.local_only, reason=args.reason, on=args.on, policy_path=args.policy)
                verb = "updated" if result["previous"] else "recorded"
                print(f"{verb} {result['mod']}: {'LOCAL_ONLY' if result['current']['local_only'] else 'RELEASABLE'} in {result['file']}")
        except PolicyError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        return 0
    if args.command == "done-audit":
        from .done_audit import RESULT_MD, done_audit
        from .substitutes import REPO_ROOT
        done = args.done or REPO_ROOT / "Done"
        result = done_audit(done, args.queue or REPO_ROOT / "In operation", vanilla_core=args.vanilla_core, quiet=args.quiet)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print("Counts: " + ", ".join(f"{k} {v}" for k, v in sorted(result["counts"].items())) + f". Report: {Path(done) / RESULT_MD}")
        return 0
    if args.command == "fold":
        from .fold import FoldError, fold
        try:
            result = fold(args.source, args.target, dry_run=args.dry_run, overwrite=args.overwrite, successors_path=args.successors_path)
        except FoldError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"{result['status']}: {result['source']} -> {result['destination']}" + (" (dry run)" if result["dry_run"] else ""))
            if result["status"] == "CONFLICT":
                print("  conflicts: " + ", ".join(result["conflicts"][:10]) + (" ..." if len(result["conflicts"]) > 10 else ""))
            elif result["status"] == "REFUSED":
                print(f"  {result['message']}")
            else:
                print(f"  files copied: {len(result['files_copied'])}; provenance written: {result['provenance_written']}; successors entry written: {result['successors_entry_written']}")
        return 0 if result["status"] in ("OK", "NOOP") else 1
    return 2
