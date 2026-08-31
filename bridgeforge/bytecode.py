from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

ASM_SHA256 = "8cadd43ac5eb6d09de05faecca38b917a040bb9139c7edeb4cc81c740b713281"


class BytecodeUnavailable(RuntimeError):
    """The inspection-only ASM helper could not be compiled or run."""


def _source() -> Path:
    return Path(__file__).with_name("java") / "BridgeforgeBytecode.java"


def _asm() -> Path:
    jar = Path(__file__).with_name("java-tools") / "bytecode" / "lib" / "asm-9.7.1.jar"
    if not jar.is_file() or hashlib.sha256(jar.read_bytes()).hexdigest() != ASM_SHA256:
        raise BytecodeUnavailable("Pinned ASM dependency is missing or has an unexpected SHA-256.")
    return jar


def _helper() -> Path:
    source, asm = _source(), _asm()
    output = Path(tempfile.gettempdir()) / "bridgeforge-bytecode" / hashlib.sha256(source.read_bytes() + asm.read_bytes()).hexdigest()[:16]
    marker = output / "bridgeforge" / "bytecode" / "BridgeforgeBytecode.class"
    if marker.is_file(): return output
    output.mkdir(parents=True, exist_ok=True)
    done = subprocess.run(["javac", "-cp", str(asm), "-d", str(output), str(source)], capture_output=True, text=True, check=False)
    if done.returncode: raise BytecodeUnavailable((done.stderr or done.stdout).strip())
    return output


def _rewrite_helper() -> Path:
    source, asm = Path(__file__).with_name("java") / "BridgeforgeBytecodeRewrite.java", _asm()
    output = Path(tempfile.gettempdir()) / "bridgeforge-bytecode-rewrite" / hashlib.sha256(source.read_bytes() + asm.read_bytes()).hexdigest()[:16]
    marker = output / "bridgeforge" / "bytecode" / "BridgeforgeBytecodeRewrite.class"
    if marker.is_file(): return output
    output.mkdir(parents=True, exist_ok=True)
    done = subprocess.run(["javac", "-cp", str(asm), "-d", str(output), str(source)], capture_output=True, text=True, check=False)
    if done.returncode: raise BytecodeUnavailable((done.stderr or done.stdout).strip())
    return output


def inspect_bytecode(inputs: list[Path]) -> dict[str, object]:
    """Return symbolic class-file inventory; this function never writes inputs."""
    selected = [path.expanduser().resolve() for path in inputs]
    if not selected or any(not path.is_file() or path.suffix.lower() not in {".class", ".jar"} for path in selected):
        raise ValueError("Bytecode inspection requires one or more existing .class or .jar files.")
    helper, asm = _helper(), _asm()
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".inputs", delete=False) as handle:
        handle.write("\n".join(map(str, selected))); inputs_file = Path(handle.name)
    try:
        done = subprocess.run(["java", "-cp", str(helper) + __import__("os").pathsep + str(asm), "bridgeforge.bytecode.BridgeforgeBytecode", "--inputs-file", str(inputs_file)], capture_output=True, text=True, check=False)
    finally: inputs_file.unlink(missing_ok=True)
    if done.returncode: raise BytecodeUnavailable((done.stderr or done.stdout).strip())
    result = json.loads(done.stdout)
    if result.get("schema_version") != 1 or result.get("mode") != "INSPECTION_ONLY": raise BytecodeUnavailable("Bytecode helper returned an unsupported protocol response.")
    return result


def rewrite_class(input_path: Path, output_path: Path, rule: object) -> int:
    """Apply one exact same-descriptor rule to a .class copy; never changes input."""
    source, output = input_path.expanduser().resolve(), output_path.expanduser().resolve()
    if source.suffix.lower() != ".class" or not source.is_file(): raise ValueError("Bytecode rewrite currently requires an existing .class input.")
    action = getattr(rule, "action"); name = getattr(rule, "name") or ""; descriptor = getattr(rule, "descriptor") or ""; opcode = getattr(rule, "opcode")
    if action == "remap-class-reference":
        raise ValueError("Class remapping requires an explicit opcode and is not yet application-enabled.")
    if action not in {"remap-method-reference", "remap-field-reference"} or not name or not descriptor or opcode is None or getattr(rule, "replacement_descriptor") != descriptor:
        raise ValueError("Only exact same-descriptor method/field remaps are application-enabled.")
    helper, asm = _rewrite_helper(), _asm(); output.parent.mkdir(parents=True, exist_ok=True)
    done = subprocess.run(["java", "-cp", str(helper) + __import__("os").pathsep + str(asm), "bridgeforge.bytecode.BridgeforgeBytecodeRewrite", str(source), str(output), action, getattr(rule, "owner"), name, descriptor, str(opcode), getattr(rule, "replacement_owner"), getattr(rule, "replacement_name"), getattr(rule, "replacement_descriptor"), str(getattr(rule, "expected_matches"))], capture_output=True, text=True, check=False)
    if done.returncode: raise BytecodeUnavailable((done.stderr or done.stdout).strip())
    return int(done.stdout.strip())
