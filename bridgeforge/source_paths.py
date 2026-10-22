"""Source inventories for audits and identities (ROADMAP-3 83 B0).

Use package-relative names so duplicate leaves remain distinct; never import sources to discover them.
"""
from __future__ import annotations

from pathlib import Path


def python_sources(root: Path) -> list[Path]:
    """Every Python source under root, excluding interpreter cache directories."""
    root = Path(root)
    return sorted(p for p in root.rglob("*.py")
                  if p.is_file() and "__pycache__" not in p.relative_to(root).parts)


def family_sources(root: Path, family: str) -> list[Path]:
    """Legacy prefix files plus all files in the family's future subpackage."""
    root = Path(root)
    return [p for p in python_sources(root)
            if p.stem == family or p.stem.startswith(family + "_")
            or family in p.relative_to(root).parts[:-1]]
