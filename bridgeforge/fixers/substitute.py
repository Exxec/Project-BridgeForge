"""`content-reference-substitute` (REVIEW fixer, ROADMAP item 73 C3): rewrite one unresolved content id to an approved replacement.

Input is the list `substitution-proposals` wrote, with `approved: true` set by a person on the entries to apply
(`options["substitutions"]`). Per entry the fixer edits only the string value equal to the old id in the entry's own referencing
files (a JSON key of that name is left alone) and nothing else; BOM, line endings and layout survive. It refuses:
- an entry that is not approved (it is ignored), or has an id/kind/file it does not understand;
- a file that changed since the proposal (SHA-256 mismatch: a stale approval);
- a `rename` or `catalogue` replacement RC8 does not define (needs `options["vanilla_core"]`);
- a `provider-rename` replacement whose provider the mod does not declare as a dependency.
Compiling or loading is not proof the swap is right: a replacement hull may have other weapon slots. Live proof is a New Game run.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

KINDS = ("hull", "weapon", "hullmod", "wing")
_SAFE_ID = re.compile(r"^[A-Za-z0-9_.\-]+$")


def _declared(root: Path) -> set[str]:
    from ..scanner import _load_lenient_json_file

    info = _load_lenient_json_file(root / "mod_info.json")
    return {str(d.get("id")) for d in (info.get("dependencies") or []) if isinstance(d, dict) and d.get("id")} if isinstance(info, dict) else set()


def _check(root: Path, entry: dict, options: dict, defined: dict) -> list[Path]:
    from . import FixerError

    kind, old, new, source = entry.get("kind"), entry.get("id"), entry.get("replacement"), entry.get("source")
    label = f"{kind}:{old}"
    if kind not in KINDS or not isinstance(old, str) or not isinstance(new, str) or not _SAFE_ID.match(old) or not _SAFE_ID.match(new) or old == new:
        raise FixerError(f"{label}: not a valid substitution ({old!r} -> {new!r}).")
    if source in ("rename", "catalogue"):
        core = options.get("vanilla_core")
        if core is None:
            raise FixerError(f"{label}: a {source} replacement is checked against RC8; pass the vanilla core.")
        if "ids" not in defined:
            from ..content_diff import content_ids

            defined["ids"] = content_ids(Path(core).expanduser().resolve())
        if new not in defined["ids"].get(kind, set()):
            raise FixerError(f"{label}: RC8 does not define {kind} '{new}'.")
    elif source == "provider-rename":
        if entry.get("provider") not in _declared(root):
            raise FixerError(f"{label}: provider '{entry.get('provider')}' is not a declared dependency; declare it first (undeclared-library-dependency).")
    else:
        raise FixerError(f"{label}: unknown source {source!r}.")
    files = []
    for name in entry.get("files") or []:
        path = (root / name).resolve()
        if root not in path.parents or not path.is_file():
            raise FixerError(f"{label}: file '{name}' is outside the mod or missing.")
        if hashlib.sha256(path.read_bytes()).hexdigest() != (entry.get("file_sha256") or {}).get(name):
            raise FixerError(f"{label}: {name} changed since the proposal (stale approval); propose again.")
        files.append(path)
    if not files:
        raise FixerError(f"{label}: the proposal names no referencing file.")
    return files


def fix_content_reference_substitute(root: Path, options: dict) -> list:
    from .. import fixers as _f

    approved = [e for e in options.get("substitutions") or [] if isinstance(e, dict) and e.get("approved") is True]
    if not approved:
        raise _f.FixerError("content-reference-substitute: no approved substitution (set \"approved\": true on a proposal and pass --substitutions).")
    defined: dict = {}
    per_file: dict[Path, list[dict]] = {}
    for entry in approved:
        for path in _check(root, entry, options, defined):
            per_file.setdefault(path, []).append(entry)
    changes = []
    for path, entries in sorted(per_file.items()):
        raw = path.read_bytes()
        text, had_bom = _f._decode(raw)
        for entry in entries:
            # A string value equal to the id; a key (followed by ':') of the same name is not a reference.
            text = re.sub(r'"' + re.escape(entry["id"]) + r'"(?!\s*:)', '"' + entry["replacement"] + '"', text)
        changes.append(_f.FileChange(path=path, before=raw, after=_f._encode(text, had_bom)))
    return changes
