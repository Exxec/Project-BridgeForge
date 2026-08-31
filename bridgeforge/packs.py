from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MigrationPack:
    id: str
    name: str
    scope: str
    status: str
    rules_file: str | None
    path: Path
    min_bridgeforge_version: str | None = None
    max_bridgeforge_version: str | None = None


BRIDGEFORGE_VERSION = "1.0.0"


def bundled_packs_root() -> Path:
    return Path(__file__).with_name("packs")


def discover_packs(root: Path | None = None) -> list[MigrationPack]:
    root = (root or bundled_packs_root()).resolve()
    packs: list[MigrationPack] = []
    for manifest in sorted(root.glob("*/pack.json")):
        try:
            raw = json.loads(manifest.read_text(encoding="utf-8"))
            if raw.get("schema_version") != 1:
                raise ValueError("unsupported schema version")
            pack = MigrationPack(raw["id"], raw["name"], raw["scope"], raw["status"], raw.get("rules_file"), manifest.parent, raw.get("min_bridgeforge_version"), raw.get("max_bridgeforge_version"))
        except (OSError, KeyError, TypeError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"Invalid migration-pack manifest {manifest}: {exc}") from exc
        packs.append(pack)
    if len({pack.id for pack in packs}) != len(packs):
        raise ValueError("Duplicate migration-pack IDs")
    return packs


def _version(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split(".")[:3])


def compatible(pack: MigrationPack) -> bool:
    current = _version(BRIDGEFORGE_VERSION)
    return (not pack.min_bridgeforge_version or current >= _version(pack.min_bridgeforge_version)) and (not pack.max_bridgeforge_version or current <= _version(pack.max_bridgeforge_version))


def resolve_pack_rule_paths(pack_ids: list[str], root: Path | None = None) -> list[Path]:
    available = {pack.id: pack for pack in discover_packs(root)}
    unknown = sorted(set(pack_ids) - set(available))
    if unknown:
        raise ValueError("Unknown migration pack(s): " + ", ".join(unknown))
    paths = []
    for pack_id in pack_ids:
        if not compatible(available[pack_id]):
            raise ValueError(f"Migration pack {pack_id} is incompatible with Bridgeforge {BRIDGEFORGE_VERSION}")
        rules_file = available[pack_id].rules_file
        if rules_file:
            path = available[pack_id].path / rules_file
            if not path.is_file():
                raise ValueError(f"Migration pack {pack_id} declares a missing rules file: {path}")
            paths.append(path)
    return paths
