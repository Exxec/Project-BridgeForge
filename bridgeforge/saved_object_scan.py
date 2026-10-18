"""`saved-object-holds-market-ref` (ROADMAP 60g(4)): a class the game saves that keeps a campaign entity in a plain field.

Starsector saves with XStream: whatever is stored in a memory, in `customData`, or registered as a listener or script is written
into the save with every non-transient field. A stored object that keeps a `MarketAPI`, `SectorEntityToken`, `PlanetAPI` or
`CampaignFleetAPI` therefore ties the save graph to that entity. The reported case is Station Augments in the Modpack 6.3 save: a
market memory held a planet while an augment held that market, and the load failed after c212 with a NullPointerException in
`PlanetConditionMarket.readResolve` (60g(3); the cycle itself is read from the save by `save-doctor`). This check finds the code
pattern, not the failure: it is REVIEW, and a reference kept in a `transient` field, or re-found by id when needed, is the usual fix.

Loose `.java` sources are read by the storing-site analysis below; jar classes (item 73 F2) are judged only by interface and field
(see `saved_interface`). Pure functions over source text so tests need no files.
"""
from __future__ import annotations

import re

ENTITY_TYPES = ("MarketAPI", "SectorEntityToken", "PlanetAPI", "CampaignFleetAPI")
_ENTITY = re.compile(r"\b(" + "|".join(ENTITY_TYPES) + r")\b")
_STORE = re.compile(r"getMemory(?:WithoutUpdate)?\s*\(\s*\)\s*\.\s*set\s*\(|\bcustomData\s*\.\s*put\s*\(|getCustomData\s*\(\s*\)\s*\.\s*put\s*\(")
_MEMORY_VAR_SET = re.compile(r"\b(\w+)\s*\.\s*set\s*\(")
_REGISTER = re.compile(r"\.\s*(addListener|addScript|addEveryFrameScript)\s*\(")
_NEW = re.compile(r"\bnew\s+(\w+)\s*(?:<[^>]*>)?\s*\(")
_DECL = re.compile(r"\b([A-Z]\w*)(?:<[^<>;=()]*>)?\s+(\w+)\s*(?:=|;|,|\))")
_CLASS = re.compile(r"\b(?:class|interface)\s+(\w+)")
_MODIFIERS = {"public", "protected", "private", "static", "final", "transient", "volatile"}


def _braced(text: str, open_index: int) -> int:
    """Index just past the brace block that opens at `open_index`."""
    depth, i = 0, open_index
    while i < len(text):
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        i += 1
        if depth == 0:
            break
    return i


def class_spans(text: str) -> list[tuple[str, int, int]]:
    """(name, body start, body end) for each class declared in `text`, nested ones included."""
    spans = []
    for match in _CLASS.finditer(text):
        opening = text.find("{", match.end())
        semicolon = text.find(";", match.end())
        if opening != -1 and (semicolon == -1 or opening < semicolon):
            spans.append((match.group(1), opening, _braced(text, opening)))
    return spans


def _top_level(body: str) -> str:
    """A class body with every nested brace block replaced by ';', so what is left are its member declarations."""
    out, depth = [], 0
    for char in body:
        if char == "{":
            if depth == 0:
                out.append(";")
            depth += 1
        elif char == "}":
            depth -= 1
        elif depth == 0:
            out.append(char)
    return "".join(out)


def entity_fields(text: str, start: int, end: int) -> list[str]:
    """['MarketAPI market', ...] for the non-transient, non-static entity fields declared directly in the class body text[start:end]."""
    found = []
    for piece in _top_level(text[start + 1:end - 1]).split(";"):
        declaration = piece.split("=", 1)[0].strip()
        if "(" in declaration or not declaration:
            continue
        words = declaration.replace(",", " ").split()
        modifiers = {w for w in words if w in _MODIFIERS}
        if modifiers & {"transient", "static"}:
            continue
        rest = [w for w in words if w not in _MODIFIERS]
        type_part, name = " ".join(rest[:-1]), rest[-1] if rest else ""
        if name and _ENTITY.search(type_part):
            found.append(f"{type_part} {name}")
    return found


