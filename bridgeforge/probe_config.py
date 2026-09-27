from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from .boot_test import _is_link
from .build_tag import _find_mod_info
from .probe_mod_build import RELEASE_RELATIVE
from .scanner import _load_lenient_json_file, _read_csv_rows, _wing_ids_set

DEFAULT_CAMPAIGN_INTERVAL_DAYS = 5.0
DEFAULT_COMBAT_SECONDS = 60.0
DEFAULT_COMBAT_CAP_PER_SIDE = 12

# On-disk names under <runtime_dir>/saves/common/. Starsector's SettingsAPI common-file methods
# APPEND ".data" to the name the mod asks for: the probe's Java side reads "bf_probe_rig" and the
# game looks for "bf_probe_rig.data" (every other mod's common file there ends in .data too, and the
# probe's own writeTextFileToCommon("bf_probe_report") produced bf_probe_report.data). Writing the
# bare names left the probe switched off on its first live run (live bug PRB-COMMON-01).
COMMON_FILE_SUFFIX = ".data"
RIG_MARKER_FILE = "bf_probe_rig" + COMMON_FILE_SUFFIX
CONFIG_FILE = "bf_probe_config" + COMMON_FILE_SUFFIX
# roadmap P3c-1: the rig-editable profile, read by Java's ProbeFiles.PROFILE ("bf_probe_profile").
PROFILE_FILE = "bf_probe_profile" + COMMON_FILE_SUFFIX
PROBE_MOD_ID = "bridgeforge_probe"

# Bundled profiles live under bridgeforge/probe_profiles/<name>.txt (roadmap P3c-1).
PROFILE_DIR = Path(__file__).resolve().parent / "probe_profiles"

PROFILE_APPLY_MODES = frozenset({"once-per-save", "every-load"})
DEFAULT_PROFILE_APPLY = "once-per-save"

# Mirrors com.fs.starfarer.api.campaign.RepLevel's enum constants exactly (roadmap P3b-C), so a
# --setup rep:<faction>=<value> spec that validates here is guaranteed parseable in-game by
# probe-mod's ProbeSetup.applyRep (which tries RepLevel.valueOf(...) first, then a float).
REP_LEVELS = frozenset(
    {
        "VENGEFUL", "HOSTILE", "INHOSPITABLE", "SUSPICIOUS", "NEUTRAL",
        "FAVORABLE", "WELCOMING", "FRIENDLY", "COOPERATIVE",
    }
)

# roadmap P3b-C probe setup specs. Each pattern is deliberately the same shape ProbeSetup.java's
# applyOne(...) switches on (see probe-mod/src/com/bridgeforge/probe/ProbeSetup.java), so a spec
# that validates here is guaranteed to be something the in-game applier can parse.
_SETUP_PATTERNS = {
    "rep": re.compile(r"^rep:(?P<faction>[A-Za-z0-9_]+)=(?P<value>.+)$"),
    "credits": re.compile(r"^credits:(?P<amount>-?\d+(?:\.\d+)?)$"),
    "ship": re.compile(r"^ship:(?P<variant>[A-Za-z0-9_\-]+)(?::(?P<count>\d+))?$"),
    "spawn-fleet": re.compile(r"^spawn-fleet:(?P<faction>[A-Za-z0-9_]+):(?P<fp>\d+(?:\.\d+)?)$"),
    "jump": re.compile(r"^jump:(?P<system>.+)$"),
}


class ProbeConfigError(ValueError):
    """Raised when a probe config cannot be built or installed."""


