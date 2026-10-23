"""Scan registry: which stored scan describes which bytes (ROADMAP item 75 R2, item 73 A2).

A scan report is only evidence about the inputs it read. Finding a report by folder name (`reports/scan-*`) and trusting its file
time said nothing about that: a fixer could change a file and keep the time, a report could be stored under another name (the
EPTA follow-up scan was in `reports/owner-followup-scan-20261017/` and was missed). So each successful scan is registered in
`<workspace>/reports/scan-registry.json` with the fingerprint of everything the analysis depended on, and freshness is a
comparison of content:

- `CURRENT`    a complete, digest-verified report whose recorded fingerprint equals the one computed now.
- `STALE`      a known mismatch (the parts that differ are named).
- `UNKNOWN`    a report exists but the registry cannot say what it read (a legacy `scan-*` folder with no entry, or an entry
               without a fingerprint, schema or tool identity).
- `INCOMPLETE` a required input cannot be read now, or the registered report is missing, unreadable or fails its digest.

File times appear only as a diagnostic (`report_mtime`); they never decide a state, and a new time never blesses a legacy scan.

Fingerprint parts: `inputs` (every file under the scanned folder except the exclusions below), `core` (the read-only core's
`data/` content, root jars and the names under `graphics/` and `sounds/`; hashed once per process), `dependencies` (the folders
that provide the mod's declared dependencies, when provider roots were given), `target`, `options`, `scanner` (every
`bridgeforge/**/*.py` and `**/*.json`, so a changed check or rule changes it) and `tools` (Python, and javac when compile-check ran).
The accepted-baseline filter is a separate identity (`filter_digest`): it never changes a raw scan's state, but a record that
applied a different filter is not reused.

Exclusions (EXCLUSION_VERSION 1, part of the digest): the root `reports/` folder (generated reports, including this
registry and the mod's baselines), `*.pre-bf-*.bak*` backups made by fixers, and `.git/`. Nothing else is excluded, whatever
its folder is called.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from ..safeio import atomic_write_json
from ..source_paths import python_sources

SCHEMA_VERSION = 1
EXCLUSION_VERSION = 1
REGISTRY_NAME = "scan-registry.json"
STATES = ("CURRENT", "STALE", "UNKNOWN", "INCOMPLETE")
_PART_ORDER = ("inputs", "core", "dependencies", "target", "options", "scanner", "tools")
_CORE_CACHE: dict[tuple, str] = {}
_SCANNER_CACHE: dict[str, str] = {}
_TOOL_CACHE: dict[str, str] = {}


class RegistryError(ValueError):
    """Raised when a scan cannot be registered."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _tree_digest(entries: list[tuple[str, str]]) -> str:
    digest = hashlib.sha256()
    for relative, value in sorted(entries):
        digest.update(f"{relative}\0{value}\n".encode("utf-8"))
    return digest.hexdigest()


def _excluded(relative: str) -> bool:
    parts = relative.split("/")
    name = parts[-1]
    return parts[0] == "reports" and len(parts) > 1 or parts[0] == ".git" or (".pre-bf-" in name and ".bak" in name)


def _walk_files(root: Path, incomplete: list[str]) -> list[tuple[str, Path]]:
    found = []
    if not root.is_dir():
        incomplete.append(f"{root} is not a folder")
        return found
    for path in sorted(root.rglob("*")):
        try:
            if path.is_file():
                found.append((path.relative_to(root).as_posix(), path))
        except OSError as exc:
            incomplete.append(f"{path}: {exc}")
    return found


def _hash_tree(root: Path, incomplete: list[str], *, skip=lambda relative: False) -> str:
    entries = []
    for relative, path in _walk_files(root, incomplete):
        if skip(relative):
            continue
        try:
            entries.append((relative, _sha256(path)))
        except OSError as exc:
            incomplete.append(f"{relative}: {exc}")
    return _tree_digest(entries)


