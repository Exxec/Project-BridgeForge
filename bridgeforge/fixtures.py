from __future__ import annotations

import json
from pathlib import Path


def fixture_root() -> Path:
    return Path(__file__).parent.parent / "tests" / "fixtures" / "compatibility"


def corpus_baseline_root() -> Path:
    return Path(__file__).parent.parent / "tests" / "fixtures" / "corpus-baselines"


def discover_compatibility_fixtures(root: Path | None = None) -> list[dict[str, object]]:
    root = root or fixture_root()
    cases = []
    for expected in sorted(root.glob("*/expected.json")):
        case_root = expected.parent
        data = json.loads(expected.read_text(encoding="utf-8"))
        if not (case_root / "mod_info.json").is_file():
            raise ValueError(f"Fixture missing mod_info.json: {case_root}")
        cases.append({"name": case_root.name, "path": str(case_root), "expected": data})
    return cases


def discover_corpus_baselines(root: Path | None = None) -> list[dict[str, object]]:
    root = root or corpus_baseline_root()
    baselines = []
    for path in sorted(root.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema_version") != 1 or not data.get("name") or not isinstance(data.get("expected_findings"), list):
            raise ValueError(f"Invalid corpus baseline: {path}")
        baselines.append(data)
    return baselines
