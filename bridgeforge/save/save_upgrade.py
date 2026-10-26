"""`save-upgrade`: reusable save-upgrade scenarios, offline planner and evidence evaluator (ROADMAP item 75 R6).

A save-upgrade scenario asks: does the NEW candidate of a mod load a campaign saved with the OLD candidate, migrate it correctly,
save it to a separate slot, reload that result, and do nothing the second time round? This module holds only the pure parts:

* `plan_upgrade` turns a scenario spec (exact old/new candidate manifests, a copied rig-save identity, one named case) into the ordered
  stages a live run must observe and what each must show. It refuses an inconsistent spec.
* `evaluate_upgrade` reads the evidence a run produced and returns one verdict. It refuses missing or out-of-order stages, broken save
  lineage, a candidate other than the new manifest, a touched original save and unmet case expectations. Evidence that comes from a
  proxy test (a plain-Java harness that never writes or reads a real campaign save) is labelled PROXY_ONLY and never VERIFIED.

It launches nothing and edits no save: only the in-game API changes state, in a rig, and original saves stay read-only. It is not a
save editor. Verdicts: REFUSED (structurally unusable), FAIL, PROXY_ONLY, LIVE_PENDING (no evidence given), VERIFIED.

Run identity (R1 dependency): R1 defines the run manifest. Until it lands this module takes only an opaque `run_identity` dict with
`run_id` and `shipped_hash`, checked against the new candidate's hash; once R1 exists, pass the id and hash it records.
Zorg bf.10's local `scratch/bf10/ZorgColonyRepairTest.java` is the logic example for the cases; it is a proxy test, not serialization.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from ..safeio import atomic_write_json
from ..scenarios import _condition_holds

SCHEMA_VERSION = 1
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PROXY, SERIALIZATION = "proxy", "serialization"

# stage -> (kind of evidence a VERIFIED verdict needs, one line on what it shows)
STAGES: dict[str, tuple[str, str]] = {
    "preconditions": (PROXY, "the copied save matches the recorded identity and the original is untouched"),
    "load_old_with_new": (SERIALIZATION, "the OLD campaign loads with the NEW candidate"),
    "migration_check": (SERIALIZATION, "the migration result matches the case"),
    "save_slot": (SERIALIZATION, "the migrated campaign saves to a separate rig slot"),
    "reload_saved": (SERIALIZATION, "that saved slot restarts and loads"),
    "repeat_idempotence": (SERIALIZATION, "a second load and save changes nothing"),
}
STAGE_ORDER = tuple(STAGES)
ALWAYS_REQUIRED = {"unrelated_state_unchanged": True}

# case -> what migration_check must observe (scenarios._condition_holds conditions)
CASES: dict[str, dict[str, object]] = {
    "missing-colonies": {"migration_applied": True, "colonies_created": {"min": 1}, "market_trade_visible": True, "duplicates_created": 0},
    "existing-colonies": {"migration_applied": False, "existing_colonies_preserved": True, "duplicates_created": 0},
    "captured-ownership": {"ownership_preserved": True, "ownership_reclaimed": False},
    "player-ownership": {"ownership_preserved": True, "ownership_reclaimed": False},
    "removed-colonies": {"removed_not_recreated": True},
    "missing-registration": {"migration_applied": True, "registration_restored": True, "market_trade_visible": True},
    "id-conflict": {"conflicting_entity_untouched": True, "duplicates_created": 0},
    "healthy-control": {"migration_applied": False, "state_changed": False},
}


class UpgradeError(ValueError):
    """A scenario spec or evidence file cannot be used."""


def _check_hash(value: object, what: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.match(value):
        raise UpgradeError(f"{what} must be a lowercase sha256 hex string")
    return value


def _check_candidate(spec: object, label: str) -> dict:
    if not isinstance(spec, dict):
        raise UpgradeError(f"{label}_candidate is missing")
    if not isinstance(spec.get("version"), str) or not spec["version"]:
        raise UpgradeError(f"{label}_candidate.version is missing")
    _check_hash(spec.get("shipped_hash"), f"{label}_candidate.shipped_hash")
    files = spec.get("files")
    if not isinstance(files, dict) or not files:
        raise UpgradeError(f"{label}_candidate.files must list every shipped file with its sha256 (an exact manifest)")
    for relative, digest in files.items():
        _check_hash(digest, f"{label}_candidate.files[{relative!r}]")
        if relative.startswith(("/", "\\")) or ".." in Path(relative).parts:
            raise UpgradeError(f"{label}_candidate.files has an unsafe path {relative!r}")
    return spec


def validate_spec(spec: object) -> dict:
    """Return the spec if it is usable, else raise UpgradeError naming the first problem."""
    if not isinstance(spec, dict) or spec.get("schema_version") != SCHEMA_VERSION:
        raise UpgradeError(f"not a save-upgrade scenario (schema_version {SCHEMA_VERSION})")
    if spec.get("case") not in CASES:
        raise UpgradeError(f"unknown case {spec.get('case')!r}; known: {sorted(CASES)}")
    if not isinstance(spec.get("subject_mod"), str) or not spec["subject_mod"]:
        raise UpgradeError("subject_mod is missing")
    old, new = _check_candidate(spec.get("old_candidate"), "old"), _check_candidate(spec.get("new_candidate"), "new")
    if old["shipped_hash"] == new["shipped_hash"]:
        raise UpgradeError("old and new candidates are identical: nothing to upgrade")
    identity = spec.get("save_identity")
    if not isinstance(identity, dict):
        raise UpgradeError("save_identity is missing")
    _check_hash(identity.get("original_hash"), "save_identity.original_hash")
    _check_hash(identity.get("copy_hash"), "save_identity.copy_hash")
    if identity["original_hash"] != identity["copy_hash"]:
        raise UpgradeError("save_identity: the rig copy does not match the original's hash (it must be a byte-exact copy)")
    for key in ("rig_slot", "result_slot"):
        if not isinstance(identity.get(key), str) or not identity[key]:
            raise UpgradeError(f"save_identity.{key} is missing")
    if identity["rig_slot"] == identity["result_slot"]:
        raise UpgradeError("result_slot must differ from rig_slot: the migrated save goes to a separate slot")
    return spec


def plan_upgrade(spec: object) -> dict:
    """The ordered stages a live run must produce evidence for. Pure: reads nothing, writes nothing."""
    spec = validate_spec(spec)
    required = {**ALWAYS_REQUIRED, **CASES[spec["case"]]}
    stages = [{"seq": number, "stage": name, "evidence_kind": kind, "shows": shows,
               **({"required_observations": required} if name == "migration_check" else {})}
              for number, (name, (kind, shows)) in enumerate(STAGES.items(), 1)]
    return {"schema_version": SCHEMA_VERSION, "mode": "SAVE_UPGRADE_PLAN", "case": spec["case"], "subject_mod": spec["subject_mod"],
            "old_version": spec["old_candidate"]["version"], "new_version": spec["new_candidate"]["version"],
            "new_candidate_hash": spec["new_candidate"]["shipped_hash"], "save_copy_hash": spec["save_identity"]["copy_hash"],
            "stages": stages, "status": "LIVE_PENDING",
            "note": "Run in a rig; only the in-game API changes state. Evidence must name each stage in order, with the save hashes it read and wrote."}


def _stage_problems(stage: dict, spec: dict, previous_out: str | None) -> list[str]:
    name, identity = stage["stage"], spec["save_identity"]
    new_hash, problems = spec["new_candidate"]["shipped_hash"], []
    if name != "preconditions" and stage.get("candidate_hash") != new_hash:
        problems.append(f"{name}: ran candidate {stage.get('candidate_hash')!r}, not the new candidate {new_hash}")
    if name == "preconditions":
        if stage.get("original_hash_after") != identity["original_hash"]:
            problems.append("preconditions: the original save's hash changed or is not recorded")
        if stage.get("save_out_hash") != identity["copy_hash"]:
            problems.append("preconditions: the rig copy does not match the recorded identity")
    elif stage.get("save_in_hash") != previous_out:
        problems.append(f"{name}: read save {stage.get('save_in_hash')!r}, but the previous stage left {previous_out!r} (broken lineage)")
    if name == "save_slot" and stage.get("slot") != identity["result_slot"]:
        problems.append(f"save_slot: wrote slot {stage.get('slot')!r}, expected the separate slot {identity['result_slot']!r}")
    if name in ("save_slot", "repeat_idempotence"):
        out = stage.get("save_out_hash")
        if not isinstance(out, str) or not SHA256_RE.match(out):
            problems.append(f"{name}: the saved result has no sha256")
        elif out in (identity["original_hash"], identity["copy_hash"]):
            problems.append(f"{name}: the saved result is byte-identical to the original save, so it was not written by this run")
    if name == "repeat_idempotence" and stage.get("state_hash_before") != stage.get("state_hash_after"):
        problems.append("repeat_idempotence: the second pass changed the campaign state")
    return problems


def _observation_failures(stage: dict, spec: dict, repeat: dict | None) -> list[str]:
    observed = stage.get("observations")
    if not isinstance(observed, dict):
        return ["migration_check: no observations recorded"]
    required = {**ALWAYS_REQUIRED, **CASES[spec["case"]]}
    failures = [f"migration_check: {key} expected {condition!r}, observed {observed.get(key)!r}"
                for key, condition in required.items() if key not in observed or not _condition_holds(observed[key], condition)]
    if repeat and (repeat.get("observations") or {}).get("migration_applied") not in (False, None):
        failures.append("repeat_idempotence: the migration applied again on the second pass")
    return failures


def fingerprint_judgement(spec: dict, evidence: object, run_id: object) -> dict:
    """Judge probe save-reload fingerprint records (`evidence["fingerprint_records"]`, each a `run-manifest evaluate` result of a reload
    run, optionally with `shipped_hash`) for the `reload_saved` stage. A record COUNTS only when it is observed and bound: status
    ACCEPTABLE, the run id the evaluation is bound to, `milestones.reload_after_save` true (the compare line was seen) and a
    `shipped_hash` equal to the new candidate's. A counted record whose fingerprint is not equal is a FAILURE; a counted equal one is
    serialization evidence for the stage. Anything else is listed under `rejected` and changes nothing."""
    records = evidence.get("fingerprint_records") if isinstance(evidence, dict) else None
    verdict: dict = {"counted": [], "failures": [], "rejected": []}
    for record in records if isinstance(records, list) else []:
        label = record.get("run_id") if isinstance(record, dict) else None
        if not isinstance(record, dict):
            verdict["rejected"].append("a fingerprint record is not an object")
            continue
        block, marks = record.get("fingerprint"), record.get("milestones")
        why = None
        if record.get("status") != "ACCEPTABLE":
            why = f"run evidence status is {record.get('status')!r}, not ACCEPTABLE (not bound to a manifest)"
        elif not run_id or label != run_id:
            why = f"record run {label!r} is not the run identity {run_id!r} this evaluation is bound to"
        elif record.get("shipped_hash") != spec["new_candidate"]["shipped_hash"]:
            why = "record does not name the new candidate's shipped hash"
        elif not (isinstance(marks, dict) and marks.get("reload_after_save") is True and isinstance(block, dict) and block.get("compare_observed")):
            why = "the reload's compare line was not observed (milestones.reload_after_save is not true)"
        if why:
            verdict["rejected"].append(f"{label}: {why}")
        elif block.get("equal") is True:
            verdict["counted"].append(label)
        else:
            verdict["failures"].append(f"reload_saved: fingerprint differs after reload in {', '.join(block.get('diff_sections') or ['(unspecified)'])}")
    return verdict


def evaluate_upgrade(spec: object, evidence: object, run_identity: object = None) -> dict:
    """Judge a run's evidence against the scenario. `evidence` may be None/empty: that is LIVE_PENDING, not a pass."""
    plan = plan_upgrade(spec)
    spec = validate_spec(spec)
    result = {"schema_version": SCHEMA_VERSION, "mode": "SAVE_UPGRADE_EVALUATE", "case": spec["case"], "refusals": [], "failures": [],
              "proxy_stages": [], "stages_seen": []}
    stages = evidence.get("stages") if isinstance(evidence, dict) else None
    if not stages:
        pending = {**result, "status": "LIVE_PENDING", "plan": plan["stages"]}
        if isinstance(evidence, dict) and evidence.get("fingerprint_records"):
            # A fingerprint alone covers one stage; the other five still need their own evidence, so this stays pending.
            run_id = (run_identity or {}).get("run_id") if isinstance(run_identity, dict) else evidence.get("run_id")
            pending["fingerprint_evidence"] = fingerprint_judgement(spec, evidence, run_id)
        return pending
    if not all(isinstance(s, dict) and s.get("stage") in STAGES for s in stages):
        return {**result, "status": "REFUSED", "refusals": ["evidence has a stage that is missing or unknown"]}
    names = [s["stage"] for s in stages]
    result["stages_seen"] = names
    result["refusals"] += [f"missing stage: {name}" for name in STAGE_ORDER if name not in names]
    if len(set(names)) != len(names):
        result["refusals"].append("a stage appears more than once")
    elif [n for n in names if n in STAGE_ORDER] != [n for n in STAGE_ORDER if n in names]:
        result["refusals"].append(f"stages are out of order: {names}")
    sequence = [s.get("seq") for s in stages]
    if not all(isinstance(n, int) for n in sequence) or sequence != sorted(sequence):
        result["refusals"].append("stage seq numbers are missing or not increasing")
    if run_identity is not None:
        got = run_identity.get("shipped_hash") if isinstance(run_identity, dict) else None
        if not isinstance(run_identity, dict) or not run_identity.get("run_id") or got != spec["new_candidate"]["shipped_hash"]:
            result["refusals"].append("run identity lacks a run_id or names a different candidate than the new manifest")
    elif not (isinstance(evidence, dict) and evidence.get("run_id")):
        result["refusals"].append("no run identity: pass the run id and shipped hash the run manifest (R1) records")
    if result["refusals"]:
        return {**result, "status": "REFUSED"}
    by_name = {s["stage"]: s for s in stages}
    run_id = run_identity.get("run_id") if isinstance(run_identity, dict) else evidence.get("run_id")
    judged = fingerprint_judgement(spec, evidence, run_id)
    result["fingerprint_evidence"] = judged
    result["failures"] += judged["failures"]
    previous_out = None
    for name in STAGE_ORDER:
        stage = by_name[name]
        result["failures"] += _stage_problems(stage, spec, previous_out)
        previous_out = stage.get("save_out_hash", previous_out)
        if name == "reload_saved" and judged["counted"] and not judged["failures"]:
            continue  # an observed, equal, bound fingerprint compare shows the saved campaign reloads with its state intact
        if stage.get("evidence_kind") != SERIALIZATION and STAGES[name][0] == SERIALIZATION:
            result["proxy_stages"].append(name)
    result["failures"] += _observation_failures(by_name["migration_check"], spec, by_name["repeat_idempotence"])
    status = "FAIL" if result["failures"] else "PROXY_ONLY" if result["proxy_stages"] else "VERIFIED"
    return {**result, "status": status}


