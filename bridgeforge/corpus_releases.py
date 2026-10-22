"""`bridgeforge corpus releases ROOT...` (ROADMAP-3 82.10): which releases of each mod a download folder holds.

Scans folders and .zip/.7z/.rar archives for `mod_info.json` (and the `.version` file beside it) and groups the copies by mod id:
versions, game versions, forum thread and repository links. It replaces the one-off script of 2026-10-22 (718 ids, 200 with two or
more versions). `--write DIR` writes `releases.csv`, `RELEASES.md` and `pairs.json`; the last feeds
`atlas migrations --pairs-json`.

Safety: archive content is untrusted. Only `mod_info.json` and `.version` members are read, always into memory (nothing is
extracted to disk), after a member-path check and a size cap; archives inside archives are not opened. `.rar` needs 7-Zip's
`7z.exe` (found on PATH or in Program Files); without it the archive is listed as "not read".

Pairs: a pair needs two folders, so only copies that sit in a folder are pairable. A version found only inside an archive is
listed under "not pairable" in pairs.json and RELEASES.md; extract it into a folder and run the command again to pair it.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from . import progress
from .corpus_index import _safe_member
from .safeio import atomic_write_json, atomic_write_text
from .scan_json import _parse_json
from .zipsafe import read_limited

ARCHIVE_SUFFIXES = (".zip", ".7z", ".rar")
MAX_INFO_BYTES = 1024 * 1024  # a mod_info.json or .version file is a few hundred bytes
SKIPPED_DIRS = frozenset({".git", "graphics", "sounds", "jars", "data"})
SEVEN_ZIP_TIMEOUT = 120
SEVEN_ZIP_FALLBACK = Path(r"C:\Program Files\7-Zip\7z.exe")
FORUM_URL = "https://fractalsoftworks.com/forum/index.php?topic="
PAIRS_FORMAT = "bridgeforge-pairs/1"
CSV_FIELDS = ("id", "name", "version", "gameVersion", "source", "kind", "status", "forum", "repo", "master")
_REPO_HOSTS = (
    (re.compile(r"https?://raw\.githubusercontent\.com/([^/]+)/([^/]+)/"), "https://github.com/{0}/{1}"),
    (re.compile(r"https?://github\.com/([^/]+)/([^/]+)/"), "https://github.com/{0}/{1}"),
    (re.compile(r"https?://(gitlab\.com|bitbucket\.org|codeberg\.org)/([^/]+)/([^/]+)/"), "https://{0}/{1}/{2}"),
)


@dataclass(frozen=True)
class Copy:
    """One mod_info.json found (id empty when the copy or its archive could not be read)."""
    id: str = ""
    name: str = ""
    version: str = ""
    gameVersion: str = ""  # noqa: N815 (csv column name)
    source: str = ""
    kind: str = "folder"
    status: str = "read"
    forum: str = ""
    repo: str = ""
    master: str = ""
    folder: str = ""  # set for folder copies only: what a migrations pair can open


class ArchiveNotRead(Exception):
    """An archive that cannot be listed or read; the message says why."""


# ---------------------------------------------------------------- parsing

def _json_object(data: bytes) -> dict | None:
    try:
        parsed, _ = _parse_json(data.decode("utf-8-sig", errors="replace"))
    except (json.JSONDecodeError, ValueError, RecursionError):
        return None
    return parsed if isinstance(parsed, dict) else None


def version_text(value: object) -> str:
    """"1.2" as written, or {major, minor, patch} joined with dots (empty parts dropped)."""
    if isinstance(value, dict):
        return ".".join(str(value[key]).strip() for key in ("major", "minor", "patch") if str(value.get(key, "")).strip())
    return str(value).strip() if isinstance(value, (str, int, float)) and not isinstance(value, bool) else ""


def repo_link(master_url: str) -> str:
    for pattern, template in _REPO_HOSTS:
        match = pattern.match(master_url)
        if match:
            return template.format(*match.groups())
    return ""


def _forum_link(version_info: dict) -> str:
    thread = re.match(r"\s*(\d+)", str(version_info.get("modThreadId", "")))
    return f"{FORUM_URL}{thread.group(1)}" if thread and int(thread.group(1)) else ""


def make_copy(info_bytes: bytes, version_bytes: bytes | None, source: str, kind: str, folder: str = "") -> Copy:
    info = _json_object(info_bytes)
    if info is None or not isinstance(info.get("id"), str) or not info["id"].strip():
        return Copy(source=source, kind=kind, status="unreadable: mod_info.json has no readable id")
    version_info = _json_object(version_bytes) if version_bytes else None
    master = str((version_info or {}).get("masterVersionFile") or "").strip()
    return Copy(id=info["id"].strip(), name=str(info.get("name") or "").strip(), version=version_text(info.get("version")),
                gameVersion=str(info.get("gameVersion") or "").strip(), source=source, kind=kind,
                forum=_forum_link(version_info or {}), repo=repo_link(master), master=master, folder=folder)


# ---------------------------------------------------------------- folders

def _is_link(path: str) -> bool:
    return os.path.islink(path) or (hasattr(os.path, "isjunction") and os.path.isjunction(path))


def _read_small(path: Path) -> bytes | None:
    try:
        if path.stat().st_size > MAX_INFO_BYTES:
            return None
        return path.read_bytes()
    except OSError:
        return None


def scan_folder(root: Path) -> tuple[list[Copy], list[Path]]:
    """Folder copies under `root` and the archives found on the way (links are not followed)."""
    copies: list[Copy] = []
    archives: list[Path] = []
    for current, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIPPED_DIRS and not d.startswith(".") and not _is_link(os.path.join(current, d)))
        folder = Path(current)
        if "mod_info.json" in files:
            copies.append(_folder_copy(folder, sorted(f for f in files if f.lower().endswith(".version"))))
        archives.extend(folder / f for f in sorted(files) if f.lower().endswith(ARCHIVE_SUFFIXES))
    return copies, archives


def _folder_copy(folder: Path, version_files: list[str]) -> Copy:
    info = _read_small(folder / "mod_info.json")
    version = _read_small(folder / version_files[0]) if version_files else None
    if info is None:
        return Copy(source=str(folder), status="unreadable: mod_info.json missing or over the size cap")
    return make_copy(info, version, str(folder), "folder", str(folder))


# ---------------------------------------------------------------- archives

def find_seven_zip() -> str | None:
    return shutil.which("7z") or shutil.which("7za") or (str(SEVEN_ZIP_FALLBACK) if SEVEN_ZIP_FALLBACK.is_file() else None)


def select_members(entries: list[tuple[str, int]]) -> list[tuple[str, str | None]]:
    """(mod_info path, .version path or None) for every safe, small mod_info.json in `entries` (name, size)."""
    sizes = {name.replace("\\", "/"): size for name, size in entries}
    pairs = []
    for name in sorted(n for n in sizes if n.rsplit("/", 1)[-1].lower() == "mod_info.json"):
        if not _safe_member(name) or sizes[name] > MAX_INFO_BYTES:
            continue
        folder = name.rpartition("/")[0]
        versions = sorted(n for n in sizes if n.rpartition("/")[0] == folder and n.lower().endswith(".version")
                          and _safe_member(n) and sizes[n] <= MAX_INFO_BYTES)
        pairs.append((name, versions[0] if versions else None))
    return pairs


def _zip_backend(path: Path) -> tuple[list[tuple[str, int]], Callable[[list[str]], dict[str, bytes]]]:
    try:
        archive = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError, NotImplementedError) as exc:
        raise ArchiveNotRead(f"not a readable zip ({exc})") from None
    infos = {i.filename.replace("\\", "/"): i for i in archive.infolist() if not i.is_dir()}

    def fetch(names: list[str]) -> dict[str, bytes]:
        try:
            return {name: read_limited(archive, infos[name], MAX_INFO_BYTES) for name in names}
        except (OSError, zipfile.BadZipFile, RuntimeError, NotImplementedError, EOFError) as exc:
            raise ArchiveNotRead(f"member could not be read ({exc})") from None
        finally:
            archive.close()
    return [(n, i.file_size) for n, i in infos.items()], fetch


def _7z_backend(path: Path) -> tuple[list[tuple[str, int]], Callable[[list[str]], dict[str, bytes]]]:
    try:
        import py7zr
        from py7zr.io import BytesIOFactory
    except ImportError:
        raise ArchiveNotRead(".7z not read: pip install bridgeforge[archives] (py7zr)") from None
    try:
        archive = py7zr.SevenZipFile(path, "r")
        if archive.needs_password():
            archive.close()
            raise ArchiveNotRead("encrypted .7z")
        entries = [(i.filename, i.uncompressed or 0) for i in archive.list() if not i.is_directory]
    except ArchiveNotRead:
        raise
    except Exception as exc:  # py7zr raises its own and many stdlib errors on a damaged archive
        raise ArchiveNotRead(f"not a readable .7z ({type(exc).__name__}: {exc})") from None

    def fetch(names: list[str]) -> dict[str, bytes]:
        factory = BytesIOFactory(MAX_INFO_BYTES + 1)  # in memory: nothing is written to disk
        try:
            if not names:
                return {}
            archive.extract(targets=names, factory=factory)
            return {name: _drain(factory.get(name)) for name in names}
        except Exception as exc:  # noqa: BLE001
            raise ArchiveNotRead(f".7z member could not be read ({type(exc).__name__}: {exc})") from None
        finally:
            archive.close()
    return entries, fetch


def _drain(buffer) -> bytes:
    buffer.seek(0)
    data = buffer.read()
    if len(data) > MAX_INFO_BYTES:
        raise ArchiveNotRead("member larger than its declared size")
    return data


def _seven_zip_run(exe: str, args: list[str]) -> bytes:
    try:
        done = subprocess.run([exe, *args], capture_output=True, timeout=SEVEN_ZIP_TIMEOUT, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ArchiveNotRead(f"7-Zip failed ({type(exc).__name__})") from None
    if done.returncode != 0:
        raise ArchiveNotRead(f"7-Zip exit code {done.returncode} (damaged, encrypted or unsupported)")
    return done.stdout


def _rar_entries(listing: str) -> list[tuple[str, int]]:
    entries = []
    for block in listing.split("----------")[-1].split("\n\n"):
        fields = dict(line.split(" = ", 1) for line in block.splitlines() if " = " in line)
        if "Path" in fields and fields.get("Folder") != "+" and fields.get("Size", "").isdigit():
            entries.append((fields["Path"], int(fields["Size"])))
    return entries


def _rar_backend(path: Path) -> tuple[list[tuple[str, int]], Callable[[list[str]], dict[str, bytes]]]:
    exe = find_seven_zip()
    if not exe:
        raise ArchiveNotRead(".rar not read: 7-Zip (7z.exe) not found")
    listing = _seven_zip_run(exe, ["l", "-slt", "-p-", "-sccUTF-8", "--", str(path)]).decode("utf-8", errors="replace")
    entries = _rar_entries(listing.replace("\r\n", "\n"))

    def fetch(names: list[str]) -> dict[str, bytes]:
        # -spd: names are literal (no wildcards); output goes to memory through -so
        return {name: _seven_zip_run(exe, ["e", "-so", "-p-", "-spd", "--", str(path), name])[:MAX_INFO_BYTES + 1] for name in names}
    return entries, fetch


_BACKENDS = {".zip": _zip_backend, ".7z": _7z_backend, ".rar": _rar_backend}


def scan_archive(path: Path) -> list[Copy]:
    kind = path.suffix.lower().lstrip(".")
    try:
        entries, fetch = _BACKENDS[path.suffix.lower()](path)
        chosen = select_members(entries)
        wanted = sorted({n for pair in chosen for n in pair if n})
        data = fetch(wanted)
    except ArchiveNotRead as exc:
        return [Copy(source=str(path), kind=kind, status=f"unreadable: {exc}")]
    return [make_copy(data[info], data.get(version) if version else None, f"{path} :: {info.rpartition('/')[0] or '/'}", kind)
            for info, version in chosen]


# ---------------------------------------------------------------- scan driver

def _archive_key(path: Path) -> str:
    stat = path.stat()
    return f"{path}|{stat.st_size}|{stat.st_mtime_ns}"


def scan_roots(roots: list[Path], checkpoint: progress.Checkpoint | None = None, quiet: bool = True) -> list[Copy]:
    copies: list[Copy] = []
    archives: list[Path] = []
    for root in roots:
        if root.is_file() and root.suffix.lower() in ARCHIVE_SUFFIXES:
            archives.append(root)
        elif root.is_dir():
            found, nested = scan_folder(root)
            copies.extend(found)
            archives.extend(nested)
        else:
            raise ValueError(f"{root} is not a folder or a .zip/.7z/.rar file")
    archives = sorted(set(archives))
    for index, archive in enumerate(archives, 1):
        key = _archive_key(archive)
        saved = checkpoint.get(key) if checkpoint else None
        started = time.monotonic()
        found = [Copy(**item) for item in saved["copies"]] if saved else scan_archive(archive)
        if checkpoint and not saved:
            checkpoint.add(key, {"copies": [asdict(c) for c in found]})
        copies.extend(found)
        if not quiet:
            progress.report(index, len(archives), archive.name, f"{len([c for c in found if c.id])} mod_info.json", None if saved else time.monotonic() - started)
    return sorted(copies, key=lambda c: (c.id.lower(), c.source))


# ---------------------------------------------------------------- grouping and output

def version_key(version: str) -> tuple:
    """Natural order for version strings: 1.9 < 1.10, numbers before words."""
    tokens = re.findall(r"\d+|[A-Za-z]+", version)
    return tuple((0, int(t), "") if t.isdigit() else (1, 0, t.lower()) for t in tokens) or ((2, 0, ""),)  # unknown ("?") last


def group_by_id(copies: list[Copy]) -> dict[str, list[Copy]]:
    groups: dict[str, list[Copy]] = defaultdict(list)
    for copy in copies:
        if copy.id:
            groups[copy.id.lower()].append(copy)
    return dict(sorted(groups.items()))


def versions_of(copies: list[Copy]) -> list[str]:
    return sorted({c.version or "?" for c in copies}, key=version_key)


def revival_ids(repo_root: Path) -> frozenset[str]:
    """Ids BridgeForge already works on: In operation/*/working and Done/*/* (lowercase)."""
    ids = set()
    for pattern in ("In operation/*/working/mod_info.json", "Done/*/*/mod_info.json"):
        for path in sorted(repo_root.glob(pattern)):
            data = _read_small(path)
            info = _json_object(data) if data else None
            if info and isinstance(info.get("id"), str) and info["id"].strip():
                ids.add(info["id"].strip().lower())
    return frozenset(ids)


def build_pairs(groups: dict[str, list[Copy]]) -> tuple[list[dict], list[dict]]:
    """Adjacent-version pairs of folder copies per id, and the multi-version ids that cannot be paired (with why)."""
    pairs, unpairable = [], []
    for mod_id, copies in groups.items():
        if len({c.version or "?" for c in copies}) < 2:
            continue
        by_version = {}
        for copy in copies:
            if copy.folder:
                by_version.setdefault(copy.version or "?", copy)
        ordered = sorted(by_version, key=version_key)
        for older, newer in zip(ordered, ordered[1:]):
            pairs.append({"label": f"{mod_id} {older} -> {newer}", "old": by_version[older].folder, "new": by_version[newer].folder,
                          "old_version": older, "new_version": newer})
        if len(ordered) < 2:
            unpairable.append({"id": mod_id, "versions": versions_of(copies), "reason": "fewer than two versions sit in a folder; extract the archive copies first"})
    return pairs, unpairable


def csv_text(copies: list[Copy]) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=CSV_FIELDS, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(asdict(c) for c in copies)
    return out.getvalue()


def _row(mod_id: str, copies: list[Copy], revived: frozenset[str]) -> str:
    games = sorted({c.gameVersion for c in copies if c.gameVersion})
    forum = next((c.forum for c in copies if c.forum), "")
    repo = next((c.repo for c in copies if c.repo), "")
    links = " ".join(x for x in (f"[forum]({forum})" if forum else "", f"[repo]({repo})" if repo else "") if x) or "none found"
    name = next((c.name for c in copies if c.name), "").replace("|", "/")
    return f"| `{mod_id}` | {name} | {', '.join(versions_of(copies))} | {', '.join(games)} | {'yes' if mod_id in revived else ''} | {len(copies)} | {links} |"


def releases_markdown(copies: list[Copy], groups: dict[str, list[Copy]], revived: frozenset[str], unpairable: list[dict], pair_count: int) -> str:
    multi = {k: v for k, v in groups.items() if len(versions_of(v)) > 1}
    single = {k: v for k, v in groups.items() if k not in multi}
    unread = sorted((c for c in copies if not c.id), key=lambda c: c.source)
    head = "| Mod id | Name | Versions found | Game versions | In BridgeForge | Copies | Links |\n|---|---|---|---|---|---|---|"
    order = lambda d: sorted(d, key=lambda k: (k not in revived, k))  # noqa: E731
    lines = [
        "# Mod release inventory", "",
        f"{len(copies)} copies, {len(groups)} mod ids. {len(multi)} ids have two or more distinct versions; {len(single)} have one. "
        f"Rows marked *In BridgeForge* are revival targets and matter most. {pair_count} version pair(s) in pairs.json "
        f"(`atlas migrations --pairs-json`); {len(unpairable)} multi-version id(s) cannot be paired because their versions are not in folders.", "",
        "## Need an older (or newer) copy: only one version found", "",
        "Look for the forum thread's older download links, a GitHub releases page, or an older modpack.", "", head,
        *[_row(k, single[k], revived) for k in order(single)], "",
        "## Already have two or more versions (usable for migration mining now)", "", head,
        *[_row(k, multi[k], revived) for k in order(multi)], "",
        f"## Multi-version ids not pairable ({len(unpairable)})", "",
        "A pair needs two folders; extract the archive copies and run the command again.", "",
        *[f"- `{u['id']}`: {', '.join(u['versions'])}" for u in unpairable], "",
        f"## Archives or files with no mod_info.json read ({len(unread)})", "",
        *[f"- {c.source}: {c.status}" for c in unread],
    ]
    return "\n".join(lines) + "\n"


def write_outputs(copies: list[Copy], repo_root: Path, folder: Path) -> list[Path]:
    groups = group_by_id(copies)
    pairs, unpairable = build_pairs(groups)
    revived = revival_ids(repo_root)
    return [
        atomic_write_text(folder / "releases.csv", csv_text(copies), newline=""),
        atomic_write_text(folder / "RELEASES.md", releases_markdown(copies, groups, revived, unpairable, len(pairs))),
        atomic_write_json(folder / "pairs.json", {"format": PAIRS_FORMAT, "pairs": pairs, "not_pairable": unpairable}),
    ]


def summary(copies: list[Copy]) -> dict:
    groups = group_by_id(copies)
    multi = sum(1 for v in groups.values() if len(versions_of(v)) > 1)
    return {"copies": len(copies), "ids": len(groups), "multi_version": multi, "single_version": len(groups) - multi,
            "unread": sum(1 for c in copies if not c.id)}


# ---------------------------------------------------------------- command

def add_parser(subcommands) -> None:
    corpus = subcommands.add_parser("corpus", help="corpus-wide inventories of a download folder (see `corpus releases`)")
    sub = corpus.add_subparsers(dest="corpus_command", required=True)
    releases = sub.add_parser("releases", help="release inventory: scan folders and .zip/.7z/.rar for mod_info.json; versions, game versions and forum/repo links per mod id; writes releases.csv, RELEASES.md and a pairs.json for `atlas migrations --pairs-json` (ROADMAP-3 82.10)")
    releases.add_argument("roots", type=Path, nargs="+", metavar="ROOT", help="folders or archives to scan, e.g. Downloads")
    releases.add_argument("--write", type=Path, metavar="DIR", help="write releases.csv, RELEASES.md and pairs.json into DIR (progress is kept in DIR/releases.partial.jsonl so an interrupted run resumes)")
    releases.add_argument("--repo-root", type=Path, default=Path("."), help="repo root holding In operation/ and Done/, to mark revival targets (default: cwd)")
    releases.add_argument("--restart", action="store_true", help="with --write: ignore an earlier interrupted run's releases.partial.jsonl")
    releases.add_argument("--quiet", action="store_true", help="no per-archive progress lines on stderr")
    releases.add_argument("--json", action="store_true")


def run_cli(args) -> int:
    roots = [Path(r).expanduser() for r in args.roots]
    checkpoint_path = args.write / "releases.partial.jsonl" if args.write else None
    if checkpoint_path and args.restart and checkpoint_path.is_file():
        checkpoint_path.unlink()
    header = {"command": "corpus releases", "roots": sorted(str(r.resolve()) for r in roots)}
    try:
        with progress.Checkpoint(checkpoint_path, header) as checkpoint:
            copies = scan_roots(roots, checkpoint, args.quiet)
            written = write_outputs(copies, args.repo_root, args.write) if args.write else []
        if checkpoint_path:
            checkpoint.finish()
    except (ValueError, OSError) as exc:
        print(f"bridgeforge: {exc}", file=sys.stderr)
        return 2
    counts = summary(copies)
    if args.json:
        print(json.dumps({**counts, "written": [str(p) for p in written]}, indent=2))
        return 0
    print(f"{counts['copies']} copies, {counts['ids']} ids, {counts['multi_version']} multi-version, {counts['single_version']} single, {counts['unread']} unread")
    for path in written:
        print(f"wrote {path}")
    return 0
