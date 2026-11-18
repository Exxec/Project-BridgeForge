# Verified BridgeForge 0.4.1 publication

Published 2026-11-18 01:02:07 UTC, the evening of 2026-11-17 locally (the date CHANGELOG gives):
[BridgeForge 0.4.1](https://github.com/Exxec/Project-BridgeForge/releases/tag/v0.4.1), on the owner's word of 2026-11-17
("yes" to tagging a 0.4.1 with the security fixes and to a known-issue line on v0.4.0's page; ROADMAP-3 96.7). It was
published as a pre-release, not marked Latest. The same evening the owner made it a full release ("You can make it a full
release instead of pre-release"): at 01:23 UTC it became a full release marked Latest, the first full BridgeForge release.
0.4.0 and 0.2.0 stay pre-releases.

Release source: `ed77cbb87d5d5426821105e77b7b5eac899a6243`, the merge of #121, which assembled the notes and set the
version. The remote annotated tag `v0.4.1` (object `ce1433f3c6b2dc8495b5ba9c3ca0da1e18ad88a0`) peels to that commit. This
document is a later receipt, not a change to the tag or its source.

## What it fixes

The four problems found after v0.4.0 was published. Each let a mod's own files steer a tool BridgeForge starts.
[RELEASE_0_4_0.md](RELEASE_0_4_0.md) describes them under "Known issues found after publication".

| Item | What a mod could do in v0.4.0 | Fixed by |
|---|---|---|
| 93.45 | put JVM options on javap's command line through a jar entry's name (`-J...`) during a scan | #113 |
| 93.46 | make `compile-check` run an annotation processor from its own jar, through a line break in a mod_info.json `"jars"` entry | #115 |
| 93.47 | run a command through cmd.exe or PowerShell during `mass-test`, through its mod id | #116 |
| 93.48 | make `src-to-jar` overwrite an existing file outside its scratch folder, through a jar entry stored with backslashes | #117 |

It also carries the v0.4.0 receipt (#114). Nothing else is new: 96.5's performance items (P1 #118, P2 #119, P7 #120) and
later work wait for the next version, whose fragments go under `## 0.4.2 (unreleased)`.

## Validation before tagging

- **Full guarded suite** at the release commit, in a clean worktree, with the project `.venv` and JDK 25: 2987 tests, OK
  (skipped=12), 635.2 s. Hermeticity PASS.
- **Main CI** on the release commit passed all nine jobs:
  [run 44210899558](https://github.com/Exxec/Project-BridgeForge/actions/runs/44210899558). Since #107 a push runs CI only on
  main, so the tag push started no run of its own. The tag points at the commit this run tested.
- **Wheel and sdist** were built with `pyproject-build` from a clean checkout of the release commit:
  - Every packaged file that Git tracks equals its blob at that commit: 400 files in the wheel, 722 in the sdist.
  - The wheel has the package, its CLI and `release_policy.json`. The sdist has CHANGELOG, LICENSE, README, pyproject and
    the release policy.
- **Installed-wheel check** in a fresh Python 3.15 environment, on the local wheel at 00:50 UTC, before tagging. It was
  repeated at 01:02 UTC on the wheel downloaded from the public release. Both runs are logged with the evidence:
  - the version reads 0.4.1, imported from site-packages;
  - `release_policy.json` is installed with it, with 176 entries;
  - Scrapyard reads `local_only`;
  - the CLI's `--help` exits 0.

## Publication checks

- **The draft:** its three assets were downloaded into an empty folder.
  - They match `SHA256SUMS.txt`, which is byte-identical to the local copy, and GitHub's per-asset SHA-256 digests.
  - The draft's notes equal the notes file.
- **After publishing:** the assets were downloaded again from the public release, with the same hashes. The blob check
  was run once more on that download, against the tag. Every tracked file again equals its blob (wheel 400, sdist 722),
  and the `SHA256SUMS.txt` it wrote is byte-identical to the published one.

| Asset | SHA256 |
|---|---|
| bridgeforge-0.4.1-py3-none-any.whl | 614a0bb1f351a68e665629ac0f2a20eeb9a5b6f9018157a2e7a5567884317cc0 |
| bridgeforge-0.4.1.tar.gz | 193e58e5c455fd4c975599256c40b0e59ffdf82ed59c05e139bc5242706a2dd2 |
| SHA256SUMS.txt | 19351930a90c7ab8c2e9b89b0c10995e5ca2a6bd34e45d1e9b6b18ad81f57c06 |

The release notes are CHANGELOG.md's 0.4.1 section (five entries) under a short header.

- **v0.4.0's release page:** after 0.4.1 was published, its known-issue note was rewritten. It now names all four
  problems and links v0.4.1.
  - Only that paragraph changed. The stored body was read back and equals the intended text.
  - v0.4.0 is still a pre-release, not a draft, and not marked Latest.
- **Tags and other releases:** no existing tag or release was changed in any other way.

## Promotion to a full release

At 2026-11-18 01:23:47 UTC, on the owner's word, v0.4.1 was edited to a full release (not a pre-release) and marked Latest.
- **Notes:** the opening sentence of the notes said the release was a pre-release whose promotion waited on live
  acceptance work. It now reads "It is a full release: the owner promoted it from pre-release on 2026-11-17. 0.4.0 and 0.2.0
  stay pre-releases." Nothing else in the notes changed.
- **Read back at 01:23:55 UTC:**
  - not a draft and not a pre-release, and `releases/latest` returns `v0.4.1`;
  - the stored notes equal the intended text;
  - the three assets' GitHub digests are the ones in the table above;
  - the tag still peels to `ed77cbb`;
  - v0.4.0 is still a pre-release.
- **Not a live test:** the promotion certifies the package, as built and checked above. It certifies no mod.

## Scope

- **Contents:** the assets are tool-only. They contain no game files, original mods, rigs or saves.
- **Workflows:** the wheel holds only the `bridgeforge` package. The in-game probe (`probe-mod/`) and `tools/bf-test.ps1` are
  not in it. The revival guide runs its commands from the tagged Git checkout; the sdist also carries copies.
- **Requirements:** the package requires Python 3.15 or later. Salvor's pin, `bridgeforge>=0.4,<0.5`, covers it (94 D4).
- **Not a live test:** publishing the package promoted or certified no mod. Each mod's live evidence is in its own revival
  report.

Live testing is wrapped up for now (owner, 2026-11-17): Test1 is in use. The live work still open:
- The first live run with the `canSkipTutorial` pin (93.28).
- Bultach Coalition: one passing re-run, then its archive (93.41, 93.44). SR6 and SR7 did not pass (93.49, 93.50).
- UAF: its round-2 re-run (93.37).
- The JDK 27 comparison run (93.43).
- A StarsectorPrepatcher release that knows RC7 (93.42).
- 96.2's ports.

Local evidence on the owner's machine, in the gitignored `In operation/_attic/release-0.4.1/`:
- the built assets;
- both downloads;
- the notes and the draft's body;
- v0.4.0's release body before and after its edit, and v0.4.1's before and after the promotion;
- the suite, CI, build, blob-check and both installed-wheel logs, and a note of the suite's commit and worktree state;
- the promotion log, with the asset digests before and after it;
- the scripts:
  - `verify_dist.py` (the blob check);
  - `installed_wheel_check.py`;
  - `make_041_notes.py` (the notes);
  - `v040_link_041.py` (v0.4.0's note);
  - `v041_full_release_notes.py` (the promoted notes).

Before any later re-publication, look at the existing tag and release first. Never recreate them blindly.
