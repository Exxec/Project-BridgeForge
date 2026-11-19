# Verified BridgeForge 0.4.2 publication

Published 2026-11-19 02:36:42 UTC, the evening of 2026-11-18 locally (the date CHANGELOG gives):
[BridgeForge 0.4.2](https://github.com/Exxec/Project-BridgeForge/releases/tag/v0.4.2), on the owner's word of 2026-11-18
("Go ahead with 0.42 release", read as 0.4.2, the version after 0.4.1; ROADMAP-3 96.8). It was published as a full release
marked Latest, as 0.4.1 became. 0.4.1 stays a full release; 0.4.0 and 0.2.0 stay pre-releases.

Release source: `4e71782b5655410c341df7c9fe0dbc6e0eaae20c`, the merge of #141, which assembled the notes and set the
version. The remote annotated tag `v0.4.2` (object `c5eb5f16c285ff444372e6f81e100b0f93b5dd96`) peels to that commit. This
document is a later receipt, not a change to the tag or its source.

## What it carries

The 22 changelog entries since v0.4.1, under `## 0.4.2 (2026-11-18)` in CHANGELOG:
- **Scans:** 96.5's performance items P1-P4 and P7 (javap once per jar, provider lookups per provider, one scan per
  revive, each file's comments blanked once, the core read once per process).
- **Saves and the rig:** save-doctor's version-object, alias and FACTION_UNDEFINED fixes (93.52, 93.53, 93.55), the
  0.98.5a-RC7 main-menu reader (93.54), and rig-doctor and dependency-substitutes judging mods against the core's own build
  (96.5 A8).
- **CI and tooling:** tracked git hooks, docs-only CI, pre-push tiers, one JDK, shared CI setup with timeouts and a pinned
  ruff, a registry guard for the tests, progress for the long-running commands, the pre-push report check's shared status
  list (96.5 C1, C3-C8, A3, A9).
- **Records:** the Bultach and UAF archives, the 0.4.1 receipt, and two roadmap notes.

## Validation before tagging

- **Full guarded suite** at the release commit, in the detached worktree `BridgeForge-v042-suite`, with the project
  `.venv` and JDK 25: 3075 tests, OK (skipped=12), 699.5 s, finished 02:34:29 UTC. Hermeticity PASS; 0 uncommitted or
  untracked paths afterwards.
- **Main CI** on the release commit passed all ten jobs that ran (the documentation-only job skips on a push):
  [run 44443836062](https://github.com/Exxec/Project-BridgeForge/actions/runs/44443836062). The tag push started no run of
  its own; the tag points at the commit this run tested.
- **Wheel and sdist** were built with `pyproject-build` (build 1.6.1) from a second clean worktree of the release commit.
  The build printed the same 26 setuptools package-discovery warnings as 0.4.1's.
  - Every packaged file that Git tracks equals its blob at that commit: 401 files in the wheel, 732 in the sdist. The
    sdist's 8 other files are ones the build generates (egg-info, `setup.cfg` and two `PKG-INFO`).
- **Installed-wheel check** in a fresh Python 3.15.2 environment, on the local wheel before tagging and again on the wheel
  downloaded from the public release:
  - the version reads 0.4.2, imported from site-packages;
  - `release_policy.json` is installed with it, with 178 entries;
  - Scrapyard reads `local_only`;
  - the CLI's `--help` exits 0.

## Publication checks

- **The draft:** created with `--verify-tag`, not a pre-release. Its three assets were downloaded into an empty folder.
  - They match `SHA256SUMS.txt`, which is byte-identical to the local copy, and GitHub's per-asset SHA-256 digests.
  - The draft's notes equal the notes file (the stored body ends with one more newline).
- **Publishing:** at 02:36:42 UTC the draft was published as a full release marked Latest. Read back: not a draft, not a
  pre-release, `releases/latest` returns `v0.4.2`, v0.4.1 is still a full release, and the tag still peels to `4e71782`.
- **After publishing:** the assets were downloaded again from the public release, with the same hashes. The blob check was
  run once more on that download, against the tag: every tracked file again equals its blob (wheel 401, sdist 732), and the
  `SHA256SUMS.txt` it wrote is byte-identical to the published one.

| Asset | SHA256 |
|---|---|
| bridgeforge-0.4.2-py3-none-any.whl | 3fa9558a82718f685aac81acf8446ebd6fe61fb6311bc2bd63c67571a082d794 |
| bridgeforge-0.4.2.tar.gz | a6450bda284b0e2c8b80135ee0696281b7f3ffae12db0513899198df5b726a06 |
| SHA256SUMS.txt | 3cf28a4608c712f9f508f9f52ef09bf7b717cccfc2aa6246164a3185c65a9a0e |

The release notes are CHANGELOG.md's 0.4.2 section (22 entries) under a short header.

## Scope

- **Contents:** the assets are tool-only. They contain no game files, original mods, rigs or saves.
- **Workflows:** the wheel holds only the `bridgeforge` package. The in-game probe (`probe-mod/`) and `tools/bf-test.ps1` are
  not in it. The revival guide runs its commands from the tagged Git checkout; the sdist also carries copies.
- **Requirements:** the package requires Python 3.15 or later. Salvor's pin, `bridgeforge>=0.4,<0.5`, covers it.
- **Not a live test:** publishing the package promoted or certified no mod. Each mod's live evidence is in its own revival
  report. One check on Test1's 0.98.5a rig after A8 merged (2026-11-18): rig-doctor's `enabled_mods_resolve` compares with
  `0.98.5a`, read from the rig's core, and warns only about the four enabled mods that still declare `0.98a` (LazyLib,
  MagicLib, AshLib, the probe).

Local evidence on the owner's machine, in the gitignored `In operation/_attic/release-0.4.2/`:
- the built assets, the draft download and the public download;
- the notes and the draft's stored body;
- the suite log and its provenance note, the CI, build, blob-check, publish and both installed-wheel logs;
- the scripts: `verify_dist.py` (the blob check), `installed_wheel_check.py` and `make_042_notes.py` (the notes).

Before any later re-publication, look at the existing tag and release first. Never recreate them blindly.
