from __future__ import annotations

import csv
import json
import zipfile
from pathlib import Path

"""Shared fixture builders for save-tooling tests (P3b), kept self-contained per this
project's convention (see test_save_compat.py) rather than depending on any one test module."""


def _u2(value: int) -> bytes:
    return value.to_bytes(2, "big")


def _utf8_entry(text: str) -> bytes:
    encoded = text.encode("utf-8")
    return b"\x01" + _u2(len(encoded)) + encoded


def _class_entry(name_index: int) -> bytes:
    return b"\x07" + _u2(name_index)


def build_class_file(this_class: str, super_class: str = "java/lang/Object") -> bytes:
    pool: list[bytes] = []

    def add_utf8(text: str) -> int:
        pool.append(_utf8_entry(text))
        return len(pool)

    def add_class(name_index: int) -> int:
        pool.append(_class_entry(name_index))
        return len(pool)

    this_class_idx = add_class(add_utf8(this_class))
    super_class_idx = add_class(add_utf8(super_class))

    constant_pool_count = len(pool) + 1
    data = b"\xca\xfe\xba\xbe" + _u2(0) + _u2(52) + _u2(constant_pool_count)
    data += b"".join(pool)
    data += _u2(0x0021)
    data += _u2(this_class_idx)
    data += _u2(super_class_idx)
    data += _u2(0)
    data += _u2(0)
    data += _u2(0)
    data += _u2(0)
    return data


def write_jar(path: Path, members: dict[str, bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for member, content in members.items():
            archive.writestr(member, content)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_mod_info(mod_dir: Path, *, mod_id: str, name: str | None = None, version: str = "1.0") -> None:
    write_text(
        mod_dir / "mod_info.json",
        json.dumps({"id": mod_id, "name": name or mod_id, "version": version}),
    )


def write_mod_class_jar(mod_dir: Path, class_names: list[str], jar_name: str = "mod.jar") -> None:
    write_jar(
        mod_dir / "jars" / jar_name,
        {f"{name.replace('.', '/')}.class": build_class_file(name.replace(".", "/")) for name in class_names},
    )


def write_mod_data(
    mod_dir: Path,
    *,
    hulls: tuple[str, ...] = (),
    variants: tuple[str, ...] = (),
    weapons: tuple[str, ...] = (),
    hullmods: tuple[str, ...] = (),
    factions: tuple[str, ...] = (),
    commodities: tuple[str, ...] = (),
    industries: tuple[str, ...] = (),
    market_conditions: tuple[str, ...] = (),
    special_items: tuple[str, ...] = (),
) -> None:
    data = mod_dir / "data"
    for hull in hulls:
        write_text(data / "hulls" / f"{hull}.ship", json.dumps({"hullId": hull}))
    for variant in variants:
        write_text(data / "variants" / f"{variant}.variant", json.dumps({"variantId": variant}))
    for weapon in weapons:
        write_text(data / "weapons" / f"{weapon}.wpn", json.dumps({"id": weapon}))
    if hullmods:
        _write_csv(data / "hullmods" / "hull_mods.csv", hullmods)
    for faction in factions:
        write_text(data / "world" / "factions" / f"{faction}.faction", '{id:"%s","displayName":"%s"}' % (faction, faction))
    for category, ids in (
        ("commodities", commodities),
        ("industries", industries),
        ("market_conditions", market_conditions),
        ("special_items", special_items),
    ):
        if ids:
            _write_csv(data / "campaign" / f"{category}.csv", ids)


def _write_csv(path: Path, ids: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["name", "id"])
        writer.writeheader()
        for id_ in ids:
            writer.writerow({"name": id_, "id": id_})


def write_descriptor(
    save_dir: Path,
    mods: list[dict[str, str]],
    *,
    character_name: str = "Test Character",
    save_date: str = "2026-09-10 00:00:00.000 UTC",
    game_version: str = "0.98a-RC8",
) -> None:
    """Write a synthetic descriptor.xml matching the real structure verified against
    `In operation/_rig/saves/save_FourthAnderson_*/descriptor.xml`:
    `allModsEverEnabled/EnabledModData/spec[@z]` plus `enabledMods/EnabledModData/spec[@ref]`.
    """
    lines = ['<?xml version="1.0" ?>', '<SaveGameData z="1">']
    lines.append(f"<characterName>{character_name}</characterName>")
    lines.append(f"<gameVersion>{game_version}</gameVersion>")
    lines.append(f'<saveDate z="3">{save_date}</saveDate>')
    lines.append('<allModsEverEnabled z="4">')
    z = 10
    spec_zs = []
    for mod in mods:
        emd_z, z = z, z + 1
        spec_z, z = z, z + 1
        gv_z, z = z, z + 1
        vi_z, z = z, z + 1
        spec_zs.append(spec_z)
        lines.append(f'<EnabledModData z="{emd_z}">')
        lines.append(f'<spec z="{spec_z}">')
        lines.append(f'<id>{mod["id"]}</id>')
        lines.append(f'<name>{mod.get("name", mod["id"])}</name>')
        lines.append(f'<gameVersion z="{gv_z}"><string>{mod.get("game_version", "0.98a-RC8")}</string></gameVersion>')
        lines.append(f'<versionInfo z="{vi_z}"><string>{mod.get("version", "1.0")}</string></versionInfo>')
        lines.append(f'<dirName>{mod.get("dir_name", mod["id"])}</dirName>')
        lines.append("</spec>")
        lines.append("</EnabledModData>")
    lines.append("</allModsEverEnabled>")
    lines.append(f'<enabledMods z="{z}">')
    z += 1
    for spec_z in spec_zs:
        lines.append(f'<EnabledModData z="{z}"><spec ref="{spec_z}"></spec></EnabledModData>')
        z += 1
    lines.append("</enabledMods>")
    lines.append("</SaveGameData>")
    write_text(save_dir / "descriptor.xml", "\n".join(lines) + "\n")
