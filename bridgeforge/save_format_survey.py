"""`bridgeforge save-format-survey`: a neutral, read-only survey of where a save keeps the player's fleet cargo
and credits (ROADMAP item 59; groundwork for VoidSmith's Save Workshop slice S0).

VoidSmith's parser gate wants a documented format description with version boundaries before it parses a save.
This reads real saves and reports structure only: the game version the descriptor names, the player fleet's
element, the attributes on its cargo container (capacity and space-used figures), how many resource stacks it
holds, and whether a credits value is present. It never records a player-chosen name, a quantity or the credits
amount: the survey is meant to be shared with another project.

Read-only on saves. Uses `save_reader.iter_elements`, which relies on Starsector's one-tag-per-line XML (see that
module). Pass 1 finds the `playerFleet` reference; pass 2 collects that fleet's subtree; a cargo that is itself a
reference (`ref=`) costs one more pass to resolve.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from .save_reader import campaign_xml_path, iter_elements, parse_descriptor, resolve_save_dir

_CARGO_RESOURCE_TAG = "CIStack"


def _subtree(campaign_xml: Path, z: str) -> list:
    """Every element below (and including) the first element whose `z` attribute is `z`."""
    collected: list = []
    depth: int | None = None
    for element in iter_elements(campaign_xml):
        if depth is None:
            if element.attrs.get("z") == z:
                depth = len(element.path)
                collected.append(element)
            continue
        if len(element.path) <= depth:
            break          # a sibling or an ancestor's next child: the subtree has ended
        collected.append(element)
    return collected


def _survey_cargo(elements: list) -> dict[str, object]:
    """Structure of one cargo container's subtree; never a quantity, name or credit amount."""
    cargo = elements[0]
    stacks: Counter[str] = Counter()
    has_credits = False
    base = len(cargo.path)
    for element in elements[1:]:
        relative = element.path[base:]
        if element.tag == _CARGO_RESOURCE_TAG:
            stacks[element.attrs.get("t", "?")] += 1
        if relative[:2] == ("c", "value") or (element.tag == "value" and relative[:1] == ("c",)):
            has_credits = True
    return {
        "attribute_names": sorted(cargo.attrs),
        "stack_types": dict(sorted(stacks.items())),
        "credits_value_present": has_credits,
    }


def survey_save(save: Path | str) -> dict[str, object]:
    folder = resolve_save_dir(save)
    campaign = campaign_xml_path(folder)
    descriptor = parse_descriptor(folder)
    result: dict[str, object] = {
        "game_version": descriptor.get("game_version") or descriptor.get("gameVersion"),
        "campaign_xml_bytes": campaign.stat().st_size,
        "player_fleet": None,
        "cargo": None,
        "notes": [],
    }
    notes: list[str] = result["notes"]  # type: ignore[assignment]

    player_ref = None
    for element in iter_elements(campaign):
        if element.tag == "playerFleet" and "ref" in element.attrs:
            player_ref = element.attrs["ref"]
            break
    if player_ref is None:
        notes.append("no playerFleet reference found")
        return result

    fleet = _subtree(campaign, player_ref)
    if not fleet:
        notes.append("playerFleet reference did not resolve to an element")
        return result
    result["player_fleet"] = {"tag": fleet[0].tag, "child_elements": len(fleet) - 1}

    cargo_index = next((i for i, element in enumerate(fleet) if element.tag == "cargo"), None)
    if cargo_index is None:
        notes.append("no cargo element inside the player fleet subtree")
        return result
    cargo_head = fleet[cargo_index]
    if "ref" in cargo_head.attrs and "z" not in cargo_head.attrs:
        resolved = _subtree(campaign, cargo_head.attrs["ref"])
        if not resolved:
            notes.append("the cargo reference did not resolve")
            return result
        notes.append("cargo reached by reference")
        cargo_elements = resolved
    else:
        cargo_elements = _subtree(campaign, cargo_head.attrs["z"]) if "z" in cargo_head.attrs else [cargo_head]
    result["cargo"] = _survey_cargo(cargo_elements)
    return result


def survey_saves(saves: list[Path | str]) -> dict[str, object]:
    """Survey each save and compare: which cargo attribute names and stack types every save shares."""
    surveys = []
    for save in saves:
        try:
            surveys.append({"status": "OK", **survey_save(save)})
        except (ValueError, OSError) as exc:
            surveys.append({"status": "ERROR", "error": str(exc)})
    ok = [s for s in surveys if s["status"] == "OK" and s.get("cargo")]
    attribute_sets = [frozenset(s["cargo"]["attribute_names"]) for s in ok]
    common = sorted(frozenset.intersection(*attribute_sets)) if attribute_sets else []
    by_version: dict[str, int] = Counter(str(s.get("game_version")) for s in surveys if s["status"] == "OK")
    return {
        "schema_version": 1,
        "saves_surveyed": len(surveys),
        "saves_with_player_cargo": len(ok),
        "game_versions": dict(sorted(by_version.items())),
        "cargo_attributes_in_every_save": common,
        "credits_value_present_in_every_save": bool(ok) and all(s["cargo"]["credits_value_present"] for s in ok),
        "surveys": surveys,
    }
