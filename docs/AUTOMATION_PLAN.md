# BridgeForge automation plan: less hand work (ROADMAP item 73)

Owner request 2026-10-14: "design a roadmap plan for further automation, fixers, checks and anything that would let
bridgeforge do more in terms of hand work", then "write the plan so it can be implemented by any AI". Item 73 remains planned;
existing tools named below are foundations, not evidence that these extensions are complete.
This file is the specification: each work item names the files to touch, the behaviour, the tests and when it is done. An
implementer needs this file, `CLAUDE.md` and the code; no chat history.

Revision 2026-10-17: owner "ok add/modify roadmap with these recommendations and if possible a plan on how to implement for other agent."
See [ROADMAP_IMPLEMENTATION_HANDOFF.md](ROADMAP_IMPLEMENTATION_HANDOFF.md), item 75, for R1-R8 implementation contracts.
These refine items 70/73. No implementation or live validation is claimed by this planning revision.

2026-10-18 source-audit warning: DOC-001 in `BUGS.md` records that current archive refresh deletes the old artifact,
contrary to owner policy. R5/H2 finalization must fix preservation before using this path; do not refresh known-good
archives in the meantime. This is a blocker within S1, not a new strategic direction or completed implementation.

## 1. Owner decisions (recorded 2026-10-14)

| # | Decision | Answer | Applies to |
|---|---|---|---|
| 1 | May crafted descriptions be drafted for review in batches (marked crafted and credited)? | **Yes** | D1 |
| 2 | May one ruling become a standing approval for every mod with the same question (three or more prior answers)? | **Yes** | C1, B4 |
| 3 | May an agent's change be accepted without a person when every gate passes? | **Yes** | E2 |
| 4 | May overnight regression runs use the rig unattended on a schedule? | **Yes, on the dedicated rig only** (2026-10-14, owner: "follow your recommendations"): the rig's `starsector-core` must be a junction, results are reported and never acted on automatically, and a run that finds a regression stops the schedule until a person looks | G2 |
| 5 | Which archived mods with a lost feature get a re-creation plan? | **After the sweep** (same date): build E4 and the `Done/` sweep first; the owner then picks per mod, from the list | E3 |

## 2. Evidence

Measured 2026-10-14 on `main` (`d7a57d68`) with `python -m bridgeforge finding-stats --json` (latest stored scan per
workspace, accepted baselines subtracted):

| Fact | Number |
|---|---|
| Workspaces / scanned / archives in `Done/` | 316 / 300 / 171 |
| Mods by hardest tier: none, auto, input, decision, inspect, code | 94, 21, 37, 56, 3, 89 |
| Unattended now / with every mechanical fixer | 115 / 115 (no mechanical gain left) |
| Fixers (`fixers.SUPPORTED_FINDINGS`) / standing approvals (`In operation/AUTOMATION_POLICY.json`) | 56 / 18 |
| Escalation packets on disk / `ESCALATION_REVIEW.md` files | 662 / 102 |

Many stored scans predate later fixes (several newest scans are from 2026-09-29), so these counts overstate what is open; A1
re-measures. Tiers are defined in `bridgeforge/automation_tiers.json`.

Largest blockers ("unlocks": mods for which this is the only id between them and an unattended revival):

| Finding | Tier | Mods | Unlocks | Packets |
|---|---|---|---|---|
| `description-missing` | input | 86 | 27 | 55 |
| `content-reference-unresolved` | decision | 18 | 7 | 15 |
| `obfuscated-internal-api-use` | code | 12 | 5 | 0 |
| `preset-entry-drops-vanilla-fields` | decision | 20 | 4 | 4 |
| `settings-json-override-breadth` | decision | 10 | 4 | 0 |
| `system-generation-unguarded` | code | 38 | 3 | 12 |
| `loose-script-compile-error` | code | 15 | 3 | 0 |
| `wing-op-cost-blank` | input | 7 | 3 | 0 |
| `source-import-unresolved` | decision | 18 | 1 | 18 |
| `player-text-non-english` | decision | 19 | 0 | 16 |
| `vanilla-path-shadowing` | input | 12 | 2 | 12 |
| `local-weapon-spec-unregistered` | input | 9 | 0 | 9 |

