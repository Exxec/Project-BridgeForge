"""94.G2: the static halves of a gene's two proofs (docs/FEATURE_GENOME_ROADMAP.md section 6), as WP5 evidence files.

**Subtraction.** A copy of the donor without the gene's members is scanned and compared with the donor's own scan, by the
references each finding names (its evidence lines), not by finding keys: `content-reference-unresolved` gathers every
unresolved reference of a mod into one finding, so a key-level diff would hide a new dangling reference inside an old
finding. Each new reference is
- a **dependent** when it names an id the gene provides: another feature of the donor uses the gene (the Ebirah hull has
  `sa_lobster_tanks` built in). That is an edge in the gene graph, recorded in the proof, not a closure error;
- a **leak** when it names something of the gene that is not an id it provides (its script class, a settings key, a
  sprite): the closure took something shared;
- **unexplained** otherwise.
PASS when every new reference is a dependent (advisor review 2026-11-19). Dependents are a fact about the donor, so they
are kept in the proof, not in gene.json.

**Isolation.** A carrier mod holding only the gene's members (its own mod_info.json with the donor's gameVersion and the
gene's mod needs as dependencies) is scanned. A finding the donor has for the same file is inherited; one about the
carrier's own mod_info.json is the carrier's. Anything else fails it, and so does a reference left unresolved that is
neither provided by the gene nor among its needs. The rule was chosen against P1's real carrier scan, which shows exactly
two findings: an inherited Janino risk and the carrier's mod_info version.

The copies are made without disturbing what the gene does not own: a CSV row is cut out of the table's text, a settings
key's line out of settings.json, so the rest of each file reads exactly as before. A key whose value spans lines is
removed by re-writing the file, and the proof says so. A jar-class member is removed from a zip copy, which is fine for
these static scans; the boot halves must rebuild jars with the JDK `jar` tool (house rule) and are not run here.

The boot halves (subtraction: the donor still boots; isolation: the carrier boots) need the test rig and are not written
until live testing runs them.
"""
from __future__ import annotations

import csv
import io
import json
import re
import shutil
import zipfile
from pathlib import Path

from bridgeforge.genome.closure import pointer
from bridgeforge.genome.evidence import header
from bridgeforge.genome.gene import describe, dumps
from bridgeforge.licence_ledger import member_file
from bridgeforge.mod_files import read_mod_info
from bridgeforge.safeio import atomic_write_text
from bridgeforge.scan.scan_json import _parse_json

CARRIER_FILES = ("mod_info.json",)
# The value must start on the key's line and not open an array or object (`\s*` must not backtrack past a `[`).
_KEY_LINE = r'^\s*"{key}"\s*:\s*(?![\s\[{{]).*?,?\s*(?:#.*|//.*)?$'


class ProofError(ValueError):
    """A gene whose members cannot be taken out of, or put into, a copy."""


def _rows_with_lines(text: str):
    """(row, first line, end line) per CSV record, lines counted from 0 over `text.splitlines(keepends=True)`."""
    reader = csv.reader(io.StringIO(text))
    start = 0
    for row in reader:
        yield row, start, reader.line_num
        start = reader.line_num


def cut_csv_row(text: str, ident: str) -> tuple[str, str]:
    """(table without the row, the row's own text). The id column is found from the header."""
    lines = text.splitlines(keepends=True)
    records = list(_rows_with_lines(text))
    if not records:
        raise ProofError("an empty table")
    header_row = [cell.strip() for cell in records[0][0]]
    if "id" not in header_row:
        raise ProofError("the table has no id column")
    column = header_row.index("id")
    for row, first, end in records[1:]:
        if len(row) > column and row[column].strip() == ident:
            return "".join(lines[:first] + lines[end:]), "".join(lines[first:end])
    raise ProofError(f"no row {ident!r}")


def cut_json_key(text: str, key: str) -> str | None:
    """settings.json without the line of one top-level key whose value fits on that line, or None when it does not."""
    pattern = re.compile(_KEY_LINE.format(key=re.escape(key)), re.MULTILINE)
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        return None
    match = matches[0]
    end = match.end() + (1 if text[match.end():match.end() + 1] == "\n" else 0)
    return text[:match.start()] + text[end:]


