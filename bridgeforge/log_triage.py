from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .jar_audit import _resolve_jar_classes
from .scanner import _load_lenient_json_file, _loaded_mod_jars

DEFAULT_MOD_PREFIXES = ("data.scripts", "exigency")

# Vanilla/library namespaces a stack frame's class may live in even when it appears inside a mod's
# jar (e.g. a bundled org.json copy); these are never attributed to a mod.
VANILLA_FRAME_PREFIXES = ("com.fs.", "java.", "sun.", "org.lwjgl.", "org.json.")

_FRAME_CLASS_RE = re.compile(r"^\s*at\s+(?P<qualified>[\w.$]+)\(")

LINE_RE = re.compile(r"^(?P<millis>\d+)\s+\[(?P<thread>[^\]]*)\]\s+(?P<level>INFO|WARN|ERROR|DEBUG|FATAL)\s+(?P<logger>\S+)\s+-\s+(?P<message>.*)$")

# Lines/stack traces that end the game outright.
FATAL_PATTERNS = (
    # Live run SK13-1d: setPersonality() with an id RC8 does not define (0.6.x's "suicidal"/"fearless")
    # leaves the officer's personality null; the ship AI then NPEs on deploy (scanner: personality-id-unknown).
    ("Null officer personality (unknown personality id)", re.compile(r'rpg\.Person\.getPersonality\(\)" is null')),
    ("Fatal error dialog", re.compile(r"\bFatal:")),
    ("SecurityException", re.compile(r"java\.lang\.SecurityException")),
    ("Spec not found", re.compile(r"RuntimeException: Spec of class \[.+?\] with id \[.+?\] not found")),
    # Loose scripts (missions, data/**/*.java) are compiled at runtime by Janino; a failure there is
    # a Fatal dialog before the main menu (live bug PRB-MISSION-02), logged only as these two lines.
    ("Janino script compile error", re.compile(r"org\.codehaus\.commons\.compiler\.CompileException")),
    ("Script class load error", re.compile(r"RuntimeException: Error loading \[[\w.$]+\]")),
    ("NoClassDefFoundError", re.compile(r"NoClassDefFoundError")),
    ("AbstractMethodError", re.compile(r"AbstractMethodError")),
    ("NoSuchMethodError", re.compile(r"NoSuchMethodError")),
    ("ClassCastException", re.compile(r"ClassCastException")),
    ("XStream conversion error", re.compile(r"CannotResolveClassException|com\.thoughtworks\.xstream\.[\w.]*ConversionException")),
)

# Known-benign noise observed across a week of live RC8 testing; each carries a one-line reason
# so a triage report explains itself instead of just suppressing lines.
KNOWN_NOISE = (
    ("Ship hull spec [flare] not found", re.compile(r"Ship hull spec \[flare\] not found"), "Cosmetic vanilla-shadowed hull spreadsheet lookup miss; non-fatal."),
    ("module_hightech_decor hull spec", re.compile(re.escape("[module_hightech_decor]")), "Known vanilla-file-shadowing hull id miss; non-fatal."),
    ("LunaLib setting missing", re.compile(r"LunaSettings: Value .* not found in JSONObject"), "LunaLib settings key absent from a mod's modSettings.json; falls back to a default."),
    ("Music source AL error", re.compile(r"Error initializing music source - AL error"), "OpenAL device/driver hiccup starting a music source; playback recovers, non-fatal."),
    ("Version-checker master file", re.compile(r"Failed to load master version file"), "Version-checker network/URL failure reaching an update endpoint; no gameplay effect."),
    ("Version-checker malformed URL", re.compile(r"MalformedURLException"), "Version-checker malformed update URL; non-fatal network-check failure."),
    ("Nexerelin quest-skip JSON", re.compile(r"QuestChainSkipEntry"), "Nexerelin quest-skip list JSON parse hiccup; known non-fatal first-run/format issue."),
    ("Nexerelin first-run setup", re.compile(r"ExerelinSetupData"), "Nexerelin first-run setup-data initialization notice; non-fatal."),
    ("MagicLib subsystemInfoKey", re.compile(r"subsystemInfoKey"), "MagicLib subsystem settings key type warning; falls back to a default, non-fatal."),
    ("Vanilla lightmortar_fighter row", re.compile(r"Weapon \[lightmortar_fighter\] from weapon_data\.csv not found in store"), "RC8's own weapon_data.csv keeps a '#'-named Light Mortar (Fighter) row with no .wpn file; logged every run, no effect."),
)

