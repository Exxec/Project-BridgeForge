"""Moving BridgeForge to another computer (ROADMAP item 64, docs/MIGRATION_PLAN.md).

`migrate-inventory` classifies what is on this machine, `relocate` rewrites the absolute paths that break
on a new one, `migrate-verify` proves a copied tree arrived intact. Nothing here edits game files; the
rig's `starsector-core` junction is listed, never followed.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .progress import Checkpoint, report

IN_GIT, IRREPLACEABLE, REGENERABLE, GAME_FILES = "in-git", "gitignored-irreplaceable", "regenerable", "game-files"
REGENERABLE_PATTERNS = (".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "*.egg-info", ".coverage*",
                        "htmlcov", "hs_err_pid*", "*.partial.jsonl", "build", "dist", ".claude")
GAME_PATTERNS = ("Starsector*", "starsector-core", "Fractal Softworks")
BACKUP_SUFFIX = ".pre-relocate.bak"
MAX_JSON_BYTES = 200 * 1024 * 1024
MAX_LINKS_LISTED = 50
HASH_CHUNK = 1024 * 1024
ABS_PATH = re.compile(r"[A-Za-z]:[\\/][^\"'\r\n<>|*?]*")
REPARSE_POINT = 0x400


def is_link(path: Path | os.DirEntry) -> bool:
    """Symlink or NTFS junction: never descended into (junctions point at the game install)."""
    try:
        if path.is_symlink():
            return True
        attrs = getattr(os.lstat(path), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attrs & REPARSE_POINT)


def link_target(path: Path) -> str:
    try:
        return os.readlink(path)
    except OSError:
        return "?"


def is_absolute_text(value: str) -> bool:
    return bool(re.match(r"^[A-Za-z]:[\\/]", value)) or value.startswith(("\\\\", "/"))


def claude_memory_dir(root: Path, claude_home: Path | None = None) -> Path:
    """`C:\\Users\\x\\Project` -> `c--Users-x-Project`: every non-alphanumeric becomes `-`, drive letter lowercased."""
    text = str(root)
    key = re.sub(r"[^A-Za-z0-9]", "-", text[:1].lower() + text[1:] if text[1:2] == ":" else text)
    return (claude_home or Path.home() / ".claude") / "projects" / key / "memory"


def _git(root: Path, *args: str) -> list[str] | None:
    try:
        done = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.splitlines() if done.returncode == 0 else None


def tracked_files(root: Path) -> set[str] | None:
    lines = _git(root, "ls-files", "-z")
    if lines is None:
        return None
    return {name for name in "\n".join(lines).split("\0") if name}


def tracked_top_level(files: set[str]) -> set[str]:
    return {name.split("/", 1)[0] for name in files}


def classify(name: str, tracked_tops: set[str]) -> str:
    if name == ".git" or name in tracked_tops:
        return IN_GIT
    if any(fnmatch.fnmatch(name, p) for p in GAME_PATTERNS):
        return GAME_FILES
    if any(fnmatch.fnmatch(name, p) for p in REGENERABLE_PATTERNS):
        return REGENERABLE
    return IRREPLACEABLE


def measure(path: Path) -> dict:
    """Files, bytes and links under `path`, without following links."""
    files = size = 0
    links: list[dict] = []
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError:
            continue
        for entry in entries:
            if is_link(entry):
                links.append({"path": entry.path, "target": link_target(Path(entry.path))})
            elif entry.is_dir(follow_symlinks=False):
                stack.append(Path(entry.path))
            else:
                try:
                    size += entry.stat(follow_symlinks=False).st_size
                    files += 1
                except OSError:
                    continue
    return {"files": files, "bytes": size, "links": len(links), "link_list": links[:MAX_LINKS_LISTED]}


def inventory_item(path: Path, tracked_tops: set[str]) -> dict:
    if is_link(path):
        stats = {"files": 0, "bytes": 0, "links": 1, "link_list": [{"path": str(path), "target": link_target(path)}]}
        kind = "link"
    elif path.is_dir():
        stats, kind = measure(path), "dir"
    else:
        stats, kind = {"files": 1, "bytes": path.stat().st_size, "links": 0, "link_list": []}, "file"
    return {"name": path.name, "kind": kind, "class": classify(path.name, tracked_tops), **stats}


def _strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


def _absolute_in_text(text: str) -> list[str]:
    return sorted({m.group(0).rstrip("\\/ ,;)") for m in ABS_PATH.finditer(text)})


def _json_paths(path: Path) -> list[str] | str:
    try:
        if path.stat().st_size > MAX_JSON_BYTES:
            return "too large to scan"
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        return f"unreadable: {exc}"
    return sorted({s for s in _strings(data) if is_absolute_text(s)})


def state_json_files(root: Path) -> list[Path]:
    state = root / "bridgeforge-state"
    found = [p for p in state.glob("*.json") if p.is_file()] if state.is_dir() else []
    found += [p for p in (state / "reference-rigs").glob("*.json")] if (state / "reference-rigs").is_dir() else []
    return sorted(found)


def rig_dirs(root: Path) -> list[Path]:
    base = root / "In operation"
    return sorted(p for p in base.glob("_rig*") if p.is_dir()) if base.is_dir() else []


def rig_bat_files(root: Path) -> list[Path]:
    """Top-level and one-level-down .bat files in each rig, never inside the game junction."""
    found: list[Path] = []
    for rig in rig_dirs(root):
        found += sorted(rig.glob("*.bat"))
        for child in sorted(p for p in rig.iterdir() if p.is_dir() and not is_link(p) and p.name != "starsector-core"):
            found += sorted(child.glob("*.bat"))
    return found


def absolute_path_hazards(root: Path) -> list[dict]:
    hazards: list[dict] = []
    hooks = _git(root, "config", "--get", "core.hooksPath")
    if hooks and is_absolute_text(hooks[0].strip()):
        hazards.append({"kind": "git-hooksPath", "file": ".git/config", "paths": [hooks[0].strip()], "fix": "git config core.hooksPath .githooks"})
    for psd1 in sorted((root / "config").glob("*.psd1")) if (root / "config").is_dir() else []:
        paths = _absolute_in_text(psd1.read_text(encoding="utf-8-sig", errors="replace"))
        if paths:
            hazards.append({"kind": "psd1", "file": psd1.relative_to(root).as_posix(), "paths": paths, "fix": "relocate"})
    for rig in rig_dirs(root):
        core = rig / "starsector-core"
        if is_link(core):
            hazards.append({"kind": "rig-junction", "file": core.relative_to(root).as_posix(), "paths": [link_target(core)], "fix": "recreate the junction with the rig setup (not copied)"})
    for bat in rig_bat_files(root):
        paths = _absolute_in_text(bat.read_text(encoding="utf-8", errors="replace"))
        if paths:
            hazards.append({"kind": "rig-bat", "file": bat.relative_to(root).as_posix(), "paths": paths, "fix": "relocate or java-matrix setup"})
    for js in state_json_files(root):
        paths = _json_paths(js)
        if isinstance(paths, str):
            hazards.append({"kind": "state-json", "file": js.relative_to(root).as_posix(), "paths": [], "note": paths})
        elif paths:
            hazards.append({"kind": "state-json", "file": js.relative_to(root).as_posix(), "paths": paths, "fix": "relocate"})
    if (root / "bridgeforge-state" / "corpus-index.sqlite").is_file():
        hazards.append({"kind": "sqlite", "file": "bridgeforge-state/corpus-index.sqlite", "paths": [], "fix": "rebuild (corpus-index build); not rewritten"})
    return hazards


def _ignored_inside(root: Path, tracked_tops: set[str]) -> dict[str, list[str]]:
    lines = _git(root, "ls-files", "--others", "--ignored", "--exclude-standard", "--directory")
    inside: dict[str, list[str]] = {}
    for line in lines or []:
        top = line.split("/", 1)[0]
        if "/" in line and top in tracked_tops:
            inside.setdefault(top, []).append(line)
    return inside


def migrate_inventory(root: Path, out: Path | None = None, checkpoint: Path | None = None, quiet: bool = False,
                      claude_home: Path | None = None) -> dict:
    root = root.resolve()
    files = tracked_files(root)
    tracked_tops = tracked_top_level(files) if files is not None else set()
    names = sorted(p.name for p in root.iterdir())
    memory = claude_memory_dir(root, claude_home)
    total = len(names) + 1
    items: list[dict] = []
    with Checkpoint(checkpoint, {"command": "migrate-inventory", "root": str(root), "items": names}) as saved:
        for index, name in enumerate(names, 1):
            cached = saved.get(name)
            started = time.monotonic()
            item = cached or inventory_item(root / name, tracked_tops)
            if cached is None:
                saved.add(name, item)
            items.append(item)
            if not quiet:
                report(index, total, name, f"{item['class']}, {item['files']} file(s), {item['bytes']:,} bytes", None if cached else time.monotonic() - started)
        started = time.monotonic()
        cached = saved.get("<claude-memory>")
        mem = cached or ({**measure(memory), "name": str(memory), "kind": "dir", "class": IRREPLACEABLE} if memory.is_dir()
                         else {"name": str(memory), "kind": "missing", "class": IRREPLACEABLE, "files": 0, "bytes": 0, "links": 0, "link_list": []})
        if cached is None:
            saved.add("<claude-memory>", mem)
        if not quiet:
            report(total, total, "claude memory", f"{mem['files']} file(s) at {memory}", None if cached else time.monotonic() - started)
        saved.finish()
    result = {
        "root": str(root), "git_available": files is not None, "items": items, "outside": [mem],
        "ignored_inside_tracked": _ignored_inside(root, tracked_tops), "hazards": absolute_path_hazards(root),
        "totals": {c: sum(i["bytes"] for i in items if i["class"] == c) for c in (IN_GIT, IRREPLACEABLE, REGENERABLE, GAME_FILES)},
    }
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def format_inventory(result: dict) -> str:
    lines = [f"Root: {result['root']}"]
    for item in result["items"]:
        lines.append(f"  {item['class']:<26} {item['name']}  ({item['files']} file(s), {item['bytes']:,} bytes, {item['links']} link(s))")
    for item in result["outside"]:
        lines.append(f"  {item['class']:<26} {item['name']}  ({item['files']} file(s), {item['bytes']:,} bytes)")
    lines.append("Totals (bytes): " + ", ".join(f"{k}={v:,}" for k, v in result["totals"].items()))
    lines.append(f"Absolute-path hazards: {len(result['hazards'])}")
    for hazard in result["hazards"]:
        lines.append(f"  [{hazard['kind']}] {hazard['file']}: {len(hazard['paths'])} path(s) -> {hazard.get('fix') or hazard.get('note', '')}")
    return "\n".join(lines)


# ---- relocate -------------------------------------------------------------------------------------------------

def _variants(old: str, new: str) -> list[tuple[re.Pattern, str]]:
    """Plain, JSON-escaped (doubled backslash) and forward-slash spellings of one path pair."""
    spellings = [(old, new), (old.replace("\\", "\\\\"), new.replace("\\", "\\\\")), (old.replace("\\", "/"), new.replace("\\", "/"))]
    unique = list(dict.fromkeys(spellings))
    return [(re.compile(re.escape(o) + r"(?=[\\/\"'\s;,)]|$)", re.IGNORECASE), n) for o, n in unique]


def rewrite_text(text: str, old: str, new: str) -> tuple[str, int]:
    count = 0
    for pattern, replacement in _variants(old.rstrip("\\/"), new.rstrip("\\/")):
        text, n = pattern.subn(lambda _m, r=replacement: r, text)
        count += n
    return text, count


def relocate_targets(root: Path) -> list[Path]:
    psd1 = sorted((root / "config").glob("*.psd1")) if (root / "config").is_dir() else []
    return psd1 + state_json_files(root) + rig_bat_files(root)


def relocate(root: Path, old: str, new: str, apply: bool = False) -> dict:
    root = root.resolve()
    files = tracked_files(root) or set()
    changes: list[dict] = []
    for path in relocate_targets(root):
        rel = path.relative_to(root).as_posix()
        if "starsector-core" in path.relative_to(root).parts or is_link(path):
            continue  # game files and links are never touched
        try:
            original = path.read_bytes().decode("utf-8-sig") if path.suffix == ".json" else path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            changes.append({"file": rel, "replacements": 0, "applied": False, "note": f"unreadable: {exc}"})
            continue
        rewritten, count = rewrite_text(original, old, new)
        if not count:
            continue
        change = {"file": rel, "replacements": count, "git_tracked": rel in files, "applied": False}
        if apply:
            backup = path.with_name(path.name + BACKUP_SUFFIX)
            if not backup.exists():
                shutil.copy2(path, backup)  # keep the first original if run again
            path.write_text(rewritten, encoding="utf-8", newline="")
            change["applied"], change["backup"] = True, backup.name
        changes.append(change)
    notes = []
    hooks = _git(root, "config", "--get", "core.hooksPath")
    if hooks and is_absolute_text(hooks[0].strip()):
        notes.append("git core.hooksPath is absolute: run `git config core.hooksPath .githooks` (not changed here)")
    if (root / "bridgeforge-state" / "corpus-index.sqlite").is_file():
        notes.append("bridgeforge-state/corpus-index.sqlite is not rewritten: rebuild it with `corpus-index build`")
    if any(is_link(rig / "starsector-core") for rig in rig_dirs(root)):
        notes.append("rig starsector-core junctions are not rewritten: recreate them with the rig setup")
    return {"root": str(root), "from": old, "to": new, "apply": apply, "changes": changes, "notes": notes}


def format_relocate(result: dict) -> str:
    mode = "APPLIED" if result["apply"] else "DRY RUN (use --apply to write)"
    lines = [f"relocate {result['from']} -> {result['to']}: {mode}"]
    for c in result["changes"]:
        tag = " [git-tracked]" if c.get("git_tracked") else ""
        lines.append(f"  {c['file']}: {c['replacements']} replacement(s){tag}" + (f" ({c['note']})" if c.get("note") else "")
                     + (f", backup {c['backup']}" if c.get("backup") else ""))
    if not result["changes"]:
        lines.append("  no files contain the old path")
    lines += [f"  note: {n}" for n in result["notes"]]
    return "\n".join(lines)


# ---- migrate-verify -------------------------------------------------------------------------------------------

def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(HASH_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_files(top: Path, root: Path, excludes: tuple[str, ...]) -> list[Path]:
    found: list[Path] = []
    for current, dirs, names in os.walk(top):
        base = Path(current)
        dirs[:] = sorted(d for d in dirs if not is_link(base / d) and not any(fnmatch.fnmatch(d, e) for e in excludes))
        found += [base / n for n in sorted(names) if not is_link(base / n) and not any(fnmatch.fnmatch(n, e) for e in excludes)]
    return found


def hash_tree(directory: Path, checkpoint: Path | None, quiet: bool, excludes: tuple[str, ...] = (), header_extra: str = "") -> dict[str, dict]:
    """sha256 and size of every file under `directory` (links skipped), reported per top-level entry, resumable per file."""
    directory = directory.resolve()
    tops = sorted(p for p in directory.iterdir() if not any(fnmatch.fnmatch(p.name, e) for e in excludes) and not is_link(p))
    result: dict[str, dict] = {}
    header = {"command": "migrate-verify", "dir": str(directory), "mode": header_extra, "excludes": list(excludes), "tops": [p.name for p in tops]}
    with Checkpoint(checkpoint, header) as saved:
        for index, top in enumerate(tops, 1):
            started = time.monotonic()
            members = [top] if top.is_file() else _tree_files(top, directory, excludes)
            resumed = 0
            for path in members:
                rel = path.relative_to(directory).as_posix()
                stat = path.stat()
                prior = saved.get(rel)
                if prior and prior["size"] == stat.st_size and prior["mtime_ns"] == stat.st_mtime_ns:
                    result[rel] = {"size": prior["size"], "sha256": prior["sha256"]}
                    resumed += 1
                    continue
                entry = {"size": stat.st_size, "sha256": sha256_of(path), "mtime_ns": stat.st_mtime_ns}
                saved.add(rel, entry)
                result[rel] = {"size": entry["size"], "sha256": entry["sha256"]}
            if not quiet:
                report(index, len(tops), top.name, f"{len(members)} file(s), {resumed} from checkpoint", None if members and resumed == len(members) else time.monotonic() - started)
        saved.finish()
    return result


def verify_write(directory: Path, manifest: Path, quiet: bool = False, excludes: tuple[str, ...] = ()) -> dict:
    files = hash_tree(directory, manifest.with_name(manifest.name + ".partial.jsonl"), quiet, excludes, "write")
    data = {"root": str(directory.resolve()), "excludes": list(excludes),
            "files": [{"path": p, "size": f["size"], "sha256": f["sha256"]} for p, f in sorted(files.items())]}
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(data, indent=1), encoding="utf-8")
    return {"files": len(files), "bytes": sum(f["size"] for f in files.values()), "manifest": str(manifest)}


def verify_check(directory: Path, manifest: Path, quiet: bool = False, excludes: tuple[str, ...] = ()) -> dict:
    data = json.loads(manifest.read_text(encoding="utf-8"))
    expected = {f["path"]: f for f in data["files"]}
    excludes = excludes or tuple(data.get("excludes", ()))
    actual = hash_tree(directory, manifest.with_name(manifest.name + ".check.partial.jsonl"), quiet, excludes, "check")
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    changed = sorted(p for p in set(expected) & set(actual) if expected[p]["sha256"] != actual[p]["sha256"] or expected[p]["size"] != actual[p]["size"])
    return {"checked": len(expected), "missing": missing, "changed": changed, "extra": extra, "ok": not (missing or changed or extra)}


# ---- command line ---------------------------------------------------------------------------------------------

def add_parser(subcommands) -> None:
    inv = subcommands.add_parser("migrate-inventory", help="classify the repo and its gitignored trees for a move to another computer (in git / irreplaceable / regenerable / game files) and list absolute-path hazards (ROADMAP item 64); slow on a big tree, run it in the background")
    inv.add_argument("--root", type=Path, default=Path.cwd(), help="repo root (default: current folder)")
    inv.add_argument("--out", type=Path, help="write the full inventory as JSON here")
    inv.add_argument("--checkpoint", type=Path, help="resume file (default: beside --out, else bridgeforge-state/migrate-inventory.partial.jsonl)")
    inv.add_argument("--claude-home", type=Path, help="Claude config folder holding projects/ (default: ~/.claude)")
    inv.add_argument("--quiet", action="store_true", help="no per-folder progress lines on stderr")
    inv.add_argument("--json", action="store_true")
    rel = subcommands.add_parser("relocate", help="rewrite the old absolute path in config/*.psd1, known bridgeforge-state JSON and rig .bat files; dry run unless --apply; writes .pre-relocate.bak beside each changed file (ROADMAP item 64)")
    rel.add_argument("--from", dest="old", required=True, metavar="OLD")
    rel.add_argument("--to", dest="new", required=True, metavar="NEW")
    rel.add_argument("--root", type=Path, default=Path.cwd())
    rel.add_argument("--apply", action="store_true", help="write the changes (default is a dry run)")
    rel.add_argument("--json", action="store_true")
    ver = subcommands.add_parser("migrate-verify", help="hash manifest of a tree: `write` it on the old machine, `check` it on the new one (ROADMAP item 64)")
    sub = ver.add_subparsers(dest="verify_command", required=True)
    for name, text in (("write", "hash every file under DIR into the manifest (resumable)"), ("check", "compare DIR with the manifest: missing, changed, extra")):
        cmd = sub.add_parser(name, help=text)
        cmd.add_argument("dir", type=Path, metavar="DIR")
        cmd.add_argument("--manifest", type=Path, required=True)
        cmd.add_argument("--exclude", action="append", default=[], metavar="NAME", help="file or folder name pattern to skip (repeatable)")
        cmd.add_argument("--quiet", action="store_true", help="no per-folder progress lines on stderr")
        cmd.add_argument("--json", action="store_true")


def run_cli(args) -> int:
    try:
        if args.command == "migrate-inventory":
            checkpoint = args.checkpoint or (args.out.with_name(args.out.name + ".partial.jsonl") if args.out else Path("bridgeforge-state") / "migrate-inventory.partial.jsonl")
            result = migrate_inventory(args.root, args.out, checkpoint, args.quiet, args.claude_home)
            print(json.dumps(result, indent=2) if args.json else format_inventory(result))
            return 0
        if args.command == "relocate":
            result = relocate(args.root, args.old, args.new, args.apply)
            print(json.dumps(result, indent=2) if args.json else format_relocate(result))
            return 0
        excludes = tuple(args.exclude)
        if args.verify_command == "write":
            result = verify_write(args.dir, args.manifest, args.quiet, excludes)
            print(json.dumps(result, indent=2) if args.json else f"Manifest written: {result['files']} file(s), {result['bytes']:,} bytes -> {result['manifest']}")
            return 0
        result = verify_check(args.dir, args.manifest, args.quiet, excludes)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Checked {result['checked']} file(s): {len(result['missing'])} missing, {len(result['changed'])} changed, {len(result['extra'])} extra")
            for label in ("missing", "changed", "extra"):
                for path in result[label]:
                    print(f"  {label}: {path}")
        return 0 if result["ok"] else 1
    except (OSError, ValueError) as exc:
        print(f"bridgeforge: {exc}", file=sys.stderr)
        return 2
