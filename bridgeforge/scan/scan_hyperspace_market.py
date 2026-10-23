"""`market-on-hyperspace-entity` (ROADMAP 58, item 73 F1): a market attached to an entity that lives in hyperspace.

Exigency's Avesta was the first case: its market's entity sat in hyperspace, so `MarketAPI.getStarSystem()` was null and
Nexerelin's raid intel crashed on it (probe check `market-star-system` finds the market live, 2026-10-06/11). This is the
static counterpart: an entity created with `getHyperspace().addCustomEntity/addEntity` (directly or through a variable that
holds the hyperspace location) that is then given a market, by `entity.setMarket(...)` or `market.setPrimaryEntity(entity)`.

Loose sources only. A compiled-class variant (a class referencing getHyperspace, addCustomEntity, createMarket and
setPrimaryEntity together) was tried in the 316-workspace sweep and dropped: 22 of 22 jar hits were classes that build
markets in star systems and add hyperspace entities elsewhere (even Exigency's fixed Avesta), because a constant pool cannot say
which entity got the market. Decompile a jar class named by the live `market-star-system` probe check instead.
Pure functions over comment-blanked text so tests need no files.
"""
from __future__ import annotations

import re
from pathlib import Path

from ..models import ScanResult
from .scan_common import _relative
from .scan_javatext import _blank_java_comments

_HYPER_CALL = r"getHyperspace\s*\(\s*\)"
_HYPER_VAR_DECL = re.compile(r"\b(\w+)\s*=\s*[^;=]*?" + _HYPER_CALL)
_ADD_ENTITY = r"\.\s*add(?:Custom)?Entity\s*\("
_CHAINED_SET_MARKET = re.compile(_HYPER_CALL + r"\s*" + _ADD_ENTITY + r"[^;]*?\)\s*\.\s*setMarket\s*\(")


def hyperspace_market_entities(text: str) -> list[str]:
    """Names of entity variables created in hyperspace that this source also gives a market (`<chained>` for a chained call).

    `text` is comment-blanked source. Variables holding the hyperspace location are followed one step, which covers
    `LocationAPI hyper = sector.getHyperspace(); SectorEntityToken e = hyper.addCustomEntity(...)`."""
    holders = {m.group(1) for m in _HYPER_VAR_DECL.finditer(text)}
    sources = "|".join([_HYPER_CALL] + [rf"\b{re.escape(name)}\b" for name in sorted(holders)])
    entity_decl = re.compile(rf"\b(\w+)\s*=\s*(?:[\w.]+\s*\(\s*\)\s*\.\s*)*(?:{sources})\s*{_ADD_ENTITY}")
    found: list[str] = []
    for match in entity_decl.finditer(text):
        name = match.group(1)
        has_market = re.search(rf"\b{re.escape(name)}\s*\.\s*setMarket\s*\(", text) or re.search(rf"\.\s*setPrimaryEntity\s*\(\s*{re.escape(name)}\s*\)", text)
        if has_market and name not in found:
            found.append(name)
    if _CHAINED_SET_MARKET.search(text):
        found.append("<chained>")
    return found


EXPLANATION = (
    "This source creates an entity in hyperspace and gives it a market. A market whose entity is in hyperspace has no star "
    "system (MarketAPI.getStarSystem() is null): Nexerelin's raid intel crashed on it in Exigency's Avesta (ROADMAP 56/58). "
    "Put the market on an entity inside a star system. `probe-group` logs market-star-system FAIL for the live case."
)


def scan_market_on_hyperspace_entity(root: Path, result: ScanResult) -> None:
    for source in sorted(root.rglob("*.java")):
        relative = _relative(root, source)
        if "disabled_files" in Path(relative).parts:
            continue
        try:
            text = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        # Only a market registered with the economy reaches Nexerelin's raid intel: SEEKER's size-0 wreck markets (4 sweep hits) never are.
        names = hyperspace_market_entities(text) if re.search(r"\.\s*addMarket\s*\(", text) else []
        if names:
            result.add(id="market-on-hyperspace-entity", category="campaign", severity="high", classification="REVIEW", confidence="MEDIUM",
                       explanation=EXPLANATION, file=relative, evidence=[f"entity:{name}" for name in names])
