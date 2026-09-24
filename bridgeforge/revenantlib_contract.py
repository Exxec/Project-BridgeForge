"""`bridgeforge revenantlib-check`: does a RevenantLib build provide what BridgeForge's fixers call?

The `removed-api-call` fixer rewrites 0.6-era calls into static calls on RevenantLib classes and adds
`revenantlib` as a dependency (see `fixers._BF_CALL_SIGNATURES`). If a RevenantLib build renames,
drops or re-signatures one of those methods, every mod the fixer touched compiles fine in
BridgeForge's own tests and then fails in the game. `CONTRACT` pins the exact methods; this checks
a jar against it, and (given a mod folder with `src/`) that every source file has a compiled class
in the jar, so a stale jar is caught before a rig run.

Contract evidence: descriptors read from RevenantLib 1.2.0+bf.1's `jars/RevenantLib.jar` with
`rebuild_jar._parse_class`, 2026-09-24 (all three `public static`).

Read-only.
"""
from __future__ import annotations

import json
from pathlib import Path

from .api_diff import render_method
from .rebuild_jar import _classes_from_jar, _parse_class

SCHEMA_VERSION = 1
_ACC_PUBLIC_STATIC = 0x0001 | 0x0008

# (class, method, descriptor, the fixer rule that emits the call)
CONTRACT = (
    ("bf/legacyfleets/LegacyFleets", "createFleet",
     "(Ljava/lang/String;Ljava/lang/String;)Lcom/fs/starfarer/api/campaign/CampaignFleetAPI;",
     "SectorAPI.createFleet(factionId, fleetTypeId)"),
    ("bf/legacyworld/LegacyWorld", "addPlanet",
     "(Lcom/fs/starfarer/api/campaign/LocationAPI;Lcom/fs/starfarer/api/campaign/SectorEntityToken;"
     "Ljava/lang/String;Ljava/lang/String;FFFF)Lcom/fs/starfarer/api/campaign/PlanetAPI;",
     "LocationAPI.addPlanet(...) 7-argument 0.6 form"),
    ("bf/legacyworld/LegacyWorld", "addOrbitalStation",
     "(Lcom/fs/starfarer/api/campaign/LocationAPI;Lcom/fs/starfarer/api/campaign/SectorEntityToken;"
     "FFFLjava/lang/String;Ljava/lang/String;)Lcom/fs/starfarer/api/campaign/SectorEntityToken;",
     "LocationAPI.addOrbitalStation(...) 6-argument 0.6 form"),
)


class RevenantLibCheckError(ValueError):
    """Raised when the input is neither a jar nor a RevenantLib mod folder with a declared jar."""


def _locate(path: Path) -> tuple[Path, Path | None]:
    """(jar, src dir or None). Accepts the jar, a mod folder, or a repo root holding working/."""
    path = Path(path).expanduser().resolve()
    if path.is_file():
        return path, None
    mod = path / "working" if (path / "working" / "mod_info.json").is_file() else path
    info = mod / "mod_info.json"
    if not info.is_file():
        raise RevenantLibCheckError(f"{path} is not a jar, a mod folder with mod_info.json, or a repo root holding working/.")
    try:
        jars = json.loads(info.read_text(encoding="utf-8-sig")).get("jars") or []
    except (json.JSONDecodeError, AttributeError) as exc:
        raise RevenantLibCheckError(f"{info} is not strict JSON: {exc}") from None
    if len(jars) != 1 or not (mod / jars[0]).is_file():
        raise RevenantLibCheckError(f"{info} must declare exactly one existing jar; declares {jars}.")
    src = mod / "src"
    return mod / jars[0], src if src.is_dir() else None


def check_revenantlib(path: Path) -> dict:
    jar, src = _locate(path)
    classes = _classes_from_jar(jar.read_bytes())
    parsed: dict[str, object] = {}
    contract = []
    for owner, name, descriptor, replaces in CONTRACT:
        entry = {"call": f"{owner.replace('/', '.')}.{render_method(owner, name, descriptor).split(' ', 1)[-1]}", "replaces": replaces}
        data = classes.get(owner + ".class")
        info = parsed.setdefault(owner, _parse_class(data) if data is not None else None)
        member = info.methods.get((name, descriptor)) if info is not None else None
        if info is None:
            entry["status"], entry["detail"] = "FAIL", "class missing from the jar" if data is None else "class file unparseable"
        elif member is None:
            others = sorted(render_method(owner, n, d) for (n, d) in info.methods if n == name)
            entry["status"], entry["detail"] = "FAIL", "method missing" + (f"; same name: {', '.join(others)}" if others else "")
        elif member.access_flags & _ACC_PUBLIC_STATIC != _ACC_PUBLIC_STATIC:
            entry["status"], entry["detail"] = "FAIL", f"not public static (access flags {member.access_flags:#06x})"
        else:
            entry["status"] = "PASS"
        contract.append(entry)

    stale = {"checked": src is not None, "sources_without_class": [], "classes_without_source": []}
    if src is not None:
        sources = {p.relative_to(src).with_suffix("").as_posix() for p in src.rglob("*.java")}
        top_level = {name[:-len(".class")] for name in classes if "$" not in name}
        stale["sources_without_class"] = sorted(sources - top_level)
        stale["classes_without_source"] = sorted(top_level - sources)
    ok = all(entry["status"] == "PASS" for entry in contract) and not stale["sources_without_class"] and not stale["classes_without_source"]
    return {
        "schema_version": SCHEMA_VERSION, "mode": "REVENANTLIB_CHECK", "jar": str(jar), "status": "PASS" if ok else "FAIL",
        "contract": contract, "jar_vs_source": stale,
        "note": "Checks presence and signatures only; it cannot tell whether the jar was built from the current source text.",
    }
