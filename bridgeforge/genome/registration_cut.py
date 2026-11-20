"""94.G2 slice 8: cut a star-system gene's registration out of the subtraction copy, so the donor without the gene can boot.

The gene's registration is the donor plugin's call into the generator (genome/campaign.py). Subtraction removes the generator,
so the copy's plugin still calls a class that is gone: the game would fail at New Game. This removes that call from the call
site's build source in the copy, recompiles it, and puts the class into the copy's jar. It is done only when each step is
shown, and refused otherwise (the proof then keeps its "needs the call cut" boot note):

1. **The source is the shipped class.** The donor's own build source of the call site, compiled against the donor's own
   classpath for the shipped class's Java release, gives the shipped class instruction for instruction (javap, constant-pool
   numbers aside). Eridani's ECEModPlugin.java did, 2026-11-20.
2. **Only whole statements go.** A line naming the generator may only be its `import` or `new <Generator>().<method>(...);`
   with the recorded method, and the line before such a call must end a statement or open or close a block (after a bare
   `if (c)` the call is the whole body, and cutting it would make the next statement the body). Any other mention refuses.
3. **The cut is complete.** The cut source compiles against the copy, which no longer has the generator.
4. **Nothing else changed.** Against step 1's class, the cut class's javap only loses lines (instruction offsets aside), and
   none of what is left names the generator.

Every site is planned in a temp folder first; nothing in the copy is written until all pass. Then the jars (written fresh by
copying each entry's ZipInfo, the method `patch-jar-class` uses) and the sources are written, and a failure puts back what
was written from the bytes held in memory: the copy is fully cut or as subtraction made it (review 2026-11-20: a restore by
delete-and-copy could itself fail on a locked jar and lose the backup). Provider roots are folders of mods holding the
libraries the source imports (a rig's `mods/`), as `assemble_classpath` takes them.
"""
from __future__ import annotations

import difflib
import re
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path

# An instruction line's offset (`12: invokevirtual`); a switch table's `1: 40` keeps its case value and target (review
# 2026-11-20: stripping it let different case labels compare equal).
_OFFSET = re.compile(r"^\d+:\s+(?=[a-z])")
_POOL_INDEX = re.compile(r"#\d+(?:,\s*\d+)?")
_JUMP = re.compile(r"^((?:if\w*|goto(?:_w)?|jsr(?:_w)?)\s+)\d+")  # a branch's target offset
# The line before a cut call must end a statement or open or close a block. After `if (c)`, `else`, `while (...)`, `for
# (...)`, `do` or a label the call is the only body, and cutting it would make the next statement the body: a change that
# javap cannot show, since jump targets are compared as labels (review 2026-11-20).
_STATEMENT_BOUNDARY = (";", "{", "}")
_COMMENT = re.compile(r"^\s*(?://|/\*|\*)")
_CHECKS = ["the donor's source compiles to the shipped class (javap)",
           "only the import and whole call statements removed, each after a statement or block boundary",
           "the cut source compiles without the generator", "the cut class only lost lines (javap)"]


class CutRefused(ValueError):
    """The registration cannot be cut with every step shown."""


def javap_lines(javap: Path, class_file: Path) -> list[str]:
    """`javap -c -p`, each line by meaning (`normalise`): removing a call shortens its method, so every later jump target moves
    (Eridani: `ifnull 110`)."""
    try:
        done = subprocess.run([str(javap), "-c", "-p", str(class_file)], capture_output=True, text=True, check=False)
    except OSError as error:
        raise CutRefused(f"javap could not be started: {error}") from error
    if done.returncode != 0:
        raise CutRefused(f"javap could not read {class_file.name}: {done.stderr.strip()[:200]}")
    return [normalise(line) for line in done.stdout.splitlines() if line.strip() and not line.startswith("Compiled from")]


def normalise(line: str) -> str:
    """One javap line by meaning: no instruction offset, no pool index, a jump target as `L`, and one space for any run (javap
    pads its comment column after the pool index, so `#99` and `#100` pad differently: Eridani's RepLevel getstatic)."""
    line = _POOL_INDEX.sub("#", _OFFSET.sub("", line.strip()))
    return re.sub(r"\s+", " ", _JUMP.sub(r"\1 L", line))


def only_lost_lines(before: list[str], after: list[str]) -> list[str]:
    """The lines `after` has that `before` does not, by a strict alignment (no junk heuristic): empty when the cut only removed."""
    matcher = difflib.SequenceMatcher(None, before, after, autojunk=False)
    return [line for tag, _i1, _i2, j1, j2 in matcher.get_opcodes() if tag in ("insert", "replace") for line in after[j1:j2]]


