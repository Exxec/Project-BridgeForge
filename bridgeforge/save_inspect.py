from __future__ import annotations

import re
from pathlib import Path

from .save_compat import ModClassIndex, _package_of, _resolve_save_path
from .save_reader import (
    campaign_xml_path,
    coerce_scalar,
    iter_elements,
    parse_build_tag,
    parse_descriptor,
)

"""Read-only save inspection (roadmap P3b-A/F/G/H): tracked state, diffs, script-duplication
audit, growth trend across a save chain, and provenance. Everything here streams `campaign.xml`
line-by-line (see `save_reader.iter_elements`); nothing loads the ~10 MB file whole.
"""

_KNOWN_LIST_TAG = re.compile(r"known", re.IGNORECASE)
_SCRIPT_CONTAINER_TAG = re.compile(r"^(scripts|listeners|listenersWithTimeout)$")


def _single_pass(campaign_xml: Path, *, track_classes: set[str], track_ids: set[str], mod_index: ModClassIndex | None):
    """One streaming pass collecting everything `inspect_save`/`audit_scripts` need.

    Returns (tracked_objects, tracked_id_hits, known_lists, namespace_counts, script_instances).
    A single shared pass -- rather than one per concern -- keeps this within one read of the
    file even when several checks are requested together.
    """
    tracked_objects: list[dict[str, object]] = []
    tracked_id_hits: list[dict[str, object]] = []
    known_lists: list[dict[str, object]] = []
    namespace_counts: dict[str, int] = {}
    script_instances: list[dict[str, object]] = []

    # Open-record stacks, keyed by the depth (len(path)) at which the record started.
    open_tracked: list[dict[str, object]] = []
    open_known: list[dict[str, object]] = []
    # Last <id> leaf seen directly under the element at each depth, so a known list can name its
    # owning faction. Every faction's list has the same path; without this, save baselines had
    # duplicate subjects and behavior-diff refused them (Flu-X, 2026-09-13).
    ids_by_parent_depth: dict[int, str] = {}

    for element in iter_elements(campaign_xml):
        depth = len(element.path)
        for stale in [key for key in ids_by_parent_depth if key >= depth]:
            del ids_by_parent_depth[stale]
        if element.tag == "id" and element.text is not None:
            ids_by_parent_depth[depth - 1] = str(element.text)

        # Close any open records whose scope has ended (this element is a sibling or higher).
        while open_tracked and depth <= open_tracked[-1]["depth"]:
            finished = open_tracked.pop()
            tracked_objects.append(
                {
                    "class": finished["tag"],
                    "z": finished["z"],
                    "path": "/" + "/".join(finished["path"]),
                    "fields": finished["fields"],
                }
            )
        while open_known and depth <= open_known[-1]["depth"]:
            finished = open_known.pop()
            known_lists.append(
                {
                    "tag": finished["tag"],
                    "path": "/" + "/".join(finished["path"]),
                    "size": finished["count"],
                    "owner": finished.get("owner"),
                }
            )

        # Feed fields into any still-open tracked-class / known-list records.
        for record in open_tracked:
            if depth == record["depth"] + 1:
                if element.attrs.get("ref"):
                    record["fields"][f"{element.tag}@ref"] = element.attrs["ref"]
                elif element.attrs.get("cl"):
                    record["fields"].setdefault(f"{element.tag}@cl", element.attrs["cl"])
                elif element.text is not None:
                    record["fields"][element.tag] = coerce_scalar(element.text)
        for record in open_known:
            if depth == record["depth"] + 1:
                record["count"] += 1

        # Open a new tracked-class record.
        if element.tag in track_classes and element.text is None:
            open_tracked.append(
                {"depth": depth, "tag": element.tag, "z": element.attrs.get("z"), "path": element.path, "fields": {}}
            )

        # Open a new known-list container (heuristic: tag name containing "known").
        if element.text is None and _KNOWN_LIST_TAG.search(element.tag):
            open_known.append({"depth": depth, "tag": element.tag, "path": element.path, "count": 0, "owner": ids_by_parent_depth.get(depth - 1)})

        # Tracked entity ids: match on leaf text or on any attribute value.
        if track_ids:
            if element.text is not None and element.text in track_ids:
                tracked_id_hits.append(
                    {"id": element.text, "field": element.tag, "path": "/" + "/".join(element.path)}
                )
            for attr_value in element.attrs.values():
                if attr_value in track_ids:
                    tracked_id_hits.append(
                        {"id": attr_value, "field": element.tag, "path": "/" + "/".join(element.path)}
                    )

        # Per-mod object counts by class namespace, and script/listener instances. Every tag
        # name is a candidate (matching `save_compat`'s own tokenizer -- a class reference can
        # be a genuine leaf-looking `<Tag></Tag>` pair with empty text, not just a multi-line
        # structural element), filtered by whether the mod's alias index resolves it at all.
        if mod_index is not None:
            tokens = [element.tag]
            cl_attr = element.attrs.get("cl")
            if cl_attr:
                tokens.append(cl_attr)
            for token in tokens:
                classes = mod_index.resolve(token)
                if not classes:
                    continue
                for class_name in classes:
                    package = _package_of(class_name)
                    namespace_counts[package] = namespace_counts.get(package, 0) + 1
                if len(element.path) >= 2 and _SCRIPT_CONTAINER_TAG.match(element.path[-2]):
                    holder_path = element.path[:-2]
                    script_instances.append(
                        {
                            "class": sorted(classes)[0],
                            "holder": "/" + "/".join(holder_path) if holder_path else "(sector)",
                        }
                    )

    # Flush anything still open at end of file (shouldn't normally happen for well-formed saves).
    for finished in open_tracked:
        tracked_objects.append(
            {
                "class": finished["tag"],
                "z": finished["z"],
                "path": "/" + "/".join(finished["path"]),
                "fields": finished["fields"],
            }
        )
    for finished in open_known:
        known_lists.append(
            {"tag": finished["tag"], "path": "/" + "/".join(finished["path"]), "size": finished["count"], "owner": finished.get("owner")}
        )

    return tracked_objects, tracked_id_hits, known_lists, namespace_counts, script_instances


