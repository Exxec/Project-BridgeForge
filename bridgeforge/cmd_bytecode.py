"""Bytecode, jar and decompiler commands (ROADMAP 70 H2.1)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .bytecode import BytecodeUnavailable, inspect_bytecode
from .bytecode_diff import diff_bytecode
from .bytecode_rules import apply_bytecode_class, apply_bytecode_jar, plan_bytecode
from .copy_drift import compare_copies, sync_copies
from .decompiler import create_decompiler_review, run_decompiler_review
from .jar_audit import audit_jar


def add_parser(subcommands) -> None:
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
    jar_audit = subcommands.add_parser("jar-audit", help="compare a rebuilt mod jar with its original for bundled libraries, removed classes, and reflection use")
    jar_audit.add_argument("rebuilt", type=Path)
    jar_audit.add_argument("--original", required=True, type=Path, help="original .jar file, or a .zip archive containing one")
    jar_audit.add_argument("--json", action="store_true")
    copy_drift = subcommands.add_parser("copy-drift", help="hash-compare a mod working copy against its deployed/test-rig copy")
    copy_drift.add_argument("working_copy", type=Path)
    copy_drift.add_argument("deployed_copy", type=Path)
    copy_drift.add_argument("--sync", action="store_true", help="copy missing/different files working -> deployed (test rigs only; never the reverse)")
    copy_drift.add_argument("--prune", action="store_true", help="with --sync: move deployed-only files to <rig>/pruned/<date>/<mod>/")
    copy_drift.add_argument("--json", action="store_true")
    pjs_cmd = subcommands.add_parser("patch-jar-sources", help="edits in a jar's source tree (with *.pre-bf-* backups) -> the jar: prove the pre-edit source rebuilds the shipped class, then patch the edited class in")
    pjs_cmd.add_argument("workspace", type=Path)
    pjs_cmd.add_argument("--vanilla-core", type=Path, required=True)
    pjs_cmd.add_argument("--apply", action="store_true")
    pjs_cmd.add_argument("--json", action="store_true")
    patch_jar_cmd = subcommands.add_parser("patch-jar-class",help="recompile a few edited classes and swap them into a mod jar, checked against the shipped classes with javap (members, calls, null checks)")
    patch_jar_cmd.add_argument("mod", type=Path, help="mod workspace (holding working/)")
    patch_jar_cmd.add_argument("--jar", required=True, help="the jar to patch, relative to working/ (e.g. jars/Name.jar)")
    patch_jar_cmd.add_argument("sources", type=Path, nargs="+", help="the edited .java files (a scratch copy or an escalation attempt's)")
    patch_jar_cmd.add_argument("--source-root", help="the mod's source tree, relative to working/ (e.g. jars/src); with --install each source is copied there by its package")
    patch_jar_cmd.add_argument("--allow-removed", action="append", default=[], help="a member name whose removal is intended (a hull-mod field moved to per-ship custom data); repeatable")
    patch_jar_cmd.add_argument("--vanilla-core", type=Path, help="read-only starsector-core, put on the compile classpath")
    patch_jar_cmd.add_argument("--jdk", type=Path)
    patch_jar_cmd.add_argument("--install", action="store_true", help="only when PASS: keep the old jar and sources in scratch/jar-patch-<date>/ and swap the classes in")
    patch_jar_cmd.add_argument("--json", action="store_true")
    jar_packets_cmd = subcommands.add_parser("jar-packets", help="for each jar-only escalation packet: find the class's source, copy it to scratch/jar-packets/ to edit, and say whether it rebuilds the shipped class unchanged (FAITHFUL) or not")
    jar_packets_cmd.add_argument("mod", type=Path, help="mod workspace (holding working/)")
    jar_packets_cmd.add_argument("--vanilla-core", type=Path, help="read-only starsector-core, put on the compile classpath")
    jar_packets_cmd.add_argument("--jdk", type=Path)
    jar_packets_cmd.add_argument("--json", action="store_true")
    rebuild_jar_cmd = subcommands.add_parser("rebuild-jar", help="rebuild a mod's jar from its sources and compare it with the original: class/method/field added or removed, forbidden sandbox references")
    rebuild_jar_cmd.add_argument("mod", type=Path, help="mod workspace (holding working/) or the working copy itself")
    rebuild_jar_cmd.add_argument("--sources", required=True, help="sources directory, relative to the workspace or the working copy (e.g. working/data/scripts)")
    rebuild_jar_cmd.add_argument("--jar", required=True, help="the ORIGINAL jar to rebuild and compare against, relative to the workspace, an original/<archive folder>/, or the working copy (e.g. jars/Name.jar)")
    rebuild_jar_cmd.add_argument("--vanilla-core", type=Path, help="read-only starsector-core, put on the compile classpath")
    rebuild_jar_cmd.add_argument("--jdk", type=Path, help="JDK home (default: this repo's rig JDK, else JAVA_HOME, else PATH)")
    rebuild_jar_cmd.add_argument("--providers", type=Path, action="append", default=[], help="mods folder, mod folder or In operation tree to search for declared dependencies; repeatable (default: <repo>/In operation and its rig's mods)")
    rebuild_jar_cmd.add_argument("--output", type=Path, help="where the rebuilt jar and compiled classes go (default: a new temp directory)")
    rebuild_jar_cmd.add_argument("--install", action="store_true", help="only when status is PASS: move the working copy's current jar to scratch/moved-<date>/ (logged in MOVES.log) and copy the rebuilt jar in")
    rebuild_jar_cmd.add_argument("--json", action="store_true")
    dj_cmd = subcommands.add_parser("decompile-jar", help="decompile a jar (Vineflower) into an editable source tree, the first step before rebuild-jar")
    dj_cmd.add_argument("jar", type=Path)
    dj_cmd.add_argument("--output", type=Path, required=True, help="folder for the source tree (e.g. a workspace's scratch/decompiled)")
    dj_cmd.add_argument("--vineflower", type=Path, help="vineflower jar (default: In operation/_tools/vineflower*.jar)")
    dj_cmd.add_argument("--jdk", type=Path)
    dj_cmd.add_argument("--json", action="store_true")
    delegate_cmd = subcommands.add_parser("delegate-method", help="replace chosen method bodies with a call into a compiled helper class (for a jar whose decompiled source does not recompile, e.g. Kotlin); only those methods may change, checked by bytecode; writes a new jar with the JDK jar tool")
    delegate_cmd.add_argument("jar", type=Path, help="the jar to read (never written)")
    delegate_cmd.add_argument("--spec", type=Path, required=True, help="JSON naming each owner/name/descriptor, its helper method and a reason")
    delegate_cmd.add_argument("--helper-classes", type=Path, required=True, help="folder holding the compiled helper class(es) at their package paths")
    delegate_cmd.add_argument("--output", type=Path, required=True, help="the patched jar to create (must not exist)")
    delegate_cmd.add_argument("--jdk", type=Path)
    delegate_cmd.add_argument("--json", action="store_true")
    decompiler = subcommands.add_parser("decompiler-review", help="record or explicitly run a user-supplied decompiler as untrusted review evidence")
    decompiler.add_argument("input", type=Path)
    decompiler.add_argument("--adapter", type=Path, required=True)
    decompiler.add_argument("--adapter-argument", action="append", default=[], help="adapter argument; include {input} and {output} placeholders")
    decompiler.add_argument("--output", required=True, type=Path)
    decompiler.add_argument("--execute", action="store_true")
    port_cmd = subcommands.add_parser("port-interfaces", help="jar classes missing a method RC8's interfaces require (jar-interface-method-missing): port the known contract changes in shipped or decompiled source and patch only when nothing else changes. A queue or one workspace")
    port_cmd.add_argument("path", type=Path)
    port_cmd.add_argument("--vanilla-core", type=Path, required=True)
    port_cmd.add_argument("--apply", action="store_true")
    port_cmd.add_argument("--restart", action="store_true", help="ignore an earlier run's checkpoint")
    port_cmd.add_argument("--quiet", action="store_true", help="no per-workspace progress lines on stderr")
    port_cmd.add_argument("--json", action="store_true")
    port_state_cmd = subcommands.add_parser("port-hullmod-state", help="move a hull mod source's per-ship instance fields into a per-ship State in ship.getCustomData() and write the result (for a jar source, feed it to patch-jar-class --allow-removed)")
    port_state_cmd.add_argument("source", type=Path, help="the hull mod's .java (a decompiled or bundled jar source)")
    port_state_cmd.add_argument("--field", action="append", required=True, help="a field to move (the finding's field:NAME); repeatable")
    port_state_cmd.add_argument("--out", type=Path, required=True, help="where to write the ported source (never the input)")


def run_cli(args: argparse.Namespace) -> int:
    if args.command == "decompile-jar":
        from .decompile import decompile_jar
        try:
            result = decompile_jar(args.jar, args.output, args.vineflower, args.jdk)
        except ValueError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(result, indent=2) if args.json else f"{result['sources']} Java and {result['kotlin_sources']} Kotlin source file(s) in {result['output']} (exit {result['exit_code']}). Next: {result['next']}")
        return 0 if result["exit_code"] == 0 else 1
    if args.command == "delegate-method":
        from .delegate_method import delegate_methods
        try:
            result = delegate_methods(args.jar, args.spec, args.helper_classes, args.output, args.jdk)
        except (ValueError, BytecodeUnavailable) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            for row in result["classes"]:
                print(f"{'OK  ' if row['ok'] else 'FAIL'} {row['class']}: changed {', '.join(row['changed']) or 'nothing'}")
            print(f"{result['status']}: {result['output'] or 'no jar written'}")
        return 0 if result["status"] == "PASS" else 1
    if args.command == "port-interfaces":
        from .jar_batch import port_interfaces, port_interfaces_queue
        path = args.path.expanduser().resolve()
        if (path / "working" / "mod_info.json").is_file():
            rows = [port_interfaces(path, args.vanilla_core, apply=args.apply)]
            result = rows[0]
        else:
            result = port_interfaces_queue(path, args.vanilla_core, apply=args.apply, quiet=args.quiet, restart=args.restart)
            rows = result["workspaces"]
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        for row in rows:
            print(f"{row['workspace']}: {row['classes']} class(es)" + "".join(f"\n  {j['jar']}: {j['state']} ({j['classes']})" for j in row["jars"])
                  + "".join(f"\n  not ported: {u['class']} ({u['why']})" for u in row["unported"][:6]))
        return 0
    if args.command == "patch-jar-sources":
        from .jar_batch import patch_jar_sources
        result = patch_jar_sources(args.workspace, args.vanilla_core, apply=args.apply)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        for row in result["jars"]:
            print(f"{row['state']:20} {row['jar']}: {', '.join(row['files'])}")
            for cls, change in (row.get("classes") or {}).items():
                print(f"  {cls}: null checks {change['null_checks']}, calls {change['calls'] or '{}'}, members {change['members'] or '{}'}")
        for name in result["not_in_any_jar"]:
            print(f"NOT IN ANY JAR       {name}")
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
    if args.command == "copy-drift":
        if args.prune and not args.sync:
            print("bridgeforge: --prune needs --sync.", file=sys.stderr)
            return 2
        if args.sync:
            try:
                synced = sync_copies(args.working_copy, args.deployed_copy, prune=args.prune)
            except ValueError as exc:
                print(f"bridgeforge: {exc}", file=sys.stderr)
                return 2
            if args.json:
                print(json.dumps(synced, indent=2, sort_keys=True))
                return 0 if synced["status"] == "PASS" else 1
            for item in synced["copied"]:
                print(f"COPIED {item}")
            for item in synced["pruned"]:
                print(f"PRUNED {item} -> {synced['pruned_to']}")
            for item in synced["extra_kept"]:
                print(f"EXTRA-KEPT {item} (use --prune to move it out)")
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
    if args.command == "jar-packets":
        from .jar_patch import JarPatchError, prepare_jar_packets
        try:
            result = prepare_jar_packets(args.mod, vanilla_core=args.vanilla_core, jdk=args.jdk)
        except (JarPatchError, OSError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        for row in result["packets"]:
            print(f"{row['state']:15} {row['class']}  ({row['finding']})\n  {row['next']}")
        if not result["packets"]:
            print("No jar-only packets.")
        return 0
    if args.command == "port-hullmod-state":
        from .hullmod_state import HullModStateError, port_hullmod_state
        if args.out.resolve() == args.source.resolve():
            print("bridgeforge: --out must not be the input source.", file=sys.stderr)
            return 2
        try:
            ported = port_hullmod_state(args.source.read_text(encoding="utf-8"), args.field, args.source.stem)
        except (HullModStateError, OSError) as exc:
            print(f"bridgeforge: not ported: {exc}", file=sys.stderr)
            return 2
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(ported, encoding="utf-8")
        removed = " ".join(f"--allow-removed {f}" for f in args.field)
        print(f"Ported: {args.out}\nNext: bridgeforge patch-jar-class MOD {args.out} --jar JAR {removed} --install")
        return 0
    if args.command == "patch-jar-class":
        from .jar_patch import JarPatchError, patch_jar_classes
        try:
            result = patch_jar_classes(args.mod, args.jar, args.sources, vanilla_core=args.vanilla_core, jdk=args.jdk,
                                       source_root=args.source_root, allow_removed=args.allow_removed, install=args.install)
        except (JarPatchError, OSError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"{result['status']}: {args.jar}" + (" (installed)" if result["installed"] else ""))
            for error in result["compile"]["errors"][:5]:
                print(f"  compile: {error}")
            for entry in result["classes"]:
                bits = [f"null checks {entry['null_checks'][0]}->{entry['null_checks'][1]}"] if "null_checks" in entry else ["new"]
                if entry.get("members"):
                    bits.append("members " + json.dumps(entry["members"]))
                if entry.get("calls_changed"):
                    bits.append("calls " + json.dumps(entry["calls_changed"]))
                print(f"  {entry['class']}: " + "; ".join(bits))
            for refusal in result.get("refusals", []):
                print(f"  refused: {refusal}")
        return 0 if result["status"] == "PASS" else 1
    if args.command == "rebuild-jar":
        from .rebuild_jar import RebuildJarError, rebuild_jar
        try:
            result = rebuild_jar(args.mod, args.sources, args.jar, vanilla_core=args.vanilla_core, jdk=args.jdk,
                                  provider_roots=args.providers, output=args.output, install=args.install)
        except (RebuildJarError, ValueError, OSError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"{result['status']}: {args.mod}")
            if result["status"] == "UNAVAILABLE":
                print(f"  {result['reason']}")
            comparison = result.get("comparison")
            if comparison:
                print(f"  classes: +{len(comparison['added_classes'])} -{len(comparison['removed_classes'])}; changed: {len(comparison['class_changes'])}")
                if comparison["forbidden_sandbox_references"]:
                    print(f"  forbidden sandbox references: {len(comparison['forbidden_sandbox_references'])} class(es)")
            if result.get("installed"):
                print(f"  installed: {result.get('installed_to')} (previous jar: {result.get('moved_original_to') or 'none'})")
            elif result.get("install_note"):
                print(f"  {result['install_note']}")
        return 0 if result["status"] == "PASS" else 1
    return 2