def cut_lines(text: str, generator: str, method: str) -> tuple[str, list[str]]:
    """(the source without the generator's import and its `new G().method(...);` statements, the removed lines)."""
    simple = generator.rsplit(".", 1)[-1]
    import_line = re.compile(rf"^\s*import\s+{re.escape(generator)}\s*;\s*$")
    call_line = re.compile(rf"^\s*new\s+(?:{re.escape(generator)}|{re.escape(simple)})\s*\(\s*\)\s*\.\s*{re.escape(method)}\s*"
                           rf"\([^;{{}}]*\)\s*;\s*(?://.*)?$")
    kept, removed, calls, previous = [], [], 0, ""
    for line in text.splitlines(keepends=True):
        bare = line.rstrip("\r\n")
        if re.search(rf"(?<![\w$]){re.escape(simple)}(?![\w$])", line):
            if call_line.match(bare):
                if not previous.endswith(_STATEMENT_BOUNDARY):
                    raise CutRefused(f"`{line.strip()[:80]}` follows `{previous[-60:]}`: it may be the only body of an if, else, "
                                     "loop or label, and cutting it would change what runs")
                calls += 1
            elif not import_line.match(bare):
                raise CutRefused(f"a line names {simple} and is not its import or `new {simple}().{method}(...);`: "
                                 f"{line.strip()[:120]}")
            removed.append(line.strip())
            continue
        kept.append(line)
        code = re.sub(r"//.*$", "", bare).strip()
        if code and not _COMMENT.match(bare):
            previous = code
    if not calls:
        raise CutRefused(f"no `new {simple}().{method}(...);` statement was found to cut")
    return "".join(kept), removed


def _compile(source: Path, classpath: str, release: str | None, out: Path, internal: str) -> Path:
    from bridgeforge.bytecode.java_toolchain import find_jdk, run_javac

    jdk = find_jdk()
    if jdk is None:
        raise CutRefused("no JDK found")
    try:
        run = run_javac(jdk.javac, classpath, [source], out, release=release)
    except OSError as error:
        raise CutRefused(f"javac could not be started: {error}") from error
    if run.returncode != 0:
        first = (run.errors[0].get("message") if run.errors else None) or run.stderr.strip()[:200]
        raise CutRefused(f"javac: {first}")
    built = out / f"{internal}.class"
    if not built.is_file():
        raise CutRefused(f"javac wrote no {internal}.class")
    return built


def _jar_holding(root: Path, entry: str) -> Path:
    from bridgeforge.genome.gene import _loaded_classes

    jar = _loaded_classes(root).get(entry)
    if jar is None:
        raise CutRefused(f"no loaded jar of {root.name} holds {entry}")
    return root / jar


def plan_site(donor: Path, copy: Path, element: dict, vanilla_core: Path | None, provider_roots: list[Path], work: Path) -> dict:
    """Everything one site's cut needs, worked out in `work`: nothing in `copy` is written here. Returns the record plus the
    planned writes (`source_path`, `source_text`, `jar`, `entry`, `data`)."""
    import hashlib
    import os

    from bridgeforge.bytecode.java_toolchain import assemble_classpath, class_release, find_jdk
    from bridgeforge.genome.proof import _build_sources
    from bridgeforge.zipsafe import read_limited

    owner = element["locus"].rsplit(".", 1)[0]
    generator, _, called = element["statement"].partition(":")
    generator = generator.strip()
    methods = [m.strip() for m in called.split(",") if m.strip() and m.strip() != "<init>"]
    if len(methods) != 1:
        raise CutRefused(f"{element['statement']}: one method call is cut, not {len(methods)}")
    internal, entry = owner.replace(".", "/"), owner.replace(".", "/") + ".class"
    donor_sources, copy_sources = _build_sources(donor, {internal}), _build_sources(copy, {internal})
    if len(donor_sources) != 1 or len(copy_sources) != 1:
        raise CutRefused(f"{owner}: {len(donor_sources)} build source(s) in the donor, {len(copy_sources)} in the copy; one is cut")
    jdk = find_jdk()
    if jdk is None:
        raise CutRefused("no JDK found")
    with zipfile.ZipFile(_jar_holding(donor, entry)) as archive:
        shipped = read_limited(archive, entry)
    release = class_release(shipped)
    site = work / f"site-{len(list(work.iterdir()))}"
    site.mkdir()
    (site / "shipped.class").write_bytes(shipped)
    rebuilt = _compile(donor_sources[0], os.pathsep.join(assemble_classpath(donor, vanilla_core, provider_roots).entries()),
                       release, site / "donor", internal)
    before = javap_lines(jdk.javap, rebuilt)
    if before != javap_lines(jdk.javap, site / "shipped.class"):
        raise CutRefused(f"{donor_sources[0].relative_to(donor).as_posix()} does not compile to the shipped {entry}")
    text, removed = cut_lines(copy_sources[0].read_text(encoding="utf-8-sig"), generator, methods[0])
    cut_source = site / "cut" / copy_sources[0].name  # javac wants the file named for its public class
    cut_source.parent.mkdir()
    cut_source.write_bytes(text.encode("utf-8"))
    cut = _compile(cut_source, os.pathsep.join(assemble_classpath(copy, vanilla_core, provider_roots).entries()), release,
                   site / "copy", internal)
    after = javap_lines(jdk.javap, cut)
    added = only_lost_lines(before, after)
    pattern = re.compile(rf"{re.escape(generator.replace('.', '/'))}(?![\w$])|{re.escape(generator)}(?![\w$])")
    named = [line for line in after if pattern.search(line)]
    if added or named:
        raise CutRefused(f"the cut class changed more than the call: added {added[:3]}, still naming {named[:3]}")
    data = cut.read_bytes()
    jar = _jar_holding(copy, entry)
    record = {"locus": element["locus"], "source": copy_sources[0].relative_to(copy).as_posix(), "removed_lines": removed,
              "class": f"{jar.relative_to(copy).as_posix()}!{entry}", "release": release,
              "class_sha256_before": hashlib.sha256(shipped).hexdigest(), "class_sha256_after": hashlib.sha256(data).hexdigest(),
              "checks": list(_CHECKS)}
    return {"record": record, "source_path": copy_sources[0], "source_text": text, "jar": jar, "entry": entry, "data": data}