def inspect_save(
    save: Path | str,
    *,
    track_classes: list[str] | None = None,
    track_ids: list[str] | None = None,
    mod_dir: Path | str | None = None,
    vanilla_core: Path | str | None = None,
) -> dict[str, object]:
    """Stream `campaign.xml` and report tracked objects/ids, known-list sizes, and per-mod counts.

    - `track_classes`: element-tag class aliases to fully capture (e.g. `ExipiratedAvestaMovement`
      -> its `waypoint`/`progress`/`loitering`/... immediate scalar fields, one record per instance).
    - `track_ids`: entity id strings to locate; a hit reports the field it was found in and its
      containment path. This is a streaming, path-based "location" (the save's ancestor-element
      chain), not a resolved sector coordinate -- reported explicitly as `path`, never invented.
    - `mod_dir`/`vanilla_core`: when given, resolves class references the same way `save_compat`
      does (reusing `ModClassIndex`) and reports per-mod object counts grouped by class package
      ("namespace").
    - Faction known-list sizes: heuristic -- any container element whose tag contains "known"
      (`knownFactions`, `knownShips`, ...) reports its immediate-child count. This is intentionally
      broad rather than a curated list of exact vanilla field names, and is labelled as such.
    """
    campaign_xml = campaign_xml_path(save)
    track_classes_set = set(track_classes or [])
    track_ids_set = set(track_ids or [])
    mod_index = ModClassIndex(Path(mod_dir).expanduser().resolve()) if mod_dir is not None else None

    tracked_objects, tracked_id_hits, known_lists, namespace_counts, _scripts = _single_pass(
        campaign_xml, track_classes=track_classes_set, track_ids=track_ids_set, mod_index=mod_index
    )

    return {
        "schema_version": 1,
        "mode": "READ_ONLY_SAVE_INSPECT",
        "save": str(campaign_xml),
        "tracked_classes": track_classes or [],
        "tracked_objects": tracked_objects,
        "tracked_ids": track_ids or [],
        "tracked_id_hits": tracked_id_hits,
        "known_lists": [
            {**entry, "limitation": "heuristic: any container tag containing 'known'"} for entry in known_lists
        ],
        "mod_object_counts": (
            {
                "mod_dir": str(Path(mod_dir).expanduser().resolve()),
                "by_namespace": dict(sorted(namespace_counts.items())),
                "total": sum(namespace_counts.values()),
            }
            if mod_dir is not None
            else None
        ),
    }


