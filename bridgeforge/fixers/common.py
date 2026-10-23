from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path


SUPPORTED_FINDINGS = (
    "mod-info-game-version-inexact",
    "csv-row-extra-columns",
    "csv-missing-design-type-column",
    "procgen-planet-row-missing",
    "procgen-star-row-missing",
    "faction-known-lists-missing",
    "mod-info-triage-banner",
    "wing-data-missing-role-desc-column",
    "target-interface-method-missing",
    "removed-api-call",
    "carrier-bays-proposal",
    "revenantlib-fold-conflict",
    "undeclared-library-dependency",
    "rules-firebest-populate-options",
    "personality-id-unknown",
    "hullmod-instance-state",
    "runtime-placeholder-unsupported-operation",
    "hulk-death-effect-repeats",
    "black-hole-type-missing-flag",
    "nexerelin-corvus-mode-import",
    "spawned-ship-captain-personality-risk",
    "json-missing-comma",
    "builtin-wing-is-hullmod",
    "wing-op-cost-blank",
    "campaign-lookup-dereferenced-unguarded",
    "temporary-market-fleet-source",
    "rc8-signature-changed",
    "person-names-duplicate-row",
    "json-duplicate-key",
    "dependency-version-major-mismatch",
    "conversion-faction-names-removed-hull",
    "conversion-faction-names-missing-content",
    "conversion-vanilla-lifecycle-plugin",
    "factions-csv-relists-neutral",
    "vanilla-path-shadowing",
    "ship-data-supplies-legacy-column",
    "rules-csv-duplicate-id",
    "rules-csv-whitespace-only-line",
    "rules-csv-curly-quote-unreadable",
    "csv-vanilla-row-override",
    "faction-trait-weight-legacy-personality-id",
    "shiproles-wing-id",
    "csv-fullwidth-number",
    "ship-data-missing-fighter-bays-column",
    "missing-custom-ui-button-pressed-callback",
    "shippable-work-file",
    "data-file-not-utf8",
    "fleet-type-name-missing",
    "variant-op-over-budget",
    "procgen-mod-body-leak",
    "csv-slash-quote-escape",
    "variant-wings-exceed-bays",
    "variant-weapon-slot-mismatch",
    "variant-weapon-slot-missing",
    "hard-coded-campaign-system-reference",
    "hard-coded-campaign-entity-reference",
    "system-generation-unguarded",
    "orbit-period-computed-unguarded",
    "local-weapon-spec-unregistered",
    "content-reference-substitute",
    "preset-entry-drops-vanilla-fields",
)


class FixerError(ValueError):
    """Raised for an unsupported finding id, a missing required option, or a refusal to guess."""


@dataclass
class FileChange:
    path: Path
    before: bytes
    after: bytes
    existed_before: bool = True
    removed: bool = False  # delete `path`; a plan that also writes the same bytes elsewhere is a move

    @property
    def changed(self) -> bool:
        return self.removed or self.before != self.after


@dataclass
class FixPlan:
    finding_id: str
    mod_root: Path
    changes: list[FileChange] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Text/byte helpers shared by every fixer. All edits are surgical: only the
# located span(s) are rewritten, so unrelated bytes (line endings, comments,
# key order, BOM) survive untouched.
# ---------------------------------------------------------------------------


def _decode(raw: bytes) -> tuple[str, bool]:
    had_bom = raw.startswith(b"\xef\xbb\xbf")
    return raw.decode("utf-8-sig"), had_bom


def _encode(text: str, had_bom: bool) -> bytes:
    return (b"\xef\xbb\xbf" if had_bom else b"") + text.encode("utf-8")


_LINE_SPLIT_RE = re.compile(r"(.*?)(\r\n|\r|\n)?\Z", re.S)


def _split_terminator(line_with_ending: str) -> tuple[str, str]:
    match = _LINE_SPLIT_RE.match(line_with_ending)
    assert match is not None
    return match.group(1), match.group(2) or ""


def _line_field_spans(line: str, delimiter: str = ",") -> list[tuple[int, int, str]]:
    """(start, end, raw_text_incl_quotes) for each field of one CSV line (no embedded newlines)."""
    spans: list[tuple[int, int, str]] = []
    i = 0
    n = len(line)
    while True:
        start = i
        if i < n and line[i] == '"':
            j = i + 1
            while j < n:
                if line[j] == '"':
                    if j + 1 < n and line[j + 1] == '"':
                        j += 2
                        continue
                    j += 1
                    break
                j += 1
            end = j
        else:
            found = line.find(delimiter, i)
            end = found if found != -1 else n
        spans.append((start, end, line[start:end]))
        if end >= n or (end < n and line[end] != delimiter):
            break
        i = end + 1
    return spans


def _field_value(raw: str) -> str:
    if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
        return raw[1:-1].replace('""', '"')
    return raw


def _quote_like(raw: str, value: str) -> str:
    if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
        return '"' + value.replace('"', '""') + '"'
    return value


def _csv_escape(value: str) -> str:
    if any(ch in value for ch in ',"\n\r'):
        return '"' + value.replace('"', '""') + '"'
    return value


def _format_csv_row(fields: list[str]) -> str:
    return ",".join(_csv_escape(field_value) for field_value in fields)


def _csv_records(text: str) -> list[tuple[int, int]]:
    """(start, end) char spans for each logical CSV record, quote-aware across embedded newlines."""
    records: list[tuple[int, int]] = []
    start = 0
    in_quotes = False
    n = len(text)
    for index, char in enumerate(text):
        if char == '"':
            in_quotes = not in_quotes
        elif char == "\n" and not in_quotes:
            records.append((start, index + 1))
            start = index + 1
    if start < n:
        records.append((start, n))
    return records


def _parse_rgb(text: str) -> list[int]:
    parts = text.split(",")
    if len(parts) != 3:
        raise FixerError("--design-color must be R,G,B.")
    try:
        values = [int(part.strip()) for part in parts]
    except ValueError as exc:
        raise FixerError(f"--design-color must be three integers: {exc}") from exc
    if any(not 0 <= value <= 255 for value in values):
        raise FixerError("--design-color values must each be 0-255.")
    return values


def _findings_of(root: Path, options: dict, finding_id: str) -> list:
    """This finding id's findings: the caller's own scan when it passes one (`options["scan_findings"]`,
    Finding objects or their dicts, as `revive` does, so a fixer run doesn't rescan the whole mod),
    else a fresh scan. Only the files and evidence are read, so either source gives the same edit.
    """
    supplied = options.get("scan_findings")
    if supplied is None:
        from bridgeforge.scan.scanner import scan_mod

        return [f for f in scan_mod(root, vanilla_core=options.get("vanilla_core")).findings if f.id == finding_id]
    from types import SimpleNamespace

    found = [SimpleNamespace(**f) if isinstance(f, dict) else f for f in supplied]
    return [f for f in found if f.id == finding_id]


def _relative_path(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)
