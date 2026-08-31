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
            pack = MigrationPack(raw["id"], raw["name"], raw["scope"], raw["status"], raw.get("rules_file"), manifest.parent)
        except (OSError, KeyError, TypeError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"Invalid migration-pack manifest {manifest}: {exc}") from exc
        packs.append(pack)
    if len({pack.id for pack in packs}) != len(packs):
        raise ValueError("Duplicate migration-pack IDs")
    return packs


def resolve_pack_rule_paths(pack_ids: list[str], root: Path | None = None) -> list[Path]:
    available = {pack.id: pack for pack in discover_packs(root)}
    unknown = sorted(set(pack_ids) - set(available))
    if unknown:
        raise ValueError("Unknown migration pack(s): " + ", ".join(unknown))
    paths = []
    for pack_id in pack_ids:
        rules_file = available[pack_id].rules_file
        if rules_file:
            path = available[pack_id].path / rules_file
            if not path.is_file():
                raise ValueError(f"Migration pack {pack_id} declares a missing rules file: {path}")
            paths.append(path)
    return paths
