"""Governed recipe trials and the promotion gate (S2.3, docs/S2_RECIPE_GOVERNANCE.md).

A recipe is a fixer plus the conditions under which it may run. This module runs each recipe a case's findings ask for on a
private copy of that case, and records what actually happened: applied and verified, partly applied, refused, abstained or
failed. Training cases supply the positives. Holdout cases can only confirm or block, so they never select a recipe.

Read-only for its inputs: no input mod, automation policy or ruling is written. READY_FOR_OWNER_REVIEW is a report, not an
approval; an approval is still recorded by a person through `escalation rule`.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
from dataclasses import asdict
from pathlib import Path
from typing import Callable

from bridgeforge.automation import TIERS_PATH, tier_for
from bridgeforge.escalation.escalation_precedent import STANDING_THRESHOLD, invalid_ids, load_log, person_only
from bridgeforge.fixers import SUPPORTED_FINDINGS, FixerError, apply_fix, compute_fix
from bridgeforge.progress import Checkpoint, report as report_progress
from bridgeforge.revive import DEFAULT_TARGET, _fix_options, load_policy
from bridgeforge.safeio import atomic_write_json

SCHEMA = "bridgeforge.recipe-trial"
SCHEMA_VERSION = 1
SPLITS = ("training", "holdout")
VERIFIED, PARTIAL, REFUSED, ABSTAINED, FAILED = "VERIFIED", "PARTIAL", "REFUSED", "ABSTAINED", "FAILED"
# The same bar a standing ruling needs: three independent mods, not one convenient example.
MIN_TRAINING_POSITIVES = STANDING_THRESHOLD
ENGINE_PATHS = ("fixers", "scan", "recipe_trial.py", "revive.py", "automation_tiers.json")

Scan = Callable[[Path, Path | None, bool], list[dict]]


class RecipeTrialError(ValueError):
    """The cohort cannot be trialled as given."""


def read_cohort(path: Path) -> list[dict]:
    """Validated cases of a schema-1 cohort: `{"schema_version": 1, "cases": [{"name", "path", "split"}]}`."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RecipeTrialError(f"cannot read cohort {path}: {exc}") from exc
    if not isinstance(data, dict) or set(data) != {"schema_version", "cases"} or data["schema_version"] != 1 or not isinstance(data["cases"], list) or not data["cases"]:
        raise RecipeTrialError("expected a schema-1 cohort with a nonempty cases list")
    cases, names = [], set()
    for case in data["cases"]:
        if not isinstance(case, dict) or set(case) != {"name", "path", "split"} or not all(isinstance(case[k], str) and case[k] for k in case):
            raise RecipeTrialError(f"a case needs exactly name, path and split: {case!r}")
        if case["split"] not in SPLITS:
            raise RecipeTrialError(f"{case['name']}: split must be one of {', '.join(SPLITS)}")
        if case["name"] in names:
            raise RecipeTrialError(f"duplicate case name {case['name']}")
        names.add(case["name"])
        root = Path(case["path"])
        if not (root / "mod_info.json").is_file():
            raise RecipeTrialError(f"{case['name']}: {root} has no mod_info.json")
        cases.append({**case, "path": str(root.resolve())})
    return sorted(cases, key=lambda c: c["name"])


def tree_digest(root: Path) -> str:
    """Content identity of a physical mod tree. A link is a refusal: a copy of it would not be a private copy."""
    digest = hashlib.sha256()
    for folder, subdirs, files in os.walk(root):
        subdirs.sort()
        for name in [*subdirs, *files]:
            if Path(folder, name).is_symlink() or Path(folder, name).is_junction():
                raise RecipeTrialError(f"{Path(folder, name)} is a link; a recipe trial needs a physical tree")
        for name in sorted(files):
            path = Path(folder, name)
            digest.update(path.relative_to(root).as_posix().encode("utf-8") + b"\0")
            digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def engine_digest() -> str:
    """What the trial's meaning depends on: fixers, scanner, this gate and the tier table. A change restarts a checkpoint."""
    package = TIERS_PATH.parent
    digest = hashlib.sha256()
    for name in ENGINE_PATHS:
        target = package / name
        for path in sorted(target.rglob("*.py")) if target.is_dir() else [target]:
            digest.update(path.relative_to(package).as_posix().encode("utf-8") + b"\0" + path.read_bytes())
    return digest.hexdigest()


def scan_findings(working: Path, core: Path | None, compile_check: bool) -> list[dict]:
    from bridgeforge.scan.scanner import scan_mod

    return [asdict(f) for f in scan_mod(working, vanilla_core=core, compile_check=compile_check).findings]


def _keys(findings: list[dict]) -> set[tuple[str, str]]:
    return {(f["id"], str(f.get("file") or "")) for f in findings}


def _evidence(findings: list[dict]) -> list[tuple[str, list[str]]]:
    return sorted((str(f.get("file") or ""), sorted(str(e) for e in f.get("evidence") or [])) for f in findings)


