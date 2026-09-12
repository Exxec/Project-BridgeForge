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

## External setup still required

No historical Starsector install was present on 2026-09-12, so no game was
launched and no original behavior was observed.

1. Supply dedicated installs for 0.7.2a and 0.8.1a first.
2. Register each with `rig-create`, then run `rig-doctor` against its manifest.
3. Locate and provenance-check Exigency's historical LazyLib and GraphicsLib
   builds. Do not substitute current libraries merely because their ids match.
4. Run Exigency 0.7.2a, save after the Avesta movement/market/known-list
   scenario, and import it with `save-baseline`.
5. Capture the matching revived-build baseline, then run `behavior-diff` and
   `coverage`. Record decisions in `expected-changes.json`.
6. Repeat on the shared 0.8.1a install for FlowerGod and Flu-X.

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

## State

`READY_FOR_REFERENCE_INSTALL_SETUP`