def validate_setup_spec(spec: str) -> str:
    """Validate one --setup spec string; raise ProbeConfigError with a precise reason if malformed.

    Supported kinds (roadmap P3b-C): rep:<faction>=<RepLevel-or-number>, credits:<N>,
    ship:<variant_id>[:<count>], spawn-fleet:<faction>:<fleet_points>, jump:<star_system_name>.
    Never touches a rig; this is pure string validation, reused by both build_probe_config and the
    CLI before anything is written.
    """
    spec = spec.strip()
    kind = spec.split(":", 1)[0] if ":" in spec else spec
    pattern = _SETUP_PATTERNS.get(kind)
    if pattern is None:
        raise ProbeConfigError(
            f"Unrecognized --setup kind in {spec!r}; expected one of "
            "rep:/credits:/ship:/spawn-fleet:/jump:."
        )
    match = pattern.match(spec)
    if not match:
        raise ProbeConfigError(f"Malformed --setup spec {spec!r} for kind {kind!r}.")
    if kind == "rep":
        value = match.group("value").strip()
        if value.upper() not in REP_LEVELS:
            try:
                float(value)
            except ValueError:
                raise ProbeConfigError(
                    f"--setup {spec!r}: rep value must be a RepLevel name "
                    f"({sorted(REP_LEVELS)}) or a number."
                )
    return spec


def parse_setups(specs: list[str] | None) -> list[str]:
    """Validate every --setup spec, preserving caller order (repeats are allowed as given)."""
    return [validate_setup_spec(spec) for spec in (specs or [])]


# roadmap P3c-1 profile grammar. Each pattern below produces exactly one --setup spec string,
# which is then re-validated through validate_setup_spec -- one validation path, shared with
# --setup and with the Java-side parser this mirrors (probe-mod/src/.../ProbeProfile.java).
_PROFILE_APPLY_RE = re.compile(r"^apply\s*=\s*(?P<mode>\S+)$", re.IGNORECASE)
_PROFILE_REP_RE = re.compile(r"^rep\s+(?P<faction>\S+)\s*=\s*(?P<value>.+)$", re.IGNORECASE)
_PROFILE_CREDITS_RE = re.compile(r"^credits\s*=\s*(?P<amount>-?\d+(?:\.\d+)?)$", re.IGNORECASE)
_PROFILE_SHIP_RE = re.compile(r"^ship\s+(?P<variant>\S+?)(?:\s+x(?P<count>\d+))?$", re.IGNORECASE)
_PROFILE_SPAWN_RE = re.compile(r"^spawn\s+(?P<faction>\S+)\s+(?P<fp>\S+)$", re.IGNORECASE)
_PROFILE_JUMP_RE = re.compile(r"^jump\s+(?P<system>.+)$", re.IGNORECASE)


def _strip_inline_comment(line: str) -> str:
    """Drop everything from the first '#' onward, then trim whitespace ('#' always starts a
    comment; no profile line form ever needs a literal '#' in a faction/variant/system token)."""
    hash_index = line.find("#")
    if hash_index >= 0:
        line = line[:hash_index]
    return line.strip()


def _profile_body_to_spec(source: str, line_no: int, body: str) -> str:
    """Translate one comment-stripped, non-'apply' profile line into a --setup spec string."""
    match = _PROFILE_REP_RE.match(body)
    if match:
        return f"rep:{match.group('faction')}={match.group('value').strip()}"
    match = _PROFILE_CREDITS_RE.match(body)
    if match:
        return f"credits:{match.group('amount')}"
    match = _PROFILE_SHIP_RE.match(body)
    if match:
        count = match.group("count")
        return f"ship:{match.group('variant')}:{count}" if count else f"ship:{match.group('variant')}"
    match = _PROFILE_SPAWN_RE.match(body)
    if match:
        return f"spawn-fleet:{match.group('faction')}:{match.group('fp')}"
    match = _PROFILE_JUMP_RE.match(body)
    if match:
        return f"jump:{match.group('system').strip()}"
    raise ProbeConfigError(
        f"{source}:{line_no}: Unrecognized profile line {body!r}; expected 'apply = ...', "
        "'rep F = L', 'credits = N', 'ship V [xN]', 'spawn F FP', or 'jump S'."
    )