def _jar_bytes(jar: Path, replaced: dict[str, bytes]) -> bytes:
    """`jar` with `replaced` entries swapped in, each entry's ZipInfo copied (the method patch-jar-class uses)."""
    import io

    from bridgeforge.zipsafe import read_limited

    buffer = io.BytesIO()
    with zipfile.ZipFile(jar) as source, zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as out:
        for item in source.infolist():
            out.writestr(item, replaced.get(item.filename) or read_limited(source, item.filename))
    return buffer.getvalue()


def _put(path: Path, data: bytes) -> None:
    """Write `path` through a temp file and a replace, retrying while an indexer holds it: VS Code's Java extension held P3's
    subtracted ECE.jar (WinError 5, 2026-11-20), as it held Arkgneisis's for patch-jar-class (2026-09-30)."""
    fresh = path.with_name(path.name + ".cut")
    try:
        fresh.write_bytes(data)
        for attempt in range(10):
            try:
                fresh.replace(path)
                return
            except PermissionError as error:
                if attempt == 9:
                    raise CutRefused(f"{path.name} stayed locked for 10 s (an indexer or scanner holding it): {error}") from error
                time.sleep(1)
    finally:
        fresh.unlink(missing_ok=True)


def _commit(plans: list[dict]) -> None:
    """Write the planned jars, then the sources. A failure puts back what was already written (from bytes held in memory)
    and refuses, so the copy is either fully cut or as subtraction made it."""
    by_jar: dict[Path, dict[str, bytes]] = {}
    for plan in plans:
        by_jar.setdefault(plan["jar"], {})[plan["entry"]] = plan["data"]
    writes = [(jar, _jar_bytes(jar, replaced)) for jar, replaced in by_jar.items()]
    writes += [(plan["source_path"], plan["source_text"].encode("utf-8")) for plan in plans]
    originals = {path: path.read_bytes() for path, _data in writes}
    done = []
    try:
        for path, data in writes:
            _put(path, data)
            done.append(path)
    except (CutRefused, OSError) as error:
        for path in reversed(done):
            _put(path, originals[path])
        raise CutRefused(f"writing the cut failed and the copy was put back: {error}") from error


def cut_registrations(donor: Path, copy: Path, gene: dict, vanilla_core: Path | None, provider_roots: list[Path]) -> dict:
    """{"cut": [one record per site]} or {"refused": reason}. Every site is planned in a temp folder first, writing nothing in
    `copy`; only when all pass are the jars and sources written (`_commit`), so the copy is fully cut or untouched."""
    sites = gene["registrations"]
    if len({element["locus"].rsplit(".", 1)[0] for element in sites}) != len(sites):
        return {"refused": "two registration sites are in one class; a cut edits each class's source once"}
    with tempfile.TemporaryDirectory(prefix="bf-cut-") as work:
        try:
            plans = [plan_site(Path(donor), Path(copy), element, vanilla_core, provider_roots, Path(work)) for element in sites]
        except CutRefused as refused:
            return {"refused": str(refused)}
        except Exception as error:  # noqa: BLE001 - planning writes nothing in the copy; any failure is a recorded refusal
            return {"refused": f"{type(error).__name__}: {error}"}
    try:
        _commit(plans)
    except CutRefused as refused:
        return {"refused": str(refused)}
    return {"cut": [plan["record"] for plan in plans]}


__all__ = ["CutRefused", "cut_lines", "cut_registrations", "javap_lines", "normalise", "only_lost_lines", "plan_site"]
