"""Mod Atlas runtime layer (ROADMAP item 67, phase 5): probe results join the static index.

`atlas runtime LOG...` reads a probe-group test log (BF-PROBE lines) into the `runtime` table: every FAIL line, plus the
market-supply lines that say which industries supplied each mod commodity. `forecast` then attaches that evidence:

- ATLAS-RUNTIME-SUPPLY: a mod's commodity had demand and no supply in a live run (probe 0.2.25 market-supply), or an expected
  supplier ("commodity@industry") supplied nothing. Evidence, not a guess: REVIEW, with the test id.
- A static ATLAS-READS-REPLACED finding about the same mod is marked as confirmed live when such a run exists (DNEEP x AoTD:
  GRP-DNEEP-SUPPLY-BEFORE-20261011 showed the missing food the static read of `farming` predicted).
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from .atlas_rules import SILENT, Finding

PROBE_LINE = re.compile(r"BF-PROBE\|(?P<version>[^|]*)\|(?P<check>[^|]*)\|(?P<status>[^|]*)\|(?P<subject>[^|]*)\|(?P<detail>.*)$")
KEPT = {"FAIL"}
KEPT_ANY_STATUS = {"market-supply"}
RUNTIME_SCHEMA = ("CREATE TABLE IF NOT EXISTS runtime (test TEXT, probe TEXT, chk TEXT, status TEXT, subject TEXT, detail TEXT);"
                  "CREATE INDEX IF NOT EXISTS runtime_by_test ON runtime (test);")


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(RUNTIME_SCHEMA)


def ingest(conn: sqlite3.Connection, logs: list[Path]) -> dict:
    """Read each log into the runtime table, replacing whatever the same test id (the log's stem) held before."""
    ensure_schema(conn)
    stats = {"logs": 0, "lines": 0, "tests": []}
    for log in logs:
        test = Path(log).name.removesuffix(".stdout.log").removesuffix(".log")
        rows = []
        for line in Path(log).read_text(encoding="utf-8", errors="replace").splitlines():
            match = PROBE_LINE.search(line)
            if match and (match["status"] in KEPT or match["check"] in KEPT_ANY_STATUS):
                rows.append((test, match["version"], match["check"], match["status"], match["subject"], match["detail"].strip()[:400]))
        conn.execute("DELETE FROM runtime WHERE test = ?", (test,))
        conn.executemany("INSERT INTO runtime VALUES (?, ?, ?, ?, ?, ?)", rows)
        stats["logs"] += 1
        stats["lines"] += len(rows)
        stats["tests"].append(test)
    conn.commit()
    return stats


def _commodity_owners(conn: sqlite3.Connection, mods: list[dict]) -> dict[str, list[str]]:
    owners: dict[str, list[str]] = {}
    for mod in mods:
        for row in conn.execute("SELECT id FROM facts WHERE mod = ? AND version = ? AND kind = 'commodity' AND action = 'defines'",
                                (mod["id"], mod["version"])):
            owners.setdefault(row["id"], []).append(mod["id"])
    return owners


SUPPLIED_IN = re.compile(r"supplied in (\d+) market")


def _fixed_since(conn: sqlite3.Connection, rowid: int, subject: str) -> str | None:
    """The test of a later ingested run in which `subject` was supplied (market-supply OK, or INFO with supply in 1+ markets), if any.
    Order is ingest order: the table's rowid, so logs are ingested oldest first and a re-ingested test counts as its newest run."""
    for row in conn.execute("SELECT test, status, detail FROM runtime WHERE chk = 'market-supply' AND subject = ? AND rowid > ? "
                            "ORDER BY rowid", (subject, rowid)):
        if row["status"] == "OK":
            return row["test"]
        match = SUPPLIED_IN.search(row["detail"])
        if row["status"] == "INFO" and match and int(match.group(1)) > 0:
            return row["test"]
    return None


def runtime_findings(conn: sqlite3.Connection, subjects: list[dict]) -> list[Finding]:
    """ATLAS-RUNTIME-SUPPLY for the subjects' commodities, from the runtime table (empty when no log was ingested). A failure that a
    later ingested run shows fixed is kept at SAFE with that run named, so the history stays visible and nothing stale looks open."""
    ensure_schema(conn)
    rows = conn.execute("SELECT rowid AS rid, test, subject, detail FROM runtime WHERE chk = 'market-supply' AND status = 'FAIL' "
                        "AND subject != 'commodities'").fetchall()
    if not rows:
        return []
    owners = _commodity_owners(conn, subjects)
    found: list[Finding] = []
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        commodity = row["subject"].split("@", 1)[0]
        for mod in owners.get(commodity, []):
            key = (mod, row["subject"], row["test"])
            if key in seen:
                continue
            seen.add(key)
            later = _fixed_since(conn, row["rid"], row["subject"])
            text = f"{mod}: live run {row['test']} found {row['subject']} unsupplied: {row['detail']}"
            found.append(Finding("ATLAS-RUNTIME-SUPPLY", "SAFE" if later else "REVIEW", SILENT,
                                 text + (f" (fixed since: {later} supplied it)" if later else ""), [mod], [], [commodity]))
    return found


def confirmed_by_runtime(findings: list[Finding]) -> None:
    """Mark ATLAS-READS-REPLACED findings about a mod whose commodity failed live, in place: still failing, or seen failing and fixed."""
    live: dict[str, tuple[str, bool]] = {}
    for finding in findings:
        if finding.rule == "ATLAS-RUNTIME-SUPPLY":
            test, fixed = finding.summary.split("live run ", 1)[1].split(" ", 1)[0], finding.level == "SAFE"
            for mod in finding.mods:
                if mod not in live or (live[mod][1] and not fixed):  # an open failure outranks a fixed one
                    live[mod] = (test, fixed)
    for finding in findings:
        if finding.rule != "ATLAS-READS-REPLACED" or "[confirmed live" in finding.summary or "[seen live" in finding.summary:
            continue
        hit = next((live[mod] for mod in finding.mods if mod in live), None)
        if hit:
            finding.summary += f" [seen live in {hit[0]}, fixed since]" if hit[1] else f" [confirmed live: {hit[0]}]"
