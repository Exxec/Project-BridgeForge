"""Archive content parity (ROADMAP item 77.18): what the author's `original/` shipped under `data/` that a shipped tree lacks.

FIX-001 shipped a LIVE_VALIDATED archive whose whole `rules.csv` was gone. A shipped tree (a folder or a zip, read in place) is
compared with the matching original mod root (chosen by mod id, as the dropped-feature sweep does) and every `data/` file the
original has and the shipped tree lacks is classed:

- MISSING: a real loss, unless `reports/REMOVALS.json` records it (a `files` category, once the file format has one).
  A vanilla-path CSV (rules.csv, ...) is merged by the game, never a shadow of vanilla, so it is MISSING too.
- SHADOW_REMOVAL: the same path exists in vanilla core (not a CSV): the file only overrode the game.
- RENAMED: the same file name or the same bytes ships elsewhere.
- JUNK: `.old`, `~`, nested archives, desktop.ini, "copy of" files: the author's litter.
- SOURCE_OMITTED: a `.java` file whose class ships in a jar.

Verdicts (worst first): LOSS_SUSPECTED, REVIEW, UNDETERMINED, CLEAN. Read-only for the audited trees.
"""
from __future__ import annotations

import hashlib
import io
import re
import tempfile
import time
import zipfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Callable, Iterator

from .archive_intake import _normalized_member_name, inspect_zip_archive
from .progress import Checkpoint, report
from .removals import RemovalsError, covers, load_removals, split_explained
from .safeio import atomic_write_json, atomic_write_text, safe_rmtree

VERDICTS = ("LOSS_SUSPECTED", "REVIEW", "UNDETERMINED", "CLEAN")
RESULT_JSON, RESULT_MD, CHECKPOINT = "CONTENT_PARITY.json", "CONTENT_PARITY.md", "CONTENT_PARITY.partial.jsonl"
CLASSES = ("MISSING", "SHADOW_REMOVAL", "RENAMED", "JUNK", "SOURCE_OMITTED")
LOSS_CATEGORIES = ("rules.csv", "events.json", "reports.csv")  # an unexplained drop here is a loss, as for MISSING files
HASH_LIMIT = 64 * 1024 * 1024  # larger files are matched by name only
JAR_LIMIT = 256 * 1024 * 1024
ROOT_DEPTH = 5
_JUNK_SUFFIXES = (".old", "~", ".orig")
_ARCHIVE_SUFFIXES = (".zip", ".7z", ".rar")
_JUNK_NAMES = frozenset({"desktop.ini", "thumbs.db", ".ds_store"})
_COPY_NAME = re.compile("копия|copy of| - copy|\\(\\d\\)\\.", re.IGNORECASE)
_BACKUP = re.compile(r"\.bak(\.\d+)?$|\.pre-bf", re.IGNORECASE)
_ID = re.compile(r'"id"\s*:\s*"([^"]+)"')
_STATUS = re.compile(r"report status:\s*\*\*([^*]+)\*\*", re.IGNORECASE)


def is_junk(relative: str, archives: bool = True) -> bool:
    """True for editor/OS litter and copies. `archives` also counts a nested .zip/.7z/.rar (the audit does; archiving does not)."""
    low = relative.lower()
    name = PurePosixPath(low).name
    if low.endswith(_JUNK_SUFFIXES) or name in _JUNK_NAMES or _COPY_NAME.search(low):
        return True
    return archives and low.endswith(_ARCHIVE_SUFFIXES)


def junk_members(names: list[str]) -> list[str]:
    """The members `archive-preflight` and `archive` refuse (nested archives are not refused)."""
    return sorted(n for n in names if is_junk(n.replace("\\", "/"), archives=False))


