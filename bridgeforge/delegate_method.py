"""`bridgeforge delegate-method`: replace chosen method bodies with a call into a helper class (Exotica 2.1.1-RC4,
2026-10-26).

For a jar whose source is not available and whose decompiled form does not recompile (Kotlin: Vineflower writes .kt
that `rebuild-jar` cannot build), the fixed logic is written as a separately compiled Java helper class. Each chosen
method then becomes "load this and the arguments, invokestatic the helper, return", and every other method of the
class keeps its bytes. The result is checked by bytecode, not by trust: the changed methods must be exactly the
delegated ones, and no method may be added or removed. The output jar is a copy patched with the JDK `jar` tool
(CLAUDE.md: never rewrite a jar with another zip writer); the input jar is never written.

Spec file (JSON): {"schema_version": 1, "kind": "bridgeforge-delegate-methods", "delegations": [{"owner": "a/b/C",
"name": "get", "descriptor": "(La/B;)La/C;", "helper_owner": "a/b/Helper", "helper_name": "cGet", "reason": "..."}]}.
The helper's descriptor is the method's own, with the owner type first for an instance method.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .bytecode.bytecode import BytecodeUnavailable, _asm, inspect_bytecode
from .bytecode.bytecode_diff import changed_methods
from .bytecode.java_toolchain import find_jdk, helper_java_tools
from .zipsafe import MAX_CLASS_BYTES, read_limited

SPEC_KIND = "bridgeforge-delegate-methods"


@dataclass(frozen=True)
class Delegation:
    owner: str
    name: str
    descriptor: str
    helper_owner: str
    helper_name: str
    reason: str


def load_spec(path: Path) -> list[Delegation]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if payload.get("schema_version") != 1 or payload.get("kind") != SPEC_KIND:
            raise ValueError(f"expected schema_version 1 and kind {SPEC_KIND}")
        delegations = [Delegation(**entry) for entry in payload["delegations"]]
    except (OSError, KeyError, TypeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"Invalid delegation spec {path}: {exc}") from exc
    if not delegations:
        raise ValueError(f"Delegation spec {path} names no methods")
    for item in delegations:
        if not all((item.owner, item.name, item.descriptor, item.helper_owner, item.helper_name, item.reason)):
            raise ValueError(f"Delegation {item.owner}.{item.name} needs every field, including a reason")
        if item.name in {"<init>", "<clinit>"} or not item.descriptor.startswith("("):
            raise ValueError(f"Delegation {item.owner}.{item.name}{item.descriptor} cannot be replaced")
    keys = [(item.owner, item.name, item.descriptor) for item in delegations]
    if len(set(keys)) != len(keys):
        raise ValueError(f"Delegation spec {path} names a method twice")
    return delegations


def _delegate_helper() -> Path:
    source, asm = Path(__file__).with_name("java") / "BridgeforgeDelegateMethod.java", _asm()
    output = Path(tempfile.gettempdir()) / "bridgeforge-delegate" / hashlib.sha256(source.read_bytes() + asm.read_bytes()).hexdigest()[:16]
    if (output / "bridgeforge" / "bytecode" / "BridgeforgeDelegateMethod.class").is_file():
        return output
    output.mkdir(parents=True, exist_ok=True)
    done = subprocess.run([helper_java_tools()[0], "-cp", str(asm), "-d", str(output), str(source)], capture_output=True, text=True, check=False)
    if done.returncode:
        raise BytecodeUnavailable((done.stderr or done.stdout).strip())
    return output


def _rewrite(before: Path, after: Path, items: list[Delegation]) -> None:
    args = [str(before), str(after)]
    for item in items:
        args += [item.name, item.descriptor, item.helper_owner, item.helper_name]
    helper, asm = _delegate_helper(), _asm()
    done = subprocess.run([helper_java_tools()[1], "-cp", str(helper) + os.pathsep + str(asm), "bridgeforge.bytecode.BridgeforgeDelegateMethod", *args],
                          capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    if done.returncode:
        raise BytecodeUnavailable((done.stderr or done.stdout).strip())


def _verify(before: Path, after: Path, items: list[Delegation]) -> dict[str, object]:
    """Only the delegated methods may change; none may be added or removed."""
    old, new = inspect_bytecode([before])["classes"][0], inspect_bytecode([after])["classes"][0]
    verdict = changed_methods(old, new)
    changed = {(row["name"], row["descriptor"]) for row in verdict["changed"]}
    expected = {(item.name, item.descriptor) for item in items}
    ok = changed == expected and not verdict["added"] and not verdict["removed"]
    return {"ok": ok, "changed": sorted(f"{name}{desc}" for name, desc in changed), "expected": sorted(f"{name}{desc}" for name, desc in expected),
            "added": verdict["added"], "removed": verdict["removed"]}


def delegate_methods(jar: Path, spec: Path, helper_classes: Path, output: Path, jdk: Path | None = None) -> dict[str, object]:
    jar, output, helper_classes = Path(jar).resolve(), Path(output).resolve(), Path(helper_classes).resolve()
    if not jar.is_file():
        raise ValueError(f"{jar} is not a file")
    if output == jar or output.exists():
        raise ValueError(f"refusing to write {output}: it is the input or already exists")
    delegations = load_spec(spec)
    toolchain = find_jdk(jdk)
    if toolchain is None or not toolchain.jar.is_file():
        raise ValueError("no JDK with a jar tool found (pass --jdk)")
    helpers = sorted({item.helper_owner for item in delegations})
    missing = [owner for owner in helpers if not (helper_classes / f"{owner}.class").is_file()]
    if missing:
        raise ValueError(f"helper class(es) not compiled under {helper_classes}: {', '.join(missing)}")
    by_owner: dict[str, list[Delegation]] = {}
    for item in delegations:
        by_owner.setdefault(item.owner, []).append(item)
    classes: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="bf-delegate-") as scratch:
        work = Path(scratch)
        stage = work / "stage"
        with zipfile.ZipFile(jar) as archive:
            names = set(archive.namelist())
            for owner, items in sorted(by_owner.items()):
                entry = f"{owner}.class"
                if entry not in names:
                    raise ValueError(f"{entry} is not in {jar.name}")
                before = work / "before" / entry
                after = stage / entry
                before.parent.mkdir(parents=True, exist_ok=True)
                after.parent.mkdir(parents=True, exist_ok=True)
                before.write_bytes(read_limited(archive, entry, MAX_CLASS_BYTES))
                _rewrite(before, after, items)
                verdict = _verify(before, after, items)
                classes.append({"class": owner, **verdict})
        for owner in helpers:
            for compiled in helper_classes.glob(f"{owner}*.class"):
                if compiled.name == f"{Path(owner).name}.class" or compiled.name.startswith(f"{Path(owner).name}$"):
                    target = stage / Path(owner).parent / compiled.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(compiled, target)
        status = "PASS" if all(row["ok"] for row in classes) else "FAIL"
        if status == "PASS":
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(jar, output)
            done = subprocess.run([str(toolchain.jar), "uf", str(output), "-C", str(stage), "."], capture_output=True, text=True, check=False)
            if done.returncode:
                output.unlink(missing_ok=True)
                raise ValueError(f"jar tool failed: {(done.stderr or done.stdout).strip()}")
    return {"schema_version": 1, "mode": "DELEGATE_METHODS", "status": status, "input": str(jar), "output": str(output) if status == "PASS" else None,
            "helpers": helpers, "classes": classes, "reasons": {f"{item.owner}.{item.name}": item.reason for item in delegations}}
