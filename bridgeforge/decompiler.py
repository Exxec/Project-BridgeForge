from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from bridgeforge.file_hash import sha256_file as _sha256  # 96.5 A10

# A .bat or .cmd adapter runs under cmd.exe. Python quotes an argument only when it holds a space or tab, so in a path
# without one cmd.exe acts on & | < > ^; and it expands % and ! and ends quoting at " even inside quotes (ROADMAP-3 93.51;
# launch.command_line refuses the same for the game, 93.47).
_CMD_ACTS = re.compile(r'[&|<>^"%!\x00-\x1f\x7f]')


def _refuse_cmd_metacharacters(adapter: Path, command: list[str]) -> None:
    # Windows strips a trailing dot or space, so "x.bat." and "x.bat " still run under cmd.exe; the plan JSON is not resolved.
    if Path(str(adapter).rstrip(". ")).suffix.lower() not in {".bat", ".cmd"}:
        return
    for argument in command:  # the adapter's own path reaches cmd.exe too
        if _CMD_ACTS.search(argument):
            raise ValueError(f"refusing to run a .bat/.cmd adapter: an argument holds a character cmd.exe would act on: {argument!r}")



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
    _refuse_cmd_metacharacters(adapter, command)
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