def diff_saves(
    a: Path | str,
    b: Path | str,
    *,
    track_classes: list[str] | None = None,
    track_ids: list[str] | None = None,
    mod_dir: Path | str | None = None,
    vanilla_core: Path | str | None = None,
) -> dict[str, object]:
    """Compare `inspect_save(a, ...)` against `inspect_save(b, ...)`.

    Tracked objects are matched by `(class, path)`, **not** `(class, z)`: XStream's `z=` id is
    only a per-file sequence number, not a stable object identity -- confirmed on a real save and
    its own `.bak` predecessor (`In operation/_rig/saves/save_FourthAnderson_*`),
    where the same `ExipiratedAvestaMovement` singleton was `z="889"` in the `.bak` and `z="891"`
    in the current save, while its containment path was byte-identical between the two. Path is
    stable for a singleton-per-campaign tracked class (the common case for a mod's own manager
    script); a class with more than one same-path instance on one side is handled by only
    matching the first, with the rest falling into added/removed, which is reported rather than
    guessed. Field-level differences are reported per matched object. Mod object counts are
    diffed per namespace.
    """
    left = inspect_save(a, track_classes=track_classes, track_ids=track_ids, mod_dir=mod_dir, vanilla_core=vanilla_core)
    right = inspect_save(b, track_classes=track_classes, track_ids=track_ids, mod_dir=mod_dir, vanilla_core=vanilla_core)

    def _by_key(objs: list[dict[str, object]]) -> dict[tuple[str, str], dict[str, object]]:
        by_key: dict[tuple[str, str], dict[str, object]] = {}
        for obj in objs:
            key = (obj["class"], obj["path"])
            by_key.setdefault(key, obj)
        return by_key

    left_objs = _by_key(left["tracked_objects"])
    right_objs = _by_key(right["tracked_objects"])

    changed: list[dict[str, object]] = []
    for key in sorted(set(left_objs) & set(right_objs)):
        left_fields = left_objs[key]["fields"]
        right_fields = right_objs[key]["fields"]
        field_diffs = {}
        for field in sorted(set(left_fields) | set(right_fields)):
            lv, rv = left_fields.get(field), right_fields.get(field)
            if lv != rv:
                field_diffs[field] = {"a": lv, "b": rv}
        if field_diffs:
            changed.append({"class": key[0], "path": key[1], "fields": field_diffs})

    added = [right_objs[key] for key in sorted(set(right_objs) - set(left_objs))]
    removed = [left_objs[key] for key in sorted(set(left_objs) - set(right_objs))]

    namespace_diff = {}
    if left["mod_object_counts"] and right["mod_object_counts"]:
        left_ns = left["mod_object_counts"]["by_namespace"]
        right_ns = right["mod_object_counts"]["by_namespace"]
        for namespace in sorted(set(left_ns) | set(right_ns)):
            la, rb = left_ns.get(namespace, 0), right_ns.get(namespace, 0)
            if la != rb:
                namespace_diff[namespace] = {"a": la, "b": rb, "delta": rb - la}

    return {
        "schema_version": 1,
        "mode": "READ_ONLY_SAVE_DIFF",
        "a": left["save"],
        "b": right["save"],
        "changed_objects": changed,
        "added_objects": added,
        "removed_objects": removed,
        "tracked_id_hits_a": left["tracked_id_hits"],
        "tracked_id_hits_b": right["tracked_id_hits"],
        "mod_object_namespace_diff": namespace_diff,
    }


