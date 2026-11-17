from __future__ import annotations
import codecs
import json
import threading
from pathlib import Path
from .common import FileChange, FixerError
from bridgeforge.zipsafe import read_limited


_REFERENCE_SUFFIXES = {".json", ".csv", ".java", ".kt", ".faction", ".ship", ".skin", ".variant", ".wpn", ".proj",
                       ".system", ".wing", ".ini", ".txt", ".xml", ".properties"}


def _referencing_bytes(root: Path, skip: set[str]) -> bytes:
    """Lower-cased text of every file that could name another file at runtime, jar members included."""
    import zipfile

    parts = []
    from ..copy_drift import _is_excluded

    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        # IDE/VCS folders (.idea, .git, src*...) never ship and the game never reads them; a mention there
        # is not a runtime reference (Jackundor's .idea/libraries/data.xml named its backup zips, 2026-09-27).
        if not path.is_file() or relative in skip or _is_excluded(relative):
            continue
        suffix = path.suffix.lower()
        # A root readme or changelog is for people, never read by the game (Hiver Swarm's README named its
        # "Replacement Ships.rar", which kept the archive shipping; ROADMAP 34.18, 2026-10-04).
        if "/" not in relative and suffix in {".txt", ".md"}:
            continue
        try:
            if suffix in _REFERENCE_SUFFIXES and path.stat().st_size <= 8 * 1024 * 1024:
                parts.append(path.read_bytes().lower())
            elif suffix == ".jar":
                with zipfile.ZipFile(path) as jar:
                    parts.extend(read_limited(jar, info, 8 * 1024 * 1024).lower() for info in jar.infolist() if not info.is_dir() and info.file_size <= 8 * 1024 * 1024)
        except (OSError, zipfile.BadZipFile):
            continue
    return b"\n".join(parts)


# CP-1252's typographic bytes: curly quotes, en/em dash, ellipsis, no-break space. Mac Roman reads the
# same bytes as accented letters (0x92 = í, 0x93 = ì) and Shift-JIS/GBK need two high bytes, so an
# isolated one of these between ASCII bytes has one plausible reading. Surveyed 2026-09-27 over the
# queue's 44 non-UTF-8 data files: 30 meet this; the rest carry Mac Roman (DME's 0xD5 for ’), Shift-JIS
# (Stinger-Shipyards' 0x81 0x66) or accented letters, whose encoding a person must name.
_CP1252_TYPOGRAPHY = frozenset({0x85, 0x91, 0x92, 0x93, 0x94, 0x96, 0x97, 0xA0})


# One decode with an error handler that records each undecodable byte and resumes one byte past it. That is where the old
# loop resumed, so the offsets are the same. The old loop re-decoded the rest of the file after every bad byte: quadratic, and
# a large CP-1252 rules.csv took 24-38 s (ROADMAP-3 96.5 P6). The list is thread-local, because the handler is global.
_OFFSET_HANDLER = "bridgeforge-invalid-utf8-offsets"
_collected = threading.local()


def _record_invalid_byte(exc: UnicodeError) -> tuple[str, int]:
    _collected.offsets.append(exc.start)
    return "", exc.start + 1


codecs.register_error(_OFFSET_HANDLER, _record_invalid_byte)


def _invalid_utf8_offsets(raw: bytes) -> list[int]:
    """Offsets of the bytes UTF-8 cannot decode, each found where decoding resumes one byte past the previous one."""
    _collected.offsets = []
    raw.decode("utf-8", _OFFSET_HANDLER)
    offsets, _collected.offsets = _collected.offsets, []
    return offsets


def _fix_data_file_not_utf8(root: Path, options: dict) -> list[FileChange]:
    """Re-encode data files whose only non-UTF-8 bytes are isolated CP-1252 punctuation (P15 item 15).

    Valid UTF-8 already in the file is kept byte for byte; each invalid byte becomes its CP-1252
    character in UTF-8. A file with any other invalid byte is refused with the bytes it holds, because
    its real encoding (Mac Roman, Shift-JIS, GBK, CP-1252 letters) cannot be told from the bytes alone.
    """
    from bridgeforge.scan.scanner import _PLAYER_TEXT_SUFFIXES

    data = root / "data"
    paths = [root / "mod_info.json"] + ([p for p in data.rglob("*") if p.suffix.lower() in _PLAYER_TEXT_SUFFIXES] if data.is_dir() else [])
    changes, refused = [], []
    named_encodings = dict(options.get("encodings") or {})
    for relative, encoding in named_encodings.items():
        if encoding not in _NAMEABLE_ENCODINGS:
            raise FixerError(f"{relative}: encoding {encoding!r} is not one of {', '.join(sorted(_NAMEABLE_ENCODINGS))}.")
    for path in sorted(p for p in paths if p.is_file()):
        raw = path.read_bytes()
        offsets = _invalid_utf8_offsets(raw)
        if not offsets:
            continue
        invalid = set(offsets)

        def plain(index: int) -> bool:
            return index < 0 or index >= len(raw) or raw[index] < 0x80 or index in invalid

        relative = path.relative_to(root).as_posix()
        named = named_encodings.pop(relative, None)
        if named is not None:
            changes.append(FileChange(path=path, before=raw, after=_reencode_invalid(raw, offsets, named, relative)))
            continue
        # « » (0xAB/0xBB) count as typography only in matched pairs: as quotes they open and close, while the same bytes are
        # unrelated letters elsewhere (Shift-JIS half-width katakana, Mac Roman). Musashi Manufactorum's descriptions.csv held
        # only NBSP and three «...» pairs, and was refused (ROADMAP-3 item 92.19, 2026-11-16).
        allowed = set(_CP1252_TYPOGRAPHY)
        if sum(raw[i] == 0xAB for i in offsets) == sum(raw[i] == 0xBB for i in offsets):
            allowed |= {0xAB, 0xBB}
        if not all(raw[i] in allowed and plain(i - 1) and plain(i + 1) for i in offsets):
            odd = sorted({f"0x{raw[i]:02x}" for i in offsets if raw[i] not in allowed})
            refused.append(f"{path.relative_to(root).as_posix()} ({', '.join(odd) or 'adjacent high bytes'})")
            continue
        out, last = bytearray(), 0
        for i in offsets:
            out += raw[last:i] + bytes([raw[i]]).decode("cp1252").encode("utf-8")
            last = i + 1
        out += raw[last:]
        changes.append(FileChange(path=path, before=raw, after=bytes(out)))
    if named_encodings:
        raise FixerError(f"No invalid UTF-8 to re-encode in: {', '.join(sorted(named_encodings))}.")
    if not changes and refused:
        raise FixerError("No file has only CP-1252 punctuation outside UTF-8; name the real encoding by hand for: " + "; ".join(refused)
                         + " (fix --encoding FILE=ENCODING)")
    if refused:
        # Some files converted, others not: the caller (revive) reports these as still pending (ROADMAP P15 20.5).
        options.setdefault("partial_refusals", []).append("Not converted; name the real encoding by hand for: " + "; ".join(refused)
                                                          + " (fix --encoding FILE=ENCODING)")
    return changes


