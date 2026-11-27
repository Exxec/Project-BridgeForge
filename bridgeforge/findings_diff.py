"""`findings-diff`: what a change to a check drops and adds over the archive, per archive (ROADMAP-3 98.19).

98.8 changed `settings-key-missing` and was judged by a hand-made sweep over Test1's Done/ with the old code and the new: 53
findings became 20, nothing new appeared, and each dropped one was explained. This compares two such runs. Each input is either
`done-audit`'s `Done/DONE_AUDIT.json`, one run with each checkout's code, or a plain `{"<archive>": [finding, ...]}` map, a
finding being a scan finding (`id`, `file`, `evidence`) or a list of strings (98.8's sweep wrote `[file, key]`).

Run done-audit with `--all-findings` for this. Without it, a record keeps only the crash-class, MANUAL and UNKNOWN findings the
baseline does not accept (about a third of the check ids), so a change to any other check compares nothing; the output says so.

A finding is matched by its id, file and first evidence line, and counted: two identical findings in one file are two (Sunrider
has nine). An archive that either run could not audit (ERROR, NO_MOD_ROOT, or closed by the owner) is listed as not compared,
so a scan failure never reads as findings dropped. done-audit records the checkout and git HEAD that ran; two inputs from the
same code are refused, since a crashed run leaves the other run's file in place (review, 2026-11-27).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
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


def _rows(path: Path, data) -> tuple[list[tuple[str, object, str | None]], dict]:
    """[(archive, findings, why it was not audited)], and what kind of input this is."""
    if isinstance(data, dict) and data.get("mode") == "DONE_AUDIT":
        every = data.get("all_findings") is True
        rows = []
        for record in data.get("mods") or []:
            if not isinstance(record, dict) or not isinstance(record.get("mod"), str):
                raise FindingsFileError(f"{path}: a mods entry has no mod name")
            status = str(record.get("status") or "")
            skipped = status if status in NOT_AUDITED or record.get("closed") else None
            rows.append((record["mod"], record.get("all_findings" if every else "findings") or [], skipped))
        kind = "done-audit --all-findings" if every else "done-audit (crash-class, MANUAL and UNKNOWN findings only)"
        return rows, {"kind": kind, "filtered": not every, "code": data.get("code")}
    if isinstance(data, dict) and all(isinstance(value, list) for value in data.values()):
        return [(name, value, None) for name, value in data.items()], {"kind": "archive map", "filtered": False, "code": None}
    raise FindingsFileError(f"{path} is neither done-audit's DONE_AUDIT.json nor a map of archive to findings")


def load(path: Path, ids: set[str] | None = None) -> tuple[dict[str, Counter], dict[str, str], dict]:
    """(archive -> counted finding keys, archive -> why it was not audited, what the input is) from one input file. The
    input description also lists the finding ids seen, before `ids` filtered them."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise FindingsFileError(f"cannot read {path}: {exc}") from exc
    rows, meta = _rows(path, data)
    found: dict[str, Counter] = {}
    skipped: dict[str, str] = {}
    seen: set[str] = set()
    for name, findings, not_audited in rows:
        if not_audited:
            skipped[name] = not_audited
            continue
        if not isinstance(findings, list):
            raise FindingsFileError(f"{path}: {name}'s findings are not a list")
        keys: Counter = Counter()
        for finding in findings:
            key = _key(finding)
            if key is None:
                raise FindingsFileError(f"{path}: {name} lists something that is not a finding: {str(finding)[:80]}")
            if isinstance(finding, dict):
                seen.add(key[0])
            if _wanted(key, finding, ids):
                keys[key] += 1
        found[name] = keys
    return found, skipped, {**meta, "ids_seen": seen}


def _same_code(first: dict | None, second: dict | None) -> bool:
    return bool(first and second and first.get("head") and first == second)


