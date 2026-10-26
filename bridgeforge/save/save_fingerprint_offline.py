"""Offline save fingerprint (ROADMAP-3 item 79.2): the probe's in-game fingerprint sections, computed from a save folder without the game.

`FingerprintSections.java` (the probe) hashes canonical text per section with 64-bit FNV-1a over UTF-16 code units. This module
re-derives the same text from `campaign.xml` (XStream XML, streamed one line at a time, never loaded whole) and hashes it the same way,
so a save can be compared with an in-game `fingerprint|...` log, or two saves (an original and a repaired copy) with each other.

Only sections whose every field the XML holds in the probe's own form are computed:

- markets: id, factionId, size, condition ids (`MCon@i`), industry ids (`@id`), submarket spec ids (`Submarket@s`), for the markets in the
  economy's market list (the PCMarkets that only carry planet conditions are not in it, as in `getMarketsCopy()`).
- cargo: the player fleet's cargo capacity/fuel/personnel (`mC mF mP`), space used (`sU`), and the fuel, crew and supplies stacks.

Everything else is not comparable offline and excluded with the reason, never faked: systems/totals (system ids and the live entity
count are not stored as such), rings (the band index is not stored), fleets (the probe counts fleets present in locations; the save also
keeps route fleets), player (hull ids are not in the XML for stock variants, and member status is stored only when damaged), mod
(depends on the probe config's faction and system lists).

Read-only. Bounded: a campaign.xml over MAX_BYTES or more than MAX_MARKETS markets is refused.
"""
from __future__ import annotations

import json
import math
import struct
from pathlib import Path

from .save_fingerprint import SECTIONS, parse_fingerprint
from .save_reader import SaveReadError, iter_elements, parse_descriptor, resolve_save_dir

SCHEMA_VERSION = 1
MAX_BYTES = 1 << 30
MAX_MARKETS = 50_000
NOT_COMPARABLE = {
    "systems": "system ids and the live entity count are not stored in the save in the probe's form",
    "rings": "the ring band index is not stored in the save",
    "fleets": "the probe counts fleets present in locations; the save also holds route fleets",
    "player": "hull ids are not in the XML for stock variants and member status is stored only when damaged",
    "mod": "depends on the probe config's faction and system lists",
    "totals": "includes system, planet, fleet and player-member counts that are not comparable",
}
_FNV_OFFSET = 0xCBF29CE484222325
_FNV_PRIME = 0x100000001B3
_MASK = (1 << 64) - 1
_CARGO_COMMODITIES = ("fuel", "crew", "supplies")


class FingerprintError(ValueError):
    """The folder is not a save, or is too large to read within the bounds."""


def fnv64(text: str) -> str:
    """64-bit FNV-1a over the UTF-16 code units, two bytes each (low byte first), as 16 lowercase hex digits (FingerprintSections.fnv64)."""
    value = _FNV_OFFSET
    for byte in text.encode("utf-16-le", errors="surrogatepass"):
        value = ((value ^ byte) * _FNV_PRIME) & _MASK
    return format(value, "016x")


def _f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def hundredths(value: float) -> str:
    """Java `String.valueOf(Math.round(value * 100f))` for a float: float32 product, round half up."""
    return str(math.floor(_f32(_f32(value) * _f32(100.0)) + 0.5))


def _java_sorted(lines: list[str]) -> list[str]:
    """Sorted like Java's String.compareTo (UTF-16 code unit order)."""
    return sorted(lines, key=lambda line: line.encode("utf-16-be", errors="surrogatepass"))


def _number(text: str | None) -> float:
    try:
        return float(text) if text is not None else 0.0
    except ValueError:
        return 0.0


def _markets_line(market: dict) -> str:
    cond, ind, sub = (",".join(_java_sorted(market[key])) for key in ("cond", "ind", "sub"))
    return f"{market['id']};faction={market['faction']};size={market['size']};cond={cond};ind={ind};sub={sub}"