def parse_profile(text: str, *, source: str = "<profile>") -> dict[str, object]:
    """Parse a Notepad-editable probe profile (roadmap P3c-1) into {apply, setups, disabled}.

    Grammar, one instruction per line (case-insensitive keywords, extra spaces tolerated):
      apply = once-per-save | every-load
      rep <faction> = <RepLevel-or-number>
      credits = <N>
      ship <variant> [xN]
      spawn <faction> <fleet_points>
      jump <star_system_name>
    '#' starts a comment anywhere on the line (inline comments included); blank/comment-only
    lines are ignored. A leading '-' (before any comment is stripped) disables the line: it is
    still parsed and validated, but its spec goes into `disabled` instead of `setups`.

    Every constructed spec is re-validated through validate_setup_spec, so a profile line that
    parses here is guaranteed to be something ProbeSetup.applyOne (Java) can also apply -- the
    same one-validation-path guarantee --setup already has. Raises ProbeConfigError with
    'source:line_no: reason' for anything malformed.
    """
    apply_mode = DEFAULT_PROFILE_APPLY
    setups: list[str] = []
    disabled: list[str] = []
    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line
        stripped_leading = line.lstrip()
        line_disabled = stripped_leading.startswith("-")
        if line_disabled:
            leading_ws = line[: len(line) - len(stripped_leading)]
            line = leading_ws + stripped_leading[1:]
        body = _strip_inline_comment(line)
        if not body:
            continue
        apply_match = _PROFILE_APPLY_RE.match(body)
        if apply_match:
            mode = apply_match.group("mode").lower()
            if mode not in PROFILE_APPLY_MODES:
                raise ProbeConfigError(
                    f"{source}:{line_no}: Unrecognized apply mode {mode!r}; expected one of "
                    f"{sorted(PROFILE_APPLY_MODES)}."
                )
            if not line_disabled:
                apply_mode = mode
            continue
        spec = _profile_body_to_spec(source, line_no, body)
        try:
            spec = validate_setup_spec(spec)
        except ProbeConfigError as exc:
            raise ProbeConfigError(f"{source}:{line_no}: {exc}") from exc
        (disabled if line_disabled else setups).append(spec)
    return {"apply": apply_mode, "setups": setups, "disabled": disabled}


def load_profile(name_or_path: str | Path) -> dict[str, object]:
    """Resolve name_or_path to a profile file and parse it (roadmap P3c-1).

    Tries name_or_path as a literal path first, then as a bundled name under
    bridgeforge/probe_profiles/<name>.txt. The returned dict adds 'text' (the raw file contents,
    written verbatim into the rig by write_probe_config) and 'path' (the resolved file) to
    parse_profile's {apply, setups, disabled}.
    """
    candidate = Path(name_or_path).expanduser()
    if candidate.is_file():
        path = candidate.resolve()
    else:
        bundled = PROFILE_DIR / f"{name_or_path}.txt"
        if not bundled.is_file():
            raise ProbeConfigError(
                f"Profile {str(name_or_path)!r} not found as a file, nor as a bundled profile "
                f"under {PROFILE_DIR}."
            )
        path = bundled
    text = path.read_text(encoding="utf-8")
    parsed = parse_profile(text, source=str(path))
    parsed["text"] = text
    parsed["path"] = str(path)
    return parsed


def _spec_to_profile_line(spec: str) -> str:
    """Reverse of _profile_body_to_spec: render a validated --setup spec back as a profile line."""
    kind, _, rest = spec.partition(":")
    if kind == "rep":
        faction, _, value = rest.partition("=")
        return f"rep {faction} = {value}"
    if kind == "credits":
        return f"credits = {rest}"
    if kind == "ship":
        variant, _, count = rest.partition(":")
        return f"ship {variant} x{count}" if count else f"ship {variant}"
    if kind == "spawn-fleet":
        faction, _, fp = rest.partition(":")
        return f"spawn {faction} {fp}"
    if kind == "jump":
        return f"jump {rest}"
    return spec  # pragma: no cover - unreachable, every spec here already passed validate_setup_spec


def _render_profile_text(profile: dict[str, object]) -> str:
    """The raw text write_probe_config writes to the rig's bf_probe_profile common file.

    Prefers the profile's original file text verbatim (present whenever the profile came from
    load_profile). Falls back to a synthesized rendering, in the same grammar parse_profile
    accepts, for a profile dict built directly from parse_profile(text) without going through
    load_profile.
    """
    text = profile.get("text")
    if isinstance(text, str):
        return text
    lines = [f"apply = {profile.get('apply', DEFAULT_PROFILE_APPLY)}"]
    lines.extend(_spec_to_profile_line(str(spec)) for spec in profile.get("setups") or [])
    return "\n".join(lines) + "\n"


