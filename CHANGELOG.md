# Changelog

## Unreleased
- Hygiene (ROADMAP P15 item 10): duplicate roadmap entries from the local/cloud merge are merged and this session's P14 items 29-36 renumbered 47-54; `docs/LOCAL_HANDOFF.md` rewritten for the kept commands; `revive` no longer makes each fixer rescan the whole mod.
- **Decisions come with their options (ROADMAP P15 items 7-9).** `vendor-copy --plan FILE --to DIR` copies everything a `vendor-plan` lists (any kind, not just hull mods), re-checked against the provider, with SHA-256s for PROVENANCE.md. `revive --draft-report` drafts REVIVAL_REPORT.md/REVIVAL_PLAN.md when a run leaves nothing to do. Missing-content packets now show the substitute strategy, a vendor plan and a strip plan side by side, with the commands to act on each. `revival-report-draft` honours the mod's accepted-findings baseline.
- **One command per job (ROADMAP P15 items 5-6).** The local/GitHub merge left two versions of seven commands; the `-local` variants, `archive-index`/`archive-search` and `provider-index-update` are removed in favour of `strip-plan`, `diff-data`, `verify-shadow`, `dependency-graph`, `rebuild-from-reference`, `corpus-index` and `provider-index build`. `vendor-plan` and `vendor-copy` both stay. An existing folder-format provider cache still loads. `revive` now runs the `rules-firebest-populate-options`, `personality-id-unknown` and `shiproles-wing-id` fixers (with approval, as before), and `revive`/`finding-stats` skip findings a mod's baseline accepts.
- **`corpus-recheck` now honours a mod's own accepted-findings baseline (ROADMAP P14 item 46).** The mechanism existed on both ends already — `scan --write-baseline` writes the file, `scan --baseline` reads it — but the corpus recheck ignored it, so deliberately accepting a reviewed finding did nothing: the mod kept reporting as a `REGRESSION` on every sweep forever. `_recheck_one` now picks up `working/reports/baseline*.json`, reporting `baselined_findings` and the baseline path so the suppression is visible rather than silent; a corrupt or unreadable baseline is ignored and its findings still count, because a broken file must never hide a real regression. Found while acting on an instruction to baseline Xenoargh-FX-Example's intentional preset overrides — writing the baseline *looked* like it worked while the recheck would have gone on flagging the mod. Verified on the real mod: 19 findings baselined, MANUAL 3 → 0.
- **Better-Deserving-Smods first revival pass, and a 0.95.1a reference rig registered (ROADMAP P14 item 45).** Findings 12 → 4; `compile-check` PASS (0 errors, 50 loose scripts — its 2023 code compiles clean on RC8 with no API drift). **Fixed 7 Janino launch blockers (10 instances):** BDS ships no jar and no core jar supplies any `data/hullmods` class, so all 50 loose scripts are Janino-compiled at startup; 10 typed for-eaches over generic collections rewritten as raw `Iterator` with explicit casts (every one over a real collection — an array for-each is fine under Janino and has no `.iterator()`, so rewriting one would break it). Second mod in two days where `loose-script-janino-risk` caught a live, unshadowed blocker. **Registered 0.95.1a as a reference rig** — the highest-value one in the set, since **255 corpus mods declare a 0.95.x base** against 40 already on 0.98a. With it, BDS's core defect is now measured exactly instead of inferred: it **silently reverts 260 lines** of vanilla's own post-0.95.1a hullmod changes while deliberately removing only 10. A first pass using the 0.9a rig as a proxy reported 255/1 and was described as an upper bound; it was actually an **under-count**, because it silently skipped files with no 0.9a counterpart — a concrete argument for era-matched references over near-miss proxies.
- **Maelstrom Interstellar Imperium Unofficial Expansion closed out (ROADMAP P14 item 44): ESCALATIONS E8 resolved, `READY_WITH_REVIEW_ITEMS`.** Its long-standing "compile FAIL, 42 errors" was a classpath artifact — base Interstellar Imperium is installed only in the real game install, outside both default provider roots; with `--providers` pointed there it is PASS, 0 errors. Verified the one genuinely open risk from E8 addendum 2: the expansion's 8 `rules.csv` override row ids were enumerated against base II 2.5.2, but 2.6.9 is installed, and a drifted id fails **silently** — all 8 still match, every base row referencing `II_TitanStrike` covered. **Also found and fixed a real latent launch blocker:** pre-existing `imperiumVectorThruster.java` used a typed for-each over a generic collection, which Janino 2.7.8 cannot compile (Fatal before the main menu); confirmed genuinely exposed (base II's jar does not supply that class, unlike the two Titan scripts) and rewritten as a raw `Iterator` with an explicit cast — the first live, unshadowed instance `loose-script-janino-risk` has caught in this corpus.
- **`replace`-array hygiene, identical-copy detection, and cross-mod row-id collisions (ROADMAP P14 item 43).** Four new checks, all mechanical: **`replace-entry-ignored`** (a `replace` entry ending in `settings.json` — RC8's `ModManager` silently drops exactly those, so the declaration never takes effect and the author is never told); **`replace-entry-stale`** (naming a file the mod does not ship; Rebal has 5); **`settings-json-override-breadth`** (how many vanilla settings keys a mod overrides — since settings.json can only ever merge, each one silently wins over the current game's value; Rebal's 29-of-616 is a deliberate tuning set, a few hundred would be a stale wholesale copy); and **`vanilla-file-identical-copy`** (a file byte-identical to vanilla's at the same path, which overrides vanilla with vanilla and changes nothing — **613 across 13 mods** corpus-wide; collected inside the existing shadow walk rather than a second pass, after item 42's O(n²) lesson). Plus cross-mod **`merge_table_row_collisions`**: two mods shipping the same `hull_mods.csv` row id is last-loaded-wins too, and is exactly what a file-path collision becomes once both mods repoint off vanilla's path — without it, acting on item 42's advice would have hidden the conflict from our own tooling. **Also fixed a real defect in item 42's `vanilla-script-shadow-repointable`:** it did not skip byte-identical files, so it advised repointing 14 no-op copies when the right advice is to drop them.
- **Two new checks for the vanilla-script-shadow pattern, from a design pass on Xenoargh-Rebal and Maelstrom II Unofficial Expansion (ROADMAP P14 item 42).** **`vanilla-script-shadow-repointable`** (scanner, REVIEW): a mod replacing a vanilla *script* at vanilla's own path usually need not - the class is resolved by a CSV row's `script` column (or a `.system` `statsScript` key) and those CSVs merge by row id, so renaming the class and repointing the mod's own row gives identical behaviour with no shadow, and survives the next vanilla update instead of silently reverting it (49 repointable instances across 3 mods; all 50 of Rebal's). **`vanilla_script_shadow_collisions`** (`cross-mod-analyze --vanilla-core`): two mods shadowing the *same* vanilla script is a conflict, not duplication - load order picks a winner silently. Rebal and Better-Deserving-Smods collide on 22 hullmod scripts; the check reports whether the collision can be folded into a shared library (`REPOINT_TO_SHARED_LIBRARY`) or needs a CSV row first. Also established by bytecode: **`"replace"` in mod_info.json is live in RC8** (`ModManager` -> `ModSpec.getFullOverrides()`), and it **silently skips any entry ending in `settings.json`**, so that file can never be fully replaced by a mod. Maelstrom's long-standing "42 compile errors" turned out to be a classpath artifact - base Interstellar Imperium is installed only in the real Starsector install, and pointing `--providers` at it gives PASS with 0 errors.
- **Thule-Legacy triage: 37 MANUAL findings -> 0, `compile-check` FAIL (65 errors) -> PASS (ROADMAP P14 item 41).** LazyLib declared as a real hard dependency (the mod's own code throws if it's missing); Nexerelin deliberately left undeclared as a real soft one (guarded by `isModEnabled`, matching real corpus precedent for keeping optional integrations undeclared) - verified its code still compiles clean via a one-off classpath check. RC8's six new `ShipSystemStatsScript` `*Override` methods and `OnHitEffectPlugin.onHit`'s new parameter fixed via the existing fixer (`--allow-shadowed-edit`, since this mod's whole loose-script tree is jar-shadowed); hand-fixed `FakeEntity`'s 8 missing `CombatEntityAPI` methods and two changed/removed `AddMarketplace.java` calls. **New scanner check `removed-market-condition-id`**, a genuine corpus-wide gap: RC8's colony overhaul turned four 0.8-era `Conditions` ids (`MILITARY_BASE`/`ORBITAL_STATION`/`TRADE_CENTER`/`HEADQUARTERS`) into buildable `Industries` instead - a different API, not a rename; real precedent for the mapping already existed in Exigency's own code, also found live in 3 Tore-Up-Plenty files (noted for later). Rebuilt the shipped jar surgically (9 already-shipped classes recompiled and byte-replaced, not a whole-tree `rebuild-jar --install`, after that full rebuild's own comparison flagged 4 separate judgment calls about newly-added classes that deserved a deliberate decision rather than a side effect). **Fixed a real tooling gap along the way: `compile_loose_scripts` now separates a jar-shadowed loose script's compile errors (which can never block the game) from the blocking status**, found because this mod's correctly-unedited, jar-shadowed `TLPlugin.java` was causing a `compile-check` FAIL it could never actually cause in game.
- **Corpus-wide check on `mod-info-jar-missing` prevalence found only two instances total (ROADMAP P14 item 40).** Same prevalence-check discipline item 37 established: only Firestorm-Federation (fixed by hand in item 39) and Covert-Cargoliners carry it, so no generic fixer is warranted. Covert-Cargoliners' `"jars":["jars/example.jar"]` is unedited mod_info.json template boilerplate — no jar or `.java` source exists anywhere in the mod — fixed by removing the key. Also this mod's first full revival pass: drafted `REVIVAL_REPORT.md` via `revival-report-draft --apply` off the post-fix scan (0 MANUAL, 6 REVIEW, compile PASS), `READY_FOR_LIVE_TEST`.
- **New fixer for `shiproles-wing-id`, plus a new `HullModEffect.isSModEffectAPenalty` contract entry (ROADMAP P14 item 39).** 0.98a's `shipRoles` only resolves variant ids; a fighter-wing id there is fatal at load. The fixer renames each flagged key to that wing's own `wing_data.csv` `variant` column value, sharing its surgical rename/merge machinery with `faction-trait-weight-legacy-personality-id`'s own fixer. Applied to Scion-Collective and Firestorm-Federation (both now 0 MANUAL). Also: RC8's `HullModEffect` interface gained `isSModEffectAPenalty()` (in addition to the already-tracked `showInRefitScreenModPickerFor`) since whatever version several old mods were written against; new contract entry + fixer default (`false`, javap-verified against vanilla's `BaseHullMod`). Firestorm-Federation itself was fixed at the root instead - its own `BaseHullMod.java` now extends RC8's real `BaseHullMod` rather than implementing `HullModEffect` directly, inheriting every current and future default. Also fixed on Firestorm-Federation: a stale `mod-info-jar-missing` entry (the mod never shipped a jar) and a genuinely-dead, 0-byte `invalid-csv` file (moved to `scratch/`).
- **Fixed: `external-mod-api-import` no longer fires MANUAL for a dependency `mod_info.json` already declares (ROADMAP P14 item 38).** A declared dependency is hard-required - Starsector refuses to enable the mod without it - so direct API use needs no compatibility shim. New id `external-mod-api-import-declared` (SAFE) for this case (kept separate from the MANUAL id so `cross_mod.py`/`integration_scenarios.py`/`library_api.py` still see every direct external-API use via `dependency_compatibility`). Found on Arkgneisis (MagicLib, declared, its only remaining MANUAL finding); also reclassified a real instance each on Vayra-Merged and Void-Tec while correctly leaving their separate, genuinely-undeclared findings (Console Commands, Industrial Evolution) MANUAL.
- **New fixer for `faction-trait-weight-legacy-personality-id`, applied to 8 real corpus mods (ROADMAP P14 item 37).** A corpus-wide check for the same pattern found the identical `cowardly`/`suicidal`/`fearless`-weight-1 shape (byte-for-byte) in 10 `.faction` files across 8 more mods beyond Zorg18 - a shared template lineage, not a one-off. `fix --finding faction-trait-weight-legacy-personality-id --apply` renames `cowardly`->`timid` and merges `suicidal`+`fearless`'s weights into one `reckless` entry, as a surgical text edit (comments/formatting/key order survive). Applied for real to Antediluvians, Batavia, Cobalt-Arms, Firestorm-Federation, Gekelonians, Independant-Mining-Faction, Qualljom and Renis-Imperium.
- **New scanner check `faction-trait-weight-legacy-personality-id` (ROADMAP P14 item 36).** A `.faction`'s `traits.<role>` block weights personality ids for random officer generation; a 0.6-era id there (`cowardly`/`suicidal`/`fearless`) is the same crash class as `personality-id-unknown` (an officer drawn with it gets a null personality, Fatal dialog on deploy) reached through faction generation instead of a hard-coded `setPersonality()` call. Found reading Zorg18's own report by hand (it had flagged and deferred this exact bug); verified `"traits"` is read by RC8 (`Faction`/`SpecStore` reference the string, javap-confirmed) before treating it as live, not dead, content. Fixed Zorg's own file - `cowardly`→`timid`, and `suicidal`+`fearless` (both map to `reckless`) merged to weight 2 rather than left as a colliding duplicate key. Zorg18 and Leon-Heavy-Industries are both now declared (`READY_WITH_REVIEW_ITEMS` and `READY_FOR_LIVE_TEST` respectively).
- **New command `revival-report-draft`: drafts REVIVAL_REPORT.md/REVIVAL_PLAN.md from real scan+compile evidence for a genuinely clean mod (ROADMAP P14 item 35).** Refuses outright on any MANUAL finding or compile FAIL - never fabricates a PASS - and always records SAVE COMPATIBILITY CHECK/LIVE STARSECTOR TEST as not performed (they're never mechanically checkable), drafting `READY_FOR_LIVE_TEST`. `--apply` writes the pair, refusing to overwrite an existing report without `--force`. Found and fixed a real bug applying it to the corpus: **new scanner check `working-copy-tool-debris`** (MANUAL) catches a mod root that holds a `scratch/` folder - real case, Leon-Heavy-Industries' `working/` copy carried debris from an earlier refused `scan --output` command that a release build would have shipped. Leon-Heavy-Industries and Zorg18 were both re-triaged: Leon is now clean and declared `READY_FOR_LIVE_TEST` (its real hand-authored report gained the formal status line it was missing); Zorg18 was left alone pending two genuine owner decisions already on record in its own report.
- **New fixers `rules-firebest-populate-options`/`personality-id-unknown`: two of the 38 MANUAL findings that had no mechanical fixer at all (ROADMAP P14 item 34).** Found auditing fixer coverage after confirming both BridgeForge and RevenantLib are otherwise clean (RevenantLib `compile-check` PASS, `rebuild-jar` 0 drift, `scan_mod` only 4 low-severity findings). `fix --finding rules-firebest-populate-options` swaps `FireBest PopulateOptions` for `FireAll PopulateOptions` in rules.csv (VAC-DIALOG-01: vanilla's own rules.csv uses `FireAll` 462 times and `FireBest` never). `fix --finding personality-id-unknown` rewrites `setPersonality("cowardly"/"suicidal"/"fearless")` to RC8's own `timid`/`reckless`/`reckless` in loose scripts, refusing a match found only in a jar's bundled source (SK13-1d). The other 34 MANUAL ids stay MANUAL by design (a missing mod_info.json, an unresolved content reference with no known successor, and similar cases genuinely need a human decision, not a guess).
- **`content-reference-unresolved` now says "removed-vanilla-content, not just missing" for a known, catalogued vanilla-content removal, not just "defined nowhere" (ROADMAP P14 item 8).** `dependency_successors.json` already had two real, verified entries' worth of shape but was only consulted by `dependency-substitutes`; a plain `scan` never read it. Added real `thruster_fighter_sm`/`shields_formshield` entries (independently re-confirmed absent from the real RC8 install and present/resolvable in RevenantLib's own files) and wired the scanner's own finding to consult the same catalogue.
- **New commands `strip-plan`/`vendor-copy`: the exact edit list and a real vendoring path for a STRIP_FROM_MOD recommendation (ROADMAP P14 item 4).** `strip-plan` finds every `.variant`/`.ship`/`.skin`/`.faction` file+field that references a genuinely-uncovered id, and for weapons proposes real vanilla substitutes "of the same slot type and size" (reusing the scanner's own slot-fit logic, never invented); `--write-expected` turns each entry into a real `expect` PROPOSED entry. `vendor-copy hullmod <id> <from> <to>` copies a hullmod's CSV row, its declared script, and any same-mod script it directly depends on, refusing a local-only source (the same licence gate item 7 uses) or a conflict; dry-run by default, `--apply` to write. Verified against real data throughout: Zorg18's jar-only `zorg_zetaoverride` (correctly not vendored), Batavia's loose `pb_batavianradar` (full copy verified on disk), and Rebal's real `shields_formshield` (correctly refused — Rebal is genuinely local-only, the item's own worked example).
- **Fixed: `dependency-substitutes` could silently understate what a mod needs, for a mod with more than 25 unresolved content ids or 20 unresolved imports (ROADMAP P14 item 33, found building item 4).** `substitutes.required_from_scan` read only the finding's own evidence line, capped for human readability; it now prefers the full, untruncated lists both checks already store in `migration_context` for exactly this reason.
- **New check: a loose script shadowed by a *declared dependency's* jar, not just the mod's own (ROADMAP P14 item 12).** Extends `loose-script-shadowed-by-jar`'s existing detection (all mod jars share one classloader) across mods: `loose-script-shadowed-by-dependency-jar` (MANUAL) fires when a script's class name is already compiled into a declared dependency's jar, naming the dependency; the false `loose-script-janino-risk` is suppressed the same way the same-mod case already was. Extended `fix`'s shadowed-edit refusal (item 14) to the same case, with a new `fix --providers` flag. **Caught and fixed a real regression before committing:** the first version silently defaulted to scanning this repo's own real ~325-mod `In operation` folder on every scan with declared dependencies (no `provider_roots` given), turning the ~78s test suite into ~518s; fixed by requiring an explicit opt-in, matching `compile-check`'s own convention. Verified against the real, reconstructed Maelstrom Interstellar Imperium Unofficial Expansion bug state this item was written from.
- **`corpus-recheck`/`dependency-graph` gained `--include-intake` (ROADMAP P14 item 8, the Ironclads queue triage pass).** Both commands widen from "mods with a REVIVAL_REPORT.md" to "every mod with a `working/` copy," covering the 265-mod Ironclads intake queue with the exact same scan/compile-check/dependency-graph machinery already built for the revived corpus — no new discovery logic needed, since the intake queue shares the identical `working/` layout.
- **Licence-aware revival: `dependency-substitutes` now flags a REVIVE_DEPENDENCY recommendation as local-only when its licence doesn't allow redistribution (ROADMAP P14 item 7, item 9).** Reuses `release`'s own `_licence_gate` against `release_policy.json` — one licence check, not two — and appends a `[licence: local-only ...]` note to the recommendation text right where it's made, rather than only being discovered later at `release` time. New `dependency-substitutes --policy` flag. Read-only; never changes the recommended strategy itself.
- **New commands `provider-index-update`/`dependency-graph`: a persistent provider cache and a cross-mod dependency graph (ROADMAP P14 item 6, items 2-3).** `bridgeforge provider-index-update` caches every visible mod's "provides" set to `bridgeforge-state/provider-index/` (one JSON file per mod id, matching `novelty.py`'s own corpus-fingerprints convention), so a lookup is instant and survives the mod no longer being installed anywhere live. `bridgeforge dependency-graph` uses that cache to find, for every mod with real revival work recorded, which of its unresolved content needs could be covered by an unrevived provider, ranked by how many mods each would unblock. Verified against the real corpus (317 real providers cached; the graph correctly resolves the exact real Communist-Clouds/Vayra's-Sector case the whole roadmap section was written from).
- **New commands `archive-index`/`archive-search`: a one-time content index of a mod-archive folder, not a live timeout-prone grep (ROADMAP P14 item 18).** `bridgeforge archive-index <root> --output <index.db>` builds a small sqlite3 FTS5 database over every `*.zip` under `root` — every member's filename always, and the text content of small source/data files only (binary assets are filename-only). Incremental (unchanged archives are skipped on re-run). Verified against the real, full 214-archive Downloads folder: `archive-search ... "shieldbypass"` reproduces the exact real case that motivated this item — a `timeout 60 grep -rl` false negative — finding the real file plus 49 other real matches the timeout had silently missed.
- **New command `corpus-recheck`: generalizes item 23's full corpus recheck into a reusable command (ROADMAP P14 item 32).** `bridgeforge corpus-recheck [--vanilla-core] [--write-markdown] [--json]` re-scans every mod with real revival work recorded (discovered via `project_board`'s own tested layout logic — verified to reproduce the exact 40-mod list item 23 built by hand), reports finding counts/compile signal/declared status per mod, flags a `REGRESSION` (exit code 1) when a declared-ready mod now carries a MANUAL finding, and can write the same roll-up table format by itself.
- **Fixed: `board`'s status parser now resolves almost every real report, via a separate best-effort fallback (ROADMAP P14 item 31).** The strict single-final-line pattern `audit_revival` correctly demands for release gating was also the only thing `board` tried, and most real `REVIVAL_REPORT.md` files write the status inline with a trailing explanation, never matching it — only 9 of 40 real reports resolved a status before this fix. New `project_board._best_effort_last_status` takes the last `**STATUS**` bold marker anywhere in the report as a fallback, tagged with a new `declared_completion_status_confidence` field (`EXACT`/`BEST_EFFORT`/`None`) so a consumer can tell a confident read from a best-effort one. `audit_revival`/`release`'s strict gate is unchanged. Resolution on the real corpus went from 9/40 to 32/40.
- **Fixed: `scan_mod` now refuses a workspace root instead of silently scanning into `original/` (ROADMAP P14 item 30).** Found doing item 23's corpus recheck by hand: scanning `In operation/<Mod>/` instead of its own `working/` subfolder meant `scan_mod` walked into the untouched `original/` copy too and misattributed its findings to the live mod — real for two mods in the recheck (`BF-Legacy-Fleets`, `Leon-Heavy-Industries`), both actually clean once scanned correctly. `scan_mod` now raises a clear `ValueError` naming the right path when it detects this exact shape (no `mod_info.json` at the scanned root, but a sibling `original/` and a `working/mod_info.json`).
- **Fixed: `scan --compile-check` couldn't resolve a declared dependency at all (ROADMAP P14 item 29, found during item 23's corpus recheck).** `scanner._scan_compile_check` called `compile_loose_scripts` with no `provider_roots`, unlike the standalone `compile-check` command; a mod whose dependency lives outside even the default provider roots (a base mod only in the real Starsector install, as `Maelstrom-Interstellar-Imperium-Unofficial-Expansion`'s is) got a false compile FAIL under `scan --compile-check` alone. `scan_mod` now takes `provider_roots`, and `scan` has a new `--providers` flag mirroring `compile-check --providers`.
- **Full corpus recheck before live testing (ROADMAP P14 item 23, owner-requested).** Every mod with real revival work recorded (40 total) re-scanned with every fix landed this session. No regression: all 9 mods with a clean declared ready status are still 0 MANUAL findings, compile clean. Real finding: the new preset-whole-entry-replace check (item 15) found 6 previously-unknown, real mod-wide bugs — `Antediluvians`/`Batavia`/`Renis-Imperium`/`Vacuum`/`Xenoargh-EZFaction` downgraded to in-progress pending a fix, `Xenoargh-FX-Example` downgraded pending an owner call on intent. `Firestorm-Federation` (a real `initStar` compile-breaking bug) and `Scion-Collective` got their first full compile-check pass. Full roll-up in the gitignored `In operation/CORPUS_RECHECK_2026-09-21.md`.
- **New command `rebuild-from-reference`: generalizes E11's real Rebal rebuild method (ROADMAP P14 item 21).** `bridgeforge rebuild-from-reference <mod> --reference-core <rig> --current-core <RC8> [--glob] [--apply <dir>]` overlays a mod's own genuine authored changes (found by diffing against a historical reference rig's vanilla copy) onto a fresh copy of current RC8 vanilla, so RC8's own subsequent fixes are kept and only the mod's real edits carry forward — the fix E12 needed after finding 50 of Rebal's files wrongly dropped as "jar-shadowed" instead. A conflict (current vanilla itself diverged from the reference on a path the mod also touched) is surfaced by path, never silently resolved. Read-only by default; `--apply` writes to a separate output directory, never the mod's own working copy. Verified against Rebal's real registered reference rig and RC8's actual vanilla: 82 real `.wpn` files, 76 rebuilt cleanly, 5 genuine conflicts correctly named.
- **New command `diff-data`: value-diff two org.json-dialect files, not a line diff (ROADMAP P14 item 19).** `bridgeforge diff-data <file_a> <file_b>` loads both through `_load_lenient_json_file` and reports only real added/removed/changed field values, recursing into nested dicts and same-length lists — formatting, comment and key-order differences (pretty-printed vs. commented blocks, the exact noise E11's Rebal rebuild had to diff by hand) produce no output at all. Verified on Rebal's real `amblaster.wpn` against RC8 vanilla: exactly 5 true field differences, zero formatting noise.
- **New scanner check: a mod redefining a vanilla preset id silently loses fields game-wide (ROADMAP P14 item 15, `docs/BUG_CLASSES.md` BF-PRESET-01).** `engine_styles.json`/`hull_styles.json`/`custom_entities.json`/`planets.json` are merged by whole-entry replace, not a per-field merge; found on Zorg18 when its `engine_styles.json` silently stripped a colour field from every `LOW_TECH`/`MIDLINE`/`HIGH_TECH`-styled ship in the player's entire game (vanilla and every other enabled mod). New `preset-whole-entry-replace-loses-vanilla-fields` (MANUAL) and `-changes-vanilla-fields` (REVIEW) findings diff a mod's redefined id against vanilla's field by field. `sounds.json` is deliberately not covered — its nested category/list structure has unverified merge semantics.
- **New dev-facing self-check for the BF-SKIN-01 blind spot (ROADMAP P14 item 24).** `tests/test_skin_chain_resolution_audit.py` walks `bridgeforge/scanner.py`'s own AST for every function that builds a hull-id set from `*.ship` files or `_ship_file_index`, and fails if a new one doesn't resolve a `.skin`'s `baseHullId` chain (or isn't on a written exemption list) — so the next instance of item 17's bug is caught at review time instead of by accident in a live mod. Verified against a synthetic offending function to confirm it actually catches a regression.
- **Audited every mod's `scratch/MOVES.log` for a "moved because shadowed" decision made before `verify-shadow` existed (ROADMAP P14 item 27).** 299 logs checked; only two real shadowing-rationale moves found outside Rebal's already-corrected E12 case (Maelstrom-Interstellar-Imperium-Unofficial-Expansion's `II_TitanBombardment.java`/`II_TitanPlugin.java`), and both were independently re-verified SHADOWED against the base mod's real `II.jar` — no further wrong moves found.
- **New command `verify-shadow`: a direct, callable answer to "does this jar set actually supply a compiled class for this loose script?" (ROADMAP P14 item 26).** `bridgeforge verify-shadow <script> --against <jar-or-dir> [--root <root>]` reuses the same real class-file parsing item 14's fixer guard already uses, rather than the `Path.is_file()` path-existence guess that led E12 to wrongly conclude 50 of Rebal's loose `.java` files were jar-shadowed when none were. `--against` can be a single jar or any directory searched recursively for jars, so it answers against an arbitrary jar set, not just a mod's own declared jars.
- **Six more roadmap P14 items landed (2026-09-21), several finding a real bug along the way.**
  - `result.migration_context["unresolved_content_references"]` and `["vanilla_path_shadowing_total_files"]`: the exact per-id file list and a whole-mod grand total for content-reference/vanilla-shadow findings, not just a folder-rollup count — the gap that let Rebal's real ~642-file shadowed scope go uncaught as "~79" for a whole session (items 5's foundation, 20).
  - `campaign-fleet-reference-missing` now resolves a hull literal through a `.skin` chain before flagging it, the same fix BF-SKIN-01 made for mission variants — a second real instance of the same blind spot (item 17).
  - `_scan_variant_validity` now applies a `.skin`'s own `weaponSlotChanges` before checking weapon/slot fit, not just the base `.ship`'s raw slots — fixed a false positive (Rebal's `brawler_tritachyon`) and, on the same real data, correctly *revealed* a genuine mismatch it had been hiding (`falcon_p_Strike` mounts a ballistic weapon in a slot the skin retypes to missile-only) (item 28).
  - New fixer `undeclared-library-dependency`: declares a library (LazyLib/MagicLib/GraphicsLib/LunaLib/Nexerelin) a mod already reaches by package, hand-applied three times earlier this session before this existed. Found and fixed a real bug while building it: `scanner.LIBRARY_DEPENDENCY_IDS` had the wrong case for two libraries (`magiclib`/`shaderlib` instead of the real `MagicLib`/`shaderLib`), confirmed by reading those libraries' own installed `mod_info.json` (item 16).
  - `compute_fix` now refuses to plan an edit to a loose script one of the mod's own jars already shadows — the edit would have no effect, exactly what happened on Thule-Legacy's `MissionDefinition.java` this session (six `setPersonality()` edits, zero in-game effect). New `fix --allow-shadowed-edit` overrides it when the jar is also being rebuilt in the same pass. The real jar-parsing logic was factored out of the scanner's own `loose-script-shadowed-by-jar` check into `scanner.mod_jar_class_names`/`loose_script_jar_shadowed_class` so this reuses it rather than reimplementing it (item 14).
  - `rig-doctor`'s `enabled_mods_resolve` no longer FAILs a freshly registered P10 reference rig just because it has no mods enabled yet (item 22).
- **Unattended revival with verified AI escalation (ROADMAP P15).**
  - `finding-stats` counts findings across workspaces by automation tier: how many mods could be revived unattended today, which finding id would unlock the most mods if automated, and which fixes AI has repeatedly made that should become fixers.
  - `revive` loops scan, permitted fixers and rescan until nothing changes, then writes escalation packets: self-contained prompts for an AI agent (evidence, allowed files, numbered excerpt, rules, the check that decides "done") and questions for the owner (with the dry-run diff of any fixer awaiting approval). Standing approvals live in the queue's `AUTOMATION_POLICY.json`.
  - `escalation run` runs any agent command on a packet in a throwaway copy and keeps the result only if BridgeForge's own rescan verifies it; edits outside the packet are rejected; every attempt is logged. `escalation list|show|verify` cover the rest.
  - New fixers: `csv-fullwidth-number`, `ship-data-missing-fighter-bays-column`, `missing-custom-ui-button-pressed-callback`.
- `verify-shadow` reads the game's own large jars (a higher entry cap for jars in a `starsector-core`; mod jars keep the zip-bomb cap).
- `corpus-index` reads `.7z` archives with the optional `bridgeforge[archives]` extra (`py7zr`), with the same safety checks as zips.
- New `release-policy show|set` records a mod's publishing decision (reason required, date kept).
- **`board` shows dependency evidence (ROADMAP P14 item 3).** `dependency-graph --write` and `dependency-substitutes --write` record their results; `board` shows each mod's dependency strategy and the queue's revival order with the dates they were recorded, and warns when a mod was rescanned since.
- **New `vendor-plan` command (ROADMAP P14 item 4, last slice).** Traces the closure of one piece of an abandoned mod for folding into RevenantLib: files and rows to include, SUSPECT files that mention it but nothing references, missing references, what RevenantLib already has, and the licence decision. Copies nothing. Reproduces RevenantLib's two hand-traced closures exactly.
- `strip-plan --expected FILE --build rN --link ...` adds PROPOSED expected changes for the files a strip deletes, ready for `expect approve` (ROADMAP P14 item 4, second slice).
- **New `provider-index build` and `dependency-graph` (ROADMAP P14 items 2-3).** Save what every visible mod provides so lookups work without the mods installed (`dependency-substitutes --provider-index`), and rank queue-wide which old dependencies to revive first by how many queued mods each unblocks.
- **`dependency-substitutes` is licence-aware (ROADMAP P14 item 9).** Each dependency it would have you revive shows its `release_policy.json` decision (LOCAL_ONLY, RELEASABLE, or UNRECORDED when no one has checked), with a `LICENCE:` note on what that means for shipping.
- **New `strip-plan` command (ROADMAP P14 item 4, first slice).** For content a mod uses but nothing defines, lists every file and field each id sits in (variant slots, hull-mod and wing lists, built-in weapons, faction known-lists), with vanilla weapons that fit each emptied slot. Edits nothing.
- **New finding `loose-script-shadowed-by-dependency-jar` (ROADMAP P14 item 12).** `compile-check` and `scan --compile-check` now detect a loose script whose class a declared dependency's jar already compiles: the game never compiles it, so the mod's edit does nothing. Its javac errors no longer fail the compile check.
- Tests: a self-check (ROADMAP P14 item 24) fails the suite when new code builds a hull-id set from `.ship` files without resolving `.skin` ids (the BF-SKIN-01 blind spot), unless it is an explained exemption.
- **New scanner checks `preset-entry-drops-vanilla-fields` (MANUAL) and `preset-entry-overrides-vanilla` (REVIEW) (ROADMAP P14 item 15).** A mod's `engine_styles`/`hull_styles`/`custom_entities`/`sounds`/`planets.json` entry with a vanilla id replaces vanilla's whole entry game-wide; the scan now names every vanilla field such an entry drops or changes (Zorg18's `contrailCampaignColor`).
- **New `verify-shadow` command (ROADMAP P14 item 26).** Answers "does this jar set really compile the class this loose script defines?" by parsing class files, never by path existence (E12), naming the supplying jar and listing any jar it could not read.
- **New `content-diff` command and `scan --removed-content` (ROADMAP P14 item 8).** Catalogues the content ids an older install defined that RC8 dropped, with same-named RC8 candidates; the scan then reports unresolved references vanilla removed as `content-reference-removed-in-vanilla` instead of a missing dependency.
- **New `corpus-index build|search` (ROADMAP P14 item 18).** Index a large mod archive once (inside zips too) and search file contents or paths in milliseconds; each result states what the index could not read, so an empty result is real evidence of absence.
- **New `rebuild-from-reference` command (ROADMAP P14 item 21).** Ports a mod's edited copies of vanilla `.ship`/`.wpn`/`.variant`/`.skin`/`.system` files to RC8 with a three-way merge (reference vanilla, mod, RC8): RC8's changes kept, the mod's edits applied, overlaps reported as conflicts, unedited copies flagged for removal. Writes only clean merges, to a separate folder; `--class` stages a large mod.
- **New `diff-data` command (ROADMAP P14 item 19).** Compares two data files (JSON dialect or CSV) by value, so key/row/column order, comments, trailing commas and `10` vs `10.0` never count; lists slots by id and reports a reordered list once. The primitive item 21's rebuild-from-reference needs.
- `docs/LOCAL_HANDOFF.md`: work cloud sessions built but could not finish without the game, a rig or Windows.
- **Probe 0.2.2: `content-ids` campaign check (ROADMAP P14 item 49).** The game itself resolves every variant and wing id the mod defines, and builds each of the mod's own ship variants as a fleet member (resolving hull, weapons and hull mods); failures name the id and the game's error. `probe-config` writes the new `content_variants`/`content_wings` keys. Rebuild with `build-probe-mod --install-release` before the next rig run.
- Fixed: `probe-config` picked each hull's variant by file name instead of the declared `variantId` (ROADMAP P14 item 50).
- **New `revenantlib-check` command and `rig-doctor` check `revenantlib_contract` (ROADMAP P14 item 48).** Pins the three `bf.*` methods `fix --finding removed-api-call` rewrites calls to and verifies a RevenantLib jar provides them with the exact signatures, plus that its jar and `src/` agree class for class. RevenantLib 1.2.0+bf.1 passes.
- **New `api-diff` command (ROADMAP P14 item 47): where did a removed API go?** Compares two `starfarer.api.jar`s and catalogues every public class, method and field removed or changed, with same-named candidates (a moved method, a changed overload, a class in a new package). `compile-check --api-diff FILE` prints those leads under the javac errors they explain. javac now runs with `-Xdiags:verbose` so a changed single-overload call names its method and class.
- Fixed: `rebuild-jar` accepts backslash `--jar`/`--sources` paths on POSIX; the compile-check scan finding keeps a relative file key when javac reports the mod root through an alias (Windows 8.3 short name, symlink); `docs/COMMANDS.md` no longer embeds the generating machine's path for `--repo-root`.
- Tooling: ruff lint, `uv.lock` sync check, coverage floor and Python 3.13 in CI; Dependabot for GitHub Actions; rig-safety tests now also run on POSIX (directory symlink in place of a junction).
- Fixed: `mission-local-variant-hull-missing` (and its sibling weapon check) now resolves a variant's hullId through any `.skin` chain before flagging it missing, matching `_scan_variant_validity`. Found on Leon-Heavy-Industries: 4 real, campaign-wired pirate-raider missions were false-flagged (BF-SKIN-01).

- **Xenoargh FX Core folded into RevenantLib (ROADMAP P14 item 10, task A13, owner decision `In operation/ESCALATIONS.md` E9 course A: 2026-09-20).**
  - `bridgeforge fold "In operation/Xenoargh-FX-Core/working" "In operation/RevenantLib"` run for real (dry-run first); its 13-file byte-for-byte copy landed at `original/working/` (the tool names that folder after the literal basename of `source`, which is always `working` under BridgeForge's own workspace layout) and was renamed to `original/Xenoargh-FX-Core/` to match the `original/Vacuum`/`original/Xenoargh-Rebal` naming convention, logged in RevenantLib's `scratch/MOVES.log`.
  - Unlike the Vacuum/Rebal folds, FX Core's package (`data.scripts.fx_Particle`/`fx_SharedLib`/`fx_Trail`/`plugins.FX_Plugin`) was kept exactly as upstream, not renamed to `xenoargh.shared.*`, so Xenoargh-FX-Example's existing imports resolve unchanged. That makes enabling the standalone Xenoargh-FX-Core mod alongside RevenantLib 1.2.0+ a hard class clash, not a soft id collision — documented in `reports/README.md`/`PROVENANCE.md`.
  - **The owner's "make the always-on cost lazy" decision:** `FX_Plugin`'s `public static ExecutorService fx_PluginCommonExecutor` used to be initialized eagerly (`= Executors.newFixedThreadPool(1)`), spinning up a background thread as soon as the class loaded — before any dependent used FX at all. Changed to lazy, thread-safe (double-checked locking) initialisation via a new private `ensureExecutor()`, called from the two internal use sites; the field keeps its name, type and `public static` contract. `AAA_Starsector_FX_mod_ModPlugin` (whose only job is to throw if `lw_lazylib` isn't enabled) was carried across for provenance but not declared as RevenantLib's `modPlugin`, since RevenantLib already hard-declares `lw_lazylib`.
  - `data/config/settings.json`'s `fx_trailCoreSprite` path case was corrected from upstream's `graphics/fx/...` to the actual on-disk `graphics/FX/...` (Windows hid the mismatch; Starsector's asset loader is case-sensitive). The stray, unreferenced `fx_trail_core - Copy.png` was checked (no reference anywhere) and left out of `working/`, kept only in the provenance copy.
  - RevenantLib bumped to `1.2.0+bf.1`; jar rebuilt (`bridgeforge rebuild-jar`: 0 errors, 0 members/classes lost, 0 forbidden sandbox references — REVIEW status only because of the 6 expected additions, which is `rebuild-jar`'s own rule for any addition) and installed by hand (`rebuild-jar --install` refuses on non-PASS).
  - Xenoargh-FX-Example's dependency repointed `xxx_ss_FX_mod_core` -> `revenantlib` via the `revenantlib-fold-conflict` fixer path; rescanned clean (0 MANUAL, same REVIEW/SAFE counts as before), and `compile-check` confirmed RevenantLib.jar now supplies the classes FX Example imports.
- **Fold-in workflow (ROADMAP P14 item 10, owner policy 2026-09-14): a new `fold` command, a fixer, a scanner check and the `dependency_successors.json` entry shape that ties them together.**
  - New command `fold <source> <target>` (`bridgeforge/fold.py`): copies a discontinued library-like mod's entire directory byte-for-byte into `<target>/original/<source folder name>/`, keeping its ids and class names exactly as they are so dependents keep resolving them. `source`/`target` are always explicit arguments — this never hardcodes or touches "In operation" itself. Records a provenance section (source path, mod id, name, author, version, `gameVersion`, a licence-file evidence note, and a SHA-256 per file) in `<target>/reports/PROVENANCE.md`, and writes a `dependency_successors.json` entry (kind `folded-into-revenantlib`) so `dependency-substitutes` proposes the `revenantlib` swap. `--dry-run` writes nothing; an existing `original/<name>/` is refused outright without `--overwrite`; a file that already exists with *different* content is a conflict that stops the whole run — reported, never silently overwritten or deleted. Re-running with unchanged inputs is a no-op. Curating what actually belongs in RevenantLib's own `working/` copy (the "traced closure") stays a coordinator task, not this command's.
  - New scanner check `revenantlib-fold-conflict` (MANUAL): fires when `mod_info.json` declares both `revenantlib` and an id `dependency_successors.json` records as folded into it — enabling both together double-registers the same ids and classes.
  - New fixer `fix <mod> --finding revenantlib-fold-conflict --apply`: drops the redundant original dependency entry/entries (object or bare-string form) and leaves `revenantlib`'s own entry untouched, reusing `_add_revenantlib_dependency` as a safety net; standard `.pre-bf-fix-revenantlib-fold-conflict.bak` backup and rescan-based resolution.
  - **Bug fix, found by that fixer's own test:** `_add_revenantlib_dependency`'s "already declared" check only recognized a `{"id": "revenantlib", ...}` object entry, not a bare `"revenantlib"` string entry (a shape Starsector accepts and `_mod_info_declares_dependency` already handled) — it would double-add a redundant object entry onto a mod_info.json that already declared `revenantlib` as a bare string. Now checks both shapes.
- **`scan --compile-check` (finishes ROADMAP P14 item 11): the javac loose-script compile check is now wired into `scan_mod` itself, opt-in.**
  - `scan_mod` gained `compile_check: bool = False` and the `scan` CLI command a matching `--compile-check` flag; off by default so a plain scan stays fast and hermetic. When enabled with `--vanilla-core`, it calls `bridgeforge.compile_check.compile_loose_scripts` and reports `loose-script-compile-error` (MANUAL, one finding per failing loose script, with up to 5 errors' line/message/symbol as evidence) or `loose-script-compile-unavailable` (UNKNOWN, no JDK or no core available).
  - Same real cases as the standalone `compile-check` command (2026-09-15): Renis-Imperium, AI-War, Argamede-Union and EZFaction were each marked ready by every other check and failed only this one.
  - **Janino version evidence:** RC8's `starsector-core/janino.jar` manifest reads `Implementation-Version: 2.7.8`. Janino's own changelog dates the diamond operator (a test added 3.0.7, 2017-03-22), try-with-resources (implemented 3.0.9, 2018-08-23) and multi-catch/lambda/method-reference parsing (3.0.13, 2019-06-23) all to releases well after 2.7.8; `var` (Java 10) has no earlier claim either. None of `janino_gap_warnings`' flagged constructs are documented as supported in 2.7.8, so every pattern keeps flagging exactly as before, now with that evidence recorded in `bridgeforge/compile_check.py`.
- New scanner check `mod-info-jar-missing` (MANUAL): flags each `mod_info.json` `"jars"` entry that doesn't exist under the mod root — the game is asked to load a jar that isn't there, a launch blocker to verify in game. Evidence: Xenoargh's EZFaction and AI Overhaul originals both declare `jars/LazyLib.jar` and ship neither.
  - `_attribute_library_usage`'s "bundled" check now also verifies the matching jar actually exists on disk (defense in depth: `_loaded_mod_jars`/`_scan_jars` already filtered to existing files, but the check no longer trusts that implicitly). A declared-but-missing `LazyLib.jar` had been masking EZFaction's real, undeclared LazyLib dependency, later surfaced the hard way as 48 javac errors by the compile check above.
- **Carrier-bay fixer (ROADMAP P14 item 6): `fix <mod> --finding carrier-bays-proposal --hull ID=N [--hull ID=N ...] --apply`.**
  - Writes the approved fighter-bay count into `data/hulls/ship_data.csv`'s `fighter bays` column (RC8's own header name, read from the core), adding the column — blank for every hull not named — the same way `wing-data-missing-role-desc-column` adds `role desc`, if the mod's file predates it.
  - `--hull` is repeatable and required; every id must already exist as a ship_data.csv row (an unknown id is refused, not silently skipped) and its count must be 0-6 (vanilla's own maximum, the Astral, read from RC8's own `ship_data.csv`).
  - The `carrier-bays-proposal` scanner check no longer proposes a hull whose `fighter bays` is already set, so a partial approval run correctly narrows what's still proposed on rescan.
- **`build-tag` bug: it tagged the first `"name"`/`"version"` key found anywhere in the file, not the mod's own top-level one.** Batavia, Qualljom and Antediluvians all list `"dependencies":[{"id":"revenantlib","name":"RevenantLib"}]` before their real top-level `"name"`, which the old first-match search would tag instead — caught by `build_tag`'s own round-trip check, so it always refused rather than mistagging silently, but a real revival build couldn't be tagged at all. `bridgeforge/build_tag.py` now does a brace/bracket-depth-aware scan (`_structural_depths`/`_find_top_level_key`, skipping string contents and `#`/`//` comments) and only matches a key sitting directly inside the root object (depth 1); `fixers._fix_mod_info_triage_banner` (which had the identical first-match risk on the same `_NAME_PATTERN`) now uses the same top-level lookup. File formatting outside the two edited value spans is unchanged, as before.
- **`removed-api-call` fixer, CrewXPLevel rule: refuses to rewrite a file that declares a CrewXPLevel-typed variable or parameter** (e.g. `CrewXPLevel level` or `CargoAPI.CrewXPLevel x`), with a message to hand-port it instead. Real case: AI-War's `data/missions/aiw_midnight/MissionDefinition.java` had a helper `addToFleetAndAddSkills(..., CrewXPLevel level, boolean isFlagship)` with a body default (`if (level == null) level = CrewXPLevel.REGULAR;`); the literal call-site-only rewrite would have dropped the argument at call sites while leaving the helper's own (now-unresolvable) parameter type and default-value line untouched, desyncing call-site argument counts from the signature. The owner's task A10 hand-ported this file. The refusal is per-file: a plain, non-wrapper call site elsewhere in the same mod is still rewritten as before.
- **CLI output safety: piped/redirected `--json` output could raise `UnicodeEncodeError` on Windows** (cp1252 console codepage rejecting the non-ASCII text several modules print with `ensure_ascii=False`, or the CJK strings `translate-check` reports). `main()` now calls a new `_reconfigure_streams_for_pipes()` helper first: any of stdout/stderr that exposes `TextIOWrapper.reconfigure` and is not an interactive console (`isatty()` false or absent) is switched to UTF-8 with `errors="replace"`. An interactive console's own encoding is left untouched.
- New command `compile-check <mod>` (ROADMAP P14 item 11): compiles a mod's loose `data/**.java` scripts against RC8 with javac and reports every error (file, line, kind, symbol, location).
  - The classpath is the core jars, the mod's own jars and its declared dependencies' jars, through the new shared `java_toolchain` module. It reports declared dependencies whose jars weren't found.
  - RC8's own loose vanilla scripts (such as `BaseSpawnPoint`) are compiled alongside, so a mod script extending one resolves.
  - It warns about Java 8+ syntax that javac accepts but the game's own compiler (Janino) may reject.
  - First sweep (2026-09-15): four mods marked ready failed (Renis-Imperium, AI-War missions, Argamede-Union, EZFaction). The earlier checks couldn't see these errors.
- New command `rebuild-jar <mod> --sources DIR --jar JAR` (ROADMAP P14 item 7): rebuilds a mod's jar from source and compares it with the original.
  - It reports classes, methods and fields added or removed. Lombok lock fields, synthetic `access$`/`lambda$` members, `synchronized`-only changes and class-file version bumps count as expected compiler differences.
  - It reports forbidden sandbox references in the rebuild.
  - `--install` installs only a PASS rebuild, moving the old jar to `scratch/moved-<date>/` with a MOVES.log line.
- Credit wording (owner, 2026-09-15): BridgeForge's own credit reads "BridgeForge by Exxec", and original authors always come first.

- **BF Legacy Fleets folds into RevenantLib; new `bf.legacyworld.LegacyWorld`; CrewXPLevel dropped; all six spawn-point mods compile clean (2026-09-15, task A8, owner-approved).**
  - **Fold-in.** `bf.legacyfleets.LegacyFleets` (id `bf_legacy_fleets`) is copied unchanged, same fully-qualified name, into `In operation/RevenantLib/working/src/bf/legacyfleets/LegacyFleets.java`; `RevenantLib.jar` is rebuilt with all five classes (`xenoargh.shared.hullmods.FormShield`, `xenoargh.shared.sfx.rearThrusterJet`, `bf.legacyfleets.LegacyFleets`, `bf.legacyworld.LegacyWorld`, `bf.legacyworld.LegacyWorld$StockTransferScript`). RevenantLib bumps to `1.1.0+bf.1`; author becomes `Xenoargh (shields_formshield, thruster_fighter_sm); legacy API functions by BridgeForge by Exxec; assembled for 0.98a by BridgeForge by Exxec`. `In operation/BF-Legacy-Fleets/reports/SUPERSEDED.md` records the retirement and the hard class-clash warning (never enable both). The six mods' `mod_info.json` `"dependencies"` swap `bf_legacy_fleets` → `revenantlib`; no source change needed (same fully-qualified call sites).
  - **New `bf.legacyworld.LegacyWorld`** (RevenantLib, `working/src/bf/legacyworld/LegacyWorld.java`), javap-verified against RC8's `starfarer.api.jar`, no forbidden sandbox API in the compiled classes (`javap -v` constant-pool check).
    - `addPlanet(LocationAPI, SectorEntityToken, String, String, float, float, float, float)`: the removed 0.6 7-argument `LocationAPI.addPlanet` with the old receiver as an explicit first argument. Generates a deterministic id (sanitized location id + sanitized name, numeric suffix on collision, checked against `Global.getSector().getEntityById`) and forwards to RC8's id-first `addPlanet`.
    - `addOrbitalStation(LocationAPI, SectorEntityToken, float, float, float, String, String)`: RC8 has no `addOrbitalStation` at all. Owner decision ("option A"): 0.6 orbital stations become real, dockable RC8 markets. Builds a `station_side00` custom entity (`data/config/custom_entities.json`) in a circular orbit around the focus (`SectorEntityToken.setCircularOrbit`, same trailing 3 numbers the old call took); creates a market (`Global.getFactory().createMarket`), `Conditions.POPULATION_3`, `Industries.POPULATION`/`SPACEPORT`/`ORBITALSTATION`, `Submarkets.SUBMARKET_OPEN`/`SUBMARKET_BLACK`/`SUBMARKET_STORAGE`, and registers it (`EconomyAPI.addMarket(market, true)`) — every call mirrors, call for call, RC8's own `data/scripts/world/systems/Galatia.java` `derinkuyu_station`/`derinkuyu_market` pair. Attaches a one-shot `StockTransferScript` (`EveryFrameScript`) that on the first campaign frame moves whatever the caller put into the station token's own cargo (crew/marines/fuel/supplies via scalar accessors; weapons/fighter wings via itemised `getWeapons`/`getFighters`; everything else via `getStacksCopy`/`addFromStack` with the already-handled kinds skipped; mothballed ships via `FleetDataAPI.getMembersListCopy`/`addFleetMember`, since `CargoAPI$CargoItemType` has no ship/wing constant) into the market's open submarket cargo, then clears the source and reports `isDone()` — cannot duplicate (one-shot completion flag, idempotent-by-clearing, and `addOrbitalStation` itself only runs once per new campaign).
    - Both scanner and fixer had a self-matching bug caught during testing: the rewrite `bf.legacyworld.LegacyWorld.addOrbitalStation(...)` itself matches the receiver pattern `receiver.addOrbitalStation(` (receiver = `LegacyWorld`), which without a guard re-flagged, and would have re-rewritten, the fixer's own output forever. Fixed with an explicit `receiver == "LegacyWorld"` exclusion in both finder functions (addPlanet is incidentally protected by its 7-argument count check, since the rewritten call always has 8; the guard was added to both for consistency).
  - **CrewXPLevel now has a fixer (owner decision, coordinator's recommendation: RC8 has no crew quality — drop the level, keep the counts).** `bridgeforge/scanner.py`'s `CargoAPI.CrewXPLevel` rule now matches three shapes (the now-unresolvable import line; `CrewXPLevel.X` as `addCrew`'s leading argument; a trailing `, CrewXPLevel.X` argument to `MissionDefinitionAPI.addToFleet`) and the fixer deletes all three: `addCrew(CrewXPLevel.X, n)` → `addCrew(n)`; `addToFleet(..., CrewXPLevel.X)` → `addToFleet(...)`; the import is removed. Expected change recorded per mod: "crew quality no longer exists in RC8; crew counts are kept." No `bf.` call is introduced, so this rule never adds a dependency.
  - **New `REMOVED_API_CALLS` entries and rewrites** for the two `LocationAPI` calls above. addPlanet's matcher is a dedicated finder (`_find_legacy_add_planet_calls`, using the existing `_extract_call_arguments_text`/`_split_call_arguments` helpers) that counts top-level arguments and matches only an exact 7 — RC8's own 8-argument id-first form and `MissionDefinitionAPI`'s unrelated 5/6-argument `addPlanet` are never flagged ("be conservative", per task instruction). addOrbitalStation's matcher (`_find_legacy_add_orbital_station_calls`) needs no such count check (RC8 has no method of that name at all). `REMOVED_API_CALLS` entries can now carry either a compiled regex or a plain finder function as their matcher; `_removed_api_call_spans` (scanner) hides the difference for both `_scan_removed_api_calls` and `fixers._fix_removed_api_call`. `createFleet`/`addPlanet`/`addOrbitalStation` all introduce a `bf.` call and add the `revenantlib` dependency once per run (`_add_revenantlib_dependency`, replacing `_add_legacy_fleets_dependency`); `addMessage`/`CrewXPLevel` do not.
  - **Applied to all six mods** (Cobalt-Arms, Gekelonians, Independant-Mining-Faction, Batavia, Qualljom, Antediluvians): every `removed-api-call` finding is resolved (0 MANUAL remaining for this id on all six). `target-interface-method-missing` and `wing-data-missing-role-desc-column` also applied where present (Batavia, Qualljom, Antediluvians). `csv-row-extra-columns` applied where it doesn't refuse (none of the six qualified: Batavia and Antediluvians have real spilled data in `descriptions.csv`/`weapon_data.csv` and the fixer correctly refuses; Qualljom, Cobalt-Arms, Independant-Mining-Faction, Gekelonians had nothing to trim).
  - **Whole-mod compile-check** (every loose script, not just touched files, against RC8 core jars + `RevenantLib.jar`; `-sourcepath` set to both the mod root and the RC8 core root so vanilla loose scripts like `BaseSpawnPoint.java` resolve) found and fixed issues outside the new rules' scope: Gekelonians'/Antediluvians' mission files used the removed `FleetGoal.DEFEND` (RC8 has only `ATTACK`/`ESCAPE`; hand-ported to `ATTACK`, matching the same mission's `ENEMY` fleet); Batavia's `TorpedoLoaderAI.java` contained a misnamed copy of vanilla's own tutorial `FastMissileRacksAI` example (public-class/filename mismatch, fails Janino regardless of the file's own use being commented out; renamed the class to match); nine `data/hullmods/Batavian*.java` files were missing `import com.fs.starfarer.api.combat.BaseHullMod;` entirely; Qualljom's `QualljomHolotisGen.java` needed two more hand-ports outside `LegacyWorld`'s mechanical scope (`initStar` had no evidenced 7-arg-removed → 4-arg-RC8 mapping, since the old call took no star type at all; `createJumpPoint` needs an id argument RC8 added). **All six mods now compile clean.**
  - Tests: `tests/test_fixers.py` (`CrewXPLevelRewriteTests` replaces the old `CrewXPLevelNotRewrittenTests`; new `LegacyWorldRewriteTests`, 6 cases including the RC8-8-arg and MissionDefinitionAPI-5/6-arg false-positive checks and the self-matching-loop regression), `tests/test_batch_lessons.py` (2 new scanner-level cases; the CrewXPLevel case's evidence count updated for the wider match). Full suite: 878 tests, unchanged pass rate (was previously reported at lower counts before A9's concurrent `compile_check`/`java_toolchain`/`rebuild_jar` additions).
- **Correction:** MagicLib attribution now covers only `data.scripts.util.Magic*`, the legacy classes MagicLib 1.5.6 ships, instead of the whole `data.scripts.util` package, and it never counts the mod's own classes.
  - `source-library-dependency-undeclared` had credited AI-War's own `AIWTwig`, `AIW_AnamorphicFlare` and `AIW_StringHelper` to MagicLib (reported by the A6 revival).
  - The own-class list is now one helper, `_local_class_names`, shared with the import checks.

- **New library `In operation/BF-Legacy-Fleets`** (id `bf_legacy_fleets`, no upstream original) restores 0.6's removed `SectorAPI.createFleet(factionId, fleetTypeId)` as `bf.legacyfleets.LegacyFleets.createFleet(...)`.
  - Rebuilds the faction's `fleetCompositions` entry at runtime through `SettingsAPI` only (`getMergedSpreadsheetData`/`getMergedJSON`, no `java.io.File`, no reflection): minimum ship/wing counts first, then random extras up to each entry's max while the fleet stays under `maxFleetPoints`; unresolved variant/wing ids are skipped and logged once. Standalone fighter-wing fleet members were verified valid in RC8 (javap: `FleetMemberType.FIGHTER_WING`, the `...WithFightersCopy` accessors, and vanilla's own `FleetFactoryV3.addCarrierFleetPoints`), so they are added, not skipped.
  - Never returns `null` or an empty fleet: if no composition is found or it yields nothing, it falls back to `FleetFactoryV3.createFleet(FleetParamsV3)` (vanilla's own generator) with `combatPts` near the composition's `maxFleetPoints` or a documented default of 20.
  - Compiled `--release 17 -proc:none` against the RC8 core jars; `javap` on the packaged jar's constant pool confirms no `java.lang.reflect`/`java.nio.file`/`java.io.File*` reference. See `In operation/BF-Legacy-Fleets/reports/README.md` for the full design (including two argument-order ambiguities javap alone can't resolve, documented rather than guessed) and its limits (no supplies/fuel/crew/marines, no officer auto-assignment, and a real gap: Qualljom's `independent`/`pirates` fleet types have no `fleetCompositions` anywhere in RC8).
- New fixer `removed-api-call` (`bridgeforge/fixers.py`): rewrites `getSector().createFleet(`/`Global.getSector().createFleet(` in loose `data/` scripts (same receiver match as the scanner, comments and `disabled_files` ignored; jar-bundled sources are refused, same as `target-interface-method-missing`) to the fully qualified `bf.legacyfleets.LegacyFleets.createFleet(`, and adds `bf_legacy_fleets` to `mod_info.json`'s `dependencies` if not already declared.
  - Applied to all 17 call sites across the six spawn-point mods (Cobalt-Arms, Gekelonians, Independant-Mining-Faction, Batavia, Qualljom, Antediluvians): `removed-api-call` is now clear on all six (rescan MANUAL counts: Cobalt-Arms 1→0, Gekelonians 1→0, Independant-Mining-Faction 1→0, Batavia 34→33, Qualljom 15→14, Antediluvians 20→19). Gekelonians had no other MANUAL finding and moves to `READY_WITH_REVIEW_ITEMS`.
  - **Correction found by this pass's compile-check (not caught by any scanner check): RC8's `SectorAPI` also has no `addMessage(String)` any more, and `CargoAPI` no longer nests a `CrewXPLevel` enum.** Both are used by the `*ConvoySpawnPoint` files in Cobalt-Arms, Independant-Mining-Faction, Batavia, Qualljom and Antediluvians (`addMessage`, all five; `CrewXPLevel` also in Batavia/Qualljom/Antediluvians), so those five files still fail to compile even after the `removed-api-call` fix — a second, independent loose-script blocker. Cobalt-Arms and Independant-Mining-Faction therefore stay `ESCALATION_REQUIRED` rather than `READY_WITH_REVIEW_ITEMS` (their `CAPSCOSpawnPoint.java`/`MineFactionSpawnPoint.java` compile clean; only their convoy spawner does not). Reported per each mod's `reports/REVIVAL_REPORT.md`; not fixed (no scanner/fixer changes for this beyond `removed-api-call` itself).
  - `reports/REVIVAL_PLAN.md`/`REVIVAL_REPORT.md` created for Batavia, Qualljom and Antediluvians (previously missing); all three record only the E6 port, with their pre-existing MANUAL findings listed untouched. Qualljom additionally documents a fleet-type gap: `QuaIndependentSpawnPoint`/`QuaPirateSpawnPoint` request 15 fleet-type ids that exist in no `fleetCompositions` anywhere in RC8 (vanilla `independent.faction`/`pirates.faction` no longer have that key; Qualljom ships no override), so those two spawn points always take BF Legacy Fleets' `FleetFactoryV3` fallback.
  - All six mods' `mod_info.json` `"author"` field now keeps the original author (or `"unknown"` where none was ever recorded, for Batavia and Antediluvians) with `"; 0.98a revival by BridgeForge"` appended, on owner instruction.
- **`removed-api-call` follow-up (2026-09-15): two more removed RC8 APIs, a scanner false positive fixed, and the fixer generalized per-rule.**
  - `bridgeforge/scanner.py` `REMOVED_API_CALLS` gained two entries (javap evidence in-line): `SectorAPI.addMessage(String)` (RC8's `SectorAPI` has no `addMessage`; `SectorAPI.getCampaignUI()` returns `CampaignUIAPI`, which has it) and `CargoAPI.CrewXPLevel` (RC8's `CargoAPI` no longer nests that enum; a jar-wide search of `starfarer.api.jar` finds no `CrewXPLevel`/`XPLevel` anywhere; RC8's plain `addCrew(int)` is *not* a behaviour-equivalent replacement, so this entry is detection-only, no fixer rewrite). The `createFleet` entry's receiver now also matches `Global.getSectorAPI()` (javap-confirmed to also return `SectorAPI`), not just `getSector()`/`Global.getSector()`.
  - Fixed a scanner false positive: `_scan_script_sandbox_forbidden_api`'s loose-source check matched `java.io.File`/`java.nio.file`/`java.lang.reflect` inside comments (a comment merely *naming* what a class avoids read the same as code using it — real case: BF Legacy Fleets' own class Javadoc). It now blanks comments first via `_blank_java_comments`, the same helper `_scan_removed_api_calls` already used.
  - `bridgeforge/fixers.py`'s `removed-api-call` fixer is generalized: each `REMOVED_API_CALLS` rule now has its own rewrite (`_REMOVED_API_CALL_REWRITES`, keyed by signature). `createFleet` keeps its exact prior behaviour (full-span rewrite to `bf.legacyfleets.LegacyFleets.createFleet(`) and is the *only* rule that adds the `bf_legacy_fleets` dependency, and only when it actually rewrote something in that run. The new `addMessage` rule inserts `.getCampaignUI()` immediately before `.addMessage(`, keeping the original receiver text untouched. `CargoAPI.CrewXPLevel` has no rewrite; a file where it's the *only* removed-api-call match now refuses with a clear "no safe mechanical rewrite" message instead of silently doing nothing.
  - Applied to the five convoy-spawner mods (Cobalt-Arms, Independant-Mining-Faction, Batavia, Qualljom, Antediluvians): all ten `*ConvoySpawnPoint.java` `addMessage` calls are fixed and now compile clean against RC8 core jars + the recompiled `BFLegacyFleets.jar`. **Correction to the prior pass's status projection:** compiling `CAPSCOModGen.java` and `MineFactionModGen.java` (found via this pass's new mod-wide `CrewXPLevel` scanner rule, not scoped to the convoy files) shows both **also** use `CargoAPI.CrewXPLevel` (no fixer) plus two unrelated, uncatalogued `LocationAPI.addPlanet`/`StarSystemAPI.addOrbitalStation` signature mismatches — so Cobalt-Arms and Independant-Mining-Faction do **not** reach `READY_WITH_REVIEW_ITEMS` after all; both stay `ESCALATION_REQUIRED`. The same mod-wide rule also found `CrewXPLevel` in `Gen.java`/`ModGen.java`/mission `MissionDefinition.java` files across all five mods (up to 12 files in one mod), previously undercounted by the prior pass's single-file compile-check; Batavia/Qualljom/Antediluvians were already `ESCALATION_REQUIRED` on other findings, so their status is unchanged, but their reports now list the true scope. All five mods' `reports/REVIVAL_REPORT.md`/`REVIVAL_PLAN.md` updated with per-file compile results.
  - Tests: `tests/test_batch_lessons.py` (3 new scanner cases: extended `createFleet` receiver, `addMessage`, `CrewXPLevel`), `tests/test_rc8_bytecode_checks.py` (2 new: comment-only mention not flagged, same-line real use still flagged), `tests/test_fixers.py` (9 new: `addMessage` rewrite incl. bare-receiver form, `createFleet`+`addMessage` together adding the dependency once, `CrewXPLevel`-only refusal, mixed-file partial rewrite). Full suite: 803 tests, unchanged pass rate.
- **BF Legacy Fleets hardening (2026-09-15).** `LegacyFleets.addMember` no longer lets a single bad id abort the whole `fleetCompositions` build: an exception from `SettingsAPI.getFighterWingSpec`/`doesVariantExist` or `FactoryAPI.createFleetMember` (none declares a checked exception, javap-confirmed) is now caught per-call and treated exactly like the documented "not found" signal (skip, log once), instead of propagating out of `buildFleet` and discarding the entire partially-built fleet via `createFleet`'s outer `catch`. The `getMergedSpreadsheetData(idColumn, path)` argument order is now confirmed from real call sites (`javap -c` on 12+ MagicLib/LazyLib/Nexerelin call sites of the sibling `getMergedSpreadsheetDataForMod` overload, plus a LazyLib Kotlin extension function whose compiled `Intrinsics.checkNotNullParameter` calls embed its real parameter names `"id"` then `"path"`) — the order already used was correct; no code change was needed for that part. Recompiled and repackaged `working/jars/BFLegacyFleets.jar`; `javap -v` on the new jar confirms no forbidden sandbox reference.
- **Qualljom fleet-composition gap closed (2026-09-15, owner-approved, balance deferred).** `QuaIndependentSpawnPoint`/`QuaPirateSpawnPoint` request 15 fleet-type ids RC8's vanilla `independent`/`pirates` factions no longer define compositions for. Two new, partial (`fleetCompositions`-only) files, `In operation/Qualljom/working/data/world/factions/{independent,pirates}.faction`, were added at the vanilla paths (Starsector merges same-path faction files across mods) using only real RC8 vanilla variant/wing ids matching each faction's style; all 33 ship/wing references across both files were verified to resolve, and a rescan shows 0 new findings. Content is BridgeForge-authored, credited as such (not Qualljom's). Not yet live-tested: the cross-mod `getMergedJSON` merge this relies on is javap-verified but was previously unexercised by any of the six ported mods.
- New command `dependency-substitutes <mod>`: can a missing or discontinued dependency be replaced?
  - It indexes the hull mods, weapons, wings, hulls and classes (jar and loose) of every visible mod (`In operation` and the rig by default, or `--providers`).
  - It finds the smallest set of mods that provides what the mod needs, from the scanner's `content-reference-unresolved` and `source-import-unresolved` findings.
  - It recommends one course: SWAP, REVIVE_DEPENDENCY (an outdated provider that is a workspace here with 15 MANUAL or fewer), STRIP_FROM_MOD (3 or fewer unprovided ids in 5 or fewer places), or ESCALATE.
  - Queue results: FX Example → revive FX Core; Rebal → declare EZ Damage and Vacuum, revive AI Overhaul and FX Core; Explorer Society → escalate (`shields_formshield`, 14 places, exists only in Rebal); Communist Clouds → escalate (6 `vayra_*` ids; only a local, unrevived 0.95.1a Vayra's Sector 3.2.1 build provides them).
  - `bridgeforge/dependency_successors.json` records renames and dead ends with evidence: MagicLib's legacy `data.scripts.util.Magic*` classes, `BaseSpawnPoint`, `Corvus`, GraphicsLib's `shaderLib`, and the discontinued Vayra's Sector.
  - `docs/DEPENDENCY_STRATEGY.md` explains the courses and when to revive a dependency, strip it, or escalate.
- ROADMAP P14 (planned): dependency intelligence and queue throughput.
- **Correction: `BaseSpawnPoint` and `corvus.Corvus` were never removed.**
  - RC8's `starsector-core` still ships both as loose scripts (`data/scripts/world/BaseSpawnPoint.java`, `.../corvus/Corvus.java`). `BaseSpawnPoint` has the same constructor and abstract `spawnFleet()` that the 0.6 mods extend, and `LocationAPI.addSpawnPoint` still exists (javap).
  - The earlier "removed" evidence had checked only the jars. `LEGACY_VANILLA_CLASSES` is now empty, with a rule that entries need evidence from both the jars and the loose scripts.
  - All 116 of RC8's loose vanilla scripts count as defined classes: 58 hull mods, 23 star systems, 13 ship-system scripts, 18 missions and 4 others. They are listed in the new `bridgeforge/vanilla_loose_scripts_rc8.json`, generated from the core. So they are neither `legacy-vanilla-class-import` nor `source-import-unresolved`; Adjusted Sector imports `data.hullmods.HeavyArmor`.
  - The spawn-point findings on Cobalt-Arms, Gekelonians, Independant-Mining-Faction, Batavia, Qualljom, Antediluvians and Adjusted Sector were false positives for the class.
  - **The real blocker is the new MANUAL finding `removed-api-call`.** Those spawn points build fleets with `getSector().createFleet(faction, fleetType)`, and RC8's `SectorAPI` has no `createFleet` (javap). That's 17 calls in 6 mods.
    - The check matches only receivers whose type is certain (`getSector()`, `Global.getSector()`), and it ignores comments and `disabled_files`.
    - Without it, the three mods escalated for spawn points would have scanned with 0 MANUAL.
- **Packaging:** `pyproject.toml` package data now includes `dependency_successors.json` and `vanilla_loose_scripts_rc8.json`; the former was missing from installed copies.
- `legacy-vanilla-class-import` changes (the machinery is kept for evidenced entries):
  - It now finds a removed class used by simple name from its own package: `data.scripts.world` scripts extend `BaseSpawnPoint` with no import. Antediluvians wasn't flagged before; Batavia and Qualljom were flagged only partly; Cobalt-Arms and Independant-Mining-Faction each had a second, missed spawn-point file.
  - A mod that ships its own copy of the class, such as Vacuum's earlier shim, is no longer flagged.
  - The evidence gives the file count and up to 6 files, instead of silently cutting at 3.
- **Correction:** `dependency-substitutes` no longer offers a total conversion as a provider unless the mod declares it (an add-on). Vacuum defines `thruster_fighter_sm`, but Explorer Society and Rebal can't run beside it, so the earlier advice to declare Vacuum was wrong. The report lists excluded total conversions.
- Lenient JSON now follows RC8's `org.json` on every case found in the Ironclads archive triage. Each case was run through `starsector-core/json.jar` itself, not inferred.
  - **Strings:**
    - Raw tabs and other control characters load, so they're now accepted: new SAFE finding `json-raw-control-char` (Metelson Industries).
    - `\'` reads as an apostrophe: new SAFE finding `json-escaped-apostrophe` (Magellan, Foundation of Borken).
  - **Unquoted values** follow org.json's own rule. The value runs to the next `, : ] } / \ " [ { ; = #` or control character, and trailing spaces are trimmed. So `0b` and `博尔肯基金会（F.O.B）` are text, and a full-width `１.0` stays text, as in the game, where `getDouble` then fails on it.
    - `True`, `TRUE` and `False` are booleans (`equalsIgnoreCase`). 97 values across 31,713 files were previously read as text.
  - **Numbers:** these now read as org.json reads them: `1.`, `0.`, `.0f`, `1.f`, `+5`, `+0.5` and hex `0x1F` (Dassault-Mikoyan, Magellan, SCY, VAO).
  - **Empty array elements** (`["a",,"b"]`, `[,"a"]`) load as null. New REVIEW finding `json-empty-array-element`, since list readers may fail on the null (Valhalla Starworks' Nexerelin start ships).
  - **Result:** compared with the previous parser on 31,713 real files, no value changed except those 97 booleans, and 436 more files now parse. The 5 files that still fail are also rejected by the game's `org.json`:
    - missing commas in Hiigaran Descendants `polaris.json`, Yuri Expedition `vesperon_blueprints.json` and wotani `Wotani04.json`;
    - `::` in Tyrador `blacklist.json`;
    - bare Chinese notes in Mirfak's annotated copy of a `.proj` file.

- **Correction:** RC8's `com.fs.starfarer.api.loading.WingRole` still has ASSAULT (javap on starfarer.api.jar; Vacuum's ASSAULT wings load live, VAC-R003).
  - `fighter-wing-role-invalid` no longer reports ASSAULT.
  - `wing-role-assault-removed` and its fixer, which rewrote ASSAULT to FIGHTER and silently changed wing AI, are retired.
  - BUG_CLASSES SK-10 is updated. SEEKER was not affected: its 5 ASSAULT wings were replaced in its module migration, not rewritten.
- New fixer `target-interface-method-missing`, for loose `data/` scripts only; jar sources are refused, since the jar needs a rebuild. Types are fully qualified, so imports are untouched. It adds:
  - the six `ShipSystemStatsScript` `*Override` methods, with `BaseShipSystemScript`'s defaults (-1f / -1 / null);
  - RC8's `ApplyDamageResultAPI` parameter in `OnHitEffectPlugin.onHit`, before `CombatEngineAPI`;
  - `HullModEffect.showInRefitScreenModPickerFor`, returning `true` (BaseHullMod's default).

  All values were read from RC8's jar. The three API changes cause every `target-interface-method-missing` in the 2026-09-14 batch.
- Scanner, from the owner's carrier question and the queue:
  - `carrier-bays-proposal` (pre-0.8 data only): carriers come from the old `hangar` column or variant wings, and the count from the hull's LAUNCH_BAY slots. Drone-launcher systems get a caution. A description mentioning carriers is not evidence, and CARRIER hints or designations alone get no number.
  - `content-reference-unresolved`: hull mods, wings, weapons or hulls used by hulls, skins and variants that neither the mod nor vanilla defines, with the common id prefix named. It is MANUAL without declared dependencies. Communist Clouds is a Vayra's Sector add-on (`vayra_*`); Explorer Society and Rebal use a `thruster_fighter_sm` defined nowhere.
  - `library-import-unused-in-jar` (SAFE): source mentions a library, but the shipped jar never references it, so no dependency is needed. Examples: Bionic Alteration's unused Nexerelin import, AI-War, Edmunds-Church. `source-library-dependency-undeclared` defers to it.
  - `console-command-optional` (SAFE): Console Commands API used only by classes registered in `data/console/commands.csv`.
  - `source-import-unresolved` (REVIEW): `data.*` imports defined neither in the mod nor in a known library, so another mod is required (FX Example → FX Core; Explorer Society → EZ Damage). `disabled_files/` is ignored.
  - `legacy-vanilla-class-import` (MANUAL): 0.6-era vanilla classes that 0.98a no longer ships (`data.scripts.world.BaseSpawnPoint`, `data.scripts.world.corvus.Corvus`). Five queued mods build their faction fleets on BaseSpawnPoint.
- Fix: the `wing-data-missing-role-desc-column` fixer counted comma-only padding rows as blank and refused Cobalt Arms as if it had a multi-line field.
- New fixer `wing-data-missing-role-desc-column` (`bridgeforge fix --finding wing-data-missing-role-desc-column`). It appends a blank `role desc` column to `wing_data.csv`, padding short rows so the blank lands in the new column. RC8 cannot load the file without it (live bug VAC-R002, Vacuum), and a blank value was shown live to be accepted. It refuses when the column exists or a quoted field spans lines. Applied to four pre-0.8 mods from the 2026-09-14 queue.
- Fix: `mod-info-game-version-inexact` now also runs against a generic target such as the default `0.98.x`, comparing version series (`0.9.1a-RC8` is series 0.9.1, `0.98a-RC7` is series 0.98). It used to return early, so none of the 25 batch mods (0.53a–0.9.1a) was told the launcher would untick them.
- Lessons from the 2026-09-14 batch intake of 25 older mods (0.53a–0.98a). BridgeForge had no crashes; these five fixes came out of it:
  - **org.json separators.** The lenient JSON parser accepts `;` between pairs and elements, and `=` / `=>` between key and value. Starsector's `json.jar` accepts all of them, checked with the rig JDK. New SAFE finding `json-orgjson-separator`. Xenoargh's Rebal `settings.json` (`"baseNumOfficers":45;`) was an UNKNOWN unparsed file.
  - **Better parse errors.** A file that still fails after the lenient rewrites now reports where the rewrite stopped, not just the strict parser's first complaint (which pointed at a harmless `#` comment 26 lines earlier).
  - **Class declarations in strings.** Archaeology and the scanner's class index no longer read class declarations out of string literals, and archaeology rejects Java keywords as class names. A log message `"couldn't find the class for a System"` produced a class `data.scripts.for` (Xenoargh's AI Overhaul). `_blank_java_comments(text, strings=True)` blanks literal contents.
  - **Loose scripts need no jar.** `configured-source-class-missing-from-jar` no longer reports loose `.java` under `data/`: the game compiles those itself (vanilla ships loose `data/hullmods/*.java`; live bug PRB-MISSION-02). They are listed as `loose_scripts` in the scan context instead. 11 of the 25 old mods had a false MANUAL for this.
  - **Grouped shadowing.** `vanilla-path-shadowing` groups a folder with more than 5 shadowed files into one finding (count plus the first 25 files). Xenoargh's Rebal replaces 498 vanilla scripts, which had produced 498 MANUAL findings.

- New `lookup <thing> --mod DIR [--top N]`: a query surface over the mod's existing archaeology graph, not a second database. The saved `architecture.json` is used while its file hashes match the mod; otherwise it is rebuilt in memory with the same builder.
  - For a class, id, file or symbol it joins: definitions; references in and out by relation; related classes; lifecycle hooks and registrations; persistent-state candidates; save and probe baseline observations; source/bytecode status; scanner findings; behavior-map entries and their runtime coverage; external-mod references.
  - A class is queried through its aliases: its source file (imports hang off it), the same-named `symbol:` node (mod_info and data references) and its hook nodes.
  - Every item gets an **inspection priority**, an archaeology priority rather than an error score. Each point carries its reason: source/bytecode divergence (only when the mod has both), persistence (+1 unconfirmed, +3 with save/probe evidence, constants excluded), runtime registration, no known reference, external-mod references, findings (MANUAL/REVIEW), missing runtime coverage.
  - `--top N` ranks a mod's classes into a treasure map. On Flu-X it puts the mod plugin and the two unplayed plugin missions on top.
- New `novelty <mod> [--record]`: compares a mod's fingerprint with the corpus in `bridgeforge-state/corpus-fingerprints/` (gitignored). The fingerprint covers:
  - core API classes (members and constants folded into their class, the mod's own classes excluded even inside vanilla packages);
  - lifecycle hooks and registrations;
  - edge structures, with data files reduced to folder and type and jar resources to their top folder;
  - finding kinds;
  - weak ownership (no known reference, unresolved ownership, missing campaign fleet ids).

  `disabled_files/` is ignored. The report counts patterns already seen, unusual structures (seen in fewer than 2 other mods), and new API usages, lifecycle patterns and finding kinds. First corpus of 14 mods: Zorg18 has 92/92 patterns seen; Mirfak has 47 unusual structures and 18 new API classes.

- New `preset-check <bf-test.ps1>`: checks every test preset against the rig's installed mods. Errors: the preset's own mod or a dependency it declares isn't enabled, an enabled id isn't installed, or the folder has no mod_info. Warning: an enabled library that no enabled non-library mod needs, either through declared dependencies (followed transitively) or by referencing its package in sources or jar classes. That keeps optional LunaLib use quiet when a mod really uses it. First run: the `flux` preset still enabled the LazyLib and MagicLib that Flu-X r3 dropped (fixed); five other presets carry a possibly deliberate extra library.
- New `docs-index` command (with `--check`). It regenerates `docs/CHECKS.md` and a new `docs/COMMANDS.md`, which covers every command and nested subcommand with its arguments, notes and help, taken from the real argument parser. `docs/CHECKS.md` gains a *Bug classes* column linking each finding to the `docs/BUG_CLASSES.md` rows that cite it. A ratchet (`tests/untested_checks_baseline.json`, 23 ids today) fails when a new finding id has no test naming it, and when a baselined id gains one, so the list can only shrink. `docs/CHECKS.md` is built from the source with `ast`:
  - every scan finding id (including table-driven ones like `LEGACY_API_RULES` and computed `bundled-{...}` ids), with its classifications and severities (both branches of a conditional), the `module:function` that emits it, the first sentence of its explanation, and the test modules that name it;
  - every `revival-audit` issue id;
  - an index of `scanner.py`'s private helpers with signatures, to reuse instead of re-deriving.

  `tests/test_checks_index.py` fails when either file is stale, so neither can drift. The first index shows which finding ids no test names; for example, the lenient-JSON findings are only tested through the parser's tolerance list.
- Fix: `revival-audit` no longer reads "NOT PERFORMED" as a completed validation. It had reported `plan-validation-state-stale` for honestly unticked plan items (Zorg18 r1).
- Scanner, from Zorg18:
  - New `campaign-fleet-reference-missing` (MANUAL). Campaign spawners that keep variant and wing ids in arrays and pick one at run time are now checked. In any source that uses `FleetMemberType`, a mod-prefixed `..._wing` literal must be a wing, and a literal starting with one of the mod's hull ids must be a variant. Missions keep their own check.
  - `faction-known-lists-missing` drops to low when the faction has no shipRoles and no market evidence: no econ JSON, no Nexerelin faction config, and no `setFactionId`/`createMarket`/`addMarket` beside the faction id in the sources or in the jar's bytecode. It stays high when compiled code without sources could create markets. First sweep: only helper factions dropped (Exigency `mysterious_contact`, FlowerGod `copyplayer`, Zorg18 `zorg`).
  - New `system-generation-unguarded` (REVIEW): `createStarSystem("X")` with no null check on `getStarSystem("X")` anywhere and no memory-flag check around the generator. It rates medium when the generator is named in a ModPlugin's `onGameLoad` (the system is duplicated on every load) and low otherwise. Total conversions and `SectorGeneratorPlugin` replacements are exempt. Zorg18 r2 now has both guards.
  - New `core-campaign-plugin-reregistered` (REVIEW/low): a mod that registers vanilla's `CoreCampaignPluginImpl`, which vanilla's SectorGen already registers (RC8 `SectorGen.java:168`), so each new game keeps a duplicate core plugin in its save. It's a 0.6-era template line. Total conversions and `SectorGeneratorPlugin` replacements (Vacuum) are exempt. First sweep: Zorg18 only.
  - `hard-coded-campaign-system-reference` is SAFE/low when the lookup is null-checked, inline or through the variable it is assigned to (Flu-X `radikius`, Zorg18 `askonia`, Arkgneisis `Anargaia`, Broken-Star `Danai`). Unguarded lookups stay REVIEW/medium.
- Fix: `translate-apply --out` makes its own copy writable. `copytree` kept the read-only attribute of Mirfak's source files, so writing the translation failed half-way. The source keeps its attributes.
- Scanner (P13), three more checks from the Chinese mods:
  - `non-ascii-identifier` flags spec ids (CSV `id`, `hullId`, `skinHullId`, `variantId`, `.wpn`/`.proj`/`.faction`/`.system` `id`) with non-ASCII characters. Prose spilled into an id column is left to `csv-row-extra-columns`.
  - `non-ascii-file-path` flags shipped file names with non-ASCII characters.
  - `data-file-not-utf8` flags data files that aren't valid UTF-8, with the line and the likely encoding (GB18030 or CP-1252).
  - `csv-fullwidth-number` (SAFE) flags CSV cells that are numbers written with full-width digits or punctuation (`１５００`, `0。5`); prose with Chinese punctuation is ignored.
  - `shippable-work-file` now also lists archives (`.rar`, `.7z`, `.zip`) and Windows shortcuts (`.lnk`, `.url`); Omega-Trauma ships both.

- New `behavior-decide <discovery_dir> <decisions.json>`: applies written decisions (select by risk/unknown/behavior ids, lifecycle, subsystem or entry-point prefix; status, why, evidence, by, on) and writes `risks.decided.json` / `unknowns.decided.json` for `release-behavior-evaluate`. The generated maps are never edited. A decision that selects nothing is refused as stale, so regenerating the maps can't silently drop one. Exit 1 while HIGH risks or unknowns are still open. First used on Flu-X: 38 of 42 unknowns decided; the 4 mission-plugin unknowns and 4 HIGH risks wait for the mission live test.
- Scanner: `rules-condition-merged-lines` flags a rules.csv condition where two lines were glued together (`$faction.id == infected$faction.hostileToPlayer`), so the rule never fires. Vanilla RC8 has 0 such rules in 11,107. `rules-condition-unknown-faction` (needs `--vanilla-core`) flags `$faction.id ==` naming a faction neither vanilla nor the mod defines. Found in the original Flu-X greetings, including one copied from Templars.
- Fix: archaeology no longer reads class declarations out of comments. Flu-X's `// Only class allowed to import exerelin.*` produced a fake class `allowed`. The scanner's own-class index had the same bug.
- Fix: `archaeology --output <discovery>/archaeology` no longer nests a second `archaeology/` folder, which had left the old maps in place and stale (Flu-X). The discovery folder is still the documented argument.
- Scanner: `jar-entry-unreadable` names jar entries that fail their CRC or can't be decompressed, and the rest of the jar is still scanned. Previously a single bad entry turned the whole jar into `unreadable-jar` (the Chinese Nightcross jar). Every entry is now read, so resource files are checked too.
- `revival-audit`: new WARNING `dependency-claim-stale` when the report's DEPENDENCY CHECK calls a library (LazyLib, MagicLib, GraphicsLib, Nexerelin, LunaLib) declared but mod_info.json doesn't declare it. Clauses that call a library optional are ignored. Found on Flu-X after its unused libraries were dropped.
- Releases and copy-drift never include OS/VCS litter: `Thumbs.db`, `desktop.ini`, `.DS_Store`, `__MACOSX/`, `.git/`, `.svn/`, `.idea/`, `.vscode/`. New scanner check `shippable-work-file` (REVIEW) lists editor and work files that would ship (`.psd`, `.xcf`, `.kra`, `.blend`, `.tmp`, `.orig`, `.old`, `.log`, `*~`, `.swp`, `.rej`, `.diff`, `.patch`).
- Scanner (P13): `player-text-non-english` counts CJK text in data files outside comments, per file; `translate-check` also covers jar strings. `design-type-color-duplicate-key`, `design-type-color-unused` and `design-type-without-color` (the last needs `--vanilla-core`) check that designTypeColors keys match the tech/manufacturer text exactly, counting vanilla's keys. Starsector's `#` comments are honoured.

- New `translate-export` / `translate-apply` / `translate-check` commands (`bridgeforge/translation.py`) for mods whose player-visible text isn't English. They read Starsector's own lenient formats directly, with no input normalisation:
  - CSV cells by raw span
  - JSON-like strings and keys, with their paths, through `#` and `//` comments, single quotes and barewords
  - loose Janino `.java` scripts outside `src/`
  - jar string constants (CONSTANT_String → Utf8)
  - prefill from a zh/en translator record (`--record`) or an English copy of the mod (`--reference`: CSV row+column, JSON path, and jar constants when the class layout matches)
  - apply refuses changed sources, checks placeholders (`%s`, `$vars`, `\u0001`), edits only each value's span, and re-verifies CSV shape, JSON parsing and class parsing
  - `translate-check` reports leftover CJK and designTypeColors keys that no tech/manufacturer uses
  - jar entries with bad CRCs are reported, not fatal
  - `translate-tm` writes a translation layer as Project Go (SSMT) translation memory, for `ssmt tm import <db> json <file>`. English recovered from the original author is marked `AUTHOR_LOCALIZATION`; our translations are `AI_TRANSLATED`. Verified on Nightcross: 1,035 entries imported into a Project Go database, passed `tm integrity`, and exported back identical.
  - `$variable` placeholders are ASCII-only. Python's `\w` also matches CJK, so a memory key glued to Chinese text (`$LTHS_Person1标记的NPC…`, Mirfak's rules notes) had swallowed the sentence into one "placeholder" that no translation could keep.
  Built for the 2026-09-13 Chinese intake (Nightcross, Mirfak Parcel Service, Blackrock CN), where Project Go's strict parsers and partial coverage fell short.
- `_parse_json` now accepts the remaining org.json leniencies seen in that intake: leading-zero and leading-dot numbers (`098`, `.7`), and data after the root value, taking the first value as the game does. New findings:
  - `json-lenient-number` (SAFE)
  - `json-trailing-brackets` (SAFE)
  - `json-content-after-root` (REVIEW): keys after an early closing brace never load; Blackrock's `br_consortium.faction` loses its `factionDoctrine`
  All 19 Mirfak and Blackrock files that failed to parse now parse.
- Scanner false positives fixed:
  - `.wpn` / `.variant` / `.ship` specs are keyed by their declared id, not their filename. Nightcross's `naai_mare_center.wpn` declares `naai_mare_deco`, which is registered.
  - `csv-row-extra-columns` now separates spilled content (MANUAL/high) from empty spreadsheet padding (SAFE/low).
  - `undeclared-library-dependency` recognises `isModEnabled` guards in bytecode, for jar-only mods, not just in source.
  - `loose-script-janino-risk` skips loose scripts whose class is also in a loaded jar. The game never compiles those ("already loaded (perhaps from jar file) ... skipping compilation"). They are reported once as the new `loose-script-shadowed-by-jar` (SAFE): Mirfak ships most of its hullmods both ways.
  - With `--vanilla-core`, a local `.wpn` that overrides a vanilla-registered weapon (Blackrock's `blinker_green`) is no longer also reported as `local-weapon-spec-unregistered`; `vanilla-path-shadowing` already reports the override.
  - `external-mod-api-import` ignores imports of the mod's own classes, even in a library-named package. Blackrock ships its own `data.scripts.util.AnamorphicFlare` / `BRDYMulti`, and `data.scripts.util` is MagicLib's legacy prefix.
- `scan --output` help now says it is an output folder.
- Nightcross (English mod shipped as a Chinese re-translation): English fully restored into `working` from the translator's own record, via Project Go plus a finishing pass (861 more strings: 530 jar constants, 331 data values). Its three required libraries are now declared in `mod_info.json`. Build tag Nightcross Armory [BF r1]; synced to the rig. `bf-test.ps1` presets `nightcross` / `nightcross-nex`.

- Live run EX-7c confirmed EXI-EVENT-01 fixed on Exigency [BF r3]. Flying an Exigency destroyer past an Exigency fleet showed the "caught" message and "Relationship with ExigencyCorp reduced by 20 (hostile)". Exigency EX-7 now passes, along with EX-B5 (Nex Corvus, scenario PASS) and EX-B6 (Nex random sector, clean).
- Live run EX-7b confirmed EXI-FLEET-01 fixed. Exigency fleets spawn from the Tasserus anomaly, and probe 0.2.1 counted 21-23 of them.
- Exigency fix for EXI-EVENT-01 (live run EX-7b). The illegal-tech event detected Exigency hardware in the player's fleet but applied its reputation penalty inside a `reportEventStage` delivery script, and that call does nothing in 0.98a. The penalty now runs directly, with a campaign message ("An ExigencyCorp fleet has identified restricted Exigency technology in your fleet."); RC8's reputation plugin posts its own notice of the change. The recompile kept the jar's class names (`$1`/`$2`/`$3`/`$Offense`). Backup `EXI.jar.pre-event-fix.bak`. Build tag Exigency [BF r3].
- New check `legacy-event-report-noop` (MANUAL) flags calls to `SectorAPI.reportEventStage` in jars and source. A sweep found Exigency's event and FlowerGod's `FG_PersonBountyEvent`; FlowerGod's is still to be reviewed.
- Probe 0.2.1: the known-lists and fleet-count checks now include the tested mod's own factions even when they own no markets (PRB-FACTION-01). `probe-config` writes a new `factions` config key, read from the mod's `data/world/factions/*.faction`. Those counts are logged as INFO, because contact or story factions may field no fleets. Market-owning factions keep WARN at 0 fleets. The stock check also skips each market's storage tab, which is always empty for the player (PRB-STORAGE-01).
- Exigency fix for EXI-FLEET-01, "no fleets in Tasserus" (live run EX-7). Exigency's attack and defense fleet managers, and its random missions, build fleets from a bare `createMarket()` market. RC8's `FleetFactoryV3` scales fleet size by that market's combat fleet-size stat, which is 0 on a bare market, so every fleet came out empty and vanished, with no error. The shared revival adapter `exigency_FleetParamsCompat` now gives such markets what vanilla gives its own no-market fallback: fleet-size multiplier 1 and quality 0.5. Real markets such as Avesta are untouched. Only that one class changed in `jars/EXI.jar` (backup `EXI.jar.pre-fleetsize-fix.bak`). Build tag Exigency [BF r2].
- New check `fleet-source-bare-market` (REVIEW) flags fleets built from a bare `createMarket()` source when the same tier (jar or source) never sets the fleet-size multiplier. It flags the pre-fix Exigency jar (4 classes) and passes the fixed one. It also flags FlowerGod's vendored `FleetFactoryV2_FG`, which is still to be reviewed.
- The probe mission's `icon.jpg` is vanilla art (Fractal Softworks), so the public repo no longer carries it. Both copies are gitignored. `build-probe-mod --install-release` copies it from `--core` (`data/missions/afistfulofcredits/icon.jpg`), and without it the release fails with a clear error instead of shipping a mission that Fatals at startup.
- Live run SK13-1e confirmed SEEKER-PERSONALITY-01 fixed on Seeker [BF r3]: triage FATAL=0, MOD-ERROR=0, no `getPersonality` NPE. Live runs FLX-R4b (Nexerelin Corvus: Radikius generated once, Infected fleets normal) and FLX-R5 passed, so Flu-X has now passed FLX-R1..R5.
- `log-triage` now files RC8's own `Weapon [lightmortar_fighter] from weapon_data.csv not found in store` warning as known noise. Vanilla keeps a `#`-named row with no `.wpn` file, so every run logged it and it showed up as an unexplained OTHER event.
- SEEKER fix for SEEKER-PERSONALITY-01, a Fatal on deploy in five SEEKER missions (live run SK13-1d). The missions gave enemy captains the 0.6-era personalities "suicidal"/"fearless", which RC8 lacks, so the personality stayed null and the ship AI crashed. The five `MissionDefinition` classes now use "reckless", changed by a same-length constant-pool edit in `jar/SEEKER.jar` with no recompile; the other 122 jar entries are byte-identical. Build tag Seeker [BF r3].
- New check `personality-id-unknown` (MANUAL) flags `setPersonality` ids RC8 doesn't define, in jars and in source. Ids a mod adds in its own `data/characters/personalities.csv` count as valid (Vacuum). A sweep of every working copy found SEEKER's 5 classes and nothing else. Flu-X's "The infected are fearless" briefing line is correctly ignored.
- `log-triage` names this crash: new FATAL rule "Null officer personality (unknown personality id)".
- `bf-test.ps1` gains a `flux-nex` preset (Flu-X plus Nexerelin) for FLX-R4. Live runs FLX-R1..R3 passed with no issues.

- The probe combat mission no longer deploys wreck-only hulls (PRB-DEBRIS-01): hulls whose `ship_data.csv` designation is Debris, Wreck, Hulk or Fragment. SEEKER's 13 "Debris" hulks were disabled on arrival and pushed real hulls (ART_armor, SKR_clipper, CIV_titanic) out of the battle.
- Live run SK13-1c confirmed SEEKER-DEATH-01 fixed (the Betelgeuse shatters once, with no slowdown) and the pirate spawn sized correctly (12 ships, ~120 FP).

- SEEKER fix for SEEKER-DEATH-01, the Betelgeuse death slowdown (live run SK13-1b). `ART_organicHull` ran its death effect every frame on the persisting wreck, spawning 3 debris ships and 15 projectiles each frame. It now runs once per ship, guarded by the ship's custom data. The class was patched into `jar/SEEKER.jar` the same way as SEEKER-STATIC-01.
- New check `hullmod-instance-state` (REVIEW) flags hull mods that keep mutable instance fields, which are shared across every ship with that hull mod. It works on jars or source.
- Fix the probe's `spawn-fleet` sizing (PRB-FLEET-02). It stops at the requested fleet points via `getFleetPoints()`; before, 120 FP produced a 40-ship fleet.

- Fix `copy_drift` ignoring jars outside `jars/` (BF-DRIFT-01). It now also collects every jar `mod_info.json` declares. SEEKER's `jar/SEEKER.jar` had never been compared or synced, so drift reported PASS while the rig ran an old jar, and a `release` would have shipped SEEKER without its code.

- SEEKER fix for SEEKER-STATIC-01, the first real mod crash found by a live run (SK13-1).
  - `ART_thrusterRotation` and `ART_shockwave_weaponGlow` kept per-weapon state in `static` fields shared across every copy in a battle. Vector-cruiser debris spawned mid-battle overwrote them, and a living cruiser then read a ship with no system, which was a Fatal NPE.
  - The fields are now instance fields, `getSystem()` is null-checked, and the glow effect skips ships lacking their gun or beam.
  - The two classes were recompiled from the jar's own decompiled source and swapped into `jar/SEEKER.jar` surgically; all other entries are unchanged, and the pre-patch jar is kept as `SEEKER.jar.pre-static-fix.bak`.

- Fix the Vacuum bounty-board dialog lock (VAC-DIALOG-01, player report). The revival's station options re-populated the menu with `FireBest PopulateOptions`, so only one options rule ran and Leave could disappear. Both rows now use `FireAll PopulateOptions`, as vanilla does everywhere. Vacuum's build tag is bumped.
  - New check `rules-firebest-populate-options` (MANUAL) flags this in any mod's `rules.csv`; Vacuum was the only mod affected.
- SEEKER and Flu-X pulled back from `Done/` for re-processing (owner, 2026-09-13), logged in `In operation/_REORG_2026-09-13_done-pullback.json`. SEEKER's working copy is now `In operation/SEEKER/working`.

- New check `weapon-effect-static-combat-state` (MANUAL) from live run SK13-1, SEEKER's first real crash found by a live run.
  - It flags per-weapon plugin classes (`EveryFrameWeaponEffectPlugin`, `OnFire`/`OnHit` effects) that keep a ship, weapon, engine controller, system or projectile in a `static` field, in loaded jars or in source.
  - SEEKER's `ART_thrusterRotation` shares `static ShipAPI ship` across every weapon copy, so Vector-cruiser debris spawned mid-battle made a living cruiser read a ship with no system, which is a Fatal NPE.
  - The class-file parser now records the superclass, interfaces and field flags.
- `log-triage` classifies an exception escaping `CombatMain` as FATAL ("Combat loop exception"). It had shown as MOD-ERROR, although the game shows a Fatal dialog.
- Fix the probe's `spawn-fleet` setup (PRB-FLEET-01). It asked factions for role `"combat"`, which doesn't exist, and now tries `combatSmall`/`Medium`/`Large`/`Capital`.

- Fix `save-content` false failures found by live run PRB-2: 50+ false "missing" ids on a healthy Exigency save.
  - Wing ids now come from `wing_data.csv`, not variant file names.
  - Faction relation keys (`exigency_hegemony`…) are skipped.
  - A mod-prefixed string counts as MISSING only inside real data-id lists: known lists, hullmods, wings, fleet-member variants. Elsewhere, for example runtime-created market ids, it goes to a new `unattributed_prefix_matches` list and doesn't fail the check.
- Fix `save-diff campaign.xml campaign.xml.bak` comparing a file with itself. An explicit `campaign.xml*` path is now used as given.

- Fix the probe's planet check reporting every planet as a failure (PRB-PLANET-01). It looked types up with `getSpec(PlanetSpecAPI.class, …)`, which never resolves them. It now checks each planet's type against `getAllPlanetSpecs()`, logs FAIL only for genuinely unresolved types, and ends with one summary line instead of one line per planet.
- First fully working live run (PRB-1c): the campaign checks ran, 12 real Exigency ships deployed with no Nebulas, and the `avesta-near` scenario passed. The clock timestamp was logged as `-55661260032000`, confirming PRB-CAMPAIGN-01's negative-timestamp cause.

- Fix fighter hulls being deployed as ships in the probe combat mission (PRB-FIGHTER-01). Exigency's Tarujan, Azata and Naxos have blank `ship_data.csv` hints, so the probe treated them as ships, and the game swapped in a vanilla Nebula starliner. The probe's hull list now also excludes any hull whose `.ship` file declares `hullSize: FIGHTER`.

- Fix the probe's combat logging (PRB-COMBAT-01). The first successful run logged only START and END: ships spawn after the plugin's `init()`, so the deployment and captain-personality checks saw no ships.
  - Each ship is now logged the first time a combat frame sees it, with a `combat-summary` count at the end.
  - The campaign script logs `campaign-armed` on its first tick, so a log shows whether the check window was ever reached.
- Fix the campaign probe never running its checks (PRB-CAMPAIGN-01). It used `startTimestamp < 0` as "not started", but campaign clock timestamps can be negative, so it re-armed every frame (1,519 `campaign-armed` lines in one session). It now uses a boolean, and the heartbeat records the clock timestamp.

- Fix the third live-run failure (PRB-COMMON-01): the probe stayed switched off because Starsector appends `.data` to common-file names.
  - `probe-config` now writes `bf_probe_rig.data`, `bf_probe_config.data` and `bf_probe_profile.data`.
  - A new test pins each on-disk name to its Java `ProbeFiles` name plus `.data`.

- Fix the second live-run crash (PRB-MISSION-02). The game compiles loose scripts with Janino, which ignores generics, so the probe mission's for-each over `Map.Entry<String, String>` failed as Object → String.
  - The mission now iterates with a raw iterator and explicit casts, the way vanilla loose scripts do.
  - A new scanner check, `loose-script-janino-risk` (REVIEW), flags typed for-each loops, diamonds and lambdas in loose `data/**/*.java` files.
  - `log-triage` now classifies Janino compile errors and `Error loading [class]` failures as FATAL; before, they showed as FATAL=0.

- Fix the first live-run crash (PRB-MISSION-01). The probe's combat mission shipped without `mission_text.txt` and an icon, which is a Fatal dialog before the main menu.
  - The mission now ships all four files every vanilla mission has.
  - A new scanner check, `mission-required-file-missing`, flags any listed mission missing a required file or its declared icon.
- `rig-doctor` no longer compares the revived working copies with a historical reference rig. It had suggested a `prepare-test --sync` that would overwrite the original mod there. By default it now compares only the mods installed in the rig being checked (Vacuum has its own rig), and explicit `--working` entries are still always checked.

## 0.2.0 — 2026-09-12

Everything landed since the `v0.1.0-alpha.1` tag. The tool and
`bridgeforge-probe` report version `0.2.0`. This tool release does not certify
individual mod revivals, historical runtime behavior, or save compatibility.

- Complete P12C Vacuum layout migration with before/after byte and link evidence.
  Retain the earlier modified attempt and pre-carrier ZIP, correct only the rig
  JDK path and working-copy junction, and keep probe/report/live gates explicit.

- Implement P12B dry-run-first guarded `promote`, staged package identity checks,
  per-release reports, recoverable prior-release retention, and publication rollback.
  Preserve declared live-test requirements. Bundle release policy in installed
  packages and fail closed on missing or malformed policies.

- Implement P12A source-preserving ZIP `intake`, deterministic declared-evidence
  `board`, optional generated status files, and read-only rig-doctor layout warnings.
  Intake never replaces existing mod folders or approves a revival plan; unknown
  test/risk evidence remains explicit. Harden portable ZIP paths/collisions and
  retain empty upstream directories. Promotion/release hygiene remain separate.

- Implement P11 tool hygiene: read-only `who-locks` and rig-doctor process-path
  checks, Windows Restart Manager diagnostics, declared psutil dependency, and
  PID/start-time-scoped interruption cleanup in the versioned `tools/bf-test.ps1`.
- Guard the six-job CI suite against checkout/probe-release end-state drift;
  add resolved-temp-path fixtures and move checkout/setup-python to Node24.

- Implement the offline portion of roadmap P10 reference rigs.
  - Add `rig-create` manifests with core/JRE hashes, bundled Java metadata, run command, save location, and an explicit unprovable-isolation limitation.
  - Teach `rig-doctor --reference-manifest` to validate historical rig identity/version while skipping the incompatible RC8 probe.
  - Add five evidence-gated `era-*` compatibility sets; their installer accepts a verified `--reference-manifest` without weakening the normal junction guard. Add `save-baseline` conversion of old-game saves into D2 no-verdict observations.
  - Keep the Exigency and 0.8.1a live pilots separately gated on dedicated-install identity, authoritative dependencies, and observed runtime evidence.

- Implement roadmap P9 v2 stages D0-D6 as an interruption-safe behavior-discovery pipeline.
  - Add deterministic `archaeology`, `behavior-map`/`risk-register`, no-verdict `probe-baseline`, `hypotheses --tests`, `behavior-diff`, `release-behavior-evaluate`, and counts-only `coverage` commands.
  - Add the `expect add|approve|retire|check` decision lifecycle with required RISK/HYP/TEST breadcrumbs and recoverable last-edit backups.
  - Dossier presentation now includes architecture, behavior, risk, unknown, coverage, and recommended-test sections.
  - CLI release packaging now requires D5 behavior evidence and can block on unresolved deltas, open HIGH risks, preserved unknowns, or invalid expected changes; approved changes are grouped by build in release notes.
  - Exigency and SEEKER D0/D1 pilots are kept under ignored artifact storage; they do not modify source mods or completed releases.
  - Align runtime `bridgeforge.__version__` with the `0.2.0` package metadata so generated evidence records the correct tool version.

- Fix the CI failures of the 0.2.0 push.
  - `test_prepare_test` imported the Windows-only `_winapi` unguarded, which broke Linux.
  - The boot-test launch and matrix tests are now Windows-only, since they launch a `.bat`.
  - Five tests now resolve their temp dirs, because GitHub's Windows runners use 8.3 short paths (`RUNNER~1`).
- `test_probe_mod_build` no longer deletes the real `probe-mod/releases/bridgeforge-probe` copy that `probe-config --install` ships. It parks and restores it.
- `rig-doctor` finds working copies by the folder convention (`In operation/<Mod>/working`, then `Done/<Mod>/<release>`) instead of a hard-coded list. The test rig is now `In operation/_rig`.

The probe gained `ProbeSetup` and `ProbeProfile`. Its `BF-PROBE|0.2.0|…` lines
show which probe build produced a log.

- `log-triage --mods-dir <mods>` (with `--all-mods` for a log from another mod list) names the mod whose loaded jar threw each exception.
  - Each exception gets `suspect`, the mod closest to the throw, and `involved`, every mod on the stack. The attribution summary counts exceptions per suspect.
  - Built for the SEEKER/AI Tweaks NPE (SK-13) and for foreign modpack logs.
  - The package fallback uses only a class's own package, only when a single mod owns it, and never the shared `data.*` loose-script packages, which misattributed Exigency frames to SEEKER.
- Add `bootstrap <mod_dir>… --vanilla-core <core>`: writes a scan baseline (`bridgeforge-state/baselines/<mod-id>.json`, kept unless `--overwrite`) and records the current build manifest for each mod, so `test-plan` and `release` work immediately. Nothing is written inside mods.
  - `build-tag --record-only` records the manifest for the current build (`r0` if untagged) without bumping.
- Add editable probe setup profiles (P3c-1): Notepad-friendly `.txt` files.
  - Line forms: `rep F = L`, `credits = N`, `ship V xN`, `spawn F FP`, `jump S` and `apply = once-per-save|every-load`, with `#` comments and a leading `-` to disable a line.
  - Wired as `probe-config --profile NAME|PATH`, with bundled `exigency-rep`, `seeker-betelgeuse` and `flux-basic`.
  - The profile is written to the rig as `saves/common/bf_probe_profile`. The probe re-reads it at every campaign load, and when present it replaces the config's setups.
  - A leftover profile is retired to `bf_probe_profile.prev` when a later `probe-config` has none, so it can't silently override that run's `--setup` list.
  - The probe jar now has 16 classes and remains sandbox-clean.

- Add `rig-doctor <rig>`: pre-flight checks before a test session. Each problem comes with the command that fixes it, and it exits 1 on any FAIL.
  - Checks: the `starsector-core` junction, no rig game running, the probe installed and matching its release copy, every enabled mod resolving (dependencies and base `gameVersion`), and working-copy drift for the 9 known mods (from `default_working_copies`).
  - `--real-install` confirms the real install's saves are untouched, compared with a listing recorded once by `--write-saves-baseline` in the gitignored `bridgeforge-state/`.

- Add `test-plan <mod> --since rN` (P5): lists the features and minimal live tests to re-run for what changed since a build tag.
  - Changed files map to features (markets and fleets, ship systems, new game, refit, combat, scripted, text, launcher) through a data-driven rules table.
  - It returns the matching probe assertions and `LIVE_TEST_INSTRUCTIONS.md` test IDs.
  - `build-tag` and `prepare-test --bump` now record a per-tag file hash manifest by default (`--no-manifest` to skip). Manifests are stored outside the mod, in `bridgeforge-state/build-manifests/` (gitignored).
- Add `perf-gate` (P6): ingests SPW's `performance-report.json` at file level, counts log spam per mod, and gates against owner thresholds. It is report-only until thresholds are set.
- Dossier gains `--save` (runtime footprint: live classes, scripts, factions and markets; P3b-J) and `--perf` / `--perf-mod-prefix`.
- Add `docs/BUG_CLASSES.md` (P7): 14 live-found bug classes, each with its check, probe assertion or test.
  - A registry test fails if a listed check id stops existing.
  - `AGENTS.md` now requires every live finding to close with a check, a probe assertion, a test or a written reason.
- Add `release` (P8, plus the P3b-M save-corpus gate). It is a dry run by default; `--apply` writes only when every gate passes.
  - Gates: no new MANUAL findings against the baseline, jar-audit against the original, a build tag present, copy-drift, a save-corpus re-check and a licence policy (`bridgeforge/release_policy.json`; Exigency is `local_only`).
  - Output: a forward-slash zip and the `Done/` layout, with a release note built from the build manifests.
  - Jars in `jars/` that `mod_info.json` doesn't load are listed (`excluded_unlisted_jars`) and never shipped. This was found in Omega-Trauma, whose `jars/` holds three unloaded `Omega_Psychasthenia_old*.jar` leftovers.

- Add read-only save tools (roadmap P3b A/E/F/G/H/I/L).
  - `save-inspect`/`save-diff`: tracked mod state (e.g. Avesta's `waypoint`/`progress`/`loitering`), known-list sizes and per-mod object counts, compared across two saves. The diff matches objects by path, because XStream's `z=` ids are not stable between saves.
  - `save-scripts`: flags a mod script or listener registered more than once on the same holder.
  - `save-growth`: object and size growth across a save chain.
  - `save-provenance`: which mod versions and BF build tags made a save, compared with the working copies (`STALE_BUILD`).
  - `save-content`: the data ids a save stores as strings, checked against the build plus vanilla.
  - `save-removal`: internal only.
  - `save-summary`: a redacted, shareable summary with no player data.
  - Shared streaming reader: `bridgeforge/save_reader.py`.
  - Validated on real Exigency and SEEKER rig saves.
- Add `save-snapshot {tag,list,restore}` (P3b-D): rig-only save copies with a hash and build-tag manifest. Restore never overwrites without `--replace`, and never touches `saves/common`.
- Add `probe-config --setup` (P3b-C): `rep:`, `credits:`, `ship:`, `spawn-fleet:` and `jump:`.
  - The probe mod's new `ProbeSetup` applies each setup once per save through the public API.
  - RC8 has no public `FleetFactoryV3`, so fleets are built with `createEmptyFleet` plus `pickShipAndAddToFleet`.
  - The probe jar now has 15 classes and remains sandbox-clean.
- Add `scenario {list,plan,check}` (P3b-K), with bundled scenarios `avesta-near`, `betelgeuse-damaged` and `nex-corvus-day1`, each listing its expected probe and save results.

- Correct the `gameVersion` rule. The Starsector launcher matches on the
  **base** version (`0.98a`), not the release candidate: LazyLib, LunaLib
  and Console Commands (`0.98a-RC5`) and MagicLib (`0.98a-RC7`) all loaded
  and ran in an RC8 test rig.
  - `mod-info-game-version-inexact` now fires only when the base version
    differs (e.g. `0.97a` against an RC8 target), at high severity with an
    accurate explanation. An older RC of the same version is no longer
    flagged.
  - `compat-set install`'s gameVersion warning follows the same rule.
  - This replaces the earlier "exact RC match or the launcher silently
    unchecks the mod" assumption.
- Add the standard compatibility pack (roadmap P4).
  - `bridgeforge compat-set install <set> --runtime <rig> --source-mods <dir>
    [--dry-run] [--json]` installs a named mod set from
    `bridgeforge/compat_sets/standard.json` into an isolated rig:
    - `libs`: LazyLib, MagicLib, LunaLib, GraphicsLib (`shaderLib`).
    - `standard`: the libs plus AI Tweaks, Nexerelin (recorded as needing
      MagicLib for new-game generation), Ship/Weapon Pack, Industrial
      Evolution, Unknown Skies and Tahlan Shipworks.

    It copies only missing or drifted files, never copies rig → source, and
    refuses a rig without a junction.
  - `bridgeforge boot-test --mods … --pack standard` runs a two-leg matrix
    (the target with its libs, then the target plus the whole set) through
    `boot_test.run_boot_matrix`. The verdict is `PASS`, `FAIL_ALONE`,
    `FAIL_WITH_PACK_ONLY` (the interaction class behind this week's
    SEEKER/AI Tweaks and Nexerelin/MagicLib crashes) or `SUSPECT_FATAL_DIALOG`.
- Polish `bridgeforge dossier`:
  - `open_questions` leaves out retain-unchanged and informational findings
    (SAFE or info severity, plus a documented noise-id set such as
    `non-strict-json-trailing-comma`), which stay in the parts.
  - A finding id repeated across ≥3 files collapses to one line with a count
    and a file sample.
  - The index Markdown renders as readable prose and tables, not Python
    reprs.
  - `external-mod-api-import` now carries the real importing file and line,
    not "unknown location".
  - Real effect on Legacy of Arkgneisis: index 25.5 KB → 16.0 KB, open
    questions 62 → 21.
- Add `bridgeforge save-compat <save> <mod_dir> [--vanilla-core] [--compare-old
  X --compare-new Y] [--json]` (roadmap P3b-B, `bridgeforge/save_compat.py`).
  It checks whether an existing save's referenced mod classes are present in
  the build's loaded jars (`LOADS`/`WILL_FAIL`/`UNKNOWN`), reading the save as
  a stream. It resolves XStream's forms verified against real rig saves:
  simple-name element tags, outer+inner concatenation for aliased inner
  classes, and dotted FQNs with `_-` or a literal `$`. Vanilla's short `cl=`
  aliases are never attributed to a mod. `compare_builds` narrows
  `jar-audit`'s removed-class list to the classes a specific save needs. On a
  real Exigency save it reports `LOADS` (14 classes referenced, 0 missing).
- Add `bridgeforge-probe` (roadmap P3): a rig-only in-game evidence-tier-T2
  probe mod (`probe-mod/`), public API only, built with SPW's Tick Marker
  recipe (`javac --release 17` against `starfarer.api.jar`). It does nothing
  unless a `bf_probe_rig` common-file marker is present. The campaign probe
  (an `EveryFrameScript` added from both `onGameLoad` and
  `onNewGameAfterTimePass`, first run after ~1 in-game day via
  `CampaignClockAPI.getElapsedDaysSince`, then every `campaign_interval_days`)
  checks ring-band/orbit finiteness, faction known-list emptiness, submarket
  stock after `updateCargoPrePlayerInteraction()`, per-faction fleet
  presence, tracked custom-entity positions, and planet spec resolution
  (`PlanetSpecAPI` — `StarGenDataSpec`/`PlanetGenDataSpec` are not public in
  this build). The combat probe is a mission (`bfprobe_combat`, a loose
  `MissionDefinition.java` compiled by the game like a vanilla mission) that
  deploys the target mod's hulls alternating on both sides up to a cap, logs
  deployment and a captain-personality WARN (the SK-13 class), lets AI fight
  for a configured duration, then calls `CombatEngineAPI.endCombat`. Every
  result is both a `BF-PROBE|<version>|<check>|<status>|<subject>|<detail>`
  log line and a JSON line appended to a `bf_probe_report` common-file; every
  check is wrapped in try/catch(Throwable) so one broken check never stops
  the rest. `bridgeforge/probe_mod_build.py` compiles and packs the jar
  deterministically (fixed-timestamp `zipfile`, no `jar` tool); a jar-audit
  reuse in `tests/test_probe_mod_build.py` proves it references no
  `java.lang.reflect`/`java.io.File`/`java.nio.file` symbol. `bridgeforge
  probe-config <mod_dir> --runtime <rig_dir> [--install]` builds the config
  from the mod's hull/variant inventory and writes it plus the rig marker
  into `<rig_dir>/saves/common/`, refusing unless `starsector-core` is a
  junction/symlink. `log-triage` now parses `BF-PROBE` lines into a `probe`
  section (counts by status/check, plus the FAIL/WARN list). The save-round-trip
  spike found no public API or Console Commands trigger for a save/load;
  that stays `MANUAL`/T3 (see `probe-mod/README.md`).

- Variant checks now honour a weapon's `.wpn` `mountTypeOverride` (e.g. an
  ENERGY weapon with `HYBRID` fits BALLISTIC slots), and count fighter bays
  added by hull mods (`converted_hangar` +1, whether built in or installed by
  the variant). Found by triaging Legacy of Arkgneisis from its dossier: 16
  false slot mismatches (`loa_flashlight`) and 4 false wings-exceed-bays
  (`loamtp_thatcher`) disappeared, leaving the one real bug (a Vulcan in an
  ENERGY slot on `loa_buffalo_ars_basic`).
- Add `bridgeforge dossier <mod_dir>` (roadmap P2): a deterministic,
  size-capped triage packet for a reviewing agent. It writes a small index
  (`dossier.json`/`.md`) with identity and build tag, an inventory (hulls,
  weapons, wings, systems, factions with known-list sizes, custom planet/star
  types, created star systems, jar classes), all open questions, optional
  `jar-audit`/`copy-drift`/`log-triage` summaries, and a manifest. Findings go
  into numbered parts (`dossier.part-NN.json`/`.md`), each under `--max-kb`.
  Parts are ordered MANUAL > REVIEW > UNKNOWN > SAFE, grouped by file, and
  carry context snippets and whether a `bridgeforge fix` fixer exists. The
  size cap **splits, never truncates**; only a single oversized finding's
  snippet is trimmed, and that is recorded. `--baseline` limits the dossier to
  new findings. It refuses to write its default output into `In operation`
  or `Done`.
- Fix `data-class-reference-missing` for `rules.csv` commands: vanilla keeps
  rule commands in `rulecmd` sub-packages too (e.g.
  `rulecmd.salvage.AddBarEvent`), so a bare command now resolves by simple
  name against any vanilla class under a `.rulecmd.` package. Real false
  positive: Legacy of Arkgneisis's `AddBarEvent`.
- Add `bridgeforge/boot_test.py` (`run_boot_test`), a headless boot test for
  an isolated Starsector rig. It refuses when `starsector-core` isn't a
  junction or symlink (save isolation; NTFS junctions are detected via the
  reparse-point attribute), or when a java.exe under the rig is already
  running (matched by executable path, not name). It backs up and restores
  `enabled_mods.json`, launches through a fully quoted `cmd /c` bat path, and
  polls for the main-menu marker. The result is PASS, FAIL, or
  `SUSPECT_FATAL_DIALOG` (process alive, no menu, since Fatal errors show only
  as a modal dialog). It then terminates the process tree and runs
  `log-triage`.
- Add variant validity checks with skin-aware hull resolution, skipping
  fighter-size hulls: `variant-wings-exceed-bays`, `variant-op-over-budget`
  (tolerance `max(3, 5% of OP)`), and `variant-weapon-slot-mismatch`.
- Add `description-missing` (falls back to vanilla's `descriptions.csv`, read
  leniently because it isn't valid UTF-8) and `asset-reference-missing`.
- Fix `data-class-reference-missing` so it resolves vanilla loose scripts
  under all of `data/**` (not only `data/scripts`), using each file's own
  `package` line when present.
- Add `bridgeforge fix <mod_dir> --finding ID [--apply] [--json]`
  (`bridgeforge/fixers.py`): SAFE, mechanical, surgical-text fixers for eight
  finding ids (`wing-role-assault-removed`, `mod-info-game-version-inexact`,
  `csv-row-extra-columns`, `csv-missing-design-type-column`,
  `procgen-planet-row-missing`/`procgen-star-row-missing`,
  `faction-known-lists-missing`, `mod-info-triage-banner`); any other id is
  refused with the supported list. Dry-run (default) prints a unified diff
  per file and never writes; `--apply` writes the change, keeps a
  `<file>.pre-bf-fix-<id>.bak` backup per pre-existing file (numbered instead
  of clobbering an existing backup), then re-runs `scan_mod` and reports
  whether the finding is gone. `csv-row-extra-columns` only drops trailing
  *empty* extra fields and refuses outright if any extra field is non-empty;
  validated read-only against a copy of FlowerGod's real
  `descriptions.csv.pre-row64-trim.bak` (10-field row), which correctly
  refuses. `faction-known-lists-missing` derives `knownShips`/`knownWeapons`/
  `knownFighters` from the faction's own `shipRoles` variant keys and refuses
  if any resolved hull/weapon/wing id doesn't validate against mod+vanilla
  data (never adds `knownHullMods`).
- Add `bridgeforge prepare-test <working_dir> <rig_mod_dir> [--sync] [--bump]
  [--label BF] [--boot RUNTIME_DIR --mods ID...] [--json]`
  (`bridgeforge/prepare_test.py`): detects a same-folder junction/symlink rig
  ("same folder (junction), nothing to sync"); `--bump` runs
  `apply_build_tag` on the working copy first; runs `copy_drift.compare_copies`
  and, with `--sync`, copies only drifted/missing working -> rig files (never
  the reverse, never deletes rig extras -- it lists them), then requires 0
  drift afterward. `--boot` lazily calls `boot_test.run_boot_test` and
  reports "boot-test module unavailable" instead of crashing if that module
  isn't present. Validated read-only against real rigs: `Flu-X-0.98a` vs its
  `Flu-X-rc8-runtime` junction correctly reports "same folder"; `Done/
  SEEKER-0.98a-workspace` vs the `Flu-X-rc8-runtime` SEEKER rig copy compares
  cleanly in no-sync mode.
- Wire `bridgeforge boot-test <runtime_dir> --mods ID [ID...] [--timeout 240]
  [--log-name NAME] [--keep-mods] [--json]` in `cli.py`, calling
  `boot_test.run_boot_test` via a lazy import and printing its status,
  reason, log path, and triage counts.

- Add `data-class-reference-missing` (MANUAL, critical): every fully qualified
  class named in mod data (hull_mods.csv/ship_systems.csv/submarkets.csv
  `script`, industries.csv `plugin`, weapon_data.csv script-like columns,
  `.system` `statsScript`/`aiScript`, `.wpn`/`.proj` `onHitEffect`/
  `everyFrameEffect`/`onFireEffect`, `rules.csv` bare rule commands,
  `settings.json` `plugins`, and `mod_info.json` `modPlugin`) must resolve to
  a class in the mod's own loaded jars/sources or (when `--vanilla-core` is
  supplied) vanilla; a `com.fs.*` reference with no vanilla core supplied is
  reported UNKNOWN ("vanilla class, unverified") rather than guessed missing,
  and a known third-party library package (org.lazywizard, org.magiclib,
  data.scripts.util.Magic*, org.dark, lunalib, exerelin) is reported UNKNOWN
  ("external dependency, unverified") instead of MANUAL. A row/line commented
  out with `#` is skipped. Real validation: Exigency's disabled
  `combat_radar_plugins.csv` row correctly does not fire. Vanilla loose
  scripts anywhere under `data/**` (e.g. `data/shipsystems/scripts/`) resolve
  when `--vanilla-core` is supplied; without it such references are UNKNOWN,
  not MANUAL.
- Add `hardcoded-hyperspace-coordinates` (REVIEW, low): a hyperspace-touching
  class (`getHyperspace()`/`getLocationInHyperspace`/a waypoint-like list)
  hard-coding 3 or more literal `Vector2f`/`getLocation().set(...)` coordinate
  pairs. Real validation: fires once on Exigency's
  `ExipiratedAvestaMovement` (29 waypoints) and once on Legacy of
  Arkgneisis's `loa_anargaia`; does not fire on commented-out coordinates.
- Add `hardcoded-terrain-grid-size` (REVIEW, low): a literal grid size/mask
  used to index or divide near a `getTiles()` call; skipped entirely for a
  class that already calls `getTileCenter`. Real validation: correctly does
  NOT fire on Exigency's `Tasserus.removePNGFromNebula`, which was already
  fixed to use `getTileCenter` instead of the old 260-tile mask.
- Add `bridgeforge scan --baseline FILE` / `--write-baseline FILE`: writes or
  compares accepted finding keys (id + file + first evidence item) so a
  re-scan reports only new findings plus a count of previously accepted
  findings that are now resolved. Default scan output is unchanged when
  neither flag is given.
- Add scanner checks for a second wave of live-RC8 crash classes: a zero or
  unguarded-computed orbit period passed to `addRingBand`/`addAsteroidBelt`/
  `setCircularOrbit*` (`orbit-period-zero`, `orbit-period-computed-unguarded`
  — the next save throws a non-finite-number crash such as
  `RingBand.writeReplace`; real case: Legacy of Arkgneisis's
  `SpawnChampionRing`), a `SHIP_WITH_MODULES` hull or a `spawnShipOrWing`/
  `spawnFleetMember` call spawning a ship variant (not a wing) whose captain
  can have no personality and NPEs in `Ship.getPersonality()`
  (`module-captain-personality-risk`, `spawned-ship-captain-personality-risk`
  — real case: SEEKER's `ART_*_hulk*` debris spawns), and a `mod_info.json`
  name/description/author still carrying a pre-release triage banner
  (`mod-info-triage-banner`).
- Add `bridgeforge build-tag <mod_dir> [--label BF] [--set N] [--dry-run]
  [--json]` to iterate a visible build number in a revived mod's
  `mod_info.json` `name` (` [BF rN]`) and, when `version` is a string,
  `version` (`+bf.N`). Edits only those two string values in place by regex
  (honoring `"`/`'` quoting) and never re-serializes the file, so comments,
  trailing commas, key order, BOM, and line endings survive untouched; `id`
  and `.version` (version-checker) files are never touched. The result is
  re-parsed with the lenient JSON reader before being trusted.
- Source checks for orbit periods and spawned-ship captains now blank out Java
  `//` and `/* */` comments first (string literals preserved, line numbers
  kept), so commented-out code is no longer flagged. Real false positive: a
  disabled `setCircularOrbit` block in Legacy of Arkgneisis's procgen
  generator. `mod-info-triage-banner` now matches only banner forms (all-caps
  `BROKEN`, a parenthesised `(broken`, `BROEKN`, etc.), so an ordinary name
  such as "Broken Star" isn't flagged.
- Fix `jar-audit --original`/rebuilt-jar detection to sniff zip content (a
  `.class`-bearing zip is a jar; otherwise, a zip containing a `.jar` member
  is used) instead of trusting the file extension, so a real revival backup
  named e.g. `al_arkleg.jar.pre-ring-guard.bak` is accepted.
- Add live-RC8-testing static checks to the scanner: missing procgen
  star/planet rows for campaign-placed `planets.json` types
  (`procgen-star-row-missing`/`procgen-planet-row-missing`), factions missing
  `knownShips`/`knownWeapons`/`knownFighters` (`faction-known-lists-missing`),
  the 0.8a carrier-rework gap (`shiproles-wing-id`,
  `shiproles-obsolete-fighter-role`, `ship-data-missing-fighter-bays-column`,
  `wing-data-missing-role-desc-column`, `wing-role-assault-removed`,
  `wing-op-cost-blank`, `carrier-without-bays-or-wings`), black hole star
  types missing `isBlackHole` (`black-hole-type-missing-flag`), an inexact
  `mod_info.json` `gameVersion` against an RC target
  (`mod-info-game-version-inexact`), and mod files shadowing vanilla data at
  the same path with different bytes (`vanilla-path-shadowing`).
- Add an optional `vanilla_core` scan input (`scan_mod(..., vanilla_core=...)`,
  CLI `bridgeforge scan --vanilla-core`) so the new checks can exempt vanilla
  procgen rows, vanilla faction merge-fragments, and diff against vanilla
  data; every new check degrades gracefully (documented in finding evidence)
  when no vanilla core is supplied.
- Legacy-JSON parsing now also accepts a comma after the root object's closing
  brace (Exigency's shipped faction files end with `},`; Starsector loads them).
  A faction file BridgeForge still cannot parse is reported as
  `faction-file-unparsed` (UNKNOWN) instead of being skipped silently, so an
  unchecked file can no longer read as a clean one.
- `vanilla-path-shadowing` is downgraded to REVIEW/low for mods declaring
  `"totalConversion": true`, where vanilla overrides are expected.
- Add bytecode checks from live RC8 testing, built on a real class-file
  constant-pool parser: `script-sandbox-forbidden-api` (java.lang.reflect,
  java.io.File-family or java.nio.file references, which RC8's script
  classloader rejects at runtime, sometimes mid-combat),
  `bundled-library-classes` (GraphicsLib/LazyLib/MagicLib/LunaLib/Nexerelin
  classes compiled into a mod jar), `vanilla-class-duplicated-in-jar` (a mod
  copy of a vanilla class or loose script, MANUAL when it lacks vanilla public
  methods; new `rulecmd` classes are exempt), and `obfuscated-internal-api-use`.
  Also add `csv-missing-design-type-column` and
  `undeclared-library-dependency`, and extend `vanilla-path-shadowing` to
  loose `.java` scripts.
- Bytecode checks read only the jars Starsector loads: `mod_info.json`'s
  `jars` list, or every jar outside `build/`, `out/`, `tmp/` and `target/`.
  Compile-classpath caches and unloaded legacy jars are skipped.
- Legacy-JSON parsing now accepts Starsector's full org.json dialect:
  single-quoted strings, unquoted keys, bareword values, `//` comments and
  Java number suffixes (`0.5f`). Each accepted tolerance is reported as a SAFE
  informational finding.
- Add workflow commands: `bridgeforge log-triage` (classify a Starsector log
  into FATAL / mod errors / known noise, with the top mod stack frame and
  milestones), `bridgeforge copy-drift` (hash-compare a working copy with its
  deployed test-rig copy), and `bridgeforge jar-audit` (compare a rebuilt jar
  with the original: bundled library packages, removed classes, sandbox-banned
  references). `log-triage` counts a campaign load only from RC8's real
  `CampaignGameManager - Loading <path>` line (absolute paths with spaces
  included). Save-menu descriptor reads and startup mission-variant preloads
  are not treated as progress.
- Add a review-gated bytecode inspection, diff, plan, and apply workflow
  bounded to pinned-ASM class/JAR symbolic remaps written to a separate
  output copy (`bytecode-inspect`, `bytecode-diff`, `bytecode-plan`,
  `bytecode-apply`); see `docs/BYTECODE_BOUNDARY.md`.
- Add read-only ZIP archive intake (`archive-preflight`, `archive-stage`)
  that reports traversal, symlink, duplicate-member, and mod-root ambiguity
  evidence before any extraction, and never writes beside the input archive.
- Add read-only, budget-bounded multi-mod corpus auditing (`corpus-audit`)
  and two-directory release comparison (`release-evaluate`).
- Add local, review-only library API inventory/match research tooling
  (`library-api-inventory`, `library-api-match`) and an opt-in local
  library registry (`--library-registry`) that auto-resolves a mod's
  declared dependency IDs to local JARs for compile validation.
- Add deterministic output-copy JAR packaging after a successful compile
  (`package-jar`), with an input/output SHA-256 manifest confirming the
  source JAR was preserved.
- Bytecode rewriting is therefore no longer an alpha-1 limitation: it is
  available as a narrow, review-gated remap of exact same-descriptor
  symbols only. Library API *transformation* and cross-mod dependency
  graphing remain unimplemented; see the roadmap.

## 0.1.0 — Alpha 1 — 2026-08-31

First public alpha of the read-only Bridgeforge compatibility workflow.

- Scan Starsector mod folders without modifying them and emit Markdown plus
  JSON compatibility artifacts.
- Use evidence-aware JSON, encoding, metadata, archive, bytecode, source, and
  dependency findings; `UNKNOWN` is not a breakage verdict.
- Provide explicit working-copy planning, approval-gated application,
  provenance, conflict, compile, validation, save-risk, and review artifacts.
- Include Windows and Ubuntu CI on Python 3.10–3.12 with Java 17.

### Alpha limitations

- Migration packs are scaffolds only; no library API transformation is shipped.
- Runtime launching, decompilation, bytecode rewriting, and cross-mod analysis
  are not part of this alpha release.
- Scanner output is evidence for review, not proof that a mod will load or
  behave correctly.
