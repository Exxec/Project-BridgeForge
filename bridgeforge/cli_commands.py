"""Registry of the commands that live in their own module (ROADMAP 70 H2.1).

`cli.py` once held every command's parser and handler, so every feature branch edited the same two places and conflicted. A command
that lives in its own module defines `add_parser(subcommands)` and `run_cli(args) -> int` and is listed here with the command names
its handler serves; `cli.build_parser` and `cli.main` need no edit. `tests/test_cli_golden.py` pins every command's --help text.
"""
from __future__ import annotations

import argparse
import importlib

# module name (in bridgeforge/) -> command names its run_cli handles; the order is the order of the parsers in --help
COMMAND_MODULES: dict[str, tuple[str, ...]] = {
    "atlas_report": ("atlas",),
    "baseline_audit": ("baseline-audit", "baseline-accept"),
    "rig_reset": ("rig-reset",),
    "live_ledger": ("live-ledger",),
    "roadmap_lint": ("roadmap-lint",),
    "agent_diff_check": ("agent-diff-check",),
    "move_machine": ("migrate-inventory", "relocate", "migrate-verify"),
    "cmd_workspace": ("workspace", "plan", "apply", "rollback", "build-plan", "compile", "package-jar", "compile-feedback", "review-bundle", "validate", "save-risk", "pipeline", "packs", "migration-pack-candidate", "runtime-profile", "runtime-smoke", "inspect", "export-patch", "opportunities", "doctor", "conflicts", "provenance"),
    "cmd_scan": ("mods-compat", "baseline-stats", "docs-index", "preset-check", "scan", "working-tree-layout", "source-authority", "build-input-manifest", "integration-scenarios", "compile-check", "revenantlib-check", "check-impact"),
    "cmd_analysis": ("corpus-audit", "cross-mod-analyze", "campaign-identity-inventory", "campaign-identity-check", "release-lineage", "library-api-inventory", "library-api-match", "dependency-api-check", "corpus-compare", "release-evaluate", "revival-audit", "api-diff"),
    "cmd_bytecode": ("decompile-jar", "port-interfaces", "patch-jar-sources", "decompiler-review", "bytecode-inspect", "bytecode-plan", "bytecode-diff", "bytecode-apply", "copy-drift", "jar-audit", "jar-packets", "port-hullmod-state", "patch-jar-class", "rebuild-jar"),
    "cmd_translate": ("translate-export", "translate-apply", "translate-tm", "translate-check", "fix", "strip-plan", "descriptions", "translate-batch", "renamed-ids"),
    "cmd_save": ("compat-set", "save-compat", "save-removal-plan", "save-doctor", "save-format-survey", "save-content", "save-diff", "save-growth", "save-inspect", "save-provenance", "save-removal", "save-scripts", "save-summary", "save-snapshot", "scenario"),
    "cmd_rig": ("accept", "soak-report", "log-triage", "prepare-test", "env-check", "java-matrix", "boot-test", "dossier", "build-probe-mod", "probe-config", "bootstrap", "rig-create", "rig-doctor", "who-locks", "test-plan", "perf-gate"),
    "cmd_probe_group": ("probe-group",),
    "cmd_behavior": ("lookup", "novelty", "behavior-decide", "archaeology", "behavior-diff", "behavior-map", "coverage", "expect", "hypotheses", "probe-baseline", "release-behavior-evaluate", "risk-register", "save-baseline"),
    "cmd_corpus": ("dependency-substitutes", "provider-index", "supersession", "finding-stats", "dependency-graph", "corpus-recheck", "sibling-assets", "vendor-copy", "revival-report-draft", "diff-data", "rebuild-from-reference", "corpus-index", "content-diff", "verify-shadow", "vendor-plan"),
    "cmd_archive": ("audit-shipped", "audit-explain", "archive", "relink", "bump-version", "declare-providers", "close", "restore-from-done", "promote", "board", "intake", "archive-preflight", "archive-stage", "build-tag", "release", "release-policy", "done-audit", "fold"),
    "cmd_revive": ("revive-review", "mod-changelog", "ready-list", "revive-queue", "revive", "escalation"),
}


def register_all(subcommands) -> None:
    for module_name in COMMAND_MODULES:
        importlib.import_module(f"{__package__}.{module_name}").add_parser(subcommands)


def handler_for(command: str):
    """The `run_cli` of the module that serves `command`, or None for a command still handled inside cli.py."""
    for module_name, commands in COMMAND_MODULES.items():
        if command in commands:
            return importlib.import_module(f"{__package__}.{module_name}").run_cli
    return None


def dispatch(args: argparse.Namespace) -> int | None:
    handler = handler_for(args.command)
    return None if handler is None else handler(args)
