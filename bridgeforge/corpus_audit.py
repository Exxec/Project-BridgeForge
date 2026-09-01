from __future__ import annotations

from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path

from .models import TargetProfile
from .scanner import scan_mod


def _source_layout(inventory: list[dict], finding_counts: Counter) -> dict:
    java_paths = [Path(item["path"]) for item in inventory if Path(item["path"]).suffix.lower() == ".java"]
    disabled = [path for path in java_paths if "disabled_files" in path.parts]
    archived = [path for path in java_paths if "jar" in path.parts or "jars" in path.parts]
    return {
        "java_file_count": len(java_paths),
        "active_java_file_count": len([path for path in java_paths if path not in disabled and path not in archived]),
        "disabled_java_file_count": len(disabled),
        "bundled_or_archive_java_file_count": len(archived),
        "duplicate_source_layout_findings": finding_counts["duplicate-source-layout"],
    }


def audit_directories(mod_directories: list[Path], target: TargetProfile, continue_on_error: bool = False) -> dict:
    """Create a deterministic, read-only compatibility summary for explicit mod roots."""
    rows = []
    for directory in sorted((path.expanduser().resolve() for path in mod_directories), key=lambda path: path.name.casefold()):
        if not directory.is_dir():
            if continue_on_error:
                rows.append({"mod": directory.name, "audit_status": "UNAVAILABLE", "error": "Input directory does not exist."})
                continue
            raise ValueError(f"Corpus mod directory does not exist: {directory}")
        try:
            result = scan_mod(directory, target)
        except (OSError, ValueError) as exc:
            if not continue_on_error:
                raise
            rows.append({"mod": directory.name, "audit_status": "UNAVAILABLE", "error": str(exc)})
            continue
        finding_counts = Counter(finding.id for finding in result.findings)
        rows.append({
            "mod": directory.name,
            "metadata_parse_mode": result.metadata_parse_mode,
            "declared_starsector": result.declared_starsector,
            "estimated_starsector": result.estimated_starsector,
            "file_count": len(result.files),
            "jar_count": len(result.jars),
            "finding_counts": dict(sorted(finding_counts.items())),
            "source_layout": _source_layout(result.files, finding_counts),
            "library_usage": result.library_usage,
        })
    aggregate = Counter()
    for row in rows:
        aggregate.update(row.get("finding_counts", {}))
    return {
        "schema_version": 1,
        "mode": "READ_ONLY_CORPUS_AUDIT",
        "target": asdict(target),
        "mod_count": len(rows),
        "unavailable_mod_count": sum(row.get("audit_status") == "UNAVAILABLE" for row in rows),
        "finding_counts": dict(sorted(aggregate.items())),
        "mods": rows,
    }


def write_corpus_audit(report: dict, output: Path, mod_directories: list[Path]) -> Path:
    output = output.expanduser().resolve()
    for directory in mod_directories:
        try:
            output.relative_to(directory.expanduser().resolve())
        except ValueError:
            continue
        raise ValueError("Corpus report output must not be inside an input mod directory.")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output