def _load_json(path: Path) -> object:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UpgradeError(f"{path}: {exc}") from exc


def add_parser(subcommands) -> None:
    command = subcommands.add_parser("save-upgrade", help="offline planner/evaluator for save-upgrade scenarios (old->new candidate, copied save, separate slot, reload, idempotence); launches nothing")
    sub = command.add_subparsers(dest="save_upgrade_command", required=True)
    plan = sub.add_parser("plan", help="show the ordered stages and per-case expectations for a scenario spec")
    plan.add_argument("spec", type=Path)
    plan.add_argument("--json", action="store_true")
    evaluate = sub.add_parser("evaluate", help="judge a run's evidence file against the spec; exit 1 unless VERIFIED")
    evaluate.add_argument("spec", type=Path)
    evaluate.add_argument("evidence", type=Path, nargs="?", help="evidence JSON; omitted means LIVE_PENDING")
    evaluate.add_argument("--run-id", help="run identity id (from the R1 run manifest once available)")
    evaluate.add_argument("--run-hash", help="the shipped hash that run identity records")
    evaluate.add_argument("--fingerprint-record", type=Path, action="append", default=[], metavar="JSON",
                          help="a `run-manifest evaluate` result of a save-reload run (milestones.reload_after_save, fingerprint block) plus the shipped_hash it ran; repeatable")
    evaluate.add_argument("--out", type=Path, help="also write the verdict JSON here")
    evaluate.add_argument("--json", action="store_true")


