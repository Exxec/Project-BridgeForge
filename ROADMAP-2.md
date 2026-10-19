<!-- page-nav:start -->
> Page 2 of 3 of the BridgeForge roadmap. Previous: [ROADMAP.md](ROADMAP.md). Next: [ROADMAP-3.md](ROADMAP-3.md). Newest entries: [ROADMAP-3.md](ROADMAP-3.md).
<!-- page-nav:end -->

## P15: Unattended revival with verified AI escalation (planned 2026-09-26) (continued)

1. **Measure the ceiling: `finding-stats`.** **Done 2026-09-26.** `bridgeforge/automation_tiers.json`
   places every scan finding id in one tier (none, auto, mechanical, input, decision, inspect, code);
   a test fails when a new check has no tier, and an `auto` id must name a real fixer.
   `finding-stats [ROOT...] [--scan] [--write DIR]` groups workspaces by their hardest tier, reports
   how many could run unattended now and with every `mechanical` finding fixed, ranks finding ids by
   how many mods each is the only blocker for (`unlocks`), and lists ids AI agents have fixed and
   BridgeForge verified 3+ times across 2+ mods (fixer candidates). The real queue run is local
   (`docs/LOCAL_HANDOFF.md`). Tests: `tests/test_finding_stats.py`.
2. **Orchestrator and escalation packets: `revive`.** **Done 2026-09-26.** Scan (with the compile check
   given `--vanilla-core`), apply permitted fixers, rescan, until a round changes nothing; dry run
   unless `--apply`. A fixer is applied unattended only when all its findings are SAFE; anything
   else needs `--approve ID` or a standing approval in the queue's `AUTOMATION_POLICY.json` (decide
   once, apply to every mod); MANUAL/UNKNOWN are never fixed without one. The rest becomes packets in
   `<ws>/reports/escalations/`: agent packets (code/mechanical/inspect; one per finding and file,
   with evidence, the allowed files, a numbered excerpt around the lines the evidence names, a hint
   for the finding family, rules, and the verify command) and owner packets (decisions, inputs, and
   fixers awaiting approval with their dry-run diff). Tests: `tests/test_revive.py` (`ReviveTests`).
3. **Agent runner with re-verification: `escalation run`.** **Done 2026-09-26.** Runs any agent command
   in a throwaway copy with the packet on stdin; rejects edits outside the packet's files; requires
   the agent's note; rescans (and compile-checks) the copy and passes only if the finding is gone and
   no new actionable finding appeared; retries a failure with BridgeForge's reasons appended; copies a
   verified result back only with `--apply` (backups kept), labelled REVIEW. `escalation
   list|show|verify` cover the rest. Tests: `tests/test_revive.py` (`EscalationRunTests`, with a
   scripted stand-in agent).
4. **Ledger and fixer promotion.** **Started 2026-09-26.** Every fixer application and agent attempt
   is appended to `<ws>/reports/escalations/ledger.jsonl`; `finding-stats` turns it into the fixer
   candidate list. Three `mechanical` ids became fixers now (safe, deterministic, common in pre-0.8a
   mods): `csv-fullwidth-number` (SAFE, so unattended), `ship-data-missing-fighter-bays-column` (blank
   column, reusing the carrier-bays edit) and `missing-custom-ui-button-pressed-callback` (no-op
   callback in loose scripts). Tests: `tests/test_fixers.py`. **Next:** write fixers for the top
   `unlocks` ids from the first local `finding-stats` run, and for whatever the ledger promotes.
5. **One command per job after the local/GitHub merge (owner decision 2026-09-27).** The 2026-09-27
   merge kept both sides' versions of seven commands. **Done 2026-09-27.** Kept `strip-plan`,
   `diff-data`, `verify-shadow`, `dependency-graph`, `rebuild-from-reference`, `corpus-index` and
   `provider-index build`; removed `strip-plan-local`, `diff-data-local`, `verify-shadow-local`,
   `dependency-graph-local`, `rebuild-from-reference-local`, `archive-index`/`archive-search` and
   `provider-index-update` with their modules (`diff_data`, `rebuild_from_reference`,
   `archive_index`, `dependency_graph`, `scanner.verify_shadow`). Kept both `vendor-plan` (what a
   closure needs) and `vendor-copy` (copies a hullmod), per the owner. A provider cache the local
   `provider-index-update` wrote (a folder, one JSON per mod) still loads through
   `load_provider_index` and `--provider-index`. Tests: `tests/test_substitutes.py`
   (`LegacyProviderCacheTests`), `tests/test_vendor_copy.py`, `tests/test_strip_plan.py`,
   `tests/test_verify_shadow.py`.
6. **Automation follows the merged fixers and baselines.** **Done 2026-09-27.** Three fixers from the
   local history were tiered so `revive` never ran them: `rules-firebest-populate-options`,
   `personality-id-unknown` and `shiproles-wing-id` are now `auto` (their MANUAL/REVIEW findings
   still need approval), and a test fails when any fixer's finding is not `auto` or `input`. `revive`,
   `escalation verify` and `finding-stats` now honour the mod's accepted-findings baseline
   (`working/reports/baseline*.json`) as `corpus-recheck` does since item 46, sharing
   `baseline.mod_baseline_path`. Tests: `tests/test_finding_stats.py`, `tests/test_revive.py`.
7. **`vendor-copy --plan`: copy a whole `vendor-plan` closure.** **Done 2026-09-27.** `vendor-copy` copied
   one hull mod; `vendor-plan` traces any piece (weapon, wing, hull, variant, ship system) but copied
   nothing. `vendor-copy --plan FILE --to DIR [--apply] [--allow-partial]` (`vendor_plan.copy_plan`)
   copies exactly what a plan lists, files byte for byte and CSV rows appended under the target's own
   header, and re-checks it first: the provider must still hold every file and row (else STALE), the
   licence gate is re-read (the one `vendor-copy` and `release` use), a differing target file or row
   is a CONFLICT and nothing is written, identical ones are skipped, and a plan with MISSING or SUSPECT
   entries or compiled-only classes is INCOMPLETE unless `--allow-partial`. Every copied file's
   SHA-256 is returned for PROVENANCE.md. Tests: `tests/test_vendor_plan.py` (`VendorCopyPlanTests`).
8. **`revive --draft-report`.** **Done 2026-09-27.** When a run ends UNATTENDED_DONE, `revive` calls
   `revival-report-draft`, so the mod reaches the live test with REVIVAL_REPORT.md/REVIVAL_PLAN.md
   drafted (written only with `--apply`, never over an existing report; any other status records
   NOT_DRAFTED). The drafter now honours the mod's baseline too: accepted findings no longer block it
   and are listed in the report's own "Accepted by baseline" section. Tests: `tests/test_revive.py`,
   `tests/test_revival_report_draft.py` (`DraftHonoursBaselineTests`).
9. **Missing-content packets carry the options.** **Done 2026-09-27.** `content-reference-unresolved`
   and `content-reference-removed-in-vanilla` owner packets now hold, computed once per run and only
   when such a packet exists: `dependency-substitutes`' strategy, reason, provider set and licence
   notes; a `vendor-plan` summary for up to two providers that cover the ids (files, rows,
   compiled-only classes, SUSPECT/MISSING) with the commands to reproduce and copy it; and
   `strip-plan`'s edit count per id with vanilla slot substitutes (needs `--vanilla-core`). Providers
   default to the workspace's queue folder and its `_rig/mods` (`--providers`, `--provider-index`).
   A part that cannot be computed is a note, never a failed run. Tests: `tests/test_revive.py`.