def _enclosing(spans: list[tuple[str, int, int]], offset: int) -> str | None:
    inside = [s for s in spans if s[1] < offset < s[2]]
    return min(inside, key=lambda s: s[2] - s[1])[0] if inside else None


def stored_classes(text: str) -> dict[str, str]:
    """{class name: how it is saved} for classes this source puts in a memory, in customData, or registers as a listener/script."""
    spans = class_spans(text)
    variables = {name: kind for kind, name in _DECL.findall(text)}
    memory_vars = {name for kind, name in _DECL.findall(text) if kind == "MemoryAPI"}
    found: dict[str, str] = {}
    offset = 0
    for statement in text.split(";"):
        position = offset + len(statement) - len(statement.lstrip())
        offset += len(statement) + 1
        via_var = next((m for m in _MEMORY_VAR_SET.finditer(statement) if m.group(1) in memory_vars), None)
        register = _REGISTER.search(statement)
        if _STORE.search(statement) or via_var:
            how = "stored in a memory or customData"
        elif register:
            how = f"registered with {register.group(1)}"
        else:
            continue
        names = set(_NEW.findall(statement))
        names |= {variables[w] for w in re.findall(r"\b[a-z_]\w*\b", statement) if w in variables}
        if re.search(r"[(,]\s*this\s*[,)]", statement):
            owner = _enclosing(spans, position)
            if owner:
                names.add(owner)
        for name in names:
            found.setdefault(name, how)
    return found


def saved_object_findings(sources: dict[str, str]) -> list[dict]:
    """[{file, class, how, fields}] over {relative path: comment-blanked source}: stored classes that keep entity fields."""
    stored: dict[str, str] = {}
    for text in sources.values():
        for name, how in stored_classes(text).items():
            stored.setdefault(name, how)
    findings = []
    for path, text in sorted(sources.items()):
        for name, begin, end in class_spans(text):
            if name in stored:
                fields = entity_fields(text, begin, end)
                if fields:
                    findings.append({"file": path, "class": name, "how": stored[name], "fields": fields})
    return findings


# Compiled classes (item 73 F2). A jar class cannot show where it is stored, so only a class that implements a campaign
# interface the game saves and runs by registration (EveryFrameScript, the campaign listener interfaces) is judged.
_ENTITY_DESCRIPTOR = re.compile(r"^L[\w/$]+/(" + "|".join(ENTITY_TYPES) + r");$")
_SAVED_INTERFACE_PREFIXES = ("com/fs/starfarer/api/campaign/listeners/",)
_SAVED_INTERFACES = frozenset({"com/fs/starfarer/api/EveryFrameScript", "com/fs/starfarer/api/campaign/CampaignEventListener",
                               "com/fs/starfarer/api/campaign/FleetEventListener"})


def saved_interface(interfaces: list[str]) -> str | None:
    """The first implemented interface that makes a class a saved, registered campaign object, or None."""
    for name in interfaces:
        if name in _SAVED_INTERFACES or name.startswith(_SAVED_INTERFACE_PREFIXES):
            return name.rsplit("/", 1)[-1]
    return None


def compiled_entity_fields(fields: list[tuple[str, str, bool, bool]], transient: frozenset[str]) -> list[str]:
    """['MarketAPI market', ...] for the non-static, non-transient fields whose type is a campaign entity (generic element types are
    erased in the descriptor and not seen). Empty unless one of them is a MarketAPI or PlanetAPI: the first sweep (160 hits in 38
    of 316 workspaces) was mostly fleet AIs and scripts holding their own fleet or a token, which is not the market/planet reference
    cycle of the Station Augments save."""
    found = []
    for name, descriptor, is_static, _ in fields:
        match = _ENTITY_DESCRIPTOR.match(descriptor)
        if match and not is_static and name not in transient:
            found.append(f"{match.group(1)} {name}")
    return found if any(f.startswith(("MarketAPI ", "PlanetAPI ")) for f in found) else []
