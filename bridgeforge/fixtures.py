from __future__ import annotations

import json
from pathlib import Path


def fixture_root() -> Path:
    return Path(__file__).parent.parent / "tests" / "fixtures" / "compatibility"


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
