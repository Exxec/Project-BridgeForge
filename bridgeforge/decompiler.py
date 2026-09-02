from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def create_decompiler_review(input_path: Path, output: Path, adapter: Path, arguments: list[str]) -> dict:
    """Record a user-supplied decompiler plan without invoking it."""
    input_path, output, adapter = input_path.expanduser().resolve(), output.expanduser().resolve(), adapter.expanduser().resolve()
    if not input_path.is_file() or input_path.suffix.lower() not in {".jar", ".class"}:
        raise ValueError("Decompiler review requires an existing .jar or .class input.")
    if not adapter.is_file():
        raise ValueError("Decompiler adapter executable does not exist.")
    if input_path == output or input_path.is_relative_to(output):
        raise ValueError("Decompiler review output must not contain the input file.")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Decompiler review output must be new or empty.")
    if "{input}" not in arguments or "{output}" not in arguments:
        raise ValueError("Decompiler adapter arguments must include both {input} and {output} placeholders.")
    output.mkdir(parents=True, exist_ok=True)
    plan = {
        "schema_version": 1,
        "mode": "DECOMPILER_REVIEW_PLAN",
        "input_path": str(input_path),
        "input": {"name": input_path.name, "sha256": _sha256(input_path)},
        "adapter": str(adapter),
        "arguments": arguments,
        "decompiled_output": "decompiled",
        "execution_requires_explicit_flag": True,
        "limitations": [
            "Decompiler output is untrusted review evidence, not authoritative source.",
            "Bridgeforge will not compile, package, or replace code from decompiler output.",
        ],
    }
    (output / "decompiler-review-plan.json").write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return plan


def run_decompiler_review(output: Path, execute: bool = False) -> dict:
    output = output.expanduser().resolve()
    plan_path = output / "decompiler-review-plan.json"
    if not plan_path.is_file():
        raise ValueError("No decompiler review plan found.")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if not execute:
        return {"status": "NOT_EXECUTED", "reason": "Pass --execute to run the user-supplied decompiler adapter."}
    input_path, adapter = Path(plan["input_path"]), Path(plan["adapter"])
    if not input_path.is_file() or _sha256(input_path) != plan["input"]["sha256"]:
        return {"status": "STALE_INPUT", "reason": "Decompiler input changed after the review plan was recorded."}
    if not adapter.is_file():
        return {"status": "ADAPTER_UNAVAILABLE", "reason": "Decompiler adapter is no longer available."}
    decompiled = output / plan["decompiled_output"]
    if decompiled.exists() and any(decompiled.iterdir()):
        raise ValueError("Decompiler output directory is not empty; create a new review plan.")
    decompiled.mkdir(exist_ok=True)
    command = [str(adapter), *[argument.replace("{input}", str(input_path)).replace("{output}", str(decompiled)) for argument in plan["arguments"]]]
    completed = subprocess.run(command, cwd=output, capture_output=True, text=True, check=False)
    files = sorted(path.relative_to(decompiled).as_posix() for path in decompiled.rglob("*") if path.is_file())
    result = {
        "status": "PASS" if completed.returncode == 0 else "FAILED",
        "mode": "DECOMPILER_OUTPUT_UNTRUSTED_REVIEW_ONLY",
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "output_file_count": len(files),
        "output_files": files,
        "limitations": plan["limitations"],
    }
    (output / "decompiler-review-result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result
