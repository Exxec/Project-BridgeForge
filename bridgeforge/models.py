from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TargetProfile:
    starsector: str = "0.98.x"
    java: int = 17


@dataclass
class Finding:
    id: str
    category: str
    severity: str
    classification: str
    confidence: str
    explanation: str
    file: str | None = None
    evidence: list[str] = field(default_factory=list)


@dataclass
class ScanResult:
    input_path: Path
    target: TargetProfile
    files: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    jars: list[dict[str, Any]] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    source_facts: list[dict[str, Any]] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    estimated_starsector: str = "UNKNOWN"
    estimated_java: str = "UNKNOWN"

    def add(self, **kwargs: Any) -> None:
        self.findings.append(Finding(**kwargs))

    def manifest(self) -> dict[str, Any]:
        return {
            "bridgeforge_version": "0.1.0",
            "input_mod": str(self.input_path),
            "target": asdict(self.target),
            "metadata": self.metadata,
            "estimated_original_environment": {
                "starsector": self.estimated_starsector,
                "java": self.estimated_java,
            },
            "inventory": self.files,
            "jars": self.jars,
            "imports": self.imports,
            "source_facts": self.source_facts,
            "findings": [asdict(finding) for finding in self.findings],
        }
