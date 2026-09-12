# P10 reference-rig status

Durable handoff for roadmap P10. Update this file after each setup or live-test
phase so a usage interruption does not erase what is known.

## Delivered offline tooling

- `rig-create --game-version <v> --install <dir>` registers a dedicated old-game
  install in gitignored `bridgeforge-state/reference-rigs/` by default.
- The manifest hashes `starfarer.api.jar` and the bundled Java executable,
  records the Java version from its `release` file when available, the run
  command/working directory, and the saves directory. It never launches or
  changes the selected install, and refuses to replace an existing manifest
  unless `--replace` is explicit.
- `rig-doctor <install> --reference-manifest <json>` checks manifest/install
  identity drift, historical base-version declarations, running Java,
  dependency resolution, and working-copy drift. It explicitly skips the RC8
  probe, which is incompatible with historical APIs.
- Era sets are available as `era-0.8.1a`, `era-0.7.2a`,
  `era-0.97a-RC11`, `era-0.65.2a`, and `era-0.62a`. Known dependencies are
  represented; library builds lacking authority evidence are marked
  `EXACT_VERSION_UNRESOLVED` and produce warnings. `compat-set install` accepts
  the same `--reference-manifest`, allowing the dedicated historical install's
  plain core directory without weakening the default junction-only guard.
- `save-baseline` converts `save-inspect` evidence from a historical save into
  the hash-bound, no-verdict D2 schema. It captures requested class fields and
  ids, known-list counts, and optional mod namespace counts.

## Trust boundaries

- Selecting `--install` asserts that it is a dedicated historical copy.
  BridgeForge cannot independently prove it is not the player's primary
  install; the manifest records this limitation.
- The requested game version is an operator claim. The core API hash detects
  later drift but does not identify an official Starsector distribution.
- An era set identifies required mod ids, not authoritative downloads. Any
  dependency marked `EXACT_VERSION_UNRESOLVED` remains a setup blocker until an
  archive/version is supplied and its provenance recorded.
- A save baseline reports observations, never a compatibility verdict.

## Reference-install setup completed

On 2026-09-12 the operator identified dedicated installs under
`C:\Program Files (x86)\Fractal Softworks`. BridgeForge registered these
gitignored reference-rig manifests without changing the installs:

- `Starsector62` as claimed `0.62a`; API SHA-256
  `534f7cb68d00dc234c39c09a98f51e108456cbccd3412446c418cf59d4ec642a`.
- `Starsector7.2` as claimed `0.7.2a`; API SHA-256
  `9d77d2e3c87adb8692e5a21111ecff43f3c0a0ed847afd5aa086a984dfa42d4e`.
- `Starsector8.1` as claimed `0.8.1a`; API SHA-256
  `3e34be087b64cdd12b04999538626dbf5673ff8b9a35b5cd261b253fb1aa823c`.

All three identity, run-command, bundled-Java, isolation, and no-running-Java
checks passed. Each pristine install initially failed only the missing
`mods/enabled_mods.json` check. Folder labels remain operator claims; distinct
hashes establish distinct core bytes, not official distribution authenticity.

Exigency's untouched `0.7.2` archive was safely staged from
`In operation/Exigency/original/Exigency 0.7.2.zip` (SHA-256
`d7d9196b429b79c1d01ce25a0b04519982cbe47804da1cce45c5a9e11d8d2a80`).
Its metadata declares Starsector `0.7.2a` and names LazyLib and GraphicsLib.
The exact era dependencies were recovered from links preserved in archived
official mod threads and staged under Exigency's ignored `scratch/` area:

- `LazyLib_2.1.zip`, SHA-256
  `e7257fec8ad0d949397bc691a18f73193852d251f8ebdf28d7bcd7ca9f3f8983`;
  embedded version `2.1`, game version `0.7a`.
- `ShaderLib Beta 1.2.1b.7z`, SHA-256
  `37bb253494b8056c43257c626098e6174b50a205934a4f5c626b27e20d8f9b02`;
  thread/package label `1.2.1b`, embedded version `Beta 1.2.1`, game version
  `0.7.2a`.

