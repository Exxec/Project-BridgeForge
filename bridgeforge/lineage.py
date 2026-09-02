from __future__ import annotations

from pathlib import Path

from .evaluation import evaluate_releases
from .models import TargetProfile
from .scanner import scan_mod


def analyze_release_lineage(release_directories: list[Path], target: TargetProfile) -> dict:
    """Compare explicitly ordered releases without asserting maintainer intent."""
    directories = [path.expanduser().resolve() for path in release_directories]
    if len(directories) < 2 or any(not path.is_dir() or not (path / "mod_info.json").is_file() for path in directories):
        raise ValueError("Release lineage requires two or more existing mod roots with mod_info.json, in chronological order.")
    if len(set(directories)) != len(directories):
        raise ValueError("Release lineage directories must be distinct.")
    scans = [scan_mod(directory, target) for directory in directories]
    releases = [
        {
            "ordinal": index + 1,
            "release": directory.name,
            "declared_mod_id": scan.metadata.get("id"),
            "declared_starsector": scan.declared_starsector,
            "metadata_parse_mode": scan.metadata_parse_mode,
            "file_count": len(scan.files),
            "jar_count": len(scan.jars),
            "finding_count": len(scan.findings),
        }
        for index, (directory, scan) in enumerate(zip(directories, scans))
    ]
    transitions = []
    for index in range(len(directories) - 1):
        evaluation = evaluate_releases(directories[index], directories[index + 1], target)
        transitions.append({
            "from_ordinal": index + 1,
            "to_ordinal": index + 2,
            "assessment": evaluation["assessment"],
            "same_declared_mod_id": evaluation["comparability"]["same_declared_mod_id"],
            "content": {
                "identical_file_count": evaluation["content"]["identical_file_count"],
                "changed_file_count": evaluation["content"]["changed_file_count"],
                "before_only_file_count": evaluation["content"]["before_only_file_count"],
                "after_only_file_count": evaluation["content"]["after_only_file_count"],
            },
            "finding_delta": {
                "resolved_count": len(evaluation["finding_delta"]["resolved"]),
                "introduced_count": len(evaluation["finding_delta"]["introduced"]),
                "shared_count": evaluation["finding_delta"]["shared_count"],
            },
        })
    return {
        "schema_version": 1,
        "mode": "READ_ONLY_RELEASE_LINEAGE",
        "release_count": len(releases),
        "releases": releases,
        "transitions": transitions,
        "limitations": [
            "Input order is user-supplied and is not independently verified as chronological.",
            "File continuity and finding deltas do not establish maintainer intent, behavioral compatibility, or a safe migration mapping.",
        ],
    }
