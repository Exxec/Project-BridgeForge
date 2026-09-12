from __future__ import annotations

import json
import re
from pathlib import Path

"""SPW performance bridge (roadmap P6).

File-level only, by design (`docs/REVIVAL_ASSURANCE_PLAN.md` principle 4): this module never
imports anything from the Starsector Performance Workbench (SPW) repository. It only reads SPW's
own JSON/log artifacts, exactly as any other consumer of those files would.

SPW's `performance-report.json` schema is still a design document at the time this was written
(`Starsector project workbench/docs/PERFORMANCE_WORKBENCH_DESIGN.md`), not yet a stable shipped
format, so `ingest_spw_report` is deliberately schema-tolerant: it recognizes a handful of
plausible key spellings for "per-mod entries", "CPU share", "top scripts" and "startup time", and
reports whatever it can't find as an explicit limitation rather than guessing or raising.
"""

# Per-mod list may be spelled any of these at the top level.
_MOD_LIST_KEYS = ("mods", "per_mod", "attribution", "mod_attribution")
# Within one per-mod entry, the mod identifier.
_MOD_ID_KEYS = ("mod_id", "id", "mod", "owner")
# Within one per-mod entry, its CPU share (0..1 or a percentage; both are passed through as-is,
# with whichever key matched recorded so a reader can tell them apart).
_CPU_SHARE_KEYS = ("cpu_share", "cpu_fraction", "cpu_percent", "cpu_pct")
# Within one per-mod entry, its heaviest every-frame scripts.
_TOP_SCRIPTS_KEYS = ("top_scripts", "hot_scripts", "heaviest_scripts", "scripts")
# Startup time, either a flat number at the top level or a per-mod breakdown.
_STARTUP_TOP_KEYS = ("startup_ms", "startup_time_ms", "startup")
_STARTUP_PER_MOD_KEYS = ("per_mod", "by_mod", "per_mod_ms")


class SpwBridgeError(ValueError):
    """Raised when an SPW report or a log path cannot be read at all."""


def _first_present(data: dict, keys: tuple[str, ...]):
    for key in keys:
        if key in data:
            return key, data[key]
    return None, None


def _normalize_mod_entry(entry: dict) -> dict[str, object]:
    _id_key, mod_id = _first_present(entry, _MOD_ID_KEYS)
    cpu_key, cpu_value = _first_present(entry, _CPU_SHARE_KEYS)
    scripts_key, scripts_value = _first_present(entry, _TOP_SCRIPTS_KEYS)
    limitations: list[str] = []
    if mod_id is None:
        limitations.append("no recognized mod-identifier key on this entry")
    if cpu_key is None:
        limitations.append("no recognized CPU-share key on this entry")
    scripts: list[dict[str, object]] = []
    if isinstance(scripts_value, list):
        for script in scripts_value:
            if isinstance(script, dict):
                scripts.append(script)
            elif isinstance(script, str):
                scripts.append({"name": script})
    elif scripts_key is not None:
        limitations.append(f"'{scripts_key}' was present but not a list")
    return {
        "mod_id": mod_id,
        "cpu_share": cpu_value,
        "cpu_share_key": cpu_key,
        "top_scripts": scripts,
        "limitations": limitations,
    }


def _normalize_startup(data: dict) -> dict[str, object]:
    top_key, top_value = _first_present(data, _STARTUP_TOP_KEYS)
    per_mod: dict[str, object] = {}
    limitations: list[str] = []
    if isinstance(top_value, dict):
        _pm_key, pm_value = _first_present(top_value, _STARTUP_PER_MOD_KEYS)
        if isinstance(pm_value, dict):
            per_mod = pm_value
        total = top_value.get("total_ms")
    elif isinstance(top_value, (int, float)):
        total = top_value
    else:
        total = None
        if top_key is None:
            limitations.append("no recognized startup-time key at the report's top level")
    return {"total_ms": total, "per_mod_ms": per_mod, "limitations": limitations}


