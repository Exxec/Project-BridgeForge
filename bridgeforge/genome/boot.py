"""94.G2: the boot halves of a gene's proofs, `gene boot stage` and `gene boot evaluate`.

`gene prove` writes the static halves and two copies under the proof's `work/`: the donor without the gene (`subtraction`) and
the gene alone in a carrier mod (`carrier`). Each copy's boot half is a live run on the test rig. P1's two boots
(P1B-SUB2-20261120, P1B-CAR3-20261122) were staged and read by hand; this is that procedure as a command.

- `stage` copies one half's work copy into a boot queue as a workspace (`<queue>/<proof>-<half>/working`) with a marker,
  `GENE_BOOT_STAGED.json`, naming the proof, the half, the gene identity and the copy's tree hash. An older copy is moved to
  `<queue>/_replaced-<date>/`, never deleted. It refuses when the half's static proof did not pass, or the rig lacks a mod the
  gene needs. `probe-group plan --retest` and `install` then stage it as for any mod.
- `evaluate` reads the run back. The run must be bound to the proof: its manifest names the half's mod, staged with exactly the
  bytes of the proof's work copy, and the shared evaluator finds the log is this run's with nothing drifted. The verdict:
  - carrier: PASS when the game loaded it (no `Error loading mod`, 93.65), the probe report passes it, and the log shows no
    Fatal and no mod error. Each id the gene provides is listed as observed by the probe or not;
  - subtraction: PASS (`BOOTED`) when the donor loaded and reached the main menu with no Fatal and no mod error. Owner
    2026-11-20 ("Expected outcome"): when every Fatal and mod error names an id the gene provides, through a dependent the static
    proof recorded whose load condition held in this run, it is `BLOCKED_BY_DEPENDENT` and the gene still passes. Anything else
    fails it.
  A run that shows neither the main menu nor a Fatal is UNKNOWN (P1B-SUB-20261120 stalled before the game's agents started).

  It copies the log, the dialog log and the manifest to `<proof>/boot/<TESTID>/` and writes `<proof>/boot-<half>-<TESTID>.json`
  with the common evidence header (kind `gene-boot`). The static proofs are not changed.

A gene boot run is never recorded or archived: `probe-group record` refuses a workspace that carries the marker.
"""
from __future__ import annotations

import json
import shutil
from datetime import date, datetime, timezone
from pathlib import Path

BOOT_KIND = "gene-boot"
STAGED_MARKER = "GENE_BOOT_STAGED.json"
# The static proof each half boots: a carrier is a gene's (`gene prove`) or a gene set's (`gene prove-set`).
HALVES = {"subtraction": ("subtraction-proof.json",), "carrier": ("isolation-proof.json", "set-isolation-proof.json")}
BLOCKED, BOOTED = "BLOCKED_BY_DEPENDENT", "BOOTED"
MESSAGE_CHARS = 300
# A gene's provided kinds and the probe config list that checks that kind (probe_group's group_members); the probe has no
# check of the other kinds, so their ids are never observed.
PROBE_LISTS = {"hull": "hulls", "variant": "variants", "wing": "wings", "faction": "factions", "commodity": "commodities"}


class BootError(ValueError):
    """The proof, the queue, the rig or the run cannot be used: nothing was written."""


