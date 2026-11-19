"""The current target game build and the game-build registry (ROADMAP-3 item 90, 2026-11-15).

Moving from 0.98a-RC8 to 0.98.5a-RC3 took a dozen hand-run commands, each given the core path again, and a throwaway
script to merge their results. This module keeps that state in `bridgeforge-state/`:

- `target.json` names the current target build and its core. `--vanilla-core @target` (or any other core argument)
  resolves to it in `cli.main`, so the token is explicit and no command changes behaviour by itself.
- `targets/<build>/build.json` is one registry entry: the build string read from the core's jar, a fingerprint of the
  core's jars, the `mod_info.json` `gameVersion` strings that mean the build, observed save versions and a status
  (`QUALIFIED` live-proven, `OBSERVED` diffed and scanned only, `RETIRED`). `target export` writes them all as
  `game-builds.json` for the sister repos, which pin a copy by hash (docs/MULTI_VERSION_COMPAT_DESIGN.md; owner
  decisions 2026-11-15).
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .game_version import core_game_version
from .safeio import atomic_write_json
from bridgeforge.file_hash import sha256_file as _sha256  # 96.5 A10

SCHEMA_VERSION = 1
TOKEN = "@target"
STATUSES = ("QUALIFIED", "OBSERVED", "RETIRED")
FINGERPRINT_JARS = ("starfarer.api.jar", "starfarer_obf.jar", "fs.common_obf.jar")
# mod_info gameVersion strings seen on mods that ran on RC8 (Done/ archives; the game loads both).
KNOWN_MOD_GAME_VERSIONS = {"0.98a-RC8": ("0.98a", "0.98a-RC8")}


class TargetError(Exception):
    pass


def state_dir(repo_root: Path | None = None) -> Path:
    from .substitutes import REPO_ROOT

    return Path(repo_root or REPO_ROOT) / "bridgeforge-state"


def build_dir(state: Path, build: str) -> Path:
    return Path(state) / "targets" / build



def core_fingerprint(core: Path) -> dict[str, str]:
    return {name: _sha256(Path(core) / name) for name in FINGERPRINT_JARS if (Path(core) / name).is_file()}


def mod_game_versions(build: str) -> list[str]:
    """`0.98.5a-RC3` -> ["0.98.5a", "0.98.5a-RC3"]; the build plus its release name without the RC."""
    known = KNOWN_MOD_GAME_VERSIONS.get(build)
    return list(known) if known else sorted({build, build.rsplit("-RC", 1)[0]})


def core_build(core: Path) -> str:
    core = Path(core).expanduser().resolve()
    if not (core / "starfarer.api.jar").is_file():
        raise TargetError(f"{core} is not a starsector-core folder (no starfarer.api.jar).")
    build = core_game_version(core)
    if not build:
        raise TargetError(f"{core}: no game version found in starfarer_obf.jar.")
    return build


def load_build(state: Path, build: str) -> dict | None:
    path = build_dir(state, build) / "build.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def record_build(state: Path, core: Path, *, status: str | None = None, previous: str | None = None) -> dict:
    """Write or refresh `targets/<build>/build.json`; keeps recorded save versions, status and previous build."""
    if status is not None and status not in STATUSES:
        raise TargetError(f"status must be one of {', '.join(STATUSES)}.")
    core = Path(core).expanduser().resolve()
    build = core_build(core)
    old = load_build(state, build) or {}
    fingerprint = core_fingerprint(core)
    if old.get("core_fingerprint") and old["core_fingerprint"] != fingerprint:
        raise TargetError(f"{core} claims {build} but its jars differ from the recorded {build} core "
                          f"({old.get('core')}); a patched or different install. Record it under its own name by hand.")
    entry = {"schema_version": SCHEMA_VERSION, "build": build, "core": str(core), "core_fingerprint": fingerprint,
             "mod_game_versions": old.get("mod_game_versions") or mod_game_versions(build),
             "save_versions": old.get("save_versions", []), "status": status or old.get("status", "OBSERVED"),
             "previous": previous if previous is not None else old.get("previous"),
             "recorded": old.get("recorded", date.today().isoformat())}
    atomic_write_json(build_dir(state, build) / "build.json", entry, indent=2)
    return entry


def load_target(state: Path) -> dict | None:
    path = Path(state) / "target.json"
    if not path.is_file():
        return None
    try:
        target = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise TargetError(f"cannot read target {path}: {exc}; run `bridgeforge target set CORE`.") from exc
    if not isinstance(target, dict) or any(not isinstance(target.get(key), str) or not target[key].strip()
                                           for key in ("build", "core")):
        raise TargetError(f"invalid target {path}: expected non-empty build and core strings; run `bridgeforge target set CORE`.")
    return target


def set_target(state: Path, core: Path, *, status: str | None = None, previous: str | None = None) -> dict:
    entry = record_build(state, core, status=status, previous=previous)
    target = {"schema_version": SCHEMA_VERSION, "build": entry["build"], "core": entry["core"], "set": date.today().isoformat()}
    atomic_write_json(Path(state) / "target.json", target, indent=2)
    return target


def target_core(state: Path) -> Path:
    target = load_target(state)
    if not target:
        raise TargetError(f"no target set ({Path(state) / 'target.json'} missing); run `bridgeforge target set CORE`.")
    core = Path(target["core"])
    if not (core / "starfarer.api.jar").is_file():
        raise TargetError(f"the target core {core} is gone; run `bridgeforge target set CORE` again.")
    return core


def resolve_tokens(args, state: Path | None = None) -> None:
    """Replace every argument that is exactly `@target` with the target core (Path or str, also inside lists)."""
    resolved: list[Path] = []

    def swap(value):
        if isinstance(value, (str, Path)) and str(value) == TOKEN:
            if not resolved:
                resolved.append(target_core(state or state_dir()))
            return resolved[0] if isinstance(value, Path) else str(resolved[0])
        return value

    for name, value in vars(args).items():
        if isinstance(value, list):
            setattr(args, name, [swap(item) for item in value])
        else:
            setattr(args, name, swap(value))


def registry(state: Path) -> dict:
    builds = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((Path(state) / "targets").glob("*/build.json"))]
    target = load_target(state)
    return {"schema_version": SCHEMA_VERSION, "target": target["build"] if target else None,
            "builds": [{k: v for k, v in b.items() if k != "core"} for b in builds]}  # local paths stay local
