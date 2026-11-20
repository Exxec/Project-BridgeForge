"""94.G1 WP4 (GR-6): the one place that answers what a mod's licence allows.

`bridgeforge/release_policy.json` and its fragments (`release_policy.d/`, 96.5 A7) stay the only record: one entry per mod
with `local_only`, `reason`, `recorded_on` and, new here, optional `paths` exceptions. This module is the only reader
outside `release.py` (which owns the file format and the writers); `tests/test_licence_ledger.py` fails on any other module
importing the policy internals. `vendor-copy`, `vendor-plan`, `gene describe`, the release gate, dependency-substitutes,
case qualification and the archive note all ask here, so GD-2 is enforced in one place. GD-2 as amended by the owner on
2026-11-19: a recorded LOCAL_ONLY decision, or a local-only path, stops distribution; a mod with no recorded decision counts
as releasable. Archiving still records the standing local-only decision for a revival (owner 2026-09-27).

A path exception marks part of a mod local-only although the mod is releasable: another author's sprites or a bundled
library. `prefix` is relative to the mod root (the folder holding mod_info.json), in posix form, and matches whole path
segments: `graphics/foo` covers `graphics/foo/a.png`, not `graphics/foobar/a.png`. A member path is matched by its file:
`jars/x.jar!a/B.class` by `jars/x.jar`, `data/hullmods/hull_mods.csv [id]` by the CSV file.

Uses (`licence_allows`):
- `local`: always allowed.
- `vendor`: copy content into another mod. A local-only source, or a local-only path of a releasable one, may go only into
  a target that is itself local-only, which must then stay local-only (owner decision 2026-09-27; RevenantLib).
- `distribute`: publish. Refused for a LOCAL_ONLY decision or a local-only path among the paths given; allowed for a
  RELEASABLE decision and, by the owner's 2026-11-19 ruling, for a mod with no decision, as the release gate already read it.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from bridgeforge.release import DEFAULT_POLICY_PATH, _licence_gate, _load_policy, policy_entry

USES = ("local", "vendor", "distribute")
UNRECORDED_REASON = "no entry in release_policy.json: check the licence and record a decision before reviving"


def decision(mod_id: str | None, name: str | None, policy_path: Path | None = None) -> dict[str, object]:
    """LOCAL_ONLY, RELEASABLE or UNRECORDED with its reason, from the mod's own entry (never the default)."""
    entry = policy_entry(_load_policy(policy_path), mod_id, name)
    if entry is None:
        return {"decision": "UNRECORDED", "reason": UNRECORDED_REASON}
    return {"decision": "LOCAL_ONLY" if entry.get("local_only") else "RELEASABLE", "reason": entry.get("reason")}


def explicit_entry(mod_id: str | None, name: str | None, policy_path: Path | None = None) -> dict | None:
    """The mod's own entry as recorded, or None; for checks that need a written decision, not the default."""
    return policy_entry(_load_policy(policy_path), mod_id, name)


def release_gate(mod_id: str | None, name: str | None, policy_path: Path | None = None) -> dict[str, object]:
    """The release gate's verdict: the mod's entry, or the policy's default when it has none (PASS unless local-only)."""
    return _licence_gate(mod_id, name, policy_path)


_JAR_CLASS = re.compile(r"^(?P<file>.+?\.jar)!.")
_CSV_ROW = re.compile(r"^(?P<file>.+?\.csv) \[.*\]$", re.IGNORECASE)
_JSON_ENTRY = re.compile(r"^(?P<file>.+?\.json)#/", re.IGNORECASE)  # gene.json schema 3 (94.G2)


def member_file(path: str) -> str:
    """The file a member path names: `jars/x.jar!a/B.class` -> `jars/x.jar`, `t.csv [id]` -> `t.csv`,
    `data/config/settings.json#/key` -> `data/config/settings.json`. Other paths are files, whatever they contain:
    `foo [v2].png` and `boom!.ogg` are names, not members of something."""
    match = _JAR_CLASS.match(path) or _CSV_ROW.match(path) or _JSON_ENTRY.match(path)
    return match["file"] if match else path


def _covers(prefix: str, path: str) -> bool:
    # Case-folded: mods ship for Windows, where Graphics/Ships and graphics/ships are one folder (review 2026-11-19).
    prefix, path = prefix.rstrip("/").casefold(), path.casefold()
    if path == prefix or path.startswith(prefix + "/"):
        return True
    # vendor-plan names a jar-class member by the jar's file name only (`x.jar!a/B.class`): an exception on any jar of that
    # name covers it. That may cover too much, never too little.
    return "/" not in path and path.endswith(".jar") and prefix.rsplit("/", 1)[-1] == path


