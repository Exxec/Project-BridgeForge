from __future__ import annotations
import re
from pathlib import Path
from ..scanner import _load_lenient_json_file
from .common import FileChange, FixerError, _decode, _encode, _findings_of


# ---------------------------------------------------------------------------
# Fixer: wing-op-cost-blank (ROADMAP 34.22; approval-gated: the value is a comparison, not a conversion)
# ---------------------------------------------------------------------------


def _raw_csv_spans(line: str) -> list[tuple[int, int]]:
    spans, start, quoted = [], 0, False
    for i, ch in enumerate(line):
        if ch == '"':
            quoted = not quoted
        elif ch == "," and not quoted:
            spans.append((start, i))
            start = i + 1
    spans.append((start, len(line.rstrip("\r\n"))))
    return spans


def _approved_wing_costs(raw) -> dict[str, str] | None:
    """The approved {wing id: op cost} map as strings, or None when the caller gave none. A cost must be a whole number
    from 1 to 999 (RC8's own wings run 0-45; 0 is special-purpose and is never proposed)."""
    if raw is None:
        return None
    costs: dict[str, str] = {}
    for wing_id, value in dict(raw).items():
        text = str(value).strip()
        if not re.fullmatch(r"\d{1,3}", text) or int(text) < 1:
            raise FixerError(f"wing-op-cost-blank: approved cost for {wing_id} must be a whole number from 1 to 999 (got '{text}').")
        costs[str(wing_id)] = str(int(text))
    if not costs:
        raise FixerError("wing-op-cost-blank: no approved proposals were given.")
    return costs


def _fix_wing_op_cost_blank(root: Path, options: dict) -> list[FileChange]:
    """Set a blank wing `op cost` to the nearest vanilla RC8 wing's (same role, nearest fleet pts, then fighter
    count), only for a wing a variant fits or a faction knows (autofit can fit it): built-in or unused wings are never
    charged and stay as they are. A pre-0.8 file without the column gets an `op cost` column appended, rows padded to
    the header first. Only the one cell changes. Done by hand for 36 wings in 7 mods on 2026-10-04 (owner ruling)."""
    import csv as _csv
    import io as _io


    # `options["proposals"]` (ROADMAP item 73 B5, `value-proposals --apply`): {wing id: op cost} a person approved. Those
    # wings take exactly that value, whether or not a variant or faction uses them, and no vanilla comparison is made.
    proposals = _approved_wing_costs(options.get("proposals"))
    core = options.get("vanilla_core")
    if not core and proposals is None:
        raise FixerError("wing-op-cost-blank needs --vanilla-core: the cost is read from the nearest vanilla wing.")
    vanilla = [] if proposals is not None else [
               r for r in _csv.DictReader(_io.StringIO((Path(core) / "data/hulls/wing_data.csv").read_text(encoding="utf-8-sig")))
               if r.get("id") and (r.get("op cost") or "").strip()
               # A 0-cost RC8 wing is special-purpose, not a price (mining_drone, borer, terminator): Ironclads'
               # su57_wing was matched to one and charged 0 (2026-10-05).
               and (r.get("op cost") or "").strip() not in ("0", "0.0")]
    if not vanilla and proposals is None:
        raise FixerError("the vanilla core's wing_data.csv has no op costs to compare with.")

    def number(value) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    if proposals is not None:
        flagged = set(proposals)
    else:
        flagged = {e.split(":", 1)[1] for f in _findings_of(root, options, "wing-op-cost-blank") for e in f.evidence if e.startswith("wing:")}
    used: set[str] = set()
    for spec_path in (root / "data" / "variants").rglob("*.variant") if (root / "data" / "variants").is_dir() else []:
        spec = _load_lenient_json_file(spec_path)
        if isinstance(spec, dict):
            used |= {w for w in spec.get("wings") or [] if isinstance(w, str)}
    factions = " ".join(p.read_text(encoding="utf-8", errors="replace") for p in (root / "data/world/factions").glob("*.faction")) \
        if (root / "data/world/factions").is_dir() else ""
    targets = set(flagged) if proposals is not None else {w for w in flagged if w in used or f'"{w}"' in factions}
    if not targets:
        raise FixerError("No blank-cost wing is fitted by a variant or known to a faction: nothing is ever charged, accept as authored.")
    path = root / "data/hulls/wing_data.csv"
    raw = path.read_bytes()
    text, had_bom = _decode(raw)
    lines = text.splitlines(keepends=True)
    header = next(_csv.reader(_io.StringIO(lines[0])))
    if "op cost" not in header:
        width, eol = len(header), ("\r\n" if lines[0].endswith("\r\n") else "\n")
        lines[0] = lines[0].rstrip("\r\n") + ",op cost" + eol
        for n, line in enumerate(lines[1:], 1):
            if line.strip():
                body = line.rstrip("\r\n") + "," * max(0, width - len(_raw_csv_spans(line)))
                lines[n] = body + "," + (line[len(line.rstrip("\r\n")):] or eol)
        header = header + ["op cost"]
    column = header.index("op cost")
    changed = 0
    for n, line in enumerate(lines[1:], 1):
        row = next(_csv.reader(_io.StringIO(line)), [])
        if not row or row[0] not in targets or len(row) <= column or row[column].strip():
            continue
        start, end = _raw_csv_spans(line)[column]
        if proposals is not None:
            cost = proposals[row[0]]
        else:
            fields = dict(zip(header, row))
            same = [v for v in vanilla if v["role"] == (fields.get("role") or "").strip()] or vanilla
            best = min(same, key=lambda v: (abs(number(v["fleet pts"]) - number(fields.get("fleet pts"))), abs(number(v["num"]) - number(fields.get("num")))))
            cost = best["op cost"].strip()
        lines[n] = line[:start] + cost + line[end:]
        changed += 1
    if not changed:
        raise FixerError("The flagged wings' rows could not be edited mechanically.")
    return [FileChange(path=path, before=raw, after=_encode("".join(lines), had_bom))]