def audit_scripts(save: Path | str, mod_dir: Path | str, *, vanilla_core: Path | str | None = None) -> dict[str, object]:
    """Count mod-owned `<scripts>`/`<listeners>` instances per holder, and flag duplicates.

    A "holder" is the element two levels above a script instance in the save's containment path
    (the instance's grandparent -- its parent is the `scripts`/`listeners` list container itself);
    reported as that ancestor's tag path, or `"(sector)"` when the container sits at the campaign
    root. Ownership is attributed the same way `save_compat` attributes any class reference (exact
    alias match, or surviving-package match for a removed class); vanilla and other mods' scripts
    are never counted. A duplicate is >1 instance of the same class under the same holder -- the
    classic "onGameLoad re-adds a script every load" bug class (VT-7 in the revival plan).
    """
    campaign_xml = _resolve_save_path(Path(save))
    mod_dir = Path(mod_dir).expanduser().resolve()
    mod_index = ModClassIndex(mod_dir)

    _objects, _ids, _known, _namespaces, script_instances = _single_pass(
        campaign_xml, track_classes=set(), track_ids=set(), mod_index=mod_index
    )

    counts: dict[tuple[str, str], int] = {}
    for instance in script_instances:
        key = (instance["holder"], instance["class"])
        counts[key] = counts.get(key, 0) + 1

    per_holder: dict[str, list[dict[str, object]]] = {}
    duplicates: list[dict[str, object]] = []
    for (holder, class_name), count in sorted(counts.items()):
        per_holder.setdefault(holder, []).append({"class": class_name, "count": count})
        if count > 1:
            duplicates.append({"holder": holder, "class": class_name, "count": count})

    return {
        "schema_version": 1,
        "mode": "READ_ONLY_SAVE_SCRIPT_AUDIT",
        "save": str(campaign_xml),
        "mod_dir": str(mod_dir),
        "total_instances": len(script_instances),
        "by_holder": [{"holder": holder, "scripts": scripts} for holder, scripts in sorted(per_holder.items())],
        "duplicates": duplicates,
        "status": "DUPLICATES_FOUND" if duplicates else "CLEAN",
    }


def growth_trend(saves: list[Path | str], *, mod_dir: Path | str | None = None, growth_rate_warning: float = 2.0) -> dict[str, object]:
    """Per-mod object counts and file sizes across an ordered chain of saves, with a growth warning.

    `saves` should be given oldest-first (e.g. day 1, day 30, day 90). `growth_rate_warning` is a
    multiplier on `total object count / file size` growth between consecutive saves; exceeding it
    on either axis is reported (never silently), catching leaks like an ever-growing list that
    never gets cleaned up.
    """
    points: list[dict[str, object]] = []
    for save in saves:
        campaign_xml = campaign_xml_path(save)
        size = campaign_xml.stat().st_size
        by_namespace: dict[str, int] = {}
        total = 0
        if mod_dir is not None:
            report = inspect_save(save, mod_dir=mod_dir)
            by_namespace = report["mod_object_counts"]["by_namespace"]
            total = report["mod_object_counts"]["total"]
        points.append(
            {
                "save": str(campaign_xml),
                "file_size_bytes": size,
                "mod_object_count": total,
                "by_namespace": by_namespace,
            }
        )

    warnings: list[dict[str, object]] = []
    for prev, curr in zip(points, points[1:]):
        for axis, prev_v, curr_v in (
            ("file_size_bytes", prev["file_size_bytes"], curr["file_size_bytes"]),
            ("mod_object_count", prev["mod_object_count"], curr["mod_object_count"]),
        ):
            if prev_v <= 0:
                continue
            ratio = curr_v / prev_v
            if ratio >= growth_rate_warning:
                warnings.append(
                    {
                        "from": prev["save"],
                        "to": curr["save"],
                        "axis": axis,
                        "from_value": prev_v,
                        "to_value": curr_v,
                        "ratio": ratio,
                    }
                )

    return {
        "schema_version": 1,
        "mode": "READ_ONLY_SAVE_GROWTH_TREND",
        "mod_dir": str(Path(mod_dir).expanduser().resolve()) if mod_dir is not None else None,
        "growth_rate_warning_threshold": growth_rate_warning,
        "points": points,
        "warnings": warnings,
        "status": "GROWTH_WARNING" if warnings else "OK",
    }


