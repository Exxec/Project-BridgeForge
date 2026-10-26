"""The `probe-group` command and its sub-commands (ROADMAP 70 H2.1)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bridgeforge.probe.probe_config import ProbeConfigError
from bridgeforge.safeio import atomic_write_text


def add_parser(subcommands) -> None:
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
    group_install.add_argument("--save-reload-after-days", type=int, default=0, metavar="N", help="opt in to the save-and-reload fingerprint stage: at in-game day N the probe logs a fingerprint, saves, and stores it; `live --save-reload` then reloads that save (next probe version)")
    group_install.add_argument("--save-reload-note", default="", help="free text recorded with the fingerprint (slot or scenario note)")
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
    group_record.add_argument("--refresh", action="store_true", help="with --archive: replace an earlier archive of the same mod in Done/ (the old one is moved to Done/_replaced-<date>/, never deleted; Done/ must hold an ARCHIVE_NOTE.md there)")
    group_record.add_argument("--accept", action="store_true", help="record each PASS member through the single-mod acceptance checks (main menu, campaign load, no FATAL or MOD-ERROR) and write a dated 'Live run' section; probe FAIL lines and caught exceptions are carried only when an earlier acceptance of the same mod version covers them (reports/live_accepted.jsonl, working/reports/probe_accepted.json), otherwise nothing is recorded and the uncovered ones are listed; needs --note")
    group_record.add_argument("--note", help="with --accept: what was run and seen, written into each report as the owner's account")
    group_record.add_argument("--observe-exit", action="store_true", help="put the exit `live --natural-exit` observed (<rig>/logs/<TESTID>.exit.json) into the run record's process_exit_code / process_exit_observed; without the file it stays UNKNOWN")
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
    group_live.add_argument("--natural-exit", action="store_true", help="after the run, do not kill the game: wait for you to quit it from the main menu and record its return code (NATURAL), or KILLED if it is still up after --exit-wait")
    group_live.add_argument("--no-graceful-close", action="store_true", help="do not close the game by itself when the probe's done marker appears; stop it as before (the exit is then not recorded)")
    group_live.add_argument("--exit-wait", type=int, default=180, help="with --natural-exit: seconds to wait for the game to exit by itself (default 180)")
    group_live.add_argument("--save-reload", action="store_true", help="after the live run, start the game a second time, Continue the save the probe wrote at save_reload.after_days and wait for the fingerprint compare line (install with --save-reload-after-days); the reload run gets its own log <TESTID>-reload and manifest")
    group_live.add_argument("--interactive", action="store_true", help="start the game with the manifest, window watcher and exit observation but do not touch the mouse or keyboard: you play and close the game; the run records NATURAL with the exit code")
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
    group_regress.add_argument("--changed-since", metavar="COMMIT", help="rerun only the workspaces whose shipped files changed since their last PASS run, or all of them when the probe or harness changed since COMMIT; writes every archive's verdict, prints only the changed ones, never records. A regression (PASS before, not now) writes <queue>/_regress/REGRESSION_HOLD.json and later --changed-since runs refuse to start until --clear-hold (rig must be a junction)")
    group_regress.add_argument("--clear-hold", action="store_true", help="with --changed-since: remove an earlier regression hold after looking at it")
    group_regress.add_argument("--quiet",action="store_true", help="no per-group progress lines")
    group_regress.add_argument("--rig", type=Path)
    group_regress.add_argument("--queue", type=Path)
    group_regress.add_argument("--json", action="store_true")
    group_duel = group_sub.add_parser("duel", help="after `install` of the mod that owns the hulls: play the rig-only duel missions (SEEKER's Bone-Breaker against Betelgeuse, and two vanilla Onslaughts as the baseline) unattended and report the frame cost of a destruction; leave the mouse and keyboard alone")
    group_duel.add_argument("test_id", help="log name: writes <rig>/logs/<TESTID>.stdout.log")
    group_duel.add_argument("--bat", default="run-j25-direct.bat")
    group_duel.add_argument("--only", action="append", default=[], choices=["seeker", "baseline", "overwhelm", "ubique", "probestop"], help="play just this duel (repeatable)")
    group_duel.add_argument("--rig", type=Path)
    group_duel.add_argument("--queue", type=Path)
    group_duel.add_argument("--json", action="store_true")
    group_report_cmd = group_sub.add_parser("report", help="per-mod verdicts for a group's run log")
    group_report_cmd.add_argument("log", type=Path, help="the run's stdout log (bf-test launch) or the rig's starsector.log")
    group_report_cmd.add_argument("--rig", type=Path)
    group_report_cmd.add_argument("--queue", type=Path)
    group_report_cmd.add_argument("--json", action="store_true")


def run_cli(args: argparse.Namespace) -> int:
    if args.command == "probe-group":
        from bridgeforge.probe.probe_group import ProbeGroupError, group_report, install_group, plan_groups
        from bridgeforge.probe.probe_config import CONFIG_FILE
        from bridgeforge.substitutes import REPO_ROOT
        queue = (args.queue or REPO_ROOT / "In operation").expanduser().resolve()
        rig = (args.rig or queue / "_rig").expanduser().resolve()
        try:
            if args.probe_group_command == "plan":
                from bridgeforge.probe.probe_group import DEFAULT_PROVIDER_SOURCES
                sources = args.provider_source if args.provider_source is not None else [p for p in DEFAULT_PROVIDER_SOURCES if p.is_dir()]
                from bridgeforge.probe.probe_group import ready_workspaces
                # Workspace arguments take a path ("In operation/<name>") or a bare name; the plan matches folder names
                # (`--retest "In operation/X"` was read as In operation/In operation/X, 2026-10-13).
                args.retest = [Path(name).name for name in args.retest]
                args.exclude = [Path(name).name for name in args.exclude]
                args.solo = [Path(name).name for name in args.solo]
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
                                       save_reload_after_days=args.save_reload_after_days, save_reload_note=args.save_reload_note,
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
                from bridgeforge.live.live_run import live_run
                if args.interactive:
                    print("Starting the game: play, then close it; nothing is clicked for you after the launcher's Play button.", file=sys.stderr)
                else:
                    print("Starting the live run: leave the mouse and keyboard alone until it finishes (about three minutes after loading).", file=sys.stderr)
                if args.save_reload and args.interactive:
                    print("bridgeforge: --save-reload cannot be combined with --interactive", file=sys.stderr)
                    return 2
                if args.save_reload:
                    from bridgeforge.save.save_reload_run import clear_stale_fingerprint, save_reload_configured
                    if not save_reload_configured(rig):
                        print("bridgeforge: --save-reload needs the rig probe config's save_reload.after_days (install with --save-reload-after-days N)", file=sys.stderr)
                        return 2
                    clear_stale_fingerprint(rig)
                live = live_run(rig, args.test_id, bat_name=args.bat, menu_timeout=args.menu_timeout,
                                natural_exit=args.natural_exit, exit_wait=args.exit_wait, save_reload=args.save_reload,
                                graceful_exit=not args.no_graceful_close, interactive=args.interactive)
                result = {"verdict": live.verdict, "stage": live.stage, "detail": live.detail, "rounds": live.rounds, "stages": live.stages, "log": live.log}
                if args.save_reload and live.verdict == "LIVE_DONE":
                    from bridgeforge.save.save_fingerprint import parse_fingerprint
                    from bridgeforge.save.save_reload_run import reload_run
                    reloaded = reload_run(rig, f"{args.test_id}-reload", bat_name=args.bat, menu_timeout=args.menu_timeout)
                    block = parse_fingerprint(Path(reloaded.log).read_text(encoding="utf-8", errors="replace")) if reloaded.log and Path(reloaded.log).is_file() else None
                    result["reload"] = {"verdict": reloaded.verdict, "stage": reloaded.stage, "detail": reloaded.detail, "stages": reloaded.stages,
                                        "log": reloaded.log, "reload_after_save": bool(block and block["compare_observed"]), "fingerprint": block}
                    if not args.json:
                        print(f"  reload: {reloaded.verdict}; reload_after_save={result['reload']['reload_after_save']}; "
                              f"equal={block['equal'] if block else None}; differing sections: {', '.join(block['diff_sections']) if block and block['diff_sections'] else 'none'}")
                        print(f"  Next: bridgeforge run-manifest evaluate for {args.test_id}-reload (milestones.reload_after_save, fingerprint block).")
                    if reloaded.verdict != "LIVE_DONE":
                        live = reloaded
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

                from bridgeforge.regress import rejudge, run_regression
                out = args.out or Path(queue) / "_regress" / f"regress-{_date.today():%Y%m%d}.json"
                if args.rejudge:
                    out = args.out or Path(queue) / "_regress" / f"rejudged-{_date.today():%Y%m%d}.json"
                    result = rejudge(queue, rig, args.rejudge, out)
                elif args.changed_since:
                    from bridgeforge.regress_changed import RegressChangedError, run_changed
                    out = args.out or Path(queue) / "_regress" / f"regress-changed-{_date.today():%Y%m%d}.json"
                    try:
                        print("Starting the changed-only regression pass: leave the mouse and keyboard alone until it finishes.", file=sys.stderr)
                        result = run_changed(queue, rig, out, args.changed_since, repo_root=REPO_ROOT, bat=args.bat, size=args.size, limit=args.limit,
                                             quiet=args.quiet, test_prefix=args.test_prefix, clear_hold=args.clear_hold)
                    except RegressChangedError as exc:
                        raise ProbeGroupError(str(exc)) from exc
                    if not args.json:
                        print(f"{len(result['selected'])} workspace(s) rerun, {len(result['changed_verdicts'])} verdict(s) changed; summary {out}")
                        for name, row in result["changed_verdicts"].items():
                            print(f"  {name}: {row['previous']} -> {row['verdict']} ({row['why']})")
                        if result.get("hold"):
                            print(f"  REGRESSION: later --changed-since runs stop until a person looks ({result['hold']}).")
                else:
                    print("Starting the regression pass: leave the mouse and keyboard alone until it finishes (about five minutes a group).", file=sys.stderr)
                    result = run_regression(queue, rig, out, bat=args.bat, size=args.size, limit=args.limit, only=args.only or None,
                                        quiet=args.quiet, test_prefix=args.test_prefix)
                if not args.json and not args.changed_since:
                    print(f"{len(result['groups'])} group(s); {len(result['attention'])} item(s) need a look; summary {out}")
                    for item in result["attention"]:
                        print(f"  group {item['group']}: {item.get('mod') or item.get('members')}: {item['why']}")
            elif args.probe_group_command == "duel":
                from bridgeforge.duel_run import run_duel
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
                from bridgeforge.probe.probe_group import smoke_group
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
                from bridgeforge.probe.probe_group import bisect_group
                plan_path = args.plan or queue / "PROBE_GROUPS.json"
                result = bisect_group(json.loads(plan_path.read_text(encoding="utf-8")), args.group)
                atomic_write_text(plan_path, json.dumps(result, indent=2))
                if not args.json:
                    for group in result["groups"][-2:]:
                        print(f"Group {group['group']} ({len(group['members'])} mod(s)): " + ", ".join(m["workspace"] for m in group["members"]))
                    print(f"Plan updated: {plan_path}. Install and run each half.")
            elif args.probe_group_command == "record":
                from bridgeforge.probe.probe_group import record_group
                config = json.loads((rig / "saves" / "common" / CONFIG_FILE).read_text(encoding="utf-8"))
                result = record_group(rig / "logs" / f"{args.test_id}.stdout.log", config, queue, rig, test_id=args.test_id, archive=args.archive, refresh=args.refresh,
                                      accept=args.accept, note=args.note, observe_exit=args.observe_exit)
                if not args.json:
                    if result.get("stopped"):
                        print(f"STOPPED, not everything recorded: {result['stopped']}")
                    print(f"Recorded LIVE_VALIDATED ({result['probe_version']}): {', '.join(result['recorded']) or 'none'}")
                    if args.archive:
                        print(f"Archived to Done/: {', '.join(result['archived']) or 'none'}")
                    for item in result["skipped"]:
                        print(f"  not recorded: {item['mod_id']} ({item['verdict']}) {item.get('archive', '')}")
                    for item in result.get("warnings", []):
                        print(f"  WARN {item}")
                    if args.accept:
                        from bridgeforge.archive_checks import archive_offer

                        for line in archive_offer(result, queue):
                            print(line)
            else:
                config = json.loads((rig / "saves" / "common" / CONFIG_FILE).read_text(encoding="utf-8"))
                from bridgeforge.probe.probe_group import accepted_probe_findings
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
        return 1 if args.probe_group_command == "record" and result.get("stopped") else 0
    return 2