def _core_digest(core: Path, incomplete: list[str]) -> str:
    core = Path(core).resolve()
    stats = []
    for relative, path in _walk_files(core, incomplete):
        top = relative.split("/")[0]
        if top == "data" or (relative.endswith(".jar") and "/" not in relative) or top in ("graphics", "sounds"):
            try:
                info = path.stat()
            except OSError as exc:
                incomplete.append(f"core {relative}: {exc}")
                continue
            stats.append((relative, path, info.st_size, info.st_mtime_ns))
    key = (str(core), tuple((r, s, m) for r, _, s, m in stats))  # in-process cache of digests only; a new process rehashes
    if key not in _CORE_CACHE:
        entries = []
        for relative, path, size, _ in stats:
            top = relative.split("/")[0]
            try:
                entries.append((relative, _sha256(path) if top not in ("graphics", "sounds") else f"name:{size}"))
            except OSError as exc:
                incomplete.append(f"core {relative}: {exc}")
        _CORE_CACHE[key] = _tree_digest(entries)
    return _CORE_CACHE[key]


def scanner_identity() -> str:
    """Digest of the checks and rules themselves: every `*.py` and `**/*.json` in the bridgeforge package."""
    if "value" not in _SCANNER_CACHE:
        package = Path(__file__).resolve().parent.parent
        rules = [p for p in package.rglob("*.json") if p.is_file() and "__pycache__" not in p.relative_to(package).parts]
        sources = sorted([*python_sources(package), *rules])
        _SCANNER_CACHE["value"] = _tree_digest([(p.relative_to(package).as_posix(), _sha256(p)) for p in sources])
    return _SCANNER_CACHE["value"]


def _tools(compile_check: bool, incomplete: list[str]) -> str:
    parts = [f"python {sys.version_info.major}.{sys.version_info.minor}"]
    if compile_check:
        if "javac" not in _TOOL_CACHE:
            javac = shutil.which("javac")
            try:
                _TOOL_CACHE["javac"] = (subprocess.run([javac, "-version"], capture_output=True, text=True, timeout=30).stderr.strip()
                                        or "javac ?") if javac else "no javac"
            except (OSError, subprocess.SubprocessError) as exc:
                _TOOL_CACHE["javac"] = f"unreadable: {exc}"
        if _TOOL_CACHE["javac"].startswith("unreadable"):
            incomplete.append(f"javac: {_TOOL_CACHE['javac']}")
        parts.append(_TOOL_CACHE["javac"])
    return "; ".join(parts)


def normalise_context(context: dict | None) -> dict:
    """The scan options that change what a scan reads, as JSON-safe values."""
    context = context or {}

    def text(value):
        return str(Path(value).expanduser().resolve()) if value else None

    return {"vanilla_core": text(context.get("vanilla_core")), "compile_check": bool(context.get("compile_check")),
            "provider_roots": sorted(text(p) for p in context.get("provider_roots") or []) or None,
            "removed_content": text(context.get("removed_content")),
            "target": context.get("target") or None}


def fingerprint(working: Path, context: dict | None = None) -> dict:
    """{"schema", "digest", "parts", "incomplete"}: the analysis-input fingerprint of scanning `working` with `context`.
    `incomplete` lists every required input that could not be read; the digest is then not usable as CURRENT."""
    working = Path(working).expanduser().resolve()
    context = normalise_context(context)
    incomplete: list[str] = []
    parts: dict[str, object] = {"inputs": _hash_tree(working, incomplete, skip=_excluded)}
    parts["core"] = _core_digest(Path(context["vanilla_core"]), incomplete) if context["vanilla_core"] else None
    dependencies = None
    if context["provider_roots"]:
        from .scan_references import _dependency_roots

        roots = _dependency_roots(working, [Path(p) for p in context["provider_roots"]])
        dependencies = _tree_digest([(str(Path(r).resolve()), _hash_tree(Path(r), incomplete, skip=_excluded)) for r in roots])
    parts["dependencies"] = dependencies
    parts["target"] = context["target"]
    removed = context["removed_content"]
    try:
        removed_digest = _sha256(Path(removed)) if removed else None
    except OSError as exc:
        removed_digest = "unreadable"
        incomplete.append(f"removed-content catalogue: {exc}")
    parts["options"] = {"compile_check": context["compile_check"], "removed_content": removed_digest}
    parts["scanner"] = scanner_identity()
    parts["tools"] = _tools(context["compile_check"], incomplete)
    body = json.dumps({"schema": SCHEMA_VERSION, "exclusions": EXCLUSION_VERSION, "parts": parts}, sort_keys=True)
    return {"schema": SCHEMA_VERSION, "exclusions": EXCLUSION_VERSION, "digest": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            "parts": parts, "incomplete": incomplete}


