"""`bridgeforge fold`: fold a discontinued library-like mod into RevenantLib (ROADMAP P14 item 10).

Owner policy (docs/DEPENDENCY_STRATEGY.md, "Folding discontinued libraries into RevenantLib"): a
discontinued, library-like, no-licence-conflict dependency is folded into RevenantLib (id
`revenantlib`) rather than revived as one more standalone mod. Folding keeps the original mod's ids
and class names exactly as they are, so any mod that already depends on it keeps resolving those ids
once its own dependency line is repointed at `revenantlib` (see `fixers._fix_revenantlib_fold_conflict`
and the `revenantlib-fold-conflict` scan check in `scanner.py`).

This command does only the mechanical, safe half of a fold:

1. Copy the source mod's entire directory tree, byte-for-byte, into
   `<target>/original/<source folder name>/`. Nothing is renamed, rewritten or excluded, so ids and
   class names are untouched. Curating what actually belongs in RevenantLib's own `working/` copy (the
   "traced closure": which files a dependent really needs) is deliberately left to the coordinator
   afterwards -- see `reports/PROVENANCE.md`'s existing hand-written entries for what that curation
   looks like once it's done.
2. Record a provenance section in `<target>/reports/PROVENANCE.md` naming the original mod, its
   author, version and declared game version, plus a SHA-256 per copied file.
3. Write a `dependency_successors.json` entry (kind `folded-into-revenantlib`) so
   `dependency-substitutes` proposes the `revenantlib` swap for mods that still declare the original id.

Source and target are always explicit arguments -- this module never hardcodes or touches
"In operation" itself. Never deletes anything: an existing destination folder is refused outright
unless `overwrite=True`, and even then a file that already exists with *different* content is a
conflict that stops the whole run and is reported, never silently resolved either way. Re-running
with unchanged inputs is a no-op.
"""

from __future__ import annotations

import json
from pathlib import Path

from .scanner import _load_lenient_json_file
from .substitutes import SUCCESSORS_PATH, load_successors
from .workspace import sha256_file

SCHEMA_VERSION = 1
FOLD_KIND = "folded-into-revenantlib"


class FoldError(ValueError):
    """Raised when the source or target isn't a usable directory, or the source has no mod_info.json."""