SPEC_STORE_SHIP_SYSTEM_RE = re.compile(r"Ship system \[(?P<system>[^\]]+)\] from (?P<csv>\S+\.csv) not found in store")
MAIN_MENU_RE = re.compile(r"Playing music with id \[miscallenous_main_menu\.ogg\]")
FINISHED_SAVING_RE = re.compile(r"Finished saving")
# The real load line is "CampaignGameManager - Loading ..\saves/save_X..." (then "Loading stage N").
# "Reading save data from [...descriptor.xml]" is NOT a load: RC8 logs it for every save whenever the
# Load menu lists them.
# The path may be absolute and contain spaces (e.g. "...\Project BridgeForge\In operation\...\saves\save_X");
# the save folder name itself never does. Requiring "saves" + a separator keeps "Loading stage N",
# "Loading rule:" and "Loading saved variants for mission" out.
CAMPAIGN_LOAD_RE = re.compile(r"^Loading (?P<path>.*?saves[\\/]\S+?)(?:\.\.\.)?\s*$")
# Not a progress milestone: RC8 logs this for EVERY mission during startup preloading (24+ lines on a
# plain boot), so it says nothing about whether a mission was actually played.
MISSION_PRELOAD_RE = re.compile(r"Loading saved variants for mission (?P<mission>\S+)")

# BF-PROBE|<version>|<check>|<status>|<subject>|<detail>, emitted by the bridgeforge-probe mod
# (roadmap P3) via Global.getLogger(...).info(...); always at log4j level INFO regardless of the
# probe's own OK/FAIL/WARN/INFO status, so it is matched against every line's message, not just
# ERROR/WARN/FATAL ones.
PROBE_LINE_RE = re.compile(
    r"^BF-PROBE\|(?P<version>[^|]*)\|(?P<check>[^|]*)\|(?P<status>[^|]*)\|(?P<subject>[^|]*)\|(?P<detail>.*)$"
)
PROBE_STATUSES = ("OK", "FAIL", "WARN", "INFO")

FATAL_ABSENCE_CAVEAT = (
    "A Java Fatal Error can surface only as a modal dialog and never reach a redirected stdout log; "
    "absence of a FATAL classification here is not proof the run succeeded unless a milestone "
    "(main menu reached, a campaign load, or a save) confirms the process actually progressed."
)


@dataclass
class _Event:
    line_no: int
    level: str
    logger: str
    head_message: str
    frames: list[str] = field(default_factory=list)

    @property
    def haystack(self) -> str:
        return self.head_message + "\n" + "\n".join(self.frames)


_STACK_FRAME_RE = re.compile(r"^\s*at\s")


def _first_mod_frame(event: _Event, mod_prefixes: tuple[str, ...]) -> str | None:
    # Prefer an actual "\tat ..." stack frame over exception message text, so an exception whose
    # message happens to mention a mod id (e.g. "...with id [exigency_planetoid] not found") still
    # surfaces the real offending frame (e.g. "at data.scripts.world.exigency.Tasserus.generate").
    stack_frames = [line for line in event.frames if _STACK_FRAME_RE.match(line)]
    for line in (*stack_frames, *event.frames, event.head_message):
        for prefix in mod_prefixes:
            if prefix in line:
                return line.strip()
    return None