# ---------------------------------------------------------------------------
# Fixer: builtin-wing-is-hullmod (2026-10-04)
# ---------------------------------------------------------------------------


def _fix_builtin_wing_is_hullmod(root: Path, options: dict) -> list[FileChange]:
    """Rename `builtInWings` to `builtInMods` when every entry under it is a hull mod and the spec has no
    `builtInMods` yet (The Nomads' nom_komodo_p.ship, fixed by hand 2026-10-04). Mixed lists, or a spec that already
    has builtInMods, are refused: moving single entries between arrays is left to a person."""

    files = sorted({f.file for f in _findings_of(root, options, "builtin-wing-is-hullmod") if f.file})
    flagged: dict[str, set[str]] = {}
    for finding in _findings_of(root, options, "builtin-wing-is-hullmod"):
        flagged.setdefault(finding.file, set()).update(e.split(":", 1)[1] for e in finding.evidence if e.startswith("hullmod:"))
    changes, refused = [], []
    for rel in files:
        path = root / rel
        spec = _load_lenient_json_file(path) or {}
        wings = [w for w in spec.get("builtInWings") or [] if isinstance(w, str)]
        if "builtInMods" in spec or set(wings) - flagged.get(rel, set()):
            refused.append(rel)
            continue
        raw = path.read_bytes()
        text, had_bom = _decode(raw)
        new_text, count = re.subn(r'(["\'])builtInWings\1(\s*:)', r'\1builtInMods\1\2', text, count=1)
        if count:
            changes.append(FileChange(path=path, before=raw, after=_encode(new_text, had_bom)))
    if not changes:
        raise FixerError("No builtInWings list can be renamed mechanically" + (f" (refused: {', '.join(refused[:5])})" if refused else "."))
    return changes


# ---------------------------------------------------------------------------
# Fixer: json-missing-comma (ROADMAP 34.16)
# ---------------------------------------------------------------------------


def _fix_json_missing_comma(root: Path, options: dict) -> list[FileChange]:
    """Apply scanner._repair_missing_commas, which only succeeds when the file then parses as RC8 reads it."""
    from ..scanner import _repair_missing_commas

    changes: list[FileChange] = []
    for rel in sorted({f.file for f in _findings_of(root, options, "json-missing-comma") if f.file}):
        path = root / rel
        raw = path.read_bytes()
        text, had_bom = _decode(raw)
        repaired = _repair_missing_commas(text)
        if repaired:
            changes.append(FileChange(path=path, before=raw, after=_encode(repaired[0], had_bom)))
    if not changes:
        raise FixerError("No flagged JSON file parses after adding the missing commas.")
    return changes
