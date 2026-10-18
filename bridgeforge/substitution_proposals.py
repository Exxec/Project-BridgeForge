"""`bridgeforge substitution-proposals`: for each unresolved content id, a replacement id with its evidence (ROADMAP item 73 C3).

`content-reference-unresolved` names hulls, weapons, wings and hull mods that nothing defines. Before a person chooses between
a provider, vendoring and stripping, this asks whether the id was simply renamed, in this order:
1. `rename`: the reference install the mod targets defines the id, RC8 does not, and exactly one RC8 entry has the same display
   name (and, for hull mods, the same description) - `renamed_ids.find_renamed`. A shared name word alone (SIMILAR) is never a proposal.
2. `provider-rename`: a mod this one declares as a dependency defines a close id with the same first token
   (`provider_renamed_ids.closest_known`). Declared providers only, as for industry ids.
3. `catalogue`: a `content-diff` catalogue lists exactly one RC8-only id with the removed id's display name.
The first applicable source is the proposal; the others are kept as alternatives. Proposals are advice: each is written with
`approved: false`, the SHA-256 of every referencing file, and the files themselves. The REVIEW fixer `content-reference-substitute`
(`fixers_substitute`) applies only entries a person set to `approved: true`, and refuses a file that changed since.
Read-only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from .safeio import atomic_write_json

SCHEMA_VERSION = 1
KINDS = ("hull", "weapon", "hullmod", "wing")
SOURCES = ("rename", "provider-rename", "catalogue")


class ProposalError(ValueError):
    pass


def _sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def _declared_provider_dirs(working: Path, provider_roots: list[Path], index_path: Path | None) -> list[tuple[str, Path]]:
    from .scanner import _load_lenient_json_file
    from .substitutes import merged_providers

    info = _load_lenient_json_file(working / "mod_info.json")
    declared = {str(d.get("id")) for d in (info.get("dependencies") or []) if isinstance(d, dict) and d.get("id")} if isinstance(info, dict) else set()
    if not declared:
        return []
    return [(p.mod_id, Path(p.path)) for p in merged_providers(provider_roots, index_path, exclude=working) if p.mod_id in declared and Path(p.path).is_dir()]


def _unresolved(working: Path, vanilla_core: Path) -> dict[str, dict[str, list[str]]]:
    from .models import TargetProfile
    from .scanner import scan_mod

    context = scan_mod(working, TargetProfile(), vanilla_core).migration_context
    return context.get("unresolved_content_references") or {}


def _rename(kind: str, ident: str, reference_core: Path | None, vanilla_core: Path) -> dict | None:
    from .renamed_ids import find_renamed

    if reference_core is None:
        return None
    verdict = find_renamed(reference_core, vanilla_core, [f"{kind}:{ident}"])[0]
    if verdict.get("verdict") != "RENAMED":
        return None
    new = verdict["renamed_to"][0]
    return {"source": "rename", "replacement": new, "provider": None,
            "evidence": f"{reference_core.name} defines {kind} '{ident}' (\"{verdict['old_name']}\"); RC8's only entry with that name"
                        + (" and description" if kind == "hullmod" else "") + f" is '{new}'."}


def _provider_rename(kind: str, ident: str, providers: list[tuple[str, Path]]) -> dict | None:
    from .provider_renamed_ids import closest_known
    from .renamed_ids import _rows

    best = None
    for mod_id, folder in providers:
        near = closest_known(ident, set(_rows(folder, kind)))
        if near and (best is None or near[1] > best[1]):
            best = (near[0], near[1], mod_id)
    if best is None:
        return None
    return {"source": "provider-rename", "replacement": best[0], "provider": best[2],
            "evidence": f"declared dependency '{best[2]}' defines {kind} '{best[0]}', {best[1]:.0%} like '{ident}' and with the same first token."}


def _catalogue(kind: str, ident: str, catalogue: dict | None) -> dict | None:
    for entry in ((catalogue or {}).get("removed") or {}).get(kind, []):
        leads = entry.get("same_name_in_rc8") or []
        if entry.get("id") == ident and len(leads) == 1:
            return {"source": "catalogue", "replacement": leads[0], "provider": None,
                    "evidence": f"content-diff catalogue: '{ident}' was removed from vanilla and RC8's only id with its name"
                                + (f" (\"{entry['name']}\")" if entry.get("name") else "") + f" is '{leads[0]}'."}
    return None


def propose(working: Path, vanilla_core: Path, *, reference_core: Path | None = None, provider_roots: list[Path] | None = None,
            index_path: Path | None = None, catalogue: dict | None = None, unresolved: dict | None = None) -> dict:
    working, vanilla_core = Path(working).expanduser().resolve(), Path(vanilla_core).expanduser().resolve()
    reference_core = Path(reference_core).expanduser().resolve() if reference_core else None
    table = unresolved if unresolved is not None else _unresolved(working, vanilla_core)
    providers = _declared_provider_dirs(working, provider_roots or [], index_path)
    proposals, unproposed = [], []
    for kind in KINDS:
        for ident, files in sorted((table.get(kind) or {}).items()):
            found = [c for c in (_rename(kind, ident, reference_core, vanilla_core), _provider_rename(kind, ident, providers),
                                 _catalogue(kind, ident, catalogue)) if c]
            # The same replacement offered by two sources is one proposal with the first source's evidence.
            if not found:
                unproposed.append(f"{kind}:{ident}")
                continue
            first, *rest = found
            proposals.append({"kind": kind, "id": ident, **first, "alternatives": [r for r in rest if r["replacement"] != first["replacement"]],
                              "files": sorted(files), "file_sha256": {f: _sha256(working / f) for f in sorted(files)}, "approved": False})
    return {"schema_version": SCHEMA_VERSION, "mode": "SUBSTITUTION_PROPOSALS", "mod": str(working), "vanilla_core": str(vanilla_core),
            "reference_core": str(reference_core) if reference_core else None, "proposals": proposals, "unproposed": unproposed,
            "note": "Advice only. Set \"approved\": true on the entries a person accepts, then "
                    "`bridgeforge fix MOD --finding content-reference-substitute --substitutions FILE`."}


def render_lines(result: dict) -> list[str]:
    lines = [f"- **Substitution proposals** ({len(result['proposals'])} of {len(result['proposals']) + len(result['unproposed'])} unresolved id(s)):"]
    for item in result["proposals"]:
        lines.append(f"  - `{item['kind']}:{item['id']}` -> `{item['replacement']}` ({item['source']}): {item['evidence']}")
        lines += [f"    - or `{alt['replacement']}` ({alt['source']}): {alt['evidence']}" for alt in item["alternatives"]]
    if result["unproposed"]:
        lines.append("  - no replacement found for: " + ", ".join(result["unproposed"][:12]))
    return lines


def add_parser(subcommands) -> None:
    cmd = subcommands.add_parser("substitution-proposals", help="for each unresolved content id, a renamed replacement with its evidence (reference-install rename, declared-provider rename, content-diff catalogue); read-only, writes proposals you approve for `fix --finding content-reference-substitute`")
    cmd.add_argument("workspace", type=Path, help="a workspace folder holding working/mod_info.json")
    cmd.add_argument("--vanilla-core", type=Path, required=True, help="RC8 starsector-core")
    cmd.add_argument("--reference-core", type=Path, help="the older starsector-core the mod was made for (enables the rename source)")
    cmd.add_argument("--providers", type=Path, action="append", default=[], help="where to look for declared dependencies (default: the workspace's queue folder); repeatable")
    cmd.add_argument("--provider-index", type=Path)
    cmd.add_argument("--catalogue", type=Path, help="a `content-diff --json` output")
    cmd.add_argument("--write", type=Path, metavar="FILE.json", help="write the proposals (approved: false) for review")
    cmd.add_argument("--json", action="store_true")


def run_cli(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).expanduser().resolve()
    working = workspace / "working"
    if not (working / "mod_info.json").is_file():
        print(f"bridgeforge: {workspace} has no working/mod_info.json.", file=sys.stderr)
        return 2
    try:
        catalogue = json.loads(args.catalogue.read_text(encoding="utf-8")) if args.catalogue else None
        result = propose(working, args.vanilla_core, reference_core=args.reference_core, provider_roots=args.providers or [workspace.parent],
                         index_path=args.provider_index, catalogue=catalogue)
    except (OSError, ValueError) as exc:
        print(f"bridgeforge: {exc}", file=sys.stderr)
        return 2
    if args.write:
        atomic_write_json(args.write, result)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("\n".join(render_lines(result)) + (f"\nWritten: {args.write}" if args.write else ""))
    return 0
