"""Test-rig, probe and live-run commands (ROADMAP 70 H2.1)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bridgeforge.bootstrap import bootstrap_mods
from bridgeforge.build_tag import BuildTagError, DEFAULT_LABEL
from bridgeforge.compat_sets import CompatSetError
from bridgeforge.dossier import DEFAULT_CONTEXT_LINES, DEFAULT_MAX_KB, DossierError, write_dossier
from bridgeforge.live.live_accept import accept_run, AcceptError
from bridgeforge.locks import who_locks
from bridgeforge.log_triage import triage_log
from bridgeforge.prepare_test import prepare_test, PrepareTestError
from bridgeforge.probe.probe_config import load_profile, ProbeConfigError, write_probe_config
from bridgeforge.probe.probe_mod_build import build_probe_mod, install_release, ProbeModBuildError
from bridgeforge.reference_rigs import ReferenceRigError, write_reference_rig_manifest
from bridgeforge.rig.rig_doctor import default_working_copies, rig_doctor
from bridgeforge.soak_report import soak_report
from bridgeforge.spw_bridge import ingest_spw_report, log_spam, perf_gate, SpwBridgeError
from bridgeforge.test_plan import plan_tests, TestPlanError


def add_parser(subcommands) -> None:
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
    boot_test_cmd.add_argument("--natural-exit", action="store_true", help="record the observed exit (<rig>/logs/<LOG>.exit.json, ROADMAP 77.21): NATURAL with the launcher's return code if the game quit by itself before the test would kill it, else KILLED with no code. The test does not wait for the game")
    boot_test_cmd.add_argument("--json", action="store_true")
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
    locks_cmd = subcommands.add_parser("who-locks", help="read-only process/Restart Manager diagnosis; never stops processes")
    locks_cmd.add_argument("path", type=Path)
    locks_cmd.add_argument("--json", action="store_true")
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
    accept_cmd = subcommands.add_parser("accept", help="record a passing hand-run live test of one workspace: checks the log, writes the dated evidence section and LIVE_VALIDATED to the revival report, and a run record the archive gate reads")
    accept_cmd.add_argument("workspace", type=Path)
    accept_cmd.add_argument("--log", required=True, type=Path, help="the run's stdout log")
    accept_cmd.add_argument("--test-id", required=True)
    accept_cmd.add_argument("--note", required=True, help="what the owner did and saw")
    accept_cmd.add_argument("--not-exercised", help="what the run did not cover (for example: no raid on the station happened)")
    accept_cmd.add_argument("--days", type=float, help="campaign days the run was meant to cover; INCOMPLETE soak is refused")
    accept_cmd.add_argument("--rig", type=Path, help="the rig the run used: its logs/<test id>.manifest.json (written before launch by run-manifest prepare) binds the run to the staged files; required, a run without a manifest is not accepted")
    accept_cmd.add_argument("--mods-dir", type=Path, help="the rig's mods/ directory, to attribute errors to mods")
    accept_cmd.add_argument("--accept-findings", help="reason to accept probe FAIL lines or caught exceptions; written into the report")
    accept_cmd.add_argument("--record-only", action="store_true", help="write only the run record, not a report section (the report already says it)")
    accept_cmd.add_argument("--json", action="store_true")
    soak_cmd = subcommands.add_parser("soak-report", help="judge a long-run campaign session from its log: days covered, FATAL/MOD-ERROR, probe FAILs and caught exceptions (read-only)")
    soak_cmd.add_argument("log", type=Path)
    soak_cmd.add_argument("--days", type=float, required=True, help="campaign days the run was meant to cover")
    soak_cmd.add_argument("--mods-dir", type=Path, help="the rig's mods/ directory, to attribute caught exceptions to mods")
    soak_cmd.add_argument("--json", action="store_true")
    log_triage = subcommands.add_parser("log-triage", help="classify a Starsector log into FATAL / MOD-ERROR / KNOWN-NOISE / OTHER without modifying it")
    log_triage.add_argument("log", type=Path)
    log_triage.add_argument("--mod-prefix", action="append", default=[], metavar="PREFIX", help="additional mod source/package prefix to attribute errors to; repeatable")
    log_triage.add_argument("--mods-dir", type=Path, help="mods folder the log ran with: names the mod whose jar owns each crash frame (suspect/involved)")
    log_triage.add_argument("--all-mods", action="store_true", help="with --mods-dir: index every mod folder, not just enabled_mods.json (e.g. a log from a different mod list)")
    log_triage.add_argument("--last-sessions", type=int, metavar="N", help="a rolling starsector.log: triage only its last N game sessions (a relaunch during a test logs only there)")
    log_triage.add_argument("--json", action="store_true")
    bootstrap_cmd = subcommands.add_parser("bootstrap", help="one-time: write a scan baseline and record the current build manifest for each mod (nothing written inside mods)")
    bootstrap_cmd.add_argument("mod_dirs", nargs="+", type=Path)
    bootstrap_cmd.add_argument("--vanilla-core", required=True, type=Path)
    bootstrap_cmd.add_argument("--baselines-dir", type=Path, help="default: <repo>/bridgeforge-state/baselines")
    bootstrap_cmd.add_argument("--manifests-dir", type=Path, help="default: <repo>/bridgeforge-state/build-manifests")
    bootstrap_cmd.add_argument("--overwrite", action="store_true", help="replace existing baselines (default: keep them)")
    bootstrap_cmd.add_argument("--json", action="store_true")
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


def run_cli(args: argparse.Namespace) -> int:
    if args.command == "accept":
        try:
            result = accept_run(args.workspace, args.log, test_id=args.test_id, note=args.note, days=args.days,
                                not_exercised=args.not_exercised, mods_dir=args.mods_dir,
                                accept_findings=args.accept_findings, record_only=args.record_only, rig=args.rig)
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

                    from bridgeforge.log_triage import class_owner_index
                    index = class_owner_index(args.mods_dir, enabled_only=not args.all_mods)
                    stack = re.findall(r"\bat\s+((?:data|src|org|com)\.[\w.$]+)\.[\w$<>]+\(", args.log.read_text(encoding="utf-8", errors="replace"))
                    unowned = sorted({c.split("$")[0] for c in stack if not c.startswith(("com.fs.", "org.lwjgl", "org.json", "org.codehaus.", "org.apache.", "com.thoughtworks.", "sun.", "java."))
                                      and c.split("$")[0] not in index})
                    if unowned:
                        print(f"  Not in any mod under {args.mods_dir}: {', '.join(unowned[:5])} -- the log likely came "
                              "from a different mods folder; pass that folder as --mods-dir.")
            print(result["caveat"])
        return 0 if not result["fatal"] else 1
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
    if args.command == "env-check":
        from bridgeforge import env_check as envc
        try:
            checked = envc.env_check(args.launcher, args.vmparams, args.mods_dir)
        except OSError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(checked, indent=2) if args.json else envc.render(checked))
        return 1 if checked["findings"] else 0
    if args.command == "java-matrix":
        from bridgeforge.bytecode import java_matrix as jm
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
                from bridgeforge import mass_test as mt
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
            from bridgeforge import boot_test as boot_test_module
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
            result = boot_test_module.run_boot_test(args.runtime_dir, args.mods, timeout=args.timeout, log_name=args.log_name, keep_mods=args.keep_mods, natural_exit=args.natural_exit)
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
        repo_root = Path(__file__).resolve().parents[2]
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
            print(f"Bounty check (loose, MagicLib): {result.get('bounty_check')}")
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
        working: dict[str, Path] = dict(default_working_copies(Path(__file__).resolve().parents[2])) if use_defaults else {}
        if use_defaults:
            # Defaults cover every project mod, but each rig holds only some (Vacuum has its own rig), so
            # compare only the ones installed in THIS rig. Explicit --working entries are never filtered.
            from bridgeforge.rig.rig_doctor import _mods_by_id
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
    return 2