def _classify_event(event: _Event, mod_prefixes: tuple[str, ...]) -> dict[str, object]:
    for label, pattern, reason in KNOWN_NOISE:
        if pattern.search(event.haystack):
            return {"category": "KNOWN-NOISE", "known_noise_rule": label, "reason": reason}
    for label, pattern in FATAL_PATTERNS:
        if pattern.search(event.haystack):
            return {"category": "FATAL", "matched_rule": label}
    # An exception escaping the combat loop is a Fatal dialog (live run SK13-1: SEEKER's
    # ART_thrusterRotation NPE). The logger/level live outside `haystack`, so check them directly.
    if event.level == "ERROR" and event.logger.endswith("combat.CombatMain") and re.match(r"java\.lang\.\w+(?:Exception|Error)\b", event.head_message.strip()):
        return {"category": "FATAL", "matched_rule": "Combat loop exception"}
    if _first_mod_frame(event, mod_prefixes) is not None:
        return {"category": "MOD-ERROR"}
    return {"category": "OTHER"}


def _iter_events_and_milestones(
    lines: list[str],
) -> tuple[list[_Event], dict[str, object], list[dict[str, object]], list[dict[str, object]]]:
    events: list[_Event] = []
    milestones = {"main_menu_reached": False, "finished_saving_count": 0, "campaign_loads": [], "mission_variant_preloads": []}
    shadow_symptoms: list[dict[str, object]] = []
    probe_entries: list[dict[str, object]] = []
    current: _Event | None = None
    for line_no, raw in enumerate(lines, start=1):
        line = raw.rstrip("\n")
        match = LINE_RE.match(line)
        if match is not None:
            if current is not None:
                events.append(current)
                current = None
            level = match.group("level")
            message = match.group("message")
            if MAIN_MENU_RE.search(message):
                milestones["main_menu_reached"] = True
            if FINISHED_SAVING_RE.search(message):
                milestones["finished_saving_count"] += 1
            campaign = CAMPAIGN_LOAD_RE.search(message)
            if campaign is not None:
                milestones["campaign_loads"].append(campaign.group("path"))
            mission = MISSION_PRELOAD_RE.search(message)
            if mission is not None:
                milestones["mission_variant_preloads"].append(mission.group("mission"))
            shadow = SPEC_STORE_SHIP_SYSTEM_RE.search(message) if "SpecStore" in match.group("logger") else None
            if shadow is not None:
                shadow_symptoms.append({"line": line_no, "ship_system": shadow.group("system"), "csv": shadow.group("csv")})
            probe = PROBE_LINE_RE.match(message)
            if probe is not None:
                status = probe.group("status")
                probe_entries.append(
                    {
                        "line": line_no,
                        "version": probe.group("version"),
                        "check": probe.group("check"),
                        "status": status if status in PROBE_STATUSES else status,
                        "subject": probe.group("subject"),
                        "detail": probe.group("detail"),
                    }
                )
            if level in ("ERROR", "WARN", "FATAL"):
                current = _Event(line_no, level, match.group("logger"), message)
        elif current is not None:
            if line.strip():
                current.frames.append(line)
            else:
                events.append(current)
                current = None
    if current is not None:
        events.append(current)
    return events, milestones, shadow_symptoms, probe_entries


def _summarize_probe(entries: list[dict[str, object]]) -> dict[str, object]:
    counts_by_status: dict[str, int] = {}
    counts_by_check: dict[str, int] = {}
    for entry in entries:
        counts_by_status[entry["status"]] = counts_by_status.get(entry["status"], 0) + 1
        counts_by_check[entry["check"]] = counts_by_check.get(entry["check"], 0) + 1
    flagged = [entry for entry in entries if entry["status"] in ("FAIL", "WARN")]
    return {
        "entry_count": len(entries),
        "counts_by_status": counts_by_status,
        "counts_by_check": counts_by_check,
        "flagged": flagged,
        "started": any(entry["check"] == "probe" and entry["detail"] == "START" for entry in entries),
        "ended": any(entry["check"] == "probe" and entry["detail"] == "END" for entry in entries),
    }


def _mod_id_of(mod_info_path: Path) -> str | None:
    data = _load_lenient_json_file(mod_info_path)
    if isinstance(data, dict):
        value = data.get("id")
        if isinstance(value, str) and value:
            return value
    return None


