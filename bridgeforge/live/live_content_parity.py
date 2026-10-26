"""Live content parity (ROADMAP 77.17): what the game loaded for a mod against what its working copy defines.

FIX-001 (All the Domain Drones 0.6) reached LIVE_VALIDATED with the mod's whole `rules.csv` missing, because the probe proved
boot and campaign load but never counted content. Before launch `expected_content` reads the candidate's data files (the ids per
kind) into the probe config as `content_parity`; the probe's `content-parity` stage looks every id up in the running game and
logs one INFO summary and one FAIL line per kind with missing ids. `parity_findings` reads those lines back and judges a member.
(Not to be confused with `content_parity.py`, the offline archive audit, 77.18.)

Log shapes (house format `BF-PROBE|<ver>|<check>|<status>|<subject>|<detail>`):
    content-parity|INFO|mod=<id>|rules=12/12,hulls=3/4,...,src_hulls=3,src_weapons=9
    content-parity|FAIL|mod=<id>|kind=rules missing 12/12: a,b,c ...      (one line per kind with a shortfall)
`have/expected` counts expected ids the game resolves; `src_<kind>` counts every spec of that kind whose source mod is this mod
(`WithSourceMod.getSourceMod().getId()`), so src above expected is excess content (information, never a failure).
"""
from __future__ import annotations

import re
from pathlib import Path

# kind -> data file relative to the mod root; each file's `id` column names the loaded ids.
CSV_KINDS: dict[str, tuple[str, ...]] = {
    "rules": ("data", "campaign", "rules.csv"),
    "hulls": ("data", "hulls", "ship_data.csv"),
    "weapons": ("data", "weapons", "weapon_data.csv"),
    "wings": ("data", "hulls", "wing_data.csv"),
    "hullmods": ("data", "hulls", "hull_mods.csv"),
    "industries": ("data", "campaign", "industries.csv"),
    "conditions": ("data", "campaign", "market_conditions.csv"),
    "submarkets": ("data", "campaign", "submarkets.csv"),
}
KINDS = tuple(CSV_KINDS) + ("systems", "planet_types")
MAX_LISTED_IDS = 40

_PARITY_LINE = re.compile(r"BF-PROBE\|[^|]*\|content-parity\|(?P<status>[^|]*)\|mod=(?P<mod>[^|]*)\|(?P<detail>.*)$")
_MISSING = re.compile(r"kind=(?P<kind>\w+) missing (?P<have>\d+)/(?P<expected>\d+): ?(?P<ids>.*)$")


def expected_content(mod_root: Path, *, systems: list[str] | None = None, body_types: list[str] | None = None) -> dict[str, list[str]]:
    """{kind: sorted ids} the mod's own data files define; kinds with no ids are left out."""
    from bridgeforge.probe.probe_config import _csv_ids

    found: dict[str, list[str]] = {}
    for kind, parts in CSV_KINDS.items():
        ids = sorted(_csv_ids(Path(mod_root).joinpath(*parts)))
        if ids:
            found[kind] = ids
    if systems:
        found["systems"] = sorted(set(systems))
    if body_types:
        found["planet_types"] = sorted(set(body_types))
    return found


def merge_parity(configs: list[dict]) -> dict[str, dict[str, list[str]]]:
    """Group config: each member keeps its own expectations, keyed by mod id."""
    merged: dict[str, dict[str, list[str]]] = {}
    for config in configs:
        parity = config.get("content_parity") or {}
        merged.update({mod: {k: list(v) for k, v in kinds.items()} for mod, kinds in parity.items()})
    return merged


def parity_findings(log: Path, config: dict) -> dict[str, dict]:
    """Per mod with expectations: `status` PASS / FAIL / NOT_OBSERVED, `missing` {kind: [ids]} (the probe caps the listed ids, so
    `missing_counts` carries the true number), `excess` {kind: n} from the source-mod counts, and the raw `counts`."""
    expected = config.get("content_parity") or {}
    result = {mod: {"status": "NOT_OBSERVED", "missing": {}, "missing_counts": {}, "excess": {}, "counts": {}} for mod in expected}
    for line in Path(log).read_text(encoding="utf-8", errors="replace").splitlines():
        match = _PARITY_LINE.search(line)
        if not match or match["mod"] not in result:
            continue
        entry = result[match["mod"]]
        if entry["status"] == "NOT_OBSERVED":
            entry["status"] = "PASS"
        if match["status"] == "FAIL":
            miss = _MISSING.match(match["detail"].strip())
            entry["status"] = "FAIL"
            if miss:
                entry["missing"][miss["kind"]] = [i for i in miss["ids"].replace(" ...", "").split(",") if i]
                entry["missing_counts"][miss["kind"]] = int(miss["expected"]) - int(miss["have"])
            else:
                entry["missing"].setdefault("unparsed", []).append(match["detail"].strip()[:120])
        elif match["status"] == "INFO":
            entry["counts"] = {k.strip(): v.strip() for k, _, v in (pair.partition("=") for pair in match["detail"].split(","))}
    for mod, entry in result.items():
        for kind, ids in expected[mod].items():
            source = entry["counts"].get("src_" + kind, "")
            if source.isdigit() and int(source) > len(ids):
                entry["excess"][kind] = int(source) - len(ids)
    return result


def parity_failure_lines(findings: dict[str, dict]) -> dict[str, list[str]]:
    """Failure texts per mod for the group verdict: one per kind, listing the missing ids."""
    lines: dict[str, list[str]] = {}
    for mod, entry in findings.items():
        if entry["status"] != "FAIL":
            continue
        lines[mod] = [f"content-parity|{kind}|missing {entry['missing_counts'].get(kind, len(ids))}: {', '.join(ids[:MAX_LISTED_IDS])}"[:240]
                      for kind, ids in sorted(entry["missing"].items())] or ["content-parity|unknown|probe reported a shortfall"]
    return lines