Open although tier `auto` with a standing approval: `hard-coded-campaign-entity-reference` (54 mods),
`hard-coded-campaign-system-reference` (41), `variant-wings-exceed-bays` (14), `csv-row-extra-columns` (11). Not standing-approved
but tier `auto`: `hullmod-instance-state` (40). The ledger's `promote_to_fixer` list names code-tier ids agents fixed and
BridgeForge verified with no fixer: `loose-script-compile-error` (5 verified fixes), `campaign-memory-live-object` (4),
`orbit-period-computed-unguarded` (4).

## 3. Rules for the implementer

1. Read `CLAUDE.md` first; its non-negotiables, hardening rules and test conventions apply to every item. In particular:
   writes through `safeio.atomic_write_text`/`atomic_write_json`; jar entries through `zipsafe.read_limited`; new finding ids
   need a tier in `automation_tiers.json`, a test that names them and a `docs-index` run; a new command is a `cmd_*.py` or own
   module listed in `cli_commands.COMMAND_MODULES`, and changes the golden `--help` hashes (`python -m tests.test_cli_golden
   --write`, review the diff).
2. `MANUAL` and `UNKNOWN` findings are never auto-applied. Confidence (SAFE/REVIEW/MANUAL/UNKNOWN) and automation tier
   (none/auto/input/mechanical/decision/code/inspect) are separate. Repeated verified applications support promotion;
   they do not by themselves establish SAFE confidence or authorize balance/save changes.
3. `bridgeforge/fixers.py` is 3,899 lines (soft ceiling 800). Put new fixers in a new module per family (`fixers_guards.py`,
   `fixers_data.py`, ...). The new module imports helpers at call time (`from . import fixers as _f` inside functions) to avoid an
   import cycle; `fixers.py` imports the new functions immediately above `_FIXER_FUNCS`, adds them there and to
   `SUPPORTED_FINDINGS`. A fixer has the signature `(root: Path, options: dict) -> list[FileChange]`, raises `FixerError` to
   refuse, edits only the located spans (line endings, BOM, comments survive), and must be idempotent (a second run computes no
   change, which `compute_fix` turns into `FixerError("No change ...")`).
4. Fixtures come from real cases: copy the smallest file excerpt that reproduces the finding from the named mod's `original/`
   into the test as a string; never commit game files.
5. Long commands follow the long-running rule (`progress.report`, `progress.Checkpoint`, `LONG_RUNNING_COMMANDS`).
6. One item per commit, subject "Add item 73 <id>: ...", body ends with the full-suite result. Mark the sub-item done in
   ROADMAP item 73 with the tests that cover it.
7. Work needing the game, a rig or `In operation/` that you cannot run: add a `docs/LOCAL_HANDOFF.md` entry and say so.

## 4. Work items

Each item: **Files**, **Behaviour**, **Tests**, **Done when**. Order is section 5.

### Phase A: measure and close the loop

**A1. Fresh baseline (run, no code).**
Run `python -m bridgeforge finding-stats --scan --write bridgeforge-state/finding-stats/<date>` in the background (about 45
minutes; it checkpoints). Copy the bucket table and top-20 blockers into ROADMAP item 73 as the "before". Done when: the
dated `FINDING_STATS.md` exists and the roadmap quotes it.

**A2. Content-based scan freshness (R2).**
- Files: `bridgeforge/finding_stats.py`, `bridgeforge/cmd_scan.py`, scan report writer; details in item 75.
- Behaviour: register scans regardless of output-folder name, with hashes of actual scan inputs, dependency/core inputs,
  target, scanner/check revisions and relevant options. Timestamps are hints, never freshness proof. Legacy scans without
  fingerprints are UNKNOWN; unreadable inputs are INCOMPLETE. Generated reports must not invalidate their own scan.
  `--rescan-stale` refreshes stale/unknown inputs and reuses only matching complete records.
- Tests: changed bytes with unchanged mtime, changed provider/check/options, nonstandard output directory, missing legacy
  fingerprints, generated-report exclusion and selective rescan.
- Done when: CURRENT means matching content and analysis context; A1 distinguishes current, stale and unknown results.