def _enabled_mod_ids(mods_dir: Path) -> set[str] | None:
    """The `enabledMods` list from `enabled_mods.json`, or None if the file is absent/unreadable."""
    enabled_path = mods_dir / "enabled_mods.json"
    if not enabled_path.is_file():
        return None
    data = _load_lenient_json_file(enabled_path)
    ids = data.get("enabledMods") if isinstance(data, dict) else None
    if not isinstance(ids, list):
        return None
    return {value for value in ids if isinstance(value, str)}


def _jar_class_entry_names(jar_path: Path) -> list[str]:
    """Zip-sniff `jar_path` (same non-extension-trusting logic as `jar_audit`) for .class entry names."""
    try:
        classes = _resolve_jar_classes(jar_path, None, "mod jar")
    except (ValueError, OSError, zipfile.BadZipFile):
        return []
    return list(classes)


def class_owner_index(mods_dir: Path, enabled_only: bool = True) -> dict[str, str]:
    """Map a class FQN (and its package, when unambiguous and not a shared `data.*` package) to the mod id whose LOADED jar carries it.

    Built from `mod_info.json`'s "jars" list (via `scanner._loaded_mod_jars`, the same jars the
    game actually loads) for every mod under `mods_dir`, restricted to `enabled_mods.json`'s
    `enabledMods` list when `enabled_only` is True and that file exists; otherwise every mod dir
    under `mods_dir` is considered. Read-only: never writes into `mods_dir`.
    """
    root = Path(mods_dir).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"{root} is not an existing directory.")
    enabled_ids = _enabled_mod_ids(root) if enabled_only else None

    index: dict[str, str] = {}
    package_owners: dict[str, set[str]] = {}
    jar_cache: dict[tuple[str, int, int], list[str]] = {}
    for child in sorted(p for p in root.iterdir() if p.is_dir()):
        mod_info_path = child / "mod_info.json"
        if not mod_info_path.is_file():
            continue
        mod_id = _mod_id_of(mod_info_path)
        if mod_id is None:
            continue
        if enabled_ids is not None and mod_id not in enabled_ids:
            continue
        for jar in _loaded_mod_jars(child):
            try:
                stat = jar.stat()
            except OSError:
                continue
            cache_key = (str(jar), stat.st_size, stat.st_mtime_ns)
            if cache_key not in jar_cache:
                jar_cache[cache_key] = _jar_class_entry_names(jar)
            for entry_name in jar_cache[cache_key]:
                if not entry_name.lower().endswith(".class"):
                    continue
                fqn = entry_name[:-len(".class")].replace("\\", "/").replace("/", ".")
                if not fqn or fqn.startswith("."):
                    continue
                index.setdefault(fqn, mod_id)
                segments = fqn.split(".")
                if len(segments) > 1:
                    package_owners.setdefault(".".join(segments[:-1]), set()).add(mod_id)
    # Package fallback (for classes a rebuilt jar renamed or a log from another build): only the
    # class's own immediate package, only when exactly one mod uses it, and never the loose-script
    # `data.*` packages (data.scripts, data.hullmods, data.shipsystems...) that nearly every old mod
    # shares -- those once pinned Exigency's frames on SEEKER.
    for package, owners in package_owners.items():
        if len(owners) == 1 and not (package == "data" or package.startswith("data.")):
            index.setdefault(package, next(iter(owners)))
    return index


def _frame_owner(line: str, owner_index: dict[str, str]) -> str | None:
    """The mod id owning a `\tat <class>.<method>(...)` frame, or None for vanilla/unowned frames."""
    match = _FRAME_CLASS_RE.match(line)
    if match is None:
        return None
    qualified = match.group("qualified")
    parts = qualified.split(".")
    if len(parts) < 2:
        return None
    class_name = ".".join(parts[:-1])  # drop the trailing method name
    if any(class_name == prefix.rstrip(".") or class_name.startswith(prefix) for prefix in VANILLA_FRAME_PREFIXES):
        return None
    if class_name in owner_index:
        return owner_index[class_name]
    outer_class = class_name.split("$")[0]
    if outer_class in owner_index:
        return owner_index[outer_class]
    segments = class_name.split(".")
    if len(segments) > 1:
        package = ".".join(segments[:-1])
        if package in owner_index:
            return owner_index[package]
    return None


