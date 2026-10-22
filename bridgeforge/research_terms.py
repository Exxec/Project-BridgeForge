"""Feature terms and evidence labels for `research report` (ROADMAP-3 item 82).

A FEATURE is one or more search terms separated by commas: class names, rule ids, csv ids, strings. `*` matches any run of
identifier characters (`player_*`). A term with a file extension (`commands.csv`) also names a file: it matches that file's name
and, for the data readers, the ids that file defines or references. Matching is case-insensitive substring matching.

Evidence labels (82 guiding rule: nothing is upgraded on the way through):
  STATIC     read from files, bytecode, an index or a record; says what code and data contain, not what the game does.
  OBSERVED   seen in a recorded live run or captured baseline (a fact about that run only).
  VALIDATED  a gate in gates.json that is PASS with evidence, within that gate's declared scope.
A claim keeps the label of its weakest source; `weakest` is the only way labels combine.
"""
from __future__ import annotations

import re
from typing import Iterable

STATIC, OBSERVED, VALIDATED = "STATIC", "OBSERVED", "VALIDATED"
LABEL_ORDER = (STATIC, OBSERVED, VALIDATED)
_FILE_TERM = re.compile(r"\.[A-Za-z0-9]{2,5}\Z")


def parse_terms(text: str) -> tuple[str, ...]:
    """The distinct, non-empty comma separated terms of `text`, in the order given."""
    return tuple(dict.fromkeys(part.strip() for part in text.split(",") if part.strip()))


def weakest(labels: Iterable[str]) -> str:
    """The weakest label of `labels` (STATIC when empty): a claim built from several sources is only as strong as the weakest."""
    ranks = [LABEL_ORDER.index(label) for label in labels if label in LABEL_ORDER]
    return LABEL_ORDER[min(ranks)] if ranks else STATIC


def is_file_term(term: str) -> bool:
    return bool(_FILE_TERM.search(term))


def term_pattern(term: str) -> re.Pattern[str]:
    """Plain terms are substrings; a term with `*` must start at the beginning of an identifier (`player_*` skips `battle_player_x`)."""
    parts = [re.escape(part) for part in term.split("*")]
    anchor = r"(?<!\w)" if "*" in term else ""
    return re.compile(anchor + r"\w*".join(parts), re.IGNORECASE)


class Matcher:
    """Tests names, file names and text against a set of terms."""

    def __init__(self, terms: tuple[str, ...]) -> None:
        self.terms = terms
        self._patterns = {term: term_pattern(term) for term in terms}

    def name_hits(self, name: str) -> list[str]:
        """Terms whose pattern occurs in `name`."""
        return [term for term, pattern in self._patterns.items() if pattern.search(name)]

    def file_hits(self, path: str) -> list[str]:
        """File terms (`commands.csv`) equal to the file name of `path` (case-insensitive)."""
        base = path.replace("\\", "/").rsplit("/", 1)[-1].lower()
        return [term for term in self.terms if is_file_term(term) and "*" not in term and term.lower() == base]

    def text_hits(self, text: str) -> list[str]:
        return self.name_hits(text)

    def any_name(self, *names: str) -> list[str]:
        found: dict[str, None] = {}
        for name in names:
            found.update(dict.fromkeys(self.name_hits(name)))
        return list(found)


FILE_EXTENSIONS = frozenset("png jpg jpeg ogg wav csv json java class ship wpn variant skin faction ini txt jar system md kt".split())


def concept_key(name: str) -> str:
    """Normal form used to line two indexes up: the last dotted segment of a class-like name, lower case, no `#` prefix."""
    text = name.strip().lstrip("#").strip()
    stem, _, extension = text.rpartition(".")
    if extension.lower() in FILE_EXTENSIONS and stem:
        # the archaeology graph names a file reference like a class (`graphics.x.y.png`); Atlas keeps the path (`graphics/x/y.png`)
        return (stem.replace("\\", "/").replace(".", "/") + "." + extension).lower()
    if "/" in text or " " in text:
        return text.replace("\\", "/").lower()
    return text.rsplit(".", 1)[-1].lower() if "." in text else text.lower()