def _cargo_line(cargo: dict) -> str:
    stacks = cargo["stacks"]
    return (f"mC={hundredths(cargo['mC'])};mF={hundredths(cargo['mF'])};mP={hundredths(cargo['mP'])};spaceUsed={hundredths(cargo['sU'])}"
            f";fuel={hundredths(stacks.get('fuel', 0.0))};crew={int(stacks.get('crew', 0.0))};supplies={hundredths(stacks.get('supplies', 0.0))}")


def _market_child(open_market: tuple[int, dict], el, depth: int) -> None:
    base, record = open_market
    if depth == base + 1 and el.text is not None:
        key = {"id": "id", "factionId": "faction", "size": "size"}.get(el.tag)
        if key and not record[key]:
            record[key] = el.text.strip()
        if el.tag == "isPlanetConditionMarketOnly":
            record["pcmo"] = el.text.strip() == "true"
    elif depth == base + 2 and len(el.path) >= 2:
        parent = el.path[-2]
        if parent == "conditions" and el.tag == "MCon" and el.attrs.get("i"):
            record["cond"].append(el.attrs["i"])
        elif parent == "industries" and el.attrs.get("id"):
            record["ind"].append(el.attrs["id"])
        elif parent == "submarkets" and el.tag == "Submarket" and el.attrs.get("s"):
            record["sub"].append(el.attrs["s"])


def _scan(campaign_xml: Path) -> tuple[list[dict], list[str], dict[str, dict], str | None]:
    """One streaming pass: market definitions, the economy's market list (z values), fleet cargos by fleet z, the player fleet z."""
    defs: dict[str, dict] = {}
    listed: list[str] = []
    cargos: dict[str, dict] = {}
    player_z: str | None = None
    open_markets: list[tuple[int, dict]] = []
    open_fleets: list[tuple[int, str]] = []
    open_cargo: tuple[int, dict] | None = None
    stack_size: float | None = None
    for el in iter_elements(campaign_xml):
        depth = len(el.path)
        while open_markets and depth <= open_markets[-1][0]:
            open_markets.pop()
        while open_fleets and depth <= open_fleets[-1][0]:
            open_fleets.pop()
        if open_cargo and depth <= open_cargo[0]:
            open_cargo = None
        z = el.attrs.get("z")
        if el.tag == "playerFleet":
            player_z = z or el.attrs.get("ref") or player_z
        if depth >= 3 and el.tag == "Market" and el.path[-2] == "markets" and el.path[-3] == "econ":
            listed.append(z or el.attrs.get("ref", ""))
        if z and (el.tag == "Market" or el.attrs.get("cl") == "Market"):
            record = {"z": z, "id": "", "faction": "", "size": "", "cond": [], "ind": [], "sub": [], "pcmo": False}
            defs[z] = record
            open_markets.append((depth, record))
            if len(defs) > MAX_MARKETS:
                raise FingerprintError(f"more than {MAX_MARKETS} markets: refusing to read further")
            continue
        if open_markets:
            _market_child(open_markets[-1], el, depth)
        if z and el.tag == "Flt":
            open_fleets.append((depth, z))
        if open_fleets and z and el.tag == "cargo" and el.path[-2] == "fD" and open_fleets[-1][1] not in cargos:
            record = {"mC": _number(el.attrs.get("mC")), "mF": _number(el.attrs.get("mF")), "mP": _number(el.attrs.get("mP")),
                      "sU": _number(el.attrs.get("sU")), "stacks": {}}
            cargos[open_fleets[-1][1]] = record
            open_cargo = (depth, record)
        if open_cargo and el.tag == "CIStack":
            stack_size = _number(el.attrs.get("s")) if el.attrs.get("t") == "RESOURCES" else None
        elif open_cargo and stack_size is not None and el.tag == "d" and el.text:
            name = el.text.strip()
            if name in _CARGO_COMMODITIES:
                stacks = open_cargo[1]["stacks"]
                stacks[name] = _f32(stacks.get(name, 0.0) + stack_size)
            stack_size = None
    return list(defs.values()), listed, cargos, player_z