def _text(value: object, default: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if value in (None, ""):
        return default
    return json.dumps(value, sort_keys=True)


def _mod_metadata(root: Path) -> dict[str, str]:
    mod_info = root / "mod_info.json"
    if not mod_info.is_file():
        raise FoldError(f"No mod_info.json found at {mod_info}; fold's source must be a mod's own directory (e.g. its 'working' copy).")
    data = _load_lenient_json_file(mod_info)
    if not isinstance(data, dict) or not str(data.get("id") or "").strip():
        raise FoldError(f"{mod_info} could not be parsed, or has no non-empty 'id'.")
    mod_id = str(data["id"]).strip()
    return {
        "id": mod_id,
        "name": _text(data.get("name"), mod_id),
        "author": _text(data.get("author"), "unknown"),
        "version": _text(data.get("version"), "unknown"),
        "game_version": _text(data.get("gameVersion") or data.get("game_version"), "unknown"),
    }


def _licence_evidence(root: Path) -> str:
    """A factual note only, never a licence *judgement* -- release readiness stays release_policy.json's
    call (see release.py's licence gate), decided once, for RevenantLib as a whole."""
    names = sorted(p.name for p in root.iterdir() if p.is_file() and "licen" in p.name.lower())
    return f"a licence-named file is present at the source root: {', '.join(names)}" if names else "no licence-named file was found at the source root"


def _relative_files(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def _origin_folder_name(source_root: Path) -> str:
    """Folder name for the fold under `<target>/original/`.

    BridgeForge workspaces are laid out as `<Workspace>/working`, so the source basename is almost
    always the literal `working` - every fold would land at `original/working/` and collide with the
    next one. Use the workspace folder instead, which is what the hand-curated sections already use
    (`original/Vacuum`, `original/Xenoargh-Rebal`). Falls back to the basename if that is unhelpful.
    """
    if source_root.name.lower() in {"working", "original", "src"}:
        parent = source_root.parent.name
        if parent:
            return parent
    return source_root.name


def _append_provenance_section(
    path: Path,
    source_root: Path,
    metadata: dict[str, str],
    licence_evidence: str,
    relative_files: list[str],
    manifest: dict[str, str],
) -> None:
    origin_name = _origin_folder_name(source_root)
    under = f"original/{origin_name}/"
    lines = [
        f"## Origin: {origin_name}",
        "",
        f"- **Source path:** `{source_root}` (mod id `{metadata['id']}`, version `{metadata['version']}`, "
        f"`gameVersion \"{metadata['game_version']}\"`, author `{metadata['author']}`)",
        f"- **Licence status:** {licence_evidence}. Not a redistribution judgement -- see `release_policy.json`.",
        f"- **Content taken:** the entire source tree, unmodified ({len(relative_files)} file(s)) -- every id "
        "and class name kept exactly as the original mod defines it, so existing dependents keep resolving "
        "them unchanged. Curating what RevenantLib's own working copy actually uses from this (the traced "
        "closure) is the coordinator's next step, not `bridgeforge fold`'s.",
        "",
        "### Files folded (SHA-256)",
        "",
        f"| File (under `{under}`) | SHA-256 |",
        "|---|---|",
    ]
    lines += [f"| `{relative}` | `{manifest[relative]}` |" for relative in relative_files]
    lines += ["", "---", ""]
    section = "\n".join(lines) + "\n"
    if path.is_file():
        existing = path.read_text(encoding="utf-8")
        separator = "" if existing.endswith("\n\n") else ("\n" if existing.endswith("\n") else "\n\n")
        path.write_text(existing + separator + section, encoding="utf-8")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        header = (
            "# PROVENANCE\n\nAdded by `bridgeforge fold`. Each folded mod gets its own section below "
            "(source path, licence status, every file taken with its SHA-256).\n\n---\n\n"
        )
        path.write_text(header + section, encoding="utf-8")


def _append_successors_entry(path: Path, source_root: Path, target_root: Path, metadata: dict[str, str]) -> None:
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise FoldError(f"{path} could not be parsed as JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise FoldError(f"{path} must contain a JSON object.")
    else:
        data = {
            "schema_version": 1,
            "note": "Known renames, splits and dead ends that id coverage cannot see. Every entry cites evidence checked on this machine or a dated source; add entries only with evidence.",
            "successors": [],
        }
    entries = data.setdefault("successors", [])
    if not isinstance(entries, list):
        raise FoldError(f"{path} 'successors' is not a JSON array.")
    entries.append({
        "match": metadata["id"],
        "kind": FOLD_KIND,
        "successor": (
            f"Folded into RevenantLib (id revenantlib). Original: {metadata['name']} by {metadata['author']}, "
            f"version {metadata['version']}, gameVersion {metadata['game_version']}."
        ),
        "action": (
            f"Declare revenantlib instead of {metadata['id']}. Never enable {metadata['id']} alongside "
            "revenantlib: folding keeps its ids and class names unchanged, so both loaded together would "
            "double-register them (bridgeforge fix --finding revenantlib-fold-conflict resolves that if it "
            "already happened)."
        ),
        "evidence": f"bridgeforge fold {source_root} {target_root}, copied byte-for-byte; see {target_root / 'reports' / 'PROVENANCE.md'}.",
    })
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def fold(
    source: Path,
    target: Path,
    *,
    dry_run: bool = False,
    overwrite: bool = False,
    successors_path: Path | None = None,
) -> dict[str, object]:
    """Fold `source` (a library-like mod's own directory) into `target` (a RevenantLib-shaped
    directory). See the module docstring for exactly what gets written and when.
    """
    source_root = Path(source).expanduser().resolve()
    target_root = Path(target).expanduser().resolve()
    successors_file = Path(successors_path).expanduser().resolve() if successors_path is not None else SUCCESSORS_PATH
    if not source_root.is_dir():
        raise FoldError(f"{source_root} is not an existing directory.")
    if not target_root.is_dir():
        raise FoldError(f"{target_root} is not an existing directory.")
    if source_root == target_root or source_root in target_root.parents or target_root in source_root.parents:
        raise FoldError(f"Source ({source_root}) and target ({target_root}) must not be nested inside each other.")

    metadata = _mod_metadata(source_root)
    dest_root = target_root / "original" / _origin_folder_name(source_root)

    result: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "mode": "FOLD",
        "dry_run": dry_run,
        "source": str(source_root),
        "target": str(target_root),
        "destination": str(dest_root),
        "successors_path": str(successors_file),
        "mod_id": metadata["id"],
        "mod_name": metadata["name"],
        "author": metadata["author"],
        "version": metadata["version"],
        "game_version": metadata["game_version"],
        "licence_evidence": _licence_evidence(source_root),
        "files_copied": [],
        "files_unchanged": [],
        "conflicts": [],
        "provenance_file": str(target_root / "reports" / "PROVENANCE.md"),
        "provenance_written": False,
        "successors_entry_written": False,
    }

    if dest_root.is_dir() and not overwrite:
        result["status"] = "REFUSED"
        result["message"] = f"{dest_root} already exists; pass --overwrite to fold into it (files that differ are still never overwritten)."
        return result

    relative_files = _relative_files(source_root)
    files_copied: list[str] = []
    files_unchanged: list[str] = []
    conflicts: list[str] = []
    for relative in relative_files:
        source_file = source_root / relative
        dest_file = dest_root / relative
        if dest_file.is_file():
            if dest_file.read_bytes() == source_file.read_bytes():
                files_unchanged.append(relative)
            else:
                conflicts.append(relative)
        else:
            files_copied.append(relative)
    result["conflicts"] = conflicts

    if conflicts:
        result["status"] = "CONFLICT"
        result["message"] = (
            f"{len(conflicts)} file(s) already exist at {dest_root} with different content; nothing was "
            "written. They are never silently overwritten or deleted -- resolve by hand, then re-run."
        )
        return result

    result["files_copied"] = files_copied
    result["files_unchanged"] = files_unchanged
    manifest = {relative: sha256_file(source_root / relative) for relative in relative_files}
    result["manifest_sha256"] = manifest

    provenance_path = target_root / "reports" / "PROVENANCE.md"
    origin_heading = f"## Origin: {_origin_folder_name(source_root)}"
    provenance_exists_already = provenance_path.is_file() and origin_heading in provenance_path.read_text(encoding="utf-8", errors="replace")

    successors_exists_already = any(
        entry.get("kind") == FOLD_KIND and str(entry.get("match")) == metadata["id"] for entry in load_successors(successors_file)
    )

    if not files_copied and provenance_exists_already and successors_exists_already:
        result["status"] = "NOOP"
        result["message"] = "Nothing to copy; a provenance section and successors entry already record this fold."
        return result

    if dry_run:
        result["status"] = "OK"
        result["message"] = "dry run: nothing written."
        result["would_write_provenance"] = not provenance_exists_already
        result["would_write_successors_entry"] = not successors_exists_already
        return result

    for relative in files_copied:
        destination = dest_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((source_root / relative).read_bytes())

    if not provenance_exists_already:
        _append_provenance_section(provenance_path, source_root, metadata, str(result["licence_evidence"]), relative_files, manifest)
        result["provenance_written"] = True

    if not successors_exists_already:
        _append_successors_entry(successors_file, source_root, target_root, metadata)
        result["successors_entry_written"] = True

    result["status"] = "OK"
    return result
