from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from .models import ScanResult


def render_markdown(result: ScanResult) -> str:
    counts = Counter(finding.classification for finding in result.findings)
    lines = [
        "# Bridgeforge modernization report",
        "",
        "## Scan summary",
        "",
        f"- Input mod: `{result.input_path}`",
        f"- Target: Starsector {result.target.starsector}, Java {result.target.java}",
        f"- Files inventoried: {len(result.files)}",
        f"- JARs inspected: {len(result.jars)}",
        f"- Estimated original Starsector: {result.estimated_starsector}",
        f"- Estimated original Java/bytecode: {result.estimated_java}",
        f"- Findings: {len(result.findings)} (SAFE {counts['SAFE']}, REVIEW {counts['REVIEW']}, MANUAL {counts['MANUAL']}, UNKNOWN {counts['UNKNOWN']})",
        "",
        "## Metadata",
        "",
    ]
    if result.metadata:
        for key in ("id", "name", "version", "gameVersion", "author"):
            if key in result.metadata:
                lines.append(f"- {key}: {result.metadata[key]}")
    else:
        lines.append("- No valid mod metadata parsed.")
    lines.extend(["", "## Findings", ""])
    if not result.findings:
        lines.append("No findings. This only means the V0.1 checks found no issues; it is not proof of runtime compatibility.")
    for finding in result.findings:
        location = f" — `{finding.file}`" if finding.file else ""
        lines.append(f"### [{finding.classification}] {finding.id}{location}")
        lines.append("")
        lines.append(f"- Severity: {finding.severity}")
        lines.append(f"- Confidence: {finding.confidence}")
        lines.append(f"- {finding.explanation}")
        if finding.evidence:
            lines.append(f"- Evidence: {', '.join(finding.evidence)}")
        lines.append("")
    lines.extend(["## Scope boundary", "", "This report is read-only analysis. It does not claim the mod compiles, loads, or behaves correctly.", ""])
    return "\n".join(lines)


def write_artifacts(result: ScanResult, output: Path) -> tuple[Path, Path]:
    output = output.expanduser().resolve()
    try:
        output.relative_to(result.input_path)
    except ValueError:
        pass
    else:
        raise ValueError("Output directory must not be inside the input mod directory; this preserves the original mod unchanged.")
    report_path = output / "MODERNIZATION_REPORT.md"
    manifest_path = output / "bridgeforge.compat.json"
    output.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_markdown(result), encoding="utf-8")
    manifest_path.write_text(json.dumps(result.manifest(), indent=2, sort_keys=True), encoding="utf-8")
    return report_path, manifest_path
