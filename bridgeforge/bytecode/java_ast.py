from __future__ import annotations

import base64
import hashlib
import subprocess
import tempfile
from pathlib import Path
from .helper_cache import helper_directory


def _java_tools() -> tuple[str, str]:
    from .java_toolchain import helper_java_tools  # local: java_toolchain imports scanner, which imports this chain
    return helper_java_tools()


class AstUnavailable(RuntimeError):
    """The selected runtime has no usable JDK compiler."""


def _run(*args, **kwargs) -> subprocess.CompletedProcess:
    """subprocess.run, with a JDK that cannot be started reported as AstUnavailable: with no JDK found `helper_java_tools`
    falls back to bare names, and the FileNotFoundError ended a whole scan (2026-11-15, ROADMAP-3 item 89)."""
    try:
        return subprocess.run(*args, **kwargs)
    except OSError as exc:
        raise AstUnavailable(f"Could not start the JDK ({exc}); no JDK was found in the rig, JAVA_HOME or PATH.") from exc


def utf16_offset_to_index(text: str, offset: int) -> int:
    units = 0
    for index, character in enumerate(text):
        if units == offset:
            return index
        units += 2 if ord(character) > 0xFFFF else 1
    if units == offset:
        return len(text)
    raise ValueError(f"Invalid UTF-16 source offset: {offset}")


def _helper_source() -> Path:
    return (Path(__file__).parent.parent / "java") / "BridgeforgeAst.java"


def _helper_directory() -> Path:
    source = _helper_source()
    digest = hashlib.sha256(b"release-17" + source.read_bytes()).hexdigest()[:16]
    return helper_directory("ast", digest, AstUnavailable)  # private per-user folder (93.51)


def _ensure_helper() -> Path:
    source = _helper_source()
    output = _helper_directory()
    marker = output / "bridgeforge" / "ast" / "BridgeforgeAst.class"
    if marker.is_file():
        return output
    output.mkdir(parents=True, exist_ok=True)
    completed = _run([_java_tools()[0], "--release", "17", "-d", str(output), str(source)], capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise AstUnavailable((completed.stderr or completed.stdout or "javac unavailable").strip())
    return output


def analyze_sources(root: Path) -> list[dict[str, object]]:
    root = root.resolve()
    sources = sorted(root.rglob("*.java"))
    if not sources:
        return []
    helper = _ensure_helper()
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".sources", delete=False) as handle:
        handle.write("\n".join(map(str, sources)))
        sources_file = Path(handle.name)
    try:
        completed = _run([_java_tools()[1], "-cp", str(helper), "bridgeforge.ast.BridgeforgeAst", "--sources-file", str(sources_file)], capture_output=True, text=True, check=False)
    finally:
        sources_file.unlink(missing_ok=True)
    if completed.returncode != 0:
        raise AstUnavailable((completed.stderr or completed.stdout or "Java AST helper failed").strip())
    facts: list[dict[str, object]] = []
    # One resolve per source file, not per fact: Sunrider's 86 files gave 12,003 facts, and resolving each fact's path
    # took 3.4 of the 4.2 profiled seconds here (96.5 P5).
    relative_of: dict[str, str] = {}
    for raw in completed.stdout.splitlines():
        kind, file_value, line, position, value = raw.split("\t", 4)
        fact_kind = {"I": "import", "M": "method_invocation", "D": "method_declaration", "C": "call_edge", "V": "variable_declaration"}.get(kind)
        if fact_kind is None:
            raise AstUnavailable(f"Java AST helper emitted an unknown fact type: {kind}")
        relative = relative_of.get(file_value)
        if relative is None:
            source_path = Path(base64.b64decode(file_value).decode("utf-8")).resolve()
            relative = relative_of[file_value] = str(source_path.relative_to(root)).replace("\\", "/")
        facts.append({"kind": fact_kind, "file": relative, "line": int(line), "position": int(position), "value": base64.b64decode(value).decode("utf-8")})
    return facts