**A3. Why an auto-tier finding stays open.**
- Files: new `bridgeforge/auto_open.py`, command `auto-open QUEUE [--json]` (own module, registered).
- Behaviour: for each workspace and each open finding whose tier is `auto`, give one reason: `NOT_APPROVED` (no standing
  approval, not in `--approve` history), `FIXER_REFUSED` (newest ledger entry for that id has state `FIXER_REFUSED`; quote its
  reason), `NEVER_REVIVED` (no ledger), `STALE_SCAN` (A2), or `UNEXPLAINED`. Print counts per id and reason, then per mod.
  Read-only.
- Tests: `tests/test_auto_open.py`: one fixture per reason built from ledger lines and a stored scan.
- Done when: run on `In operation/`, every open auto-tier finding has a reason; `UNEXPLAINED` cases are written into ROADMAP item
  73 as bugs to fix. Expected first use: `hullmod-instance-state` (40 mods) shows `NOT_APPROVED`; decide its standing approval
  with `escalation rule --approve-fixer` (decision 2 allows it when its ledger shows three verified applications).

**A4. Promotion candidates with fixtures.**
- Files: `bridgeforge/finding_stats.py` (where `promote_to_fixer` is built), new `bridgeforge/promotion.py`, flag
  `finding-stats --promotion DIR`.
- Behaviour: for each `promote_to_fixer` id, collect each accepted attempt's diff (attempt folders that `escalation apply`
  copied; `escalation_review.review_attempt` already computes the diff against the start file). Group hunks by a normalised
  shape: identifiers replaced by `ID`, string literals by `STR`, numbers by `NUM`, whitespace collapsed. Write
  `DIR/PROMOTION_CANDIDATES.md`: per id, per shape, the count, the mods, one before/after pair (at most 40 lines each), and the
  file kind.
- Tests: `tests/test_promotion.py`: two fake attempts with the same edit shape on different identifiers group into one shape;
  a different edit makes a second shape.
- Done when: the file exists for the three promotion ids and B1/B2/B3 cite its shapes.

### Phase B: fixers from verified agent work

All B fixers: new module per section 3.3, registered, REVIEW confidence until the narrow cause/replacement is evidenced
and meets the SAFE contract. Three verified applications are promotion evidence, not automatic SAFE classification.
Automation tier stays recorded separately in `automation_tiers.json` (move an id from `code` to `auto` only when the
fixer covers every supported A4 shape with explicit refusal boundaries and authorization; otherwise retain `code`).

**B1. Generation and orbit guards** (`system-generation-unguarded`, `orbit-period-computed-unguarded`).
- Files: `bridgeforge/fixers_guards.py`; scanner checks are in `scan_campaign.py` (read them for the exact evidence fields).
- Behaviour: (a) `system-generation-unguarded`: at the start of the flagged generate method, insert
  `if (sector.getStarSystem("<name>") != null) return;` where `<name>` is the system name literal the method passes to
  `createStarSystem`, and `sector` is the method's `SectorAPI` parameter name (or `Global.getSector()` if none). Refuse when the
  name is not a single string literal or when the method already contains `getStarSystem(` on that name. (b)
  `orbit-period-computed-unguarded`: wrap the computed period expression `E` as `Math.max(1f, E)`; refuse when the expression
  spans lines or is already wrapped. A clamp is allowed only for a proven finite expression and justified one-day minimum;
  it does not repair NaN or infinity. Refuse side effects and ambiguous fallbacks. A generation early-return is allowed
  only when skipping the complete method preserves required setup; otherwise refuse. Both refuse jar-shadowed scripts.
- Tests: `tests/test_fixers_guards.py`: fixtures from Vacuum and zzz-Bingus-Sustem (`original/`), idempotence, each refusal.
  Add NaN/infinity, side-effect and multi-purpose generation refusal cases. Compilation skipped for lack of a core is
  incomplete evidence and cannot qualify a code change for E2.
- Done when: on the 38 + 16 mods, `revive` applies it or records a refusal; `finding-stats` count drops.

**B2. Compile-error rewrites** (`loose-script-compile-error`).
- Files: `bridgeforge/signature_rewrites.py` (`RULES`), `bridgeforge/fixers.py` (`_fix_rc8_signature_changed` already applies
  `RULES`); the API drift catalogue from P14 item 47.
