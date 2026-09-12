from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .save_compat import check_save_compat
from .save_content_compat import check_save_content
from .save_inspect import inspect_save
from .save_reader import parse_descriptor

"""Redacted, shareable save summary for bug reports (roadmap P3b-L).

`redacted_summary` writes a small JSON document -- mod list/versions, `save_compat` and
`save_content_compat` verdicts, the ids/classes that would fail to load, and per-mod object
counts -- without the 10 MB save itself, so a player or the owner can share it without copying a
whole campaign.

## No player data, by construction

This function never reads `descriptor.xml`'s `characterName`, `saveDate`, or `portraitName`, and
never reads any save element's free-text fields (ship names like `FMmbr`'s `sN=`, fleet names,
`desc`/`locDesc`). It is built entirely from `save_compat`/`check_save_content`/`inspect_save`
results, which only ever report class names, data ids, counts, and structural paths -- none of
which are player-chosen text. The save directory's own path (which can contain the player's
in-game character name, since Starsector names save folders `save_<CharacterName>_<seed>`) is
never included in the clear; only its SHA-256 hash (truncated to 16 hex chars) is.

Writes only to the `out_path` the caller supplies -- never a default location under the save,
the rig, or any Starsector install.
"""


def redacted_summary(
    save: Path | str,
    mod_dirs: list[Path | str],
    *,
    out_path: Path | str,
    vanilla_core: Path | str | None = None,
) -> dict:
    descriptor = parse_descriptor(save)
    save_id_hash = hashlib.sha256(descriptor["save_dir"].encode("utf-8")).hexdigest()[:16]

    mods = [
        {
            "id": mod.get("id"),
            "version": mod.get("version"),
            "game_version": mod.get("game_version"),
            "build_tag": mod.get("build_tag"),
        }
        for mod in descriptor["enabled_mods"]
    ]

    checks: list[dict[str, object]] = []
    for mod_dir in mod_dirs:
        compat = check_save_compat(save, mod_dir, vanilla_core=vanilla_core)
        content = check_save_content(save, mod_dir, vanilla_core=vanilla_core)
        object_counts = inspect_save(save, mod_dir=mod_dir)["mod_object_counts"]
        checks.append(
            {
                "mod_id": compat.get("mod_id"),
                "class_compat_status": compat["status"],
                "class_missing": sorted(entry["reference"] for entry in compat["missing"]),
                "content_compat_status": content["status"],
                "content_missing": sorted(entry["id"] for entry in content["missing"]),
                "object_counts_by_namespace": (object_counts or {}).get("by_namespace", {}),
            }
        )

    summary = {
        "schema_version": 1,
        "mode": "REDACTED_SAVE_SUMMARY",
        "save_id_hash": save_id_hash,
        "save_game_version": descriptor["game_version"],
        "mods": mods,
        "checks": checks,
    }

    out_path = Path(out_path).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return summary
