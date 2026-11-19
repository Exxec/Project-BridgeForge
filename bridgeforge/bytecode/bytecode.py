from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path

ASM_SHA256 = "8cadd43ac5eb6d09de05faecca38b917a040bb9139c7edeb4cc81c740b713281"


# Helpers are compiled with --release 17 and cached by that: a helper built by the rig's Java 25 was reused under the game's
# Java 17 and failed with UnsupportedClassVersionError (2026-11-15, ROADMAP-3 item 89).
def _java_tools() -> tuple[str, str]:
    from .java_toolchain import helper_java_tools  # local: java_toolchain imports scanner, which imports this chain
    return helper_java_tools()


class BytecodeUnavailable(RuntimeError):
    """The inspection-only ASM helper could not be compiled or run."""


def _run(*args, **kwargs) -> subprocess.CompletedProcess:
    """subprocess.run, with a JDK that cannot be started reported as BytecodeUnavailable (see java_ast._run)."""
    try:
        return subprocess.run(*args, **kwargs)
    except OSError as exc:
        raise BytecodeUnavailable(f"Could not start the JDK ({exc}); no JDK was found in the rig, JAVA_HOME or PATH.") from exc


def _source() -> Path:
    return (Path(__file__).parent.parent / "java") / "BridgeforgeBytecode.java"


def _asm() -> Path:
    jar = (Path(__file__).parent.parent / "java-tools") / "bytecode" / "lib" / "asm-9.7.1.jar"
    if not jar.is_file() or hashlib.sha256(jar.read_bytes()).hexdigest() != ASM_SHA256:
        raise BytecodeUnavailable("Pinned ASM dependency is missing or has an unexpected SHA-256.")
    return jar


def _helper() -> Path:
    source, asm = _source(), _asm()
    output = Path(tempfile.gettempdir()) / "bridgeforge-bytecode" / hashlib.sha256(b"release-17" + source.read_bytes() + asm.read_bytes()).hexdigest()[:16]
    marker = output / "bridgeforge" / "bytecode" / "BridgeforgeBytecode.class"
    if marker.is_file(): return output
    output.mkdir(parents=True, exist_ok=True)
    done = _run([_java_tools()[0], "--release", "17", "-cp", str(asm), "-d", str(output), str(source)], capture_output=True, text=True, check=False)
    if done.returncode: raise BytecodeUnavailable((done.stderr or done.stdout).strip())
    return output


def _rewrite_helper() -> Path:
    source, asm = (Path(__file__).parent.parent / "java") / "BridgeforgeBytecodeRewrite.java", _asm()
    output = Path(tempfile.gettempdir()) / "bridgeforge-bytecode-rewrite" / hashlib.sha256(b"release-17" + source.read_bytes() + asm.read_bytes()).hexdigest()[:16]
    marker = output / "bridgeforge" / "bytecode" / "BridgeforgeBytecodeRewrite.class"
    if marker.is_file(): return output
    output.mkdir(parents=True, exist_ok=True)
    done = _run([_java_tools()[0], "--release", "17", "-cp", str(asm), "-d", str(output), str(source)], capture_output=True, text=True, check=False)
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
        done = _run([_java_tools()[1], "-cp", str(helper) + __import__("os").pathsep + str(asm), "bridgeforge.bytecode.BridgeforgeBytecode", "--inputs-file", str(inputs_file)], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    finally: inputs_file.unlink(missing_ok=True)
    if done.returncode: raise BytecodeUnavailable((done.stderr or done.stdout).strip())
    result = json.loads(done.stdout)
    if result.get("schema_version") != 1 or result.get("mode") != "INSPECTION_ONLY": raise BytecodeUnavailable("Bytecode helper returned an unsupported protocol response.")
    return result


def append_constant_argument(input_path: Path, output_path: Path, owner: str, name: str, descriptor: str, opcode: int,
                             new_descriptor: str, constant: str, expected: int) -> int:
    """Push `null` or `false` before each matching call and give it `new_descriptor` (one trailing parameter more), into a
    copy of a .class file; the Java helper checks the shape. `getter:NAME:()I:K` instead appends the receiver's NAME() + K
    to a no-argument instance call (95.14). Returns the number of calls rewritten (must be `expected`)."""
    source, output = input_path.expanduser().resolve(), output_path.expanduser().resolve()
    if source.suffix.lower() != ".class" or not source.is_file() or source == output:
        raise ValueError("append_constant_argument needs an existing .class input and a different output path.")
    if constant not in {"null", "false"} and not re.fullmatch(r"getter:[A-Za-z_$][\w$]*:\(\)I:-?\d{1,3}", constant):
        raise ValueError("The appended value is null, false or getter:NAME:()I:K.")
    helper, asm = _rewrite_helper(), _asm()
    output.parent.mkdir(parents=True, exist_ok=True)
    done = _run([_java_tools()[1], "-cp", str(helper) + __import__("os").pathsep + str(asm), "bridgeforge.bytecode.BridgeforgeBytecodeRewrite",
                 str(source), str(output), "append-constant-argument", owner, name, descriptor, str(opcode), owner, constant,
                 new_descriptor, str(expected)], capture_output=True, text=True, check=False)
    if done.returncode: raise BytecodeUnavailable((done.stderr or done.stdout).strip())
    return int(done.stdout.strip())


def rewrite_class(input_path: Path, output_path: Path, rule: object) -> int:
    """Apply one exact same-descriptor rule to a .class copy; never changes input."""
    source, output = input_path.expanduser().resolve(), output_path.expanduser().resolve()
    if source.suffix.lower() != ".class" or not source.is_file(): raise ValueError("Bytecode rewrite currently requires an existing .class input.")
    if source == output: raise ValueError("Bytecode output must differ from input; in-place replacement is forbidden.")
    action = getattr(rule, "action"); name = getattr(rule, "name") or ""; descriptor = getattr(rule, "descriptor") or ""; opcode = getattr(rule, "opcode")
    if action == "remap-class-reference":
        if opcode is None or name or descriptor or getattr(rule, "replacement_name") or getattr(rule, "replacement_descriptor"):
            raise ValueError("Class remaps require only an exact type opcode.")
    elif action not in {"remap-method-reference", "remap-field-reference"} or not name or not descriptor or opcode is None or getattr(rule, "replacement_descriptor") != descriptor:
        raise ValueError("Only exact same-descriptor method/field remaps are application-enabled.")
    helper, asm = _rewrite_helper(), _asm(); output.parent.mkdir(parents=True, exist_ok=True)
    done = _run([_java_tools()[1], "-cp", str(helper) + __import__("os").pathsep + str(asm), "bridgeforge.bytecode.BridgeforgeBytecodeRewrite", str(source), str(output), action, getattr(rule, "owner"), name, descriptor, str(opcode), getattr(rule, "replacement_owner"), getattr(rule, "replacement_name"), getattr(rule, "replacement_descriptor"), str(getattr(rule, "expected_matches"))], capture_output=True, text=True, check=False)
    if done.returncode: raise BytecodeUnavailable((done.stderr or done.stdout).strip())
    return int(done.stdout.strip())