def local_only_paths(mod_id: str | None, name: str | None, paths: Iterable[str], policy_path: Path | None = None) -> list[dict]:
    """[{path, prefix, reason}] for each of `paths` that a local-only exception of the mod covers, in the given order."""
    entry = explicit_entry(mod_id, name, policy_path) or {}
    exceptions = [e for e in entry.get("paths") or [] if e.get("local_only")]
    found = []
    for path in paths:
        hit = next((e for e in exceptions if _covers(e["prefix"], member_file(path))), None)
        if hit is not None:
            found.append({"path": path, "prefix": hit["prefix"], "reason": hit["reason"]})
    return found


def _target_info(target_root: Path) -> tuple[str | None, str | None]:
    from bridgeforge.release import _load_lenient_json_file

    root = Path(target_root).expanduser().resolve()
    info_path = root / "mod_info.json" if (root / "mod_info.json").is_file() else root / "working" / "mod_info.json"
    info = _load_lenient_json_file(info_path) if info_path.is_file() else None
    return (info.get("id"), info.get("name")) if isinstance(info, dict) else (None, None)


def vendoring(source_id: str | None, source_name: str | None, target_root: Path, policy_path: Path | None = None,
              paths: Iterable[str] = ()) -> dict[str, object]:
    """May `paths` of `source` be copied into the mod at `target_root`? {allowed, must_stay_local_only, reason}."""
    policy_path = policy_path or DEFAULT_POLICY_PATH
    label = source_name or source_id
    source = _licence_gate(source_id, source_name, policy_path)
    restricted = local_only_paths(source_id, source_name, paths, policy_path)
    if not source["local_only"] and not restricted:
        return {"allowed": True, "must_stay_local_only": False, "reason": None}
    if source["local_only"]:  # the whole mod: the wording vendor-copy has always given
        what, short = f"{label} is local-only per release_policy.json ({source.get('reason')})", f"{label} is local-only"
    else:
        first = restricted[0]
        short = f"{len(restricted)} path(s) of {label} are local-only ({first['path']} under {first['prefix']}: {first['reason']})"
        what = f"{len(restricted)} path(s) of {label} are local-only per release_policy.json ({first['path']} under {first['prefix']}: {first['reason']})"
    target_id, target_name = _target_info(target_root)
    if _licence_gate(target_id, target_name, policy_path)["local_only"]:
        return {"allowed": True, "must_stay_local_only": True,
                "reason": f"{short}, and so is {target_name or target_id}; it must stay local-only while it holds this content"}
    return {"allowed": False, "must_stay_local_only": False,
            "reason": f"{what}; it may only be vendored into a local-only target such as RevenantLib"}


def licence_allows(mod_id: str | None, name: str | None, use: str, *, paths: Iterable[str] = (), target: Path | None = None,
                   policy_path: Path | None = None) -> dict[str, object]:
    """{allowed, reason} for one use of the mod's content (see the module docstring); `vendor` needs `target`."""
    if use not in USES:
        raise ValueError(f"use is one of {', '.join(USES)}; got {use!r}")
    if use == "local":
        return {"allowed": True, "reason": "local, personal use (GD-2)"}
    paths = list(paths)
    if use == "vendor":
        if target is None:
            raise ValueError("the vendor use needs the target mod")
        verdict = vendoring(mod_id, name, target, policy_path, paths)
        return {"allowed": verdict["allowed"], "reason": verdict["reason"], "must_stay_local_only": verdict["must_stay_local_only"]}
    recorded = decision(mod_id, name, policy_path)
    if recorded["decision"] == "LOCAL_ONLY":
        return {"allowed": False, "reason": f"LOCAL_ONLY: {recorded['reason']}"}
    restricted = local_only_paths(mod_id, name, paths, policy_path)
    if restricted:
        return {"allowed": False, "reason": f"{restricted[0]['path']} is local-only under {restricted[0]['prefix']}: {restricted[0]['reason']}"}
    if recorded["decision"] == "UNRECORDED":  # owner 2026-11-19: "mark unmarked mods as releasable", by rule, no records written
        return {"allowed": True, "reason": "no decision recorded: releasable by default (owner 2026-11-19)"}
    return {"allowed": True, "reason": recorded["reason"]}


__all__ = ["USES", "decision", "explicit_entry", "licence_allows", "local_only_paths", "member_file", "release_gate", "vendoring"]
