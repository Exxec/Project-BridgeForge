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
removed by re-writing the file (non-ASCII kept as text), and the proof says so. A jar that loses classes is written fresh
from the donor's jar by copying each kept entry's ZipInfo, the method `patch-jar-class` uses; the jar that loaded no class
in 2026-10 came from .NET ZipArchive's Update mode, not this. So the boot halves can stage these copies byte for byte.

**Star systems (slice 7, 2026-11-20).** The registration is an element, not a member, so subtraction leaves the donor's plugin
calling the removed generator: a new reference naming the generator is classified as the `registration`, and the proof lists
the call sites (`registration_sites`). Such a donor cannot boot until slice 8 cuts the call, and its boot note says so. The
carrier gets a generated plugin making the recorded call (`genome/carrier_plugin.py`), and every carrier's mod_info lists the
jars it holds (the game loads only listed jars). A gene need (`needs.genes`) may stay unresolved in the carrier, like a
vanilla need; the carrier's boot then waits for that gene.

The boot halves (subtraction: the donor still boots; isolation: the carrier boots) need the test rig and are not written
until live testing runs them.
"""
from __future__ import annotations

import json
import re
import shutil
import zipfile
from pathlib import Path

from bridgeforge import game_csv
from bridgeforge.genome import carrier_plugin
from bridgeforge.genome.carrier_plugin import CarrierPluginRefused
from bridgeforge.genome.evidence import header
from bridgeforge.genome.gene import TABLE_KEYS, describe, dumps
from bridgeforge.licence_ledger import member_file
from bridgeforge.mod_files import read_mod_info
from bridgeforge.safeio import atomic_write_text
from bridgeforge.scan.scan_json import _parse_json

CARRIER_FILES = ("mod_info.json",)
# The value must start on the key's line and not open an array or object (`\s*` must not backtrack past a `[`).
_KEY_LINE = r'^\s*"{key}"\s*:\s*(?![\s\[{{]).*?,?\s*(?:#.*|//.*)?$'


class ProofError(ValueError):
    """A gene whose members cannot be taken out of, or put into, a copy."""


def cut_csv_row(text: str, ident: str, key: str = "id") -> tuple[str, str]:
    """(table without the row, the row's own text). The key column (`gene.TABLE_KEYS`, else `id`) is found from the header:
    factions.csv rows are keyed by `faction` (slice 11). The row is one the game keeps: a commented row with the same id is
    left in place (RC8-47, slice 16). Lines are counted as csv counts them, not by str.splitlines, which also breaks at a
    form feed or a Unicode line separator inside a quoted cell."""
    physical = game_csv.lines(text)
    found = list(game_csv.records(text))
    if not found:
        raise ProofError("an empty table")
    header_row = [cell.strip() for cell in found[0][0]]
    if key not in header_row:
        raise ProofError(f"the table has no {key} column")
    column = header_row.index(key)
    for row, first, end, commented in found[1:]:
        if not commented and len(row) > column and row[column].strip() == ident:
            return "".join(physical[:first] + physical[end:]), "".join(physical[first:end])
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


def pointer_tokens(ptr: str) -> list[str]:
    """The keys a JSON Pointer walks (RFC 6901: `~1` is `/`, `~0` is `~`)."""
    return [token.replace("~1", "/").replace("~0", "~") for token in ptr[1:].split("/")]


def _nested_get(data: dict, tokens: list[str]) -> object:
    for token in tokens:
        data = data[token]
    return data


def _nested_pop(data: dict, tokens: list[str]) -> None:
    for token in tokens[:-1]:
        data = data.get(token, {}) if isinstance(data, dict) else {}
    if isinstance(data, dict):
        data.pop(tokens[-1], None)


def _nested_set(data: dict, tokens: list[str], value: object) -> None:
    for token in tokens[:-1]:
        data = data.setdefault(token, {})
    data[tokens[-1]] = value


def subtract(root: Path, gene: dict, dest: Path) -> list[str]:
    """Copy the donor to `dest` without the gene's members; the notes say which files were re-written whole. A jar that
    loses classes is not copied and then rewritten (a just-copied jar can be held open by a scanner on Windows: P2,
    2026-11-19): it is written once, fresh, from the donor's jar without those entries."""
    dropped: dict[str, set[str]] = {}
    for member in gene["members"]:
        if member["what"] == "jar-class":
            jar, _, entry = member["path"].partition("!")
            dropped.setdefault(jar, set()).add(entry)
    skip = {(Path(root) / jar).resolve() for jar in dropped}

    def ignore(folder: str, names: list[str]) -> set[str]:
        # reports/ is copied too: the scanner reads it (src-to-jar's build record), and leaving it out made every edited
        # source read as "not rebuilt" in P2's subtraction copy (2026-11-19).
        return {n for n in names if (Path(folder) / n).resolve() in skip}

    shutil.copytree(root, dest, ignore=ignore)
    notes = []
    for jar, entries in sorted(dropped.items()):
        _write_jar_without(Path(root) / jar, dest / jar, entries)
        notes.append(f"{jar} written without {len(entries)} class(es) of the gene by zipfile (static scan only)")
    # The build source of a removed class is the same code (P2, 2026-11-19: left in src/, the scanner reported the jar and its
    # sources out of step). It goes too, and the proof says which files.
    outer = {entry.split("$", 1)[0].removesuffix(".class") for entries in dropped.values() for entry in entries}
    for source in sorted(_build_sources(dest, outer)):
        source.unlink()
        notes.append(f"{source.relative_to(dest).as_posix()} removed with its class (build source)")
    # Slice 20 review: a member that is also a donor need (the gene's hull sprite that a shared style names as a cover) is
    # kept: other donor content still loads it. Compared casefolded, as the game's Windows file reads are.
    needed = {p.casefold() for p in (gene.get("needs") or {}).get("donor") or []}
    for member in gene["members"]:
        path = member["path"]
        if path.casefold() in needed:
            notes.append(f"{path} kept: a member that is also a donor need")
            continue
        if member["what"] == "file":
            (dest / path).unlink()
        elif member["what"] == "csv-row":
            table, _, ident = path.partition(" [")
            target = dest / table
            text, _row = cut_csv_row(target.read_text(encoding="utf-8-sig"), ident.rstrip("]"))
            atomic_write_text(target, text, newline="")
        elif member["what"] == "json-entry":
            file, _, ptr = path.partition("#")
            target, tokens = dest / file, pointer_tokens(ptr)
            text = target.read_text(encoding="utf-8-sig")
            cut = cut_json_key(text, tokens[0]) if len(tokens) == 1 else None  # a nested key's line is not cut by text
            if cut is None:
                data, _ = _parse_json(text)
                _nested_pop(data, tokens)
                # Non-ASCII stays text: escaped, Eridani's CJK designTypeColors key stopped matching its manufacturer
                # (P3, 2026-11-20).
                cut = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
                why = "a nested key" if len(tokens) > 1 else "its value spans lines"
                notes.append(f"{file} re-written whole to remove {ptr} ({why})")
            atomic_write_text(target, cut, newline="")
    return notes


_PACKAGE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.MULTILINE)


