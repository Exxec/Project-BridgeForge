"""93.68: a mod's variants and the ship sections they carry, for the probe's combat plan (`probe_config`).

A ship section is a hull another variant lists under `modules`: it fights with its parent and logs its deployment when the
parent's ship appears. P035-BULTACH-20261122 gave 32 of its 108 planned hulls a fleet slot of their own.
"""
from __future__ import annotations

from pathlib import Path

from bridgeforge.scan.scanner import _load_lenient_json_file


def variant_index(mod_root: Path) -> tuple[dict[str, str], dict[str, list[str]]]:
    """({variant id: hull id}, {variant id: the module variants its `modules` lists}) of the mod's data/variants. `modules` is a
    {slot: variant} object or a list of them."""
    variants_root = Path(mod_root) / "data" / "variants"
    hull_of: dict[str, str] = {}
    modules_of: dict[str, list[str]] = {}
    for path in sorted(variants_root.rglob("*.variant")) if variants_root.is_dir() else []:
        data = _load_lenient_json_file(path)
        if not isinstance(data, dict) or not isinstance(data.get("hullId"), str):
            continue
        variant_id = str(data.get("variantId") or data.get("id") or path.stem)
        hull_of[variant_id] = data["hullId"]
        modules = data.get("modules")
        entries = modules if isinstance(modules, list) else [modules] if isinstance(modules, dict) else []
        modules_of[variant_id] = [v for entry in entries if isinstance(entry, dict) for v in entry.values() if isinstance(v, str)]
    return hull_of, modules_of


def ship_sections(mod_root: Path, deploy_variants: dict[str, str]) -> list[str]:
    """The hulls the probe's chosen variants carry as modules. Review of 0.3.6: a hull is a section only when the variant the
    plan deploys for its parent lists it; a parent deployed through a variant without modules leaves it a ship of its own."""
    hull_of, modules_of = variant_index(mod_root)
    carried = {hull_of[module] for variant in deploy_variants.values() for module in modules_of.get(variant, []) if module in hull_of}
    return sorted(carried & set(deploy_variants))


__all__ = ["ship_sections", "variant_index"]