def _private_copy(source: Path, base: Path, name: str) -> Path:
    """`<base>/<name>/working`: the folder above it stands in for the workspace, so a fixer's move out of working/ stays owned."""
    working = base / name / "working"
    shutil.copytree(source, working)
    return working


def _scrub(text: str, base: Path) -> str:
    return text.replace(str(base), "<copy>")


def try_recipe(source: Path, finding_id: str, group: list[dict], before_all: list[dict], base: Path, slot: str, *, core: Path | None,
               scan: Scan, target: str = DEFAULT_TARGET) -> dict:
    """One recipe on one fresh private copy. Never touches `source`."""
    row: dict = {"finding": finding_id, "outcome": FAILED, "reasons": [], "changed_files": [], "compile_checked": False,
                 "classifications": sorted({str(f.get("classification")) for f in group})}
    tier = tier_for(finding_id)
    if tier != "auto":
        return {**row, "outcome": ABSTAINED, "reasons": [f"tier '{tier}' is not an unattended recipe"]}
    if any(person_only(f) for f in group):
        return {**row, "outcome": ABSTAINED, "reasons": ["MANUAL/UNKNOWN, gameplay, balance and save decisions are person-only"]}
    working = _private_copy(source, base, slot)
    owned = working.parent.resolve()
    option_sets = _fix_options(finding_id, working, target, core, group)
    changed: set[str] = set()
    refusals: list[str] = []
    applied = 0
    try:
        for options in option_sets:
            try:
                plan = compute_fix(working, finding_id, options)
            except FixerError as exc:
                refusals.append(_scrub(str(exc), base))
                continue
            refusals += [_scrub(str(r), base) for r in options.get("partial_refusals") or []]
            outside = [c.path for c in plan.changes if not Path(c.path).resolve().is_relative_to(owned)]
            if outside:
                return {**row, "reasons": [f"plan writes outside the workspace: {_scrub(str(outside[0]), base)}"]}
            changed |= {Path(os.path.relpath(Path(c.path).resolve(), working.resolve())).as_posix() for c in plan.changes}
            for entry in apply_fix(plan):
                if entry.get("backup"):
                    Path(str(entry["backup"])).unlink()
            applied += 1
        row["changed_files"] = sorted(changed)
        if not applied:
            return {**row, "outcome": REFUSED, "reasons": sorted(set(refusals)) or ["no change was computed"]}
    except Exception as exc:  # a crashing recipe is the trial's result; the next recipe still gets its turn
        return {**row, "reasons": [_scrub(f"{type(exc).__name__}: {exc}", base)]}
    compile_check = core is not None and any(name.endswith(".java") for name in changed)
    row["compile_checked"] = compile_check
    before = scan(source, core, True) if compile_check else before_all
    after = scan(working, core, compile_check)
    # A real second pass rescans first; replaying the first scan's numbers would test the harness, not the fixer.
    remaining = [f for f in after if f["id"] == finding_id]
    for options in _fix_options(finding_id, working, target, core, remaining):
        try:
            again = compute_fix(working, finding_id, options)
        except FixerError:
            continue
        except Exception as exc:
            return {**row, "reasons": [_scrub(f"second run: {type(exc).__name__}: {exc}", base)]}
        return {**row, "reasons": [f"not idempotent: a second run still changes {len(again.changes)} file(s)"]}
    introduced = sorted(key for key in _keys(after) - _keys(before) if tier_for(key[0]) != "none")
    if introduced:
        return {**row, "reasons": [f"introduced {key[0]} in {key[1] or 'the mod'}" for key in introduced[:5]]}
    if not remaining and not refusals:
        return {**row, "outcome": VERIFIED}
    if remaining and _evidence(remaining) == _evidence([f for f in before if f["id"] == finding_id]):
        return {**row, "reasons": ["the finding is still reported, unchanged"]}
    return {**row, "outcome": PARTIAL, "reasons": [f"{len(remaining)} finding(s) remain, with changed evidence", *sorted(set(refusals))]}


def trial_case(case: dict, *, core: Path | None, scan: Scan = scan_findings) -> dict:
    """Every recipe the case's findings ask for, each on its own copy, and proof that the input did not change."""
    source = Path(case["path"])
    identity = tree_digest(source)
    result = {"name": case["name"], "split": case["split"], "input_digest": identity, "recipes": [], "errors": []}
    with tempfile.TemporaryDirectory(prefix="bf-recipe-", ignore_cleanup_errors=True) as tmp:
        base = Path(tmp).resolve()
        findings = scan(source, core, False)
        groups: dict[str, list[dict]] = {}
        for finding in findings:
            if finding["id"] in SUPPORTED_FINDINGS:
                groups.setdefault(finding["id"], []).append(finding)
        for index, finding_id in enumerate(sorted(groups)):
            result["recipes"].append(try_recipe(source, finding_id, groups[finding_id], findings, base, str(index), core=core, scan=scan))
    if tree_digest(source) != identity:
        result["errors"].append("the input changed during the trial")
    return result


