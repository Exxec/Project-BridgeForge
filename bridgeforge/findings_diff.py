"""`findings-diff`: what a change to a check drops and adds over the archive, per archive (ROADMAP-3 98.19).

98.8 changed `settings-key-missing` and was judged by a hand-made sweep over Test1's Done/ with the old code and the new: 53
findings became 20, nothing new appeared, and each dropped one was explained. This compares two such runs. Each input is either
`done-audit`'s `Done/DONE_AUDIT.json` (one run with each checkout's code; it lists every crash-class, MANUAL and UNKNOWN finding the
baseline does not accept) or a plain `{"<archive>": [finding, ...]}` map, a finding being a scan finding (`id`, `file`,
`evidence`) or a list of strings (98.8's sweep wrote `[file, key]`).

A finding is matched by its id, file and first evidence line. An archive that one run could not audit (ERROR, NO_MOD_ROOT, or
closed by the owner) is listed as not compared, so a scan failure never reads as findings dropped.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bridgeforge.report_status import CLOSED_STATUSES

# done-audit's statuses for an archive it did not scan; a record it marks `closed` is skipped whatever its status says.
NOT_AUDITED = frozenset({"ERROR", "NO_MOD_ROOT", *CLOSED_STATUSES})
SHOWN_PER_ARCHIVE = 20


class FindingsFileError(ValueError):
    """An input that is neither a DONE_AUDIT.json nor an archive-to-findings map."""


def _key(finding) -> tuple[str, ...] | None:
    """A finding's identity, or None for something that is not a finding."""
    if isinstance(finding, dict):
        evidence = finding.get("evidence")
        first = evidence[0] if isinstance(evidence, list) and evidence else ""
        return (str(finding.get("id") or "?"), str(finding.get("file") or ""), str(first))
    if isinstance(finding, list) and all(isinstance(part, (str, int, float)) for part in finding):
        return tuple(str(part) for part in finding)
    if isinstance(finding, str):
        return (finding,)
    return None


def _wanted(key: tuple[str, ...], finding, ids: set[str] | None) -> bool:
    """With `ids`, only scan findings carrying one of them (a bare list or string has no id)."""
    return ids is None or (isinstance(finding, dict) and key[0] in ids)


def load(path: Path, ids: set[str] | None = None) -> tuple[dict[str, set[tuple[str, ...]]], dict[str, str]]:
    """(archive -> finding keys, archive -> why it was not audited) from one input file."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise FindingsFileError(f"cannot read {path}: {exc}") from exc
    rows: list[tuple[str, list, str | None]] = []
    if isinstance(data, dict) and data.get("mode") == "DONE_AUDIT":
        for record in data.get("mods") or []:
            if not isinstance(record, dict) or not isinstance(record.get("mod"), str):
                raise FindingsFileError(f"{path}: a mods entry has no mod name")
            status = str(record.get("status") or "")
            rows.append((record["mod"], record.get("findings") or [], status if status in NOT_AUDITED or record.get("closed") else None))
    elif isinstance(data, dict) and all(isinstance(value, list) for value in data.values()):
        rows = [(name, value, None) for name, value in data.items()]
    else:
        raise FindingsFileError(f"{path} is neither done-audit's DONE_AUDIT.json nor a map of archive to findings")
    found: dict[str, set[tuple[str, ...]]] = {}
    skipped: dict[str, str] = {}
    for name, findings, not_audited in rows:
        if not_audited:
            skipped[name] = not_audited
            continue
        keys = set()
        for finding in findings:
            key = _key(finding)
            if key is None:
                raise FindingsFileError(f"{path}: {name} lists something that is not a finding: {str(finding)[:80]}")
            if _wanted(key, finding, ids):
                keys.add(key)
        found[name] = keys
    return found, skipped


def diff(before_path: Path, after_path: Path, ids: set[str] | None = None) -> dict:
    """Per archive, the findings `after` dropped and the ones it added, with totals."""
    before, before_skipped = load(before_path, ids)
    after, after_skipped = load(after_path, ids)
    compared = sorted(before.keys() & after.keys())
    changes = []
    for name in compared:
        dropped, appeared = sorted(before[name] - after[name]), sorted(after[name] - before[name])
        if dropped or appeared:
            changes.append({"archive": name, "dropped": [list(k) for k in dropped], "appeared": [list(k) for k in appeared]})
    not_compared = sorted({*before_skipped, *after_skipped} & ({*before, *before_skipped} & {*after, *after_skipped}))
    return {
        "mode": "FINDINGS_DIFF", "before": str(before_path), "after": str(after_path), "ids": sorted(ids) if ids else None,
        "archives_compared": len(compared),
        "findings_before": sum(len(before[n]) for n in compared), "findings_after": sum(len(after[n]) for n in compared),
        "dropped": sum(len(c["dropped"]) for c in changes), "appeared": sum(len(c["appeared"]) for c in changes),
        "changes": changes,
        "not_compared": [{"archive": n, "before": before_skipped.get(n), "after": after_skipped.get(n)} for n in not_compared],
        "only_before": sorted(before.keys() - after.keys() - after_skipped.keys()),
        "only_after": sorted(after.keys() - before.keys() - before_skipped.keys()),
    }


def _shown(key: list[str]) -> str:
    return f"{key[0]} {key[1]}: {key[2]}" if len(key) == 3 else " | ".join(key)


def render(result: dict) -> str:
    scope = f" ({', '.join(result['ids'])})" if result["ids"] else ""
    lines = [f"{result['findings_before']} findings become {result['findings_after']}{scope} over {result['archives_compared']} archives: "
             f"{result['dropped']} dropped, {result['appeared']} new, in {len(result['changes'])} archive(s)."]
    for change in result["changes"]:
        lines.append(f"\n{change['archive']}: -{len(change['dropped'])} +{len(change['appeared'])}")
        for sign, keys in (("-", change["dropped"]), ("+", change["appeared"])):
            lines += [f"  {sign} {_shown(key)}" for key in keys[:SHOWN_PER_ARCHIVE]]
            if len(keys) > SHOWN_PER_ARCHIVE:
                lines.append(f"  {sign} ... and {len(keys) - SHOWN_PER_ARCHIVE} more (--json lists all)")
    for row in result["not_compared"]:
        lines.append(f"\nnot compared: {row['archive']} (before: {row['before'] or 'audited'}; after: {row['after'] or 'audited'})")
    for side in ("only_before", "only_after"):
        if result[side]:
            lines.append(f"\nin one run only ({side.replace('_', ' ')}): {', '.join(result[side])}")
    return "\n".join(lines)


def add_parser(subcommands) -> None:
    command = subcommands.add_parser("findings-diff", help="compare two per-archive finding lists (done-audit's DONE_AUDIT.json, one "
                                                          "run with each code): the findings dropped and added, per archive "
                                                          "(ROADMAP-3 98.19); read-only")
    command.add_argument("before", type=Path, help="the run with the old code")
    command.add_argument("after", type=Path, help="the run with the new code")
    command.add_argument("--id", action="append", dest="ids", metavar="FINDING_ID",
                         help="compare only scan findings with this id; repeatable (a finding written as a bare list has no id and is left out)")
    command.add_argument("--json", action="store_true")


def run_cli(args: argparse.Namespace) -> int:
    try:
        result = diff(args.before, args.after, set(args.ids) if args.ids else None)
    except FindingsFileError as exc:
        print(f"bridgeforge: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False) if args.json else render(result))
    return 0