def _build_sources(root: Path, classes: set[str]) -> list[Path]:
    """The `.java` files under `root` whose package and name are one of `classes` (internal names, `a/b/C`)."""
    found = []
    for source in Path(root).rglob("*.java"):
        package = _PACKAGE.search(source.read_text(encoding="utf-8-sig", errors="replace"))
        name = (package.group(1).replace(".", "/") + "/" if package else "") + source.stem
        if name in classes:
            found.append(source)
    return found


def _write_jar_without(source_jar: Path, target: Path, entries: set[str]) -> None:
    from bridgeforge.zipsafe import read_limited

    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source_jar) as source, zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as out:
        for item in source.infolist():
            if item.filename not in entries:
                out.writestr(item, read_limited(source, item.filename))


def build_carrier(root: Path, gene: dict, dest: Path, *, vanilla_core: Path | None = None, work: Path | None = None) -> dict | None:
    """An empty mod holding only the gene's members. Its mod_info lists the jars it holds: the game loads only listed jars, and
    P2's carrier (2026-11-19) listed none, so a boot would have loaded no class. A star-system gene's carrier also gets a
    generated plugin making the recorded call (`genome/carrier_plugin.py`); its record is returned, else None."""
    info = read_mod_info(root) or {}
    dest.mkdir(parents=True)
    # RC7's ModManager.loadModSpec reads `id`, `name` and `description` with JSONObject.getString (javap 2026-11-20): without
    # `description` the carrier never loaded (P1B-CAR-20261120: "JSONObject["description"] not found"). RC8_BEHAVIOUR RC8-45.
    carrier_info = {"id": f"gene_carrier_{gene['identity'][:12]}", "name": f"Gene carrier {gene['anchors'][0]}", "version": "0.0.1",
                    "author": "BridgeForge gene proof", "description": f"Isolation carrier for {gene['anchors'][0]} (94.G2).",
                    "gameVersion": info.get("gameVersion"), "dependencies": [{"id": mod} for mod in gene["needs"]["mods"]]}
    settings: dict[str, dict] = {}
    # Slice 20: donor parts the gene needs and does not own (a shared hull style and its files) are copied too.
    donor = [{"what": "json-entry" if member_file(path) != path else "file", "path": path}  # `cover#1.png` is a file
             for path in (gene.get("needs") or {}).get("donor") or []]
    for member in [*gene["members"], *donor]:
        path = member["path"]
        if member["what"] == "file":
            (dest / path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / path, dest / path)
        elif member["what"] == "csv-row":
            table, _, ident = path.partition(" [")
            text = (root / table).read_text(encoding="utf-8-sig")
            _rest, row = cut_csv_row(text, ident.rstrip("]"), TABLE_KEYS.get(table, "id"))
            target = dest / table
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                atomic_write_text(target, text.splitlines(keepends=True)[0], newline="")
            with target.open("a", encoding="utf-8", newline="") as out:
                out.write(row if row.endswith("\n") else row + "\n")
        elif member["what"] == "json-entry":
            file, _, ptr = path.partition("#")
            data, _ = _parse_json((root / file).read_text(encoding="utf-8-sig"))
            tokens = pointer_tokens(ptr)
            _nested_set(settings.setdefault(file, {}), tokens, _nested_get(data, tokens))
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
        atomic_write_text((dest / file), json.dumps(values, indent=2, ensure_ascii=False) + "\n", newline="")
    plugin = None
    if gene["kind"] == "star-system":
        plugin = carrier_plugin.build(dest, gene["registrations"], vanilla_core, Path(work) if work else dest.parent)
        carrier_info["modPlugin"] = plugin["class"]
    jars = sorted(path.relative_to(dest).as_posix() for path in dest.rglob("*.jar"))
    if jars:
        carrier_info["jars"] = jars
    atomic_write_text((dest / "mod_info.json"), json.dumps(carrier_info, indent=2) + "\n", newline="")
    return plugin


