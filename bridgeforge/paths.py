"""Where BridgeForge's checkout and its data live (ROADMAP-3 96.5 A2).

Two different places, which 19 modules each worked out for themselves from their own file location:
- `checkout_root()`: the source tree this package was imported from (docs, changelog.d, tests, tools).
- `data_root()`: the folder holding `In operation/`, `Done/` and `bridgeforge-state/`. On Test1 it is the checkout; on
  White_Legion the checkouts are worktrees under `bridgeforge-state/github-fixes/` and the data is three levels up, so a
  run that needs the real data there names it with `BRIDGEFORGE_DATA_ROOT`.

Without the variable both are the checkout, which is what every module computed before; nothing moves. A path given on
the command line still wins over either.
"""
from __future__ import annotations

import os
from pathlib import Path

DATA_ROOT_ENV = "BRIDGEFORGE_DATA_ROOT"
STATE_DIR_NAME = "bridgeforge-state"
OPS_DIR_NAME = "In operation"
DONE_DIR_NAME = "Done"


def checkout_root() -> Path:
    """The source tree holding this package (`<root>/bridgeforge/paths.py`)."""
    return Path(__file__).resolve().parent.parent


def data_root() -> Path:
    """`BRIDGEFORGE_DATA_ROOT` when set (expanded and resolved), else the checkout."""
    configured = os.environ.get(DATA_ROOT_ENV, "").strip()
    return Path(configured).expanduser().resolve() if configured else checkout_root()


def state_dir() -> Path:
    return data_root() / STATE_DIR_NAME


def ops_dir() -> Path:
    return data_root() / OPS_DIR_NAME


def done_dir() -> Path:
    return data_root() / DONE_DIR_NAME
