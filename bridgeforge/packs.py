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