- Behaviour: add one `RULES` entry per A4 shape that maps a removed or changed RC8 member to its replacement. Each entry carries
  a comment with the javap line for the RC8 member and the date (house rule). After rewriting, the fixer's verifier is
  `compile-check`; a rewrite that leaves the file failing to compile is reverted and reported.
- Tests: `tests/test_signature_rewrites.py`: one before/after per new rule from Mountain-and-Sea and Smol-Shippack.
- Done when: those two mods compile clean through `revive` without an agent.

**B3. Detach-before-save template** (`campaign-memory-live-object`; ROADMAP 68d).
- Files: new `bridgeforge/detach_template.py`, command `detach-template WORKSPACE --finding KEY --out DIR`.
- Behaviour: from the finding's evidence (class, field names holding `MarketAPI`/`SectorEntityToken`/`CampaignFleetAPI`), write a
  wrapper plugin source `BfDetach<Mod>Plugin.java` that in `beforeGameSave` stores ids in memory and nulls the fields, in
  `afterGameSave` and `onGameLoad` restores them by id lookup. Modelled on `In operation/_patches/station-augments`
  (`niko_SA.BfSAModPlugin`). Never edits the mod; output is a patch directory plus `README.md` with the save-reload test to
  run (probe `--save-after-checks`, RC8-29). REVIEW.
- Tests: `tests/test_detach_template.py`: generated Java for a two-field fixture contains both fields in all three hooks and
  compiles with `javac` when a JDK is available (skip otherwise).
- Done when: running it on Station Augments' original finding reproduces the shipped plugin's structure. Live proof is a
  LOCAL_HANDOFF entry.

**B4. Preset field merge** (`preset-entry-drops-vanilla-fields`).
- Files: `bridgeforge/fixers_data.py`; scanner check in `scan_settings.py` or `scan_data_rules.py` (grep the id).
- Behaviour: for a preset entry that replaces a vanilla entry whole, add back each vanilla field the mod's entry lacks, value
  from RC8's file (`options["vanilla_core"]`), keeping every mod value. Refuse when the vanilla core is not given. Insert with
  the file's own indentation. Missing fields may be intentional: apply only a field-specific approved proposal or a C1
  ruling with matching semantic conditions, never approval based only on the finding id or three arbitrary mods.
- Tests: fixture with a vanilla entry of five fields and a mod entry of three; result has five, mod values kept; idempotent.
- Done when: the 20 mods are fixed or refused with a reason.

**B5. Values from comparable rows** (`wing-op-cost-blank`, `carrier-bays-proposal`).
- Files: extend `_fix_wing_op_cost_blank` (fixers.py) to accept `options["proposals"]`; new `bridgeforge/value_proposals.py`,
  command `value-proposals WORKSPACE --write SHEET.csv` and `--apply SHEET.csv`.
- Behaviour: for each blank OP cost, propose the median OP of the mod's own wings with the same role and size, else vanilla's
  (`wing_data.csv` in the core); the sheet shows the comparison rows. The owner fills or confirms the `approved` column;
  `--apply` passes approved values to the fixer. Bays: same with hull size and the mod's own carriers.
- Tests: `tests/test_value_proposals.py`: median from three comparable rows; vanilla fallback; only `approved=yes` rows applied.
- Done when: the 7 + 2 mods have a sheet; applying an approved sheet clears the finding.

**B6. Missing weapon row** (`local-weapon-spec-unregistered`).
- Files: `bridgeforge/fixers_data.py`.
- Behaviour: prefer an evidenced original/version/sibling row for the same weapon identity. Otherwise draft a comparable
  row as a proposal only, listing every copied value and its source. Type/size similarity does not establish balance.
  Drafting writes reports only; applying needs owner approval of the exact row and an unchanged input fingerprint.
  `specClass` is not a display-name source. Refuse missing required evidence.
- Tests: exact-source preference, drafts do not edit data, unapproved/stale proposal refused, approved scoped application.
- Done when: each mod has an evidenced row or review proposal/refusal; balance inference is never applied unattended.

**B7. Import resolution from the provider index** (`source-import-unresolved`).
- Files: `bridgeforge/revive.py` (`content_options`, `build_packets`), `bridgeforge/substitutes.py` (`merged_providers`).
- Behaviour: when exactly one provider in the index exports the unresolved package, add a `fix_options` entry that runs the
  `undeclared-library-dependency` fixer with that provider's id and version. When none does, attach to the packet the API drift
  catalogue entry for the package if one exists, else "not provided by any indexed mod".