NAMED_ENCODINGS_FILE = "NAMED_ENCODINGS.json"


def _named_encodings_path(mod_dir: Path) -> Path | None:
    """<workspace>/NAMED_ENCODINGS.json when mod_dir is a workspace's working/ (ROADMAP P15 item 20.4)."""
    mod_dir = Path(mod_dir).resolve()
    return mod_dir.parent / NAMED_ENCODINGS_FILE if mod_dir.name == "working" else None


def record_named_encodings(mod_dir: Path, encodings: dict[str, str]) -> Path | None:
    """Keep a person's `fix --encoding FILE=ENC` decisions in the workspace, so a fresh copy from original/ (and revive) can reapply them."""
    path = _named_encodings_path(mod_dir)
    if path is None or not encodings:
        return None
    known = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    known.update({name.replace("\\", "/"): encoding for name, encoding in encodings.items()})
    path.write_text(json.dumps(dict(sorted(known.items())), indent=2) + "\n", encoding="utf-8")
    return path


def pending_named_encodings(mod_dir: Path) -> dict[str, str]:
    """Recorded encodings whose file is still not valid UTF-8 (already converted files are left out)."""
    path = _named_encodings_path(mod_dir)
    if path is None or not path.is_file():
        return {}
    pending = {}
    for name, encoding in json.loads(path.read_text(encoding="utf-8")).items():
        target = Path(mod_dir) / name
        try:
            target.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            pending[name] = encoding
        except OSError:
            continue
    return pending


# Encodings a person may name for data-file-not-utf8 (`fix --encoding FILE=ENC`), each seen in the queue
# 2026-09-27: CP-1252 letters (Thule-Legacy, Epta-Consortium), Mac Roman (DME), Shift-JIS (Stinger-Shipyards).
_NAMEABLE_ENCODINGS = frozenset({"cp1252", "mac_roman", "shift_jis", "gbk", "gb18030", "latin-1"})


def _reencode_invalid(raw: bytes, offsets: list[int], encoding: str, relative: str) -> bytes:
    """Decode only the invalid bytes (a lead byte takes its trail byte with it in a two-byte encoding)
    with the encoding a person named; bytes that are already valid UTF-8 stay as they are."""
    out, last = bytearray(), 0
    for i in offsets:
        if i < last:
            continue  # consumed as a trail byte
        for width in (1, 2):
            try:
                text = raw[i:i + width].decode(encoding)
            except UnicodeDecodeError:
                continue
            if len(text) == 1:
                break
        else:
            raise FixerError(f"{relative}: byte 0x{raw[i]:02x} at offset {i} does not decode as {encoding}.")
        out += raw[last:i] + text.encode("utf-8")
        last = i + width
    return bytes(out + raw[last:])


def _fix_fullwidth_punctuation(root: Path, options: dict) -> list[FileChange]:
    """fullwidth-punctuation-in-text: full-width punctuation in English player text made ASCII, line by line, with the same rule
    the check uses (`scan_text.fullwidth_punctuation_fixed`); lines still holding other CJK are left to translation. Line
    endings and a BOM are kept (ROADMAP-3 item 92.32)."""
    from bridgeforge.scan.scan_text import fullwidth_punctuation_files, fullwidth_punctuation_fixed

    changes = []
    for path in fullwidth_punctuation_files(root):
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            continue  # data-file-not-utf8 first
        lines = text.splitlines(keepends=True)
        changed = False
        for index, line in enumerate(lines):
            body = line.rstrip("\r\n")
            fixed = fullwidth_punctuation_fixed(body)
            if fixed is not None:
                lines[index] = fixed + line[len(body):]
                changed = True
        if changed:
            bom = b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b""
            changes.append(FileChange(path=path, before=raw, after=bom + "".join(lines).encode("utf-8")))
    if not changes:
        raise FixerError("No English player text with full-width punctuation found.")
    return changes