def _hull_sizes(mod_root: Path) -> dict[str, str]:
    """hullId -> hullSize from every data/hulls/*.ship file (keyed by the declared hullId, not the file name)."""
    sizes: dict[str, str] = {}
    for path in sorted((mod_root / "data" / "hulls").glob("*.ship")):
        data = _load_lenient_json_file(path)
        if isinstance(data, dict) and isinstance(data.get("hullId"), str) and isinstance(data.get("hullSize"), str):
            sizes[data["hullId"]] = data["hullSize"].strip().upper()
    return sizes


def _hull_inventory(mod_root: Path) -> list[str]:
    """Deployable hull ids from data/hulls/ship_data.csv: no modules, no fighters.

    A fighter is caught by its ship_data `hints` OR by its .ship `hullSize` of FIGHTER. Many mods
    leave `hints` blank for fighters (Exigency's Tarujan/Azata/Naxos), and deploying a fighter variant
    as a SHIP made the game substitute a vanilla Nebula starliner (live bug PRB-FIGHTER-01).
    """
    path = mod_root / "data" / "hulls" / "ship_data.csv"
    sizes = _hull_sizes(mod_root)
    hulls: list[str] = []
    for row in _read_csv_rows(path) or []:
        hull_id = (row.get("id") or "").strip()
        if not hull_id or hull_id.startswith("#"):
            continue
        hints = (row.get("hints") or "").upper()
        if "MODULE" in hints or "FIGHTER" in hints or sizes.get(hull_id) == "FIGHTER":
            continue
        if _is_wreck_piece(row):
            continue
        hulls.append(hull_id)
    return sorted(set(hulls))


_WRECK_DESIGNATION_WORDS = ("debris", "wreck", "hulk", "fragment")


def _is_wreck_piece(row: dict[str, str]) -> bool:
    """Hulls a mod spawns only as wreckage (SEEKER's 13 "Debris" hulks), never as fighting ships.

    Deployed as ships they are disabled on the spot ("... debris class disabled") and crowd real
    hulls out of the per-side cap (live run SK13-1c: 13 debris pieces pushed ART_armor, SKR_clipper
    and CIV_titanic out of the battle) (PRB-DEBRIS-01).
    """
    designation = (row.get("designation") or "").strip().lower()
    return any(word in designation for word in _WRECK_DESIGNATION_WORDS)


def _wreck_pieces(mod_root: Path) -> list[str]:
    path = mod_root / "data" / "hulls" / "ship_data.csv"
    return sorted({(row.get("id") or "").strip() for row in _read_csv_rows(path) or [] if (row.get("id") or "").strip() and _is_wreck_piece(row)})


def _variant_by_hull(mod_root: Path, hulls: list[str]) -> dict[str, str]:
    """Pick one variant id per hull from data/variants/**.variant (first match wins, sorted for determinism)."""
    variants_root = mod_root / "data" / "variants"
    by_hull: dict[str, str] = {}
    if not variants_root.is_dir():
        return by_hull
    wanted = set(hulls)
    for path in sorted(variants_root.rglob("*.variant")):
        data = _load_lenient_json_file(path)
        if not isinstance(data, dict):
            continue
        hull_id = data.get("hullId")
        # Starsector registers a variant under its declared "variantId", not the file name; "id" and
        # the file stem are fallbacks only (ROADMAP P14 item 32).
        variant_id = data.get("variantId") or data.get("id") or path.stem
        if not isinstance(hull_id, str) or hull_id not in wanted or hull_id in by_hull:
            continue
        if isinstance(variant_id, str) and variant_id:
            by_hull[hull_id] = variant_id
    return by_hull