def ingest_spw_report(path: Path) -> dict[str, object]:
    """Read SPW's `performance-report.json` and normalize it into per-mod CPU share, top scripts
    and startup time. Never writes, never imports SPW code -- see the module docstring."""
    report_path = Path(path).expanduser().resolve()
    if not report_path.is_file():
        raise SpwBridgeError(f"{report_path} is not an existing file.")
    try:
        raw = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SpwBridgeError(f"{report_path} is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise SpwBridgeError(f"{report_path} did not parse to a JSON object.")

    limitations: list[str] = []
    list_key, mod_list = _first_present(raw, _MOD_LIST_KEYS)
    per_mod: list[dict[str, object]] = []
    if isinstance(mod_list, list):
        for entry in mod_list:
            if isinstance(entry, dict):
                per_mod.append(_normalize_mod_entry(entry))
    elif list_key is not None:
        limitations.append(f"'{list_key}' was present but not a list")
    else:
        limitations.append("no recognized per-mod list key at the report's top level")

    startup = _normalize_startup(raw)
    limitations.extend(startup.pop("limitations"))

    return {
        "schema_version": 1,
        "mode": "READ_ONLY_SPW_REPORT",
        "source": str(report_path),
        "report_schema_version": raw.get("schema_version"),
        "per_mod": per_mod,
        "startup": startup,
        "limitations": limitations,
    }


# --- log spam (P6) -----------------------------------------------------------------------------

_LOG_LINE_RE = re.compile(r"^(?P<millis>\d+)\s+\[(?P<thread>[^\]]*)\]\s+(?P<level>\S+)\s+(?P<logger>\S+)\s+-\s+(?P<message>.*)$")
# Strip an object's identity-hash / memory address suffix so genuinely repeated log statements
# still group together, e.g. "...advance called with null engine@1a2b3c4" style noise.
_ADDRESS_SUFFIX_RE = re.compile(r"@[0-9a-fA-F]{4,}")


def _normalize_message(message: str) -> str:
    return _ADDRESS_SUFFIX_RE.sub("@*", message).strip()


def log_spam(log_path: Path, mod_prefixes: list[str], *, min_repeats: int = 5) -> dict[str, object]:
    """Count repeated identical (post-normalization) log lines per mod prefix.

    Real motivation (`docs/REVIVAL_ASSURANCE_PLAN.md` P6): Arkgneisis's
    `loa_awacs_order_manager ... advance called with null engine` logs every frame. A line whose
    logger or message contains one of `mod_prefixes` and repeats at least `min_repeats` times is
    reported as spam, grouped by that prefix and sorted by count, descending.
    """
    path = Path(log_path).expanduser().resolve()
    if not path.is_file():
        raise SpwBridgeError(f"{path} is not an existing file.")
    prefixes = list(mod_prefixes or [])
    counts: dict[str, dict[str, dict[str, object]]] = {prefix: {} for prefix in prefixes}
    for line_no, raw in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        match = _LOG_LINE_RE.match(raw)
        message = match.group("message") if match else raw
        logger = match.group("logger") if match else ""
        haystack = f"{logger} {message}"
        for prefix in prefixes:
            if prefix not in haystack:
                continue
            key = _normalize_message(message)
            bucket = counts[prefix].setdefault(key, {"count": 0, "first_line": line_no})
            bucket["count"] += 1
            bucket["last_line"] = line_no

    by_prefix: dict[str, list[dict[str, object]]] = {}
    total_spam_lines = 0
    for prefix, messages in counts.items():
        entries = [
            {"message": message, "count": info["count"], "first_line": info["first_line"], "last_line": info.get("last_line", info["first_line"])}
            for message, info in messages.items()
            if info["count"] >= min_repeats
        ]
        entries.sort(key=lambda e: e["count"], reverse=True)
        by_prefix[prefix] = entries
        total_spam_lines += sum(e["count"] for e in entries)

    return {
        "schema_version": 1,
        "mode": "READ_ONLY_LOG_SPAM",
        "log": str(path),
        "mod_prefixes": prefixes,
        "min_repeats": min_repeats,
        "by_prefix": by_prefix,
        "total_spam_lines": total_spam_lines,
    }


# --- performance gate (P6) ----------------------------------------------------------------------


def perf_gate(summary: dict[str, object], thresholds: dict[str, object] | None) -> dict[str, object]:
    """PASS / WARN / FAIL a performance summary against owner-set thresholds.

    `summary` carries flat numeric metrics (e.g. `cpu_share`, `startup_ms`, `spam_count`).
    `thresholds` maps a metric name to `{"warn": x, "fail": y}` (either bound optional). No
    thresholds (`None` or `{}`) means **report-only**: every metric is reported but nothing ever
    fails or warns, matching the roadmap's "defaults to report-only" requirement.
    """
    thresholds = thresholds or {}
    report_only = not thresholds
    checks: list[dict[str, object]] = []
    worst = "PASS"
    rank = {"PASS": 0, "WARN": 1, "FAIL": 2}
    for metric, value in summary.items():
        if not isinstance(value, (int, float)):
            continue
        bounds = thresholds.get(metric)
        if not isinstance(bounds, dict):
            checks.append({"metric": metric, "value": value, "warn_at": None, "fail_at": None, "result": "REPORT_ONLY"})
            continue
        warn_at = bounds.get("warn")
        fail_at = bounds.get("fail")
        result = "PASS"
        if isinstance(fail_at, (int, float)) and value >= fail_at:
            result = "FAIL"
        elif isinstance(warn_at, (int, float)) and value >= warn_at:
            result = "WARN"
        checks.append({"metric": metric, "value": value, "warn_at": warn_at, "fail_at": fail_at, "result": result})
        if rank.get(result, 0) > rank[worst]:
            worst = result

    return {
        "schema_version": 1,
        "mode": "READ_ONLY_PERF_GATE",
        "report_only": report_only,
        "status": "REPORT_ONLY" if report_only else worst,
        "checks": checks,
    }
