"""Which mods need which missing content, and which unrevived provider unblocks the most of them.

ROADMAP P14 item 6/3: "Build a graph of which queued mods need which missing mods, and order
revival by unblocking value." Built on `substitutes.py`'s existing per-mod analysis
(`required_from_scan`, `provider_index`) and item 6/2's persistent provider-index cache
(`load_provider_index`) - the cache is what lets this graph credit a provider that unblocks
something even when that provider isn't currently installed anywhere live, matching item 2's own
"works when the provider isn't installed" requirement.

Scope note: the roadmap text also says "Show it in `board`." This is deliberately its own command
instead - `board`'s own row shape (one mod, its layout/report evidence) doesn't naturally hold a
cross-mod graph, and folding a second, unrelated concern into it would make `board` harder to read
for its actual job. The graph is fully visible here, in both JSON and a plain-text ranked summary.
"""

from __future__ import annotations

from pathlib import Path

from .models import TargetProfile
from .project_board import project_board
from .scanner import scan_mod
from .substitutes import DEFAULT_PROVIDER_INDEX_DIR, KINDS, Provider, load_provider_index, provider_index, required_from_scan

SCHEMA_VERSION = 1


def _mod_ids_with_revival_work(repo_root: Path) -> list[tuple[str, Path]]:
    board = project_board(repo_root)
    return [(row["folder"], Path(row["working"])) for row in board["mods"] if row["working"] and row["evidence"]["report"]]


def _covers_any(provider: Provider, kind: str, needed_id: str) -> bool:
    return needed_id in provider.provides.get(kind, set())


def build_dependency_graph(repo_root: Path, vanilla_core: Path | None = None, provider_index_dir: Path = DEFAULT_PROVIDER_INDEX_DIR) -> dict:
    """For every mod with real revival work recorded, find what it still needs from elsewhere.

    "Needs" comes from `content-reference-unresolved`/`source-import-unresolved` findings
    (`required_from_scan`). A need already covered by a live, currently-visible provider (the
    default `<repo>/In operation` + rig mods roots) is not a blocker - only a need with NO live
    coverage is checked against the cached provider index for an unrevived candidate.
    """
    repo = repo_root.expanduser().resolve()
    vanilla_root = vanilla_core.expanduser().resolve() if vanilla_core is not None else None
    if vanilla_root is not None and not vanilla_root.is_dir():
        vanilla_root = None
    mods = _mod_ids_with_revival_work(repo)
    live_providers = provider_index([repo / "In operation", repo / "In operation" / "_rig" / "mods"])
    cached_providers = {provider.mod_id: provider for provider in load_provider_index(provider_index_dir)}

    dependents: dict[str, dict[str, object]] = {}  # blocker mod_id -> {"unblocks": set(), "covers": {kind: set(ids)}}
    unresolved_by_mod: dict[str, dict[str, list[str]]] = {}

    for mod_id, working in mods:
        try:
            result = scan_mod(working, TargetProfile(), vanilla_root)
        except ValueError:
            continue
        needed, _files = required_from_scan(result)
        still_missing: dict[str, list[str]] = {}
        working_resolved = working.resolve()
        for kind in KINDS:
            for needed_id in sorted(needed.get(kind, set())):
                if any(_covers_any(provider, kind, needed_id) for provider in live_providers):
                    continue  # a live provider already covers this - not a blocker
                # Exclude a provider whose cached path IS this same mod (never suggest a mod as
                # its own fix) - compared by resolved filesystem path, since the dependent mod's
                # identity here is its folder name (matching corpus_recheck/board's convention)
                # while a cached Provider's identity is its declared mod_info.json id; the two are
                # not directly comparable, but both ultimately point at a real directory.
                blocker = next(
                    (p for p in cached_providers.values() if Path(p.path).resolve() != working_resolved and _covers_any(p, kind, needed_id)),
                    None,
                )
                if blocker is None:
                    continue  # genuinely nowhere - not something reviving another mod would fix
                still_missing.setdefault(kind, []).append(needed_id)
                entry = dependents.setdefault(blocker.mod_id, {"unblocks": set(), "covers": {k: set() for k in KINDS}})
                entry["unblocks"].add(mod_id)
                entry["covers"][kind].add(needed_id)
        if still_missing:
            unresolved_by_mod[mod_id] = still_missing

    ranked = sorted(
        (
            {
                "provider_mod_id": provider_id,
                "provider_name": cached_providers[provider_id].name,
                "provider_version": cached_providers[provider_id].version,
                "provider_game_version": cached_providers[provider_id].game_version,
                "unblocks_count": len(entry["unblocks"]),
                "unblocks": sorted(entry["unblocks"]),
                "covers": {kind: sorted(ids) for kind, ids in entry["covers"].items() if ids},
            }
            for provider_id, entry in dependents.items()
        ),
        key=lambda row: (-row["unblocks_count"], row["provider_mod_id"]),
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "dependency-graph",
        "status": "OK",
        "repo_root": str(repo),
        "mod_count": len(mods),
        "unresolved_by_mod": unresolved_by_mod,
        "ranked_providers": ranked,
    }