Both archives passed format/path checks and contain the expected mod ids and
JARs. These hashes establish the retrieved bytes and make later drift visible;
there is no independent published checksum or signature, so vendor authenticity
is not claimed. The `era-0.7.2a` dry run resolved Exigency, LazyLib, and
ShaderLib with nothing missing.

The verified set is now installed in the dedicated `Starsector7.2` tree, with
only `lw_lazylib`, `shaderLib`, and `exigency` enabled. A repeat dry run reports
all three copies byte-identical and no work planned. `rig-doctor` now reports
`WARN`, not `FAIL`: every substantive check passes, with one warning because
LazyLib's authentic metadata says `0.7a` while the rig is claimed `0.7.2a`.
Contemporaneous 0.7.2a evidence shows LazyLib 2.1 running with that declaration,
so the warning remains visible but is not treated as a substituted-version fix.

During the install dry run, BridgeForge revealed that compatibility-set copying
did not include root-level runtime payloads. The copier now includes root JSON,
INI, CSV, JAR, properties, and version files; regression coverage proves these
files participate in both drift detection and installation. This was necessary
for `lazylib_settings.json`, `shaderSettings.json`, and the version descriptors.

## Setup and live work remaining

No historical game has yet been launched and no original behavior has yet been
observed.

1. Run Exigency 0.7.2a, save after the Avesta movement/market/known-list
   scenario, and import it with `save-baseline`.
2. Capture the matching revived-build baseline, then run `behavior-diff` and
   `coverage`. Record decisions in `expected-changes.json`.
3. Stage and run FlowerGod and Flu-X on the dedicated 0.8.1a install.

## Validation log

- 2026-09-12: 57 focused P10, rig-doctor, compatibility-set, D-series, and
  version-compatibility tests passed.
- 2026-09-12: 579 tests outside the known Windows boot-process and local JDK
  probe-build modules passed (1 skipped). The full 589-test run reproduced four
  locked boot-test log handles and two `Fatal Error: Cannot close compiler
  resources` probe-build failures; the two tests added after that full attempt
  passed in both focused and broad validation, and no P10 test failed.
- 2026-09-12: LIVE TEST NOT PERFORMED; LIVE VALIDATION REQUIRED.
- 2026-09-12: package build produced `bridgeforge-0.2.0-py3-none-any.whl`;
  metadata version and the new behavior/reference-rig modules plus era-set data
  were verified in the wheel (SHA-256
  `66d34115ac7693dfdc820db5ed9aa58f76cce85bc43d0500628f89c6ba367223`).
- 2026-09-12: three dedicated historical installs were registered and their
  manifest identity checks passed. Exact Exigency-era LazyLib and ShaderLib
  packages were located, hashed, archive-checked, staged, and resolved by an
  `era-0.7.2a` compatibility-set dry run. LIVE TEST NOT PERFORMED.
- 2026-09-12: fixed compatibility-set root-runtime-file copying; 17 focused
  copy-drift and compatibility-set tests passed. Installed the three-mod
  Exigency reference set, wrote the explicit enabled-mod list, and confirmed a
  no-op repeat dry run. Doctor status is `WARN` only for LazyLib 2.1's authentic
  `0.7a` declaration. LIVE TEST NOT PERFORMED; LIVE VALIDATION REQUIRED.
- 2026-09-12: all 580 tests outside the two previously identified
  environment/process-sensitive modules passed (1 skipped). The full 592-test
  run retained the same four locked boot-test log-handle errors and two
  `Fatal Error: Cannot close compiler resources` probe-build errors; no new or
  changed test failed.
- 2026-09-12: rebuilt `bridgeforge-0.2.0-py3-none-any.whl` and verified version
  metadata plus the changed copier and era-set data (SHA-256
  `b0b4635fbd8df0e1aedc25a1294e895509c37e46542b7c8eecabcedb9779d4f5`).

## State

`READY_FOR_0_7_2A_LIVE_REFERENCE_RUN`