def subtract(root: Path, gene: dict, dest: Path) -> list[str]:
    """Copy the donor to `dest` without the gene's members; the notes say which files were re-written whole."""
    shutil.copytree(root, dest, ignore=shutil.ignore_patterns("reports"))
    notes = []
    for member in gene["members"]:
        path = member["path"]
        if member["what"] == "file":
            (dest / path).unlink()
        elif member["what"] == "csv-row":
            table, _, ident = path.partition(" [")
            target = dest / table
            text, _row = cut_csv_row(target.read_text(encoding="utf-8-sig"), ident.rstrip("]"))
            atomic_write_text(target, text, newline="")
        elif member["what"] == "json-entry":
            file, _, ptr = path.partition("#")
            target, key = dest / file, ptr[1:].replace("~1", "/").replace("~0", "~")
            text = target.read_text(encoding="utf-8-sig")
            cut = cut_json_key(text, key)
            if cut is None:
                data, _ = _parse_json(text)
                data.pop(key, None)
                cut = json.dumps(data, indent=2) + "\n"
                notes.append(f"{file} re-written whole to remove {pointer(key)} (its value spans lines)")
            atomic_write_text(target, cut, newline="")
        elif member["what"] == "jar-class":
            jar, _, entry = path.partition("!")
            _drop_jar_entry(dest / jar, entry)
            notes.append(f"{jar} copied without {entry} by zipfile (static scan only)")
    return notes


def _drop_jar_entry(jar: Path, entry: str) -> None:
    from bridgeforge.zipsafe import read_limited

    kept = jar.with_name(jar.name + ".tmp")
    with zipfile.ZipFile(jar) as source, zipfile.ZipFile(kept, "w", zipfile.ZIP_DEFLATED) as out:
        for item in source.infolist():
            if item.filename != entry:
                out.writestr(item, read_limited(source, item.filename))
    kept.replace(jar)


def build_carrier(root: Path, gene: dict, dest: Path) -> None:
    """An empty mod holding only the gene's members."""
    info = read_mod_info(root) or {}
    dest.mkdir(parents=True)
    carrier_info = {"id": f"gene_carrier_{gene['identity'][:12]}", "name": f"Gene carrier {gene['anchors'][0]}", "version": "0.0.1",
                    "gameVersion": info.get("gameVersion"), "dependencies": [{"id": mod} for mod in gene["needs"]["mods"]]}
    atomic_write_text((dest / "mod_info.json"), json.dumps(carrier_info, indent=2) + "\n", newline="")
    settings: dict[str, dict] = {}
    for member in gene["members"]:
        path = member["path"]
        if member["what"] == "file":
            (dest / path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / path, dest / path)
        elif member["what"] == "csv-row":
            table, _, ident = path.partition(" [")
            text = (root / table).read_text(encoding="utf-8-sig")
            _rest, row = cut_csv_row(text, ident.rstrip("]"))
            target = dest / table
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                atomic_write_text(target, text.splitlines(keepends=True)[0], newline="")
            with target.open("a", encoding="utf-8", newline="") as out:
                out.write(row if row.endswith("\n") else row + "\n")
        elif member["what"] == "json-entry":
            file, _, ptr = path.partition("#")
            data, _ = _parse_json((root / file).read_text(encoding="utf-8-sig"))
            key = ptr[1:].replace("~1", "/").replace("~0", "~")
            settings.setdefault(file, {})[key] = data[key]
        elif member["what"] == "jar-class":
            jar, _, entry = path.partition("!")
            from bridgeforge.zipsafe import read_limited

            with zipfile.ZipFile(root / jar) as source:
                data = read_limited(source, entry)
            (dest / jar).parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(dest / jar, "a" if (dest / jar).exists() else "w", zipfile.ZIP_DEFLATED) as out:
                out.writestr(entry, data)
    for file, values in settings.items():
        (dest / file).parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text((dest / file), json.dumps(values, indent=2) + "\n", newline="")


def _references(result) -> dict[tuple[str, str], set[str]]:
    """{(finding id, file): the lines it names} for every finding; a finding with no evidence names its explanation."""
    found: dict[tuple[str, str], set[str]] = {}
    for finding in result.findings:
        found.setdefault((finding.id, finding.file or ""), set()).update(finding.evidence or [finding.explanation])
    return found


def _new_references(before, after) -> list[tuple[tuple[str, str], str]]:
    old = _references(before)
    return sorted((key, line) for key, lines in _references(after).items() for line in lines - old.get(key, set()))


def _id_named(line: str, ident: str) -> bool:
    """`ident` as a whole word of `line`; a dot before it is a boundary, so `data.hullmods.tank_script` names `tank_script`."""
    return re.search(rf"(?<!\w){re.escape(ident)}(?!\w)", line) is not None