10. **Hygiene after the merge (owner request 2026-09-27).** **Done 2026-09-27.**
    - Roadmap: P14 items 2, 3, 4, 8 and 9 each had two copies (one per history) or a block stranded under
      the wrong item; each is now one entry with both records labelled. This session's P14 items
      29-36 collided with the local items of the same numbers and are now 47-54, each noting its old
      number; code, test and changelog references to them were updated (the local 29-36 kept theirs).
    - `docs/LOCAL_HANDOFF.md` rewritten: closed entries removed (item 27's audit, E8), and the runs the
      local side made with since-removed command versions listed again for the kept ones (R1-R4).
    - Speed: five fixers rescanned the whole mod to find their own findings, so one `revive` round on
      a large mod could cost six full scans. `fixers._findings_of` uses the caller's findings when given
      (`options["scan_findings"]`, which `revive` passes) and scans only otherwise; `fix` is unchanged.
      Tests: `tests/test_fixers.py` (`SuppliedFindingsTests`, which fails if a rescan happens).
11. **Local-only content may be vendored into a local-only target (owner decision 2026-09-27).**
    **Done 2026-09-27.** `vendor-copy` refused every local-only provider, which blocked the case
    RevenantLib exists for (Rebal's `shields_formshield`, P14 item 4). `release.vendoring_licence`: a
    releasable provider always may be vendored; a local-only one only into a target that is itself
    local-only in `release_policy.json` (RevenantLib is), and the result says so
    (`must_stay_local_only`, a `LICENCE:` line); into a releasable target it is still refused. Used by
    both `vendor-copy` and `vendor-copy --plan`. Tests: `tests/test_vendor_copy.py`,
    `tests/test_vendor_plan.py`.
12. **Long runs print progress and resume from a checkpoint (owner rule 2026-09-27).** The first local
    `finding-stats --scan` ran 43m50s over 305 workspaces with no output until the end, and
    `dependency-graph --write` and `corpus-index build C:\Users\exxec\Downloads` ran over 1.5 hours
    each without a line; an interrupted run lost everything (`corpus-index build` held the whole
    archive in one SQLite transaction). **Done 2026-09-27.** `bridgeforge/progress.py`: `Checkpoint`
    (append-only `*.partial.jsonl`, header names the inputs; same header resumes, any other restarts, a
    torn last line is ignored) and `report` (`[12/305] Mod: detail (38.2s)` on stderr). Applied to
    `finding-stats` (`--write DIR` with `--scan`), `dependency-graph --write`, `corpus-recheck` (both
    checkpoint in `In operation/`, known root files for `board`), each with `--quiet` and `--restart`;
    `corpus-index build` now commits per source, so a rerun skips what an interrupted one indexed, and
    prints each file it reads. `progress.LONG_RUNNING_COMMANDS` lists them and
    `tests/test_progress.py` fails if one stops offering `--quiet`; rule recorded in `CLAUDE.md`.
    Tests: `tests/test_progress.py`, `tests/test_finding_stats.py`, `tests/test_substitutes.py`,
    `tests/test_corpus_recheck.py`, `tests/test_corpus_index.py` (each with an interrupted-run case).
13. **First local pass over `docs/LOCAL_HANDOFF.md` after the merge (2026-09-27).**
    - **P1 done:** `In operation/FINDING_STATS.md`, 305 workspaces. Unattended now 43 (14%), 50 with
      mechanical fixers; hardest tier `code` 168, `decision` 67, `auto` 41. Top unlocks:
      `settings-json-override-breadth` (decision, 14), `shippable-work-file` (mechanical, 7),
      `loose-script-janino-risk` (code, 5), `vanilla-path-shadowing` (decision, 5). No unclassified ids.
    - **G2:** catalogues written to `In operation/_reference/` for 0.8.1a, 0.9a and 0.95.1a to RC8.
      The handoff's expectations were partly wrong: 0.9a's `SectorAPI` already lacks `addMessage` and
      `createFleet(String, String)` (removed between 0.8.1a and 0.9, checked in each install's
      `starfarer.api.zip`); against 0.8.1a, `compile-check` on Batavia's `original/` prints `API CHANGE`
      lines with `CampaignUIAPI.addMessage` as a candidate and none for `createFleet`, as expected.
      `weapon:thruster_fighter_sm` and `hullmod:shields_formshield` occur in no vanilla data from 0.6.2a
      to 0.95.1a (grep of every install's `data/`): they are mod ids, not removed vanilla content.
      Noise worth fixing: `compile-check` lists every same-named overload for one call site (four
      `addMessage` lines per call) instead of matching the argument count.
    - **R2:** the BDS command cannot run as written (`--class hullmod` is not a class; the 260-line
      figure came from `.java`, which neither version merges). Rebal `.wpn` from `original/` against
      0.9a: MERGED 81, UNCHANGED_COPY 1, 0 conflicts, against the removed local version's 76 rebuilt and
      5 conflicts over the same 82 files. Not a bug: `hammer.wpn` `fireSoundTwo` and `hil.wpn` `width`
      equal the 0.9a value in Rebal, so only RC8 changed them and the three-way merge takes RC8's.
    - **R4:** DME's `strip-plan` lists exactly its one uncovered id (`hull:istl_mystere`).
      `vendor-copy --plan` for Rebal's `shields_formshield` into RevenantLib stops at a CONFLICT:
      RevenantLib's `hull_mods.csv` already carries a different `shields_formshield` row (9 SUSPECT
      shield scripts held back as designed).
    - **G1:** probe jar rebuilt against RC8 (17 classes, release copy 0.2.2); `tests/test_probe_mod_build.py`
      ran on this machine. javap (RC8 `starfarer.api.jar`, 2026-09-27) confirms `SettingsAPI.getHullSpec`,
      `getWeaponSpec`, `getHullModSpec` and `FleetMemberAPI.getHullSpec()`/`getHullId()` for the
      proposed direct lookups and substituted-hull check. Live `content-ids` run still pending.
    - **G3:** `revenantlib-check` PASS for the three `bf.*` methods; `rig-doctor` has nothing to check
      because RevenantLib is not installed in the rig.
    - **G4 done:** `tools/build_jar.py` rebuilt RevenantLib byte-identically (0 added/removed/changed,
      11 identical), `tools/check.py` three PASS; `scratch/MOVES.log` copied into `reports/MOVES.md`
      on RevenantLib branch `local-handoff-moves-log`.
    - Local tooling: `.githooks/pre-commit` runs `ruff check .` and the hooks are installed
      (`core.hooksPath` had been unset); `AGENTS.md` synced with `CLAUDE.md`.
    - **R1 done:** `In operation/DEPENDENCY_GRAPH.md`, 305 queued mods. First: Unofficial New Game Plus
      (unblocks 6), Scy Nation (4), YunruCore, Outer Rim Alliance (3 each). All 20 ranked providers show
      `licence UNRECORDED`: each needs `release-policy set` before it is revived.
14. **`shippable-work-file` fixer, and the first UNATTENDED_DONE revive (2026-09-27).** P1 ranked it the
    top `mechanical` id (the only blocker for 7 mods). **Done 2026-09-27.** `_fix_shippable_work_file`
    moves each listed file to `<workspace>/scratch/work-files/<same path>` (`<root>.work-files/` for a
    bare mod folder) and leaves any file whose name appears in the mod's data, loose scripts,
    `mod_info.json` or jar members, per the check's own caveat that a mod could read one; it refuses
    to overwrite an earlier move. `FileChange.removed` lets a plan delete a file (a move's new copy is
    its backup, a bare removal keeps the `.bak`), and diffs show removals and binary files as one line.
    Tier `mechanical` -> `auto`. Dry run on the 7 mods moved only source archives, `.url` shortcuts,
    `~`/`.old` backups and a Krita file. Tests: `tests/test_fixers.py` (`ShippableWorkFileFixerTests`).
    - **P2, first real `revive`:** ClearCommands, with `--approve` for its three REVIEW `auto` fixers
      (no standing `AUTOMATION_POLICY.json` yet: the owner's call). The run found two bugs, both fixed:
      `revive` crashed labelling a change outside `working/` (now `../scratch/...`, removals marked);
      and **`undeclared-library-dependency` declared LazyLib for a mod that only uses Console
      Commands**, because `BUNDLED_LIBRARY_PACKAGE_PREFIXES` mapped all of `org/lazywizard/` to LazyLib.
      Every class in LazyLib 3.0.0's two jars is under `org/lazywizard/lazylib/`, and Console Commands
      4.0.9 (`lw_console`) is all `org/lazywizard/console/` (208 classes), so LazyLib now has the narrow
      prefix and Console Commands its own entry. A bytecode-only Console Commands user whose classes
      are all registered in `data/console/commands.csv` gets the existing `console-command-optional`
      (SAFE) instead of a dependency. `declared-library-unreferenced` now also honours jar bytecode use.
      ClearCommands' `mod_info.json` was restored from the fixer's own backup and revive then reached
      **UNATTENDED_DONE** (report drafted; the probe run is the remaining manual step). Of the 85
      workspaces declaring `lw_lazylib`, 3 now show it unused (MAGNETAR, Persean-Chronicles,
      SCY-Nation-Utility), none from a fixer. Tests: `tests/test_rc8_bytecode_checks.py`
      (`test_declared_library_used_only_by_jar_bytecode_is_not_unreferenced`; the finding leaves
      `untested_checks_baseline.json`).
15. **`data-file-not-utf8` fixer for the one encoding the bytes prove (2026-09-27).** P1: 34 mods,
    `mechanical`. A survey of the queue's 44 non-UTF-8 data files showed the check's "decodes as"
    guess is not evidence: DME's descriptions use Mac Roman (0xD5 for ’), Stinger-Shipyards
    Shift-JIS (0x81 0x66), Union-Rail-Systems and Faction-Relationships-Uniquified are UTF-8 with stray
    bytes, and GB18030 decodes almost anything. **Done 2026-09-27.** `_fix_data_file_not_utf8`
    re-encodes a file only when every invalid byte is isolated CP-1252 typography (0x85, 0x91-0x94,
    0x96, 0x97, 0xA0: bytes Mac Roman reads as letters and GBK/Shift-JIS cannot use alone), keeping
    valid UTF-8 already present byte for byte; any other file is refused with the bytes it holds, for a
    person to name its encoding. Tier `mechanical` -> `auto` (still REVIEW, so revive asks for
    approval). Dry run over the queue: 30 files in 27 mods converted; 14 refused (Another-Random-SWP
    0xB0, DME/DME-dev, Epta-Consortium, Faction-Relationships-Uniquified, TDB-Maelstrom, MAGNETAR 0x99,
    Stinger-Shipyards, Thule-Legacy, part of ICE). Tests: `tests/test_fixers.py`
    (`DataFileNotUtf8FixerTests`).
16. **`compile-check --api-diff` lists only overloads the failing call could mean (2026-09-27).** On
    Batavia's `original/` against the 0.8.1a catalogue, every `addMessage` call printed all four
    removed `SectorAPI.addMessage` overloads. **Done 2026-09-27.** `api_diff._same_arity` reads the
    argument list javac prints (`symbol: method addMessage(String)`) and keeps the removed overloads
    with that parameter count (generics nest), falling back to every lead when none match. Batavia now
    prints one line per call. Tests: `tests/test_api_diff.py`
    (`test_only_overloads_with_the_calls_argument_count_are_listed`).
17. **Standing fixer approvals, named encodings, and the formshield conflict explained (2026-09-27).**
    - Owner asked for standing approvals: `In operation/AUTOMATION_POLICY.json` (local) approves
      `mod-info-game-version-inexact`, `shippable-work-file`, `data-file-not-utf8` and
      `csv-fullwidth-number`; revive loads it (checked on Aivon-Republic). Other `auto` fixers
      (`undeclared-library-dependency`, `csv-row-extra-columns`, `removed-api-call`, ...) still need
      `--approve` per run until each is checked on real data.
    - **Done 2026-09-27.** `fix --finding data-file-not-utf8 --encoding FILE=ENC` re-encodes a refused
      file from an encoding a person named (cp1252, mac_roman, shift_jis, gbk, gb18030, latin-1); only the
      invalid bytes are decoded (a two-byte lead takes its trail byte), and a byte that does not decode
      is refused. Applied to 13 of item 15's 14 refused files after reading each byte in context:
      CP-1252 (Another-Random-SWP `360°`, DME/DME-dev `.ship` `Mysteré`, Epta-Consortium `Pérola`, ICE
      `Steinmüller`/`Caitlín`, TDB-Maelstrom `Dà húndàn`, MAGNETAR `™`, Thule-Legacy `Bifröst`/`Brünhilde`),
      Mac Roman (DME/DME-dev descriptions: `it’s`, `Mystère`, `Émile`), Shift-JIS (Stinger-Shipyards
      `ship’s`). Left for the owner: Faction-Relationships-Uniquified's lone 0x9D, the tail of a broken
      UTF-8 `”`. Tests: `tests/test_fixers.py` (`DataFileNamedEncodingTests`).
    - R4's vendor conflict is not a decision: RevenantLib vendored `shields_formshield` from Rebal on
      purpose (`reports/PROVENANCE.md`), in RC8's column layout with the script repackaged to
      `xenoargh.shared.hullmods.FormShield`; name, costs, text and sprite are identical.
18. **First live `content-ids` runs, and Fatal dialogs now reach triage (2026-09-27, P14 item 49).**
    - **CC-1-20260927** (ClearCommands + probe 0.2.2): FATAL=0, MOD-ERROR=0, save written; the probe's
      campaign checks ran and logged `content-ids|OK|all-content|checked=0 failed=0`. ClearCommands has
      no content, so this proves the probe loads but not the check: a content mod's run is still needed.
    - **PRB-CID-FAIL-20260927** (SEEKER copy, `ART_dimention_manipulator.variant` slot `B_weapon1` =
      `ART_dimention_leftGun_BFTYPO`): RC8 itself stopped the game with the dialog "Fatal: Weapon spec
      [ART_dimention_leftGun_BFTYPO] not found!" while generating the new sector. The probe never armed
      (no `BF-PROBE` line; CC-1 logs `campaign-armed` at the same stage). So a variant naming a missing
      weapon is a hard new-game fatal on RC8 that the probe can never report; `content-ids` is for ids
      the game tolerates. The expected-FAIL test must use a softer breakage (to choose from what RC8
      skips with a WARN, e.g. an unknown hull mod in a variant; verify in a run before relying on it).
    - **Triage said FATAL=0 for that run**, because a Fatal dialog never reaches the redirected log;
      only the window watcher's screenshot showed it. **Done 2026-09-27.** `bf-test.ps1`'s watcher reads
      each game dialog's text (child controls via `EnumChildWindows`; helper type renamed `BfWin2` so an
      open session does not reuse the old one) into `<TESTID>.windows.txt` as `dialog: '<title>' text:
      '<text>'`, and `log-triage` reads that file beside `<TESTID>.stdout.log`, counting a dialog that
      matches a FATAL pattern as FATAL with its source line. The watcher compiles (`bf-test.ps1
      selftest`); reading a real dialog is confirmed on the next rig run. Tests:
      `tests/test_log_triage.py` (`DialogFatalTests`).
    - **Probe 0.2.3 (2026-09-27):** after building each ship variant, `content-ids` now looks up every hull
      mod, fitted weapon, wing and module (to depth 3) through `SettingsAPI.getHullModSpec`/`getWeaponSpec`/
      `getFighterWingSpec` (ShipVariantAPI methods javap-confirmed 2026-09-27), naming the first id with no
      spec. Building alone may carry or drop an unknown id quietly.
    - **CID-OK-20260927** (SEEKER + probe 0.2.3): `content-ids|OK|all-content|checked=40 failed=0
      ship-variants built=15`, FATAL=0, MOD-ERROR=0, 2 saves. **The check works on real content.**
    - **CID-FAIL2-20260927** (SEEKER copy with `"hullMods": ["bf_nonexistent_hullmod"]` in
      `ART_dimention_manipulator.variant`; the copy's id and path are in the log, so it loaded): the probe
      reported OK, and the game log never mentions the id. RC8 drops an unknown hull mod from a variant at
      load, silently, so the built variant no longer lists it and no runtime check can see it. Together with
      PRB-CID-FAIL: a missing weapon in a variant is a New Game fatal, a missing hull mod is silent loss of
      its effect. The static scanner catches both (`content-reference-unresolved` flagged
      `hullmod:bf_nonexistent_hullmod`); its explanation now states both consequences (test:
      `tests/test_batch_lessons.py` `UnresolvedContentTests`). The probe's `content-ids` therefore
      confirms clean content (and catches variants that do not exist or fail to build) but is not a detector
      for these two cases. No dialog appeared in either run, so the dialog-text capture is still unexercised.
    - **Probe 0.2.4 (2026-09-27): substituted-hull check.** `probe-config` writes `content_ship_hulls`
      ({variant id: the hullId its `.variant` names}) for the variants built as SHIPs, and `content-ids`
      FAILs a variant whose built member's hull (`FleetMemberAPI.getHullId()`, or the spec's
      `getBaseHullId()` for D-hulls/skins) differs: the PRB-FIGHTER-01 Nebula substitution. Config test:
      `tests/test_probe_config.py`. The config already keeps fighter/module variants out of the SHIP list,
      so this is a safety net; a SEEKER run on 0.2.4 checks it raises no false failure. The broken-SEEKER
      rig fixture and its preset were removed.
      **CID-HULL-20260927** (SEEKER, probe 0.2.4): `content-ids|OK|all-content|checked=40 failed=0 ship-variants
      built=15`, FATAL=0, MOD-ERROR=0, 1 save: the hull check raises no false failure.
19. **`settings-json-override-breadth` counted additions as overrides (2026-09-27).** P1 ranked it the finding
    that alone blocks the most mods (14). It compared whole top-level keys, so a mod that only adds an entry
    inside `plugins`, `graphics` or `designTypeColors` counted as overriding vanilla's whole block. settings.json
    merges objects key by key: SEEKER, Exigency and Flu-X all add entries this way and played normally in the
    2026-09-24 live runs. **Done 2026-09-27.** `_settings_value_changes` compares nested objects value by
    value and ignores pure additions; lists and scalars still count when they differ (list merging is not
    evidenced). 10 of the 14 clear (Anex-Weapons, Aryas-Nightingale-Ships, Fleet-Action-History,
    Hexagonal-Shieldidgeridoos, Kazeron-Navarchy, KIND-STRANGER-Automatic-Orders, RevenantLib,
    Ship-Direction-Marker, Variants-Lib, Xenoargh-FX-Core). Tests: `tests/test_replace_array_and_identical_copies.py`
    (`test_entries_only_added_inside_vanilla_objects_are_not_overrides`).
    - **Held rule (owner, 2026-09-27; applies once testing clears it):** accept a small, deliberate set of real
      value changes (up to about 25 values), recorded per mod with the exact keys in a baseline so any later
      change shows; always review a large set (over 100 usually means a stale copy of an old settings.json).
      Covers RemnantPad and S-TechPad (24 UI colours each, a UI theme) and Combat-Misc-Utils (`forceNoVBO`).
      **Applied 2026-09-27** (testing cleared lists the same day): up to 25 changed values is SAFE
      `settings-json-override-accepted`; revive records the keys in `<workspace>/SETTINGS_BASELINE.json`, and a later
      change, or more than 25 values, is REVIEW `settings-json-override-breadth`. Test: `test_owner_limit_baseline_and_a_changed_baseline`.
    - **Test first:** Blue-Friend-Balls sets `ruleCommandPackages` to its own package only. If a list value
      replaces vanilla's list rather than adding to it, vanilla's five rule-command packages are lost and much
      campaign dialogue could break. One rig run with it enabled (new game, talk to a market, open a bar) settles
      how lists merge; until then it stays blocked.
      **Settled 2026-09-27: lists add, they do not replace.** Ten rig mods set `ruleCommandPackages` to their own
      package only (MagicLib, LunaLib, Console Commands, SOTF, Tahlan, SWP, IndEvo, Nightcross, Broken Star,
      Arkgneisis); GRP-SPARKLE-20260927 ran SOTF, LunaLib and MagicLib together and New Game, which needs vanilla's
      `rulecmd.newgame` package, worked. Blue-Friend-Balls is unblocked (its report, BFB-SET-01). Evidence covers
      `ruleCommandPackages`; other list keys still count as overrides until shown the same way.
20. **Enhancements found in the 2026-09-27 local session (proposed, not started).** Most useful first.
    1. **`archive` command for local-only mods.** Archiving ClearCommands and RevenantLib into `Done/` was
       done by hand: shipped files via `copy_drift._collect`, a zip, `original/`, `workspace/` reports and an
       `ARCHIVE_NOTE.md`. `release` cannot do it: its licence gate always blocks a local-only mod, and its
       behaviour gate wants D-series evidence even when nothing that runs changed. An `archive` command should
       build that layout, write the note from the release policy and revival report, and waive the behaviour
       gate only when the jar is byte-identical and the changes are metadata (with that proof in the note).
       **Done 2026-09-27.** `bridgeforge archive WORKSPACE [--done DIR]` (`bridgeforge/archive.py`): refuses without a
       licence decision or when the archive exists; builds `<Folder>/`, `<Folder>-<version>.zip`, `original/`,
       `workspace/` and `ARCHIVE_NOTE.md` from the mod's own data (author, licence decision and reason, the report's
       final status, shipped files changed or added versus `original/`, and whether every jar is byte-identical);
       never deletes the workspace. Trial on Combat-Radar: 1 file changed (`mod_info.json`), jars identical. Test:
       `tests/test_archive.py`.
    2. **Test list merging in settings.json** (item 19's held rule), then write the fixer or baseline helper for it.
       **Done 2026-09-27:** lists add, they do not replace (item 19); no fixer needed for `ruleCommandPackages`.
    3. **`finding-stats` deltas.** Keep the previous run and report what moved between runs (mods that changed
       bucket, ids that disappeared), so the effect of new fixers and check fixes is measured, not recomputed by hand.
       **Done 2026-09-27.** `finding-stats --write` keeps the previous run as `FINDING_STATS.previous.json` and appends
       "Since the last run" to `FINDING_STATS.md` (unattended count, mods that changed bucket, finding ids whose
       occurrences changed). Test: `tests/test_finding_stats.py`.
    4. **Persist named encodings.** `fix --encoding FILE=ENC` decisions live only in the fixed files; record them in
       the workspace (REVIVAL_PLAN.md or a small JSON) so a re-copy from `original/` can reapply them, and let
       `revive` read them.
       **Done 2026-09-27:** `fix --encoding` records each decision in `<workspace>/NAMED_ENCODINGS.json`; `revive` passes
       the recorded encodings of files still not UTF-8 to the fixer. Test: `test_named_encodings_are_recorded_and_reapplied_by_revive`.
    5. **`revive` should keep a fixer's partial refusals.** When `data-file-not-utf8` converts some files and
       refuses others, the refused list is dropped because the plan has changes; surface it as a pending item.
       **Done 2026-09-27:** the fixer records `partial_refusals` on its options and `revive` adds them as a FIXER_REFUSED
       pending item next to the applied part. Test: `test_partial_refusal_is_kept_as_a_pending_item`.
    6. **`vendor-copy` should recognise an equivalent vendored row.** RevenantLib's `shields_formshield` row
       differs from Rebal's only by the newer column layout and the repackaged script, yet reports CONFLICT; compare
       values column by column and treat a known script repackaging (PROVENANCE.md) as equal.
    7. **`prepare-test` first copy.** It refuses a rig folder that does not exist yet, so the first copy had to be
       made by hand; let it create the folder and do the initial sync.
       **Done 2026-09-27:** `copy-drift --sync` makes the first copy when `<rig>/mods/<Mod>` does not exist yet (linked rigs only). Test: `test_sync_makes_the_first_copy_when_the_rig_folder_does_not_exist`.
    8. **One library table.** `revival_audit._LIBRARY_DEPENDENCY_IDS` duplicates `scanner.LIBRARY_DEPENDENCY_IDS`
       and already lacks the Console Commands entry item 14 added; derive one from the other.
       **Done 2026-09-27:** `revival_audit` now reads `scanner.LIBRARY_DEPENDENCY_IDS` (it lacked Console Commands).
    9. **Check `undeclared-library-dependency` on real data** before adding it to the standing approvals; it
       declared the wrong library once (item 14).
    10. **Confirm dialog-text capture live** (item 18): the first run that shows an error dialog should put a
        `dialog:` line in `<TESTID>.windows.txt` and a FATAL in triage.
    11. **Faction-Relationships-Uniquified's lone 0x9D byte** (item 17): the tail of a broken UTF-8 `”`; a person
        decides the replacement.
       **Done 2026-09-27:** owner chose to delete it (FRU-ENC-01 in its report).
    12. **`escalation apply <packet>`**: copy an attempt already VERIFIED (and reviewed) into `working/` with a
        backup, instead of `run --apply` re-running the agent and producing an unreviewed edit (item 21).
        **Done 2026-09-27.** `escalation apply WORKSPACE PACKET [--attempt N]` (`escalation.apply_verified`): the
        newest VERIFIED attempt from the ledger, refused when the packet's files changed since the packet or the
        attempt touched other files, re-verified, copied back with backups, ledger `APPLIED` with
        `applied_without_rerun`. Test: `tests/test_revive.py`.
    13. **Agent command discovery:** when `claude` is not on PATH, find the VS Code extension's `claude.exe` (item 21)
        or say where to look, instead of failing with WinError 2.
        **Done 2026-09-27:** `escalation.resolve_agent_command` swaps `claude` for the newest extension's
        `resources/native-binary/claude.exe` when `claude` is not on PATH. Test: `ResolveAgentCommandTests`.
    14. **Keep line endings in agent edits:** the agent turned CRLF into LF; `escalation verify` could normalise
        back to the file's original endings so diffs show only real changes.
       **Done 2026-09-27:** `escalation._copy_back` restores CRLF on an LF-only text edit of a CRLF file. Test: `tests/test_escalation_line_endings.py`.
    15. **Done 2026-09-27: `fleet-type-name-missing`** (REVIEW; source literals in loose scripts and jar sources,
        against the faction file and vanilla's/the mod's `default_fleet_type_names.json`; test
        `tests/test_fleet_type_names.py`), tier `auto` with fixer `fleet-type-name-missing` (title-cased names inserted as
        text, `--names` overrides). Original note: **Check: fleet type with no name.** Zorg18's live run showed "no name for type [Zeta AI raid]": a
        `createEmptyFleet(faction, "<type>", ...)` (source or bytecode string constant) whose faction file has no
        `fleetTypeNames` entry for that type, and no vanilla default. Cosmetic but visible in every encounter;
        the fix is a data entry, so it can be a fixer that proposes the name from the type string.
    18. **Zorg18 follow-up (owner, 2026-09-27, after archiving):** Zorg's artificial star and hive planet appear in
        random systems (seen in Johannam). `star_gen_data.csv` gives `star_zorg` vanilla `star_yellow`'s weights
        (40/35/30) and `planet_gen_data.csv` gives `zorg_planet` weight 10; the original has the same rows. Fix is
        setting those frequencies to 0 (ZorgGen places the star itself); recorded in `Done/Zorg18/ARCHIVE_NOTE.md`,
        not yet applied. **Check to add:** a mod's procgen row for a star or planet type that the mod's own code places
        by id (e.g. `addStarSystem`/`initStar` with that type) and whose texture is mod-specific, with a
        non-zero frequency, is REVIEW ("will also appear in random systems"); a fixer can zero the frequency.
        **Zorg r3 applied 2026-09-27 (owner):** `star_zorg` weights 40/35/30 -> 0 and `zorg_planet` 10 -> 0; and, from
        a mock-up of three options, the star's glow switched from Zorg's opaque tiled `zorg_halo02.png` to vanilla's
        soft `graphics/fx/star_halo.png` tinted `[40,255,120,150]` (`planets.json`, `star_zorg` only). Build
        `[BF r3]` / `V18+bf.3`; `Done/Zorg18` and the rig copy updated (drift 0). New-game check pending: the save
        should hold exactly one `star_zorg` and no `zorg_planet` outside Zorg Zeta.
        **Validated 2026-09-27 (ZG-R3-20260927):** probe 0.2.6 `campaign-layout|OK` with `star_zorg=1, zorg_planet=2`, no
        WARN/FAIL for either type (first live use of the check); owner confirmed the star; FATAL=0, MOD-ERROR=0.
       **Done 2026-09-27:** fixed in r3 (procgen weights zeroed), and r4 archived after live tests ZG4-1..4.
    17. **Triage across relaunches.** `bf-test launch` redirects only the session it starts; a player relaunch
        (ZG-7's save/quit/load) goes only to the game's `starsector.log`. `triage` should also read the rig's
        `starsector.log` lines after the launch time, so a multi-session test is triaged whole.
        **Done 2026-09-27:** `log-triage <rig>/logs/starsector.log --last-sessions N` triages only the last N sessions
        (each starts at the launcher's "Starting Starsector" line; the log has no dates). Test: `tests/test_log_triage_sessions.py`.
    16. **`shippable-work-file` references (done 2026-09-27):** mentions inside IDE/VCS folders (`.idea`, `.git`,
        `src*`) no longer count as runtime references; Jackundor's `.idea/libraries/data.xml` had kept two
        backup zips in the mod. Test: `tests/test_fixers.py`.
21. **First agent escalation run: Yunru's Unpack Blueprints reaches UNATTENDED_DONE (2026-09-27, P15 items 2-3, 8-9).**
    `revive --apply` applied the standing `mod-info-game-version-inexact` approval and left one `code` packet
    (`loose-script-janino-risk`: 9 typed for-each loops in `data/scripts/UnpackBlueprints.java`).
    `escalation run` with `claude -p --permission-mode acceptEdits --allowedTools Read,Edit,Write,Grep,Glob`
    (Claude Code 2.1.283) returned **VERIFIED after 1 attempt in 61 s**. The packet was enough: the agent
    needed nothing beyond its excerpt, allowed file and hint. The diff, read in full: all 9 loops rewritten as a
    raw `Iterator` with a `(String)` cast plus `import java.util.Iterator`; otherwise only whitespace (trailing
    blanks, 5 trailing empty lines) and CRLF -> LF. The reviewed attempt was copied into `working/` by hand
    (backup `*.pre-bf-agent-loose-script-janino-risk.bak`), then `escalation verify` PASS, `compile-check` PASS
    (0 errors in 1 loose script), `revive` UNATTENDED_DONE with the report drafted. **Live YUB-1-20260927:**
    FATAL=0, MOD-ERROR=0, the rewritten script loaded in RC8, and the owner ran tooltip, unpack and learn paths.
    Found on the way (added to item 20): the `claude` CLI was not on PATH on this machine (the VS Code
    extension ships `claude.exe` under `.vscode/extensions/anthropic.claude-code-*/resources/native-binary/`), and
    `escalation run --apply` re-runs the agent instead of applying the attempt already verified and reviewed.
22. **Recommended next work: gap coverage, fixers, RevenantLib (proposed 2026-09-27, not started).** Ranked by
    mods helped per unit of work, from the 2026-09-27 queue counts and live runs.
    1. **Compile loose scripts with the game's own Janino, offline.** `loose-script-janino-risk` is HEURISTIC
       (a typed for-each pattern; 125 occurrences in 48 mods, the only blocker for 5), while `compile-check`
       uses javac, which accepts what Janino rejects. RC8 ships `janino.jar` and `commons-compiler.jar`, and
       `build-probe-mod` already compiles the probe mission with them. Running every mod's loose scripts through
       Janino turns the risk into a DETERMINISTIC pass/fail, catches Janino-only failures the pattern misses, and
       gives agent fixes (item 21) a ground-truth check.
       **Done 2026-09-27.** `compile_check.janino_compile` runs every loose script javac accepted (and no jar
       shadows) through RC8's own `janino.jar` 2.7.8 via `bridgeforge/java/JaninoCheck.java` (now many classes and
       source roots per JVM, a fresh loader per class; the mod and vanilla core are the source roots, javac's
       classpath the parent). `compile-check` prints the result and FAILs on a Janino rejection; the scanner's
       compile step removes a file's `loose-script-janino-risk` once Janino accepts it and adds MANUAL
       `loose-script-janino-compile-error` when Janino rejects it. **Finding:** Janino 2.7.8 accepts a typed
       for-each over `List<String>` whose element calls a String method; it rejects lambdas and a method call on
       a generic-typed value (`e.getValue().size()` on a `Map.Entry<String, List<String>>`), because it erases
       generics to Object. Yunru's Unpack Blueprints' **original** compiles: item 21's rewrite was harmless but
       not needed, and the risk pattern over-reports. Tests: `tests/test_janino_compile.py` (pure outcome tests,
       plus a real-Janino test that runs only where the RC8 install is present).
       **Queue survey (2026-09-27, the 48 mods `loose-script-janino-risk` flagged, 124 files):** under RC8's Janino
       run as the game runs it, **47 mods compile clean**; the one rejection is Bird's Collection of Trinkets and
       Rarities' `bc_flarePrimaryAI.java`, which imports LazyLib the mod never declares (javac never reached it: it
       stopped at a syntax error in `BcZeroFluxJets.java`). No rejection involved a typed for-each. Harness fixes
       found on the way, each confirmed on a real mod: class names come from the file's `package` line, with the
       matching source root (Content-Unlocking-Missions, Bricky-Construction keep packages that differ from
       their folders); a failure inside a script another file loads is blamed on that file, and dropped when
       javac already rejected it (Hiver-Swarm); only Janino's own exceptions count, so a static initializer that
       calls game code offline is not a failure (Adjusted-Sector); and the harness JVM runs with `-noverify` as
       the game does (RC8 `vmparams`, the rig's `run-java25.bat`), since the verifier otherwise rejects Janino
       bytecode the game loads (DNEEP, Osiris-Alliance).
    2. **Dropped 2026-09-27 on evidence:** the queue survey in 1 found no Janino rejection of a typed for-each, so
       there is nothing for a loop fixer to fix. Superseded text: **A fixer for typed for-each loops.** The rewrite is mechanical: BDS had 10 done by hand (item 45) and the
       agent did 9 identically (item 21). When the loop variable's collection is a local or field declared with a
       generic type in the same file, rewriting to a raw `Iterator` plus cast is deterministic; anything else
       stays with the agent. Verified by (1). Moves most of the 48 mods' occurrences out of the `code` tier.
    3. **Split `content-reference-unresolved` by consequence.** Live runs proved a missing weapon in a variant is
       a New Game fatal and a missing hull mod is silent (item 18). A missing weapon should be MANUAL/high even
       when the mod declares dependencies; a missing hull mod can stay REVIEW. Needs a quick live check for
       missing wings and hulls before classifying those.
       **Done 2026-09-27** (severity; classification unchanged): `critical` when a weapon is missing, `medium`
       when only hull mods are, `high` otherwise. Tests: `tests/test_batch_lessons.py` (`UnresolvedContentTests`).
    4. **Batch-revive the `auto` bucket** (51 mods on 2026-09-27, before item 19's fix): `revive --apply
       --draft-report` over each, dry run first, with `finding-stats` before and after. Uses item 12's progress
       rule. The biggest single jump in finished mods for the least owner time.
    5. **RevenantLib bridge candidates from the queue.** Only three `bf.*` bridges exist. Run `compile-check
       --api-diff` over every queued mod's `original/` against the 0.8.1a and 0.95.1a catalogues and rank the
       removed methods by how many mods call them; the top ones with a clean RC8 equivalent become new
       RevenantLib bridges and `removed-api-call` fixer rules. Each needs javap evidence for the replacement.
       **Run 2026-09-27 (loose scripts):** `compile-check` + the 0.8.1a->RC8 catalogue over the `original/` of all
       294 queued workspaces (242 PASS, 52 FAIL). Only **10 mods** call a removed API from loose scripts. Top:
       `SectorAPI.createFleet(String, String)` (6 mods, 17 sites; RevenantLib already bridges it) and
       `SectorAPI.addMessage(String)` (5 mods, 10 sites; the `removed-api-call` fixer already rewrites it to
       `CampaignUIAPI`); everything else is one mod each (`CommodityOnMarketAPI.getSupply()`,
       `MarketDemandAPI.getNonConsumingDemand()`, removed `Conditions`/`Skills`/`Stats` ids). **No new bridge is
       justified by loose scripts.** Follow-up: the same ranking over jar bytecode (method/field references
       resolved against RC8's `starfarer.api.jar`, the "bytecode linkage" method), since most large mods ship jars.
    6. **Keep the `Done/RevenantLib` snapshot honest.** `revenantlib-check` could compare the snapshot's jar with
       the live `working/` jar and say when the snapshot is stale.
       **Done 2026-09-27.** `revenantlib-check PATH --snapshot Done/RevenantLib/RevenantLib` compares the checked mod
       folder with the archive (`copy_drift`) and prints `snapshot CURRENT` or `STALE` with the differing files.
       Today's snapshot: CURRENT. Test: `tests/test_revenantlib_contract.py`.
    7. **A special-item check in the probe.** Yunru's mod works through a `special_items.csv` plugin class; the
       probe checks ships, weapons and wings but not items. Resolving each mod special item's spec and plugin
       class at runtime would cover item mods (needs javap evidence for the SettingsAPI item-spec methods).
       **Done 2026-09-27 (probe 0.2.5, live run pending).** `probe-config` lists `special_items.csv` ids
       (`content_special_items`); `content-ids` looks each spec up and adds it to a throwaway cargo, then checks the
       stack's plugin exists, which instantiates the plugin class as real cargo does (javap 2026-09-27:
       `SettingsAPI.getSpecialItemSpec`, `FactoryAPI.createCargo`, `CargoAPI.addSpecial`/`getStacksCopy`,
       `CargoStackAPI.getPlugin`). Yunru's mod: 9 items. Test: `tests/test_probe_config.py`.
    8. **Settings list merge test** (item 19's held rule) and **dialog-capture confirmation** (item 18):
       each one short rig run.
23. **Batch revive of the unattended bucket (2026-09-27, P15 item 22.4).** `finding-stats` after items 12-19:
    65 of 304 mods unattended (21%, from 43 in the morning). Dry run of `revive` over all 65: 58 needed only
    the standing approvals (`AUTOMATION_POLICY.json`), 7 needed another fixer, no errors. Applied with
    `--apply --draft-report`: **58 of 58 reached UNATTENDED_DONE** (Jackundor's Advanced Arms after the
    work-file fixer fix in item 20.16). Of the 7, reviewed by hand: Combat-Radar, Simulator-Overhaul and
    Transfer-All-Items call `org/lazywizard/lazylib` in their jars, so LazyLib was declared (approved per run);
    Unconventional-Armaments dropped only empty trailing CSV fields; Anex-Weapons' fixer refused (non-empty
    extra fields): 9 `descriptions.csv` quotes began `- "...` unquoted, so commas split them across columns;
    each `text2` was rejoined and quoted (backup kept); all five UNATTENDED_DONE. D-MOD-Services and
    Fuel-Siphoning left open: their LunaLib use is behind `isModEnabled("lunalib")` in the mod plugin, an
    optional settings integration, so declaring LunaLib would force it on every player (owner to confirm).
    **UNATTENDED_DONE now: 63 queued mods** (plus ClearCommands archived). Each still needs its probe run.
    Later the same day: D-MOD-Services and Fuel-Siphoning accepted LunaLib as optional (owner; baselined), so
    66 at UNATTENDED_DONE. **Zorg18 live-validated** (ZG-1..ZG-7, owner, all successful; probe 0.2.5 content-ids
    checked=19 failed=0, all 11 hulls deployed). Live findings fixed: `zorg.faction` had no `fleetTypeNames`
    ("no name for type [Zeta AI raid]"). Explained, unchanged: Unimatrix has no dialog in the original either;
    the oversized fighter shields are the Trapezoid "Generator" wing's own 200 radius; Askonia raids ran (2 in
    the save). Found on the way: `bf-test launch` captures only the session it starts; a relaunch logs only to
    the game's `starsector.log` (roadmap item 20).
24. **Probe several finished mods per live session (2026-09-27).** 66 mods reached UNATTENDED_DONE and each
    still needs a probe run; one mod per session is the bottleneck. **Done 2026-09-27.** `bridgeforge
    probe-group` (`bridgeforge/probe_group.py`). The probe (0.2.5) reads a config of lists and maps and never
    uses the target id for a check, so a group is probed by merging members' `build_probe_config` output (a
    `group_members` map keeps each member's ids). `plan` groups workspaces whose report ends
    `READY_FOR_LIVE_TEST` so no two members share a mod id or content id (hull, variant, wing, special item),
    every declared dependency is installed in the rig, and a total conversion goes alone; it writes
    `In operation/PROBE_GROUPS.json`. `install N` copies or syncs members into the rig (shipped files only),
    writes the merged config and rig marker, installs the probe, and sets enabled_mods.json to the members,
    their dependencies and the probe (rig-only guard as probe-config). `report LOG` gives each member PASS,
    FAIL (probe FAIL lines matched by the id they name; crashes by log-triage's jar attribution), UNCLEAR (a
    crash no member owns: rerun that group's members alone) or INCOMPLETE (content-ids never ran). On the queue:
    **63 mods in 8 groups** of up to 8; SOTF-Addon-SPARKLE and UAF-Skills wait for dependencies the rig lacks
    (Secrets of the Frontier, UAF). Tests: `tests/test_probe_group.py`.
25. **Campaign-layer check: the mod's systems exist, and its unique bodies stay in them (owner request, 2026-09-27).**
    From Zorg18's artificial star appearing in random systems (item 20.18). **Done 2026-09-27.**
    `bridgeforge/campaign_layout.py` finds the systems a mod creates (`createStarSystem("...")` in loose or jar
    sources, and in jar bytecode an `ldc`/`ldc_w` String immediately before the call, which finds ZorgGen's
    "Zorg Zeta") and the mod's own `planets.json` types with their procgen weight. Static check
    `procgen-mod-body-leak` (REVIEW, tier `auto`): a type the mod places by id that also has a procgen weight;
    its fixer zeroes that type's frequencies only (on a copy of Zorg's original it reproduces the hand-made r3
    fix exactly). Probe 0.2.6 `campaign-layout`: FAIL for a created system missing from the sector, FAIL for a
    zero-weight mod type found in a system the mod did not create, WARN listing where a weighted one went, and an
    OK summary with per-type counts (javap 2026-09-27: `SectorAPI.getStarSystem/getStarSystems`,
    `LocationAPI.getPlanets`, `PlanetAPI.getTypeId`, `StarSystemAPI.getBaseName`). `probe-group` merges both
    fields. Installed in the rig for the Zorg r3 new-game check. Tests: `tests/test_campaign_layout.py`
    (including a compiled-jar case).
26. **`corpus-index build` was quadratic (R3, 2026-09-27).** R3's first Downloads build (42 GB) ran 11 hours; a
    psutil sample showed 18 GB read in 15 s and 2.3 s of CPU, all re-reading its own 1.3 GB index. `_forget` deleted
    content with `WHERE location IN (...)`, but `location` is UNINDEXED in the FTS5 table, so every file, even a new
    one with nothing to delete, scanned the whole index. **Done 2026-09-27.** Schema 2: `content_rows` maps each
    content rowid to its source (indexed), `_forget` deletes by rowid, new files skip `_forget`, and `files`/`skipped`
    are indexed by source; an older-schema index with content is refused rather than slowly updated. Benchmark on
    the rig's mods: a steady ~130 files/s, 32,000 files in under 4 minutes with no slowdown. Test:
    `tests/test_corpus_index.py`. R3 must be stopped and rebuilt into a fresh index.
    **R3 done 2026-09-27** on the fixed code: 69 min for all of Downloads (42 GB), 403,544 text files searched and
    1,295,212 listed by name, a 6.5 GB index. `search shieldbypass` finds `Ironclads mega archive/Ship and Weapon
    Pack/data/hullmods/hull_mods.csv` (and the 0.7.2a modpack copy): the 2026-09-20 false negative is gone. Not searched:
    87 `.rar` archives, 1,003 nested archives, 1 BCJ2 `.7z` (py7zr cannot read it), 2 password-protected zip members.
27. **The shared copy step dropped mod-specific top-level folders (GRP-3, 2026-09-27).** Flux Reticle crashed at
    startup: "Error loading [sun_fr/graphics/half.png]". Its sprites live in `sun_fr/graphics/` (settings.json points
    there), but `copy_drift._collect` (used by prepare-test, copy-drift, release, archive, probe-group) copied only
    `data`/`graphics`/`sounds`/`jars` plus declared jars, so the rig copy, and any release or archive, lacked them.
    **Done 2026-09-27.** Every top-level folder is copied except tool/build folders (`reports`, `scratch`, `src*`,
    `out`, `build`, `bin`, `disabled_files`, `gradle`, `META-INF`, `production`, `test`, VCS/IDE folders). Survey: 29
    working copies have extra folders; affected were Flux Reticle and Fuel Siphoning (`sun_fs`, group 3, resynced;
    GRP-3 then all PASS), and later-group MnemonicSensors (`imgs`) and More-Lamp-Colour-Options (`sound`); groups 1-2
    and the three `Done/` archives were unaffected. Test: `tests/test_copy_drift.py` (`CustomTopFolderTests`).
    Also: `bf-test.ps1 launch` now sets aside an old `<TESTID>.windows.txt` when a test id is reused (GRP-3's retry
    inherited the first attempt's Fatal dialog, making every member UNCLEAR); the dialog capture itself is now
    **confirmed live** (item 18): it recorded that first attempt's Fatal text and triage counted it.
    Probe groups so far: GRP-1, GRP-2, GRP-3 all PASS, 24 mods `LIVE_VALIDATED`.
28. **Lessons from the 2026-09-27 live session, as actions (proposed, not started).** Most valuable first.
    1. **Find the upstream original before reviving.** Zorg18 was revived from a modpack copy that had already
       disabled two features (allocator convoys, assimilation); the author's own V18 was in the Ironclads archive all
       along. With the Downloads index working (item 26), `revive`/`intake` should search the corpus for other copies of
       the same mod id, rank them (author release over modpack copy, by version and file dates) and report files and
       scripts the chosen copy lacks. r4 plan: `In operation/Zorg18/working/reports/REVIVAL_PLAN_R4.md`.
    2. **One source of truth for status.** Covert-Cargoliners' report said READY_FOR_LIVE_TEST while revive said
       ESCALATED. `board`/`finding-stats` should flag any workspace whose report status disagrees with its latest
       `REVIVE.json`, and `revive --draft-report` should replace a stale final status line, not append after it.
    3. **Allowlists of mod paths are wrong by default.** The shared copy step's fixed folder list dropped `sun_fr/`
       (item 27). Audit other allowlists (release hygiene, scanner inventories, `_collect` root-file globs) for the same
       assumption; prefer "everything except known tool output".
    4. **Validate heuristic checks against ground truth before they drive work.** `loose-script-janino-risk` was wrong
       for 47 of 48 mods once Janino itself was run (item 22.1), yet it had sent Yunru to an agent. Every HEURISTIC
       check should carry a measured precision from a sample, and checks under a threshold should not create agent
       packets.
    5. **Fixers can look like bug fixes and still be wrong for a mod.** `procgen-mod-body-leak` fits Zorg but not
       planet packs (Galaxy Tigers, Nightcross). A fixer with any such intent question stays out of standing
       approvals, and its finding should say what intent it assumes.
    6. **Derive library tables from the libraries' own jars.** `org/lazywizard/` was mapped wholesale to LazyLib,
       declaring the wrong dependency (item 14). Build the package-to-mod-id table from the real LazyLib, Console
       Commands, MagicLib, LunaLib and GraphicsLib jars in the rig (and RevenantLib's own), and merge
       `revival_audit`'s duplicate table into it.
    7. **Scale tests for long runs.** `corpus-index` was quadratic (item 26) and only a 42 GB run showed it. Add a
       test that times N vs 4N files and fails if the ratio is far from linear, for `corpus-index`, `finding-stats`
       and `probe-group plan`.
    8. **Archives must carry the jar source.** r3's `ZorgFleetSpawner` source survived only in `artifacts/`. `archive`
       should copy `working/src*` (and `jars/src*`) into `workspace/`, never into the shipped folder.
    9. **Live tooling:** every live session writes its own window log (done), triage folds in relaunched sessions from the
       rig's `starsector.log` (item 20.17), and groups record a per-mod verdict straight into each report (done by hand
       for GRP-1..3; make it `probe-group report --record`).
    10. **RevenantLib:** removed-API use sits in jars, not loose scripts (item 22.5 ranking): run the ranking on jar
        bytecode before adding bridges; keep `revenantlib-check --snapshot` in the release checklist.
    11. **Author updates as ground truth (2026-09-27).** 10 finished mods had a newer author release for 0.98a in the
        0.98 modpack (all marked SUPERSEDED; 5 had already passed their group probe run). Scanning each old version and
        the author's new one: `mod-info-game-version-inexact` disappeared in all 10 (the only change these authors
        needed that BridgeForge tracks, and exactly what revive applied), `library-import-unused-in-jar` in 1.
        `non-strict-json-trailing-comma` (10/10) and `json-hash-comment` (8/10) stay in the authors' working 0.98a
        releases, confirming their tier `none`. In the authors' own releases: Flux Reticle 1.4.0 and Variants-Lib 0.5.6
        use LunaLib behind a guard without declaring it (REVIEW: the D-MOD-Services pattern; `isModEnabled`-guarded use
        should be classed optional/SAFE so it stops needing an owner decision); Hexagonal Shieldidgeridoos 1.3.1 calls
        LazyLib (`FastTrig`) without declaring it (MANUAL, a real undeclared dependency the modpack hides). Action: run
        this old-vs-author comparison for every future supersession and fold the per-check outcome into item 28.4's
        precision numbers.

29. **Probe combat mission: ideas from Legacy of Arkgneisis's own test missions (2026-09-27, proposed).**
    Owner noticed LoA ships four test missions (`loa_randtest`, `loa_stationtest`, `loa_testmission`,
    `al_testmission`); read in `In operation/Arkgneisis/working/src/data/missions/`. Worth borrowing, most useful first:
    1. **Always an opponent.** `loa_randtest` builds each side with `FleetFactoryV3.createFleet(FleetParamsV3)` for a
       faction and a combat-point size. When a group has no mod ships for one side (GRP-5: one ship vs none; GRP-3:
       none), fill it with a vanilla faction fleet of similar fleet points, so every probe mission has a fight.
       **Done 2026-09-27 (probe 0.2.7):** an empty side gets 2-4 vanilla ships, logged `combat-filler`. Test: `test_probe_mission_fills_an_empty_side_with_vanilla_ships`.
    2. **Faction fleets, not just variants.** Generating a mod faction's own fleets with `FleetFactoryV3` tests its
       doctrine, known ships and autofit together, which fixed variants miss (a faction whose lists only work for
       hand-made variants).
       **Done 2026-09-27 (probe 0.2.8):** `faction-fleet-gen` builds one medium patrol per mod faction with `FleetFactoryV3` (never
       spawned); an empty or throwing build is a FAIL blamed on that faction's mod. Test: `test_a_faction_fleet_generation_failure_blames_the_factions_mod`.
    3. **Balanced sides by seed search.** It rerolls seeds and keeps the pair whose fleet points are closest, so a
       fight is fair enough to see both sides act.
    4. **Stations and modules.** `loa_stationtest` puts station variants (theirs and vanilla's `station1_Standard`...)
       on one side. The probe currently skips module hulls at the cap (`loa_module_ars_big`); a station setup would
       exercise them.
    5. **Weaponless "blank" variants** (`loa_testmission`) separate hull loading from weapon problems when a
       deployment fails.
    6. **Keyboard options on the mission screen** (reroll, size, faction) are handy for manual play but not needed
       for the probe, which runs unattended.

30. **Agent escalation, first queue run (2026-09-28).** Six packets on four mods whose only blockers were code
    packets; all VERIFIED. Reviewed before applying:
    - Doc's Needless Economic Expansion Pack: a null guard for a missing Nortia market; applied. Angry Periphery 4:
      four `getEntityById` lookups replaced by the local variables holding those entities (ids checked); applied.
    - Xenoargh AI Overhaul and Adjusted Sector: the agent only deleted commented-out code, which exposed scanner
      behaviour instead. `runtime-placeholder-unsupported-operation` matched a commented-out throw: fixed (comments
      blanked, test `test_commented_out_placeholder_throw_is_not_a_finding`). `campaign-spawn-registration-disabled`
      is correct, but the author disabled that spawn themselves: accepted in Adjusted Sector's baseline.
    - Result: Doc's, Angry Periphery 4, Xenoargh AI Overhaul, Adjusted Sector UNATTENDED_DONE.
    - **Open:** `escalation apply` refuses a later packet once an earlier packet on the same mod was applied, because
      each sandbox was copied before; the three later Angry Periphery packets were copied by hand (their own files
      only, with backups). Fix: record every file's hash at run time and ignore files outside the packet that the
      attempt did not change relative to its own starting copy.

31. **Workflow improvements found in the 2026-09-27/28 sessions (done 2026-09-28).** All 13 implemented; tests per sub-item in the commits. Most useful first; each replaces a step
    done by hand or with a throwaway script this session.
    1. **`probe-group record LOG [--archive]`.** After every group run a scratchpad `record_group.py` marked each PASS
       member LIVE_VALIDATED, then a shell loop recorded the licence decision, ran `archive` and copied the zip to the
       top of `Done/`. One command should do all of it, using the owner's standing licence reason.
       **Done:** `probe-group record TESTID [--archive]`.
    2. **`revive --queue QUEUE [--only-status ESCALATED]`.** Two bash scripts drove the batch and re-runs, with a stamp
       file to resume. Build it in with progress lines and a checkpoint (the long-running rule).
       **Done:** `revive-queue`.
    3. **`probe-group plan --solo NAME... --exclude NAME...`**, and a default that runs large campaign mods solo
       (Exigency and the other four were grouped by default and had to be planned out inline twice).
       **Done:** `probe-group plan --exclude/--solo/--no-auto-solo`.
    4. **One report-status reader.** Four places parse a report's status differently (`probe_group`, `project_board`,
       `archive`, the pre-push hook); a bold line and LIVE_VALIDATED each broke one of them this session.
       **Done:** `bridgeforge/report_status.py`.
    5. **`descriptions` workflow:** `descriptions sheet` (the queue CSV with lore snippets, weapon type, range and role),
       `descriptions apply MOD DRAFT.md` (append rows, keep CRLF, write BRIDGEFORGE_CREDITS.txt, build
       alt-original-descriptions/). This session did it with a scratchpad script.
       **Done:** `descriptions sheet|apply`.
    6. **RC8 behaviour evidence register.** Runtime facts proven from live logs this session (settings.json lists add;
       sounds.json merges by sound id; default_fleet_type_names.json merges; RC8 ships over-budget variants) live only
       in code comments. A `docs/RC8_BEHAVIOUR.md` (or JSON) with each fact, its evidence and date, cited by the checks
       that rely on it, would stop re-deriving them.
       **Done:** `docs/RC8_BEHAVIOUR.md` (15 facts).
    7. **Jar-source code packets:** let `escalation run` edit `jars/src`, then `rebuild-jar` and verify the rebuilt
       class, so code packets in compiled mods (most of the remaining `code` tier) become attemptable.
       **Done:** `escalation apply --rebuild-jar` (rebuilds in the attempt folder, refuses on any lost class or member).
    8. **`escalation apply` after an earlier apply** (item 30 open): record every file's hash at run time and compare
       the attempt with its own starting copy.
       **Done:** START_TREE.json per attempt.
    9. **Rig guard in `probe-group install`:** check `who-locks` first and say "close the game" instead of a WinError 32.
       **Done:** install checks the probe jar first.
    10. **Scanner-change impact:** `finding-stats --check ID` to rescan only one check across the queue and report which
        mods it clears or newly flags. This session wrote that loop by hand for each false-positive fix.
       **Done:** `check-impact`.
    11. **Supersession beyond the install:** also compare against the Downloads corpus index and a modpack, and flag a
        shared id under a different name (Cryosleeper 2 in AoTD) for review.
       **Done:** `supersession --corpus-index` (first run: 101 queued mods have newer 0.98 releases, 98 in the 0.98 Modpack V6.2, 83 never revived).
    12. **Decision page:** render `ESCALATIONS_BY_FINDING` as a page the owner can rule from (one ruling per finding id,
        recorded to AUTOMATION_POLICY or a baseline), instead of rulings typed into chat.
       **Done:** `escalation rule FINDING --accept|--approve-fixer --reason` (ESCALATION_RULINGS.jsonl); the page itself stays ESCALATIONS_BY_FINDING.md.
    13. **Probe: report each variant that fails to build by id** (Broken Star's ballistic-in-missile-slot variant is
        watched that way now), and count combat-filler use in the group report.

       **Done:** `combat_filler_sides` in the group report.
32. **Less hand work in escalation, from the 2026-09-29/30 batches (done 2026-09-30).** Owner-approved list; each
    replaces a step done by hand at least twice.
    1. **Review sheet** (`escalation review WS`, also written after every `escalation run`): each packet's newest
       attempt with its diff and flags for a removed hint or tag, Random/save logic, a rewritten loop, a swallowed
       exception, a net deletion, a moved baseline, or an agent asking to leave its sandbox. On the real batches it
       flagged Covert (hint removed), Vesperon (Random) and Arthr (loop), the three caught by hand.
       Tests: `tests/test_escalation_review.py`.
    2. **Watched directories** (`escalation run --watch-dir DIR`): what an agent run changed there is reported, for
       the session's memory folder.
    3. **One packet per file:** agent packets for different findings on one file merge (`merged` lists the ids;
       verify needs all gone; queue counts and `escalation rule` see every id). Pegasus's entity and system packets
       were merged by hand. Test: `SameFilePacketMergeTests`.
    4. **Run lock:** a second `escalation run` on a workspace refuses while the first's process is alive (the
       2026-09-29 pilot collisions). Test: `RunLockTests`.
    5. **`jar-packets WS`:** for each jar-only packet, finds the class's source, copies it to scratch to edit, and
       says FAITHFUL / SOURCE_DIFFERS / COMPILE_FAILED / NO_SOURCE by compiling the unedited copy with
       `patch-jar-class`. Too Much Information has no source and there is no decompiler on the machine now
       (IntelliJ's Fernflower was used for FlowerGod). Tests: `JarPacketsTests`.
    6. **`ready-list QUEUE`:** the mods ready for live testing (22 on 2026-09-30). Test: `tests/test_ready_list.py`.
    7. **Campaign lookup guard fixer** (hard-coded-campaign-system/entity-reference): a one-line declaration of a
       `getStarSystem`/`getEntityById` result directly in a void method gets `if (v == null) { warn; return; }`;
       every other shape (Pegasus's inline `getEntityById("nomios")` argument, a loop) is refused for an agent. Tier
       auto, but the findings are REVIEW, so revive applies it only once approved. A null-guarded lookup stays a note.
       Tests: `tests/test_campaign_lookup_guard_fixer.py`.
    8. **Faction known lists from `fleetCompositions`:** a 0.6-era faction without shipRoles derives its lists from
       its fleets' ships, and a wing id in a role or fleet list counts as a known fighter. A faction with no roles,
       fleets or markets is a SAFE note (`nothing-reads-lists`; hvb_hostile in three mods). Of 14 refusals, 6 now
       derive, 3 become notes, 5 name variants that do not exist (aurora_Escort, condor_FS, heron_Standard,
       mole_miner, Thule's own) and stay per-mod work. Tests: `FactionKnownListsMissingTests`.
    9. **hullmod-instance-state:** a private primitive or String field that no method writes is no longer flagged
       (9 of 86 source packets: commented-out code in AI War, Tahlan's runOnce); arrays, objects and non-private
       fields still are (KT_Biter fills an array per ship). Agents get the per-ship `getCustomData()` recipe as the
       packet hint. Tests: `tests/test_hullmod_instance_state.py`.
    10. **Not built:** blank values from another version of the mod (`wing-op-cost-blank`): 10 of the 15 mods are
        pre-0.8, when fighters had no OP cost, so no copy has a value. What RC8 does with a blank cost is not yet
        proven (vanilla has none blank); a probe row for it is the next step.
    11. **Decompile for jar-only packets:** `jar-packets` decompiles a jar with no source using Vineflower 1.12.0
        (the maintained Fernflower fork; `In operation/_tools/`, fetched from Maven Central 2026-09-30, SHA-1
        checked, never committed) into scratch with a PROVENANCE.txt, then runs the same faithful check. A call whose
        RC8 return type changed is a relink, not a difference. Too Much Information's five classes are FAITHFUL.
        Tests: `RelinkAndDecompilerTests`.
    12. **`jar-linkage-unresolved` (new check):** every Methodref/Fieldref a declared jar makes into a game class,
        resolved through RC8's core jars and hierarchy (`bridgeforge/linkage.py`); jars other rig mods declare count
        as providers. Found through Too Much Information: `TooltipMakerAPI.beginTable(...)V` returns `UIPanelAPI` in
        RC8, a NoSuchMethodError as shipped that nothing flagged. Over the 79 live-validated mods in Done/ it found
        only `addImageWithText` in four (Arkgneisis, Megastructures Tab, RogueSynth, Slightly Better Tech Mining),
        the same break on tooltip paths the probe does not open: fixed by recompiling the class. Tier code (a
        jar-only packet). Test: `tests/test_jar_linkage.py`.
    13. **Two input fixers run unattended** (owner ruling 2026-09-30): `csv-missing-design-type-column` adds the
        column blank (no design type invented, no colour), and `procgen-planet/star-row-missing` copies the vanilla
        row nearest by name (water, lava, gas giant..., else barren / star_yellow) with frequency 0. Tier auto;
        REVIEW findings, so applied where approved (planets and the design column are). Tests:
        `UnattendedInputFixerTests`.
    14. **First queue run with the linkage check (2026-09-30):** 36 queued mods call game members RC8 changed; 30
        only by return type. 19 were relinked in the main session (unedited shipped or decompiled source, patched
        only when every changed call is a return-type relink and no member changes); 11 were left: their source or
        decompile does not compile against RC8 (7), shows other differences (3), or is missing a class (2). 6 need
        a real port (a removed class or member): Dassault-Mikoyan, Kadur Remnant, More Combat Terrain Effects,
        Tore-Up-Plenty, Tyrador, Void-Tec. The four live-validated Done/ mods with the same break were relinked at
        the owner's request, versions iterated (+bf.N), back to READY_FOR_LIVE_TEST (MOD_CHANGELOG.md).
        Review of the run's 33 lookup guards found the CRLF placement bug fixed in 32.7.
33. **The 2026-09-30 scratch scripts as commands (done 2026-10-01).** Owner request: automation for hand work.
    1. `relink QUEUE|WS --vanilla-core [--apply]` (long-running: progress, RELINK.partial.jsonl): the relink path
       from 32.14, with two fixes that made more classes relinkable: an Object method whose recorded owner changed
       (`Object.equals` vs `CampaignFleetAPI.equals`) is noise, and a decompile's re-declared variable in a shared
       switch scope is commented out and recompiled (RogueSynth). Queue dry run: 157 clean, 2 more relinkable
       (Epta, Scy Nation; applied), 9 left with the reason, 6 need a port. Revive runs it itself when
       `jar-linkage-unresolved` is approved in AUTOMATION_POLICY.json (not approved yet).
    2. `patch-jar-sources WS --vanilla-core [--apply]`: edits in a jar's source tree (backups beside them) go into
       the jar after the pre-edit source is shown to rebuild the shipped class.
    3. `bump-version WS --note`: +bf.N, a dated report section ending READY_FOR_LIVE_TEST, a MOD_CHANGELOG line.
    4. `restore-from-done Done/<Mod>`: workspace back from an archive, reports and baseline included; says when
       the archive kept no baseline (Arkgneisis).
    5. `revive-review QUEUE --since DATE`: every applied fix diffed against its first backup; flags a misplaced
       lookup guard or a jar-source edit. Over 2026-09-30: 75 applied, 0 flagged after the repairs.
    Tests: `tests/test_workspace_tools.py`, `tests/test_progress.py`.
    6. **`jar-interface-method-missing` (new check, 2026-10-01):** a concrete jar class whose game supertypes declare
       an abstract method nothing in its hierarchy implements (an AbstractMethodError as shipped), from the class
       files (`linkage.missing_interface_methods`; access flags now parsed). Found by compiling Polaris Prime, UNGP
       and Wotani; the check then found nine more Wotani on-hit classes the relink never touched.
    7. **`port-interfaces QUEUE|WS --vanilla-core [--apply]`** (long-running): ports the known RC8 contract changes
       in shipped or decompiled source (onHit's ApplyDamageResultAPI, createCustomDialog's callback, an empty
       buttonPressed) or, for a class implementing HullModEffect, CustomProductionPickerDelegate,
       CampaignEntityPickerListener, CustomUIPanelPlugin or CustomDialogDelegate directly, `extends` vanilla's base
       class (each checked concrete and complete for its interface). Patched only when each class changes by exactly
       that. First run: 85 classes in 9 mods (DME 54, Wotani 10, Grytpype 6). Revive runs it when
       `jar-interface-method-missing` is approved (not yet).
    8. **Relink, three more cases:** a shipped source that does not compile (Lombok) falls back to the decompile;
       Vineflower runs with `--kt-enable=false` (Kotlin classes as Java); an RC8 overload of the same name the
       unedited source recompiles onto (Void-Tec's addCustom) and a same-descriptor rename (RENAMED_METHODS:
       pickPortrait -> pickPortraitPreferNonDuplicate, Kadur Remnant) pass the gate. Declared dependencies are found
       in the queue too (Magellan Shenanigans needs Magellan Protectorate). Scratch copies are keyed by package path
       (Kadur's seven MissionDefinition classes). Tests: `OverloadGateTests`, `JarInterfaceMethodTests`, `SourcePortTests`.
    9. **Left for a person (2026-10-01):** Tore-Up-Plenty (addMarket gained a parameter, setBaseSmugglingStabilityValue
       removed, source does not build), Tyrador (createOfficer's 4-argument form has no RC8 match), DME
       (BaseSalvageSpecial.setExtraSalvage removed; one mine-strike AI class), More Combat Terrain Effects (calls the
       obfuscated internal Cloud class), Exotica Technologies (Kotlin decompile does not build), Bounties Expanded and
       Special Hullmod Upgrades (the rebuild adds or drops a null check), Valkyrians (decompile error), and the
       anonymous classes the port does not edit.
    10. **Anonymous classes and source copy-back (2026-10-01):** an anonymous class of a base-class interface is
        ported in its outer source (`new CampaignEntityPickerListener() {` -> `new ...BaseCampaignEntityPickerListener() {`;
        Arkships' gate picker, which the full revive run caught, and RogueliteSector's startup dialog). When the
        source came from the mod's own tree, the edited file is copied back over it (backup beside it) so the shipped
        source matches the patched jar. Test: `CopyBackTests`.
    11. **Owner rulings 2026-10-01, done.** DroneLib folded into RevenantLib 1.3.0+bf.1 (whole, names unchanged;
        `dl_DroneAPI` given the 83 methods RC8 added to ShipAPI as forwarding delegates; RevenantLib builds from
        source again with the obf jars on its classpath and `setColor` -> `setBaseColor`). More Combat Terrain Effects
        and Exotica: superseded (0.98 releases in the 0.98 Modpack V6.2), as are both Dassault-Mikoyan copies,
        Logistics Notifications, ScalarTech and Stinger (name match). Hand ports: Tiandong (three inflater methods,
        vanilla bodies), Vanidad (two BoundsAPI methods), Tore-Up-Plenty (0.8 markets: industry-conditions ->
        addIndustry via LEGACY_MARKET_CONDITIONS, addMarket(m, true), smuggling stability dropped), Tyrador
        (forgeship rebuilt from the author's newer source), Valkyrians (decompile parentheses), Bounties Expanded and
        Special Hullmod Upgrades (the only extra difference was `requireNonNull(this)`), Explorer Society and
        Tyrador on-hit (jar kept a stale class the fixer had already ported in source), Neutrino and The Nomads
        (BaseShipSystemScript added to the base-class table), Xenoargh Rebal TowCable.
    12. **Tooling from those:** `close WS --status SUPERSEDED|NOT_REVIVABLE --reason` (queue commands now skip closed
        mods: 102 of 295), `requireNonNull(this)` is not a counted call, port-interfaces builds a source already in
        RC8's form, and supersession matches by name. Tests: `CloseTests`, `ThisCheckNoiseTests`, `PortTableTests`,
        `NameMatchTests`.
34. **Plan: fixers and automation for the hand work of the 2026-10-02/04 agent batches (owner request 2026-10-04).**
    Each item is work done by hand (or by agents, then reviewed by hand) at least three times. Ordered by how much
    hand work it removes.
    1. **Per-ship state fixer for `hullmod-instance-state`** (the largest packet class: 54 source + 44 jar). Done by
       hand or by agent 12+ times with one recipe: move each written field into a private static `State` class kept in
       `ship.getCustomData()` (or `member` data for campaign methods), read `State s = state(ship)` at the top of each
       method that takes the ship, `this.x` -> `s.x`. Fixer applies only when every written field is used solely inside
       methods that receive a `ShipAPI`/`FleetMemberAPI`, there are no static writers, and the compiled diff is state
       plumbing only; jar classes go through `patch-jar-class`. SEEKER's organic hull and Nightcross's plasma
       aggregator are the test cases.
       **Done 2026-10-04** for loose scripts: `bridgeforge/hullmod_state.py` `port_hullmod_state` (single-field
       private declarations; refuses a method without exactly one `ShipAPI` parameter, a shadowing local, a use outside
       a method), the `hullmod-instance-state` fixer, and `port-hullmod-state SOURCE --field F --out PATH` for jar
       sources (then `patch-jar-class --allow-removed F`). A ported fixture compiles under RC8's Janino. Tests:
       `HullModInstanceStateFixerTests`, `PortHullModStateCommandTests`. Not yet: `FleetMemberAPI` campaign methods.
    2. **Entity-lookup "use the variable" fixer** (`hard-coded-campaign-entity-reference`, the next largest: 45). The
       accepted agent fix in Hegemony, Scion, Mayorate, Gensoukyou, Traverser, Mountain-and-Sea and The Nomads was the
       same: `system.getEntityById("x")` in the method that created `"x"` with `PlanetAPI v = system.initStar/addPlanet(
       "x", ...)` -> `v`. Deterministic when exactly one local in the same method was created with that literal id
       (or a String local holding it, as Traverser's `systemName`).
    3. **Percent/multiplier fixer** (`suspicious-percent-multiplier`): `modifyPercent(id, 1f - P * 0.01f)` beside a
       `modifyMult(id, 1f - P * 0.01f)` of the same constant -> `modifyPercent(id, -P)`. Tore-Up-Plenty and Batavia (4
       hull mods), each confirmed against its description. Applied only with that sibling multiplier present.
    4. **CSV repairs:** unescaped inner quotes (`the "little" brother` -> `""little""`, New Galactic Order) when
       doubling them makes every row fit the header; and mixed-layout files (ship_systems rows from a newer header)
       rewritten by column name into RC8's header when the wide rows match RC8's positions up to the last filled
       column. Both done by hand 2026-10-02.
    5. **Missing-dependency for compile errors:** a `loose-script-compile-error` whose missing package belongs to a
       known library (GraphicsLib `org.dark.shaders`, LazyLib, MagicLib) declares the library instead of an agent
       rewriting the code (Mountain-and-Sea's agent used reflection, which the script sandbox forbids).
    6. **Own-system lookups are notes:** `hard-coded-campaign-system-reference` for a system the same mod creates with
       `createStarSystem("X")` is SAFE (Qualljom's Holotis, accepted by hand).
       **Done 2026-10-04:** a system or entity lookup whose own file creates the id is SAFE with evidence
       `created-in-same-file`, a note in revive and skipped by the lookup-guard fixer. `addPlanet`/`initStar` now count
       as creations (javap: id is the first argument), so Sylphon's Nym and Hiver's Kiztac read as local. Tests:
       `test_scanner_attributes_local_campaign_identifiers`, `test_scanner_counts_add_planet_and_init_star_as_local_entities`.
    7. **Agent-result triage before review:** flag automatically what was rejected by hand this week: reflection
       (`java.lang.reflect`, sandbox-forbidden), a method body emptied or turned into a no-op, `this` hidden behind a
       local to dodge `campaign-memory-live-object` (ICE), live objects moved to a static map (Void-Tec TimerBar),
       imports of nested classes at the wrong path (Polaris). Add to `escalation_review.FLAGS`.
       **Done 2026-10-04:** flags `reflection`, `static-map-state`, `this-hidden-in-local`, `nested-class-import` and
       `method-emptied` (a method declaration with an empty body, or a net deletion ending in a bare return; an empty
       `catch` stays `exception-swallowed`). Review prompts only. Test: `test_patterns_rejected_by_hand_are_flagged`.
    8. **Batch runner as a command:** `escalation batch MODS... [--max-minutes 55]` with the rules the scratch script
       learned: stop at the first usage-limit message from this run only, skip a mod whose workspace lock is held,
       kill the agent tree on timeout, stop before the hour cap and print what is left so the next run resumes.
       Replaces `agent_batch*.sh`.
    9. **`escalation apply --patch-class` by default** for an attempt that edits jar sources (src/, jars/src/, a
       mod's own source tree), with the new class diff shown first; refuse only when the source is not faithful.
    10. **Supersession by content, not id:** a same-id 0.98 release supersedes only when it keeps most of the old
        content ids (ships, weapons, hull mods); otherwise NEWER_DIFFERENT for a person (SEEKER 0.2 was closed by
        mistake; only 5 of its 37 ships are in 0.6.6). **Done 2026-10-04:** `supersession.content_overlap` compares
        `kind:id` rows of ship_data, weapon_data and hull_mods; under 50% of ours kept is `NEWER_DIFFERENT`; an
        unreadable side keeps the verdict with `content_overlap: null`. Rechecked the 101 SUPERSEDED verdicts in the
        queue's SUPERSESSION.json: 71 confirmed, 27 unreadable (no content CSVs), 3 NEWER_DIFFERENT: SEEKER (22 of 152,
        14%), Cebby-Ship-Pack (0 of 5) and prv-Starworks (131 of 267, 49%), all three for the owner to decide.
        Test: `ContentOverlapTests`.
    11. **Ready mods to live-test groups automatically:** `probe-group plan` over `ready-list` output, with groups sized
        by mod weight and conflicts (same id, same vanilla files overridden), so one rig session tests many mods.
    12. **`escalation accept WORKSPACE ID[:FILE_PART]... --reason`** (the scratch script used for six mods on
        2026-10-04): packet findings into the mod's baseline, the reason and keys into `ESCALATION_REVIEW.md`; a
        selector matching nothing is an error. **Done 2026-10-04.** Test: `test_accept_in_mod_by_finding_and_file_part`.
    13. **`nexerelin-corvus-mode-import` check and fixer:** a loose script importing `exerelin.campaign.SectorManager`
        only for `getCorvusMode()` fails Janino without Nexerelin (Hiver Swarm). Rewritten to
        `!getBoolean("$nex_randomSector")`, which Nexerelin 0.12.2d's `ExerelinNewGameSetup` writes (javap and bundled
        source). Skipped when the mod requires Nexerelin. **Done 2026-10-04.** Tests: `NexerelinCorvusModeImportTests`.
        Still open: confirm live that the entry point runs before mod `onNewGame` (Hiver Swarm in a Nex random sector).
    14. **Spawned-ship captain fixer:** `spawnShipOrWing(id, loc, facing)` for a ship -> the overload with a captain from
        `createPerson()` + `setPersonality(STEADY)` (RC8's `ChiralFigmentStats`); the check then treats that overload as
        guarded instead of flagging every literal id (Traverser's turrets, by hand 2026-10-04). **Done 2026-10-04:**
        `_fix_spawned_ship_captain` (loose scripts; 3-arg calls get `0f`, 4-arg keep their burn) adds a `bfSpawnCaptain()`
        helper; the check skips 5-arg calls (`_call_argument_count`). Fixer output compiles under RC8's Janino. Test:
        `SpawnedShipCaptainFixerTests`.
    15. **Orbit-period check follows constants:** when every caller of the helper passes a constant radius, compute the
        period and drop the finding (ORA's six derelicts, 250-425 days). Deferred 2026-10-04: proving the formula stays
        positive for every caller needs expression evaluation, not a pattern; a near-miss would hide a save crash.
    16. **Missing-comma JSON repair:** a list item followed by another item on the next line gets a comma, only when that
        is the parse error and the file then parses (Hiigaran's `polaris.json`). **Done 2026-10-04:** new finding
        `json-missing-comma` (REVIEW, replaces `unverified-json-syntax` only when the repair parses; org.json's
        "Expected a ',' or ']'" / "or '}'" read from RC8's json.jar) and its fixer. On Hiigaran's original it picks
        line 16, the hand fix. Tests: `JsonMissingCommaTests`.
    17. **External memory keys, fewer false positives:** a Nexerelin key only written, or read under an
        `isModEnabled("nexerelin")` guard, is a note (Kadur, Hiver). **Done 2026-10-04:** SAFE with evidence
        `written-or-guarded` (`_external_memory_keys_harmless`). Test: `test_external_memory_key_written_or_guarded_is_safe`.
    18. **Stray work archives move automatically:** `shippable-work-file` for a `.rar`/`.zip`/`.7z` in the mod root moves
        it to `scratch/moved-work-files/` (Hiver's `Replacement Ships.rar`). **Done 2026-10-04:** the fixer already
        existed; it kept the archive because Hiver's root README named it. Root `.txt`/`.md` no longer count as
        references. Test: `test_moves_unreferenced_work_files_to_scratch_and_keeps_referenced_ones`.
    19. **Missing rig providers:** `probe-group plan` copies (or names the command to copy) a ready provider into the rig
        when a mod is unplaced only for it (SCY, YunruCore, ORA).
    22. **Wing OP cost fixer and legacy wing_data layout** (owner ruling 2026-10-04: 36 blank wing costs in 7 mods set
        to the nearest vanilla wing's by hand-run script; 6 of the 7 files were the pre-0.8 layout with no `op cost`
        column at all). Two parts:
        1. `wing-op-cost-blank` fixer, approval-gated (the value is a comparison, not a conversion): for a wing a
           variant or a faction's autofit can fit, set the cost of the nearest vanilla RC8 wing with the same role
           (nearest fleet pts, then fighter count). Built-in or never-fitted wings stay notes. Edit only that cell
           (quote-aware raw edit, like the scratch script); write the table it used into the review sheet.
        2. `wing-data-legacy-layout` check and fixer: a header without `tags`, `tier`, `rarity`, `op cost`, `range`,
           `attackRunRange` or `attackPositionOffset` is the pre-0.8 layout. Rewrite rows into RC8's header by column
           name (as done for New Galactic Order's ship_systems). The missing values need the same nearest-vanilla
           comparison and approval; until then only `op cost` is filled. Needs live evidence first: what RC8 does with
           a wing that has no `range`/`attackRunRange` (fighters that never leave, or vanilla defaults).
        **Part 1 done 2026-10-04:** `_fix_wing_op_cost_blank` (tier `input`: needs the owner's approval; needs
        `--vanilla-core`; only wings a variant fits or a faction knows; appends the column to a pre-0.8 file). Test:
        `WingOpCostFixerTests`. Same day: `builtin-wing-is-hullmod` check and fixer (a hull mod id under
        `builtInWings`, The Nomads' nom_komodo_p listed vanilla `advancedcore` there; the key is renamed when every
        entry is a hull mod and there is no builtInMods yet; test `BuiltinWingIsHullmodTests`), and fresh fixer scans
        now pass the caller's vanilla core. `probe-group plan --provider-source` (default: the real install's mods/ and
        the 0.98 modpack) stages providers the queue lacks, copying from them and never writing there
        (`OutsideProviderTests`).
    23. **Content references only from files the game loads:** `content-reference-unresolved` read every `.variant`
        under `data/`, so KIND STRANGER Disassemble-Reassemble's 14 missing `dara_` ids all came from the author's
        `data/!TEMP_DISABLED_VARIANTS/`, which RC8 never loads (accepted by hand 2026-10-04). Limit variants to
        `data/variants/**` (and missions' own), hulls and skins to `data/hulls/**`, after confirming RC8's load paths
        with evidence (a live run with a variant parked outside `data/variants/`). Same day, provider staging gained
        the Ironclads archive as a source, offering only copies whose gameVersion is 0.98 and the newest version.
    24. **Renamed ids across versions:** `renamed-ids OLD_COPY NEW_COPY kind:id...` (read-only): RENAMED when the newer copy
        has one entry with the same display name and description, SIMILAR when only a name word is shared (never
        enough to remap), reading an old copy's alternate tables such as ship_data_old.csv. **Done 2026-10-04.** It
        reproduces both hand cases: Xhan Empire 3.0.1's `XHAN_targeting_mast` -> `XHAN_TargetingMast` (remapped in the
        Maelstrom Xhan expansion), and Traverser's `TDB_chuan_yue_xue_zhe` (only SIMILAR: the Cold Sky Scholar is an
        unmanned redesign, so the hull was retired). Test: `tests/test_renamed_ids.py`. Next: a remap fixer for
        RENAMED results, approval-gated.
    25. **Declared dependencies outside the queue supply content and art.** **Done 2026-10-04:**
        `scanner._dependency_roots` (every copy of each declared dependency across the provider roots, not one per
        id), used by `content-reference-unresolved` (union of ids) and `asset-reference-missing` (RC8 resolves graphics
        across enabled mods); `revive` adds `<queue>/PROVIDER_SOURCES.json` sources (opt-in; `In operation` lists the
        real install's mods/ and the 0.98 modpack, never the mostly-0.95 Ironclads archive). By hand the same day this
        cleared 16 addons' content and 6 mods' art. Tests: `test_a_declared_dependency_supplies_art_and_content`,
        `OutsideProviderSourcesTests`.
    26. **`find-providers` command:** the 2026-10-04 lookup scripts as one read-only command: missing ids and art of
        a mod looked up across the install, modpack, queue and corpus index (zips and 7z), with version, gameVersion and
        "defined" versus "only referenced".
    27. **`escalation decisions` command:** the decision sheet for the commonest blockers (DECISIONS_2026-10-04.md),
        with the evidence each recommendation rests on (built-in or fitted wings, fatal or silent missing content,
        unused referring files, CJK size).
    28. **`translate-batch` command:** the agent translation pipeline (export, 120-entry chunks, one agent per chunk,
        strict verify: every entry filled, no CJK left, markers kept; apply only when all pass; checkpointed).
        **Done 2026-10-04:** `bridgeforge/translate_batch.py`, `translate-batch MOD (--out COPY | --in-place) [--agent CMD]
        [--reference EN_COPY] [--record REC]`: export, prefill, chunks to the agent (one chunk file each, prompt on stdin),
        `verify_chunk` (ids/sources unchanged, filled, no CJK, placeholders as apply counts them), one retry, glossary
        carried between chunks, apply and translate-check; checkpointed and stops at a usage limit. In
        LONG_RUNNING_COMMANDS. Tests: `tests/test_translate_batch.py`.
    29. **Supersession across multi-mod packs:** read every root inside a pack zip (the Yunru pack held 9 modules and
        superseded YunruCore and Old School Expansion at 100% content overlap, found by hand).
    30. **References from files RC8 never loads are notes** (extends 34.23): a `.ship` or `.wpn` with no ship_data /
        weapon_data row that nothing mounts (YunruCore's 36 addon hull files, Stardust's smc_leftarm_mech, Terraformers'
        7 unfinished decorative weapons, all accepted by hand 2026-10-04), an unregistered `.faction`
        (Traverser's TDB_CN), variants outside data/variants. Needs RC8 evidence that an unregistered spec file loads
        nothing.
    31. **Remap fixer for `renamed-ids` RENAMED results**, approval-gated (Xhan's targeting mast, by hand).
    32. **Definitions index:** a derived table in bridgeforge-state (kind, id or asset path, mod id, version,
        gameVersion, source, file) built from the corpus index, so "who defines X / ships Y" is one query. Small next to
        the corpus index (which holds full file text); feeds 34.26 and 34.24.
    33. **Translation false positives and gaps found by the 2026-10-04 batch:** (a) `player-text-non-english` counted
        CJK in trailing `#` comments of JSON-like files as player text: all 8,781 of Mirfak Parcel Service's characters
        are comments (`"displayName":"Mirfak Parcel Service",  # 显示名称`) and translate-export rightly finds 0 units.
        Count only what translate-export would export. (b) **Done:** translate-export skipped nothing in CSV rows the
        game ignores (first cell starting `#`); FSF's `rules.csv` comment rows came back blank from the agent and blocked
        the mod. Test: `CommentedCsvRowTests`. Same day: intake retries a Windows PermissionError on the final rename
        (the 9-mod Yunru pack's freshly extracted tree, held open briefly; failed twice before).
    34. **Live crash lessons, 2026-10-04 (owner crash logs in Downloads):** (a) DNEEP crashed on load:
        `setIndustryOnPlanet(SystemName, ...)` dereferenced `getStarSystem(SystemName)` for vanilla systems a
        random sector lacks; the literal-name checks never saw a variable. **Done:** `campaign-lookup-dereferenced-unguarded`
        (a getStarSystem/getEntityById on a variable used directly with no null check earlier in the method) and its
        fixer (guard and return, only when the lookup is the first statement of a void method; anything else refused).
        It reproduces the hand fix on the archived DNEEP; DNEEP is now +bf.1. Test: `UnguardedVariableLookupTests`.
        (b) RogueSynth's tooltip threw NoSuchMethodError on `addImageWithText(F)V`: `jar-linkage-unresolved` had found
        it and the queue copy was relinked (+bf.2), but Done/ still held +bf.1, as did Arkgneisis, Megastructures Tab
        and Slightly Better Tech Mining. **Done:** `done-audit` (re-scans every Done/ mod: STALE when the queue copy's
        shipped files differ from the archive, plus crash-class and MANUAL/UNKNOWN findings the baseline does not
        accept; Done/DONE_AUDIT.md; long-running). Test: `tests/test_done_audit.py`. The five were re-archived (old
        archives kept in Done/_previous/<mod>-<version>; a live waiver recorded for each narrow fix); the shipped-copy
        audit compares against `scratch/original-extracted/` when original/ keeps only zips (Arkgneisis). Next: an
        `archive --replace` that does the _previous move itself, and a Done/ check after every bump-version.
    35. **Suspect initStar/addPlanet arguments** (owner request 2026-10-04). Zorg18's archived +bf.4 carried two bugs
        from the modpack port it was built from: the 0.6 call `initStar("star_zorg", 200f, 10000, -10000)` (last two the
        hyperspace location in 0.6) became RC8 `initStar(id, type, 200f, -10000)`, a corona of -10000, and Zeta I's
        `addPlanet(star, "Zeta I", "zorg_planet", 0, 100, 5000, 100)` lost its radius, shifting to `0, 0, 100, 5000`
        (a radius-0 planet orbiting at 100). Zeta II was ported right. **Done:** `bridgeforge/procgen_args.py` and
        `procgen-call-argument-suspect` (tier decision: the intended numbers need a person), from sources and, with a
        JDK, jar classes via javap (float pushes tracked to RC8's signatures; only literals judged: radius <= 0,
        corona < 0, orbitRadius < 0, orbitDays <= 0). Flags both calls in the archived jar and the modpack source; the
        owner's rebuild is clean. In `done-audit`'s crash class. Tests: `tests/test_procgen_args.py`.
    36. **Settings keys no settings.json defines** (owner crash log 2026-10-04): Exigency 0.8's
        `ExipiratedAvestaSubmarketPlugin` read `getFloat("blackMarketMinSupplies")` (and ...MinFuel, ...MinMarines):
        vanilla had them in 0.8.1a (50, 50, 30) and dropped them by 0.9a; Exigency never defined them; RC8 threw
        `JSONException` when Starpocalypse refreshed the Avesta market. Fixed in the jar (patch-jar-class: three
        getFloat -> `getSettingsJSON().optDouble(key, 0.8.1a value)`), Exigency 0.8 is +bf.1, re-archived. **Done:**
        `bridgeforge/settings_keys.py` and `settings-key-missing` (tier code: the right default needs the key's history),
        literal reads in sources and, with a JDK, jar classes via javap, against RC8's, the mod's and its declared
        dependencies' settings.json. Flags the three in the old Exigency jar, none in +bf.1. In `done-audit`'s crash
        class. Tests: `tests/test_settings_keys.py`. Same day: Zorg18 V18+bf.6 (Unimatrix size 10, owner request).
    37. **Faction blueprint tags that match nothing** (owner report 2026-10-04: Exigency's ships could not be bought).
        exigency.faction knew `knownShips/priorityShips/knownWeapons {tags: [exigency_bp]}` and exipirated.faction
        `exipirated_bp`, but no hull or weapon carried those tags (only Exigency's wings did), so neither faction knew
        its own ships or weapons: none in its markets, none from raids. Author's latent bug (original identical, no
        runtime registration). Fixed: Exigency's 7 ship hulls and 18 sellable weapons tagged exigency_bp (SYSTEM-hinted
        and fighter-only weapons and fighter hulls left out), Exipirated's 7 hulls exipirated_bp; Exipirated's
        knownWeapons left as authored (its only own weapons are SYSTEM). Exigency 0.8 is +bf.2, re-archived.
        **Done:** `faction-known-tag-unmatched` (tier decision: which items belong to the tag is a judgement), against
        the mod's, RC8's and declared dependencies' ship/weapon/wing tags; in `done-audit`. Test: `FactionKnownTagTests`.
        Same day, `done-audit` checks packaging too (owner question: are all mods correctly packaged?): the mod's
        `<folder>-<version>.zip` exists, names the version its mod_info.json declares, holds no entry twice
        (case-insensitive) and the same files as the folder. Test: `PackagingTests`.
    38. **Hooks only one mod can own** (owner question 2026-10-04: will AoTD conflict with revived mods?). AoTD sets
        six RC8 industries' plugins at load (javap, `IndustrySpecAPI.setPluginClass`): population (Theory of Toolbox),
        heavyindustry and orbitalworks (Vaults of Knowledge), patrolhq, militarybase, highcommand (Seats of Power);
        Toolbox also replaces the economy object (`AoTDEconomy`, reflection). DNEEP's industries.csv population plugin
        is therefore silently dropped with Toolbox; Adjusted Sector's new-game plugins collide with Nexerelin, Random
        Assortment of Things and Wide Horizons (same settings keys); Exigency's and Omega-Trauma's fleet spawners create
        and remove a market per fleet, which Toolbox turns into a structural economy refresh (RC8's FleetFactoryV3
        handles `source = null` itself). **Done:** `industry-plugin-override` (names the AoTD mod when it is one of the
        six), `new-game-plugin-override`, `temporary-market-fleet-source`, all REVIEW; `done-audit` lists them as
        compatibility risks without changing an archive's status; compatibility sections in the DNEEP, Adjusted Sector
        and Slightly Better Tech Mining archive notes. Test: `tests/test_shared_hooks.py`. Fixer (tier auto) for
        `temporary-market-fleet-source`: drops `removeMarket` of a market that never entered the economy (RC8-22).
    39. [x] **Closed 2026-10-12, not built (owner agreed).** Population-delta fixer (owner request 2026-10-04): an industries.csv override of a vanilla industry
        whose class is RC8's source plus added `demand()`/`supply()` calls and stability effects becomes a market
        condition adding them through `Industry.getDemand/getSupply` (RC8's ResourceDepositsCondition pattern); any
        other change is MANUAL. Proven first by hand on DNEEP (`PopulationNeedsDNEEP`) with AoTD on the rig.
        **Why closed:** of about 300 working copies only four override a vanilla industry in `industries.csv` (Better Colonies and
        Slightly Better Tech Mining and SBTM on `techmining`, Cryosleeper 2 on `cryorevival`), and none is the population-needs shape;
        DNEEP was done by hand and proved live (probe 0.2.25 supply checks, 2026-10-11), and the atlas rules
        `ATLAS-READS-REPLACED` and `ATLAS-RUNTIME-SUPPLY` flag the conflict. A fixer for one case costs more than the hand fix it
        saves. Revisit if a third mod with an added `demand()`/`supply()` industry override arrives.
    40. [x] **Crew-tier mapper** (Ironclads, 2026-10-04): `CargoAPI.CrewXPLevel` (removed in RC8) -> one crew; reads of
        REGULAR become `getCrew()`, other tiers 0 (tier sums stay right), add/removeCrew drop the tier. Owner decision
        "one crew". Done by hand in 5 Ironclads files.
    41. [x] **Signature rewrites with exact RC8 equivalents** (Ironclads, javap 2026-10-04): `EconomyAPI.addMarket(m)`
        -> `addMarket(m, true)` (vanilla passes true); `TileParams(..., 7 args)` -> RC8's 8th `name` argument;
        `RepActionEnvelope(action, param, CommMessageAPI, boolean)` -> `(action, param, message, null, boolean)`;
        `MarketAPI.addCondition(id, boolean, Object)` -> `addCondition(id, Object)`.
    42. [x] **Replaced core file drops RC8 rows** (check): a `replace` entry for an RC8 CSV the mod does not fully
        restate (Ironclads replaced commodities.csv and market_conditions.csv, losing `crew`, AI cores and every
        deposit condition RC8's own code adds). Nothing flagged it.
    43. [x] **Bundled copy of a retired vanilla class** (check): a mod class in a `com.fs.starfarer.api` package that
        RC8 no longer ships and nothing in the mod starts (Ironclads' `SystemBountyEvent` was vanilla 0.7.2's,
        unchanged; RC8 replaced it with SystemBountyIntel). `vanilla-duplicated-classes` compares only against
        classes RC8 still has.
        **Done 2026-10-05 (40-43):** 40 in `removed-api-call` (the scanner pattern now matches `getCrew(CrewXPLevel.X)`;
        REGULAR -> `getCrew()`, other tiers `getCrew() * 0`), test `test_tier_reads_become_one_crew`; 41 as
        `rc8-signature-changed` (check + auto fixer, `bridgeforge/signature_rewrites.py`; RepActionEnvelope left out: RC8
        also has a 4-argument form with another third type); 42 as `replace-drops-rc8-entries` (it also found Ironclads'
        vanilla faction copies lacking knownHullMods and doctrine); 43 as `retired-vanilla-class-copy` (classes an
        older reference install shipped and RC8 does not). Tests: `tests/test_signature_rewrites.py`.
    46. [x] **Probe: gameplay sweeps, not just load** (owner request 2026-10-05). (a) class sweep: load every class of
        each enabled mod jar and resolve its methods (catches NoSuchMethodError at the menu, RogueSynth's tooltip);
        (b) campaign smoke: after a new game and ~30 days, per faction known ships/weapons, market count, fleets alive,
        ships for sale (Exigency's unbuyable ships and missing fleets read as zeros); (c) mission sweep: each listed
        mission's fleets resolve; (d) hull mod tooltip and refit render sweep.
    47. [x] **bundled-source-stale** (check): compile the mod's bundled jar source and compare classes/members with the
        jar; when they differ, checks judge from the jar (Grytpype's hull mods, Tritachyon's PeachGarden, 2026-10-05).
    48. [x] **False-positive accounting**: baseline acceptances carry their finding id and reason; `finding-stats`
        ranks checks by how often findings were accepted as harmless; each acceptance pattern becomes a test.
    49. [x] **Faster long runs**: a checkpoint resumes when only the workspace list grew (the 2026-10-04 queue pass
        restarted from 0 because two workspaces were added); scans cached by content hash; parallel workers.
    50. [x] **mods-compat**: read-only scan of the owner's real mods folder for shared hooks (industry plugins,
        new-game generators, replaced core files, shadowed vanilla scripts) across every installed mod.
    51. [x] **Check guard patterns**: persistent-data flags (SLPC's CLASS_MARK) and nested `src/src` roots (Artefact)
        in system-generation-unguarded.
    52. [x] **Commit helper**: stage tracked docs only (a `git add docs/*.md` on gitignored files broke a commit
        chain, 2026-10-04).
    53. [x] **Crash-log triage outside the rig**: take a pasted crash log, find the owning mod and class in the
        owner's real mods folder (the EPTA crash took a manual search, 2026-10-04).
        **Done 2026-10-05 (44, 46-53):** 44 `decompile-jar` (Vineflower -> source tree; `rebuild-jar` already
        compiled, jarred and diffed). 46 probe 0.2.12: `mission-fleets` (every fleet member the missions name resolves),
        `class-sweep` (each top-level class of the target jar loads through the game's script class loader; the
        sandbox forbids reflection, so no member resolution), `hullmod-descriptions` (getDescriptionParam at each hull
        size for the target mod's hull mods; a full tooltip needs the UI), and `faction-known-lists` warns when a mod
        faction knows none of the mod's own ships (Exigency's base_bp-only case); probe-config writes
        `mission_fleets` and `class_sweep`. Live verification with the next live test. 47 `bundled-source-stale`. 48
        `baseline-stats`. 49 checkpoint resume on a grown list and `revive-queue --jobs N` (scan caching deferred:
        results also depend on the BridgeForge version). 50 `mods-compat` (on the owner's install: AI-Retrofit,
        Shadowyards and IndEvo against AoTD, two LevelupPluginImpl shadows). 51 persistent-data flags and qualified
        generator calls. 52 `docs-index --stage`. 53 `log-triage --mods-dir` indexes loose scripts and names crash
        classes in no installed mod (the EPTA report). Tests: test_decompile, test_probe_config, test_mods_compat,
        test_baseline_stats, test_progress, test_revive_queue, test_signature_rewrites.
    44. [x] **Whole-jar rebuild command**: decompile (Vineflower) -> source tree -> javac --release 17 against RC8 ->
        jar, with a class diff against the original (Ironclads' IroncladsEcon.jar was rebuilt by hand).
    45. [ ] **0.7 economy translators** (deferred, measured 2026-10-12: the trigger is not met) (decision tier, once a second 0.7 economy mod arrives): Ironclads'
        `IroncladsMarkets` condition->industry table and its commodity-row conversion (nearest RC8 analogue's
        0.7->RC8 price ratio and RC8-only columns), generalised.
        **Measured 2026-10-12:** of 16 queue mods declared for 0.6 to 0.8 only AI-War (0.7.2a, 2 to 3 line economy files) and
        FlowerGod (0.8.1a, already archived) carry economy files; no second Ironclads-style table exists. Count the owner's
        unprocessed 0.7-era mods before building.
    21. **Repeat-work report** (owner recommendation 2026-10-04): read-only, local to the corpus. Aggregate verified
        escalation outcomes by finding id across every workspace's `ledger.jsonl` and review sheets: how often the same
        edit pattern was accepted, rejected or done by hand, with links to before/after evidence. It ranks the next
        fixer from real work and never promotes a REVIEW finding to SAFE. Not for CI (private game and mod inputs).
    **Owner order 2026-10-04 for what is left of item 34:** 34.7 agent-result triage and 34.10 supersession by
    content first (both prevent costly wrong decisions), then 34.2 entity-lookup fixer (throughput), 34.11 groups from
    `ready-list`, 34.3 the narrow percent fixer (strict evidence: a matching `modifyMult` and the description), 34.21.
    20. **Commented-out mission fleet lines:** `mission-local-fleet-reference-missing` matched a `//` line (Scy-Nation's
        `SCY_11_soldierOfFortune`, MissionDefinition.java:52, 2026-10-04); blank comments first, as other source checks do.
        **Done 2026-10-04.** Test: `test_commented_out_mission_fleet_line_is_not_a_reference`.
35. **Plan: features shared with the sister programs, both ways (owner request 2026-10-04).** SPW
    (`Documents/Starsector project workbench`, `Exxec/SPW`), Project Go (`Documents/Starsector project go`) and
    Salvor (`Documents/Project Salvor`) stay separate programs with no shared runtime code; ports are copies with
    their own tests, or versioned JSON files one writes and the other reads. Project Go's and SPW's own
    interchange designs (`docs/SISTER_REPO_INTEROPERABILITY_DESIGN.md`, `docs/SISTER_REPO_INTERCHANGE_DESIGN.md`,
    2026-09-27) are the contracts to follow.

    From BridgeForge to the others:
    1. **Salvor reads per-ship state keys:** `<HullMod>_bfState` / `ART_organicHull_state` in ship custom data are
       BridgeForge's (34.1); Salvor's diagnose names them instead of reporting unknown objects, and warns when a
       save from before the patch still holds the mod's old field values.
    2. **Salvor reads the sector mode:** `$nex_randomSector` / `$nex_corvusMode` in sector memory decide whether a
       missing Corvus system is a fault (vanilla sector) or expected (Nexerelin random sector) before any removal plan.
    3. **Salvor uses `progress.py` and checkpoints** for save folders and large saves (the 2026-09-27 rule).
    4. **Salvor records "keep as is" rulings** with a reason, as `escalation accept` does, so a later run does not
       flag them again.
    5. **SPW gets the RC8 org.json leniency rules:** BridgeForge's `_parse_json` (javap-backed, see
       [[bridgeforge-json-leniency-gap]]) plus the missing-comma repair (34.16) and the early-closing root check
       (`json-content-after-root`, Holy Covenant's stray brace), so both tools agree on what RC8 loads.
    6. **SPW compiles loose scripts with RC8's Janino** before it writes one (`compile_check.janino_compile`).
    7. **Project Go gets BridgeForge's untranslated-text list:** `player-text-non-english` / `non-ascii-identifier`
       file+key evidence as an input that names what its extractor skipped (it missed 861 strings on Nightcross,
       108 units on FlowerGod). Fits Project Go's own P7 (`docs/BRIDGEFORGE_METHOD_CONVERSION.md`).
    8. **Project Go path wrapper:** copy to an ASCII, space-free path, run `ssmt-cli`, copy back; removes the
       non-ASCII path and `JAVA_HOME`-with-space launcher failures.
    9. **One evidence-row format for all three:** `docs/RC8_BEHAVIOUR.md` (one row per live-proven fact, cited by id)
       adopted by Salvor for save-format facts and by SPW for runtime facts.

    From the others to BridgeForge:
    10. **hs_err crash logs in `log-triage`** (SPW `crash_log.find_crash_logs/parse_crash_log`): a JVM crash
        (`hs_err_pid*.log`, one sits in this checkout today) is triaged with the problematic frame, the Java frames
        that belong to a mod (SPW `jar_ownership`), and memory figures, beside the game log and `windows.txt`.
    11. **Rig core integrity** (SPW `core_integrity.classify_core_integrity`): before `bf-test launch`, hash the rig's
        `starsector-core` against a recorded RC8 baseline, so "the rig matches vanilla RC8" is checked, not assumed.
    12. **SPW performance export into `spw_bridge.py`:** read SPW's versioned `performance-report.json` and mod
        identity inventory instead of guessed key aliases; keep old imports as unverified. The inventory's duplicate
        ids, renamed-disabled `mod_info`, and stale `enabled_mods.json` feed `probe-group` and the rig preflight.
    13. **Translated-clone audit** (Project Go `PatchBuilder`'s `TranslatedCloneAudit`): before `archive`/`release`,
        compare every file of the shipped copy to `original/`; a file may differ only when a recorded fix or
        translation explains it. Catches stray edits and lost files that today only a probe run would show.
    14. **Glossary for translations** (Project Go `GLOSSARY_FORMAT.md`, schema v1): `translate-apply` uses a shared
        term list so a faction, ship or weapon name is translated the same way across files and mods.
    15. **Project Go's standard CSV text columns** (`StandardCsvSchemas`): which columns of which vanilla CSVs are
        player-visible text, so `player-text-non-english` and `translate-export` check exactly those columns.
    16. **Project Go coverage export into the translation review:** join its `localization-coverage.json` on exact
        source hash and path; a mismatch blocks a "fully translated" claim.
    17. **Salvor's save fingerprint** (SPW `save_fingerprint`): `save-baseline` records which mods and versions a save
        was made with, so a probe or a Salvor repair can say a save and a rig do not match before loading it.

36. **Plan: live-test trust (owner priorities 2026-10-04).** Design: `docs/LIVE_TEST_TRUST_DESIGN.md`. Order: 2, 4, 1,
    3, 5, then 6-11.
    **Done 2026-10-04** (all eleven): `probe_group._providers_for`/`stage_providers` and `install --stage-providers`
    (36.1, `ProviderStagingTests`); `rig_doctor._check_core_integrity` with the build read from `StarfarerLauncher`
    and `bf-test.ps1 launch` refusing on a rig-doctor FAIL (36.2, `RigCoreIntegrityTests`, `RigCoreBuildTests`);
    `live_trust.audit_shipped`, `audit-shipped`, `audit-explain` (36.3, `ShippedAuditTests`); `crash_log.py`, the
    launch copying `hs_err_pid*.log` beside the log, crashes attributed in `group_report` (36.4, `tests/test_crash_log.py`);
    `live_trust.save_made_with`/`compare_made_with`, `made_with` in save baselines (36.5, `SaveMadeWithTests`);
    `write_run_record` from `probe-group record` into `<queue>/_live/` (36.6), `live_status` (36.7, `RunRecordTests`),
    `probe-group bisect` (36.8, `BisectTests`), the known-noise check in the run record (36.9), `rig_fingerprint` in
    `log-triage` (36.10), `archive_gate` in `archive` and `record --archive` (36.11, `ArchiveGateTests`).
    Left for a local session: record the RC8 core baseline once (`rig-doctor --write-core-baseline`). Mods validated
    before 2026-10-04 read `UNKNOWN_BUILD`; archive them after a re-run, or with `audit-explain --live --reason`.
    1. **Missing rig providers staged by `probe-group`** (supersedes 34.19): find the ready workspace that declares the
       missing id, print or perform the `copy-drift --sync`, verify id, version and zero drift before the probe runs.
    2. **Core integrity in the launch preflight** (35.11): `rig-doctor` `core_integrity` **built 2026-10-04**
       (`_check_core_integrity`, `--write-core-baseline`; test `RigCoreIntegrityTests`). Still: record the RC8
       baseline with its build, run it from `bf-test.ps1 launch` and stop on FAIL, cite the baseline in results.
    3. **Shipped-copy audit before archive/release** (35.13): every difference from `original/` explained by a
       recorded change, else the archive fails; `audit-explain` records a person's explanation.
    4. **JVM crash logs in `log-triage`** (35.10): **built 2026-10-04** (`bridgeforge/crash_log.py` from SPW; FATAL
       `JVM crash (hs_err)` with mod-owned frames; tests `tests/test_crash_log.py`). Still: `bf-test.ps1` copies the
       hs_err to `<TESTID>.hs_err.log`; time match where creation time is unknown; `probe-group record` uses it.
    5. **Save baselines bound to their mod set** (35.17): `made_with` from `descriptor.xml` plus rig versions/jar
       hashes; a mismatch makes a comparison REVIEW or UNKNOWN, never a pass. Shared reader with Salvor.
    6. **One run record per live test** (`reports/live/<TESTID>.json`) joining inputs and outputs.
    7. **Stale-result detection:** a live result holds only while the shipped hash matches its run record.
    8. **`probe-group bisect N`:** split a failed group into two dependency-closed groups.
    9. **Known-noise budget per group:** a jump in KNOWN-NOISE between runs of a group is REVIEW.
    10. **Rig fingerprint in triage output:** enabled mod set and core baseline id printed with the result.
    11. **Archive gate:** refuse a stale (7) or unaudited (3) mod unless the owner records why.

## Post-1.0 research and gated automation

### Deferred migration findings from the 0.98a corpus audit

These are scanner-supported, review-gated migration tracks. They are intentionally
not automatic fixes: the audit establishes candidates, not authorial intent.

1. **Runtime placeholders:** classify reachable `UnsupportedOperationException`
   and equivalent stub paths, then require a source-level replacement and compile
   validation before proposing a migration.
2. **Configured class integrity:** reconcile configured plugin/script class names
   with the packaged JAR and source layout; distinguish obsolete configuration from
   an accidentally omitted class.
3. **Campaign spawn registration:** inspect disabled or commented-out registration
   paths and propose restoration only after validating lifecycle timing, campaign
   conditions, and duplicate-spawn safeguards.
4. **Target-bytecode compatibility:** detect classes beyond the selected Java/
   Starsector profile and provide a working-copy rebuild plan using the appropriate
   source and dependency evidence.
5. **Campaign-state coupling:** review persisted live objects, external memory
   keys, and hard-coded system/entity identifiers; propose resilient lookup or
   compatibility strategies only where the mod's intended content contract is
   evidenced.
6. **Target interface contracts:** detect active source implementing known
   target-engine interfaces while missing newly mandatory methods. Require a
   source-level implementation and compile validation; never generate behavior
   automatically from the signature alone.
   **Status: initial 0.98a `LevelupPlugin` contract check implemented after
   reproducing Edmund's Church 2.5's Janino load failure.**

### Audit-derived capability gaps

The 2026-09-01 archive and installed-mod corpus audits showed that several
existing signals need stronger context before they can drive a useful migration
plan.

1. **Reachability-aware finding triage:** correlate source and bytecode findings
   with configured entry points, plugin registration, and known campaign/mission
   callbacks. Rank likely-reachable stubs and obsolete APIs above dead code,
   examples, and inactive sources, while retaining the raw evidence.
   **Status: configured-entry-point and bounded unambiguous local-call evidence
   implemented; full call-graph analysis remains research.**
2. **Packaged-versus-source reconciliation:** classify a missing configured class
   as absent from the packaged JAR, present only in source, supplied by a
   dependency, or genuinely unresolved. Generate a rebuild/package diagnosis
   rather than treating every mismatch as the same defect.
   **Status: source-only, packaged, and unresolved classification implemented;
   explicit local API inventories can now attribute configured classes without
   asserting that unselected dependencies are absent.**
3. **Content-identifier ownership and resolution:** build a mod-local/vanilla/
   external identifier index for systems, entities, variants, factions, and
   memory namespaces. Use it to distinguish intentional self-references from
   brittle cross-mod or vanilla assumptions, and detect unresolved references.
   **Status: source-defined and mod-prefix attribution implemented for campaign
   system/entity lookups, with an optional explicit registry workflow; no global
   vanilla or external-mod registry is assumed.**
4. **Mission assembly validation:** statically resolve mission fleet/member,
   variant, ship, weapon, and map references across both historical mission
   layouts. Flag missing local members separately from references supplied by a
   dependency; add an opt-in mission smoke scenario where runtime support exists.
   **Status: local ship/fighter-wing, mission-variant hull, and mission-variant
   weapon resolution implemented; maps and runtime launch remain future work.**
5. **Dependency compatibility matrix:** extend external API-import evidence with
   declared dependency versions, bundled-library ownership, and verified local
   API inventories. Report version skew and unavailable API symbols without
   proposing substitutions unless a migration-pack contract exists.
   **Status: declared dependency versus direct API-import evidence plus opt-in
   local class and unambiguous method-name inventory checks implemented;
   overload, runtime, and load-order verification remain gated.**
6. **Scenario-based runtime smoke profiles:** add opt-in, user-authored profiles
   for campaign load, mission launch, and custom-UI interaction markers. They
   must execute only in a staged working copy and must never claim runtime health
   from static analysis alone.
   **Status: scenario labels, per-scenario log assertions, and stale staged-mod
   protection implemented; game launch orchestration remains explicitly
   user-authored and opt-in.**

### Current completion map (priority order)

1. **Transactional recovery fault injection:** simulate a failure during a later migration write and prove that every earlier write is restored.
2. **Legacy JSON policy:** verify target-engine behavior for trailing commas and other observed historical syntax before changing classification or normalization behavior; retain `MANUAL` findings until the evidence exists.
3. **Cross-platform CI matrix:** run install and unit tests on Windows and Ubuntu with supported Python versions and Java 17.
4. **Opt-in corpus comparison runner:** scan user-approved local mod corpora and compare only aggregate results to sanitized baselines; keep paths and mod content out of Git and CI.
5. **Verified migration-pack contracts:** require provenance, before/after fixtures, compile validation, idempotence, conflict checks, and save-risk assessment for every MagicLib, LazyLib, or AshLib mapping.
6. **Containment and symlink security coverage:** test altered plans/manifests, symlink escapes, and archive member traversal names.
7. **Archive-intake coverage:** add bounded handling/tests for wrapper-directory layouts, corrupt archives, entry-count and compression-ratio limits, and missing metadata.
8. **Deterministic provenance coverage:** prove hashes are stable for unchanged inputs and change only with relevant content.
9. **Deferred test-suite hygiene:** split `tests/test_scanner.py` by concern only when it becomes a demonstrated maintenance burden; this must not displace product work.

- **Completion definition:** all items above have deterministic tests, documentation, and machine-readable artifacts where applicable. Research tracks below remain gated until their stated evidence and safety prerequisites are met.

**Current status: completed 2026-08-31.** The test-suite split was assessed and deliberately deferred under its documented maintenance threshold; all other completion-map items are implemented and covered by local and cross-platform CI verification.

### Corpus expansion strategy

- **Legacy campaign/code specimens:** prioritize Vayra's Sector, then one of Blackrock Drive Yards or Dassault-Mikoyan Engineering. Use them for analysis and evidence quality, never automatic migration.
- **Modern controls:** maintain known-working current specimens (starting with Nexerelin and a library-dependent modern mod) to measure false-positive rates and confirm Bridgeforge can recognize health.
- **Version lineage:** collect old/current releases of a maintained mod such as Ship/Weapon Pack or Nexerelin. Treat maintainer-driven differences as evidence for what changed, what remained intentional, and which scanner assumptions are false.
- **Dependency archaeology:** compare historical/current LazyLib, MagicLib, and optionally GraphicsLib releases. Library migration rules may use this evidence only through the verified migration-pack contract.
- **Library usage attribution:** report whether each known library is declared, bundled, imported, source-called, or bytecode-referenced; flag declared-but-unreferenced dependencies for review. This is evidence only: it must not remove, upgrade, or migrate a library without verified API-specific examples and compile/runtime validation.
- **Binary-only restraint specimen:** retain one source-less, old-bytecode mod to verify package/class inventory, dependency evidence, and graceful `UNKNOWN` handling without decompilation or speculative reconstruction.

### Evidence intake (2026-08-31)

- **Vayra's Sector archive:** a 492-file legacy campaign specimen with a JAR, non-UTF-8 CSVs, verified trailing-comma cases, and other parser-tolerance ambiguity. It is evidence for intake classification, not a migration source.
- **Ship/Weapon Pack source lineage:** the public master branch is reachable and its source tree places `mod_info.json` under `src/`; use old/current maintainer releases to distinguish source-checkout layout from a distributable mod layout.
- **Nexerelin modern control:** the public repository provides maintained 0.12.2-series tags and a large current source/data tree. Use it to measure modern false positives, especially historically loose JSON syntax.
- **LazyLib and MagicLib dependency archaeology:** both public repositories are source/build layouts, not generic migration templates. LazyLib keeps its distributable metadata below `mod/`; MagicLib contains built artifacts as well as source. Keep scans attributable to the selected root and require release-specific before/after evidence for every pack rule.

These sources are retained as external, user-approved evidence only. Bridgeforge does not vendor them, execute their code, or infer transformations from apparent API similarity.

- **Cross-mod analyzer:** construct a read-only dependency and API-use graph across a selected set of mods, including duplicate libraries, package/class ownership, declared dependencies, and version-skew findings. Reports must remain attributable to each source mod and machine-readable.
  **Status: explicit-set dependency, duplicate-class, and campaign-ID ownership graph implemented; global discovery and runtime load-order analysis remain out of scope.**
- **Bytecode rewriting:** investigate narrowly scoped, reversible bytecode transformations in working copies only. Every transform must be deterministic, generate a class-level patch/provenance record, retain the original class, and require explicit review/approval before it can be applied.
- **Decompiler integration:** add an optional local decompiler adapter for review artifacts when source is absent. Decompiled output is evidence only: it must never be treated as authoritative source or automatically recompiled/replaced without an explicit user workflow.
  **Status: hash-bound, explicit-execution adapter plan implemented; output is retained as untrusted review-only evidence.**
- **MagicLib/AshLib adoption:** develop evidence-backed migration packs for manual and review-gated adoption of MagicLib, LazyLib, and AshLib. Do **not** add transformations merely because APIs appear equivalent: every mapping must come from verified examples and documented behavioral evidence. Automatic adoption is a later, opt-in research track and may proceed only for a small allowlisted set of semantics-preserving mappings with compile, conflict, and save-risk validation; all other adoption remains recommendation-only.

## Product boundary

Bridgeforge modernizes legacy mods. It does not profile performance. The related, independent **Starsector Performance Workbench** is specified in [docs/PERFORMANCE_WORKBENCH_DESIGN.md](docs/PERFORMANCE_WORKBENCH_DESIGN.md); the only planned interchange is a small set of versioned JSON schemas.

## Void-Tec working-tree evidence tranche

1. **Working-tree layout classification:** distinguish generated and backup
   candidates from source/content candidates without suppressing any files.
   **Status: implemented as read-only `working-tree-layout` evidence.**
2. **Source-authority selection:** require an explicit source-root manifest when
   a working tree contains multiple non-generated Java roots.
   **Status: implemented as output-only `source-authority`.**
3. **Build-input manifests:** expose Lombok/annotation-processing imports,
   local processor JAR hints, and build metadata without assuming a processor
   version or attempting a rebuild. **Status: implemented.**
4. **Optional-integration scenarios:** translate direct optional API imports,
   external campaign-memory access, and UI injection into review-only staged
   runtime prompts. **Status: implemented; no runtime health claim is made.**
5. **Generated-artifact-aware release deltas:** report build/log/class and
   backup candidate deltas separately from normal content deltas. **Status:
   implemented; candidates are never ignored automatically.**

## First 10 implementation phases — V0.1 scanner

1. **CLI and target profile** — accept a mod directory and explicit Starsector/Java targets.
2. **Safe intake** — validate the input directory and scan it read-only.
3. **File inventory** — record files, sizes, and relevant layout areas.
4. **Metadata analysis** — parse `mod_info.json` and declared dependencies.
5. **JAR/bytecode analysis** — inspect archives and class-file major versions without loading code.
6. **Dependency analysis** — identify bundled libraries, duplicates, and likely obsolete runtime copies.
7. **Source inspection** — collect imports and flag a small, data-driven set of known legacy APIs.
8. **Asset/config validation** — check JSON and CSV structure in Starsector data areas.
9. **Environment inference** — estimate source Starsector and Java eras with recorded evidence.
10. **Artifacts and reporting** — emit `MODERNIZATION_REPORT.md` and `bridgeforge.compat.json`.

**Status: implemented locally.** The V0.1 scanner is deliberately read-only and has no automatic migration, bytecode rewrite, or AI dependency.

## Subsequent releases

- **V0.2:** working-copy generation, safe deterministic metadata/config fixes, checkpoints, and patch manifests. **Status: initial workspace, plan, approval, patch, and rollback foundation implemented; migration-pack coverage remains deliberately minimal.**
- **V0.3:** AST-based Java source migrations; no regex source rewrites. **Status: parse-only JDK AST import/method evidence and review-gated, AST-confirmed import replacement foundation implemented.**
- **V0.4:** JDK/dependency selection and compile validation. **Status: JDK-profile capture, command preview, controlled `javac` execution, diagnostic classification, non-applying compile feedback, and deterministic output-copy JAR packaging implemented.**
- **V0.5:** scoped agent handoff bundles for ambiguity only; Bridgeforge remains the planner and validator. **Status: bounded review-bundle artifact generation implemented.**
- **V0.6:** runtime smoke validation and log collection. **Status: reference-integrity, structural, and compile-result validation are implemented; runtime execution remains opt-in and can require configured log markers inside the selected working directory.**
- **V0.7:** ~~save-risk analysis.~~ **Closed:** save compatibility is not a Bridgeforge compatibility target across Starsector patches. The existing static identifier-diff report remains optional review context only; it must not be presented as a path to save migration or compatibility.
- **V0.8:** migration-pack/plugin ecosystem, including separate library-migration and library-adoption recommendations. **Status: discoverable, validated bundled pack registry and pack-selectable planning implemented; ecosystem rules remain deliberately empty until evidence-backed mappings are added.**
- **V0.9:** modernization-opportunity analysis; no automatic adoption. **Status: static, report-only adoption candidates implemented with explicit high behavioral risk and no automatic change path.**
- **V1.0:** repeatable scan → diagnose → plan → apply → compile → review → validate → report pipeline. **Status: orchestration command and final workspace modernization report implemented.**

## Idea: Salvor (working name), a save doctor, editor and trainer as a separate program (2026-09-29)

**Started 2026-10-02:** `Documents/Project Salvor` (local git, no remote), v0.1.0 `repair` on a copy; BridgeForge provides `save-doctor` and `save-removal-plan` (read-only).

Owner idea: a separate program that diagnoses and fixes saves, then grows into an editor and trainer. Start small, as
BridgeForge did. BridgeForge's saves stay read-only (P3b: "the game creates state, BridgeForge reads it"), so
writing lives in a sibling program that reuses BridgeForge's save reader and `save-*` commands, the RC8 registries
and `RC8_BEHAVIOUR.md`, the rig and probe patterns, Project Go's GUI and packaging, and SPW's agent-mod and
crash-log work. Proposal, growth order and owner decisions:
[docs/SAVE_TOOL_PROPOSAL.md](docs/SAVE_TOOL_PROPOSAL.md).

1. [x] Owner decisions, 2026-09-29: working name Salvor, in its own repository; Python; a trainer independent of
   the game (offline presets on a save copy, no in-game mod); local-only.
2. [ ] Diagnose (read-only): package the `save-*` commands and crash reading for players.
3. [ ] Fix on a copy: plan, write the copy, re-read it, then load-test it in the rig. Original saves are never
   overwritten.
4. [ ] Editor, validated against RC8 registries (skills RC8-18, market conditions RC8-16, weapon slots RC8-17, ids).
   **Moved to VoidSmith (owner, 2026-10-06);** Salvor stays a lightweight save rescue (diagnose and repair a copy). First scope:
   minor edits to the current state (credits, supplies, fuel, crew, marines, machinery, story points), then fleet repair
   state, then blueprints, members and relations. Blocked on a VoidSmith charter decision (it is read-only and its
   campaign-save parsing is decision-gated); capacity behaviour above cargo limits needs live evidence first.
   Design: [docs/SAVE_TOOL_PROPOSAL.md](docs/SAVE_TOOL_PROPOSAL.md), revision 2026-10-06; VoidSmith side recorded as its phase 57
   (`docs/SAVE_WORKSHOP_DESIGN.md`, design only). Overage effects (slower fleet, more supplies per day, formula unknown) need a
   controlled rig run before any rule is written down.
5. [ ] Trainer: offline presets on a save copy, through the editor's validation and the rig-load gate (follows the editor, in VoidSmith).
6. [ ] **Migrate (owner goal 2026-10-06; Salvor; may expand it a lot): make a save that a game or mod update broke load again.**
   Local-only: a public release is **not** a goal (migration data encodes third-party class names, ids and obfuscated game
   internals, which cannot be shipped, and "loads" is never "plays the same"). Plan: diff the old and new builds (classes, fields,
   enum values, data ids); classify each delta SAFE (1:1 evidenced rename, default fill for an added field), REVIEW, MANUAL or
   UNKNOWN, with evidence; apply only SAFE ones to a copy; accept only after a rig load test; keep reusable migration packs as
   local data per mod or game version pair, hand-written ones for MANUAL cases. Build on `save-compat --compare-old/--compare-new`,
   `port-interfaces` and the registries. Revived mods that rename things should ship a pack with their `+bf.N` revision. Limits:
   no generic conversion across major game versions; mods that redesign their stored state need a mod-specific migration. If a
   public release is ever wanted, only the small safe subset qualifies: drop/remove/default-fill, mapping derived at run time
   from the player's own old and new installs, nothing third-party bundled, strong disclaimers.

## Sister repository interoperability (proposed 2026-09-27)

Design and acceptance gates: [docs/SISTER_REPO_INTEROPERABILITY_DESIGN.md](docs/SISTER_REPO_INTEROPERABILITY_DESIGN.md). These are pending, separate from revival completion and release readiness.

1. [ ] Consume versioned SPW performance evidence with hash, identity, attribution, and comparability gates; retain independent operation and no automatic performance verdict.
2. [ ] Consume Project Go localization coverage for an exact mod-root hash; expose uncovered and unknown items without changing source or claiming complete coverage from partial extraction.
3. [ ] Compare BridgeForge's release evidence fields with VoidSmith and Project Go as a design reference; do not create a shared runtime dependency.
4. [ ] Consume optional SPW mod inventory with duplicate/disabled identity handling, while preserving BridgeForge's native scan.

## Proposed ideas (2026-10-06, owner asked for per-project ideas; proposed, not approved)

Each idea gives the benefit and where the evidence came from. None is scheduled.

1. [ ] **Rig bring-up in one command (`rig-up`).** Create or refresh a rig, sync its mods from working copies, enable the
   mods a test needs plus the probe and SpeedUp, write the probe config and run `rig-doctor`. Benefit: the Exigency test needed
   about ten manual steps (sync, enabled_mods, probe-config, doctor, SpeedUp); one command removes slips such as the
   `/MIR` path mangling and a stale rig copy.
2. [ ] **`accept` for a non-group live run.** After a clean run, check the log milestones (main menu, save, no FATAL or
   MOD-ERROR), append the dated evidence section to the revival report, set LIVE_VALIDATED, and archive. Benefit: this session
   hand-edited the report status and re-archived by hand; the evidence section would be uniform and checkable.
3. [ ] **`archive --refresh`.** Replace an existing Done/ folder safely and rebuild its `-with-readme.zip` for that folder
   only. Benefit: today it means deleting the folder and running a whole-Done script; a mistake could touch other archives.
4. [ ] **Caught-exception triage.** `log-triage` reported MOD-ERROR=0 on a run whose real risk (Nexerelin's `StrategicAI`
   logging an NPE and carrying on) is a logged ERROR with a stack trace, not a crash. Attribute each logged stack trace to the
   mod that owns the top non-vanilla frame and count it per mod. Benefit: finds failures that do not crash, such as the
   original Avesta error, before a player does.
5. [ ] **Time-accelerated soak run.** A scenario that lets a campaign run for many in-game months (SpeedUp, or the probe's
   interval) and then triages the whole log. Benefit: relocation, raids, economy ticks and fleet managers only show up over
   months; the Avesta hop appeared only after about 60 game days.
6. [ ] **Raid and invasion scenario mod.** A separate mod, allowed to use Nexerelin classes, that forces a raid at a chosen
   market. The public-API-only probe cannot. Benefit: turns "raid path unobserved" (item 56) into a test, and covers other
   target types (no industries, hidden markets).
7. [ ] **Finish item 58.** Run the live negative control; add a static check for `addMarket` on a hyperspace entity in loose
   scripts; sweep the corpus for other stations in hyperspace. Benefit: a known crash class found in every mod that has it.
8. [ ] **Migration packs with revivals.** A revived mod that renames ids or classes ships a local migration pack with its `+bf.N`
   revision, checked by `save-compat` before archiving. Benefit: the owner's own saves survive revisions; feeds Salvor's Migrate
   goal.
9. [ ] **Save-format survey across versions.** Run `save-format-survey` on saves from other game versions when available, to
   give VoidSmith's Save Workshop the version boundaries its parser gate needs. Benefit: closes the one-version limit of item 59.

**Implemented 2026-10-06 (owner: work in the recommended order):**
- Item 4 done: `log-triage` reports `caught_exceptions`, logged ERROR/WARN events carrying a Java exception that did not crash, grouped by exception class and first frame with a count, line range and (with `--mods-dir`) the owning mod of the nearest mod frame. The mod whose data caused it is often not on the stack, so `suspect` is where the code threw. Tests: `tests/test_caught_exceptions.py`.
- Item 5 done: probe 0.2.17 logs a `campaign-day` heartbeat; `bridgeforge soak-report LOG --days N` returns PASS, ATTENTION or INCOMPLETE from days covered, FATAL/MOD-ERROR, probe FAILs and caught exceptions; `bf-test soak <TESTID> <days>` runs it on a rig log. The campaign is sped up with the SpeedUp key; an automated clock skip was not built (`SectorAPI.setInFastAdvance` exists but its effect is unproven). Tests: `tests/test_soak_report.py`.
- Item 2 done: `bridgeforge accept WORKSPACE --log LOG --test-id ID --note ...` checks the log (main menu, a load or save, no FATAL/MOD-ERROR, enough days with `--days`), refuses probe FAIL lines and caught exceptions unless `--accept-findings` gives a reason, writes the dated evidence section and LIVE_VALIDATED, and writes the run record the archive gate reads. Tests: `tests/test_live_accept.py`.
- Item 3 done: `archive --refresh` replaces an earlier archive (only a direct child of Done/ holding an ARCHIVE_NOTE.md) and `--readme-copy` writes `<zip>-with-readme.zip` and `readme.txt` for that archive only. Tests: `tests/test_live_accept.py`.
- **Found by item 2 on first use:** the Exigency 0.8 hop run (AVESTA-HOP-1) has 129 probe FAIL lines that the hand-written acceptance did not account for: `faction-fleet-gen` FAIL for `exipirated` (FleetFactoryV3 built an empty patrolMedium although the faction knows ships and its cheapest hull is within the 60-point budget; `exigency` and `player` build 10-11 members) and `class-sweep` FAIL for `data.scripts.radar.exigency_RepulsorRenderer` (NoClassDefFoundError for the optional Combat Radar integration, which the rig does not have). The run record for AVESTA-HOP-1 is therefore not written (live status UNKNOWN_BUILD) until the owner decides: investigate, or accept with a reason. The save held an Exipirated Heavy Patrol, so fleets do spawn by another path.
  **Investigation 2026-10-06:** (1) `class-sweep` Combat Radar FAIL is harmless: no class in the 0.8 `Exigency.jar` references `exigency_RepulsorRenderer` or `org/lazywizard/radar` except that class itself (grep of the extracted jar), so nothing loads it; it is an orphan the class sweep loads. Acceptable with that reason. (2) Empty Exipirated patrol: unresolved offline. Facts: `exipirated.faction` is byte-identical to the original; its `knownShips` is the tags `exipirated_bp` and `base_bp` (so vanilla base hulls count as known), `hullFrequency` is empty (the same as `exigency.faction`, which builds 10 members); the mod's `default_ship_roles.json` lists only Exigency variants and none of Exipirated's 17 variants; all three Exipirated fleet managers build with `FleetFactoryV3` from a market. The probe's patrol is market-less, quality 1, patrolMedium, 60 points, so it may differ from a real market patrol. Probe 0.2.18 adds `faction-fleet-gen-diag` INFO lines on an empty fleet: known-ship count, variants per ship role, and a market patrol (patrolLarge, 120 points, quality -1) from the faction's own market. **Needs a live run** (one in-game day after load); then decide a fix or an accepted reason. Escalate to an agent only if the diagnostic shows the role table, since that is a data question the game cannot answer faster.
  **Result (live runs DIAG-1 and DIAG-2, probe 0.2.18/0.2.19, 2026-10-06): cause found.** Exipirated knows 27 ships (its 7 own hulls plus 20 vanilla `base_bp` hulls) but its ship roles hold only vanilla variants of those vanilla hulls: `combatSmall`, `combatMedium` and `combatLarge` each resolve to the single variant `buffalo2_FS`, `fastAttack` to `hound_Standard`, the carrier roles to four vanilla carrier variants. None of its 17 own variants is in any role, because the mod's `default_ship_roles.json` (byte-identical to the original) names Exigency's variants and no Exipirated ones, and `exipirated.faction` has no `shipRoles`. A patrol from the faction's own market (Avesta, patrolLarge, 120 points) is also empty, so this is not a probe artifact. In the game the managers drop a null fleet, which is why Exipirated fleets are rare (13 samples over 65 days showed none; the one Heavy Patrol in the save probably came via the `addGenericCombatShips` path). Own hulls: rauwel frigate (6 fleet points), azryel destroyer (11), harinder cruiser (17), kafziel light carrier (10), gehenna 'mobile outpost' (26, 4 bays), azazel and saraph (no fleet points: likely modules). **Not changed.** Whether Exipirated was meant to field its own ships is the author's design, not provable here; adding them to the roles is a REVIEW-tier content change (gameplay). Options for the owner: leave as is and accept the finding with this reason; or a `+bf.N` revision adding the variants to roles by hull size and bays, checked by the probe's `faction-fleet-gen` turning OK.
  **Resolved 2026-10-06 (owner chose the revision):** Exigency 0.8 is `+bf.9`: 24 entries for Exipirated's 17 variants added to nine roles in `default_ship_roles.json` (Azazel and Saraph are FIGHTER hulls behind the wings `exipirated_azazel_wing` and `exipirated_saraph_wing`, not modules, and no Exipirated ship has station modules; they stay out of the roles). Live run DIAG-3 (about 36 campaign days with SpeedUp, probe 0.2.19): the probe's Exipirated patrol went from empty to 8 members in all 8 samples; Exipirated fleets in the sector rose from 0 to 7 (65 days earlier showed none); no FATAL, MOD-ERROR or caught exception; the only FAIL lines were the harmless Combat Radar class sweep (accepted with that reason). Recorded with `bridgeforge accept` (run record `_live/DIAG-3.json`, live status CURRENT for bf.9, which also closes the missing run record for the hop run), `audit-explain` for the roles file, and re-archived with `archive --refresh --readme-copy`. Still unobserved: a raid on Avesta, and Exipirated's own ships in battle.
61. **Java and launcher test matrix (owner: "set things up, we will test everything again with the new setup", 2026-10-09).** **Built 2026-10-09; first live use recorded 2026-10-12 (item 70 continuation).** A tester's log (Java 28-beta, Fast Rendering) showed vanilla ids missing at load (`System with id [temporalshell] not found`, `Ship hull spec [afflictor] not found!`, the latter inside `SpecStore.lambda$SpecStore_init$0` on a thread pool, a loader vanilla does not have). The rig could not vary the JVM or launcher. `bridgeforge/java_matrix.py` + `java-matrix discover|setup|run|describe-log`: one `run-j<major>-<direct|fr>.bat` per JDK found (never touches `run-java25.bat`), `run` boots the same mods N times per variant and reports a pass rate (flaky vs fails-everywhere vs varies-by-variant), resumable, `--quiet`, listed in `LONG_RUNNING_COMMANDS`. `run_boot_test` gained `bat_name`. Tests: `tests/test_java_matrix.py`. Hypothesis, not evidence: Fast Rendering's parallel spec loading races on Java 28; record any result in `docs/RC8_BEHAVIOUR.md`. Local follow-up: `docs/LOCAL_HANDOFF.md` section 0a. **Parallel instances added 2026-10-09 (owner: at most 3 at once; vanilla, FR, Java 28, FR + Java 28):** `--parallel N` (1..3) gives each variant its own instance rig, `instances` lists them, `--preset compare`, `--skip-known` + ledger skip re-testing known-good variants for an unchanged mod set.
62. **Mass test across the Java/launcher environments (owner 2026-10-10: set up everything to mass test mods; observe Seeker lag during the FR / Java 28 runs).** **Built 2026-10-10; mass live boot results recorded 2026-10-12 (item 70 continuation).** The original 2026-10-10 instruction was no live testing that day; boot results do not establish full gameplay acceptance. `bridgeforge/mass_test.py` + `java-matrix mass RIG`: one mod per run from `Done/` with its declared dependencies only (instance rigs link just those folders), screened first on the baseline (direct, lowest Java) and the stress variant (Fast Rendering, highest Java), the other variants only on a mismatch; a LIVE_VALIDATED mod's baseline is assumed, not re-booted (`--retest-baseline` overrides). Reports which mods are environment-sensitive (pass in some variants, fail in others) apart from those failing everywhere; resumable, per-mod progress, `--quiet`, in `LONG_RUNNING_COMMANDS`. **Found by a stray boot on 2026-10-10 (no game started):** JDK 28+13 rejects `-noverify` and `fr.vmparams` has `-XX:+UseVectorStubs`, so no launcher could start; `write_launcher_files` now probes each flag with `java -version`, drops what the JVM refuses, records it per variant (`dropped_flags`) and, for Fast Rendering, writes a filtered copy of the install's `fr.vmparams` beside the bat (the install is only read). Logs are kept out of the throwaway instance rigs (`keep_logs`). Cost: about 2 boots per validated mod, so a 300-mod archive is days of boot time, not hours; use `--limit`/`--only`. Tests: `tests/test_mass_test.py`. Local follow-up: `docs/LOCAL_HANDOFF.md` section 0a.
63. **AoTD / Theory of Toolbox compatibility plan (owner 2026-10-10).** **Plan only: `docs/AOTD_COMPAT_PLAN.md`.** Key finding: StarsectorPrepatcher 0.18.4 validates Java 17 and 27+22 only and must be the last javaagent; the installed Toolbox fork requires it, the plain `vmparams`/`fr.vmparams` carry no Prepatcher agent but the owner's real launcher (`Miko_Simple.txt`) does (corrected 2026-10-10). Seven steps: a Prepatcher axis in the matrix, an `env-check` preflight, an `aotd` compat set, a Toolbox version check, re-proving item 38 against the fork, a per-frame market-work scan, a release-policy note.
    **Addendum 2026-10-10 (owner: 32 GB machine, optimise as you see fit; Java 17 not needed):** heap fixed at 4 GB per instance (5 GB for a bundle; three instances plus ~2 GB native each leave room for the OS), identical across variants so heap is not a variable. `--bundle N` (default 4) boots unrelated mods together while screening and splits in halves only on a failure; total conversions and core-replacing mods always boot alone; halves that pass alone but fail together are reported as a `bundle_conflict`, not an environment problem. New launchers `miko` and `miko-noprep` copy the owner's `Miko_Simple.txt` (resource-cache agent, Fast Rendering, Prepatcher last, G1) with only the heap, log path and JDK-refused flags changed, and `--preset real` runs both on Java 28: Prepatcher is a variant of the owner's real launch, not a separate matrix. Tests: `BundleTests`, `MikoLauncherTests` in `tests/test_mass_test.py`.
64. **Migrating everything to another computer (owner 2026-10-10).** **Plan only: `docs/MIGRATION_PLAN.md`.** What is in git, what is gitignored and irreplaceable, what is regenerable, what is game files; the absolute paths that break (git `core.hooksPath`, `config/bridgeforge.local.psd1`, rig junctions and bats, `bridgeforge-state/*.json`, the Claude memory folder key); what Syncthing can and cannot carry (not `.git/`, not junctions, not a working tree in use). Planned: `migrate-inventory`, `relocate`, `migrate-verify`, a cutover checklist.
    - **Status correction 2026-10-18:** `migrate-inventory`, `relocate`, `migrate-verify` and snapshot helpers now have implementations (`bridgeforge/move_machine.py`, `bridgeforge/state_snapshot.py`, corresponding tests). The preceding Plan-only summary is the original proposal; this does not prove machine cutover or restore qualification. Preserve unique logs/crash evidence during migration.

65. **Yellowjackets intake and the gaps it showed (owner: "investigate and process", then "any more fixers..." 2026-10-10/11).** **Mod done 2026-10-11; items 65a-c built, the rest proposed.** Yellowjackets Mining Conglomerate (a raw 0.6.1a folder dropped in the queue) was zipped and taken in with `intake`, revived, passed `java-matrix run --preset compare` (PASS_ALL) and a full live run (GRP1C-20261011), and archived as 0.1; RC8-24 records that a ship system file named differently from its id loads. Built: 65a. `csv-vanilla-row-override` (tier input) names rows of a mod's ship/weapon/wing tables whose id RC8 defines, skipping tables the mod `replace`s; its fixer removes those records (CSV-aware, multi-line safe) once approved; measured on 304 workspaces: 12 mods have such rows, most deliberately (Xenoargh-Rebal), so it asks. 65b. `fix --finding carrier-bays-proposal --hull-zero-no-evidence` writes 0 bays for hulls with a `hangar` value but no LAUNCH_BAY slot and no variant wings (the one count the data supports); other hulls stay an owner decision. 65c. Probe 0.2.23 logs `combat-launch`: the most drones and fighter wings each ship had out at once (the Yellowjackets drone check had only the owner's word). Six stale archives (Adjusted Sector, Faction Relationships Uniquified, Fuel Siphoning, Legacy of Arkgneisis, Megastructures Tab, RogueSynth: archived READY_FOR_LIVE_TEST, live-tested after) were refreshed to LIVE_VALIDATED with `archive --refresh --readme-copy` (owner approved). `Done/MASTER_LOG.md` + `.csv` (generator `Done/make_master_log.py`) list every archive with release version, dates and what was done. Proposed, not built: `intake` accepting a raw folder and the planner listing unprocessed raw folders; archive notes always carrying the live date and test id, and the master log regenerating on record/archive; a launch watchdog (the first Yellowjackets launch wrote nothing and said nothing); standing approvals for `removed-api-call`, the fighter-bays column and the supplies column (owner decision). Still open: Doc's Needless Economic Expansion Pack and Slightly Better Tech-Mining are archived as READY_FOR_LIVE_TEST with live status UNKNOWN_BUILD (revive status ESCALATED, so the planner skips them): they need a live run before their archives can be refreshed. Tests: `tests/test_vanilla_row_override.py`, `tests/test_carrier_bays_zero.py`. **65g, built 2026-10-11:** `bf-test.ps1 launch` clicks the launcher's Play button itself (posted messages, real-click fallback; proven on CLICKTEST-20261011, `BF_NO_AUTOCLICK=1` disables); `java-matrix mass` gained `--preset`, skips `_` folders, retries LunaLib-signature failures as `NEEDS_LUNALIB` (RC8-25) and retries locked instance-rig cleanup; covered by `tests/test_mass_test.py` and `tests/test_java_matrix.py`. Fast Engine Rendering 1.1.2+bf.1 and the stale archives were refreshed with `record --archive --refresh` (65d). **65h, 2026-10-11 (owner: intake and revive Neutrino older, revive Combat-Misc-Utils, live-test both with the unattended run):** Combat-Misc-Utils 0.4.1 and Neutrino Corporation 1.8.9 (upstream Flashfrozen/Deathfly line, intaken from `Neutrino corp older.zip` as `Neutrino-Corporation-1.8.9`; Nostalgia Edition is a separate balance branch with the same mod id) are archived, both live-run with `probe-group live`. Found and fixed on the way: (1) `revive --apply` gave Combat-Misc-Utils a dependency on itself (scanner now skips a library whose id is the mod's own); (2) `star-type-undefined` read commented-out code (Neutrino's Exelion.java); (3) `probe-group smoke` caught Neutrino's missing GraphicsLib dependency (`ShaderLib.init()` unguarded; the undeclared-library scan misses it because the class also probes `ShaderLibExists`: not fixed, open); (4) `live_run` clicked a Neutrino mission because mods listed after the probe put their missions below it: it now counts those rows from the log's mod list (`missions_below_probe`); (5) `campaign-layout` FAIL lines are attributed to the sole member so an accepted entry applies. Agent packets (13) were run for Neutrino 1.8.9 and reviewed by hand: the convoy-spawn rewrite was rejected and restored (adds unverified runtime behaviour the author had disabled), the rest kept; jar classes patched with `patch-jar-class` (`scratch/jar-patch-2026-10-11`). Tests: `tests/test_live_run.py`, `tests/test_probe_group.py`, `tests/test_intake_scanner_fixes.py`, `tests/test_total_conversion_scans.py`. **65i, 2026-10-11 (owner: continue adding automation, fixers, handwork improvements):** Neutrino Corporation: Nostalgia Edition revived and archived the same way. New fixers: `runtime-placeholder-unsupported-operation` for ShipSystemStatsScript's five *Override hooks (-1, BaseShipSystemScript's answer) and `black-hole-type-missing-flag` (both tier auto; run on Nostalgia's real files). `audit-explain --auto` now proves two more categories: a work file moved to `scratch/work-files/` (byte-identical copy there) and a CSV that only gained rows. The undeclared-library scan no longer treats a probe elsewhere in a file as covering an unguarded call: it tracks enclosing blocks (try/catch or an `if` naming the library) and now flags Neutrino's `ShaderLib.init()` (the 1.8.9 original reports GraphicsLib; the fixed workspace reports nothing). A whole-corpus sweep of that scan change for new false positives timed out at 15 minutes and is not done. Tests: `tests/test_placeholder_hooks_fixer.py`, `tests/test_live_trust.py`, `tests/test_intake_scanner_fixes.py`. **65j, 2026-10-11:** Ironclads re-tested on Java 28 with Fast Rendering through `probe-group live` (GRP10Y3-20261011): new game, one day, all 140 hulls in three combat rounds, report PASS; the only log line was Fast Rendering's startup BaseSpawnPoint ERROR (RC8-26), now known noise, which had made the verdict UNCLEAR. To get there: `probe-group plan --retest WORKSPACE` re-runs an already validated mod; the launcher click finds the game by the launcher's process tree (the java-28 JDK is outside the rig, so the exe-path match never clicked: SMOKE-iron28-20261011); live_run has a New Game flow for Ironclads' own screens and lays the mission list out from the log (a replacing mod such as Ironclads shows only its own missions, short lists are top-anchored). Tests: `tests/test_live_run.py`, `tests/test_launcher_click.py`, `tests/test_log_triage.py`. **65k, 2026-10-11 (owner: diagnose the Bone-Breaker destruction slowdown, measure it with a timer, then package):** `probe-group duel` plays rig-only duel missions (`probe-mod/duel-mod/bf_duel`: Bone-Breaker vs Betelgeuse, Bone-Breaker overwhelmed by four vanilla capitals with a forced kill at 45 s, two vanilla Onslaughts as the baseline) and reads the plugin's per-second frame period, field counts and FIGHT/END timers; stalls (clock frozen, or no lines for 20 s) capture three thread dumps and a game-window screenshot. Cause found: SEEKER's Liquid Skin and Phased Mainframe ran their death effect every frame on the wreck (RC8-27); fixed with the once-per-ship guard Organic Hull already had; Seeker re-archived as +bf.5 (live run GRP-SEEKER5: campaign PASS; its probe combat stage could not reach the probe mission, 10 SEEKER missions below it). Found on the way: with no flagship the game parks a mission at 'shuttle ready for command transfer' about nine seconds in (the duel plugin unpauses it); the duel mod is named 'zz ...' so its missions sit at the bottom of the list. Open: the main-menu and mission-list click positions are fixed fractions and one run found the menu laid out differently (rows 28 px apart instead of 23), so a click can miss; the mission list needs scrolling to rows more than 7 above the bottom. Tests: `tests/test_duel_run.py`. **65m, 2026-10-11 (owner: start all recommendations):** (1) `hulk-death-effect-repeats` check and fixer (65l). (2) Unattended clicks made reliable: Starsector keeps the launcher's resolution in Java preferences shared with the owner's own game (HKCU\Software\JavaSoft\Prefs\com\fs\starfarer; it had 2048x1152), which changed the rig's whole layout; `rig_prefs.pinned_launcher_prefs` pins 1920x1440 windowed for each unattended run and restores the owner's values afterwards, even on error (checked: 2048x1152 back after a killed run). Main-menu buttons are now read from the screen (`screen_read`, BMP of the game window only) once the menu stops sliding, and a click is retried until the menu goes away. The probe mod is named 'zzzz BridgeForge Probe' so the launcher lists it last and its mission is always the bottom row (the list scrolls about a sixth of a row per wheel notch and arrow keys do not move the selection, both measured live). (3) Probe 0.2.24 meters every combat: `combat-perf` INFO (frames, average and worst frame, peak hulks and ships), and FAIL plus an early end when a field runs away (400 hulks or a 2 s frame); `probe-group report` fails the only member or makes a bigger group UNCLEAR; wreck fragments are no longer logged one by one. (4) see (2). (5) the undeclared-library sweep finished (65l). (6) the raw Neutrino folder was removed. Live: GRP-CMU4 and GRP-SEEKER6-20261011 LIVE_DONE with combat (Seeker: 14 hulls, worst frame 39 ms, 2 hulks), Seeker re-recorded. Tests: `tests/test_rig_prefs.py`, `tests/test_screen_read.py`, `tests/test_probe_group.py::CombatPerfTests`.

67. **Mod Atlas: index every mod's additions, overrides, id reads, mutations and hooks; forecast conflicts (owner 2026-10-11, broad AoTD compatibility as the first use).** **Phases 1-3 done 2026-10-11** (`bridgeforge/atlas*.py`, `atlas build/show/id/forecast`, tests `tests/test_atlas.py`): real roots 349 mods, 94,228 facts, ~30 s fresh / 3.8 s unchanged; `atlas forecast DNEEP --against aotd` flags DNEEP's `farming` and `aquaculture` lookups against VoK's industries.csv downgrade chains (REVIEW), plus a `habitable` false positive from class-level jar attribution. Follow-ups found on review (2026-10-11): 67a per-call jar attribution from bytecode (the `habitable` false positive); 67b resolve mod-defined Java constants and index TASC so Tritachyon x TASC reproduces; 67c index `original/` copies to measure precision on known cases; 67d index `.ship`/`.wpn`, planet types, terrain, settings.json lists, collection-typed saved fields in jars; 67e follow jar `addScript(new X)`, drop synthetic fields from saved-field; 67f resolve runtime-built ids where possible. Phases 4-6 open. Plan: `docs/MOD_ATLAS_PLAN.md`. One SQLite fact index (mod, version, kind, id, action, file:line, evidence, confidence) over Done/, the rig, reference installs and the backlog via corpus-index; ten conflict rules (ATLAS-READS-REPLACED reproduces DNEEP x AoTD, ATLAS-SAVE-HOLDS-HEAVY the Station Augments save cycle); `atlas forecast --against aotd` from an AoTD replacement profile; forecasts proven with probe-group swap-industry/expect-supply runs. Six phases; 1-3 cloud-buildable, 4-6 local. Owner decisions 2026-10-11: Done/ + rig first, backlog from phase 4; local HTML/JSON view; a replacement profile for every scanned mod, plus a check against the whole AoTD family.

66. **Commodity supply checks: did a mod's economy actually spawn? (owner 2026-10-11, after DNEEP's food vanished with AoTD).** **Done 2026-10-11.** Probe 0.2.25: `market-supply` lists, per commodity the mod adds (`mod_commodities` from its commodities.csv minus vanilla's), the markets and industries supplying it and the markets demanding it; demand with no supply anywhere is FAIL, blamed on the commodity's mod. `probe-group install --setup swap-industry:<from>:<to>:<count>[:<condition-prefix>]` puts an industry on chosen markets (it reapplies conditions as well as industries: without that DNEEP's deposits never reached a swapped-in farm), and `--expect-supply COMMODITY@INDUSTRY` FAILs unless that industry supplies it; a failed expectation logs `market-supply-diag` per market (functional, building, supplies, industries, conditions). Group configs had dropped `class_sweep` and `mission_fleets`; merged now. Live evidence: GRP-DNEEP-SUPPLY-BEFORE-20261011 (fix reverted in the rig copy, AoTD on) FAIL: grain, meat, fruits supplied in 0 markets of 38-39 demanding; AoTD converts Farming at New Game, so the old lookup found no farm anywhere. GRP-DNEEP-SUPPLY-AOTD3-20261011 (+bf.3, AoTD) PASS: grain from 10 subsidised farms, vegetables from monoculture plots. GRP-DNEEP-SUPPLY-SOLO-20261011 (no AoTD) PASS: Farming supplies all four. Tests: `tests/test_probe_group.py` MarketSupplyTests. Open (REVIEW, owner's own game): whether a farm a player builds mid-game gets DNEEP supply at once or only after the market's conditions reapply.

68. **Save corruption investigation lessons (owner 2026-10-11: friend's Modpack 6.3 save, 'any lessons for Salvor or BridgeForge').** **Diagnosis done; Station Augments 2.4.3+bf.1 built and live-tested; tooling below proposed.** Cause: Station Augments keeps each augment's market and stores the augments in that market's memory; on two planets (Salsar, Tor) the save wrote a station's condition-market copy inside that memory, whose `<memory>` then referenced the half-read memory, so `PlanetConditionMarket.readResolve` threw (RC8-31). Repaired copy of the save: two lines changed. Not Legacy of Arkgneisis: six memories in the save are shared three ways, four on procgen planets (an early claim that Arkgneisis was the trigger was withdrawn after checking the base rate). Fix: wrapper plugin `niko_SA.BfSAModPlugin` clears augment market links before every save and re-links on load (making the field transient would likely break old saves, RC8-32); tests GRP-SA-UNPATCHED (33 markets written), GRP-SA-PATCHED4 (0 of 33), LOAD-SA-NEWSAVE2 (33 re-linked), LOAD-SA-OLDFORMAT-20261011 (old save loads, 33 linked). Patch source `In operation/_patches/station-augments`; zip for the owner in Downloads. Lessons to build: (a) diagnose against the base rate before blaming a mod (Atlas forecasts too); (b) `save-doctor` must run on `campaign.xml` without `descriptor.xml`; (c) `save-doctor` cycle check and copy repair (with 60g(3)): references to a still-open Memory inside a PCMarket, streaming, verified line edits, naming the memory keys on the path; (d) scanner check for saved objects holding market/entity/fleet fields (60g(4)), with a fixer template 'detach before save, restore after, re-link on load'; (e) patch maintained third-party mods with a wrapper plugin, never in place; (f) jars only via the JDK jar tool (CLAUDE.md); (g) a save-reload test command: probe `--save-after-checks` (probe 0.2.26, built), swap a mod, load with Continue (RC8-29), press Space (RC8-28), check logs; (h) RC8-28..32 recorded.

    - 60g(2) **partly done 2026-10-11:** `live_run` has a Nexerelin New Game driver (chosen when the log's mod list has `nexerelin`): number key 1 one page at a time until `screen_read.nexerelin_fleet_select` sees the faction page's teal Select buttons, click the first, then Ensign, Done, G. A fixed count of presses failed because Nexerelin showed a different number of pages between runs (the owner had to pick faction and loadout by hand in GRP-EXI-AVESTA-OLD2/NEW). Proven unattended: GRP-EXI-NEXFLOW-20261011. A fully generic driver for other total conversions is still open. Tests: `tests/test_live_run.py`, `tests/test_screen_read.py`.

69. **Zorg18 V18+bf.8 (owner 2026-10-12: revisit Zorg18, then 'make Zorg hostile to everyone on game start').** **Done 2026-10-12.** The archived V18+bf.7 had lost two earlier fixes: javap showed its ZorgGen still had the modpack port's corona -10000 and Zeta I radius 0 at orbit 100 (fixed in the Old System bf.5), and ZorgMarket still made Unimatrix size 3 (owner's size 10, bf.6). The scanner had flagged the port bugs (`procgen-call-argument-suspect`) but they were in Zorg's accepted baseline; that entry is removed. bf.8 = bf.7's jar with exactly ZorgGen and ZorgMarket from the Old System build (the only two classes that differed), plus `data.scripts.BfZorgModPlugin` (source in `jar/src`) setting the Zorg to -1 with every faction but itself and `neutral` in onNewGameAfterEconomyLoad (ZorgGen set only six). Live GRP-ZORG-BF8B-20261012: PASS; the save shows Zeta I orbit 5000/100 days, Unimatrix size 10, and 20 hostile relations. Lesson: an accepted baseline entry can hide a real bug; re-check accepted findings when a mod is rebuilt from another line.
    - 69a (2026-10-12, owner: apply but keep bf.8): `BfZorgModPlugin` skips the player when `Misc.getCommissionFactionId()` is `zorg` and lifts ZorgGen's -1 to 0, so a Nexerelin start that joins the Zorg is not at war with its own faction. Live GRP-ZORG-BF8C-20261012: no commission, 20 hostile, PASS; re-archived as V18+bf.8 (earlier bf.8 zip kept in `Done/_replaced-2026-10-12/`). Not tested: a start actually commissioned with the Zorg (unconfirmed that Nexerelin lists the Zorg, which have no Nexerelin faction config).

    - 67 phases 4-6 built 2026-10-12 (Sonnet session): `atlas runtime LOG...` reads probe logs (BF-PROBE lines) into the atlas; `forecast` then adds ATLAS-RUNTIME-SUPPLY (a mod's commodity unsupplied in a live run, REVIEW; SAFE with the later run named once a later ingested run shows it supplied) and marks static ATLAS-READS-REPLACED findings `[confirmed live: TEST]` or `[seen live in TEST, fixed since]` (DNEEP x AoTD: GRP-DNEEP-SUPPLY-BEFORE/AOTD3/SOLO-20261011). `atlas forecast --pack enabled_mods.json [--top N]` forecasts a whole modpack as one load set, lists ids the atlas does not hold, and ranks findings by mod group (crash-class MANUAL first); on the friend's 6.3 pack it checked 205 of 577 ids (371 not indexed) and ranked duplicated classes such as `data.scripts.world.addMarketplace` first. `atlas sweep [aotd]` forecasts every indexed mod against the family with a progress line per mod and a checkpoint. Correction to an earlier claim: AoTD's `AoTDDataInserter` really removes `hot`/`cold`/`very_cold` (and adds `very_hot`) on one planet at new game (javap), so those DNEEP findings are true but narrow, not noise. Tests: `tests/test_atlas_runtime.py`. Open: sweep over the whole index not yet run for results; precision of forecasts vs live runs is not yet measured (67c originals).
    - 67 AoTD sweep 2026-10-12: first full `atlas sweep aotd` (338 mods) flagged 80 mods that `use` an AoTD-replaced industry, nearly all via `addIndustry` or bare jar string mentions; ATLAS-READS-REPLACED now ignores `add*` calls and rates a bare string as UNKNOWN (mention), REVIEW only for a call site. Result 167 clean, 128 REVIEW, 42 UNKNOWN, 1 NEEDS PATCH. Report and caveats: `docs/AOTD_SWEEP_2026-10-12.md` (e.g. 28 mods look up `orbitalworks`; Arkgneisis' economy bonus reads heavy industry/orbital works, so AoTD likely zeroes its development bonus: prediction, not yet live-checked). Next: live-check the top rows like DNEEP.
    - 67/63 live check 2026-10-12 (owner: try Java 28 / FR): probe 0.2.27 `faction-economy` (per market of the target mod's factions: industries, heavyindustry/orbitalworks, fleetQualityMod, combatFleetSizeMult). Arkgneisis x AoTD: the sweep's prediction (AoTD zeroes the Anarakis development bonus) was NOT supported: HQ orbitalworks stays true, quality 0.375 on Java 25 direct, 28 FR, and 25/27/28 FR + Prepatcher with AoTD; fleet size mult 1.875 without AoTD, 2.125 with. Two `java-matrix --prepatcher` bugs found and fixed: the agent was appended after the main class in the argument file (an application argument, so never an agent), and every Fast Rendering variant shared one `fr.filtered.vmparams` (now `fr.filtered-<variant>.vmparams`). Prepatcher 0.18.4 then runs on Java 27 and 28 (GRP-ARK-AOTD-J27FRP2, -J28FRP-20261012); `SKIPPED_ERROR aotdCleanDeficitPath` on every Java. Tests: `tests/test_aotd_compat.py`. Details: `docs/AOTD_SWEEP_2026-10-12.md`, `docs/AOTD_COMPAT_PLAN.md`.

<!-- page-nav:start -->
> Continued on page 3: [ROADMAP-3.md](ROADMAP-3.md).
<!-- page-nav:end -->
