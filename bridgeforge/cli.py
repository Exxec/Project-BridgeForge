from __future__ import annotations


import argparse
import json
import sys
from pathlib import Path

from .archive_intake import inspect_zip_archive, stage_zip_archive
from .build_tag import apply_build_tag, BuildTagError, DEFAULT_LABEL
from .release import ReleaseError, release_mod
from .intake import intake_archive
from .project_board import project_board, render_board, write_board
from .promote import promote_mod
from .build_tag import record_current_manifest


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
    build_tag = subcommands.add_parser("build-tag", help="iterate a visible build tag in a revived mod's mod_info.json name/version, surgically (never re-serializes the file)")
    build_tag.add_argument("mod_dir", type=Path)
    build_tag.add_argument("--label", default=DEFAULT_LABEL, help=f"suffix label used in the name tag, e.g. '[LABEL rN]' (default: {DEFAULT_LABEL})")
    build_tag.add_argument("--set", dest="set_value", type=int, help="force the build number instead of incrementing")
    build_tag.add_argument("--dry-run", action="store_true", help="print the proposed change without writing mod_info.json")
    build_tag.add_argument("--no-manifest", action="store_true", help="don't record the per-tag file hash manifest that test-plan diffs against")
    build_tag.add_argument("--record-only", action="store_true", help="record the manifest for the CURRENT build (r0 if untagged) without bumping or writing mod_info.json")
    build_tag.add_argument("--manifests-dir", type=Path, help="where build manifests go (default: <repo>/bridgeforge-state/build-manifests; never inside the mod)")
    build_tag.add_argument("--json", action="store_true")
    from .cli_commands import register_all
    register_all(subcommands)

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
    from .cli_commands import dispatch
    registered = dispatch(args)
    if registered is not None:
        return registered
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
