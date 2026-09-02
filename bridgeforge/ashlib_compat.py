from __future__ import annotations

import json
from pathlib import Path


def scan_ashlib_compat(root: Path, result) -> None:
    """Read-only AshLib dependency evidence; AshLib publishes no API migration contract."""
    imports = sorted({fact["value"] for fact in result.source_facts if fact["kind"] == "import" and fact["value"].startswith("ashlib.")})
    if imports:
        result.add(id="ashlib-api-usage", category="ashlib-compatibility", severity="info", classification="SAFE", confidence="DETERMINISTIC", explanation="AST import evidence shows direct AshLib API use. The verified public AshLib legacy-to-2.2.3 history documents additive features and fixes, but no removed/deprecated API replacement contract; BridgeForge therefore makes no source-migration suggestion.", evidence=imports)
    for version_file in root.rglob("ashlib.version"):
        relative = version_file.relative_to(root).as_posix()
        try:
            marker = json.loads(version_file.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError) as exc:
            result.add(id="ashlib-version-marker-unreadable", category="dependencies", severity="medium", classification="REVIEW", confidence="DETERMINISTIC", explanation="An AshLib version marker exists but could not be structurally read. Confirm the supplied library version manually; no source migration is inferred.", file=relative, evidence=[str(exc)])
            continue
        version = marker.get("modVersion") if isinstance(marker, dict) else None
        value = f"{version['major']}.{version['minor']}.{version['patch']}" if isinstance(version, dict) and all(isinstance(version.get(part), int) for part in ("major", "minor", "patch")) else json.dumps(marker, sort_keys=True)
        result.add(id="ashlib-version-evidence", category="dependencies", severity="info", classification="SAFE", confidence="DETERMINISTIC", explanation="A local AshLib version marker was found. It establishes dependency evidence only; AshLib has no verified public API migration mapping in BridgeForge's evidence contract.", file=relative, evidence=[value])
