from __future__ import annotations

import json
import re
from pathlib import Path


VERSION_MARKERS = ("graphicslib.version", "shaderlib.version")
LEGACY_SETTINGS = "shaderSettings.json"


def scan_graphicslib_compat(root: Path, result) -> None:
    """Read-only GraphicsLib compatibility findings from its published 0.98a notes."""
    imports = sorted({fact["value"] for fact in result.source_facts if fact["kind"] == "import" and fact["value"].startswith("org.dark.shaders.")})
    if imports:
        result.add(id="graphicslib-api-usage", category="graphicslib-compatibility", severity="info", classification="SAFE", confidence="DETERMINISTIC", explanation="AST import evidence shows direct GraphicsLib (ShaderLib) API use. Verify the installed library version against the selected target; this observation does not infer an API rewrite.", evidence=imports)
    for fact in result.source_facts:
        if fact["kind"] == "import" and fact["value"].endswith(".MissileSelfDestruct"):
            result.add(id="graphicslib-missile-self-destruct-removed", category="graphicslib-compatibility", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation="GraphicsLib 1.10.0 for Starsector 0.98a removed MissileSelfDestruct. No replacement is documented, so preserve the mod's missile behavior through manual design and combat validation; BridgeForge will not rewrite it.", file=fact["file"], evidence=[fact["value"]])
    for path in root.rglob("no_self_destruct.csv"):
        result.add(id="graphicslib-no-self-destruct-config-removed", category="graphicslib-compatibility", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation="GraphicsLib 1.10.0 for Starsector 0.98a removed no_self_destruct.csv with MissileSelfDestruct. This configuration no longer has the documented owning feature; decide manually whether the missiles need a replacement behavior.", file=path.relative_to(root).as_posix(), evidence=["data/config/no_self_destruct.csv"])
    for path in root.rglob(LEGACY_SETTINGS):
        result.add(id="graphicslib-shader-settings-renamed", category="graphicslib-compatibility", severity="high", classification="REVIEW", confidence="DETERMINISTIC", explanation="GraphicsLib's documented 1.0.0 transition renamed shaderSettings.json to GRAPHICS_OPTIONS.ini. The formats and settings semantics need review, so this is an evidence-contract candidate only and BridgeForge will not rename or convert the file.", file=path.relative_to(root).as_posix(), evidence=[LEGACY_SETTINGS, "candidate: GRAPHICS_OPTIONS.ini"])
    for marker_name in VERSION_MARKERS:
        for version_file in root.rglob(marker_name):
            relative = version_file.relative_to(root).as_posix()
            try:
                raw = version_file.read_text(encoding="utf-8", errors="replace")
                marker = json.loads(re.sub(r",\s*([}\]])", r"\1", raw))
            except (OSError, json.JSONDecodeError) as exc:
                result.add(id="graphicslib-version-marker-unreadable", category="dependencies", severity="medium", classification="REVIEW", confidence="DETERMINISTIC", explanation="A GraphicsLib/ShaderLib version marker exists but could not be structurally read. Confirm the supplied library version manually; no source migration is inferred.", file=relative, evidence=[str(exc)])
                continue
            version = marker.get("modVersion") if isinstance(marker, dict) else None
            value = f"{version['major']}.{version['minor']}.{version['patch']}" if isinstance(version, dict) and all(isinstance(version.get(part), int) for part in ("major", "minor", "patch")) else json.dumps(marker, sort_keys=True)
            result.add(id="graphicslib-version-evidence", category="dependencies", severity="info", classification="SAFE", confidence="DETERMINISTIC", explanation="A local GraphicsLib/ShaderLib version marker was found. It establishes dependency evidence only; it does not authorize a source rewrite.", file=relative, evidence=[value])