def diff(before_path: Path, after_path: Path, ids: set[str] | None = None) -> dict:
    """Per archive, the findings `after` dropped and the ones it added (counted), with totals and what each input is."""
    before, before_skipped, before_meta = load(before_path, ids)
    after, after_skipped, after_meta = load(after_path, ids)
    compared = sorted(before.keys() & after.keys())
    changes = []
    for name in compared:
        dropped, appeared = before[name] - after[name], after[name] - before[name]
        if dropped or appeared:
            changes.append({"archive": name, "dropped": [list(k) for k in sorted(dropped.elements())],
                            "appeared": [list(k) for k in sorted(appeared.elements())]})
    not_compared = sorted({*before_skipped, *after_skipped})
    return {
        "mode": "FINDINGS_DIFF", "before": str(before_path), "after": str(after_path), "ids": sorted(ids) if ids else None,
        "inputs": {side: {"kind": meta["kind"], "filtered": meta["filtered"], "code": meta["code"]}
                   for side, meta in (("before", before_meta), ("after", after_meta))},
        "same_code": _same_code(before_meta["code"], after_meta["code"]),
        "unknown_ids": sorted((ids or set()) - before_meta["ids_seen"] - after_meta["ids_seen"]),
        "archives_compared": len(compared),
        "findings_before": sum(sum(before[n].values()) for n in compared), "findings_after": sum(sum(after[n].values()) for n in compared),
        "dropped": sum(len(c["dropped"]) for c in changes), "appeared": sum(len(c["appeared"]) for c in changes),
        "changes": changes,
        "not_compared": [{"archive": n, "before": before_skipped.get(n), "after": after_skipped.get(n)} for n in not_compared],
        "only_before": sorted(before.keys() - after.keys() - after_skipped.keys()),
        "only_after": sorted(after.keys() - before.keys() - before_skipped.keys()),
    }


def problems(result: dict) -> list[str]:
    """Why the comparison cannot be trusted as it stands; the command exits 1 when there is any."""
    found = []
    if result["same_code"]:
        code = result["inputs"]["before"]["code"]
        found.append(f"both inputs come from the same code ({code['checkout']} at {code['head'][:12]}): a run that crashed leaves "
                     "the other run's DONE_AUDIT.json in place. Run done-audit again with the other checkout")
    if result["unknown_ids"]:
        filtered = any(meta["filtered"] for meta in result["inputs"].values())
        found.append(f"no finding with id {', '.join(result['unknown_ids'])} in either input: a typo, or "
                     + ("an id done-audit keeps only with --all-findings" if filtered else "an id neither run found"))
    if not result["archives_compared"]:
        found.append("no archive is in both inputs")
    return found


def _shown(key: list[str]) -> str:
    return f"{key[0]} {key[1]}: {key[2]}" if len(key) == 3 else " | ".join(key)


def _code(meta: dict) -> str:
    code = meta["code"]
    return f"{meta['kind']}, {code['checkout']} at {(code.get('head') or 'no git HEAD')[:12]}" if code else meta["kind"]


def render(result: dict) -> str:
    scope = f" ({', '.join(result['ids'])})" if result["ids"] else ""
    lines = [f"before: {_code(result['inputs']['before'])}", f"after:  {_code(result['inputs']['after'])}",
             f"{result['findings_before']} findings become {result['findings_after']}{scope} over {result['archives_compared']} archives: "
             f"{result['dropped']} dropped, {result['appeared']} new, in {len(result['changes'])} archive(s)."]
    if any(meta["filtered"] for meta in result["inputs"].values()):
        lines.append("Only crash-class, MANUAL and UNKNOWN findings the baseline does not accept are compared: run done-audit "
                     "with --all-findings to compare every check.")
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
    command = subcommands.add_parser("findings-diff", help="compare two per-archive finding lists (done-audit --all-findings, one "
                                                          "run with each checkout's code): the findings dropped and added, per "
                                                          "archive (ROADMAP-3 98.19); read-only")
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
    found = problems(result)
    for problem in found:
        print(f"bridgeforge: {problem}", file=sys.stderr)
    return 1 if found else 0