def filter_digest(working: Path) -> str:
    """Identity of the accepted-baseline filter finding-stats applies on top of a raw scan."""
    from ..baseline import mod_baseline_path

    path = mod_baseline_path(Path(working))
    if path is None:
        return "no-baseline"
    try:
        return _sha256(path)
    except OSError:
        return "unreadable-baseline"


def workspace_of(input_path: Path) -> Path | None:
    """The workspace a scanned `working/` folder belongs to; None for any other scan input (not registered)."""
    path = Path(input_path).expanduser().resolve()
    return path.parent if path.name == "working" else None


def _index_path(workspace: Path) -> Path:
    return Path(workspace) / "reports" / REGISTRY_NAME


def read_index(workspace: Path) -> tuple[list[dict], str | None]:
    """(entries oldest first, problem). A missing index is ([], None); an unreadable or malformed one is ([], reason)."""
    path = _index_path(workspace)
    if not path.is_file():
        return [], None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        entries = data["entries"]
        if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
            raise TypeError("entries is not a list of objects")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return [], f"{REGISTRY_NAME} is unreadable ({exc})"
    return entries, None


def _resolve_report(workspace: Path, relative: object) -> Path | None:
    """The registered report inside the workspace, or None for an absolute path or one that escapes it."""
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        return None
    root = Path(workspace).resolve()
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return None
    return resolved