def registered_classes(gene: dict) -> list[str]:
    """The classes the gene's registrations name: a combat plugin's class, or a star system's generator (`statement` is
    `<class>: <methods called>`)."""
    return sorted({element["statement"].split(":", 1)[0].strip() for element in gene["registrations"]})


def boot_note(kind: str, gene: dict, cut: dict | None = None) -> str:
    """What the boot half of one proof needs, said honestly before the rig runs it. `cut` is the subtraction copy's
    registration cut (slice 8): when it was made, the subtracted donor can boot."""
    if kind == "subtraction-proof" and gene["kind"] == "star-system" and not (cut and cut.get("cut")):
        why = f" (the cut was refused: {cut['refused']})" if cut and cut.get("refused") else ""
        return ("NOT_RUN: the donor's plugin still calls the removed generator (the recorded registrations); booting the "
                f"donor without the gene needs that call cut (94.G2 slice 8){why}")
    genes = gene["needs"].get("genes") or []
    if kind == "isolation-proof" and genes:
        return (f"NOT_RUN: the carrier needs {', '.join(genes)}, a gene not closable yet; it cannot take the donor instead "
                "(the donor would generate the gene a second time)")
    return "NOT_RUN: needs the test rig; written by the live run when it happens"


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


# A scanner's own totals inside a finding's evidence ("differ:0", "source-only:9", "common prefix: x_ (3 ids)"): counts, not
# references to anything (P2, 2026-11-19). Set aside as summaries when they name nothing of the gene.
_PROSE = re.compile(r"^[A-Za-z][A-Za-z ,']*$")  # a qualifier in words: no id, path, number or punctuation an id carries
_SUMMARY_LINE = re.compile(r"^(?:[\w -]+:\s*\d+|.*\(\d+ ids?\)|common prefix: .*)$")


