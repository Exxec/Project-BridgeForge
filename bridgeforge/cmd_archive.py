"""Archive, intake, promote and release commands (ROADMAP 70 H2.1)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .archive_intake import inspect_zip_archive, stage_zip_archive
from .build_tag import apply_build_tag, BuildTagError, DEFAULT_LABEL, record_current_manifest
from .intake import intake_archive
from .project_board import project_board, render_board, write_board
from .promote import promote_mod
from .release import release_mod, ReleaseError


def add_parser(subcommands) -> None:
    archive_cmd = subcommands.add_parser("archive", help="package a finished revival into Done/<Mod>/: mod folder, zip, original, reports and an archive note (needs a licence decision; never deletes the workspace)")
    archive_cmd.add_argument("workspace", type=Path)
    archive_cmd.add_argument("--done", type=Path, help="default: <repo>/Done")
    archive_cmd.add_argument("--policy", type=Path)
    archive_cmd.add_argument("--refresh", action="store_true", help="replace an existing archive of this mod in Done/: the old one is moved to Done/_replaced-<date>/<Mod>[-N], never deleted, and put back if the new write fails (only a folder holding an ARCHIVE_NOTE.md directly inside Done/)")
    archive_cmd.add_argument("--readme-copy", action="store_true", help="also write <zip>-with-readme.zip and readme.txt for this archive")
    archive_cmd.add_argument("--json", action="store_true")
    archive_preflight = subcommands.add_parser("archive-preflight", help="inspect a ZIP archive without extracting it")
    archive_preflight.add_argument("archive", type=Path)
    archive_preflight.add_argument("--output", type=Path)
    archive_preflight.add_argument("--original", type=Path, help="the author's unpacked mod: warn about data/ files it has that the archive lacks")
    archive_stage = subcommands.add_parser("archive-stage", help="extract a preflight-safe ZIP into a new explicit destination")
    archive_stage.add_argument("archive", type=Path)
    archive_stage.add_argument("--output", required=True, type=Path)
    archive_stage.add_argument("--select-root", help="one preflight candidate mod root when the archive contains multiple")
    archive_stage.add_argument("--manifest-output", type=Path, help="optional manifest path outside the staged directory")
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
    build_tag = subcommands.add_parser("build-tag", help="iterate a visible build tag in a revived mod's mod_info.json name/version, surgically (never re-serializes the file)")
    build_tag.add_argument("mod_dir", type=Path)
    build_tag.add_argument("--label", default=DEFAULT_LABEL, help=f"suffix label used in the name tag, e.g. '[LABEL rN]' (default: {DEFAULT_LABEL})")
    build_tag.add_argument("--set", dest="set_value", type=int, help="force the build number instead of incrementing")
    build_tag.add_argument("--dry-run", action="store_true", help="print the proposed change without writing mod_info.json")
    build_tag.add_argument("--no-manifest", action="store_true", help="don't record the per-tag file hash manifest that test-plan diffs against")
    build_tag.add_argument("--record-only", action="store_true", help="record the manifest for the CURRENT build (r0 if untagged) without bumping or writing mod_info.json")
    build_tag.add_argument("--manifests-dir", type=Path, help="where build manifests go (default: <repo>/bridgeforge-state/build-manifests; never inside the mod)")
    build_tag.add_argument("--json", action="store_true")
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
    done_audit_cmd = subcommands.add_parser("done-audit", help="re-scan every archived revival in Done/: STALE when the queue copy changed since archiving, plus crash-class and MANUAL/UNKNOWN findings the baseline does not accept (writes Done/DONE_AUDIT.md)")
    done_audit_cmd.add_argument("--done", type=Path, help="default: <repo>/Done")
    done_audit_cmd.add_argument("--queue", type=Path, help="default: <repo>/In operation")
    done_audit_cmd.add_argument("--vanilla-core", type=Path)
    done_audit_cmd.add_argument("--quiet", action="store_true", help="no per-mod progress lines")
    done_audit_cmd.add_argument("--json", action="store_true")
    done_audit_cmd.add_argument("--content-parity", action="store_true", help="instead compare each shipped zip with its original/ (77.18): MISSING, SHADOW_REMOVAL, RENAMED, JUNK, SOURCE_OMITTED per mod and a verdict (writes CONTENT_PARITY.md/.json)")
    done_audit_cmd.add_argument("--write", type=Path, metavar="DIR", help="with --content-parity: write the report to DIR instead of Done/")
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
    fold_cmd = subcommands.add_parser("fold", help="fold a discontinued library-like mod into a RevenantLib-shaped target directory (roadmap P14 item 10): copy it byte-for-byte, keeping its ids and class names, and record provenance plus a dependency_successors.json entry")
    fold_cmd.add_argument("source", type=Path, help="the library mod's own directory (holding mod_info.json), e.g. a working copy")
    fold_cmd.add_argument("target", type=Path, help="the RevenantLib-shaped target directory (holds/gets original/<source name>/ and reports/PROVENANCE.md)")
    fold_cmd.add_argument("--overwrite", action="store_true", help="allow folding into an existing original/<source name>/ (files that differ from the source are still never overwritten -- reported as conflicts instead)")
    fold_cmd.add_argument("--dry-run", action="store_true", help="report what would happen; write nothing")
    fold_cmd.add_argument("--successors-path", type=Path, help="dependency_successors.json to update (default: bridgeforge's own copy)")
    fold_cmd.add_argument("--json", action="store_true")


def run_cli(args: argparse.Namespace) -> int:
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
            from .state_snapshot import snapshot_after_archive
            note = snapshot_after_archive(args.done or REPO_ROOT / "Done")
            if note:
                print(f"  {note}")
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
            result = inspect_zip_archive(args.archive, original=args.original)
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
        if args.write and not args.content_parity:
            print("bridgeforge: --write needs --content-parity.", file=sys.stderr)
            return 2
        if args.content_parity:
            from .content_parity import RESULT_MD as PARITY_MD, content_parity
            out = args.write or done
            result = content_parity(done, args.queue or REPO_ROOT / "In operation", out, vanilla_core=args.vanilla_core, quiet=args.quiet)
            if args.json:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print("Counts: " + ", ".join(f"{k} {v}" for k, v in result["counts"].items()) + f". Report: {Path(out) / PARITY_MD}")
            return 0
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