def _read_json(path: Path, what: str) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BootError(f"cannot read {what} {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise BootError(f"{what} {path} is not a JSON object")
    return data


def _proof_parts(proof: Path, half: str) -> tuple[dict, dict, Path]:
    """(gene.json, the half's static proof, the half's work copy) of a proof folder."""
    if half not in HALVES:
        raise BootError(f"unknown half {half!r} (one of {', '.join(HALVES)})")
    proof = Path(proof)
    gene = _read_json(proof / "gene.json", "the gene manifest")
    static_path = next((proof / name for name in HALVES[half] if (proof / name).is_file()), proof / HALVES[half][0])
    static = _read_json(static_path, f"the {half} proof")
    work = proof / "work" / half
    if not (work / "mod_info.json").is_file():
        raise BootError(f"{work} holds no mod_info.json: not a proof's work copy")
    if (static.get("gene") or {}).get("identity") != gene.get("identity"):
        raise BootError(f"{static_path} is about another gene than {proof / 'gene.json'}")
    return gene, static, work


def _mod_id(folder: Path) -> str:
    from bridgeforge.mod_files import read_mod_info

    info = read_mod_info(folder) or {}
    if not isinstance(info.get("id"), str) or not info["id"]:
        raise BootError(f"{folder / 'mod_info.json'} names no mod id")
    return info["id"]


def _rig_mod_ids(rig: Path) -> set[str]:
    from bridgeforge.mod_files import read_mod_info

    mods = Path(rig) / "mods"
    if not mods.is_dir():
        raise BootError(f"{rig} has no mods folder: not a test rig")
    ids = set()
    for folder in mods.iterdir():
        info = read_mod_info(folder) if folder.is_dir() else None
        if isinstance(info, dict) and isinstance(info.get("id"), str):
            ids.add(info["id"])
    return ids


def stage(proof: Path, half: str, queue: Path, rig: Path, *, today: str | None = None) -> dict:
    """Copy the proof's `half` work copy into `queue` as a boot workspace with its marker. Raises BootError."""
    from bridgeforge.archive import ArchiveError, _move_aside
    from bridgeforge.run_manifest import ManifestError, _tree_hash
    from bridgeforge.safeio import atomic_write_json

    proof = Path(proof).resolve()
    gene, static, work = _proof_parts(proof, half)
    if static.get("verdict") != "PASS":
        raise BootError(f"the {half} proof's static half reads {static.get('verdict')!r}, not PASS: there is nothing to boot")
    missing = sorted(set((gene.get("needs") or {}).get("mods") or []) - _rig_mod_ids(rig))
    if missing:
        raise BootError(f"the rig {rig} lacks mod(s) the gene needs: {', '.join(missing)}")
    try:
        tree = _tree_hash(work)
    except ManifestError as exc:
        raise BootError(str(exc)) from exc
    queue = Path(queue)
    queue.mkdir(parents=True, exist_ok=True)
    workspace = queue / f"{proof.name}-{half}"
    replaced = None
    if workspace.exists():
        try:
            replaced = _move_aside(workspace, queue, today or date.today().isoformat())
        except (ArchiveError, OSError) as exc:
            raise BootError(f"cannot move the older {workspace} aside: {exc}") from exc
    shutil.copytree(work, workspace / "working")
    marker = {"schema_version": 1, "mode": "GENE_BOOT_STAGED", "proof": str(proof), "half": half, "mod_id": _mod_id(work),
              "gene": {"identity": gene["identity"], "schema_version": gene.get("schema_version")}, "tree_sha256": tree,
              "staged_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    atomic_write_json(workspace / STAGED_MARKER, marker, indent=2)
    return {**marker, "workspace": str(workspace), "replaced": str(replaced) if replaced else None}


def staged_boot_workspaces(workspaces: list[Path]) -> list[Path]:
    """The workspaces among `workspaces` that `stage` made: their runs are evaluated, never recorded."""
    return [Path(w) for w in workspaces if w is not None and (Path(w) / STAGED_MARKER).is_file()]


def _binding(rig: Path, test_id: str, mod_id: str, work: Path) -> tuple[dict, dict, list[str]]:
    """(manifest, the staged entry, problems): is the run bound to this work copy?"""
    from bridgeforge.run_manifest import ManifestError, _tree_hash, evaluate_run, read_manifest

    try:
        manifest = read_manifest(rig, test_id)
    except ManifestError as exc:
        raise BootError(f"run {test_id} is not bound to anything: {exc}") from exc
    entry = next((e for e in manifest.get("enabled") or [] if e.get("id") == mod_id), None)
    if entry is None or mod_id not in (manifest.get("targets") or {}):
        raise BootError(f"run {test_id} did not test {mod_id}: its manifest names no such target")
    problems = []
    if entry["staged_sha256"] != _tree_hash(work):
        problems.append(f"the rig's {entry['folder']} was not the proof's work copy when the run was prepared")
    # The milestones are this module's own judgement per half (a subtraction boot may stop at a Fatal by design), so the shared
    # evaluator is asked only whether the log is this run's and nothing staged drifted.
    evidence = evaluate_run(rig, {**manifest, "expected_milestones": []}, rig / "logs" / f"{test_id}.stdout.log", mods_dir=rig / "mods")
    problems += evidence["problems"]
    problems += [f"{mod_id}: {p}" for p in (evidence["members"].get(mod_id) or {}).get("problems", [])]
    return manifest, entry, problems


def _condition_held(loaded: str, enabled: set[str]) -> bool:
    """Did a dependent's load condition hold in a probe boot? `always` does; `with A, B` when one of them was enabled; a
    mission's (`on mission start`) never does, the probe starts its own; `unknown` never does."""
    from .dependents import ALWAYS

    if loaded == ALWAYS:
        return True
    if loaded.startswith("with "):
        return any(mod.strip() in enabled for mod in loaded[len("with "):].split(","))
    return False


def _explained(lines: list[str], dependents: list[dict], enabled: set[str]) -> tuple[list[dict], list[str]]:
    """([{line, dependents}], unexplained lines): a line is explained by the recorded dependents whose provided id it names, as
    a whole token, and whose load condition held."""
    from .dependents import _named

    explained, unexplained = [], []
    for line in lines:
        by = [f"{d['from']} -> {d['to']}" for d in dependents
              if _named(line, str(d.get("to", "")).split(":", 1)[-1]) and _condition_held(str(d.get("loaded", "")), enabled)]
        if by:
            explained.append({"line": line, "dependents": by})
        else:
            unexplained.append(line)
    return explained, unexplained


def _observed(gene: dict, member: dict | None, config_lists: dict) -> dict[str, str]:
    """{provided ref: OBSERVED | NOT_OBSERVED}: observed when the probe's list for its kind held the id and no FAIL named it."""
    failed = {entry.split("|", 2)[1].split(":", 1)[-1] for entry in (member or {}).get("failures", []) if entry.count("|") >= 2}
    result = {}
    for ref in gene.get("provides") or []:
        kind, _, ident = ref.partition(":")
        checked = ident in (config_lists.get(PROBE_LISTS.get(kind, ""), []) or [])
        result[ref] = "OBSERVED" if checked and ident not in failed else "NOT_OBSERVED"
    return result


def _log_facts(rig: Path, log: Path, folder: str, mod_id: str) -> dict:
    from bridgeforge.log_triage import triage_log
    from bridgeforge.probe.probe_record import _enabled_mod_ids, mod_load_failures

    triage = triage_log(log, mods_dir=rig / "mods")
    text = log.read_text(encoding="utf-8", errors="replace")
    failures = [f for f in mod_load_failures(text, rig / "mods") if f["folder"].lower() == folder.lower() or f["mod_id"] == mod_id]
    return {"main_menu": bool(triage["milestones"]["main_menu_reached"]), "load_failures": failures,
            "fatal": [str(e.get("message", ""))[:MESSAGE_CHARS] for e in triage["fatal"]],
            "mod_errors": [str(e.get("message", ""))[:MESSAGE_CHARS] for e in triage["mod_errors"]],
            "enabled": _enabled_mod_ids(rig / "mods") or set()}


def _judge_subtraction(facts: dict, static: dict) -> dict:
    lines = facts["fatal"] + facts["mod_errors"]
    explained, unexplained = _explained(lines, static.get("dependents") or [], facts["enabled"])
    if facts["load_failures"]:
        verdict, boot, why = "FAIL", "NOT_LOADED", "the game did not load the subtracted donor"
    elif unexplained:
        verdict, boot, why = "FAIL", "FAILED", f"{len(unexplained)} Fatal or error line(s) name no recorded dependent"
    elif lines:
        verdict, boot, why = "PASS", BLOCKED, "every Fatal and error names a dependent the static proof recorded (owner 2026-11-20)"
    elif not facts["main_menu"]:
        verdict, boot, why = "UNKNOWN", "NO_MAIN_MENU", "the log shows neither the main menu nor a Fatal"
    else:
        verdict, boot, why = "PASS", BOOTED, "the donor without the gene reached the main menu with no Fatal and no mod error"
    return {"verdict": verdict, "boot_verdict": boot, "why": why, "explained": explained, "unexplained": unexplained}


def _judge_carrier(facts: dict, member: dict | None) -> dict:
    member_verdict = (member or {}).get("verdict", "NOT_IN_REPORT")
    if facts["load_failures"]:
        verdict, boot, why = "FAIL", "NOT_LOADED", "the game did not load the carrier (93.65)"
    elif facts["fatal"] or facts["mod_errors"]:
        verdict, boot, why = "FAIL", "FAILED", f"{len(facts['fatal'])} Fatal and {len(facts['mod_errors'])} mod error line(s)"
    elif not facts["main_menu"]:
        verdict, boot, why = "UNKNOWN", "NO_MAIN_MENU", "the log shows neither the main menu nor a Fatal"
    elif member_verdict != "PASS":
        verdict, boot, why = "FAIL", "FAILED", f"the probe report reads {member_verdict} for the carrier"
    else:
        verdict, boot, why = "PASS", BOOTED, "the carrier loaded, the probe passed it, and the log shows no Fatal and no mod error"
    return {"verdict": verdict, "boot_verdict": boot, "why": why, "member_verdict": member_verdict}


def _copy_run_files(rig: Path, test_id: str, target: Path) -> list[tuple[str, str]]:
    """Copy the run's log, dialog log and manifest into the proof; the evidence header's inputs, relative to the proof."""
    from bridgeforge.run_manifest import manifest_path

    target.mkdir(parents=True)
    logs = rig / "logs"
    inputs = []
    for role, source in (("boot-log", logs / f"{test_id}.stdout.log"), ("boot-dialogs", logs / f"{test_id}.windows.txt"),
                         ("boot-manifest", manifest_path(rig, test_id))):
        if source.is_file():
            shutil.copy2(source, target / source.name)
            inputs.append((role, f"boot/{test_id}/{source.name}"))
    return inputs


def evaluate(proof: Path, half: str, rig: Path, test_id: str) -> dict:
    """Read the boot run `test_id` of the proof's `half` and write its evidence into the proof. Raises BootError, writing nothing,
    when the run is not bound to the proof's work copy or was evaluated before."""
    from bridgeforge.probe.probe_record import group_report
    from bridgeforge.run_manifest import CONFIG_RELATIVE, check_run_id
    from bridgeforge.safeio import atomic_write_json

    from .evidence import header

    proof, rig = Path(proof).resolve(), Path(rig).resolve()
    check_run_id(test_id)
    gene, static, work = _proof_parts(proof, half)
    out = proof / f"boot-{half}-{test_id}.json"
    if out.exists() or (proof / "boot" / test_id).exists():
        raise BootError(f"run {test_id} was evaluated for this proof before ({out.name}); a new run needs a new id")
    mod_id = _mod_id(work)
    manifest, entry, problems = _binding(rig, test_id, mod_id, work)
    if problems:
        raise BootError(f"run {test_id} is not bound to the proof's {half} copy: " + "; ".join(problems[:5]))
    # Bound means nothing drifted since launch: the manifest pins the enabled list and the probe config (runtime_hashes), so the
    # rig's are this run's own. P1B-CAR3-20261122 could not be judged after RevenantLib's test replaced _rig-genes' config.
    log = rig / "logs" / f"{test_id}.stdout.log"
    facts = _log_facts(rig, log, entry["folder"], mod_id)
    if half == "subtraction":
        judged = _judge_subtraction(facts, static)
    else:
        config_path = rig / CONFIG_RELATIVE
        config = json.loads(config_path.read_text(encoding="utf-8")) if config_path.is_file() else {}
        member = group_report(log, config, mods_dir=rig / "mods")["members"].get(mod_id)
        judged = {**_judge_carrier(facts, member),
                  "provided": _observed(gene, member, (config.get("group_members") or {}).get(mod_id) or {})}
    inputs = _copy_run_files(rig, test_id, proof / "boot" / test_id)
    made = header(BOOT_KIND, gene, root=proof, inputs=inputs, verdict=judged["verdict"])
    record = {**made, "half": "boot", "boot_half": half, "test_id": test_id, "mod_id": mod_id, "manifest_id": manifest["manifest_id"],
              "staged_sha256": entry["staged_sha256"], **{k: v for k, v in judged.items() if k != "verdict"},
              "main_menu": facts["main_menu"], "load_failures": facts["load_failures"], "fatal": facts["fatal"],
              "mod_errors": facts["mod_errors"]}
    atomic_write_json(out, record, indent=2)
    return {**record, "written": str(out)}
