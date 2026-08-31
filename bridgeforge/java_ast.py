from __future__ import annotations

import base64
import hashlib
import subprocess
import tempfile
from pathlib import Path


class AstUnavailable(RuntimeError):
    """The selected runtime has no usable JDK compiler."""


def _helper_source() -> Path:
    return Path(__file__).with_name("java") / "BridgeforgeAst.java"


def _helper_directory() -> Path:
    source = _helper_source()
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / "bridgeforge-ast" / digest


def _ensure_helper() -> Path:
    source = _helper_source()
    output = _helper_directory()
    marker = output / "bridgeforge" / "ast" / "BridgeforgeAst.class"
    if marker.is_file():
        return output
    output.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(["javac", "-d", str(output), str(source)], capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise AstUnavailable((completed.stderr or completed.stdout or "javac unavailable").strip())
    return output


def analyze_sources(root: Path) -> list[dict[str, object]]:
    root = root.resolve()
    sources = sorted(root.rglob("*.java"))
    if not sources:
        return []
    helper = _ensure_helper()
    completed = subprocess.run(["java", "-cp", str(helper), "bridgeforge.ast.BridgeforgeAst", *map(str, sources)], capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise AstUnavailable((completed.stderr or completed.stdout or "Java AST helper failed").strip())
    facts: list[dict[str, object]] = []
    for raw in completed.stdout.splitlines():
        kind, file_value, line, position, value = raw.split("\t", 4)
        source_path = Path(base64.b64decode(file_value).decode("utf-8")).resolve()
        facts.append({"kind": "import" if kind == "I" else "method_invocation", "file": str(source_path.relative_to(root)).replace("\\", "/"), "line": int(line), "position": int(position), "value": base64.b64decode(value).decode("utf-8")})
    return facts