def _content_variants(mod_root: Path, deployable_hulls: list[str]) -> dict[str, list[str]]:
    """Every variant id the mod defines, split by what the probe may do with it (ROADMAP P14 item 31).

    `ship`: the variant's hullId is one of the mod's own deployable hulls, so the probe also builds it
    as a SHIP fleet member. `other`: fighter, module and wreck hulls, and hulls the mod does not define
    (a vanilla hull or a skin), which only get an existence check -- building a fighter variant as a
    SHIP made the game substitute a vanilla Nebula (PRB-FIGHTER-01).
    """
    variants_root = mod_root / "data" / "variants"
    ship: set[str] = set()
    other: set[str] = set()
    if variants_root.is_dir():
        deployable = set(deployable_hulls)
        for path in sorted(variants_root.rglob("*.variant")):
            data = _load_lenient_json_file(path)
            if not isinstance(data, dict):
                continue
            variant_id = data.get("variantId") or data.get("id") or path.stem
            if isinstance(variant_id, str) and variant_id:
                (ship if data.get("hullId") in deployable else other).add(variant_id)
    return {"ship": sorted(ship), "other": sorted(other - ship)}


def _mod_root(mod_dir: Path) -> Path:
    return _find_mod_info(mod_dir).parent


def _mod_faction_ids(mod_root: Path) -> list[str]:
    """Faction ids the mod declares in data/world/factions/*.faction.

    The probe checks these even when they own no markets. In live run EX-7, Exigency's
    market-less faction had 0 fleets for ~20 days and no probe check looked at it.
    """
    ids: set[str] = set()
    for path in sorted((mod_root / "data" / "world" / "factions").glob("*.faction")):
        try:
            data = _load_lenient_json_file(path)
        except (OSError, ValueError):
            continue
        faction_id = data.get("id") if isinstance(data, dict) else None
        if isinstance(faction_id, str) and faction_id:
            ids.add(faction_id)
    return sorted(ids)