def _mod_version_lookup(mod_dirs: list[Path | str]) -> dict[str, dict[str, object]]:
    from .build_tag import BuildTagError, _find_mod_info
    from .scanner import _load_lenient_json_file

    lookup: dict[str, dict[str, object]] = {}
    for mod_dir in mod_dirs:
        mod_dir = Path(mod_dir).expanduser().resolve()
        try:
            mod_info_path = _find_mod_info(mod_dir)
        except BuildTagError:
            continue
        data = _load_lenient_json_file(mod_info_path)
        if not isinstance(data, dict):
            continue
        mod_id = data.get("id")
        if not isinstance(mod_id, str):
            continue
        name = data.get("name") if isinstance(data.get("name"), str) else None
        version = data.get("version")
        if isinstance(version, dict):
            version_str = None
        else:
            version_str = version if isinstance(version, str) else None
        lookup[mod_id] = {
            "mod_dir": str(mod_dir),
            "name": name,
            "version": version_str,
            "build_tag": parse_build_tag(name, version_str),
        }
    return lookup


def save_provenance(save: Path | str, *, mod_dirs: list[Path | str]) -> dict[str, object]:
    """Compare a save's recorded mod versions/build tags against the current working copies.

    Reads `descriptor.xml`'s `enabled_mods` (see `save_reader.parse_descriptor`) and, for every
    mod id also present in `mod_dirs`, compares recorded vs. current `version` and BF build number.
    Warns when the save's build is older than the working copy's -- the save-side twin of
    `copy-drift` (this project once ran tests against a stale rig copy of SEEKER).
    """
    descriptor = parse_descriptor(save)
    current = _mod_version_lookup(mod_dirs)

    comparisons: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []
    for mod in descriptor["enabled_mods"]:
        mod_id = mod.get("id")
        if not mod_id or mod_id not in current:
            continue
        current_mod = current[mod_id]
        saved_build = mod["build_tag"]["build"]
        current_build = current_mod["build_tag"]["build"]
        comparison = {
            "mod_id": mod_id,
            "saved_version": mod.get("version"),
            "current_version": current_mod.get("version"),
            "saved_build": saved_build,
            "current_build": current_build,
            "version_matches": mod.get("version") == current_mod.get("version"),
        }
        comparisons.append(comparison)
        if saved_build is not None and current_build is not None and saved_build < current_build:
            warnings.append(
                {
                    "mod_id": mod_id,
                    "reason": "save was made with an older BF build than the current working copy",
                    "saved_build": saved_build,
                    "current_build": current_build,
                }
            )
        elif comparison["saved_version"] is not None and comparison["current_version"] is not None and not comparison["version_matches"]:
            warnings.append(
                {
                    "mod_id": mod_id,
                    "reason": "save's recorded version differs from the current working copy's version",
                    "saved_version": comparison["saved_version"],
                    "current_version": comparison["current_version"],
                }
            )

    return {
        "schema_version": 1,
        "mode": "READ_ONLY_SAVE_PROVENANCE",
        "save": descriptor["save_dir"],
        "save_game_version": descriptor["game_version"],
        "comparisons": comparisons,
        "warnings": warnings,
        "status": "STALE_BUILD" if warnings else "CURRENT",
    }