def run_cli(args: argparse.Namespace) -> int:
    try:
        spec = _load_json(args.spec)
        if args.save_upgrade_command == "plan":
            result = plan_upgrade(spec)
        else:
            evidence = _load_json(args.evidence) if args.evidence else None
            if args.fingerprint_record:
                if evidence is not None and not isinstance(evidence, dict):
                    raise UpgradeError("evidence must be a JSON object to take fingerprint records")
                evidence = {**(evidence or {}), "fingerprint_records": [*((evidence or {}).get("fingerprint_records") or []),
                                                                         *(_load_json(path) for path in args.fingerprint_record)]}
            identity = {"run_id": args.run_id, "shipped_hash": args.run_hash} if args.run_id or args.run_hash else None
            result = evaluate_upgrade(spec, evidence, identity)
            if args.out:
                atomic_write_json(args.out, result, indent=2)
    except UpgradeError as exc:
        print(f"bridgeforge: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"save-upgrade {result['mode']} {result['case']}: {result['status']}")
        for line in result.get("refusals", []) + result.get("failures", []):
            print(f"  {line}")
        for name in result.get("proxy_stages", []):
            print(f"  proxy evidence only: {name}")
    if args.save_upgrade_command == "plan":
        return 0
    return 0 if result["status"] == "VERIFIED" else 1
