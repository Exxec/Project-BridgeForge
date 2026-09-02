# Corpus evidence sources

Bridgeforge uses externally supplied mods and repositories to test evidence
quality. They are not copied into this repository and their code is never run.

## Current intake

- Vayra's Sector is represented by the user-provided release archive. Its scan
  is a legacy campaign/data specimen, including parser-tolerance and encoding
  cases.
- Dassault-Mikoyan Engineering is represented by the user-approved installed
  mod folder. Its 3,399-file scan provides a large legacy campaign/code
  specimen with Java 17 bytecode and untrusted historical metadata/data
  syntax; it is retained only as aggregate evidence.
- [Ship/Weapon Pack](https://bitbucket.org/DarkRevenant/ship-weapon-pack/src/master/)
  is a source-layout and version-lineage specimen. Its metadata is beneath
  `src/`, so scanning a checkout should report a wrapper layout rather than
  silently treating the checkout as a release folder.
- [Nexerelin](https://github.com/Histidine91/Nexerelin) is a maintained modern
  control. Its 0.12.2-series tags and large source/data tree help measure
  false-positive rates.
- [LazyLib](https://github.com/LazyWizard/lazylib) is dependency archaeology.
  Its distribution assets sit under `mod/`, separate from source and docs.
- [MagicLib](https://github.com/MagicLibStarsector/MagicLib) is dependency
  archaeology and a build-artifact attribution specimen.
- [Void-Tec](https://github.com/Schaf-Unschaf/Void-Tec) `develop`
  (`9cd8121f90e89c972e55fe1f6256f20af6a8fa7b`) is a user-approved,
  compile-validated 0.95a-RC15 to 0.98a source migration specimen. It covers
  Lombok annotation processing, optional Console Commands/Industrial Evolution
  APIs, MagicLib `MagicRender`, and the 0.98a custom UI/dialog callback
  signatures. It is not runtime- or save-certified and must not be used as an
  automatic migration rule source.

## Release-lineage intake

These are reproducible tag/commit pairs used to identify candidates for human
review. A changed path is not a migration mapping.

| Project | Older release | Newer release | Relevant changed paths |
| --- | --- | --- | ---: |
| [Nexerelin](https://github.com/Histidine91/Nexerelin) | `v0.12.1` (`c602e9b58219`) | `v0.12.2c` (`a669f4d0740e`) | 227 |
| [LazyLib](https://github.com/LazyWizard/lazylib) | `2.8` (`32d64ab40e04`) | `3.0` (`3b5621ba12aa`) | 21 |
| [MagicLib](https://github.com/MagicLibStarsector/MagicLib) | `1.5.8-dev05` (`aa5353c295b3`) | `1.5.8-dev08` (`7b4f1b3bad81`) | 29 |
| [Ship/Weapon Pack](https://bitbucket.org/DarkRevenant/ship-weapon-pack/src/master/) | `Ship_and_Weapon_Pack_1.1.0` (`c593d4dde3e6`) | `SWP_1_1_3` (`1c311b794a6f`) | 14 |

No rule has been derived from these comparisons. Each candidate needs a small,
independently verified before/after behavior fixture before it can enter a
migration pack.

## Rules for using this evidence

- Record only aggregate scan results or deliberately sanitized fixtures.
- Do not commit mods, jars, proprietary assets, or full upstream source trees.
- Do not convert API similarity into a migration rule. A library rule needs
  release-specific provenance, a minimal before/after fixture, idempotence,
  conflict checks, compile validation, and save-risk review.
- Treat source checkouts and release folders as different layouts. A nested
  `mod_info.json` is evidence for manual root selection, not permission to
  rewrite or relocate files.