def _attribute_event(event: _Event, owner_index: dict[str, str]) -> dict[str, object]:
    frames_by_mod: list[str] = []
    top_mod_frame: str | None = None
    suspect: str | None = None
    for line in event.frames:
        if not _STACK_FRAME_RE.match(line):
            continue
        owner = _frame_owner(line, owner_index)
        if owner is None:
            continue
        if top_mod_frame is None:
            top_mod_frame = line.strip()
            suspect = owner
        if owner not in frames_by_mod:
            frames_by_mod.append(owner)
    return {
        "frames_by_mod": frames_by_mod,
        "top_mod_frame": top_mod_frame,
        "suspect": suspect,
        "involved": sorted(frames_by_mod),
    }


def _summarize_attribution(entries: list[dict[str, object]]) -> dict[str, object]:
    counts_by_suspect: dict[str, int] = {}
    unattributed = 0
    for entry in entries:
        suspect = entry.get("suspect")
        if isinstance(suspect, str):
            counts_by_suspect[suspect] = counts_by_suspect.get(suspect, 0) + 1
        else:
            unattributed += 1
    return {
        "counts_by_suspect": counts_by_suspect,
        "attributed_count": sum(counts_by_suspect.values()),
        "unattributed_count": unattributed,
    }


def triage_log(log_path: Path, mod_prefixes: list[str] | None = None, mods_dir: Path | None = None, all_mods: bool = False) -> dict[str, object]:
    """Classify a Starsector log into FATAL / MOD-ERROR / KNOWN-NOISE / OTHER without modifying it.

    Pass `mods_dir` (a `mods/` directory -- the rig's own or a foreign modpack's) to additionally
    attribute each FATAL/MOD-ERROR/OTHER exception block to the mod whose jar owns the stack frame
    closest to the throw; see `class_owner_index`. Never writes anything.
    """
    path = Path(log_path).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"{path} is not an existing log file.")
    prefixes = tuple(DEFAULT_MOD_PREFIXES) + tuple(mod_prefixes or ())
    owner_index = class_owner_index(mods_dir, enabled_only=not all_mods) if mods_dir is not None else None
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    events, milestones, shadow_symptoms, probe_entries = _iter_events_and_milestones(lines)
    classified: dict[str, list[dict[str, object]]] = {"FATAL": [], "MOD-ERROR": [], "KNOWN-NOISE": [], "OTHER": []}
    for event in events:
        outcome = _classify_event(event, prefixes)
        category = outcome.pop("category")
        entry: dict[str, object] = {"line": event.line_no, "level": event.level, "logger": event.logger, "message": event.head_message}
        entry.update(outcome)
        if category in ("FATAL", "MOD-ERROR"):
            entry["top_mod_frame"] = _first_mod_frame(event, prefixes)
        if owner_index is not None and category in ("FATAL", "MOD-ERROR", "OTHER"):
            entry.update(_attribute_event(event, owner_index))
        classified[category].append(entry)
    result = {
        "schema_version": 1,
        "mode": "READ_ONLY_LOG_TRIAGE",
        "log": str(path),
        "mod_prefixes": list(prefixes),
        "counts": {key: len(value) for key, value in classified.items()},
        "fatal": classified["FATAL"],
        "mod_errors": classified["MOD-ERROR"],
        "known_noise": classified["KNOWN-NOISE"],
        "other": classified["OTHER"],
        "milestones": milestones,
        "vanilla_shadowing_symptoms": shadow_symptoms,
        "probe": _summarize_probe(probe_entries),
        "caveat": FATAL_ABSENCE_CAVEAT,
    }
    if owner_index is not None:
        result["mods_dir"] = str(Path(mods_dir).expanduser().resolve())
        result["attribution"] = _summarize_attribution(classified["FATAL"] + classified["MOD-ERROR"] + classified["OTHER"])
    return result