- Tests: `tests/test_revive.py`: fake index with one provider resolves; with two providers no auto option, both named.
- Done when: the 18 packets either resolve or carry the new evidence.

### Phase C: decisions answered once

Existing tools: `escalation queue` (which mods one decision would clear) and `escalation rule` (`escalation_queue.rule`: accept in
every escalated mod's baseline, or add a standing approval). Build on them; do not add a parallel mechanism.

**C1. Decision sheet with precedent.**
- Files: `bridgeforge/escalation_queue.py`, new subcommands `escalation sheet QUEUE --write SHEET.csv` and `escalation sheet
  --apply SHEET.csv`.
- Behaviour: group open decision-tier findings across the queue by `(finding id, question shape)`, where the shape is the
  finding's explanation with ids, paths and numbers replaced by placeholders. For each group list the mods, and precedent: earlier
  rulings for the same id from `ESCALATION_RULINGS.jsonl` and baseline reasons in any workspace (`baseline.mod_baseline_path`).
  Columns: `group, finding, shape, mods, precedent_count, precedent_answer, answer (accept|approve-fixer|skip), reason`.
  Pre-fill `answer` and `reason` from precedent when three or more earlier rulings agree (decision 2) and mark the row
  `prefilled=yes`. Shape grouping is presentation only. Standing eligibility needs three independent prior mods with the
  same versioned semantic predicate (target API/provider, relevant fields/values, intent and save/balance risk), no
  conflicting/revoked ruling, and complete evidence. Missing predicate fields prevent automatic reuse; retain relevant
  numbers and ids. Apply only explicitly answered rows or eligible standing rulings; untouched suggestions are not
  approvals. Log source ruling ids, predicates and hashes with "standing approval from N prior rulings". MANUAL/UNKNOWN,
  gameplay and save decisions remain person-only. Tests also cover contradictory, revoked and superficially similar rulings.
- Tests: `tests/test_escalation_queue.py`: grouping by shape; prefill only with three agreeing precedents; `--apply` calls `rule`
  once per row and never for `skip`.
- Done when: one sheet covers all 56 decision-tier mods.

**C2. Precedent in packets.**
- Files: `bridgeforge/revive.py` (`render_packet`).
- Behaviour: a decision packet gets a "Answered before" section: up to five earlier rulings for the same id (mod, answer, reason,
  date). Uses the C1 lookup function.
- Tests: rendered packet contains the section when a ruling exists, none otherwise.

**C3. Substitution proposals** (`content-reference-unresolved`).
- Files: `bridgeforge/substitutes.py`, `bridgeforge/renamed_ids.py`, `bridgeforge/provider_renamed_ids.py`, the removed-content
  catalogue (P14 item 8; grep `removed` in `bridgeforge/` for its file).
- Behaviour: for each unresolved id, propose in order: a rename found by `find_renamed` between the reference rig the mod targets
  and RC8; a provider rename (`provider_renamed_ids`); a catalogue entry naming the vanilla replacement. Each proposal carries its
  evidence. Approved proposals are applied by a fixer `content-reference-substitute` (new, REVIEW) that rewrites only the id in
  the referencing file.
- Tests: one fixture per proposal source; fixer rewrites one id and nothing else.
- Done when: the 18 mods carry proposals; live proof of an applied substitute is a LOCAL_HANDOFF entry (a missing weapon is a
  Fatal at New Game, so a New Game run is the proof).

**C4. Settings override classification** (`settings-json-override-breadth`).
- Files: the check (grep the id under `bridgeforge/scan_settings.py`).
- Behaviour: classify each overridden key as `add` (a list that RC8 merges, the rule of ROADMAP P15 item 19 and `settings_keys.py`),
  `same` (value equal to RC8's) or `change`. Report only `change` keys at the current severity; `add`/`same` become
  informational. No fixer.
- Tests: three keys, one per class.
- Done when: the 10 mods show only real changes.

### Phase D: input work drafted, owner reviews

**D1. Description drafts** (decision 1: yes).
- Files: `bridgeforge/descriptions.py` (`build_sheet`, `apply_draft`), `bridgeforge/sibling_assets.py` (already copies byte-identical
  description rows from sibling mods), new subcommand `descriptions draft WORKSPACE|QUEUE`.
- Behaviour: for every missing description, fill `reports/description-drafts.md` in the table format `parse_draft` reads, from the
  first source that has the id: (1) another version of the same mod (`Done/`, `original/` of a sibling workspace with the same
  `mod_info.json` id, reference rigs' `mods/`); (2) a sibling mod of the same pack (reuse `sibling_assets`); (3) a crafted draft
  from the mod's own data: hull size, designation, manufacturer, system, notable weapons or role, written by an agent through
  `translate_batch.agent_translator`-style chunking with a fixed prompt (two to four sentences, in the mod's own tone, no
  invented lore names). Every row records its source; crafted rows are marked `crafted` so `apply_draft` lists them in
  `BRIDGEFORGE_CREDITS.txt` (it already does). The owner reviews the sheet; `descriptions apply` writes it.
- Tests: `tests/test_descriptions.py`: source order (version beats sibling beats crafted); crafted rows marked; agent stubbed.
- Done when: drafts exist for all 86 mods; after the owner's review and `apply`, `description-missing` is no longer the top
  blocker.

**D2. Translation with memory.**
- Files: `bridgeforge/translate_batch.py`, translation memory in `bridgeforge-state/translations` (read its format first).
- Behaviour: before sending a chunk to the agent, replace every string already in the memory with its stored translation and send
  only new strings; after verification add new pairs to the memory. Report reused/new counts. The review sheet shows source and
  translation side by side.
- Tests: `tests/test_translate_batch.py`: a chunk with two known and one new string sends one string to the stub translator.
- Done when: re-translating an already translated mod sends nothing to the agent.

**D3. Shadowing triage** (`vanilla-path-shadowing`).
- Files: `bridgeforge/fixers.py` (`_fix_vanilla_path_shadowing`), `bridgeforge/reference_rigs.py`.
- Behaviour: for each shadowed file compare it with the same path in the reference rig the mod targets. If byte-identical (the
  mod shipped an unchanged copy of old vanilla), the fixer moves it to `scratch/removed-shadow/` (explainable by
  `explain_proofs.kept_elsewhere`) only after a matching owner/standing approval. Identity to old vanilla establishes
  provenance, not lack of intent. Show old-vanilla/mod/current-RC8 differences first; retain unapproved files.
- Tests: identical-but-unapproved retained; approved move backed up; changed file kept; stale approval refused.
- Done when: each shadow has a reviewed disposition or open proposal, not a target count of removed overrides.

### Phase E: escalation that reviews itself

Existing: `escalation review` writes `ESCALATION_REVIEW_SHEET.md` (`escalation_review.review_sheet`) with diffs and flags;
`escalation.verify` decides VERIFIED.

**E1. Complete review sheet.**
- Files: `bridgeforge/escalation_review.py`.
- Behaviour: per attempt add the verifier result, files changed outside the packet's `allowed_files`, the scan delta (finding ids
  removed and added), and the compile-check result before/after. End with one line per packet: `AUTO-ACCEPTABLE` (E2 rules
  hold) or `NEEDS REVIEW: <which rule failed>`.
- Tests: `tests/test_escalation_review.py`: one attempt per outcome.

**E2. Auto-accept** (decision 3: yes).
- Files: `bridgeforge/escalation.py` (`run_packet`, `apply_verified`), flag `escalation run --auto-accept`.
- Behaviour: apply a verified attempt without a person only when all hold: verifier VERIFIED; no file outside `allowed_files`;
  the packet's finding is gone and no new finding of tier above `none`; compile-check not worse; no `escalation_review.FLAGS`
  flag fires; lines deleted not more than lines added plus ten. Log `auto_accepted: true` with the rules checked in
  `ledger.jsonl`; list them in the run summary and in `revive-review`. Anything else stays for the sheet. The archive gate is
  unchanged (live test still required).
- Required R3 gates: exclude MANUAL/UNKNOWN, save migrations, gameplay decisions and maintained third-party edits.
  Record PASS/FAIL/INCOMPLETE/NOT_APPLICABLE plus applicability reasons. Missing tools, timeouts and absent fixtures are
  INCOMPLETE. Applicable compiler and regression checks must execute on final packaged bytes; data-only work may justify
  compilation NOT_APPLICABLE. Recheck packet/attempt/policy/tool and working hashes immediately before atomic application,
  protecting against concurrent edits and partial application. Line-count and regex checks are extra signals, not proof.
- Tests: one passing attempt is applied; each rule, failing alone, blocks it.
- Done when: an agent batch applies passing attempts unattended and the sheet lists only the rest.

**E3/E4. Lost features** (ROADMAP item 72).
- E4 first: finding `port-dropped-feature` (REVIEW) in a new `bridgeforge/scan_port.py`, run by `scan` when the workspace records
  a port source (read how Templars 0.9.8f's port is recorded). Lists classes by package, `events.json` ids, `reports.csv` ids,
  settings keys and `rules.csv` triggers present in the old version and absent in the new.
- E3: extend the existing `legacy-event-report-noop` (`scan_fleets.py`) into `legacy-event-system` per item 72a, only after the
  live proof (does RC8 advance a mod-registered event plugin?) is a row in `docs/RC8_BEHAVIOUR.md`; until then write the
  LOCAL_HANDOFF entry. Packet kind `recreation` writes a plan skeleton with the section headings of
  `docs/TEMPLAR_CRUSADE_PLAN.md`. Which mods get a plan is decision 5.
- Tests: `tests/test_scan_port.py` with two fixture versions; the packet skeleton has every heading.

### Phase F: checks for crash classes found by hand

Each: new id, tier, test naming it, corpus sweep for false positives before merging (`corpus-recheck` or `finding-stats --scan`
on a sample; ROADMAP 60d found 60 false hits before narrowing). Report the sweep numbers in the commit body.

- **F1. `market-on-hyperspace-entity`** (ROADMAP 58): `addMarket`/`setMarket` on an entity created with
  `getHyperspace().addCustomEntity` or added to `getHyperspace()`, in loose scripts and jar string/call evidence. REVIEW.
- **F2. `saved-object-live-reference`** (60g(4), 68d): fields typed `MarketAPI`, `SectorEntityToken`, `CampaignFleetAPI`,
  `PlanetAPI` in classes that are stored in memory, added as listeners or scripts (`addScript`, `addListener`,
  `getMemoryWithoutUpdate().set`). REVIEW; the packet points to B3.
- **F3. Provider renames beyond industries** (rest of 60d): extend `provider_renamed_ids.py` to hull mod, commodity and condition
  ids, with the same "declared provider only" rule.
- **F4. Mission variant outside the group**: in the mission-variant check, when a variant is missing, name the indexed provider
  that defines it (`substitutes.merged_providers`) and whether the mission guards it; covers Vayra's Ship Pack and Kadur Remnant
  (open in `docs/LOCAL_HANDOFF.md` section 0).
- **F5. `mission-map-reference-missing`**: background, planet and nebula references in `MissionDefinition.java`
  (`setBackgroundSpriteName`, `addPlanet`, `addNebula`) resolved against the mod and RC8.
- **F6. Obfuscated member classification** (`obfuscated-internal-api-use`): resolve each referenced obfuscated member with
  `javap` against RC8's jars (the `bytecode`/`linkage` modules already read class files); members that still exist become
  informational with that evidence, missing ones stay.

### Phase G: live testing without a person

All need the rig; build and unit-test offline, then a LOCAL_HANDOFF entry for the live proof.

- **G1. Generic New Game driver** (60g(2)): in `live_run.py`, a fallback flow that uses `screen_read` to find the bottom-right
  confirm button on each New Game page and the first selectable row, up to N pages, logging a screenshot per page. Keep the
  Nexerelin and default flows first. Done when two total conversions besides Nexerelin start unattended.
- **G2. `probe-group regress --changed-since COMMIT`**: rerun only archives whose probe, harness or shipped files changed; write
  per-archive verdicts and only print changed ones. Build and test; scheduling waits for decision 4.
- **G3. `rig-up RIG --mods ID... [--probe-config]`** (idea 1 of 2026-10-06): sync working copies, write `enabled_mods.json`, probe
  config, SpeedUp, run `rig-doctor`; record the rig state (enabled ids, versions, hashes) in the run record. Refuses unless
  `starsector-core` is a junction (house rule).
- **G4. Launch watchdog** (60f(4)): in `bf-test.ps1 launch` and `boot_test`, no java process under the rig 60 s after launch ends
  the run with `LAUNCH_NO_PROCESS`.
- **G5. Group accept**: `probe-group record --accept` calls `live_accept.accept_run` per PASS member, carrying probe FAIL lines
  that match an earlier accepted reason for the same mod version, stopping on any other.
  R1 applies to group and standalone acceptance: require pre-launch staged-input manifests, final drift checks, run/log
  identity and scenario-specific milestones. Waivers also need matching finding/check/context evidence, not just version.
  Legacy runs without manifests stay historical evidence. G2 selects by dependency/probe/launcher hashes as well as Git.
- **G6. Raid scenario mod**: separate test mod under `probe-mod/raid-mod/` allowed Nexerelin classes; forces a raid on a market
  named in its config; logs `raid-start`/`raid-end`. Turns "raid path unobserved" (item 56) into a test.

### Phase H: archive and revision chores

- **H1. Finish 60b**: add `audit-explain --auto` proofs for files under `scratch/translator-workspace/` and `scratch/removed-src/`
  (`explain_proofs.MOVED_FOLDERS` already lists them; check which are wired), extracted zip originals, `reports/translation/*.json`
  copies, and a colliding `Done/<Mod>` moved to `Done/_replaced-<date>/`. Done when re-running the audit on Ironclads, Nightcross
  and the GRP6A mods leaves under a tenth of their differences.
- **H2. Revision lifecycle (R5):** proposed `revise prepare WORKSPACE "what changed"` bumps once and records a candidate
  without archiving. Test that candidate through R1. Proposed `revise finalize WORKSPACE --revision ID --test-id ID`
  never bumps or edits tested files: verify exact candidate/run, gates and outward-action authorization, then refresh
  archives and snapshot. Use a durable journal for idempotent retries and preserve previous archives.
  Tests: prepare/test/finalize, repeated calls, post-test drift, stale run and failure/restart at each step. These commands
  are proposals until implemented; see item 75 for states and recovery.
- **H3. Migration pack with a revision** (idea 8): when `revise` sees renamed ids or classes against the previous archive
  (`content_diff`), require a migration pack per `docs/MIGRATION_PACK_CONTRACT.md` checked by `save-compat`, or a written reason.

## 5. Order

| Step | Items | Why |
|---|---|---|
| 1 | R7 initial audit; R2/A2, then A1/A3; R1 independently | current inputs before authoritative counts; establish live provenance |
| 2 | D1 | largest blocker (27 mods unlock); decision 1 given |
| 3 | C1, C2 | 56 mods; decision 2 given |
| 4 | A4, B1, B2, B7 | ledger-proven, most packets |
| 5 | R4 and R3/E1 report-only; E2 after R1-R4 gates pass | standing approval and applicable checks must be evidenced |
| 6 | G3, G4, G5, R5/H2 | manifest-bound runs; prepare/test/finalize instead of bump-and-archive |
| 7 | B3-B6, C3, C4, D2, D3, F1-F6 | each smaller, evidence first |
| 8 | G1, G2, G6, E3/E4, H1, H3/R6, R8 | live scenarios, upgrade proof and restore qualification |

After steps 1, 2, 3 and 4 run `finding-stats --scan --write` again and put the bucket table in ROADMAP item 73 with the date.
The 2026-10-17 dependency refinement takes precedence over the table: R2/A2 precedes authoritative A1 measurement;
R1-R4 precede enabling E2 (E1 evidence-only work can proceed earlier); R5 precedes automated revision finalization;
R6 precedes live acceptance of migrations; R8 precedes snapshot-based machine cutover. R7 reconciles status first.
Independent drafting/report work can proceed meanwhile. The ordered implementation handoff is in item 75.

## 6. Left out on purpose

- Automatic changes to gameplay balance, faction roles or fleet composition (the Exipirated roles change stayed an owner revision).
- Hull mod per-ship-state rewrites inside jars (ROADMAP 60: needs judgement).
- Editing maintained third-party mods in place (68e: wrapper plugins only).
- Decompiler-based fixes for source-less jars.