def build_probe_config(
    mod_dir: Path,
    track_entities: list[str] | None = None,
    combat_seconds: float = DEFAULT_COMBAT_SECONDS,
    campaign_interval_days: float = DEFAULT_CAMPAIGN_INTERVAL_DAYS,
    combat_cap_per_side: int = DEFAULT_COMBAT_CAP_PER_SIDE,
    setups: list[str] | None = None,
    profile: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build the bf_probe_config payload from a mod's scanner/dossier-style inventory.

    Never modifies the mod directory; this only reads ship_data.csv, mod_info.json, and
    data/variants/*.variant. `setups` (roadmap P3b-C) are validated (see validate_setup_spec) and
    written through verbatim; the probe mod applies each once per save via the public API.
    `profile` (roadmap P3c-1, from parse_profile/load_profile) contributes its own setups merged
    in after `setups`, in order, plus the `apply` mode ('once-per-save' by default, or
    'every-load' when the profile says so).
    """
    mod_root = _mod_root(mod_dir)
    mod_info_path = mod_root / "mod_info.json"
    mod_info = _load_lenient_json_file(mod_info_path)
    target_mod_id = mod_info.get("id") if isinstance(mod_info, dict) else None
    if not isinstance(target_mod_id, str) or not target_mod_id:
        raise ProbeConfigError(f"{mod_info_path} has no string 'id'.")

    hulls = _hull_inventory(mod_root)
    variants = _variant_by_hull(mod_root, hulls)
    hulls_with_variant = [hull for hull in hulls if hull in variants]
    skipped = sorted(set(hulls) - set(hulls_with_variant))

    merged_setups = parse_setups(setups)
    apply_mode = DEFAULT_PROFILE_APPLY
    if profile is not None:
        merged_setups = merged_setups + list(profile.get("setups") or [])
        apply_mode = profile.get("apply", DEFAULT_PROFILE_APPLY)

    return {
        "schema_version": 1,
        "target_mod_id": target_mod_id,
        "hulls": hulls_with_variant,
        "variants": variants,
        "track_entities": sorted(set(track_entities or [])),
        "factions": _mod_faction_ids(mod_root),
        "content_variants": _content_variants(mod_root, hulls),
        "content_wings": sorted(_wing_ids_set(mod_root / "data" / "hulls" / "wing_data.csv")),
        "campaign_interval_days": campaign_interval_days,
        "combat_seconds": combat_seconds,
        "combat_cap_per_side": combat_cap_per_side,
        "hulls_skipped_no_variant": skipped,
        "setups": merged_setups,
        "apply": apply_mode,
    }


def _refuse_non_rig(runtime_dir: Path) -> None:
    core_path = runtime_dir / "starsector-core"
    if not _is_link(core_path):
        raise ProbeConfigError(
            f"{core_path} is not a junction/symlink. probe-config refuses to write into a "
            "non-isolated runtime to avoid touching a real player's saves/common folder."
        )


def write_probe_config(
    mod_dir: Path,
    runtime_dir: Path,
    track_entities: list[str] | None = None,
    combat_seconds: float = DEFAULT_COMBAT_SECONDS,
    campaign_interval_days: float = DEFAULT_CAMPAIGN_INTERVAL_DAYS,
    combat_cap_per_side: int = DEFAULT_COMBAT_CAP_PER_SIDE,
    setups: list[str] | None = None,
    profile: dict[str, object] | None = None,
    dry_run: bool = False,
    install: bool = False,
) -> dict[str, object]:
    """Write bf_probe_config (and bf_probe_profile, bf_probe_rig) into <runtime_dir>/saves/common/,
    and optionally install the probe mod.

    Refuses unless runtime_dir/starsector-core is a junction/symlink (same rig-only guard as
    run_boot_test). --dry-run reports what would be written without touching the rig.
    `profile` (roadmap P3c-1, from parse_profile/load_profile) merges its setups into the config
    (see build_probe_config) AND is written verbatim to the rig's bf_probe_profile common file, so
    the owner can edit that file directly and start a New Game with no further CLI step -- the
    probe mod re-reads it at the first campaign tick and its setups replace the config's when
    present.
    """
    runtime_dir = Path(runtime_dir).expanduser().resolve()
    _refuse_non_rig(runtime_dir)

    config = build_probe_config(
        mod_dir,
        track_entities=track_entities,
        combat_seconds=combat_seconds,
        campaign_interval_days=campaign_interval_days,
        combat_cap_per_side=combat_cap_per_side,
        setups=setups,
        profile=profile,
    )

    common_dir = runtime_dir / "saves" / "common"
    config_path = common_dir / CONFIG_FILE
    marker_path = common_dir / RIG_MARKER_FILE
    profile_path = common_dir / PROFILE_FILE

    result: dict[str, object] = {
        "schema_version": 1,
        "mode": "PROBE_CONFIG",
        "runtime_dir": str(runtime_dir),
        "config_path": str(config_path),
        "marker_path": str(marker_path),
        "profile_path": str(profile_path) if profile is not None else None,
        "config": config,
        "dry_run": dry_run,
        "written": False,
        "installed": False,
    }

    if dry_run:
        return result

    common_dir.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2, sort_keys=True), encoding="utf-8")
    if not marker_path.is_file():
        marker_path.write_text("rig\n", encoding="utf-8")
    if profile is not None:
        profile_path.write_text(_render_profile_text(profile), encoding="utf-8")
    elif profile_path.is_file():
        # The probe lets a rig profile REPLACE the config's setups, so a profile left over from an
        # earlier run would silently override this run's --setup list. Retire it (kept, not deleted).
        retired = profile_path.with_name(PROFILE_FILE + ".prev")
        profile_path.replace(retired)
        result["retired_profile"] = str(retired)
    result["written"] = True

    if install:
        result["install"] = _install_probe_mod(runtime_dir)
        result["installed"] = True

    return result


def _install_probe_mod(runtime_dir: Path) -> dict[str, object]:
    """Copy the built runtime-only release copy of bridgeforge-probe into <runtime_dir>/mods/."""
    repo_root = Path(__file__).resolve().parent.parent
    release_dir = repo_root / RELEASE_RELATIVE
    if not release_dir.is_dir():
        raise ProbeConfigError(
            f"{release_dir} not found; build the probe mod first (build_probe_mod + install_release)."
        )
    dest = runtime_dir / "mods" / "bridgeforge-probe"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(release_dir, dest)
    return {"source": str(release_dir), "destination": str(dest)}