def classify_subtraction(before, after, gene: dict, used_by: list[dict]) -> dict:
    """PASS when every new reference is a dependent, a summary or, for a star system, its registration: the donor's plugin
    calling the removed generator (the gene records that call site; slice 8 cuts it)."""
    dependents, leaks, unexplained, summaries, registrations = [], [], [], [], []
    dependent_keys: set[tuple[str, str]] = set()
    others = _gene_names(gene)
    system = gene.get("kind") == "star-system"  # a partial gene (no kind) is not a star system
    qualified = {form for cls in registered_classes(gene) for form in (cls, cls.replace(".", "/"))} if system else set()
    simple = {cls.rsplit(".", 1)[-1] for cls in registered_classes(gene)} if system else set()
    for key, line in _new_references(before, after):
        # A simple name ("Via") may be any word of a line, so it counts only in an import or class finding (review
        # 2026-11-20: a faction or row named like the generator was filed as the registration, a false PASS).
        names = qualified | (simple if re.search(r"import|class", key[0]) else set())
        if any(_id_named(line, name) for name in names):
            registrations.append({"finding": key[0], "file": key[1], "reference": line})
            continue
        if _SUMMARY_LINE.match(line.strip()) and not any(_id_named(line, p.split(":", 1)[1]) for p in gene["provides"]):
            summaries.append({"finding": key[0], "file": key[1], "line": line})
            continue
        provided = [p for p in gene["provides"] if _id_named(line, p) or _id_named(line, p.split(":", 1)[1])]
        if provided:
            sources = sorted(u["path"] for u in used_by if any(p.split(":", 1)[1] in u["mentions"] for p in provided))
            dependents += [{"from": source, "to": p} for p in provided for source in (sources or ["(not located)"])]
            dependent_keys.add(key)
        elif any(_id_named(line, name) for name in others):
            leaks.append({"finding": key[0], "file": key[1], "reference": line})
        else:
            unexplained.append({"finding": key[0], "file": key[1], "reference": line})
    # One finding's lines are judged together: when a line names what the gene provides, the finding's location line
    # ("mission:data/missions/testbed/MissionDefinition.java") and its plain-prose qualifiers ("no mod under the provider roots
    # defines it") are context, not references (slice 9: the testbed mission's finding failed the whole-lobster proof on them).
    # Anything id-like stays unexplained: a broad finding naming one provided id must not absolve its other lines (review).
    def is_context(item: dict) -> bool:
        line = item["reference"].strip()
        located = bool(item["file"]) and line.endswith(item["file"])
        return (item["finding"], item["file"]) in dependent_keys and (located or _PROSE.match(line) is not None)

    context = [u for u in unexplained if is_context(u)]
    unexplained = [u for u in unexplained if not is_context(u)]
    dependents = [dict(t) for t in sorted({tuple(sorted(d.items())) for d in dependents})]
    sites = [{"locus": e["locus"], "statement": e["statement"], "status": "left in the donor, calling the removed generator"}
             for e in gene["registrations"]] if system else []
    return {"verdict": "FAIL" if leaks or unexplained else "PASS", "dependents": dependents, "leaks": leaks, "unexplained": unexplained,
            "summaries": summaries, "registrations": registrations, "registration_sites": sites, "context": context}


def classify_isolation(donor, carrier, gene: dict) -> dict:
    donor_keys = set(_references(donor))
    allowed = set(gene["provides"]) | set(gene["needs"]["vanilla"]) | set(gene["needs"].get("genes") or [])
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