def _gene_names(gene: dict) -> list[str]:
    """What else of the gene a reference could name: member file stems, settings keys, class names."""
    names = set()
    for member in gene["members"]:
        path = member["path"]
        if member["what"] == "json-entry":
            names.add(path.partition("#")[2][1:])
        elif member["what"] == "jar-class":
            names.add(Path(path.partition("!")[2]).stem)
        else:
            names.add(Path(member_file(path)).stem)
    return sorted(names - {p.split(":", 1)[1] for p in gene["provides"]})


def classify_subtraction(before, after, gene: dict, used_by: list[dict]) -> dict:
    dependents, leaks, unexplained = [], [], []
    others = _gene_names(gene)
    for key, line in _new_references(before, after):
        provided = [p for p in gene["provides"] if _id_named(line, p) or _id_named(line, p.split(":", 1)[1])]
        if provided:
            sources = sorted(u["path"] for u in used_by if any(p.split(":", 1)[1] in u["mentions"] for p in provided))
            dependents += [{"from": source, "to": p} for p in provided for source in (sources or ["(not located)"])]
        elif any(_id_named(line, name) for name in others):
            leaks.append({"finding": key[0], "file": key[1], "reference": line})
        else:
            unexplained.append({"finding": key[0], "file": key[1], "reference": line})
    dependents = [dict(t) for t in sorted({tuple(sorted(d.items())) for d in dependents})]
    return {"verdict": "FAIL" if leaks or unexplained else "PASS", "dependents": dependents, "leaks": leaks, "unexplained": unexplained}


def classify_isolation(donor, carrier, gene: dict) -> dict:
    donor_keys = set(_references(donor))
    allowed = set(gene["provides"]) | set(gene["needs"]["vanilla"])
    inherited, carrier_own, failures = [], [], []
    for (finding, file), lines in sorted(_references(carrier).items()):
        if file in CARRIER_FILES:
            carrier_own.append({"finding": finding, "file": file})
        elif (finding, file) in donor_keys:
            inherited.append({"finding": finding, "file": file})
        elif finding == "content-reference-unresolved":
            unresolved = [line for line in sorted(lines) if not any(_id_named(line, ident) for ident in allowed)]
            failures += [{"finding": finding, "file": file, "reference": line} for line in unresolved]
        else:
            failures += [{"finding": finding, "file": file, "reference": line} for line in sorted(lines)]
    return {"verdict": "FAIL" if failures else "PASS", "inherited": inherited, "carrier_own": carrier_own, "failures": failures}


def prove(mod: Path, anchor: str, out: Path, *, vanilla_core: Path | None = None) -> dict:
    """Write gene.json and the static subtraction and isolation proofs of one gene into `out` (outside the repository)."""
    from bridgeforge.models import TargetProfile
    from bridgeforge.scan.scanner import scan_mod
    from bridgeforge.vendor_plan import vendor_plan

    out, mod = Path(out), Path(mod)
    vanilla_core = Path(vanilla_core) if vanilla_core is not None else None
    if out.exists() and any(out.iterdir()):
        raise ProofError(f"{out} is not empty: proofs go into a fresh folder")
    gene = describe(mod, anchor, vanilla_core=vanilla_core)
    plan = vendor_plan(mod, [anchor], vanilla_core=vanilla_core)
    root = Path(plan["provider"])
    work = out / "work"
    notes = subtract(root, gene, work / "subtraction")
    build_carrier(root, gene, work / "carrier")
    donor_scan = scan_mod(root, TargetProfile(), vanilla_core)
    subtraction = classify_subtraction(donor_scan, scan_mod(work / "subtraction", TargetProfile(), vanilla_core), gene, plan["used_by"])
    isolation = classify_isolation(donor_scan, scan_mod(work / "carrier", TargetProfile(), vanilla_core), gene)
    inputs = [("member", path) for path in sorted({member_file(m["path"]) for m in gene["members"]})]
    atomic_write_text(out / "gene.json", dumps(gene), newline="")
    written = {}
    for kind, body, extra in (("subtraction-proof", subtraction, {"rewritten": notes}), ("isolation-proof", isolation, {})):
        made = {**header(kind, gene, root=root, inputs=inputs, verdict=body["verdict"]), "half": "static", **body, **extra,
                "boot": "NOT_RUN: needs the test rig; written by the live run when it happens"}
        atomic_write_text(out / f"{kind}.json", json.dumps(made, indent=2, ensure_ascii=False) + "\n", newline="")
        written[kind] = body["verdict"]
    return {"gene": gene["identity"], "root": str(root), "verdicts": written, "out": str(out)}


__all__ = ["ProofError", "build_carrier", "classify_isolation", "classify_subtraction", "cut_csv_row", "cut_json_key", "prove", "subtract"]
