from __future__ import annotations
import csv
import io
from pathlib import Path
from .common import FileChange, FixerError, _decode, _encode, _findings_of, _format_csv_row, _line_field_spans


# ---------------------------------------------------------------------------
# Fixer: procgen-planet-row-missing / procgen-star-row-missing
# ---------------------------------------------------------------------------


_GEN_ROW_KEYWORDS = (  # first keyword found in the type's id or name picks the vanilla row to copy
    ("black_hole", "black_hole"), ("blackhole", "black_hole"), ("neutron", "star_neutron"), ("pulsar", "star_neutron"),
    ("dwarf", "star_browndwarf"), ("blue", "star_blue_giant"), ("red", "star_red_dwarf"), ("orange", "star_orange"),
    ("white", "star_white"), ("yellow", "star_yellow"),
    ("ice_giant", "ice_giant"), ("gas", "gas_giant"), ("giant", "gas_giant"), ("lava", "lava"), ("volcan", "lava"),
    ("toxic", "toxic"), ("acid", "toxic"), ("irradiated", "irradiated"), ("radiat", "irradiated"),
    ("cryo", "cryovolcanic"), ("frozen", "frozen"), ("ice", "frozen"), ("snow", "frozen"), ("tundra", "tundra"),
    ("jungle", "jungle"), ("water", "water"), ("ocean", "water"), ("terran", "terran"), ("earth", "terran"),
    ("desert", "desert"), ("arid", "arid"), ("rock", "rocky_metallic"), ("metal", "rocky_metallic"), ("barren", "barren"),
)


def nearest_vanilla_gen_row(type_id: str, name: str, vanilla_ids: set[str], is_star: bool) -> str | None:
    """The vanilla procgen row to copy for a mod planet or star type with none: the first keyword of its id or name,
    else barren / star_yellow. Frequency is zeroed after the copy, so only scripted placement uses it; the category
    picks the conditions a scripted planet rolls, and the choice is in the reviewed diff."""
    text = f"{type_id} {name}".lower()
    for keyword, row in _GEN_ROW_KEYWORDS:
        if keyword in text and row in vanilla_ids and row.startswith(("star_", "black_hole")) == is_star:
            return row
    fallback = "star_yellow" if is_star else "barren"
    return fallback if fallback in vanilla_ids else None


def _fix_procgen_row_missing(root: Path, finding_id: str, options: dict) -> list[FileChange]:
    vanilla_core = options.get("vanilla_core")
    type_id = options.get("type_id")
    from_vanilla_id = options.get("from_vanilla_id")
    if not vanilla_core:
        raise FixerError(f"--vanilla-core is required for {finding_id}.")
    if not type_id:
        raise FixerError(f"--type-id is required for {finding_id}.")
    if not from_vanilla_id:
        raise FixerError(f"--from-vanilla-id is required for {finding_id}.")

    is_star = finding_id == "procgen-star-row-missing"
    csv_name = "star_gen_data.csv" if is_star else "planet_gen_data.csv"
    freq_columns = ["freqYOUNG", "freqAVERAGE", "freqOLD"] if is_star else ["frequency"]

    vanilla_path = Path(vanilla_core).expanduser().resolve() / "data" / "campaign" / "procgen" / csv_name
    if not vanilla_path.is_file():
        raise FixerError(f"Vanilla {csv_name} not found at {vanilla_path}.")
    vanilla_text, _vanilla_bom = _decode(vanilla_path.read_bytes())
    vanilla_rows = list(csv.reader(io.StringIO(vanilla_text)))
    if not vanilla_rows:
        raise FixerError(f"{vanilla_path} has no header row.")
    header = vanilla_rows[0]
    normalized_header = [cell.strip() for cell in header]
    match_row: list[str] | None = None
    for row in vanilla_rows[1:]:
        if row and row[0].strip() == from_vanilla_id:
            match_row = row
            break
    if match_row is None:
        raise FixerError(f"No row with id '{from_vanilla_id}' found in vanilla {csv_name}.")

    new_row = list(match_row)
    if len(new_row) < len(header):
        new_row += [""] * (len(header) - len(new_row))
    new_row[0] = type_id
    for freq_col in freq_columns:
        if freq_col in normalized_header:
            new_row[normalized_header.index(freq_col)] = "0"

    mod_path = root / "data" / "campaign" / "procgen" / csv_name
    if mod_path.is_file():
        raw = mod_path.read_bytes()
        text, had_bom = _decode(raw)
        existing_ids = set()
        for row in csv.reader(io.StringIO(text)):
            if row and row[0].strip() and not row[0].strip().startswith("#"):
                existing_ids.add(row[0].strip())
        if type_id in existing_ids:
            raise FixerError(f"{mod_path} already has a row with id '{type_id}'.")
        prefix = "" if (not text or text.endswith(("\n", "\r"))) else "\n"
        new_text = text + prefix + _format_csv_row(new_row) + "\n"
        existed_before = True
    else:
        raw = b""
        had_bom = False
        new_text = _format_csv_row(header) + "\n" + _format_csv_row(new_row) + "\n"
        existed_before = False

    return [FileChange(path=mod_path, before=raw, after=_encode(new_text, had_bom), existed_before=existed_before)]


# ---------------------------------------------------------------------------
# Fixer: faction-known-lists-missing
# ---------------------------------------------------------------------------


def _fix_procgen_mod_body_leak(root: Path, options: dict) -> list[FileChange]:
    """Zero the procgen weight of each type `procgen-mod-body-leak` names (P15 item 25): the Zorg18 r3 fix as a
    fixer. Only the frequency fields of that type's row change; the row stays so nothing else loses the type."""
    by_file: dict[str, set[str]] = {}
    for finding in _findings_of(root, options, "procgen-mod-body-leak"):
        type_id = next((e.split(":", 1)[1] for e in finding.evidence if e.startswith("type:")), None)
        if type_id and finding.file:
            by_file.setdefault(finding.file, set()).add(type_id)
    columns = {"star_gen_data.csv": ("freqYOUNG", "freqAVERAGE", "freqOLD"), "planet_gen_data.csv": ("frequency",)}
    changes = []
    for relative, types in sorted(by_file.items()):
        path = root / relative
        if not path.is_file():
            continue
        raw = path.read_bytes()
        text, had_bom = _decode(raw)
        newline = "\r\n" if "\r\n" in text else "\n"
        lines = text.split(newline)
        header = next(csv.reader([lines[0]]))
        wanted = [header.index(c) for c in columns.get(path.name, ()) if c in header]
        for number, line in enumerate(lines[1:], 1):
            fields = next(csv.reader([line]), [])
            if fields and fields[0].strip() in types:
                spans = _line_field_spans(line)
                for index in sorted(wanted, reverse=True):
                    if index < len(spans):
                        start, end, _raw = spans[index]
                        line = line[:start] + "0" + line[end:]
                lines[number] = line
        changes.append(FileChange(path=path, before=raw, after=_encode(newline.join(lines), had_bom)))
    return changes
