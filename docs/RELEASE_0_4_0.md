# Verified BridgeForge 0.4.0 publication

Published 2026-11-17 22:55:13 UTC:
[BridgeForge 0.4.0](https://github.com/Exxec/Project-BridgeForge/releases/tag/v0.4.0), on the owner's word the same day
("Yes" to tagging and publishing v0.4.0; ROADMAP-3 96.4). It is public, marked pre-release, not a draft, and not marked
Latest (no release is). As with 0.2.0, full-release promotion waits on the live work listed below, and it is the owner's call.

Release source: `128830f1b6f4420b8d343f4cbb153b2593540323`, the merge of #112, which dated the notes. The remote annotated
tag `v0.4.0` (object `ac236617845a98244bdc03941dfce06ae1b601ce`) peels to that commit. This document is a later receipt,
not a change to the tag or its source.

## Validation before tagging

- **Full guarded suite** at the release commit, in a clean worktree, with the project `.venv` and JDK 25: 2969 tests, OK
  (skipped=12), 630.7 s. Hermeticity PASS.
- **Main CI** on the release commit passed all nine jobs:
  [run 44192728646](https://github.com/Exxec/Project-BridgeForge/actions/runs/44192728646). The jobs were lint, `uv.lock` in
  sync, dependency audit, the shared fixtures, fast and slow tests on Ubuntu and Windows with Python 3.15, and coverage.
  - Since #107 (96.5 C3), a push runs CI only on main, so the tag push started no run of its own. The tag points at the
    commit this run tested.
- **Wheel and sdist** were built with `pyproject-build` from a clean checkout of the release commit:
  - Every packaged file that Git tracks equals its blob at that commit: 400 files in the wheel, 721 in the sdist.
  - The wheel has the package, its CLI and `release_policy.json`. The sdist has CHANGELOG, LICENSE, README, pyproject and
    the release policy.
- **Installed-wheel check** in a fresh Python 3.15 environment, first on the local wheel before tagging. It was repeated at
  23:11 UTC on the wheel downloaded from the public release, and that run is logged with the evidence:
  - the version reads 0.4.0, imported from site-packages;
  - `release_policy.json` is installed with it, with 176 entries;
  - Scrapyard reads `local_only`;
  - the CLI's `--help` exits 0.

## Publication checks

- **The draft:** its three assets were downloaded into an empty folder.
  - They match `SHA256SUMS.txt`, which is byte-identical to the local copy, and GitHub's per-asset SHA-256 digests.
  - The draft's notes equal the notes file.
- **After publishing:** the assets were downloaded again from the public release, with the same hashes.

| Asset | SHA256 |
|---|---|
| bridgeforge-0.4.0-py3-none-any.whl | 10f1e933031ba8b5f4642be19f0eaac853ca583089daf46e7cec4fac8f93f37c |
| bridgeforge-0.4.0.tar.gz | dce4ca8b83db7ede7cafb9c02ce344430563aaf87934703406e56d0636457158 |
| SHA256SUMS.txt | e96487d853efce3e1e36115cc0d4fa68fb4ca007d7d0c1c37b8ebaf099accc96 |

The release notes are CHANGELOG.md's 0.4.0 section (144 entries) under a short header. 0.3.0 was tagged (`v0.3.0`) but
never published, so readers coming from 0.2.0 should also read 0.3.0's section. No existing tag or release was changed.

## Scope

- **Contents:** the assets are tool-only. They contain no game files, original mods, rigs or saves.
- **Workflows:** the wheel holds only the `bridgeforge` package. The in-game probe (`probe-mod/`) and `tools/bf-test.ps1` are
  not in it. The revival guide runs its commands from the tagged Git checkout; the sdist also carries copies.
- **Requirements:** the package requires Python 3.15 or later. Salvor's pin, `bridgeforge>=0.4,<0.5`, covers it (94 D4).
- **Not a live test:** publishing the package promoted or certified no mod. Each mod's live evidence is in its own revival
  report.

Live testing is paused (owner, 2026-11-17). The live work still open:
- The first live run with the `canSkipTutorial` pin (93.28).
- Bultach Coalition: one re-run, then its archive (93.41, 93.44).
- UAF: its round-2 re-run (93.37).
- The JDK 27 comparison run (93.43).
- A StarsectorPrepatcher release that knows RC7 (93.42).
- 96.2's ports.

Local evidence on the owner's machine, in the gitignored `In operation/_attic/release-0.4.0/`:
- the built assets;
- both downloads;
- the notes and the draft's body;
- the suite, CI and installed-wheel logs;
- `verify_dist.py` (the blob check) and `installed_wheel_check.py`;
- the JDK 27 copy and setup scripts of 93.43.

Before any later re-publication, look at the existing tag and release first. Never recreate them blindly.