def _revoked_fixers(queue: Path | None) -> set[str]:
    """Fixers whose newest approve-fixer ruling no longer stands."""
    if queue is None:
        return set()
    log = load_log(queue)
    bad = invalid_ids(log)
    latest = {r["finding"]: r for r in log if r.get("ruling") == "approve-fixer" and r.get("finding") and r.get("id")}
    return {finding for finding, ruling in latest.items() if ruling["id"] in bad}


def gate(cases: list[dict], approved: set[str], revoked: set[str]) -> list[dict]:
    """One row per recipe seen. Positives come from training only; a holdout confirms or blocks, and a failure anywhere blocks."""
    rows: dict[str, dict] = {}
    for case in cases:
        for recipe in case["recipes"]:
            row = rows.setdefault(recipe["finding"], {"finding": recipe["finding"], "approved": recipe["finding"] in approved,
                                                      "training": {}, "holdout": {}, "failures": []})
            row[case["split"]].setdefault(recipe["outcome"], []).append(case["name"])
            if recipe["outcome"] == FAILED:
                row["failures"].append({"case": case["name"], "split": case["split"], "reasons": recipe["reasons"]})
    out = []
    for finding in sorted(rows):
        row = rows[finding]
        training, holdout = row["training"].get(VERIFIED, []), row["holdout"].get(VERIFIED, [])
        if finding in revoked:
            state, why = "REVOKED", ["the approval ruling for this fixer was revoked or has expired"]
        elif row["failures"]:
            state, why = "BLOCKED", [f"{len(row['failures'])} failed trial(s)"]
        elif len(training) < MIN_TRAINING_POSITIVES or not holdout:
            state, why = "NEEDS_MORE_EVIDENCE", [f"{len(training)} verified training case(s), {MIN_TRAINING_POSITIVES} needed; {len(holdout)} verified holdout case(s), 1 needed"]
        else:
            state, why = "READY_FOR_OWNER_REVIEW", ["trial evidence only: behaviour is not proven and a person still records any approval"]
        out.append({**row, "state": state, "why": why})
    return out


def selection_digest(cases: list[dict]) -> str:
    """Identity of what was selected and how it ended; repeated runs on the same inputs must match."""
    body = [[c["name"], c["split"], c["input_digest"], [[r["finding"], r["outcome"], r["changed_files"]] for r in c["recipes"]]] for c in cases]
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def run_trial(cases: list[dict], *, core: Path | None, output: Path, policy_path: Path | None = None, queue: Path | None = None,
              scan: Scan = scan_findings, quiet: bool = False) -> dict:
    """Trial the cohort, checkpointing per case, and write the report to `output` (outside every input)."""
    output = Path(output).resolve()
    for case in cases:
        if output.is_relative_to(case["path"]):
            raise RecipeTrialError(f"the output {output} is inside the input {case['name']}")
    policy = load_policy(policy_path) if policy_path else {"approved_fixers": {}}
    engine = engine_digest()
    header = {"schema": SCHEMA, "engine": engine, "core": str(core), "cases": [[c["name"], c["split"], c["path"]] for c in cases]}
    finished = []
    with Checkpoint(output.with_name(output.name + ".partial.jsonl"), header) as checkpoint:
        for number, case in enumerate(cases, 1):
            saved = checkpoint.get(case["name"])
            if saved is not None and saved["input_digest"] == tree_digest(Path(case["path"])):
                finished.append(saved)
                if not quiet:
                    report_progress(number, len(cases), case["name"], f"{len(saved['recipes'])} recipe(s)", None)
                continue
            started = time.monotonic()
            result = trial_case(case, core=core, scan=scan)
            checkpoint.add(case["name"], result)
            finished.append(result)
            if not quiet:
                report_progress(number, len(cases), case["name"], f"{len(result['recipes'])} recipe(s)", time.monotonic() - started)
        report = {"schema": SCHEMA, "schema_version": SCHEMA_VERSION, "engine": engine, "core": str(core), "target": DEFAULT_TARGET,
                  "policy_digest": hashlib.sha256(json.dumps(policy, sort_keys=True).encode("utf-8")).hexdigest(),
                  "selection_digest": selection_digest(finished), "cases": finished,
                  "gate": gate(finished, set(policy["approved_fixers"]), _revoked_fixers(queue)),
                  "limits": ["Static trial on private copies: no game was launched and behaviour is not proven.",
                             "Inputs are named by the cohort; already-revived working copies show nothing to fix.",
                             "READY_FOR_OWNER_REVIEW approves nothing; no policy or ruling is written."]}
        atomic_write_json(output, report)
        checkpoint.finish()
    return report
