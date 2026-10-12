from __future__ import annotations


import argparse
import json
import sys
from pathlib import Path



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bridgeforge", description="Safe, explainable legacy Starsector mod analysis and migration.")
    subcommands = parser.add_subparsers(dest="command", required=True)
    from .cli_commands import register_all
    register_all(subcommands)

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
    from .cli_commands import dispatch
    registered = dispatch(args)
    if registered is not None:
        return registered
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
    return 2
