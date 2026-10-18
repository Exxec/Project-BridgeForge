"""Values proposed from comparable rows, approved by a person, then applied (ROADMAP item 73 B5).

Two findings leave a number to a person: `wing-op-cost-blank` (a wing row with no `op cost`) and `carrier-bays-proposal`
(a carrier hull with no `fighter bays`). The number is a comparison, not a conversion, so BridgeForge proposes and a
person approves:

- wing op cost: the median `op cost` of the mod's own wings with the same `role` and wing size (`num`, fighters per wing),
  else the median of RC8's wings with that role and size, else RC8's nearest wing (same role, nearest fleet pts) as the
  fixer picks it. A 0-cost wing is special-purpose and never a comparison (Ironclads' su57_wing, 2026-10-05).
- fighter bays: the count the hull's own LAUNCH_BAY slots or variant wings show (the scanner's evidence), else the median
  `fighter bays` of the mod's own carriers of the same hull size, else of RC8's carriers of that size.

`write_sheet` lists every proposal with its comparison rows. The person sets `approved` to `yes` (take `proposed`) or to
their own whole number, and `apply_sheet` passes only those rows to the fixers; blank, `no` or anything else is skipped.
"""
from __future__ import annotations

import csv
import io
import math
import statistics
from pathlib import Path

from . import safeio
from .models import ScanResult, TargetProfile

SHEET_COLUMNS = ("kind", "target", "file", "proposed", "basis", "comparison", "input_sha256", "approved")
KIND_PRESET = "preset-field"
KIND_WING = "wing-op-cost"
KIND_BAYS = "carrier-bays"
MAX_COMPARISON_ROWS = 6
MAX_FIGHTER_BAYS = 6  # RC8's own maximum (the Astral); the same bound the fixer enforces


class ValueProposalError(ValueError):
    """A workspace without a mod, an unreadable sheet, or a sheet row that is not a usable approval."""


def mod_root(path: Path) -> Path:
    path = Path(path).expanduser().resolve()
    if (path / "working" / "mod_info.json").is_file():
        return path / "working"
    if (path / "mod_info.json").is_file():
        return path
    raise ValueProposalError(f"{path} is not a mod folder (no mod_info.json) or a workspace holding working/.")


def _round_half_up(value: float) -> int:
    return int(math.floor(value + 0.5))


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return []
    rows = []
    for row in csv.DictReader(io.StringIO(text)):
        cleaned = {str(k).strip().lower(): (v or "").strip() for k, v in row.items() if k}
        if cleaned.get("id") and not cleaned["id"].startswith("#"):
            rows.append(cleaned)
    return rows


def _whole(value: str) -> int | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number == int(number) else None


