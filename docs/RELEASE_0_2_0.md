# Verified BridgeForge 0.2.0 publication

Published 2026-09-12 21:30:31 UTC:
[BridgeForge 0.2.0](https://github.com/Exxec/Project-BridgeForge/releases/tag/v0.2.0).
The observable release is public and marked pre-release, not draft.
Per owner direction, full-release promotion waits until the remaining validation
gates below are complete. The initially published stable designation was corrected;
the source tag and all three artifact digests remain unchanged.

Release source and remote annotated tag's peeled commit:
`e98522109a00c27dbe73e2bb1cffcd5978427ea8`.
Release metadata and changelog-derived notes identify that same SHA.
This document is a subsequent receipt, not a change to the published tag/source.

## Validation and artifacts

- Full guarded suite: 630 tests passed, one environment-dependent symlink skip;
  checkout/probe-release hermeticity PASS.
- All six exact-source CI jobs passed:
  [source CI](https://github.com/Exxec/Project-BridgeForge/actions/runs/34719944544).
- All six tag CI jobs passed before publication:
  [tag CI](https://github.com/Exxec/Project-BridgeForge/actions/runs/34720047080).
- Wheel and sdist built from a clean LF checkout of the release SHA. All 98
  wheel runtime/data files and all 165 tracked sdist files equal Git blobs.
  Required changelog, docs, license, helper and release policy are present.
- Isolated installed-wheel checks passed version 0.2.0, moved Vacuum discovery
  without inferred readiness, and bundled Exigency license denial. The freshly
  downloaded draft wheel also passed installed version/license checks.
- All three assets freshly downloaded from both draft and public release match
  local hashes and GitHub SHA256 digests. Public source metadata and notes were
  checked after publication, not inferred from tag/CI alone.

| Asset | SHA256 |
|---|---|
| bridgeforge-0.2.0-py3-none-any.whl | e4b42fcb495779abdb2bf9e1debf7089ae0b92025e42d1a09d20bf1cc3e12cc5 |
| bridgeforge-0.2.0.tar.gz | a702d819ab29f8cc2a791c64b3ed52d0eacd077b4d69da1c8fbab0fbbee974ff |
| SHA256SUMS.txt | 378fbd4b3fb78c08ff24857eeb9f328b080b4ccd5a339619111997b03291664f |

Preflight caught a missing sdist changelog. The manifest was corrected, tests
rerun, and final assets rebuilt before tagging. Superseded 3eb1fa3 packages were
never uploaded. No existing tag or published asset was overwritten.

## Scope and handoff

Assets are tool-only wheel/sdist/receipts: no local game install, original mod,
rig or save. Repository-oriented probe/PowerShell workflows use the tagged Git
checkout. No mod was promoted or certified. LIVE TEST NOT PERFORMED.

Local evidence: `In operation/_attic/P12D_PUBLICATION.md`; final assets/notes at
`p12d-final-dist`; clean source at `p12d-release-final-lf`; independent downloads
at `p12d-draft-download` and `p12d-public-download`. Logs are beside them. On
interruption inspect existing tag/release/receipts, never recreate blindly.

P12 is complete; the overall roadmap is not. Remaining acceptance includes
approved rig boot/probe reproduction and vanilla/fixed-mod evidence, interactive
and save/load checks, P6 owner thresholds/real SPW report, and P10/D2/D5/D6
historical behavior/risk/unknown closure. Research retains evidence/scope gates.
Dedicated installs, staging and tool publication are not observed runtime proof.

Next tranche: refresh remaining acceptance evidence and prepare a scoped rig-only
validation plan. Keep unknown results explicit; do not mark the overall goal
complete or relabel existing mod reports merely to pass promotion.
