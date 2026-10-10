"""Mass-test many mods across the Java/launcher environments (ROADMAP item 62).

`java-matrix run` boots one mod set through every variant. This walks a whole archive (`Done/`) one mod at a
time, each with its declared dependencies and nothing else, through the same variants, and reports which mods
behave differently by environment. The interesting result is not "mod X fails" (it fails everywhere: that is
the mod) but "mod X passes on vanilla Java 25 and fails with Fast Rendering or Java 28" (the environment).

Cost control, because a boot is minutes and the archive is hundreds of mods:
- `screen` boots only the baseline (direct, lowest Java) and the stress variant (Fast Rendering on the highest
  Java) first. Both pass -> SCREEN_PASS; only a mismatch or a failure boots the remaining variants.
- `skip_baseline_validated` does not re-boot the baseline for a mod whose ARCHIVE_NOTE says LIVE_VALIDATED
  (it already passed there), so only the new environments cost time.
- the ledger (java_matrix) reuses recorded all-passes, and a checkpoint resumes an interrupted run.

Needs the game install and a rig, so a live run is local-only (docs/LOCAL_HANDOFF.md).
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from . import java_matrix
from .progress import Checkpoint, report
from .scanner import _load_lenient_json_file

# Folders inside a Done/<Mod>/ archive that hold other copies of the mod, never the shipped one.
NON_SHIPPED = {"original", "alt-original-descriptions", "workspace", "checkpoints", "reports", "scratch", "working"}
STATUS_RE = re.compile(r"Revival report status:\s*\*\*(\w+)\*\*")


def _mod_info(folder: Path) -> dict | None:
    info = _load_lenient_json_file(folder / "mod_info.json")
    return info if isinstance(info, dict) and isinstance(info.get("id"), str) else None


def _dep_ids(info: dict) -> list[str]:
    deps = info.get("dependencies")
    return [d["id"] for d in deps if isinstance(d, dict) and isinstance(d.get("id"), str)] if isinstance(deps, list) else []


def collect_targets(done_dir: Path, only: list[str] | None = None) -> list[dict]:
    """One target per `Done/<Name>/` archive: the shipped mod folder, its id, version, status and dependencies."""
    targets = []
    for archive in sorted(p for p in Path(done_dir).iterdir() if p.is_dir()):
        if only and archive.name not in only:
            continue
        shipped = [c for c in sorted(archive.iterdir()) if c.is_dir() and c.name not in NON_SHIPPED and (c / "mod_info.json").is_file()]
        if not shipped:
            continue
        info = _mod_info(shipped[0])
        if info is None:
            continue
        note = archive / "ARCHIVE_NOTE.md"
        match = STATUS_RE.search(note.read_text(encoding="utf-8", errors="replace")) if note.is_file() else None
        version = info.get("version")
        if isinstance(version, dict):
            version = ".".join(str(version.get(k, "")) for k in ("major", "minor", "patch"))
        targets.append({"name": archive.name, "id": info["id"], "version": str(version or ""), "folder": str(shipped[0]), "status": match.group(1) if match else None, "dependencies": _dep_ids(info)})
    return targets


def index_providers(roots: list[Path]) -> dict[str, Path]:
    """id -> mod folder for every mod found directly under each root (first root wins)."""
    found: dict[str, Path] = {}
    for root in roots:
        root = Path(root)
        if not root.is_dir():
            continue
        for child in sorted(p for p in root.iterdir() if p.is_dir()):
            info = _mod_info(child) if (child / "mod_info.json").is_file() else None
            if info is not None:
                found.setdefault(info["id"], child)
    return found


def resolve_needs(target: dict, providers: dict[str, Path]) -> dict:
    """The target plus the transitive closure of its dependencies. `missing` lists ids no provider supplies."""
    folders: dict[str, Path] = {target["id"]: Path(target["folder"])}
    missing: list[str] = []
    queue = list(target["dependencies"])
    while queue:
        dep = queue.pop(0)
        if dep in folders or dep in missing:
            continue
        folder = providers.get(dep)
        if folder is None:
            missing.append(dep)
            continue
        folders[dep] = folder
        info = _mod_info(folder)
        queue += _dep_ids(info) if info else []
    return {"ids": sorted(folders), "folders": [folders[i] for i in sorted(folders)], "missing": sorted(missing)}


def pick_screen_variants(variants: list[dict]) -> tuple[dict, dict]:
    """(baseline, stress): direct launcher on the lowest Java, Fast Rendering on the highest Java."""
    direct = [v for v in variants if v["launcher"] == "direct"] or variants
    fr = [v for v in variants if v["launcher"] == "fr"] or variants
    return min(direct, key=lambda v: v["major"]), max(fr, key=lambda v: v["major"])


def classify(matrix: list[dict]) -> str:
    """ALL_PASS | ALL_FAIL | ENVIRONMENT_SENSITIVE | FLAKY, from per-variant pass rates (assumed passes count)."""
    rates = [m["pass_rate"] for m in matrix if m["pass_rate"] is not None]
    if not rates:
        return "NOT_RUN"
    if all(r == 1.0 for r in rates):
        return "ALL_PASS"
    if all(r == 0.0 for r in rates):
        return "ALL_FAIL"
    if any(0.0 < r < 1.0 for r in rates):
        return "FLAKY"
    return "ENVIRONMENT_SENSITIVE"


def _test_one(rig: Path, target: dict, needs: dict, variants: list[dict], screen: bool, skip_baseline_validated: bool, repeats: int, timeout: int, parallel: int, ledger: Path | None, skip_known: bool, keep_logs: Path) -> dict:
    run_kwargs = dict(repeats=repeats, timeout=timeout, quiet=True, parallel=parallel, ledger=ledger, skip_known=skip_known, mod_sources=needs["folders"], keep_logs=keep_logs / target["name"], log_name=f"mass-{target['id']}")
    baseline, stress = pick_screen_variants(variants)
    assumed: list[dict] = []
    first = variants
    if screen:
        first = [baseline] if baseline is stress else [baseline, stress]
    if skip_baseline_validated and target["status"] == "LIVE_VALIDATED" and baseline in first and len(first) > 1:
        first = [v for v in first if v is not baseline]
        assumed.append(baseline)
    result = java_matrix.run_java_matrix(rig, needs["ids"], first, **{**run_kwargs, "parallel": min(parallel, max(1, len(first)))}) if first else {"matrix": []}
    matrix = list(result["matrix"])
    stage = "screen" if screen else "full"
    if screen:
        screened_ok = bool(matrix) and all(m["pass_rate"] == 1.0 for m in matrix)
        rest = [v for v in variants if v not in first and v not in assumed]
        if not screened_ok and rest:
            more = java_matrix.run_java_matrix(rig, needs["ids"], rest, **{**run_kwargs, "parallel": min(parallel, len(rest))})
            matrix += more["matrix"]
            stage = "screen+expanded"
    for v in assumed:
        matrix.append({"id": v["id"], "major": v["major"], "launcher": v["launcher"], "java_version": v["java_version"], "runs": 0, "passed": 0, "pass_rate": 1.0, "statuses": ["ASSUMED_PASS"], "results": []})
    order = {v["id"]: i for i, v in enumerate(variants)}
    matrix.sort(key=lambda m: order.get(m["id"], 99))
    verdict = classify(matrix)
    if stage == "screen" and verdict == "ALL_PASS":
        verdict = "SCREEN_PASS"
    return {"name": target["name"], "id": target["id"], "version": target["version"], "stage": stage, "verdict": verdict, "matrix": matrix}


def run_mass(rig: Path, targets: list[dict], variants: list[dict], providers: dict[str, Path], output: Path, screen: bool = True, skip_baseline_validated: bool = True, repeats: int = 1, timeout: int = 240, parallel: int = 3, ledger: Path | None = None, skip_known: bool = False, quiet: bool = False, limit: int | None = None) -> dict:
    """Test each target in turn (parallel instances within a target); resumable; writes MASS_TEST.json/.md."""
    rig = Path(rig).expanduser().resolve()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    chosen = targets[:limit] if limit is not None else targets
    header = {"rig": str(rig), "mods": [t["name"] for t in chosen], "variants": [v["id"] for v in variants], "screen": screen, "repeats": repeats}
    rows: list[dict] = []
    started_all = time.monotonic()
    with Checkpoint(output / "mass-test.partial.jsonl", header) as ckpt:
        for index, target in enumerate(chosen, 1):
            saved = ckpt.get(target["name"])
            if saved is not None:
                rows.append(saved)
                if not quiet:
                    report(index, len(chosen), target["name"], saved["verdict"], None)
                continue
            needs = resolve_needs(target, providers)
            started = time.monotonic()
            if needs["missing"]:
                row = {"name": target["name"], "id": target["id"], "version": target["version"], "stage": "none", "verdict": "SKIPPED_MISSING_DEPENDENCY", "missing": needs["missing"], "matrix": []}
            else:
                row = _test_one(rig, target, needs, variants, screen, skip_baseline_validated, repeats, timeout, parallel, ledger, skip_known, output / "logs")
            ckpt.add(target["name"], row)
            rows.append(row)
            if not quiet:
                report(index, len(chosen), target["name"], row["verdict"], time.monotonic() - started)
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1
    result = {"schema_version": 1, "mode": "MASS_TEST", "date": time.strftime("%Y-%m-%d"), "variants": [v["id"] for v in variants], "screen": screen, "tested": len(rows), "counts": counts, "elapsed_seconds": round(time.monotonic() - started_all, 1), "mods": rows}
    (output / "MASS_TEST.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (output / "MASS_TEST.md").write_text(render_markdown(result), encoding="utf-8")
    (output / "mass-test.partial.jsonl").unlink(missing_ok=True)
    return result


def render_markdown(result: dict) -> str:
    lines = [f"# Mass test {result['date']}", "", f"Variants: {', '.join(result['variants'])}. Screening: {result['screen']}. {result['tested']} mod(s) in {result['elapsed_seconds']}s.", ""]
    lines += ["| Verdict | Mods |", "|---|---|"] + [f"| {k} | {v} |" for k, v in sorted(result["counts"].items())] + [""]
    sensitive = [m for m in result["mods"] if m["verdict"] in ("ENVIRONMENT_SENSITIVE", "FLAKY")]
    lines += ["## Environment-sensitive (pass in some variants, fail in others)", ""]
    if not sensitive:
        lines.append("None.")
    for m in sensitive:
        cells = ", ".join(f"{x['id']}={x['pass_rate']}" for x in m["matrix"])
        lines.append(f"- **{m['name']}** {m['version']}: {m['verdict']} ({cells})")
    lines += ["", "## Failing everywhere (the mod itself)", ""]
    failing = [m for m in result["mods"] if m["verdict"] == "ALL_FAIL"]
    lines += [f"- {m['name']} {m['version']}" for m in failing] or ["None."]
    missing = [m for m in result["mods"] if m["verdict"] == "SKIPPED_MISSING_DEPENDENCY"]
    lines += ["", "## Not tested: dependency not found", ""]
    lines += [f"- {m['name']}: {', '.join(m['missing'])}" for m in missing] or ["None."]
    return "\n".join(lines) + "\n"