def prove(mod: Path, anchor: str, out: Path, *, vanilla_core: Path | None = None, provider_roots: list[Path] | None = None) -> dict:
    """Write gene.json and the static subtraction and isolation proofs of one gene into `out` (outside the repository). For a
    star system the registration is cut from the subtraction copy when every step can be shown (slice 8,
    genome/registration_cut.py; `provider_roots` hold the libraries its source imports)."""
    from bridgeforge.models import TargetProfile
    from bridgeforge.scan.scanner import scan_mod
    from bridgeforge.vendor_plan import vendor_plan

    out, mod = Path(out), Path(mod)
    vanilla_core = Path(vanilla_core) if vanilla_core is not None else None
    if out.exists() and any(out.iterdir()):
        raise ProofError(f"{out} is not empty: proofs go into a fresh folder")
    if anchor.startswith("faction:"):
        raise ProofError("a faction gene's own proofs are not built (its subtraction cuts a factions.csv row keyed by its "
                         "`faction` column): `gene describe` closes it, and `gene prove-set` carries it with every gene it needs")
    gene = describe(mod, anchor, vanilla_core=vanilla_core)
    # Who in the donor uses the gene: vendor-plan from the gene's content ids and the classes it registers (a combat
    # plugin's anchor is not a vendor-plan id).
    from bridgeforge.vendor_plan import KINDS

    plan = vendor_plan(mod, [p for p in gene["provides"] if p.split(":", 1)[0] in KINDS], vanilla_core=vanilla_core,
                       classes=registered_classes(gene))
    root = Path(plan["provider"])
    work = out / "work"
    notes = subtract(root, gene, work / "subtraction")
    cut = None
    if gene["kind"] == "star-system":
        from bridgeforge.genome.registration_cut import cut_registrations

        cut = cut_registrations(root, work / "subtraction", gene, vanilla_core, [Path(p) for p in provider_roots or []])
    try:
        plugin = build_carrier(root, gene, work / "carrier", vanilla_core=vanilla_core, work=work)
    except CarrierPluginRefused as refused:
        raise ProofError(f"the carrier cannot make the gene's registered call: {refused}") from refused
    donor_scan = scan_mod(root, TargetProfile(), vanilla_core)
    subtraction = classify_subtraction(donor_scan, scan_mod(work / "subtraction", TargetProfile(), vanilla_core), gene, plan["used_by"])
    from bridgeforge.genome.dependents import graded

    subtraction["dependents"] = graded(gene, subtraction["dependents"], vanilla_core, [Path(p) for p in provider_roots or []], root)
    if cut and cut.get("cut"):
        for site in subtraction["registration_sites"]:
            site["status"] = "cut from the copy's build source and class (registration_cut)"
    isolation = classify_isolation(donor_scan, scan_mod(work / "carrier", TargetProfile(), vanilla_core), gene)
    # Slice 15: the scan alone passed knock-outs (slice 12), so the carrier must also define everything the gene provides. Its
    # needs.genes are not carried by a single gene's carrier, by design.
    from bridgeforge.genome.gene_set import unresolved_in_carrier

    isolation["unresolved_in_carrier"] = unresolved_in_carrier(work / "carrier", {anchor: {**gene, "needs": {**gene["needs"], "genes": []}}})
    if isolation["unresolved_in_carrier"]:
        isolation["verdict"] = "FAIL"
    from bridgeforge.genome.carrier_load import dependency_folders, load_gaps

    # Slice 19: what the game needs to load the carrier (RC8-49). Without the core a vanilla style cannot be told from an
    # undefined one, so the check does not run (review of slice 19); a declared dependency's styles and files count.
    if vanilla_core is None:
        isolation["load_gaps"] = subtraction["load_gaps"] = ("NOT_RUN: no --vanilla-core, so a hull's vanilla style cannot be "
                                                             "told from an undefined one")
    else:
        deps = dependency_folders([Path(p) for p in provider_roots or []], gene["needs"]["mods"])
        isolation["load_gaps"] = load_gaps(work / "carrier", vanilla_core, deps)
        if isolation["load_gaps"]:
            isolation["verdict"] = "FAIL"
        # Slice 20 review: the subtraction copy must load as the donor does. Only gaps the donor lacks count: one it already
        # has is not the gene's to fix.
        before = {json.dumps(g, sort_keys=True) for g in load_gaps(root, vanilla_core, deps, code=False)}
        subtraction["load_gaps"] = [g for g in load_gaps(work / "subtraction", vanilla_core, deps, code=False)
                                    if json.dumps(g, sort_keys=True) not in before]
        if subtraction["load_gaps"]:
            subtraction["verdict"] = "FAIL"
    inputs = [("member", path) for path in sorted({member_file(m["path"]) for m in gene["members"]})]
    # Slice 20: the donor parts it needs are inputs too: they are not in the identity, so a changed style would leave stale
    # evidence looking valid (advisor 2026-11-23).
    inputs += [("need", path) for path in sorted({member_file(p) for p in gene["needs"].get("donor") or []} - {i[1] for i in inputs})]
    atomic_write_text(out / "gene.json", dumps(gene), newline="")
    written = {}
    halves = (("subtraction-proof", subtraction, {"rewritten": notes, **({"registration_cut": cut} if cut else {})}),
              ("isolation-proof", isolation, {"carrier_plugin": plugin} if plugin else {}))
    for kind, body, extra in halves:
        made = {**header(kind, gene, root=root, inputs=inputs, verdict=body["verdict"]), "half": "static", **body, **extra,
                "boot": boot_note(kind, gene, cut)}
        atomic_write_text(out / f"{kind}.json", json.dumps(made, indent=2, ensure_ascii=False) + "\n", newline="")
        written[kind] = body["verdict"]
    return {"gene": gene["identity"], "root": str(root), "verdicts": written, "out": str(out)}


__all__ = ["ProofError", "boot_note", "build_carrier", "registered_classes", "classify_isolation", "classify_subtraction", "cut_csv_row", "cut_json_key", "pointer_tokens", "prove", "subtract"]