def register(workspace: Path, manifest_path: Path, working: Path, context: dict | None) -> dict:
    """Publish one finished scan. Call only after the report files are fully written: the entry is the last thing written,
    so an interrupted scan leaves no entry. Returns the entry."""
    workspace = Path(workspace).resolve()
    manifest_path = Path(manifest_path).resolve()
    try:
        relative = manifest_path.relative_to(workspace).as_posix()
    except ValueError as exc:
        raise RegistryError(f"{manifest_path} is outside the workspace {workspace}; scan reports are registered inside their workspace.") from exc
    try:
        json.loads(manifest_path.read_text(encoding="utf-8"))
        report_digest = _sha256(manifest_path)
    except (OSError, ValueError) as exc:
        raise RegistryError(f"{manifest_path} is not a complete scan report: {exc}") from exc
    fp = fingerprint(working, context)
    if fp["incomplete"]:
        raise RegistryError("scan inputs unreadable, not registered: " + "; ".join(fp["incomplete"][:3]))
    entry = {"schema": SCHEMA_VERSION, "report": relative, "report_sha256": report_digest, "fingerprint": fp["digest"],
             "parts": fp["parts"], "exclusions": EXCLUSION_VERSION, "context": normalise_context(context),
             "registered_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    entries, problem = read_index(workspace)
    if problem:
        entries = []  # an unreadable registry is replaced; the legacy fallback still sees older folders
    entries = [e for e in entries if e.get("report") != relative] + [entry]
    atomic_write_json(_index_path(workspace), {"schema": SCHEMA_VERSION, "entries": entries}, indent=2)
    return entry


def _differing(recorded: dict, current: dict) -> list[str]:
    return [name for name in _PART_ORDER if recorded.get(name) != current.get(name)]


def legacy_scans(workspace: Path) -> list[Path]:
    return sorted((Path(workspace) / "reports").glob("scan-*/bridgeforge.compat.json"), key=lambda p: (p.stat().st_mtime, str(p)))


def assess(workspace: Path) -> dict:
    """The freshness of the workspace's stored scan: {"state", "detail", "report", "fingerprint", "report_mtime"}.
    `state` is one of STATES, or "NONE" when there is no stored scan at all. `report` is the manifest to read findings from."""
    workspace = Path(workspace).resolve()
    working = workspace / "working"
    entries, problem = read_index(workspace)
    if not entries:
        legacy = legacy_scans(workspace)
        if not legacy and not problem:
            return {"state": "NONE", "detail": "no stored scan", "report": None, "fingerprint": None}
        if legacy:
            return {"state": "UNKNOWN", "detail": problem or "legacy scan folder without a registry entry or fingerprint",
                    "report": legacy[-1], "fingerprint": None, "report_mtime": legacy[-1].stat().st_mtime}
        return {"state": "INCOMPLETE", "detail": problem, "report": None, "fingerprint": None}
    newest: dict | None = None
    fingerprints: dict[str, dict] = {}  # one hashing pass per distinct context, however many entries share it
    for entry in reversed(entries):
        report = _resolve_report(workspace, entry.get("report"))
        context = entry.get("context")
        if report is None:
            result = {"state": "INCOMPLETE", "detail": f"registered report path {entry.get('report')!r} is absolute or escapes the workspace", "report": None, "fingerprint": None}
        elif not report.is_file():
            result = {"state": "INCOMPLETE", "detail": f"registered report {entry.get('report')} is missing", "report": None, "fingerprint": None}
        else:
            try:
                digest_ok = _sha256(report) == entry.get("report_sha256")
                json.loads(report.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError) as exc:
                result = {"state": "INCOMPLETE", "detail": f"registered report {entry.get('report')} is unreadable ({exc})", "report": None, "fingerprint": None}
            else:
                if not digest_ok:
                    result = {"state": "INCOMPLETE", "detail": f"registered report {entry.get('report')} does not match its recorded digest", "report": None, "fingerprint": None}
                elif entry.get("schema") != SCHEMA_VERSION or entry.get("exclusions") != EXCLUSION_VERSION or not entry.get("fingerprint") \
                        or not isinstance(entry.get("parts"), dict) or not entry["parts"].get("scanner") or not entry["parts"].get("tools") or not isinstance(context, dict):
                    result = {"state": "UNKNOWN", "detail": "registry entry lacks a fingerprint, schema or tool identity (older registry rules)", "report": report, "fingerprint": None}
                else:
                    context_key = json.dumps(context, sort_keys=True)
                    if context_key not in fingerprints:
                        fingerprints[context_key] = fingerprint(working, context)
                    fp = fingerprints[context_key]
                    if fp["incomplete"]:
                        result = {"state": "INCOMPLETE", "detail": "input unreadable: " + "; ".join(fp["incomplete"][:3]), "report": report, "fingerprint": fp["digest"]}
                    elif fp["digest"] == entry["fingerprint"]:
                        return {"state": "CURRENT", "detail": "inputs, dependencies, options and checks match the registered fingerprint",
                                "report": report, "fingerprint": fp["digest"], "report_mtime": report.stat().st_mtime}
                    else:
                        result = {"state": "STALE", "detail": "changed since the scan: " + ", ".join(_differing(entry["parts"], fp["parts"])),
                                  "report": report, "fingerprint": fp["digest"], "report_mtime": report.stat().st_mtime}
        if newest is None:
            newest = result  # the newest entry's verdict, unless an older entry still matches the current content
    return newest or {"state": "NONE", "detail": "no stored scan", "report": None, "fingerprint": None}