def _costed(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [r for r in rows if (_whole(r.get("op cost", "")) or 0) > 0]


def _listing(rows: list[dict[str, str]], key: str) -> str:
    shown = ", ".join(f"{r['id']}={r[key]}" for r in rows[:MAX_COMPARISON_ROWS])
    return shown + (f" (+{len(rows) - MAX_COMPARISON_ROWS} more)" if len(rows) > MAX_COMPARISON_ROWS else "")


def _median_of(rows: list[dict[str, str]], key: str) -> int:
    return _round_half_up(statistics.median(_whole(r[key]) or 0 for r in rows))


def _nearest_vanilla_wing(blank: dict[str, str], vanilla: list[dict[str, str]]) -> dict[str, str] | None:
    """The fixer's own pick: same role if any, nearest fleet pts, then nearest fighter count."""
    if not vanilla:
        return None
    same = [v for v in vanilla if v.get("role") == blank.get("role")] or vanilla

    def number(value: str) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    return min(same, key=lambda v: (abs(number(v.get("fleet pts", "")) - number(blank.get("fleet pts", ""))),
                                    abs(number(v.get("num", "")) - number(blank.get("num", "")))))


def propose_wing_costs(root: Path, vanilla_core: Path | None) -> list[dict[str, str]]:
    """One row per wing whose `op cost` is blank."""
    relative = "data/hulls/wing_data.csv"
    wings = _read_rows(root / relative)
    own = _costed(wings)
    vanilla = _costed(_read_rows(vanilla_core / relative)) if vanilla_core else []
    proposals = []
    for blank in (w for w in wings if not w.get("op cost")):
        role, size = blank.get("role", ""), blank.get("num", "")
        mine = [w for w in own if w.get("role", "") == role and w.get("num", "") == size]
        theirs = [w for w in vanilla if w.get("role", "") == role and w.get("num", "") == size]
        if mine:
            proposed, basis = _median_of(mine, "op cost"), f"median of {len(mine)} own wing(s), role {role}, size {size}"
            comparison = _listing(mine, "op cost")
        elif theirs:
            proposed, basis = _median_of(theirs, "op cost"), f"median of {len(theirs)} RC8 wing(s), role {role}, size {size}"
            comparison = _listing(theirs, "op cost")
        elif (nearest := _nearest_vanilla_wing(blank, vanilla)) is not None:
            proposed, basis = _whole(nearest["op cost"]), f"RC8's nearest wing (role {nearest.get('role', '')}, fleet pts)"
            comparison = f"{nearest['id']}={nearest['op cost']}"
        else:
            proposed, basis, comparison = None, "no comparable row (no RC8 core given, no own wing of this role and size)", ""
        proposals.append({"kind": KIND_WING, "target": blank["id"], "file": relative,
                          "proposed": "" if proposed is None else str(proposed), "basis": basis, "comparison": comparison, "approved": ""})
    return proposals


def _bay_candidates(root: Path, vanilla_core: Path | None) -> list[tuple[str, int | None, str]]:
    """(hull id, count the hull's own slots/wings show or None, scanner evidence) for each hull the scanner lists."""
    import re

    from .scan_ships import _scan_carrier_bays_proposal

    result = ScanResult(input_path=root, target=TargetProfile("0.98a-RC8", 17))
    _scan_carrier_bays_proposal(root, result, vanilla_core)
    found = []
    for finding in result.findings:
        for line in finding.evidence:
            hull_id, _, rest = str(line).partition(": ")
            counted = re.match(r"(\d+) bay\(s\)", rest)
            found.append((hull_id, int(counted.group(1)) if counted else None, rest))
    return found


def propose_bays(root: Path, vanilla_core: Path | None) -> list[dict[str, str]]:
    from .scan_ships import _ship_file_index

    candidates = _bay_candidates(root, vanilla_core)
    if not candidates:
        return []
    ships = _ship_file_index(root, vanilla_core)

    def size_of(hull_id: str) -> str:
        return str((ships.get(hull_id) or {}).get("hullSize") or "").upper()

    # The mod's own carriers of known count, and RC8's carriers, both keyed by hull size.
    own_known = [(h, n) for h, n, _ in candidates if n is not None]
    vanilla_rows = [r for r in _read_rows(vanilla_core / "data/hulls/ship_data.csv") if (_whole(r.get("fighter bays", "")) or 0) > 0] \
        if vanilla_core else []
    proposals = []
    for hull_id, counted, evidence in candidates:
        size = size_of(hull_id)
        if counted is not None:
            proposed, basis, comparison = counted, "the hull's own launch-bay slots or variant wings", evidence
        else:
            mine = [(h, n) for h, n in own_known if size and size_of(h) == size]
            theirs = [r for r in vanilla_rows if size and size_of(r["id"]) == size]
            if mine:
                proposed = _round_half_up(statistics.median(n for _, n in mine))
                basis, comparison = f"median of {len(mine)} own carrier(s), hull size {size}", ", ".join(f"{h}={n}" for h, n in mine[:MAX_COMPARISON_ROWS])
            elif theirs:
                proposed = _median_of(theirs, "fighter bays")
                basis, comparison = f"median of {len(theirs)} RC8 carrier(s), hull size {size}", _listing(theirs, "fighter bays")
            else:
                proposed, basis, comparison = None, "no comparable carrier (hull size unknown or no RC8 core given)", evidence
        if proposed is not None:
            proposed = min(proposed, MAX_FIGHTER_BAYS)
        proposals.append({"kind": KIND_BAYS, "target": hull_id, "file": "data/hulls/ship_data.csv",
                          "proposed": "" if proposed is None else str(proposed), "basis": basis, "comparison": comparison, "approved": ""})
    return proposals


def propose_preset_fields(root: Path, vanilla_core: Path | None, reference_core: Path | None) -> list[dict[str, str]]:
    """One row per top-level vanilla field a preset entry lacks, with old-vanilla / mod / RC8 evidence (item 75 R4)."""
    from .fixers_presets import preset_field_proposals

    if vanilla_core is None:
        return []
    rows = []
    for item in preset_field_proposals(root, vanilla_core, reference_core):
        old = f"old vanilla: {item['old_value']}" if item["old_value"] else f"old vanilla: {item['old_state']}"
        rows.append({"kind": KIND_PRESET, "target": f"{item['entry']}.{item['field']}", "file": item["file"], "proposed": item["rc8_value"],
                     "basis": item["old_state"], "comparison": f"{old}; mod: field absent; RC8: {item['rc8_value']}", "input_sha256": item["file_sha256"],
                     "approved": ""})
    return rows


def build_sheet(workspace: Path, vanilla_core: Path | None = None, reference_core: Path | None = None) -> list[dict[str, str]]:
    root = mod_root(workspace)
    core = Path(vanilla_core).expanduser().resolve() if vanilla_core else None
    old = Path(reference_core).expanduser().resolve() if reference_core else None
    rows = propose_wing_costs(root, core) + propose_bays(root, core) + propose_preset_fields(root, core, old)
    # The input each proposal was computed from: an approval of a file that changed since is stale and is refused.
    return [{**row, "input_sha256": row.get("input_sha256") or _sha(root / row["file"])} for row in rows]


def _sha(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""


def write_sheet(rows: list[dict[str, str]], path: Path, mod: Path | None = None) -> Path:
    """Write the sheet. It is a report: it is never written inside the mod (`mod`), so a proposal cannot modify mod data."""
    if mod is not None and Path(mod).resolve() in Path(path).expanduser().resolve().parents:
        raise ValueProposalError(f"the sheet {path} must not be written inside the mod folder {mod}.")
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=SHEET_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return safeio.atomic_write_text(Path(path), buffer.getvalue(), newline="")


def read_sheet(path: Path) -> list[dict[str, str]]:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueProposalError(f"cannot read {path}: {exc}") from exc
    reader = csv.DictReader(io.StringIO(text))
    missing = [c for c in SHEET_COLUMNS if c not in (reader.fieldnames or [])]
    if missing:
        raise ValueProposalError(f"{path} lacks column(s) {', '.join(missing)}; it is not a value-proposals sheet.")
    return [{c: (row.get(c) or "").strip() for c in SHEET_COLUMNS} for row in reader]


def approved_values(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    """{kind: {target: value}} for the rows a person approved: `yes` takes `proposed`, a whole number is the person's own."""
    approved: dict[str, dict[str, str]] = {KIND_WING: {}, KIND_BAYS: {}}
    for row in rows:
        answer = row["approved"].strip().lower()
        if row["kind"] not in approved or answer in ("", "no", "n", "skip"):
            continue  # preset-field rows are handled by approved_preset_fields
        value = row["proposed"] if answer in ("yes", "y") else answer
        if _whole(value) is None:
            raise ValueProposalError(f"{row['kind']} {row['target']}: approved '{row['approved']}' with proposed '{row['proposed']}' is not a whole number.")
        approved[row["kind"]][row["target"]] = str(_whole(value))
    return approved


def _is_approved(row: dict[str, str]) -> bool:
    return row["approved"].strip().lower() not in ("", "no", "n", "skip")


def approved_preset_fields(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Approval records for the fixer from approved preset-field rows. Only `yes`: a field is restored with RC8's value or not."""
    records = []
    for row in rows:
        if row["kind"] != KIND_PRESET or not _is_approved(row):
            continue
        if row["approved"].strip().lower() not in ("yes", "y"):
            raise ValueProposalError(f"{row['kind']} {row['target']}: a preset field is approved with yes or not at all (got '{row['approved']}').")
        entry, _, field = row["target"].rpartition(".")
        records.append({"file": row["file"], "entry": entry, "field": field, "file_sha256": row["input_sha256"]})
    return records


def refuse_stale(root: Path, rows: list[dict[str, str]]) -> None:
    """An approved row whose input file changed since the sheet was written (or never recorded it) is refused, whole run."""
    stale = [f"{r['kind']} {r['target']}" for r in rows if _is_approved(r) and (not r["input_sha256"] or r["input_sha256"] != _sha(root / r["file"]))]
    if stale:
        raise ValueProposalError(f"stale approval: {r_file_list(stale)} -- the input file changed since the sheet was written; write a new sheet and approve again.")


def r_file_list(items: list[str]) -> str:
    return ", ".join(items[:8]) + (f" (+{len(items) - 8} more)" if len(items) > 8 else "")


def apply_sheet(workspace: Path, sheet: Path, *, apply: bool = True, vanilla_core: Path | None = None) -> dict:
    """Run the fixers with the approved rows. Returns {"approved": {...}, "diffs": {...}, "applied": [...]}."""
    from .fixers import FixerError, apply_fix, compute_fix, unified_diff_for_change

    root = mod_root(workspace)
    rows = read_sheet(sheet)
    refuse_stale(root, rows)
    approved = approved_values(rows)
    plans, refused = [], {}
    fields = approved_preset_fields(rows)
    if fields:
        try:
            plans.append(compute_fix(root, "preset-entry-drops-vanilla-fields", {"approved_fields": fields, "vanilla_core": vanilla_core}))
        except FixerError as exc:
            refused[KIND_PRESET] = str(exc)
    if approved[KIND_WING]:
        try:
            plans.append(compute_fix(root, "wing-op-cost-blank", {"proposals": approved[KIND_WING]}))
        except FixerError as exc:
            refused[KIND_WING] = str(exc)
    if approved[KIND_BAYS]:
        try:
            plans.append(compute_fix(root, "carrier-bays-proposal", {"hulls": [f"{h}={n}" for h, n in approved[KIND_BAYS].items()]}))
        except FixerError as exc:
            refused[KIND_BAYS] = str(exc)
    diffs = {str(change.path): unified_diff_for_change(change) for plan in plans for change in plan.changes}
    applied = [entry for plan in plans for entry in apply_fix(plan)] if apply else []
    return {"approved": approved, "diffs": diffs, "applied": applied, "refused": refused}


def add_parser(subcommands) -> None:
    cmd = subcommands.add_parser("value-proposals", help="propose a number for a blank wing op cost or a carrier's fighter bays from comparable rows (--write a sheet), then apply the rows a person approved (--apply); item 73 B5")
    cmd.add_argument("workspace", type=Path, help="workspace holding working/, or a mod folder")
    group = cmd.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", type=Path, metavar="SHEET.csv", help="write the proposals sheet; set its approved column to yes (or your own whole number)")
    group.add_argument("--apply", type=Path, metavar="SHEET.csv", help="apply the approved rows through the fixers (add --dry-run to print the diffs only)")
    cmd.add_argument("--vanilla-core", type=Path, help="RC8 starsector-core (read-only), for the RC8 comparison rows")
    cmd.add_argument("--reference-core", type=Path, help="the older starsector-core the mod was written against: gives preset-field rows their old-vanilla evidence")
    cmd.add_argument("--dry-run", action="store_true", help="with --apply: print the diffs and write nothing")
    cmd.add_argument("--json", action="store_true")


def run_cli(args) -> int:
    import json
    import sys

    try:
        if args.write:
            rows = build_sheet(args.workspace, args.vanilla_core, args.reference_core)
            write_sheet(rows, args.write, mod_root(args.workspace))
            filled = sum(1 for r in rows if r["proposed"])
            summary = {"sheet": str(args.write), "rows": len(rows), "with_proposal": filled}
            print(json.dumps(summary, indent=2) if args.json else f"Wrote {args.write}: {len(rows)} row(s), {filled} with a proposal. Set approved to yes (or a whole number), then --apply.")
            return 0
        outcome = apply_sheet(args.workspace, args.apply, apply=not args.dry_run, vanilla_core=args.vanilla_core)
    except ValueProposalError as exc:
        print(f"bridgeforge: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(outcome, indent=2, default=str))
    else:
        for path, diff in outcome["diffs"].items():
            print(f"--- {'dry-run diff' if args.dry_run else 'changed'}: {path} ---\n{diff}")
        for kind, reason in outcome["refused"].items():
            print(f"bridgeforge: {kind}: {reason}", file=sys.stderr)
        if not outcome["diffs"] and not outcome["refused"]:
            print("No approved rows in the sheet; nothing to do.")
    return 2 if outcome["refused"] else 0
