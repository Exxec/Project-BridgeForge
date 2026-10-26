"""Renamed or removed ids and classes between a mod's last archive and its next revision (ROADMAP item 73 H3).

A save made with the archived build still names its old content ids and classes. When a revision drops one, the player's save can
break, so the revision needs a migration pack (the evidence contract in `docs/MIGRATION_PACK_CONTRACT.md`, checked with
`save-compat` against a save) or a written reason why none is needed. `revise finalize` enforces this; this module computes the
requirement and judges the evidence.

BridgeForge cannot tell a rename from a removal, so every id or class present in the previous archive and absent now counts. The
evidence file `reports/REVISION_MIGRATION.json` (outside `working/`, so never shipped) carries the digest of that removed set; a file
written for another set is stale.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .safeio import atomic_write_json

EVIDENCE_FILE = "REVISION_MIGRATION.json"
PACK_FIELDS = ("provenance", "before_fixture", "after_fixture", "compile_validation", "idempotence", "conflict_review", "save_risk_assessment")
MIN_REASON_CHARS = 20


def class_names(root: Path) -> set[str]:
    """Dotted class names a mod folder provides: class entries of its jars and its loose .java scripts."""
    from bridgeforge.save.save_compat import _entry_names

    root = Path(root)
    names: set[str] = set()
    for jar in sorted(root.rglob("*.jar")) if root.is_dir() else []:
        for entry in _entry_names(jar):
            if entry.lower().endswith(".class"):
                names.add(entry[: -len(".class")].replace("/", "."))
    for java in sorted(root.rglob("*.java")) if root.is_dir() else []:
        relative = java.relative_to(root).as_posix()
        if relative.lower().startswith(("src/", "scratch/", "reports/")):
            continue
        names.add(relative[: -len(".java")].replace("/", "."))
    return names


def removed_since(previous_root: Path, working: Path) -> dict:
    """{"ids": {kind: [id...]}, "classes": [name...]} present in the previous archive's mod folder and absent from `working`."""
    from .content_diff import content_ids

    old_ids, new_ids = content_ids(Path(previous_root)), content_ids(Path(working))
    ids = {kind: sorted(old_ids[kind] - new_ids[kind]) for kind in old_ids if old_ids[kind] - new_ids[kind]}
    classes = sorted(class_names(previous_root) - class_names(working))
    return {"ids": ids, "classes": classes}


def removed_digest(removed: dict) -> str:
    return hashlib.sha256(json.dumps(removed, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def migration_requirement(workspace: Path, previous_root: Path | None, working: Path, new_version: str | None = None) -> dict:
    """Whether the revision needs migration evidence and whether it has it.

    {"required", "removed", "removed_sha256", "satisfied", "how" (pack|reason|None), "problems"}. No previous archive means a first
    archive: nothing to migrate from, nothing required."""
    workspace = Path(workspace)
    if previous_root is None or not Path(previous_root).is_dir():
        return {"required": False, "removed": {"ids": {}, "classes": []}, "removed_sha256": None, "satisfied": True, "how": None, "problems": []}
    removed = removed_since(previous_root, working)
    if not removed["ids"] and not removed["classes"]:
        return {"required": False, "removed": removed, "removed_sha256": removed_digest(removed), "satisfied": True, "how": None, "problems": []}
    digest = removed_digest(removed)
    summary = f"{sum(len(v) for v in removed['ids'].values())} id(s) and {len(removed['classes'])} class(es) of the previous archive are gone"
    problems: list[str] = []
    how = None
    try:
        evidence = json.loads((workspace / "reports" / EVIDENCE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        evidence = None
    if not isinstance(evidence, dict):
        problems.append(f"{summary}: give a migration pack or a written reason (`revise migration`; reports/{EVIDENCE_FILE})")
    elif evidence.get("removed_sha256") != digest:
        problems.append(f"reports/{EVIDENCE_FILE} was written for a different set of removed ids or classes ({summary} now); write it again")
    elif evidence.get("pack"):
        how = "pack"
        problems.extend(_pack_problems(evidence["pack"], Path(working)))
    elif len(str(evidence.get("reason") or "").strip()) >= MIN_REASON_CHARS:
        how = "reason"
    else:
        problems.append(f"reports/{EVIDENCE_FILE} has neither a migration pack nor a written reason of at least {MIN_REASON_CHARS} characters")
    return {"required": True, "removed": removed, "removed_sha256": digest, "satisfied": not problems, "how": how if not problems else None,
            "problems": problems}


def _pack_problems(pack: object, working: Path) -> list[str]:
    from bridgeforge.save.save_compat import SaveCompatError, check_save_compat

    if not isinstance(pack, dict):
        return ["the migration pack is not an object"]
    problems = [f"migration pack lacks {field} (docs/MIGRATION_PACK_CONTRACT.md)" for field in PACK_FIELDS if not str(pack.get(field) or "").strip()]
    save = (pack.get("save_compat") or {}).get("save") if isinstance(pack.get("save_compat"), dict) else None
    if not save:
        problems.append("migration pack names no save to check with save-compat (save_compat.save)")
        return problems
    try:
        result = check_save_compat(Path(save), working)
    except (SaveCompatError, OSError, ValueError) as exc:
        return [*problems, f"save-compat could not check {save}: {exc}"]
    if result.get("status") != "LOADS":
        problems.append(f"save-compat says {result.get('status')} for {save}: {len(result.get('missing') or [])} missing class reference(s)")
    return problems


def write_evidence(workspace: Path, requirement: dict, *, reason: str | None = None, pack: dict | None = None) -> Path:
    """Record the owner's answer for the current removed set: a written reason, or a migration pack. Never edits the mod."""
    if not requirement.get("required"):
        raise ValueError("this revision removes no ids or classes: no migration evidence is needed")
    if bool(reason) == bool(pack):
        raise ValueError("give exactly one of a reason or a pack")
    data: dict = {"schema_version": 1, "removed_sha256": requirement["removed_sha256"], "removed": requirement["removed"]}
    data.update({"reason": reason.strip()} if reason else {"pack": pack})
    return atomic_write_json(Path(workspace) / "reports" / EVIDENCE_FILE, data)