class Tree:
    """A read-only file tree: a folder or a zip (optionally below a prefix), names relative and '/'-separated."""

    def __init__(self, sizes: dict[str, int], read: Callable[[str], bytes], directory: Path | None = None):
        self.sizes, self._read, self.directory = sizes, read, directory
        self.folded = {name.casefold(): name for name in sizes}

    def has(self, relative: str) -> bool:
        return relative.casefold() in self.folded

    def read(self, relative: str) -> bytes:
        return self._read(self.folded.get(relative.casefold(), relative))

    def under(self, prefix: str) -> "Tree":
        """The files below `prefix` (a mod root), names relative to it."""
        cut = "" if prefix in ("", ".") else prefix.rstrip("/") + "/"
        sizes = {n[len(cut):]: s for n, s in self.sizes.items() if n.startswith(cut)}
        directory = self.directory / prefix if self.directory is not None and cut else self.directory
        return Tree(sizes, lambda n: self._read(cut + n), directory)

    def mod_roots(self) -> list[str]:
        found = sorted({str(PurePosixPath(n).parent) for n in self.sizes if PurePosixPath(n).name == "mod_info.json"
                        and len(PurePosixPath(n).parts) <= ROOT_DEPTH + 1}, key=lambda r: (r.count("/"), r.lower()))
        return [r for r in found if not any(o != r and (o == "." or r.startswith(o + "/")) for o in found)]

    @contextmanager
    def materialized(self) -> Iterator[Path]:
        """A directory holding the tree: the folder itself, or a temporary extraction of a zip (the one place a zip is written out)."""
        if self.directory is not None:
            yield self.directory
            return
        temp = Path(tempfile.mkdtemp(prefix="bf-parity-"))
        try:
            for name in self.sizes:
                target = temp.joinpath(*PurePosixPath(name).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(self._read(name))
            yield temp
        finally:
            safe_rmtree(temp, [temp.parent])


@contextmanager
def open_tree(path: Path) -> Iterator[Tree]:
    """Open a folder or a zip. A zip with extraction hazards or over archive_intake's limits raises ValueError."""
    path = Path(path)
    if path.is_dir():
        sizes = {p.relative_to(path).as_posix(): p.stat().st_size for p in path.rglob("*") if p.is_file()}
        yield Tree(sizes, lambda n: (path / n).read_bytes(), directory=path)
        return
    preflight = inspect_zip_archive(path)
    if not preflight["safe_to_stage"]:
        raise ValueError("archive refused by preflight: " + ", ".join(f["id"] for f in preflight["findings"]))
    with zipfile.ZipFile(path) as archive:
        members = {}
        for entry in archive.infolist():
            name = _normalized_member_name(entry.filename)
            if name and not entry.is_dir():
                members[name] = entry
        yield Tree({n: e.file_size for n, e in members.items()}, lambda n: archive.read(members[n]))


def _digest(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def mod_id_of(data: bytes) -> str:
    found = _ID.search(data.decode("utf-8-sig", "replace"))
    return found.group(1) if found else ""


def _jar_classes(shipped: Tree) -> set[str]:
    names: set[str] = set()
    for member, size in shipped.sizes.items():
        if not member.lower().endswith(".jar") or size > JAR_LIMIT:
            continue
        try:
            with zipfile.ZipFile(io.BytesIO(shipped.read(member))) as jar:
                names.update(PurePosixPath(n).stem.split("$")[0] for n in jar.namelist() if n.endswith(".class"))
        except (zipfile.BadZipFile, OSError):
            continue
    return names


def _vanilla_has(vanilla_core: Path | None, relative: str) -> bool:
    return vanilla_core is not None and (Path(vanilla_core) / relative).is_file()


def classify_missing(old: Path, shipped: Tree, vanilla_core: Path | None = None, removals: list[dict] | None = None) -> dict:
    """Class every `data/` file of `old` that `shipped` lacks. Returns `{CLASS: [...], "EXPLAINED": [...]}` (RENAMED as 'a -> b')."""
    removals = removals or []
    result: dict[str, list[str]] = {name: [] for name in (*CLASSES, "EXPLAINED")}
    data = Path(old) / "data"
    if not data.is_dir():
        return result
    by_name: dict[str, list[str]] = {}
    by_size: dict[int, list[str]] = {}
    for name, size in shipped.sizes.items():
        by_name.setdefault(PurePosixPath(name).name.casefold(), []).append(name)
        by_size.setdefault(size, []).append(name)
    jar_classes: set[str] | None = None
    for path in sorted(p for p in data.rglob("*") if p.is_file()):
        relative = path.relative_to(old).as_posix()
        if _BACKUP.search(relative) or shipped.has(relative):
            continue
        low = relative.lower()
        if low.endswith(".java") and jar_classes is None:
            jar_classes = _jar_classes(shipped)
        if is_junk(relative):
            result["JUNK"].append(relative)
        elif low.endswith(".java") and path.stem in (jar_classes or ()):
            result["SOURCE_OMITTED"].append(relative)
        elif _vanilla_has(vanilla_core, relative) and not low.endswith(".csv"):
            result["SHADOW_REMOVAL"].append(relative)
        elif any(covers(r, "files", relative) for r in removals):  # the `files` removal category, where it exists
            result["EXPLAINED"].append(relative)
        else:
            moved = _find_moved(path, relative, shipped, by_name, by_size)
            if moved:
                result["RENAMED"].append(f"{relative} -> {moved}")
            else:
                note = " [vanilla-path CSV: merged by the game, not a shadow]" if _vanilla_has(vanilla_core, relative) else ""
                result["MISSING"].append(relative + note)
    return result


def _find_moved(path: Path, relative: str, shipped: Tree, by_name: dict[str, list[str]], by_size: dict[int, list[str]]) -> str:
    same_name = by_name.get(PurePosixPath(relative).name.casefold())
    if same_name:
        return same_name[0]
    size = path.stat().st_size
    candidates = by_size.get(size, [])
    if candidates and size <= HASH_LIMIT:
        wanted = _digest(path.read_bytes())
        return next((c for c in candidates if _digest(shipped.read(c)) == wanted), "")
    return ""


def _count(root: Path, folder: str) -> int:
    base = Path(root) / folder
    return sum(1 for p in base.rglob("*") if p.is_file()) if base.is_dir() else 0


def _safe_removals(dirs: list[Path], notes: list[str]) -> list[dict]:
    found: list[dict] = []
    for directory in dirs:
        try:
            found += load_removals(directory)
        except RemovalsError as exc:
            notes.append(f"REMOVALS error: {str(exc)[:150]}")
    return found


def compare_root(old: Path, shipped: Tree, vanilla_core: Path | None, removals: list[dict]) -> dict:
    from .scan_port import dropped_features

    classes = classify_missing(old, shipped, vanilla_core, removals)
    with shipped.materialized() as new_root:
        split = split_explained(dropped_features(Path(old), new_root), removals)
        deficit = {k: _count(old, k) - _count(new_root, k) for k in ("graphics", "sounds")}
    return {"classes": classes, "unexplained": {c: e["unexplained"] for c, e in split.items() if e["unexplained"]},
            "explained": {c: e["explained"] for c, e in split.items() if e["explained"]}, "asset_deficit": deficit}


def verdict_of(row: dict) -> str:
    if not row.get("determined"):
        return "UNDETERMINED"
    unexplained = row.get("unexplained", {})
    if row["missing"] or row.get("orphans") or any(unexplained.get(c) for c in LOSS_CATEGORIES):
        return "LOSS_SUSPECTED"
    if unexplained or row["shadow"] or row["renamed"] or row["junk"] or row["src"] or row.get("baks"):
        return "REVIEW"
    return "CLEAN"


def audit_shipped(shipped_path: Path, original_base: Path | None, *, name: str, vanilla_core: Path | None = None,
                  removals_dirs: list[Path] | None = None) -> dict:
    """Compare a shipped folder or zip with the originals under `original_base`. Never raises for an unreadable archive."""
    row = {"mod": name, "shipped": Path(shipped_path).name, "verdict": "UNDETERMINED", "notes": [], "roots": [], "determined": False,
           "missing": [], "explained_missing": [], "shadow": [], "renamed": [], "junk": [], "src": [], "unexplained": {}, "explained": {},
           "baks": [], "orphans": [], "asset_deficit": {}}
    try:
        with open_tree(Path(shipped_path)) as tree:
            _audit_tree(row, tree, original_base, vanilla_core, list(removals_dirs or []))
    except (ValueError, OSError, zipfile.BadZipFile) as exc:
        row["notes"].append(f"unreadable: {str(exc)[:200]}")
    row["verdict"] = verdict_of(row)
    return row


def _audit_tree(row: dict, tree: Tree, original_base: Path | None, vanilla_core: Path | None, removals_dirs: list[Path]) -> None:
    from .dropped_sweep import mod_id, mod_roots
    from .fixer_backups import orphaned_backups_in

    row["baks"] = [n for n in tree.sizes if _BACKUP.search(n)]
    row["orphans"] = orphaned_backups_in(list(tree.sizes))
    roots = tree.mod_roots()
    if not roots:
        row["notes"].append("no mod_info.json in the shipped tree")
        return
    found = mod_roots(Path(original_base), 6) if original_base and Path(original_base).is_dir() else []
    originals = {r: mod_id(r / "mod_info.json") for r in found}
    if not originals:
        row["notes"].append("no matching original")
        return
    for root in roots:
        sub = tree.under(root)
        shipped_id = mod_id_of(sub.read("mod_info.json"))
        match = next((r for r, i in originals.items() if shipped_id and i == shipped_id), None)
        if match is None and len(originals) == 1 and len(roots) == 1:
            match = next(iter(originals))
            row["notes"].append("original matched as the only mod root (id differs)")
        row["roots"].append({"shipped": root, "id": shipped_id, "original": str(match) if match else None})
        if match is None:
            continue
        row["determined"] = True
        extra = [tree.directory / root] if tree.directory is not None else []
        part = compare_root(match, sub, vanilla_core, _safe_removals(removals_dirs + extra, row["notes"]))
        classes = part["classes"]
        for key, field in (("MISSING", "missing"), ("EXPLAINED", "explained_missing"), ("SHADOW_REMOVAL", "shadow"),
                           ("RENAMED", "renamed"), ("JUNK", "junk"), ("SOURCE_OMITTED", "src")):
            row[field] += classes[key]
        for key, value in part["unexplained"].items():
            row["unexplained"].setdefault(key, []).extend(value)
        for key, value in part["explained"].items():
            row["explained"].setdefault(key, []).extend(value)
        for key, value in part["asset_deficit"].items():
            row["asset_deficit"][key] = row["asset_deficit"].get(key, 0) + value
    if not row["determined"]:
        row["notes"].append("no original root with the shipped id")


def pick_zip(folder: Path) -> tuple[Path | None, str]:
    """The mod's zip in a Done/ folder: the newest plain one (a -with-readme copy only when nothing else), plus a note."""
    zips = list(Path(folder).glob("*.zip"))
    plain = [z for z in zips if "-with-readme" not in z.name and "backup" not in z.name.lower()]
    pool = plain or zips
    if not pool:
        return None, ""
    chosen = sorted(pool, key=lambda z: (z.stat().st_mtime, z.name))[-1]
    return chosen, (f"{len(plain)} plain zips; took the newest" if len(plain) > 1 else "")


def archive_status(folder: Path) -> str:
    try:
        text = (Path(folder) / "ARCHIVE_NOTE.md").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "no ARCHIVE_NOTE"
    found = _STATUS.search(text)
    return (found.group(1).strip() if found else "?")[:80]


def audit_done_folder(folder: Path, queue: Path, vanilla_core: Path | None = None) -> dict:
    zip_path, note = pick_zip(folder)
    status = archive_status(folder)
    if zip_path is None:
        return {"mod": folder.name, "shipped": "", "status": status, "verdict": "UNDETERMINED", "notes": ["no zip"], "roots": []}
    base = next((b for b in (folder / "original", Path(queue) / folder.name / "original") if b.is_dir()), None)
    row = audit_shipped(zip_path, base, name=folder.name, vanilla_core=vanilla_core,
                        removals_dirs=[Path(queue) / folder.name / "working", folder / "workspace"])
    row["status"] = status
    if note:
        row["notes"].insert(0, note)
    return row


def content_parity(done: Path, queue: Path, out_dir: Path | None = None, vanilla_core: Path | None = None, quiet: bool = False) -> dict:
    """Audit every folder in Done/; write CONTENT_PARITY.json/.md to `out_dir` (default `done`). Resumable by a checkpoint."""
    done, queue = Path(done).resolve(), Path(queue).resolve()
    out = Path(out_dir).resolve() if out_dir else done
    out.mkdir(parents=True, exist_ok=True)
    folders = sorted(p for p in done.iterdir() if p.is_dir() and not p.name.startswith("_"))
    header = {"done": str(done), "queue": str(queue), "vanilla_core": str(vanilla_core) if vanilla_core else None,
              "mods": [f.name for f in folders]}
    rows = []
    with Checkpoint(out / CHECKPOINT, header) as checkpoint:
        for number, folder in enumerate(folders, 1):
            cached = checkpoint.get(folder.name)
            started = time.perf_counter()
            try:
                row = cached if cached is not None else audit_done_folder(folder, queue, vanilla_core)
            except OSError as exc:  # a folder another process holds open: report it, go on
                row = {"mod": folder.name, "shipped": "", "verdict": "UNDETERMINED", "notes": [f"ERROR {exc}"[:200]], "roots": []}
            if cached is None:
                checkpoint.add(folder.name, row)
            rows.append(row)
            if not quiet:
                report(number, len(folders), folder.name, row["verdict"], None if cached is not None else time.perf_counter() - started)
        rows.sort(key=lambda r: (VERDICTS.index(r["verdict"]), r["mod"].lower()))
        counts = {v: sum(1 for r in rows if r["verdict"] == v) for v in VERDICTS}
        result = {"schema_version": 1, "mode": "CONTENT_PARITY", "done": str(done), "counts": counts, "mods": rows}
        atomic_write_json(out / RESULT_JSON, result, indent=2, ensure_ascii=False)
        atomic_write_text(out / RESULT_MD, render_markdown(result))
        checkpoint.finish()
    return result


def render_markdown(result: dict) -> str:
    rows = result["mods"]
    lines = ["# Done/ content parity", "",
             "OFFLINE static comparison of each shipped zip with its `original/`. A live test is not performed here.", "",
             "Counts: " + ", ".join(f"{k} {v}" for k, v in result["counts"].items()) + f" (of {len(rows)} folders).", "",
             "| verdict | mod | shipped | status | MISSING data files | unexplained drops | src/junk/shadow/renamed | backups |",
             "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if r["verdict"] == "CLEAN":
            continue
        missing = r.get("missing", [])
        shown = "; ".join(missing[:5]) + (f" (+{len(missing) - 5})" if len(missing) > 5 else "")
        drops = "; ".join(f"{k} {len(v)}" for k, v in r.get("unexplained", {}).items()) or "-"
        notes = ("; " + "; ".join(r["notes"])) if r.get("notes") else ""
        counts = "/".join(str(len(r.get(k, []))) for k in ("src", "junk", "shadow", "renamed"))
        lines.append(f"| {r['verdict']} | {r['mod']} | {r.get('shipped', '')} | {r.get('status', '')[:30]} | {shown or '-'} | "
                     f"{drops}{notes} | {counts} | {len(r.get('baks', []))}+{len(r.get('orphans', []))} |")
    lines += ["", "CLEAN: " + ", ".join(r["mod"] for r in rows if r["verdict"] == "CLEAN"), ""]
    return "\n".join(lines)
