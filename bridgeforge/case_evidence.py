"""Isolated read-only scan/compile worker used by S1 qualification (not a public CLI)."""
from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import sys

from .compile_check import compile_loose_scripts
from .models import TargetProfile
from .safeio import atomic_write_json
from .scan.scanner import scan_mod


def evaluate_request(request: dict) -> dict:
    working = Path(request['working'])
    core = Path(request['core'])
    providers = [Path(path) for path in request['providers']]
    # Keep an explicit nonempty search boundary even when no dependency is selected.
    providers = providers or [working]
    scan = scan_mod(working, TargetProfile(starsector='0.98.x', java=17), core, provider_roots=providers)
    compiled = None
    if request['compile']:
        compiled = compile_loose_scripts(working, core, Path(request['jdk']), provider_roots=providers)
    return {'schema_version': 1, 'metadata': scan.metadata, 'metadata_parse_mode': scan.metadata_parse_mode,
            'findings': [asdict(finding) for finding in scan.findings], 'compile': compiled}


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        raise ValueError('Worker requires request and response paths')
    request = json.loads(Path(args[0]).read_text(encoding='utf-8'))
    atomic_write_json(Path(args[1]), evaluate_request(request))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