def _validate(save_dir: Path) -> Path:
    campaign = save_dir / "campaign.xml"
    if not (save_dir / "descriptor.xml").is_file() or not campaign.is_file():
        raise FingerprintError(f"{save_dir} is not a save folder (needs descriptor.xml and campaign.xml)")
    if campaign.stat().st_size > MAX_BYTES:
        raise FingerprintError(f"{campaign} is over {MAX_BYTES} bytes: refusing to read it")
    with campaign.open("rb") as handle:
        head = handle.read(2048).decode("utf-8", errors="replace")
    if "<CampaignEngine" not in head:
        raise FingerprintError(f"{campaign} does not start with a CampaignEngine element: not a Starsector campaign.xml")
    try:
        parse_descriptor(save_dir)
    except SaveReadError as exc:
        raise FingerprintError(str(exc)) from exc
    return campaign


def _section(lines: list[str]) -> dict:
    text = "\n".join(_java_sorted(lines))
    return {"comparable": True, "count": len(lines), "len": len(text), "fnv": fnv64(text)}


def offline_fingerprint(save: Path | str) -> dict:
    """The offline fingerprint of a save folder: per-section digest, or the reason a section is not comparable offline."""
    save_dir = resolve_save_dir(save)
    campaign = _validate(save_dir)
    markets, listed, cargos, player_z = _scan(campaign)
    by_z = {market["z"]: market for market in markets}
    chosen = [by_z[z] for z in listed if z in by_z] if listed else [m for m in markets if not m["pcmo"]]
    sections: dict[str, dict] = {"markets": _section([_markets_line(m) for m in chosen])}
    player_cargo = cargos.get(player_z or "")
    sections["cargo"] = (_section([_cargo_line(player_cargo)]) if player_cargo
                         else {"comparable": False, "reason": "no player fleet cargo found in the save"})
    for name in SECTIONS:
        sections.setdefault(name, {"comparable": False, "reason": NOT_COMPARABLE.get(name, "not computed offline")})
    return {"schema_version": SCHEMA_VERSION, "save": save_dir.name, "sections": {name: sections[name] for name in SECTIONS}}


def _digests_from_other(path: Path) -> dict[str, str | None]:
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        data = json.loads(text)
    except ValueError:
        data = None
    if isinstance(data, dict) and isinstance(data.get("sections"), dict):
        return {name: (row.get("fnv") if isinstance(row, dict) and row.get("comparable") else None)
                for name, row in data["sections"].items()}
    parsed = parse_fingerprint(text)
    if parsed is None:
        raise FingerprintError(f"{path} is neither an offline fingerprint JSON nor a probe log with fingerprint lines")
    return {name: parsed["digests_after"].get(name) or parsed["digests_before"].get(name) for name in SECTIONS}


def compare_fingerprints(left: dict, right: dict) -> dict[str, str]:
    """Per section `equal`, `differ` or `not-comparable`, for two offline fingerprints."""
    return _compare(left, {name: row.get("fnv") if row.get("comparable") else None for name, row in right["sections"].items()})


def compare_with_file(left: dict, other: Path | str) -> dict[str, str]:
    """Per section `equal`, `differ` or `not-comparable` against an offline fingerprint JSON or a probe log (after digests, else before)."""
    return _compare(left, _digests_from_other(Path(other)))


def _compare(left: dict, theirs: dict[str, str | None]) -> dict[str, str]:
    result: dict[str, str] = {}
    for name in SECTIONS:
        mine = left["sections"][name]
        if not mine.get("comparable") or not theirs.get(name):
            result[name] = "not-comparable"
        else:
            result[name] = "equal" if mine["fnv"] == theirs[name] else "differ"
    return result


def render(fingerprint: dict, comparison: dict[str, str] | None = None) -> str:
    rows = [f"offline fingerprint of {fingerprint['save']}"]
    for name, row in fingerprint["sections"].items():
        detail = f"count={row['count']} len={row['len']} fnv={row['fnv']}" if row.get("comparable") else f"not comparable offline: {row['reason']}"
        rows.append(f"  {name:8} {comparison[name] + '  ' if comparison else ''}{detail}")
    return "\n".join(rows)
