**97. The S series' remaining work, re-queued without gates (owner 2026-11-17: "Park S4. Stop treating S2 and S3 as gates.
Check S series implementation plan and if applicable add remaining items to roadmap queue").**
**Approved; queued after items 95 and 96.** From docs/S_SERIES_IMPLEMENTATION_PLAN.md's "what remains" table (status check
2026-10-26). Each is now an ordinary item: no S-series acceptance waits on it, and it waits on nothing in the S series.
- 97.1 (M) **Copied-save upgrade pilot** (S3.3; owner-approved 2026-11-01, "copied save pilot is approved").
  - Scope: the synthetic `bf_s3_generation_control` seed only, in a new isolated rig, as docs/S3_COPIED_SAVE_PILOT_PLAN.md
    sets out.
  - Build first: an in-game observer that saves to a separately named slot (`ExistingSaveReloadStage` saves to the slot it
    loaded from), and an S3 case adapter for `evaluate_upgrade`.
  - Then one rig run: load the old save with the new build, save to the new slot, restart, reload and compare.
  - It is the base for upgrading real saves on a new game build (95). Not started.
- 97.2 (S) **Recipe reuse, the owner's look at one case** (S2.3, docs/S2_RECIPE_GOVERNANCE.md). `data-file-not-utf8`
  stays BLOCKED until the owner looks at one case where fixing the encoding exposes `rules-csv-curly-quote-unreadable`
  (All the Domain Drones or Metelson). Present that case with evidence and a recommendation, then record the ruling.
  - Two recipes are ready for owner review and 24 need more evidence (the 2026-11-01 trial).
  - A reserved holdout with providers and affected-case invalidation remain to build, as reuse earns them.
- 97.3 (M) **Scenario families and maintained qualification** (S3.2, S3.4). New-game, campaign, combat and integration
  families, each with a healthy and a known-bug control. When a provider, rule or candidate changes, the obligations it
  affects reopen. Carried by 93.30 (the scenario testbed) and 95.11 (targeted re-validation), not as a separate track.
  **Closed 2026-11-19 (roadmap review): superseded by 93.30 and 95.11.**
- 97.4 (S) **Measured review minutes** (S2 overall). Measure the owner's active review time only when a speed-up claim
  is made; it is no longer an acceptance step.
  **Closed 2026-11-19 (roadmap review): culled.** A standing rule, not work: measure review minutes only when a speed-up is claimed (owner parked it).
- 97.5 (S) **Roadmap review** (owner 2026-11-19: "Work in whatever order you think is optimal. Anything you deem low value or
  not really helpful you can cull from roadmap."). Every open item from 78 to 97 was read, except the 94.G series and
  96.5 P9/P10. 42 items now end in a `**Closed 2026-11-19 (roadmap review): ...**` line, each with its reason; no text was
  removed:
  - already built, with the file or check that does it (15): 78.1-78.8, 79.2, 82.5, 82.10, 82.11, 87.5, 88.1, 93.19;
  - superseded by the item named in the line (14): 97.3, 93.14, 93.21, 93.27, 93.29, 93.32, 93.34, 93.35, 87.9, 87.11,
    85.1, 86.3, 86.4, 86.6;
  - culled as low value (13): 86.1, 86.2, 86.5 (AoTD; the owner set it aside on 2026-11-17), 85.2, 88.18, 93.23, 97.4,
    87.6, 82.6, 79.3, 79.5, 79.6 (sister-repository features) and 88.11 (a stale merge order).
  Kept although they looked cullable: 95.6 (the owner approved it as optional), 90.4 and 90.5 (item 90 is owner-approved)
  and item 84 (nothing records that the 94.G series replaced it).
  The order for the rest (owner: "whatever order you think is optimal"): 96.5 P5/P8, 93.51, P9, P10, 95.5, then the 94.G
  series, with Test1 work (93.x rig items, 95.4, 95.11, 96.2) between CI waits.
- Parked (owner 2026-11-17), with the reason recorded beside the S-series entry below:
  - S4.1 supported configurations;
  - S4.2 private exchange and recovery;
  - S4.3 the second-operator trial;
  - S4.4 support and publication commitments.

**96. Skills, the abandoned mods' RC7 ports, a docs pass and a release (owner 2026-11-17: "Go ahead and create earlier skills and utilize other skills mentioned"; "AOTD is active and undergoing a overhaul so we can safely ignore it for now. The others mentioned are abandoned so we will have to do the hard work behind reviving them"; "If need be make sure to bump versions/releases. Also add to queue you or an agent review/update all related docs then sync to github").**
**Approved.** Queued after item 95's small items.
- 96.0 **Owner decisions on the RC8 -> RC7 catalogue (95, 2026-11-17).**
  - Done/ keeps only the latest archive of each mod id ("Only keep latest"). The seven older copies moved, unchanged, to
    `Done/_replaced-2026-11-17/` on Test1, with a README. Neutrino 1.8.9 (gameVersion 0.97) is kept over Nostalgia Edition
    1.87-RC3 (0.95.1a-RC6).
  - Nightcross is closed as SUPERSEDED once 95.15 merges.
  - KoC's G3 record, which names Tania's save, matters only to the record and is left as it is (93.38 fixes new records).
- 96.1 **Done 2026-11-17.** **Skills.**
  - In this repository, `.claude/skills/`:
    - `bridgeforge-pr`: the commit and PR routine, with `scripts/checks.sh` (ruff, roadmap-lint, docs-index, the golden and
      index tests) and `scripts/mutate_check.py`;
    - `bridgeforge-revive`: one mod from intake to archive, with the traps found on 2026-11-16/17;
    - `bridgeforge-catalogue`: Done/ against a new build.
  - On both machines, not here because the repository is public:
    - `test1-run`, a one-off interactive scheduled-task runner;
    - `memory-mirror`, a SHA-256-verified mirror of memory, rules and skills.
  - Tests:
    - `checks.sh` passed every step on this branch;
    - `test1_task.sh` ran `hostname` and `git log` on Test1 and deleted its task;
    - `mirror.py --check` found the 5 changed files, and the mirror run verified 39 memory and 4 skill files identical on
      both machines.
  - Also in use: the `skill-creator` skill to write these; an independent review agent per batch of diffs, which found 11
    problems in 95's PRs, all fixed before merging. To do: `security-review` on 93.33 and `fewer-permission-prompts`.
- 96.2 **Port the abandoned archives the catalogue flagged.** Kadur Remnant (the gated `jar-call-signature-changed` fixer),
  Broken Star (`relink`), Vayra's Sector (`PersonBountyEventData.reportSuccess(int)`: decide the argument from vanilla's own
  callers, 95.14), YunruCore (`hullmod:low_maintenance` now collides with an RC7 hull mod: rename the mod's id, with a
  save-compatibility note, or keep it; owner's call with the evidence), Neutrino Corporation 1.8.9 and Station Augments
  (hand ports of calls into obfuscated game internals). Each one: `restore-from-done`, fix, live test on Test1, `+bf.N`,
  `record --archive --refresh` (the `bridgeforge-revive` skill). AoTD (Vaults of Knowledge, Theory of Toolbox) is skipped:
  active upstream and under overhaul. Nightcross is superseded.
  Lessons from the ports, 2026-11-19, as items 96.9-96.11 and additions to 95.2 and 95.3. The owner asked for a bird's-eye
  view of what to improve and said: "if these are useful now prioritize their implementation now if not save them for after
  G series implementation or at your recommended order".
  **Done 2026-11-19.** All six are archived LIVE_VALIDATED on the 0.98.5a-RC7 rig on Test1, with the owner's standing word
  ("sure archive them if they pass along anything else").
  - **Kadur Remnant:** gated `jar-call-signature-changed` fixer.
  - **Vayra's Sector 3.2.1+bf.1:**
    - `reportSuccess(int)` through the 95.14 rule;
    - three `saved-object-holds-market-ref` findings accepted as authored ("Accept as authored");
    - Vayra's own rare_flagships.csv separator-row warning accepted with the file's hash.
  - **YunruCore +bf.1:** the placeholder `low_maintenance` row dropped ("Drop placeholder").
  - **Broken Star 0.1+bf.4:** `relink`, plus the decorative weapons moved into `data/weapons/`.
  - **Neutrino Corporation 1.8.9+bf.1:** RC8's obfuscated `combat.systems.F` is RC7's `combat.systems.return`, with the same
    members. Two constants were remapped in Neutrino_FighterDroneSystemAI.
  - **Station Augments 2.4.3+bf.2** ("Port + safety net", "Accept 1-3, draft descriptions"):
    - the shield-shunt hook's six renamed classes and the interface methods were remapped in bytecode, by shape match of both
      cores, and its catch was widened to Throwable;
    - two codex descriptions were drafted and applied;
    - the original is the author's 2.4.3 GitHub release, with its asset hash checked ("Find author's 2.4.3").

  The live runs needed 93.59 (wait for the probe's save), 93.60 (GraphicsLib's cache) and 93.61 (descriptions draft), all
  merged the same day. The remap scripts are kept in each workspace's `scratch/rc7-remap/`. Station Augments' shield-shunt
  combat path needs a station with that augment in battle and was not exercised: a wrong mapping logs and skips it rather
  than crashing.
- 96.3 **Docs pass**, by an agent with review: README, `docs/BRIDGEFORGE_REVIVAL_GUIDE.md`, `docs/LOCAL_HANDOFF.md`,
  `docs/ROADMAP_STATUS.md` and CLAUDE.md against what items 93.20-93.38, 95 and 96 changed; then push.
  **Done 2026-11-17.** An agent rewrote the five files for the 0.98.5a-RC7 target. The guide gained sections 0a (intake to
  archive), 2c (`src-to-jar`, `relink`), 6b (probe-group on the 0.98.5a rig, `probe_accepted.json`, `accept`), 12c (archive,
  refresh, restore, bump, close) and 12d (`target-impact`, `target-bump`, `retarget`). Every full command example in the five
  files was parsed against the CLI parser (134 parse; 5 are shorthand). The main session reviewed the diff and corrected
  three things: Nightcross (closed, not to do), the handoff's combat re-runs (93.39) and a user-profile path in the guide's
  `$rig`. Left for later, because each needs code and a golden-file change:
  - help texts that still name RC8 (`revive --vanilla-core`, `relink`, `scan --compile-check`, `rebuild-from-reference`,
    `content-diff`, `close --reason`);
  - `rig-doctor`, which compares mods with `0.98a` and so warns about every revived mod on the 0.98.5a rig;
  - `dependency-substitutes`, which never counts a 0.98.5a provider as current.

  With 96.5 A1.
- 96.4 **Release.** Once item 95's PRs are merged: `release-notes assemble --version <next>`, the pyproject version, a PR; a
  tag only on the owner's word. Revived mods that change get their own `+bf.N` bump through `bump-version`.
  **Notes assembled 2026-11-17; the tag waits on the owner.** `release-notes assemble --version 0.4.0` moved the 88 pending
  `changelog.d/` fragments (items 79.7 to 96.6 and 93.44) under `## 0.4.0 (unreleased)` in CHANGELOG.md. The package version stays
  0.4.0, so there is no pyproject change. Salvor pins `bridgeforge>=0.4,<0.5` and BridgeForge stays its save-diagnosis provider
  (94 D4), so a 0.5 bump would also need Salvor's pin moved. Owner 2026-11-17: tag and publish v0.4.0 ("Yes"). The heading is
  dated `## 0.4.0 (2026-11-17)`, and an empty `## 0.4.1 (unreleased)` takes the next fragments.
  **Done 2026-11-17: v0.4.0 is published as a pre-release** (22:55 UTC). The receipt is `docs/RELEASE_0_4_0.md`.
  - The annotated tag `v0.4.0` peels to `128830f`, #112's merge.
  - Checked before tagging:
    - the full suite at that commit, in a clean worktree: 2969 tests, OK (skipped=12); hermeticity PASS;
    - main CI's nine jobs on that commit (run 44192728646). A tag push runs no CI since #107.
  - Wheel and sdist were built from a clean checkout. Every packaged file Git tracks equals its blob (wheel 400, sdist 721), and
    an installed-wheel check passed.
  - The draft's and then the public release's assets were downloaded. Both matched `SHA256SUMS.txt` and GitHub's digests.
  - It is a pre-release like 0.2.0: promotion waits on the paused live work, and is the owner's call.
- 96.5 **Repo-wide suggestions** from three independent review agents on 2026-11-17 (performance and parallelism;
  architecture and process; CI and tooling). Measured on this machine, read-only. They are listed for the owner to
  approve, not done unasked. Sizes S/M/L, the most valuable first. Owner 2026-11-17: follow the recommended order of the
  suite-review handoff (FEATURE_GENOME_ROADMAP.md section 14), which takes the remaining small items after 96.4.
  - **A1 (S), first: records say RC8 after the switch to RC7.** Tania's archived report (2026-11-17) is titled
    "(0.98a-RC8)", says the scripts were "compiled against RC8", and heads its live run "(2026-11-17, RC8 rig)". The
    sources: `live/live_accept.py:114`; `probe/probe_group.py:991-993`, which also writes "Owner ran New Game" for
    harness runs; the archive credit line; the MOD_CHANGELOG lines; `master_log`; revive's "0.98a-RC8" fallback. Fix:
    one helper naming the build the core reports. Past records only matter as records (owner's rule for the G3 case).
    **Done 2026-11-17.** Two helpers in `game_version`:
    - `revival_build(working)` is the build a revived copy is for. That is its `gameVersion` (which revive's fixer and `retarget`
      set to the core's own build), else the target its last `revive` recorded, else none.
    - `rig_label(rig)` is "<build> rig", from the rig's core, or "rig (build not read)".

    They feed:
    - the ARCHIVE_NOTE credit line;
    - the MOD_CHANGELOG line (`mod_changelog.archived_text`). Lines for RC8 archives keep the words "RC8", so re-seeding adds
      no second line, and a note older than the credit line seeds as RC8;
    - the credits file;
    - `master_log` (its generic-line pattern takes any build);
    - the `accept` and group-record headings. The group record says "The run started a New Game..." rather than crediting
      the owner;
    - the report draft's title and compile line.

    Six help texts that called RC8 *the* core now say the target or the given core: `revive --vanilla-core`, `close --reason`,
    `relink`, `scan --compile-check`/`compile-check`, `content-diff` and `rebuild-from-reference`. Historical ids such as
    RC8-25 stay. Revive's documented `--target` fallback (0.98a-RC8 without a core) is unchanged: 36 tests run revive without a
    core, and the batch passes `@target`. Records written before the fix stay as they are, by the owner's rule. Tests:
    - `tests/test_build_labels.py`;
    - `tests/test_archive.py` `test_the_note_and_changelog_name_the_build_the_mod_was_revived_for`;
    - `tests/test_group_accept.py` `test_a_plain_record_names_the_rigs_build_and_not_the_owner`;
    - the `accept` headings in `tests/test_live_accept.py` and `tests/test_group_accept.py`, now on a synthetic rig whose core
      reports 0.98.5a-RC7 (`tests/bound_runs.write_core_build`).

    Left open, because each changes behaviour (96.3): `rig-doctor` compares mods with `0.98a`, and `dependency-substitutes`
    never counts a 0.98.5a provider as current.
    An independent review the same day found six problems, fixed in the same PR:
    - `revival_build` now takes the newer of a whole-build gameVersion and an applied revive's target. Revive's fixer
      leaves a same-release gameVersion such as 0.98.5a-RC3 under an RC7 target. "0.98a" alone and a dry run's target name no
      build.
    - Seeding tells a note with no credit line (RC8, as before) from a credit line naming no build ("revived and archived").
      The master log reads notes the same way (`mod_changelog.note_build`).
    - `GENERIC` matches only a whole generated line, so a hand-written "re-revived and archived after..." stays.
    - The accept and record headings read the core the run's manifest recorded at launch (`rig_core`), not wherever the
      junction points at accept time.
    - Three missed RC8 texts are gone: `close` writes "Not revivable" (the reason names the build), and two auto-explain
      reasons say "the game's parser" and "game schema".
    - The report draft's title and compile line are tested.

    Tests: `tests/test_build_labels.py` (same-release precedence, dry run, manifest core, the four kinds of note, generic
    negatives, the draft). Each review case fails on the first version (mutation-checked).
  - **Performance:**
    - P1 (S): one `javap` per jar, not per class (`settings_keys.py:116`, `procgen_args.py:151`). That is 40-77% of a
      scan (UAF: 252 launches, 52.8 of 68.6 s), and revive repeats it.
      **Done 2026-11-17.** `bytecode/javap_batch.class_listings` gives javap all of a jar's selected classes in one call, as
      many calls as the Windows command-line limit needs. It splits the output back per class by each listing's declaration
      line.
      - The split was checked with JDK 25: each listing equals that class's own call byte for byte. The test jar had an inner
        class, an enum, a generic interface, a class without a SourceFile attribute, string constants holding newlines and
        braces, and a missing class.
      - Entry names still pass `zipsafe.javap_class_name` (93.45).
      - Both checks use it.
      - A batch is used only when its listings name exactly the classes asked for, in order; otherwise it is read again one
        class at a time. An independent review found why: javap names the class a file declares, so `p/Foo.class`
        declaring `p.A` prints as `p.A`. Split by name, that listing was lost, and a decoy could replace a real class's
        listing. One call per class credited it to `p/Foo.class`, and so does the fallback.

      On UAF's three jars the two checks went from 252 javap launches and 49.5 s to 5 launches and 1.9-2.5 s, with identical
      results: 29 settings reads and 0 procgen suspects, the same SHA-256 for both lists.
      Tests: `tests/test_javap_batch.py`:
      - one launch per jar for both checks (3 launches before);
      - the split;
      - the command-line budget;
      - the declared-name cases: a misnamed file, a decoy, a class javap cannot read;
      - two real-javap comparisons with one call per class: a plain jar read in one launch, and a jar with a misnamed and a
        missing class.
      The 93.45 tests in `tests/test_untrusted_input.py` now watch `javap_batch`'s launches.
    - P2 (S-M): provider lookups read only each provider's `mod_info.json` (`substitutes.provider_for`). About 35 s per
      scan with providers (Bultach: 29.9 -> 68.2 s).
      **Done 2026-11-17.** `provider_for` and `provider_index` take `contents=False`, which reads only mod_info.json and leaves
      `provides` empty.
      - Five scan steps look providers up: `scan_classfile`, `scan_compile`, `scan_content`, `scan_libraries` and
        `scan_references`. They use only a provider's id, path and version, and now ask for just those. Before, one scan
        built the full index five times.
      - `dependency-substitutes`, revive's substitution cache and `corpus provider-index` still read contents.

      Measured on White_Legion with `In operation` as the provider root: providers added 3.1 s to a Bultach scan
      (17.5 -> 20.6 s) and now add 0.5 s (14.8 -> 15.3 s). The findings are the same 104, with the same SHA-256.
      Tests: `tests/test_substitutes.py` `IdOnlyProviderIndexTests`:
      - an id-only index opens no CSV or jar;
      - a whole scan asks only for ids.

      Both fail with their guard removed.
    - P3 (S): revive drops its duplicate final scan; compile-check caches its harness and core compile (about 2 s a scan).
      **Done 2026-11-17.**
      - **The duplicate scan was also the wrong scan.** After applying fixes, revive scanned the finished tree once more to
        write its artifacts, and that scan had no dependency providers, while every scan revive decides on has them
        (`_provider_roots`, which always includes the queue). So the scan the registry held, which `auto-open` and
        `assess` read, was not the one revive's status came from. Revive now registers its own last scan, with its
        provider roots in the registry context. Nothing in `working/` changes after that scan: packets and the ledger
        live in the workspace's `reports/`, and the fingerprint skips `working/reports/`.
      - **Compile-check** compiled RC7's 116 loose core scripts with every mod's (1.4 s of javac) and the Janino harness
        (0.4 s) on every scan, measured on White_Legion. Both now compile once per process, core and javac:
        - into a folder that process creates and removes at exit, keyed by every input's size and time. Nothing is shared
          between processes, so 93.51's planted-class route does not apply;
        - the core scripts against the core alone, as the game compiles them, with their classes last on the mod's
          classpath, so a mod jar's class still beats a same-named loose script, as in the game;
        - their errors are still reported (`vanilla_companion_errors`, and in `javac_returncode`).

      Tests:
      - `tests/test_revive.py`: every scan has providers, the registered report is the last scan, and the registry
        context and `assess` agree;
      - `tests/test_compile_check.py`: the companions compile once for two checks, and a broken core script is still
        reported.

      Each fails with its guard removed (mutation-checked).
    - P4 (S): AST facts resolve each file once (about 3.5 s a scan).
      **Done 2026-11-17.** A profile of a Sunrider scan (86 `.java` files, RC7 core, White_Legion) found the repeated work
      in `scan_javatext._blank_java_comments`: 4,523 calls and 5.06 s of a 24.8 s scan. About 40 source checks each blank
      every file's comments again. Results are now kept per text and mode for the process: least recently used first out,
      within 64 M characters (an entry counts its text and its result), under a lock; the values are strings, so a caller
      cannot change a cached one. All 129 call sites keep their code.
      After: 247 blankings, 0.51 s, and the scan took 18.8 s (both timed under cProfile). The 70 findings are the same
      (SHA-256 of the findings before and after).
      Tests: `tests/test_blank_comments_cache.py`: equal to the uncached result; each text and mode blanked once over 40
      passes, including a new string read again; the budget holds, and a text over it is blanked but not kept; 8 threads.
      The once and budget guards each fail with their guard removed (mutation-checked).
    - P6 (S): fix the quadratic `_invalid_utf8_offsets`. It is the suite's slowest test at 24 s, and large CP-1252
      files hit it too.
      **Done 2026-11-17.** One decode with a registered error handler. The handler records each undecodable byte and
      resumes one byte past it, which is where the old loop resumed, so the offsets are the same. They are collected per
      thread. `test_large_rules_csv_with_isolated_cp1252_byte_survives_the_fix` went from 37.6 s to under 0.75 s on
      White_Legion. Its five modules took 62.5 s before; with the new test module they took 21.5 s after. Test: `tests/test_utf8_offsets.py`: equal to the old
      loop on 610 inputs (truncated, overlong and surrogate sequences, stray bytes), unmixed across 8 threads, and a
      2.4 MB file with 120,000 isolated CP-1252 bytes.
    - P7 (S): parse the vanilla core once per process (about 2 s a scan, about 6 min per done-audit).
      **Done 2026-11-17.** A profile of a second Bultach scan in the same process showed three core readers called twice per
      scan and cached nothing:
      - `scan_jarchecks._vanilla_api_jar_class_info`: every class in starfarer.api.jar and starfarer_obf.jar;
      - `_vanilla_loose_script_fqns`;
      - `scan_content._vanilla_faction_ids`.

      Each is now read once per core per process. The key is the core's resolved path plus the API jars' size and
      modification time, and for factions the folder's modification time, so another build or a replaced jar is read
      again. The jar classes come back read-only and the script names as a frozenset; faction ids come back as a fresh set
      for each caller, because the rules check adds the mod's factions to it.
      Measured on RC7's core (White_Legion, under load): the jar classes take 0.56 s (6,442 classes), the scripts 0.02 s and
      the factions 0.04 s, and a repeat call under 1 ms. A scan called each twice, so the first scan saves about 0.6 s and
      every later scan in the process about 1.2 s. For `done-audit` over 184 archives that is about 4 minutes. Two Bultach
      scans gave the same 79 findings (same SHA-256) before and after.
      Tests: `tests/test_core_cache.py`:
      - parsed once;
      - read again after a jar changes;
      - read-only;
      - scripts read once;
      - each caller gets its own faction set.
    - P5, P8 (M, S): read each source and each jar class once per scan.
      **Done 2026-11-19.** Measured on Sunrider (86 `.java` files, 240 jar classes, RC7 core, White_Legion): one scan read its
      384 files 27,406 times and its jar classes 3,756 times; the lenient JSON parser ran 2,399 times. Per-check timing
      showed the reads themselves were cheap and two things cost:
      - `java_ast.analyze_sources` resolved a path for each of its 12,003 facts (3.4 of its 4.2 profiled seconds); it
        now resolves each of the 86 files once.
      - Each check re-parsed the same JSON files and jar classes. `scan_mod` now opens the existing bounded parse-reuse
        scope (`analysis_reuse.reuse_within`: 50,000 entries, 128 MB; an enclosing portfolio-worker scope is kept), so a
        file's JSON and a class's facts are parsed once per scan. Each hit is an independent copy, so a check that
        changes its result cannot affect another. Sunrider used 7,282 entries and 20 MB.
      Result, median of three fresh processes each scanning twice, identical findings (SHA-256 of the sorted findings):
      Sunrider 9.91 s -> 7.97 s first scan, 6.98 s -> 5.06 s second; UAF 23.25 s -> 18.73 s and 20.63 s -> 17.09 s.
      Left as they are: the core jars are parsed once per process already (P7), and the remaining raw text reads cost
      well under a second. `portfolio` without `--reuse-parses` now turns reuse off (`analysis_reuse.no_reuse`), so its
      reuse-on and reuse-off comparison still holds. Tests: `tests/test_scan_read_once.py` (each source resolved once
      for 50 facts, was 50 each; the reuse scope kept or opened and closed; a scan parses each JSON file once and its
      one jar class once, which was 23 times; scan_mod joins an enclosing scope and `no_reuse` turns it off). Removing
      either fix fails its test. An independent review found no behaviour change in the scan; its three points (the
      portfolio flag, the error type for an unknown AST line, thin tests) are taken.
    - P9 (M): memoize the AST helper in tests (an estimated 2-3 of 11 minutes).
      **Done 2026-11-19.** Measured first: over the whole suite (3,135 tests) `java_ast.analyze_sources` was called 1,390
      times, 930 of them on folders with no `.java` file (0.4 s); the 460 real JVM runs took 122 s on 329 distinct inputs. The
      memo is in `java_ast` itself, not only in tests, because a revive scans each mod several times: a result is keyed by
      each source's path relative to the root and its bytes, plus the helper's folder (its source digest), so an edited file
      or a new helper misses; each caller gets copies. It holds at most 1,024 results and 200,000 facts (one real mod gives
      up to 12,003). The same measurement afterwards: 70 s of AST time instead of 122 s (with other jobs on the machine).
      Tests that fake the helper's output clear it (`java_ast.clear_memo`). Tests: `tests/test_scan_read_once.py` (the same
      sources run the helper once, a caller's change does not reach the memo, new bytes run it again; fails without the memo).
    - P10 (M): a process pool for target-impact and corpus-index (5 -> about 1.5 min).
      **target-impact part done 2026-11-19.** Each mod's check (`mod_impact`) is independent and read-only, so `--jobs N`
      (default up to 4, one CPU left free; 1 keeps the in-process loop) checks mods in worker processes. The main process
      keeps the checkpoint, so an interrupted run still resumes; records stay in the mods' order and the JSON and markdown
      are unchanged. Progress lines now come in the order mods finish, numbered by mods finished, resumed ones first.
      Measured on White_Legion, RC8 -> RC7 over the owner's RC8 `mods` folder (191 mods, read-only): 68 s with one worker
      and 22 s with four once the files were cached (252 s for the first, cold run), and the two JSON results identical
      (12 BREAKS, 5 RELINK, 5 REVIEW, 169 CLEAN). On 8 mods the gain is small (6-8 s -> 5 s): each worker parses both cores
      once. corpus-index is not done: its indexers write to SQLite as they read, so a pool needs them split into read and
      write first.
      Tests: `tests/test_target_impact.py` (two workers give the same result, in the same order, with one progress line per
      mod; `--jobs 0` refused; the resume test reads the new numbering).
  - **CI and tooling:**
    - C3 (S): stop duplicate push and pull_request runs. 101 of 191 SHAs ran twice, and nine PRs queued for hours on
      2026-11-17. Docs-only PRs run only the doc-reading tests.
      **First half done 2026-11-17.** `.github/workflows/ci.yml` runs on `pull_request`, and on `push` only to `main`, so each
      PR commit runs once. A branch pushed without a PR runs no CI, and this repository opens a PR for every change. The
      docs-only path filter is still open: it needs a list of the tests that read documents (`tests/test_roadmap_lint`,
      `test_gates`, `test_checks_index`, `test_cli_golden` and others) and care that a required check still reports.
      **Done 2026-11-17.** A pull request that changes only documents runs Lint and a new Documentation tests job. Its other
      checks show as skipped, and a push to main still runs everything.
      - **The decision:** `tools/ci-scope.py` reads the pull request's own changes, its merge commit against the base. A
        change is documentation only when every changed path is a Markdown file outside `bridgeforge/`, `tests/`,
        `probe-mod/`, `tools/` and `.github/`. Markdown under those folders is input: package data
        (`kit_resources/TRIAL_GUIDE.md`), fixtures, CI.
      - **The list:** `tests/doc_tests.json` holds the test modules that read a document, with the documents each reads.
        - It was measured: the whole suite (2987 tests) ran under an audit hook on `open()`, and six modules opened a
          Markdown file in the checkout.
        - The guesses above were wrong: `test_gates` and `test_cli_golden` read none, and `test_release_notes` works on
          temporary copies.
        - The tests that start a child process were read by hand; none reads a repository document.
        - A documentation-only run is 46 tests in about 12 s here, against about 10 minutes for the suite.
      - **Every check name still reports:**
        - the single jobs skip whole, and a skipped job reports under its own name;
        - the matrix job runs and skips its steps, since a matrix job skipped whole reports once under its unexpanded name.
      - **A failed scope job runs everything:** each job that needs it carries `!cancelled()`. Otherwise a failed scope job
        would skip them, and skipped checks read as passed.
      - **Checked on GitHub** with a draft pull request based on this branch that changed one Markdown file (#126, closed
        unmerged, its branch deleted):
        - Change scope saw only `docs/INDEX.md` and set `docs_only=true`.
        - Lint and Documentation tests passed: 46 tests, hermeticity PASS.
        - The four matrix checks reported under their own names, in 4-7 s with their steps skipped.
        - Coverage, Dependency audit, uv.lock in sync and Shared fixtures showed as skipped.

      Tests: `tests/test_ci_scope.py`:
      - the classifier and its command line;
      - the list, and that each document it names is documentation;
      - the workflow's wiring.

      Each guard fails its test when removed (mutation-checked).
    - C1 (S): the git hooks never run (`.githooks/` is ignored and `core.hooksPath` is unset). A pre-commit that
      regenerates the generated files would have caught the stale CHECKS.md.
      **Done 2026-11-17.**
      - The hooks are tracked in `tools/githooks/` (`pre-commit`, `pre-push`, executable). They call the tracked
        `tools/precommit-check.ps1` and `tools/prepush-check.ps1`, and skip with a note where there is no PowerShell.
      - Enable them once per clone with `git config core.hooksPath tools/githooks`. The relative path works in every worktree.
      - The pre-commit check now also runs `docs-index --check` when Python files are staged. Checked by hand: with a staged
        new scan function it refused with exit 14 and named the fix; on clean changes it passed in 7.8 s.
      - `hygiene` reports the hooks: SKIPPED in a repository without `tools/githooks/`, PASS when `core.hooksPath` points
        there, otherwise a FINDING with the fix.

      Tests: `tests/test_hygiene.py` `HooksTests`:
      - a repository without the hooks is skipped;
      - off is a FINDING with the fix, and on passes;
      - this repository's hooks are tracked as executable and call its checks, including the `docs-index --check` call.

      The last two fail with their guard removed (mutation-checked).
    - C5 (S): a pre-push static tier plus tests selected by import, under 2 minutes.
      **Done 2026-11-17.** `tools/prepush-check.ps1` runs in three tiers:
      1. the report-status check;
      2. the static tier: ruff on the Python files the branch changed against origin/main, and `docs-index --check`
         (seconds; it catches what a commit made with the hooks off let through);
      3. the tests from `tools/prepush-select.py`, run as `tests/run_partitioned.py --partition fast --modules ...`, so the
         cases in `tests/slow_tests.json` are left to CI's slow job.
      It prints the static and total seconds, and a note when a push goes over 120 s.
      - The selection is one rule, `merge_train.select_test_modules`, shared with merge-train. It takes the cross-cutting
        tests, the tests named after a changed module (as before), and now the tests that import it: an AST read of every
        test file, including imports inside a test, `from pkg import module`, and a root facade of the same name.
        P4's change to `scan/scan_javatext.py` matched no test by name; two test modules import it
        (`test_blank_comments_cache`, `test_mod_guarded_missions`).
      - A module that more than 25 test modules import is central: `scan/scanner.py` has 73, 967 tests, 234 s on
        White_Legion. For such a module only the tests named after it run, and a note says CI runs the rest.
      - The PowerShell copy of the name mapping is gone, along with the test that kept it in step with Python's.
      Tests: `tests/test_merge_train.py`:
      - selection by import (nested, inside a test, by package, by facade; a file that does not parse);
      - the central-module cap and its note;
      - the script's tier order;
      - `prepush-select.py` prints the shared rule.

      `tests/test_source_paths.py` checks that the script has no mapping of its own. The import match and the facade
      match each fail with their guard removed (mutation-checked).
    - C6 (S): the same JDK locally and on CI, and `-encoding` on every test javac (14 of 16 lack it).
      **Done 2026-11-18.** CI installed Temurin 17 while the suite ran locally on JDK 25 (White_Legion has only
      Adoptium 25 builds). `.java-version` (25) now names one version: every setup-java step in `ci.yml` and `weekly.yml`
      reads it (`java-version-file`), and `tests/support.javac_path` asks `find_jdk(prefer_major=...)` for that version
      first, so a machine holding several JDKs compiles test fixtures with CI's. `java_toolchain.jdk_major` reads a JDK's
      `release` file. Fixtures still compile with `--release 17` where they did before.
      A count over `tests/` found 24 javac command lists without `-encoding` in 19 files, not 14 of 16; each now passes
      `-encoding UTF-8` (javac otherwise reads the platform code page on Windows and UTF-8 on Ubuntu).
      Tests: `tests/test_jdk_consistency.py`: every setup-java step reads `.java-version`; an AST check fails on a test
      javac list with no `-encoding` (a starred `DEFAULT_JAVAC_ARGS` counts); `jdk_major`; the preferred version beating
      the search order; and the local JDK matching `.java-version` (skipped with the two versions named when it does not).
      All three guards fail with their fix removed (mutation-checked).
    - C7, C8 (S): wall-clock budgets to `process_time`, `timeout-minutes`, `buffer=True`; a shared setup step and a
      pinned ruff (weekly.yml drifted from ci.yml and failed 5 weeks running).
      **Done 2026-11-18.**
      - C7: the four tests that budget a CPU-bound check (`test_forwarding_methods`, `test_target_delta`, two in
        `test_scan_robustness`) measure `time.process_time()`, not the wall clock, so a busy runner cannot fail them. The
        scan runs in one process, so its own CPU is what the budget is about; javap children are not counted. The tests
        that time a real wait (the launch watchdog, an escalation timeout) keep `monotonic`. Every job in `ci.yml` and
        `weekly.yml` has `timeout-minutes`, about three times its slowest recent run (Windows fast 11.2 min -> 35). The
        suite runners (`run_partitioned.py`, `run_reversed.py`) and the coverage job's `unittest discover -b` buffer each test's
        output, so only a failing test's prints reach the log.
      - C8: `.github/actions/setup-bridgeforge` (composite) sets up Python, the `.java-version` JDK and the install for
        every job that runs the suite: docs, coverage, the test matrix and weekly. `pyproject.toml` pins ruff with
        `required-version = "==0.17.5"`; ci.yml's ruff-action names that version, and the hooks and the PR skill's
        `checks.sh` run `uvx ruff@<pin>`.
      Tests: `tests/test_ci_setup.py`: every job has a timeout; jobs that run `test_guard` use the shared setup and only
      the action sets up Java; CI, both hooks and `checks.sh` use the pinned ruff; the runners buffer output.
      Each guard fails with its fix removed (mutation-checked).
    - C2 (M): time-balanced shards with coverage inside the Ubuntu ones (Windows-fast is 12 min now; PR results in
      about 5-6).
      **Done 2026-11-18.** The test matrix is Windows and Ubuntu x four shards, `tests/run_partitioned.py --shard K/4`.
      - Shards take whole test modules (class fixtures stay together), dealt longest first to the least loaded shard
        (`shard_modules`), so every module runs exactly once and the split is the same on every runner. A module with no
        measured weight counts as the median.
      - The weights are `tests/module_timings.json`: seconds per module from a timed full run on White_Legion (322 modules,
        630 s), written by `tools/module-timings.py` (the largest sum wins over several reports). Four shards come out at
        158 s each; the largest module, `test_behavior_observations`, takes 79 s.
      - The Ubuntu shards run under `coverage run -p` and upload `coverage-data-<K>`; the coverage job downloads, combines and
        applies the floor once every shard passed, instead of running the whole suite again under coverage (5 minutes).
      - The fast/slow split stays for the pre-push hook; CI no longer uses it. Main has no branch protection, so the renamed
        checks block nothing (checked 2026-11-18).
      Tests: `tests/test_test_shards.py` (each module once, longest first, the median for an unmeasured module, whole modules
      in order, a bad spec refused, the measured weights covering the suite and balancing four shards within a tenth, the
      weights tool); `tests/test_ci_scope.py` (the coverage job combines the Ubuntu shards after they pass, the matrix and
      the `/4` agree); `tests/test_ci_setup.py` (every shard run goes through the buffered runner). A wrong shard index fails
      them (mutation-checked).
    - C4 (M): a machine-state sandbox for the suite: winreg raises unless patched; HOME, APPDATA and TEMP point at temp
      folders.
      **Narrowed to S (owner 2026-11-18: "I like your recommended route for C4").** Only the registry guard: in
      `tests/support.py`, any `winreg` call raises unless the test patches it. `rig/rig_prefs.py` writes
      `HKCU\Software\JavaSoft\Prefs\com\fs\starfarer` (the key that also holds the licence key) and rig-doctor reads
      `LongPathsEnabled` from HKLM; today only each test's own patch keeps them off the real registry. HOME, APPDATA and
      TEMP are not redirected: 5 modules read the home folder, the tests already use temp folders, and redirecting them
      would change git's, javac's, java's and uv's environment in every test that starts one. Patch the home folder in a
      test if one of those 5 modules ever needs it.
      **Done 2026-11-18.** `tests/support.py` wraps `winreg.OpenKey`, `OpenKeyEx`, `CreateKey`, `CreateKeyEx`, `DeleteKey` and
      `DeleteKeyEx` on import: any key outside `HKEY_CURRENT_USER\Software\BridgeForgeTests` raises `RegistryGuardError`.
      It is not an `OSError`, because rig-doctor catches `OSError` as "unreadable" and would hide the access. A test that
      patches one of those calls replaces the guard on purpose. Discovery imports every test module before a test runs and
      194 of 317 import `support`, so a whole run is guarded from its first test; the four modules that reach registry
      code without importing it now do, and a test keeps it so.
      The guard found real reads at once: the tests that call `rig_doctor()` and `test_reference_rigs` read HKLM
      `LongPathsEnabled`, so their result depended on the machine; `test_rig_doctor_environment`'s "unknown long-path
      setting" test asked the real key and accepted either answer. They now patch `_long_paths_enabled`, and that test
      asserts PASS for an unknown setting. No test wrote to the preferences key.
      Tests: `tests/test_registry_guard.py` (the preferences key and HKLM refused; the guard's error escapes rig-doctor's
      `except OSError`; the test root allowed and a look-alike prefix refused; a patch replaces the guard and is restored;
      registry-reaching modules import `support`). Removing the guard fails five of them; widening the prefix rule fails
      one (mutation-checked).
    - C9 (M): shared test fixtures (`_write` is copied in 60 files; 39 copies write CRLF on Windows).
      **Done 2026-11-18.** `tests/support.write_text(path, text)` makes the parent folders and writes UTF-8 with LF. 48 test
      modules' own `_write` copies (the two-line make-folder-and-write body, with `write_text` or `write_bytes`) are replaced
      by `from tests.support import write_text as _write`, so no call site changed; the 40 of them that wrote through
      `write_text` wrote CRLF on Windows. 13 variants stay (other parameters, bytes or JSON data, a return value).
      Tests: `tests/test_test_helpers.py` (the writer's folders and LF bytes; no test module keeps a canonical copy, an AST
      check that caught the unannotated copy in `test_done_audit` the first pass missed; the detector's cases). The 704
      tests of the 47 first-pass modules passed with LF fixtures before the full suite.
  - **Architecture and process:**
    - A3 (S): `escalation run --all` breaks the long-running rule (no progress, no checkpoint). `auto-open` and
      `atlas migrations` are missing from the list, and a test should require it.
      **Done 2026-11-17.** All three now print progress and resume from a checkpoint, and all three are listed in
      `progress.LONG_RUNNING_COMMANDS`.
      - `escalation run --all` prints one line per packet and offers `--quiet`. Finished packets go to
        `reports/escalations/run-all.partial.jsonl`, so an interrupted run resumes after the last one; an agent attempt can
        take half an hour.
      - `auto-open` keeps each finished workspace in `<queue>/auto-open.partial.jsonl`.
      - `atlas migrations` keeps each finished pair in `<--write DIR>/<stem>.partial.jsonl`, when the pair labels are
        unique. Without `--write` it keeps none: the atlas folder is not its to write into.
      - Each checkpoint is removed when its run completes.
      - A checkpoint's header names the inputs that change a result, so a changed input starts the run afresh instead of
        reusing a stale record:
        - `escalation run --all`: every run option and each packet file's SHA-256, so packets `revive` wrote afresh are
          run, not skipped. A packet that finished counts as done whatever its outcome; naming it runs it again.
        - `auto-open`: the standing fixer approvals, and each workspace's scan registry, REVIVE.json, escalation ledger
          and packets, and baseline, by size and time. This is how `escalation queue` holds REVIVE.json's time. An edit
          inside `working/` that no scan recorded is not seen by a resumed walk.
        - `atlas migrations`: the API jars, by the SHA-256 the api-diff catalogue records. A pair is known by its label,
          so a pair whose folders changed in between keeps its rows.
        - `Checkpoint` takes a longer list for the same run (ROADMAP 49). The approvals and the API jars are therefore
          a string and a dict, not lists: an independent review found that one more approved fixer, or swapped jars,
          resumed with stale rows.
      - The new list test runs the other way round from the old one: every command that offers `--quiet` must be
        listed, since `--quiet` exists only where a command prints per-item progress. It found exactly `auto-open` and
        `atlas migrations`.

      Tests: `tests/test_progress.py` `LongRunningListTests`:
      - the reverse list check;
      - one resume test per command: interrupted on the second item, then resumed, the finished item is not redone and
        the checkpoint is gone;
      - tests that a changed input starts afresh: a rewritten packet, another `--timeout` or `--auto-accept`, a
        workspace revived in between, one more approved fixer, other or swapped API jars.

      Each fails with its guard removed (mutation-checked).
    - A8 (S): the revival guide still teaches the RC8 workflow (docs pass, 96.3).
      **Done 2026-11-18.** A8 was recorded at 12:28 on 2026-11-17; 96.3 rewrote the guide for RC7 at 13:58 the same day.
      This closes what 96.3 left for later, because each needed code:
      - `rig-doctor` compared every enabled mod with a fixed `0.98a`, so it warned about every mod revived to 0.98.5a on
        the 0.98.5a rig. `rig_doctor.rig_base_game_version` now reads the rig core's own build (`core_build`), falling back
        to `0.98a`. The guide's section 1 said the check was still wrong; it now says what it does.
      - `dependency-substitutes` counted a provider as current only at `0.98a`, so a 0.98.5a provider was never EXACT.
        `substitutes.target_series` takes a given core's build, else (no core given) `bridgeforge-state/target.json`'s, else
        `0.98a`; `rank` and `cover` take that series and the report names it (`target_series`). The report key stays
        `targets_0.98a` (reports and revive options carry it) and means "targets the current series". The 0.98.5a
        launcher unchecks a 0.98a mod, so on an RC7 core a 0.98a provider is no longer current either.
      - Eleven `--help` texts that called the core "RC8" now say "target" (`shadow-triage`, `strip-plan`,
        `substitution-proposals`, `value-proposals`, `api-diff`, `port-interfaces`, `scan --removed-content`, `fix
        --reference-core`, two in `rig-doctor`). The six 96.3 named were already fixed. Kept: `revive --target`'s
        `0.98a-RC8` fallback (the real default), `target-impact`'s example and the `RC8-nn` behaviour ids.
      Tests: `tests/test_rig_doctor.py` (a 0.98.5a-RC7 core warns about a 0.98a mod and not a 0.98.5a one);
      `tests/test_substitutes.py` (on an RC7 core the 0.98.5a provider is EXACT and chosen, the 0.98a one PARTIAL; the
      series from a recorded target and a named core's precedence). Both fixes fail their tests when removed
      (mutation-checked).
    - A9 (S): retire two dead tools scripts and a fourth status list (`prepush-check.ps1` lacks NOT_REVIVABLE).
      **Done 2026-11-18.**
      - `tools/build-done-master-log.ps1` and `tools/copy-done-archives-with-readme.ps1` are deleted, with their
        `.gitignore` exceptions. `master_log.py` (item 65) writes `Done/MASTER_LOG.md` after every archive, and `archive`
        writes each archive's `-with-readme.zip`; nothing called either script. `tools/RepairZorg18.java` stays: it is the
        record of how that release was repaired.
      - The pre-push report check matched its own list of seven statuses, which lacked NOT_REVIVABLE, so a report closed
        with `close --status NOT_REVIVABLE` (95.15) would have blocked a push. `tools/report-status-check.py` matches
        `report_status.REPORT_STATUSES` instead (the same any-word rule as before). It runs once Python is found; with no
        Python the hook now skips it along with the tests.
      Tests: `tests/test_report_status_check.py`: every status in the shared list passes, a report with none fails, a
      NOT_REVIVABLE report passes, the script names no statuses of its own, and the two scripts are gone. Dropping
      NOT_REVIVABLE from the check fails two of them (mutation-checked).
    - A2 (S/M): one resolver for the checkout and the state folder. The `.venv` holds a stale non-editable copy,
      0.4.0, 68 files behind.
      **Done 2026-11-18.** `bridgeforge/paths.py`: `checkout_root()` (the source tree) and `data_root()`, `state_dir()`,
      `ops_dir()`, `done_dir()` (In operation/, Done/, bridgeforge-state/). Without `BRIDGEFORGE_DATA_ROOT` both are the
      checkout, which is what every module computed before, so nothing moves; with it, the data defaults follow it. That is
      what White_Legion needs: its checkouts are worktrees under `bridgeforge-state/github-fixes/`, three levels below the
      real data.
      - 22 module-relative roots in 20 modules now go through it. The data ones (`substitutes.REPO_ROOT` and
        `java_toolchain.REPO_ROOT`, which 10 modules import, `novelty`, `bootstrap`, `build_tag`, `reference_rigs`,
        `release`, `test_plan`, `cmd_archive`'s restore, `cmd_revive`'s Done, `rig-doctor`'s baselines and working
        copies) use `data_root()`. The source-tree ones (`checks_index`, `release_notes`, the probe build and release copy,
        `atlas_predictions`, the capacity, duel and raid mods, `MOD_CHANGELOG.md`) use `checkout_root()`. rig-doctor has a
        second patchable helper, `_checkout_root()`, because it reads both. Package-internal paths (`probe_profiles`,
        `scan_registry`, the `PYTHONPATH` handed to child runs) stay as they were.
      - The suite never sees the variable: `tests/support.py` drops it and `test_guard` starts the suite without it.
      - `hygiene` has a new check, `installed_package`: a plain install, or an editable one at another version, is a
        finding, with the fix (an editable install of the main checkout, not a worktree). On White_Legion it reports the
        `.venv`'s plain 0.4.0 copy.
      Not changed: the command-line defaults written as `Path("bridgeforge-state") / ...` stay relative to the folder a
      command runs in, as documented.
      Tests: `tests/test_paths.py`: both roots default to the checkout; the variable moves the data root and not the source
      tree; a fresh interpreter's module defaults follow it; no module computes a data folder from `__file__`; the suite
      never sees it; the install check (plain, editable at another version, editable at this one, none). The hygiene tests
      patch the install check (machine state). Removing the routing, the plain-install finding or the suite's environment
      strip each fails a test (mutation-checked).
      Follow-up the same day: run from White_Legion's main checkout, the check read an old build's gitignored
      `bridgeforge.egg-info` there (the current folder is on `sys.path`) and called the fresh editable install plain.
      `hygiene._installed_distribution` now skips the checkout's own folder; `test_paths` covers it (mutation-checked). With
      that, the main checkout was fast-forwarded to main and the `.venv` reinstalled editable: `installed_package` PASS, 0.4.2.
    - A7 (S/M): MOD_CHANGELOG and release decisions as fragments, since two machines now write them.
      **Done 2026-11-18.** Test1's `archive` and White_Legion's sessions both edited `MOD_CHANGELOG.md` and
      `bridgeforge/release_policy.json`, so two branches changed the same lines (the 2026-11-17 archives).
      - `mod_changelog.add_entry` writes one file in `mod-changelog.d/` beside `MOD_CHANGELOG.md`, named by date, mod and a
        hash of the line, so the same entry made on both machines is the same file. An entry already in the file or a
        fragment is not added again. `merged_text` / `sections` read the file and the fragments together; the master log's
        timeline and `seed_from_archives` use them.
      - `release.record_policy_decision` writes `bridgeforge/release_policy.d/<mod>.json` (the existing key's spelling);
        `_load_policy`, which every reader goes through, lays the fragments over the file and refuses a malformed one. The
        wheel ships `release_policy.d/*.json`.
      - `release-notes assemble` folds both kinds into their files with the changelog (LF), and `--check` lists them.
      Tests: `tests/test_record_fragments.py` (the file untouched, one file for the same entry on two machines, no
      duplicate of a filed entry, assemble and its dry run, the master log seeing pending entries; a decision laid over
      the file with its key's spelling, folded, a malformed one refused, the package data; `release-notes --check` and
      `assemble` over both). Eight test modules that read the two files directly now read the merged views. Removing the overlay,
      the fold or the duplicate check each fails a test (mutation-checked).
    - A4, A5, A6, A10 (M): one public module for mod files (11 resolvers, 5 `_mod_info` loaders); split the `run_cli`
      if-chains (10 of the 13 functions over 200 lines); split the 1,000-line modules with a size ratchet; one shared
      tree hash with 93.27's cache (13 copies of `_sha256`).
      **A4 Done 2026-11-18.** `bridgeforge/mod_files.py` holds the shapes that were copied: `read_mod_info` (lenient, an
      object or None), `find_mod_root` (the folder or its only child holding mod_info.json, raising `ModRootError`, a
      ValueError), `nearest_mod_root` (the same, returning None) and `workspace_or_mod_root` (`working/` first). Four
      `_mod_info` loaders (live_trust, mass_test, probe_group, target_impact) and five resolvers (copy_drift, prepare_test,
      intake, value_proposals, vendor_plan) now call it; each keeps its own error class. Resolvers with other rules stay
      put and the module says why (build_tag searches two levels, supersession reads original/, target_impact follows
      Done/'s layout, master_log skips original/ and workspace/). Tests: `tests/test_mod_files.py`, including a guard that
      fails when any of those nine functions gets its own mod_info.json path back (checked by restoring vendor_plan's copy).
      Not in scope, left for a later change: 57 one-line inline reads (`_load_lenient_json_file(x / "mod_info.json")`,
      e.g. game_version, behavior_discovery, campaign_layout, cmd_shadow, descriptions_draft) could call `read_mod_info`.
      **A5 Done 2026-11-18.** The ten `run_cli` functions over 200 lines (cmd_rig 437, cmd_corpus 396, cmd_archive 346,
      cmd_bytecode 276, cmd_translate 235, cmd_analysis 233, cmd_revive 231, cmd_scan 225, cmd_probe_group 224, cmd_save
      208) are now a `_HANDLERS` table and one `_run_<command>(args)` per command (120 commands, 112 handlers); probe-group's
      sub-command chain is a `_SUB_COMMANDS` table of eight functions plus `report`. A command's own conditional branches
      (`vendor-copy --plan`, `build-tag --record-only`, the seven `escalation` sub-commands, `compat-set install`) stay in
      its handler, in their old order; `intake`/`board` and the eight save readers share one handler as before. The move
      was done by a script and checked by AST: every handler's statements equal what `run_cli` ran for that command, and
      nothing outside `run_cli` changed. An independent review found no behaviour change. `checks_index` skips `_run_*` as
      it skips `_scan_*`, so docs/CHECKS.md's scanner-helper table is unchanged. Tests: `tests/test_cli_handlers.py` (each
      table equals the command's `COMMAND_MODULES` entry; an unknown command still returns 2; probe-group's table matches
      its parser; `compat-set` with another sub-command returns 2; a failed probe-group smoke prints its JSON once and
      returns 1, an error returns 2, a stopped record returns 1; a ratchet: no new function over 200 lines, the three left
      being `build_archaeology`, `_scan_variant_validity` and `_scan_sources`).
      **A6 Done 2026-11-19.** The four modules over 1,000 lines are split along their seams; the moved code is unchanged
      apart from the one write noted below.
      - behavior_discovery (1,274) -> behavior_discovery 594 (archaeology, the behaviour model) + behavior_evaluation 702
        (probe and save baselines, synthesized tests, expected changes, diff, release evaluation, decisions, coverage).
      - probe_group (1,115) -> probe_group 692 (plan, install, bisect) + probe/probe_record 447 (report, record, smoke).
      - translation (1,086) -> translation 702 (export, prefill, apply, check) + translation_formats 409 (the CSV,
        JSON-like, loose Java, text-line and class-file readers and writers).
      - dossier (1,076) -> dossier 560 (assembly, findings, open questions) + dossier_sections 311 (inventory, artifacts)
        + dossier_render 218 (markdown).
      Each new module depends on the old one or not at all, never both ways. Callers import from the module that defines
      the name (no shims; Project Salvor imports none of the four). A script moved the statements and an AST check
      confirmed every top-level statement of each old module is in exactly one of its parts. The one exception:
      `_write_expected_decision`'s hand-made temp-file-and-replace is now `atomic_write_text` (the same bytes), so
      behavior_discovery's safeio baseline drops by one. record_group's bare `write_text` of REVIVAL_REPORT.md stays bare (an
      atomic replace fails on Windows while an editor holds the file) and its count moves with it to probe/probe_record.py.
      An independent review found no blocking bugs. Tests: `tests/test_module_size.py` (no module over 800 lines unless
      listed with a cap equal to its length, so it cannot grow back; only revive.py, 886, is listed; fails on the old
      1,076-line dossier and on a cap left above its module).
      **A10 Done 2026-11-19.** `bridgeforge/file_hash.py` holds `sha256_file` (streamed in 1 MiB blocks),
      `sha256_file_or_none` (None when not a file) and `file_hashes(root)` ({posix relative path: digest}, sorted). The
      roadmap counted 13 copies of `_sha256`; a search over every function that hashes file contents found 31 that
      compute one of these three results. 28 of them, in 27 modules, are now the shared functions, imported under their
      old names so no call site changed (api_diff, archive,
      archive_intake, src_to_jar, decompiler, dossier, escalation_policy, explain_proofs, evaluation, live_trust,
      move_machine, fixers/presets, reference_rigs, research_decompile, revise, revive, run_manifest, save_snapshot (two),
      scan_registry, shadow_triage, snapshot_restore, substitution_proposals, targets, translation, validate,
      vendor_plan, workspace). workspace's importers (case_identity, fold, migrate, provenance) import from file_hash.
      Three keep their own result for a missing file and call it: lookup (None on any read error), value_proposals ("")
      and escalation_review.snapshot_dir ({} for a missing folder). Streamed and whole-file reads give the same digest.
      Left apart, and the module says why: provenance and scan_registry fold a tree into one digest that is stored;
      revival_audit hashes an open stream in upper case; content_diff, runtime and working_tree build other digests;
      escalation's `_tree` skips `.pre-bf-` files; kit_resources/verify_kit ships in the kit and must not import
      bridgeforge. 93.27's cache (not built) is meant to sit behind `file_hashes`. Tests: `tests/test_file_hash.py`
      (digests equal hashlib's for empty, small and multi-chunk files; None and OSError cases; nested tree order; each of
      the 27 routed names is the shared function; the three wrappers' missing-file results). revive.py lost its copy, so
      A6's size ratchet lowered its cap from 886 to 884, as designed; docs/CHECKS.md lost scan_registry's `_sha256` row.
- 96.6 (S) **`archive` does what `record --archive` does first.** On 2026-11-17 the owner said "archive all". All four plain
  `archive` runs refused (Templars, KoC, Eridani, Scrapyard):
  - `audit-explain --auto` then proved 9 of their unexplained files: KoC's moved work files, Scrapyard's credits file and
    Templars' added CSV rows;
  - three lacked the licence decision the owner's standing rule gives (2026-09-27);
  - Eridani's 9 translated files went unproven because translate-batch kept its records in `scratch/translate-work/`, not
    `scratch/translation/`.

  `record --archive` already applied both; plain `archive` applied neither.
  **Done 2026-11-17.**
  - `archive.prepare_archive` (used by `archive`) proves what the files prove, checks the gate and, when the gate allows,
    records the standing LOCAL_ONLY decision for a mod with none.
  - `release.apply_standing_licence` is now shared with `record_group`. A recorded decision is never changed.
  - A refusal lists what was proven and recorded.
  - `prepare_for_audit` copies a translate-batch work folder's records (`export.json` with mode TRANSLATION_EXPORT, and
    `translations.json`) into `reports/translation/`, so the translation proof sees them.
  - `record_policy_decision` writes LF: a plain `write_text` had given Test1's policy file CRLF. One bare write converted.
  - The revive skill describes the plain-archive path and the rule to explain only from records.

  Tests: `tests/test_archive_prepare.py`:
  - plain archive with a proven difference and no decision;
  - a recorded decision kept;
  - a refused archive records no licence;
  - LF;
  - the translate-batch proof.

  Each fails on the old code.
  An independent review the same day found problems, fixed in the same PR:
  - The translation proof was CJK counts plus any record in `reports/translation/`. Copying translate-batch's
    `export.json`, which it writes before translating, armed the proof for any such workspace. It passed a CSV that lost a
    Chinese row, and jars whose bytes happened to decode as CJK. Now it applies only to CSV and JSON-like files, and only
    when every difference replaces Chinese display text (`_translation_only`): a CSV keeps its rows and each changed cell
    held CJK; a JSON-like file keeps its structure and each changed value is a string that held CJK. Values are compared,
    so an id changed on the same line as a name fails.
  - The standing licence was written before `archive_mod`'s own refusals (an existing `Done/<Mod>`, a short
    `--allow-unexplained` reason). `prepare_archive` now only returns the CURRENT live result's date. `archive_mod`
    applies the standing decision in memory and writes it to `release_policy.json` only once the archive is written.
  - A gate passed by a live waiver has no run date, so the reason claimed "live-validated <today>". Now a waiver gives no
    standing decision, and the owner records one with `release-policy set`.
  - An unreadable record (SHIPPED_CHANGES.json) refuses with exit 2 instead of a traceback.
  - The workspace path is resolved before its id is read.

  Tests (each fails on the first version):
  - `test_a_translation_record_proves_nothing_but_a_translation`;
  - `test_a_refusal_after_the_gate_leaves_the_policy_as_it_was`;
  - `test_a_waived_live_result_gets_no_standing_decision`;
  - `test_an_unreadable_record_refuses_without_a_traceback`.

  Left as they were: a proof recorded on a refused attempt is keyed by path and not re-checked when the file changes again
  (older design); `record_group` still records the standing licence before `archive_mod`.
- 96.7 (S) **Release 0.4.1: the four security fixes.** The owner was asked, 2026-11-17, whether to tag a 0.4.1 with the javap
  fix once it merged, and to add a known-issue line to v0.4.0's release page: "yes". The security review that followed 93.45
  found 93.46-93.48.
  - **What 0.4.1 carries:** all four fixes (93.45 #113, 93.46 #115, 93.47 #116, 93.48 #117) and the v0.4.0 receipt (#114).
  - **What waits:** 96.5's performance items (P1 #118, P2 #119, P7) go into the next version, so this release is only its
    fixes.
  - **The notices:** v0.4.0's release page carries a known-issue note, added after #113. `docs/RELEASE_0_4_0.md` has a
    section listing the four problems and their fixes.
  - **The notes and the version:** `release-notes assemble --version 0.4.1` moved the five fragments under
    `## 0.4.1 (2026-11-17)`, and an empty `## 0.4.2 (unreleased)` takes the next ones. The package version is 0.4.1
    (pyproject, `bridgeforge/__init__.py`, `uv.lock`). Salvor's pin `bridgeforge>=0.4,<0.5` covers it.
  - **Publication:** tag and publish follow 0.4.0's process (`docs/RELEASE_0_4_0.md`). The receipt will be
    `docs/RELEASE_0_4_1.md`.

  **Done 2026-11-17: v0.4.1 is published, and is the first full release** (2026-11-18 01:02 UTC as a pre-release, made a
  full release at 01:23 UTC). The receipt is `docs/RELEASE_0_4_1.md`.
  - The annotated tag `v0.4.1` peels to `ed77cbb`, #121's merge.
  - Checked before tagging:
    - the full suite at that commit, in a clean worktree: 2987 tests, OK (skipped=12); hermeticity PASS;
    - main CI's nine jobs on that commit (run 44210899558). A tag push runs no CI since #107.
  - Wheel and sdist were built from a clean checkout. Every packaged file Git tracks equals its blob (wheel 400, sdist 722), and
    an installed-wheel check passed, before tagging and again on the wheel downloaded from the public release.
  - The draft's and then the public release's assets were downloaded. Both matched `SHA256SUMS.txt` and GitHub's digests, and
    the blob check passed again on the public download.
  - v0.4.0's release page now names all four problems and links v0.4.1; only that paragraph changed.
  - Owner, the same evening: "You can make it a full release instead of pre-release".
    - At 01:23 UTC v0.4.1 became a full release, marked Latest. Its notes' opening sentence now says so; nothing else changed.
    - Read back: the flags, `releases/latest`, the notes, the asset digests and the tag.
    - 0.4.0 and 0.2.0 stay pre-releases. A full release certifies the package, not any mod: the live work stays open.

**95. Less hand work and faster re-validation for game updates (owner 2026-11-17: "1 through 5 add to roadmap. 6 I'm not sure we can do that always but if it can be optional that would be great. All others approved."; "Implement the smaller items not the greater phases like S and G").**
**Approved.** Found taking the six-mod batch, United Aurora Federation and Sunrider through revival and live tests on
2026-11-16/17. Sizes: S small, M medium, L large; the small ones are implemented first, one pull request each. The S and G
phases are not part of this item.
Catalogue (owner: "start the scan on already revived mods ... just catalogue what needs to be done"): `target-impact` RC8 ->
0.98.5a-RC7 over the 175 mods in Done/ ran in about 5 minutes on Test1 (2026-11-17): CLEAN 167, BREAKS 4, RELINK 3, REVIEW 1.
Finding what a build changes is already quick; the time goes to full scans and live runs (95.7, 95.10, 95.11). BREAKS: Kadur
Remnant (the gated `jar-call-signature-changed` fixer clears it), Vayra's Sector (95.14), Neutrino Corporation 1.8.9 and Station
Augments (calls into obfuscated game classes: hand ports; check the authors' current releases first). RELINK: 95.13. REVIEW:
YunruCore's `hullmod:low_maintenance` collides with a hull mod RC7 added. Informational: Ironclads replaces `ship_data.csv`
without RC7's new columns `parts/dmod`, `salary` and `salMult`, read as blank (whether a blank salary changes crew costs is
unproven).
- 96.8 (S) **Release 0.4.2: 96.5's performance, CI and small items.** Owner 2026-11-18: "Go ahead with 0.42 release"
  (0.4.2, the version after 0.4.1), cut once C7/C8 (#137), A8 (#138), A9 (#139) and C4 (#140) merged.
  - **What 0.4.2 carries:** the 22 fragments since v0.4.1, now under `## 0.4.2` in CHANGELOG: save-doctor fixes (93.52,
    93.53, 93.55's FACTION_UNDEFINED) and the RC7 menu reader (93.54); 96.5's performance items P1, P2, P3, P4 and P7;
    the CI and tooling items C1, C3, C4, C5, C6, C7/C8; A3, A8 and A9; the 0.4.1 receipt, two archive records and two
    roadmap notes (93.49-93.51, the G series queued).
  - **This PR:** `release-notes assemble --version 0.4.2`; the version in `pyproject.toml`, `bridgeforge/__init__.py` and
    `uv.lock`; README, BUGS.md and ROADMAP_STATUS name 0.4.2; CHANGELOG opens `## 0.4.3 (unreleased)`.
  - **After it merges:** the full suite at the merge commit, main CI, wheel and sdist built and checked as for 0.4.1, the
    annotated tag `v0.4.2`, a full GitHub release marked Latest (as 0.4.1 became) with the wheel, sdist and
    `SHA256SUMS.txt`, and a receipt, `docs/RELEASE_0_4_2.md`.
  **Done 2026-11-18.** Published 2026-11-19 02:36:42 UTC as a full release marked Latest: source `4e71782` (#141), annotated
  tag `v0.4.2` (object `c5eb5f1`). Suite at the source commit 3075 tests OK; main CI passed (run 44443836062); 401 wheel and
  732 sdist files equal their blobs, checked again on the public download; the installed-wheel check passed on both wheels.
  `docs/RELEASE_0_4_2.md` is the receipt, with the asset hashes.
- 96.9 (S) **The live harness checks where it is, and logs when it acted.** After Escape, Exit and OK, `to_mission_list`
  clicked Missions blind. When those keys were lost (93.59: during the probe's save), the run went on clicking the campaign
  map until LIVE_STUCK, with nothing in the result saying why.
  - Read the screen after leaving the campaign: when no main menu is found (`screen_read.main_menu_buttons`), take a
    screenshot, press Escape again and retry once, then stop with a stage that names the screen, so the next unknown cause is
    recovered from or named.
  - Record each key and click with the game log's length at that moment. A stall report then reads, for example, "Escape at log
    offset X, 1.0 s after `campaign END`, while 'Saving to' had no 'Saving stage 8'". Today that took a manual log comparison.
  Priority: now, stacked on 93.59 (the remaining 96.2 live runs).
  **Done 2026-11-19.**
  - `live_run.to_mission_list` leaves the campaign, then reads the screen up to six times, a second apart, for the main menu's
    Missions button. If none is found it takes a screenshot (`<log>.leave-campaign.png`) and sends Escape, Exit and OK once
    more. If the menu is still not there, the run stops LIVE_STUCK at `leave-campaign` and nothing more is clicked. When the
    screen cannot be read the clicks are blind as before.
  - `drive` wraps the hands in `live_run.recording`. Every key, click and scroll goes to `LiveResult.actions` as
    `{t, action, log_bytes}`, and a stuck run writes them to `<log>.actions.json`.
  - Tests: `tests/test_live_run.py`, whose `FakeGame` gains a readable screen whose menu shows after N Exit-OK clicks:
    - a lost first exit is seen, photographed and sent again;
    - a menu that never shows stops at `leave-campaign` after one retry, with its actions saved;
    - a first exit that works needs no retry;
    - every action is recorded against a growing log.
    Removing the retry, or the recording, fails two tests each (mutation-checked).
- 96.10 (S) **`restore-from-done` for a re-port.** Porting Vayra's Sector to RC7 took three manual steps:
  - a September workspace of the same name made the restore refuse ("already exists"). It was moved to
    `In operation/_stale-2026-11-19/` by hand;
  - the restored REVIVAL_REPORT (the RC8 one, LIVE_VALIDATED) made revive's draft refuse ("Would overwrite"). It needed
    `revival-report-draft --force`;
  - Station Augments cannot be restored at all: its shipped folder is "Station Augments", not the archive's name.
  `restore-from-done --for-retarget` should move a stale workspace aside (never delete; DOC-001), keep the old report as the
  previous build's, and find the shipped folder from the archive's own record. Priority: now (Station Augments is a 96.2 port).
  **Done 2026-11-19.**
  - `restore_from_done` finds the shipped folder: `Done/<X>/<X>`, or else the archive's one other folder with a
    `mod_info.json` (`original/` and `workspace/` excluded). Two candidates are refused by name.
  - `--for-retarget` moves an existing workspace to `<queue>/_stale-<date>/` (a free name; never deleted), and keeps the
    restored REVIVAL_REPORT and REVIVAL_PLAN as `*.previous-build.md`.
  - `target_impact._workspace_for` treats any shipped folder of a `Done/<Archive>` as an archive, so "Station Augments" is
    restored, not acted on in place. Its restore step carries `--for-retarget`.
  - Tests:
    - `tests/test_workspace_tools.py`: a shipped folder named otherwise; two mod folders refused; an existing workspace kept
      without the flag and moved aside with it; reports renamed; a second re-port the same day keeps both stale copies;
    - `tests/test_target_impact.py`: the Station Augments layout gets a restore step.
  - Mutation-checked: without the rename, or with `original/` counted as a mod folder, a test fails.
- 96.11 (M) **Revive applies the build-change fixes it is approved for.** `jar-call-signature-changed` is found by
  `target-impact`'s API diff, not by the scan, so `revive --approve jar-call-signature-changed` changed nothing for Vayra's
  Sector, and the fixer had to run as `bridgeforge fix ... --finding jar-call-signature-changed --apply` (as for Kadur
  Remnant). When revive has a target core, it should run the jar linkage check against it so these fixers run in the normal
  flow (`relink` likewise). Priority: after the G series (it pays off at the next game build).
- 96.12 (S) **Syncing a mod into the rig leaves stale files.** `probe-group install`'s sync and `prepare-test --sync` add
  and update files and never remove one (`sync_working_copy`: "never deleting extras"). Broken Star's bf.4 fix moved two
  `data/weapons/decorative/*.wpn` into `data/weapons/`, and the rig copy kept the old ones. P962BS5 passed live, but record
  refused it: "staged files differ from the candidate working copy". It took a hand move to `_rig-0985a/_stale-staged-2026-11-19/`
  and a re-run (BS6). Sync should move a rig file the working copy no longer has into a dated holding folder in the rig
  (never deleting it), and say so. Priority: with 95.4.
- 96.13 (S) **The probe writes no combat END when a battle ends early.** `BfProbeCombatPlugin` writes `combat-perf`,
  `combat-summary` and `combat END` only once `combatSeconds` have passed. In P962SA2-LIVE-0985a-20261119 Station Augments'
  one frigate destroyed the filler enemy first: the game closed the battle (mission score 100%), and the probe wrote none of
  the three. The run ended LIVE_STUCK at combat-round-1 ("no 'combat END' probe line"), although the battle had ended. P962SA,
  where the fight lasted the full time, ended normally. The plugin should write them as well when the engine ends the combat
  itself. That needs a probe release, checked first against RC7's `CombatEngineAPI` for the call that says combat is over.
- 96.14 (M) **A tool for game classes the obfuscator renamed.** Neutrino Corporation and Station Augments both called game
  classes that RC7's obfuscator renamed with unchanged members (`systems.F` -> `systems.return`, `specs.do` -> `specs.M`,
  `ai.ooOO` -> `ai.C`, ...). Each port needed hand tools, kept in the workspaces' `scratch/rc7-remap/`:
  - a shape matcher over `javap` of both cores (`match.py`);
  - an exact member lister (`members.py`);
  - a constant-pool rewrite (`remap_class.py`);
  - a core-ASM remapper that renames declared interface methods and changed calls (`SaRemap.java`).

  `target-impact` should propose the old-to-new class and method map when it reports a missing obfuscated class, with each
  match's score and the evidence (shape share, agreeing field types). A gated fixer should apply an accepted map to a jar's
  classes, using the bundled ASM, and re-check linkage and interfaces. Priority: after the G series (the next game build).
- 96.15 (S) **A snapshot error that never clears.** Test1's `state-snapshot` reported one error on every run, "Permission
  denied" on `Done/_previous/Fuel-Siphoning-1.2.2/Readme.txt`. That file no longer exists. The error came from a
  `snapshot.partial.jsonl` line written before H4 (2026-10-12), which checkpointed the Done source together with its error.
  Each later run reused that line and never walked Done again, so the checkpoint was never finished and
  `snapshot-restore-check` (R8) refused.
  **Done 2026-11-19.** A checkpointed source that carries errors is walked again.
  Test: `tests/test_state_snapshot.py` `test_a_checkpointed_source_that_carries_errors_is_walked_again`. On Test1 the stale
  checkpoint was moved aside (kept as `snapshot.partial.jsonl.stale-20261119`) and a fresh snapshot started. Gate R8 stays
  open until that snapshot ends with no errors and `snapshot-restore-check` passes. That snapshot ended the same day with 0
  errors, and its checkpoint cleared.
- 96.16 (S) **A flaky research test on Windows CI.** `tests/test_research_inputs.py`
  `test_flags_reach_the_report_and_the_cache_lands_beside_the_report` failed once on Windows shard 3/4 for PR #185 (run
  44643449898): it found 2 cached `TemCrusade.java` copies where it expects 1. It passes locally, and main's run on the
  same merge commit passed (44644028462). Recorded 2026-11-19, after the PR was merged on an UNSTABLE status by mistake.
  **Done 2026-11-19, the same day.** It failed again in slice 5's local full suite and passed five times run alone. The
  cause is in the test, not the product:
  - The decompile cache is keyed by the jar's SHA-256, which is right.
  - The fixture's `make_jar` used `writestr(name, data)`, which stamps each entry with the current time. The working
    and original `Tem.jar` were built moments apart, so under load they could fall on either side of a zip timestamp's
    two-second boundary. They then hashed apart and made two cache folders.
  - Reproduced: two jars built 2.1 s apart hashed `1938697e…` and `38aaa31d…`.
  - The fix is a fixed `ZipInfo` time in `make_jar`. The same reproduction now gives one hash.
- 95.1 (M) **Owner rulings as standing policy.** The owner ruled the same way many times: CSV rows with no file that nothing uses
  (Musashi, Bultach, UAF: "keep them and ignore warning if it doesn't affect anything"), findings the reference build shares in a
  mod that works there (UAF: "Your clear to proceed"), and behaviour as authored with evidence (Sunrider: "yes"). Encode them as
  rules in `AUTOMATION_POLICY.json`, each with its evidence check (no reference found, unchanged on the reference build, guard
  present), so the acceptance is written with that evidence and only exceptions reach the owner. On 2026-11-17 the owner ruled on
  64 baseline findings (UAF 39, Sunrider 25) and 24 probe findings (Musashi 4, Bultach 2, Tania 6, UAF 12); measure on these how
  many the rules settle before enabling them.
- 95.2 (M) **Findings the previous build shares, labelled (93.34).** The owner's decision sheet shows what the target build changes
  first and the pre-existing findings apart.
  Added 2026-11-19 (96.2 lessons): also label a finding whose check is newer than the archive's live validation. Vayra's Sector's
  three `saved-object-holds-market-ref` packets came from a check added after its 2026-10-05 RC8 archive, so the same code was
  live-validated without them; the sheet should say so with both dates. Owner 2026-11-19, asked about the order of this
  session's suggestions: "if these are useful now prioritize their implementation now if not save them for after G series
  implementation or at your recommended order". Priority: after the G series (it pays off at the next game build).
- 95.3 (M) **One command per stage chain.** `revive-queue` (93.14): intake, revive, decision sheet, accept, input-tier fixes
  (`bridgeforge fix`, which revive does not apply), report draft; `live-queue`: install, smoke, live, report and record per group,
  unattended, resuming after the last finished step. Each of these is a separate command today, and the Test1 live runs needed
  hand-written task scripts.
  Added 2026-11-19 (96.2 lessons): the 96.2 runs used a hand-written `.cmd` per group (rig-doctor, install, live, report), then a
  separate record and archive. `live-queue PLAN --archive-on-pass` should record and archive a passing group under the owner's
  standing 96.2 permission ("archive them if they pass") and stop on anything else with its triage. Priority: now, the
  `live-queue` half (the remaining 96.2 groups and every re-test).
  **`live-queue` done 2026-11-19** (the `revive-queue` half stays open).
  - `bridgeforge probe-group live-queue --plan P [--group N ...] [--archive [--refresh] --note "..."]` (`bridgeforge/live_queue.py`).
    It runs the plan's groups in order: install (staging providers, probe save after checks, `--also-enable`), `live_run`,
    then `group_report`.
  - With `--archive`, a group that ended LIVE_DONE goes through `record_group(..., archive=True, accept=True)`. A run that
    did not finish is never recorded: its log and the harness's actions file (96.9) go to the summary.
  - The summary's `attention` list holds an error, an unfinished run, a member that did not PASS, and (with `--archive`) a
    PASS member left unarchived, with the reason record gave. Vayra's Sector passed live on 2026-11-19, then needed four
    things explained by hand before archiving: an uncovered caught exception, files changed by the RC8 revival's fixers, a
    junk copy and the resulting stale live result.
  - One progress line per group and a checkpoint (`("probe-group", "live-queue")` in `LONG_RUNNING_COMMANDS`).
  - On Test1 it still needs the direct-start overrides of `live-wrappers/live_direct.py` until 95.4: pass that `play`.
  - Tests: `tests/test_live_queue.py`:
    - passing groups archived, a stuck one not, and listed with its triage;
    - nothing recorded without `--archive`;
    - a failing member left out;
    - a PASS left unarchived listed with why;
    - only the chosen groups run;
    - an interrupted queue resumes after its last finished group;
    - a group's error does not stop the queue.

    Mutation-checked: recording a stuck run, recording without `--archive`, and dropping the unarchived-PASS rule each fail
    a test.
- 95.4 (M) **A live harness without wrappers.** Direct start (93.21), first-run preferences pre-flight and pins (93.28), the
  report's own run config (93.29), mission-list reading (93.37) and the run's own save (93.38) in `probe-group smoke|live|record`,
  so `bridgeforge-state/live-wrappers/` can retire.
  **Direct start done 2026-11-19; live confirmation on Test1 pending.** The pins (93.28), the report's run config (93.29), the
  mission list (93.37) and the run's save (93.38) were already in BridgeForge. The wrappers' remaining job was the direct start,
  done by patching BridgeForge at run time. It is built in now:
  - `bridgeforge/live/direct_start.py`. `DirectStart(resolution, client_top)` gives:
    - the game's JAVA_TOOL_OPTIONS (`-DlaunchDirect=true -DstartRes=WxH -DstartFS=false -DstartSound=true`), added to any
      already set;
    - the launcher resolution pin for the run;
    - `place_window`, which moves the game window so its client area starts at screen y `client_top` (Windows), in place
      of the launcher click.
  - `launch.start_game(..., env=)` gives the options to the game process alone; the wrapper set them process-wide.
  - `running_game`/`live_run`, `run_boot_test` and `smoke_group` take `direct=`. `live_queue` passes it to every group's run.
  - CLI: `probe-group live|smoke|live-queue --direct [--resolution WxH] [--client-top Y]`. `--resolution` and `--client-top`
    without `--direct` are refused, and so is `live --save-reload --direct` (the reload's second start still goes through
    the launcher).
  - Test1's runs become, for example: `probe-group live TESTID --direct --client-top -200 --bat run-j25-frpp.bat`.
  - Tests: `tests/test_direct_start.py`:
    - options, environment (the caller's not changed) and pins;
    - malformed resolutions refused;
    - `start_game` passes the environment;
    - CLI validation;
    - `running_game` with `direct` places the window and never clicks the launcher; without it, it clicks as before.

    Mutation-checked: always clicking the launcher, or dropping `env` from `start_game`, fails the tests.
  - Left: one Test1 run without the wrappers to confirm, then delete `live-wrappers/live_direct.py` and `smoke_direct.py`
    (`setup_frpp.py` writes the Fast Rendering + Prepatcher bat, 93.42); `--save-reload` with `--direct`.
  - **Confirmed live 2026-11-19.** On Test1, `probe-group live P954-DIRECT-0985a-20261119 --direct --client-top -200 --bat
    run-j25-frpp.bat` ran Broken Star's group (PLAN-962b group 2) with no wrapper script. It ended LIVE_DONE (main-menu,
    campaign, probe-saved, combat-1), and the report read PASS, FATAL 0, MOD-ERROR 0. Nothing was recorded: it was a harness
    check. The wrapper scripts are local and git-ignored; they go when the owner says so.
  - Wrappers deleted on both PCs 2026-11-19 (owner: "yes").
  - `--save-reload` with `--direct` added the same day. `save_reload_run.reload_run(direct=)` starts the reload's second game
    directly too, and the CLI no longer refuses the pair. This unblocks the gates that need a save-reload run on Test1:
    bf-0b-15 (SEEKER Betelgeuse) and bf-strag-station-augments. Test: `tests/test_direct_start.py` (the reload start receives
    `direct`). Without the pass-through the test fails.
- 95.5 (M) **Run-manifest hash reuse (93.27).** About 5 minutes per live run on Test1.
  **Done 2026-11-19.** `file_hash.cached_hashes(cache_file)` opens a hash cache keyed by resolved path, size and modification
  time (ns); inside it `sha256_many` takes unchanged files from the cache and hashes the rest in 8 threads, and the cache is
  saved when the scope ends. `run_manifest.prepare_run`, `staged_drift` (so `release_run`), `evaluate_run` and
  `environment_drift` open it at `<rig>/rig_hash_cache.json`; `live_trust.shipped_hash` and `run_manifest._tree_hash` go
  through it. The digests are unchanged, so manifests written before stay valid; outside a scope nothing is cached. The cache
  is a speed-up, not evidence: a file whose size or time changed is always hashed again. Tests: `tests/test_hash_cache.py`
  (reuse across scopes, a changed size or time re-hashed, no cache file without a scope, a foreign or unreadable cache starts
  empty, tree hashes equal with and without the cache), mutation-checked on the stamp comparison and the save.
- 95.6 (M, optional) **Two-machine sync.** `sync --to HOST` for the memory folder, workspaces and Done/, hash-verified in both
  directions, never overwriting a newer change without asking; off by default (owner: "if it can be optional that would be
  great"). On 2026-11-17 development ran on White_Legion and live tests on Test1, with workspaces copied by hand (scp).
- 95.7 (L) **Scan cache.** Split the scanner's checks into mod-only (cached by file hash and checker version) and build-dependent
  (linkage, API, compile, vanilla data), so a re-scan for a new build re-runs only the build-dependent ones.
- 95.8 (M) **Member-use index.** Index once which game classes and members each mod's jars and scripts use (corpus-index), so
  "which mods use what the new build changed" is a lookup over the api-diff.
- 95.9 (M) **Parallel scanning** across mods, with the existing checkpoint and resume.
- 95.10 (S) **Acceptances carried across builds.** Baseline keys are normalized already (92.x); carry each acceptance to the new
  target unless the finding's evidence changed.
  **Done 2026-11-17.** `retarget --apply` changes only mod_info.json, but its `+bf.N` version bump made every baseline
  STALE_VERSION. A baseline current before the retarget is now re-stamped at the new version, with
  `stamp.carried = {"from", "why"}`, and each key keeps its owner's reason. The evidence condition holds by construction: a key
  is `id|file|evidence`, so a finding the new core words differently is a new key and comes back for a ruling. A baseline
  already stale before the retarget stays stale. Review fix, the same day: when the version bump fails (a locked file), the new
  gameVersion is undone, so the next plan offers the retarget again instead of skipping it as "already" retargeted. Tests:
  `tests/test_target_bump.py` `test_retarget_carries_a_current_baseline_and_leaves_a_stale_one_stale`,
  `test_a_retarget_whose_version_bump_fails_is_undone_and_planned_again`.
- 95.11 (M) **Targeted re-validation.** On a new build, smoke every archived group and run full live tests only where
  `target-impact` is not CLEAN.
- 95.12 **Further suggestions** (owner asked "Anything else for bridgeforge, this process, or any sub modules like the probe etc?"):
  (a, S) a combat-round watchdog: no `combat|START` within a bound after the click means a screenshot and one retry (UAF's round 2
  waited out the timeout, 93.37; **Done 2026-11-17**, see 93.37); (b, S) the probe's log header carries its config hash, so `report` and `record` find the run's own
  config (with 93.29); (c, M) acceptance analytics: aggregate accepted findings across mods into proposed scanner rules (Sunrider's
  `initStar(id, "nebula_center_young", 0, 0)` is vanilla's own pattern, RC7's `star_gen_data.csv` gives radius 0; a library used
  behind an `isModEnabled` guard is optional, not undeclared); (d, S) a one-page owner summary per mod at archive time: fixes,
  rebuilt classes, acceptances, shipped changes; (e, M) rig bring-up on a new machine in one command (93.3, 93.5), with the
  licence-key presence check, preference pins and the mods' declared libraries (AshLib was copied by hand for UAF); (f, S) the
  live run minimises its own console window and records the desktop size (93.24); (g, M) probe combat rounds sized by hull count,
  one progress line per round (UAF's 86 hulls took two rounds, "hulls 61-86 of 86"); (h, S) a revive with `--providers` passes
  them to the report draft's compile check (93.36); (i, S) `TARGET_IMPACT.md` shortens obfuscated member names (one Station
  Augments descriptor ran to hundreds of characters). **(i) Done 2026-11-17:** names over 160 characters are cut in the markdown with
  their length; the JSON keeps them whole (`tests/test_target_impact.py`
  `test_render_shortens_obfuscated_member_names_and_the_json_keeps_them`).
- 95.13 (S) **target-impact points at `relink`.** The three RELINK mods (AoTD Vaults of Knowledge 5.0.7, Broken Star, Nightcross)
  and Sunrider share one member: `StarSystemGenerator.addStableLocations(StarSystemAPI, int)` returns a `List` on RC7.
  `bridgeforge relink` already recompiles return-type-only calls from shipped or decompiled source, unedited; target-impact's next
  step names jar-packets and patch-jar-class instead. Nightcross is not to be worked on (owner 2026-11-17: "nightcross armory has
  been superseded and can safely be ignored").
  **Done 2026-11-17.** A workspace gets `bridgeforge relink "<workspace>" --vanilla-core <new core> --apply`. An archived
  `Done/<Mod>/<Mod>` copy gets `restore-from-done ... --queue <Done's sibling In operation>` first, and its fix and relink steps
  then name `In operation/<Mod>`: the worklist had told `fix` to edit the archive in place, while `retarget` refuses archives
  ("archives move with `archive --refresh`"). When the queue still holds that workspace (`archive` copies), the steps fix it
  and say so instead of restoring over it; review 2026-11-17 found both cases. A loose mod folder keeps the jar-packets route,
  as `relink` needs a workspace. Test: `tests/test_target_impact.py`
  `test_an_archive_is_restored_first_and_a_workspace_is_relinked_directly` (fails on the old code).
- 95.14 (M) **A changed member's default argument, decided once.** `OfficerManagerEvent.pickPortraitPreferNonDuplicate` gained a
  `Random` and a rule exists, so Kadur Remnant clears with the gated fixer; `PersonBountyEventData.reportSuccess()` gained an `int`
  and Vayra's Sector is listed as a hand port. Record what RC7's own callers pass as a rule (`jar_call_rewrites`) with that
  evidence, so the fixer applies it in every mod that makes the call.
  **Done 2026-11-19** (owner the same day: "slot in 95.14 if possible to knock out Vayra").
  - Evidence, from both versions' `starfarer.api.zip`: RC8's `reportSuccess()` counted one success. RC7's
    `reportSuccess(int completedLevel)` counts one exactly when `completedLevel == getLevel() + 1`. RC7's own caller,
    `PersonBountyIntel`, passes its bounty's level, which a rule for every mod cannot know, so the rule passes
    `getLevel() + 1` and keeps RC8's progression.
  - A constant could not do this, so the rewrite has a second kind: `getter:NAME:()I:K` appends the receiver's `NAME()` + K
    to a no-argument instance call (DUP, the getter, BIPUSH K, IADD; no branch, so frames stay valid). The Java helper
    and `append_constant_argument` check that shape.
  - On a copy of Vayra's Sector's `VayraSector.jar` against RC7: both calls (`VayraPersonBountyIntel`,
    `VayraUniqueBountyIntel`) rewritten, unresolved `reportSuccess` references 2 -> 0. The port itself goes through 96.2.
  Tests: `tests/test_jar_call_rewrites.py` (scan, fix, rescan and a run under `-Xverify:all` that prints the passed
  argument, 4 for level 3, and fails with `+0`; gated off on the old API; malformed getter specs refused).
- 95.15 (S) **Superseded archives skipped.** Seven mod ids are archived twice (14 archives: PatchLib 1.1.0 and 1.1.2, AI Tweaks
  2.2.10 and 2.2.11, Vram Optimizer 1.0.50 and 1.0.51, SEEKER 0.3.0 and 0.6, Epta Consortium 2.0.3 and 2.1.3, Templars 0.9.8f and
  0.9.9e, Neutrino 1.87-RC3 Nostalgia Edition and 1.8.9), some on the owner's word (Templars and Epta, 2026-10-13). A superseded
  mark for a Done/ archive, set only on the owner's word, that target-impact, done-audit and 95.11 skip; Nightcross is the first.
  **Done 2026-11-17.**
  - `close` takes a `Done/<Mod>` archive too. It writes the existing dated section, ending SUPERSEDED or NOT_REVIVABLE, to the
    archive's `workspace/REVIVAL_REPORT.md`.
  - done-audit and target-impact list a closed archive (or closed queue workspace) by status instead of checking it.
  - Nightcross was closed SUPERSEDED on Test1 the same day, on the owner's word ("nightcross armory has been superseded and can
    safely be ignored"). The older duplicates were not marked: the owner chose "Only keep latest" (96.0), so they moved to
    `Done/_replaced-2026-11-17/`.
  - Review fixes, the same day:
    - A close beats a done-audit record cached before it.
    - `close` takes the `Done/<Mod>/<Mod>` path target-impact prints, and refuses a folder that is neither a workspace nor an
      archive.
    - A closed library still provides its jars to mods that depend on it.
  - Tests: `tests/test_done_audit.py` (`test_an_archive_the_owner_closed_is_listed_not_audited`, the checkpoint and refusal
    cases) and `tests/test_target_impact.py` (`test_an_archive_the_owner_closed_is_listed_not_checked`, `ClosedProviderTests`).

**94. Feature genome: extract and insert features across mods and builds (owner 2026-11-17: "design roadmap from now to endgoal of being able to extract and insert features like DNA"; "all approved. Please make sure everything is traceable and each repo gets a copy of its roadmap specific portion").**
**Review and decisions D1-D4 (2026-11-17):** FEATURE_GENOME_ROADMAP.md section 14. G1 starts after item 96 (D1),
no GUI or multi-game platform (D2), sister conformance tests when their phase starts (D3), BridgeForge stays Salvor's
save-diagnosis provider (D4); work packages WP0-WP7 in the order recorded there.
**Approved strategy addition (GD-1); in progress since 2026-11-19** (owner: "then begin G series after that"; G1's WP1-WP4
done, below). Design, decisions, estimate and sister entries:
[docs/FEATURE_GENOME_ROADMAP.md](docs/FEATURE_GENOME_ROADMAP.md). Ids: phases 94.G1-94.G7, decisions GD-1-GD-5,
refinements GR-1-GR-6 (approved 2026-11-17: one pinned gene.json contract with conformance tests, a gene census before G2,
history as the closure benchmark, a cross-repository trace check, an early Java probe spike, one licence ledger per mod). Commits and pull requests implementing a phase name its id in the subject. Estimate (section 13):
27-45 BridgeForge sessions, 13-21 in sister repositories, 27-43 rig boots or live runs, about 17-29 owner hours.
- 94.G1 **Gene contract and identity** (read-only): versioned `gene.json` (kind, anchors, members with hashes, needs,
  registrations, conditions, persistent state, build, provenance and licence, phenotype obligations); content-hash identity;
  `gene describe`. Acceptance in section 6.
  **WP1 Done 2026-11-19** (owner the same day: "then begin G series after that").
  - `bridgeforge/genome/gene.py`: `describe(mod, "kind:id")` builds `gene.json` schema 1 from `vendor-plan`'s closure for
    the six content kinds. Members are files, CSV rows and jar classes, each with a SHA-256:
    - a text file without its UTF-8 BOM, with LF line ends, no trailing spaces or tabs and no trailing blank lines
      (refused over 64 MB);
    - a CSV row as its named, non-empty, trimmed cells (cells past the header are not part of it);
    - a jar class as its bytes, named by the jar's path in the mod (`jars/x.jar!a/B.class`), found without following
      links or junctions out of the mod; an unreadable jar is skipped.
  - Identity is the SHA-256 of the kind and the members. Provenance and licence are recorded but are not part of it, and
    the manifest holds no machine path, so the same feature in another mod or folder is the same allele.
  - Needs: vanilla-provided parts and the mod's declared dependencies. Licence: `revival_licence`. Unknowns: vendor-plan's
    MISSING and SUSPECT lists, never dropped. One phenotype obligation per kind (G6 makes them probe obligations).
  - Registrations, conditions and persistent state are present and empty in schema 1; `collected_from` says
    `vendor-plan`. They are filled from archaeology with G2's campaign features and registration slicing.
  - `bridgeforge gene describe MOD KIND:ID [--vanilla-core CORE] [--write FILE]`. `validate()` checks every field's shape
    (sister repositories read these files), that the identity matches the members and that no member is listed twice;
    malformed input gives problems, never an exception.
  - Acceptance on White_Legion: 18 manifests, the six kinds on three batch mods (Sunrider, United Aurora Federation,
    Bultach Coalition; RC7 core). All valid; each described twice gives the same manifest; closures of 2-36 members (15 of
    them jar classes) with their unknowns listed.
  - An independent review's points are taken: a row with cells past the header crashed the hash; the jar lookup followed
    junctions, read a jar name as a glob pattern and stopped at a corrupt jar; `validate` raised on malformed shapes. The
    licence `reason` stays in the manifest: it comes from `release_policy.json` and its fragments, which are public here.
  Tests: `tests/test_gene.py` (a hull mod's closure with hashes and its suspect; the same feature copied into another mod
  with the other line ending is the same allele, a changed member a new one; a CSV row with a BOM, padding and an extra
  cell is the same, a renamed one is not; a text file's BOM, trailing space and blank end lines do not count; a jar class
  named by its jar path and a valid jar behind a junction not used; describing twice is identical; malformed shapes are
  reported; bad anchors refused; the CLI). Without the line-ending normalization, or the junction guard, a test fails
  (mutation-checked).
  **WP2 Done 2026-11-19** (GR-1: export, fixtures and pin).
  - `docs/contracts/gene/` is the contract a sister repository copies byte for byte:
    - `gene.schema.json`, a JSON Schema (2020-12) of schema 1;
    - `fixtures/`, two valid manifests (one hull mod gene, and the same gene from another mod and build, with the same
      identity) and nine invalid ones, each breaking exactly one rule;
    - `CONTRACT.json`, with the identity rule in words, every file's SHA-256 and each fixture's verdict.
  - The consumer pins `CONTRACT.json`'s SHA-256, as it pins `target export`. `bridgeforge gene contract` checks the
    committed folder against what `bridgeforge/genome/contract.py` writes and prints the pin; `--write` rewrites it.
    The sister repositories add their conformance tests when their phase starts (D3); WP3 reports pin drift.
  - Tests: `tests/test_gene_contract.py` (the committed folder is current; fixture verdicts follow `validate`; each invalid
    fixture breaks one rule; equal identities across mods; the schema requires what `validate` requires; every file listed
    by hash; `check` names a changed, missing or extra file). Mutation-checked: an unsorted identity and a dropped duplicate
    check each fail the tests.
  **WP3 Done 2026-11-19** (GR-4: `trace` and the cross-repository check with pin drift).
  - `bridgeforge gene trace ID` (`bridgeforge/genome/trace.py`) lists what cites a roadmap id: commits on HEAD, the pull
    requests whose merge brought them in, test files and documents. It is read-only and offline. An id matches only whole:
    `94.G2` is not `94.G21`, `96.1` is not `96.10`, and a full stop after it still counts. `trace 94.G1` lists the four
    citing commits, PRs #86, #110, #162 and #163, both gene test files and the documents.
  - `bridgeforge gene sisters` (`bridgeforge/genome/sisters.py`) reads section 12 of docs/FEATURE_GENOME_ROADMAP.md and each
    sister's linked entry, through `gh api`, or from `--clone REPO=DIR`. Failures:
    - an entry that does not cite a phase section 12 lists for it;
    - a 94.Gn that ROADMAP-3 lacks;
    - a missing GD-2, GR-1 or GR-4, or a missing link to the genome document;
    - an unreadable entry;
    - pin drift: a sister's `bridgeforge-pins/gene-contract.sha256` that differs from `gene contract`'s pin.

    Other phases an entry mentions (the track's "94.G1-94.G7") and a missing pin are reported as notes: D3 adds the
    conformance test when the sister's phase starts.
  - First live run, 2026-11-19: all six sister repositories OK (RevenantLib, Project-Salvor, Project-VoidSmith, SpriteForge,
    Project-Go, SPW). None pins the contract yet.
  - Tests: `tests/test_gene_trace.py`:
    - whole-id matching;
    - trace over a scratch git repository with a pull-request merge (commit, PR #7, test and document found; `94.G21` not);
    - section 12 parsed;
    - each broken promise is a problem; the track range only a note;
    - pin drift a problem, a current pin a note;
    - `check_sisters` reads through the given reader;
    - the real section 12 has six linked rows (listed in `tests/doc_tests.json`).

    Mutation-checked: dropping the id's trailing boundary, or the pin comparison, fails a test.
  **WP4 Done 2026-11-19** (GR-6: one licence ledger per mod, read in one place).
  - `bridgeforge/licence_ledger.py` answers what a mod's licence allows. `release_policy.json` and its fragments stay the
    only record, and `release.py` keeps the file format and its writers. Every other reader asks the ledger: `vendor-copy`,
    `vendor-plan`'s copy, dependency-substitutes, `revival_licence` (and through it `gene describe` and the archive note),
    case qualification and `release-policy show`.
  - `licence_allows(mod, use, paths=, target=)` covers three uses:
    - `local`: always allowed (GD-2);
    - `vendor`: a local-only source, or a local-only path of a releasable one, goes only into a local-only target, which
      must then stay local-only;
    - `distribute`: needs an explicit RELEASABLE decision and no local-only path among those given.
  - Path exceptions: a mod's entry may list `paths` (`prefix`, `local_only`, `reason`) for another author's sprites or a
    bundled library. A prefix is relative to the mod root, in posix form, and matches whole segments (`graphics/foo` is not
    `graphics/foobar`). A member matches by its file: `jars/x.jar!a/B.class` by the jar, a CSV row by its table. The
    policy load refuses `..`, absolute paths, drive letters and backslashes.
  - New: `release-policy path MOD PREFIX --reason R` (or `--remove`). It needs a recorded decision and keeps it. A new
    decision, and the standing licence that `archive` applies, keep the exceptions: a fragment replaces the whole entry, so
    `paths` is carried over.
  - Both copy paths pass the paths they copy. `vendor-copy` refuses a script under a local-only path of a releasable mod.
  - `revival_licence`'s answer is unchanged, so `gene describe` writes the same manifest. Schema 2 (PR B) takes the
    ledger's path verdicts into `gene.json`.
  - An independent review the same day found a real bug and four gaps, all fixed here:
    - A prefix that could never match (`./graphics/x`, `graphics//x`, surrounding spaces, `.`) was stored and protected
      nothing. It is now refused, and matching ignores case, since mods ship for Windows.
    - vendor-plan names a jar member by the jar's file name only (`x.jar!a/B.class`). An exception on any jar of that name
      now covers it, so it errs towards protecting too much.
    - A file name containing `!` or ` [` is no longer cut short. Only `<file>.jar!...` and `<file>.csv [id]` are member
      forms.
    - A fragment written by a checkout older than WP4 has no `paths` key. It now keeps the exceptions already recorded,
      and removing the last exception leaves `paths: []`.
    - Two mods whose keys differ only in punctuation (`a b`, `a_b`) shared one fragment file, a fault older than WP4.
      The second now gets a hashed name.
  - **Not covered yet:** the release gate does not look at path exceptions. `release` still packages a releasable mod
    with its local-only paths; only the copy paths and `distribute` refuse them. Wiring `distribute` into the release gate
    goes with the owner question below.
  - **Owner question answered 2026-11-19:** an UNRECORDED mod got two answers: the release gate passed it, while
    `distribute` refused it, as GD-2 read. The owner said "Go ahead and mark unmarked mods as releasable" and chose,
    of the options put to them, "Rule only: no decision = releasable". So:
    - `distribute` now allows a mod with no recorded decision, matching the release gate;
    - no records are written: 328 mods had none on Test1 that day, 176 in `Done/` (mostly raw folders of current
      third-party mods) and 152 workspaces in `In operation/`;
    - a recorded LOCAL_ONLY decision and a local-only path still refuse;
    - archiving still records the standing local-only decision for a revival (owner 2026-09-27).

    GD-2 is amended to match (docs/FEATURE_GENOME_ROADMAP.md section 11). Test: `UseTests` in
    `tests/test_licence_ledger.py` (red before the change).
  - Tests: `tests/test_licence_ledger.py` (14; `ReviewTests` covers the review's points, each mutation-checked):
    - an exception survives a new decision and the standing licence;
    - whole-segment matching for files, jar classes and CSV rows;
    - prefixes that leave the mod are refused;
    - the three uses, and a local-only path vendored only into a local-only target;
    - `vendor-copy` refuses a script under a local-only path;
    - `revival_licence` is unchanged;
    - the CLI;
    - an AST check that no module other than `release.py` and the ledger imports the policy internals.

    Mutation-checked: dropping the carry-over, matching by plain prefix, or `vendor-copy`'s path check each fails a test.
  **Schema 2 Done 2026-11-19** (advisor review the same day: settle the shapes G2-G4 need before any sister pins the
  contract; WP3's live run found none pins it yet).
  - `gene.json` schema 2 replaces schema 1, which is withdrawn (`CONTRACT.json` `withdrawn_versions: [1]`). WP1's 18
    acceptance manifests were local output, and no sister had pinned schema 1.
  - Archaeology elements have fixed core fields, so G2 can fill them without another version. An element may carry more
    (`additionalProperties` open in the JSON Schema):
    - a registration is `{locus, statement}`;
    - a condition is `{kind, subject}`;
    - a persistent-state entry is `{name, via}`.
  - `derived_from` is null, or `{identity, by, from_build}` for a gene that G4 adapted. `src-to-jar`, `relink` and remaps
    change class bytes and so the identity; this field keeps the lineage that G3 records. It is not part of the identity.
  - `licence` is the ledger's answer: `mod_decision`, `local_only_members` (the members a local-only path exception covers)
    and `decision`, which is LOCAL_ONLY whenever that list is not empty. A listed member must be a member.
  - Contract: `valid-adapted-gene.json` (derived, filled elements, a local-only member of a releasable mod) and four new
    invalid fixtures, each breaking one new rule. The new pin is `14dd2ff7…` (`gene contract` prints it in full).
  - Tests: `tests/test_gene.py`:
    - element, `derived_from` and licence shapes, each malformed case giving exactly one problem;
    - a member under a local-only path makes the gene LOCAL_ONLY while the mod stays RELEASABLE;
    - withdrawn schema 1 is refused.

    Plus `tests/test_gene_contract.py` over the new fixtures. Mutation-checked: dropping the licence narrowing, the
    element check, the `derived_from` check or the local-only rule each fails a test.
  **WP5 Done 2026-11-19** (the evidence header). A second advisor review the same day corrected the first: `gene.json` is
  what evidence is *about*, so the header is not put into it, and schema 2 stays as it is.
  - `bridgeforge/genome/evidence.py` defines the header every evidence file about a gene carries: G2's proofs, G6's
    phenotype runs, Salvor's save results and SPW's cost. It is its own small schema (`bridgeforge-gene-evidence`
    schema 1), versioned apart from gene.json, and it points at a gene by `{identity, schema_version}`.
  - Required core: `evidence`, `schema_version`, `kind`, `gene`, `produced_by {tool, version}`, `created_at`,
    `build {game_version}`, `inputs [{role, path, sha256}]` and `verdict`. A producer may add fields. The names follow what
    the suite already writes: gates.json and the run manifests (`schema_version`, `kind`, `created_at` in UTC), gene.json
    (`build.game_version`), and the interop design's gate states PASS/FAIL/NOT_RUN/UNKNOWN.
  - An input's path is relative to the folder the evidence was made from, in posix form. Absolute paths, drive letters,
    backslashes, and `.`, `..` or empty segments are refused: the repository is public, and the header names no machine
    path.
  - `header()` is the writer G2 calls. `gene evidence check FILE --gene GENE.json [--root DIR]` checks that the evidence is
    about that gene: same identity, same gene schema, not a withdrawn one. With `--root` it re-hashes each input and names
    one that changed or is gone.
  - The contract folder gains `evidence-header.schema.json` and `evidence/` (two valid fixtures, one with a producer's own
    fields, and six invalid ones, one rule each), judged against `fixtures/valid-hullmod.json`. One pin still covers it
    all (GR-1). The pin becomes `eb1120bf…`.
  - Tests: `tests/test_gene_evidence.py`:
    - a written header validates, checks clean, then reports a changed and a removed input;
    - another gene, another gene schema and withdrawn schema 1;
    - machine paths refused;
    - malformed shapes give problems;
    - the fixtures and the contract record;
    - the CLI.

    Mutation-checked: the identity comparison, the re-hash, the withdrawn rule and the path rule each fail a test when
    removed.
  **WP6 Done 2026-11-19** (the duplication audit). It is a report only: BridgeForge stays Salvor's save-diagnosis
  provider (D4), and no shared package is added. It ends in a baseline that can only shrink, as the advisor review asked.
  - A read-only survey that day mapped, by hand, where the package re-implements four things instead of calling the
    canonical function: class indexing, mod identity, save reading and lenient JSON. `bridgeforge/duplication_audit.py`
    turns that map into six per-function AST rules. `duplication-audit` prints them, with the canonical function each
    one should call:
    | Rule | Re-implementations | Canonical |
    |---|---|---|
    | `classfile-pool` | 9 | `scan/scan_classfile.py::_parse_class_file_uncached` |
    | `jar-class-walk` | 42 | `scan/scan_classfile.py::iter_class_files_in_jars` |
    | `mod-info-read` | 104 | `mod_files.py::read_mod_info` |
    | `version-text` | 14 | `corpus/corpus_releases.py::version_text` |
    | `save-xml-read` | 9 | `save/save_reader.py::parse_descriptor`, `iter_elements` |
    | `json-comment-strip` | 3 | `scan/scan_json.py::_parse_json_uncached` |

    Lenient JSON is the most consolidated; mod identity and jar class indexing are the most duplicated.
  - The rules are approximate by design. A zip writer that must walk every entry is not counted. A save tokenizer is
    a `*TAG*` regex applied in a `save/` module. Some span-editing walkers are missed (`build_tag._structural_depths`,
    `fixers/presets._object_bounds`). The baseline counts what the rules see, and they stop new copies of the common
    shapes.
  - `tests/duplication_baseline.json` lists all 185 functions found. `tests/test_duplication_audit.py` fails on a new
    one, naming the canonical function to call instead, and on one that is gone, so the baseline shrinks with each
    consolidation. After a deliberate change: `python -m tests.test_duplication_audit --write`.
  - Found by the survey and confirmed in the code, not fixed here:
    - `save/save_inspect.py::_mod_version_lookup` records a `{major, minor, patch}` version as None.
    - `content_parity.py::mod_id_of` takes the first `"id"` in mod_info.json by regex. If the dependencies come first,
      it returns a dependency's id.
    - `live/live_trust.py::save_made_with` is a second descriptor parser that resolves `versionInfo ref=` while
      `save_reader.parse_descriptor` does not, so the two can disagree.

    Each is a candidate for the first consolidation PR.
  - Tests:
    - each rule on its shape;
    - the canonical shapes are not flagged: a call to `read_mod_info`, a zip writer, and a `*TAG*` regex outside
      `save/`;
    - a nested function is credited once, and the audit skips its own module;
    - the CLI;
    - the ratchet.

    Mutation-checked: dropping the writer exclusion, nested crediting, the self-exclusion, the `save/` limit or the
    `read_mod_info` exclusion each fails a test.
  **GR-2 Done 2026-11-19** (the gene census, before G2).
  - `bridgeforge gene census CORPUS --write OUT` (`bridgeforge/genome/census.py`) counts, per mod:
    - feature kinds: the six content tables, variants, factions, industries, market conditions, abilities and `rules.csv`
      rows, plus code-only star systems and markets (`createStarSystem`, `addMarketplace` in the mod's jars);
    - for each lifecycle hook of the plugin `mod_info.json` names, how many features it sets up together.
  - Following the advisor review, a hook is followed into the plugin's own methods, recording the depth, and keeps raw
    counts plus the callee list, so the score can be redone without walking the corpus again. The counts:
    - registration calls;
    - distinct mod-own classes it builds or calls;
    - distinct game-API state changes (`add*`, `set*`, `create*`, `register*`, `spawn*` on `com/fs/`);
    - all invokes.
  - Loose-script plugins are a separate "source-only" bucket. The command prints one progress line per mod, keeps a
    checkpoint (it is in `LONG_RUNNING_COMMANDS`), counts each mod once by id and version (an archive's working copy wins
    over a raw folder), and skips `_` folders. `atlas_classfile` gains `method_targets`, the (owner, name) of every
    invoke per method.
  - Calibrated by hand against source before the corpus run:
    - Eridani `onNewGame` reaches `generate` at depth 1: `ECE_StarSystem` plus faction relations and the bounty entry,
      3 features;
    - Tania: each hook builds `TaniaGen` and makes at most one inline change;
    - Bultach is monolithic: `onGameLoad` has 6 features;
    - Scrapyard declares no plugin.

    Calibration found a double count, fixed: a registration call such as `addScript` had also counted as an API
    mutation.
  - **Census of Test1's `Done/`, 2026-11-19, 342 mods.** The per-mod output stays on Test1 under
    `C:\Users\exxec\BridgeForge-census\`; only these aggregates are recorded here.

    Kinds (mods with the kind / items):
    | Kind | Mods | Items |
    |---|---|---|
    | faction | 181 | 1045 |
    | variant | 175 | 13701 |
    | hull | 173 | 6868 |
    | hullmod | 162 | 3290 |
    | weapon | 150 | 8390 |
    | wing | 138 | 1237 |
    | rule | 137 | 21357 |
    | shipsystem | 127 | 1794 |
    | code: star system | 82 | 216 |
    | industry | 80 | 448 |
    | condition | 68 | 344 |
    | code: market | 46 | 239 |
    | ability | 29 | 65 |

    Plugins: 208 measured, 111 none, 22 source-only (under a tenth of those that declare one, so the bytecode numbers
    stand), 1 not found.

    Busiest hook, features per mod (mod classes + API mutation kinds + registration calls):
    | Features | Mods |
    |---|---|
    | 0 | 13 |
    | 1 | 44 |
    | 2-3 | 30 |
    | 4-7 | 36 |
    | 8 or more | 81 |

    **147 of the 208 measured plugins (71%) have a hook that sets up two or more features.**
  - **What it means for G2.** Registration slicing is the common case, not the edge case: most campaign genes will have
    to be cut out of a shared hook, and 81 plugins put eight or more features in one hook.
    - G2's order: content kinds first (closure exists), then factions (the most common campaign kind, mostly data), then
      code-built star systems and markets (82 and 46 mods), then rules.csv dialog trees (137 mods, 21k rows: large and
      hardest).
    - The 6-10 session estimate for G2 assumed slicing was the exception. Refusals will be common until slicing works at
      statement level. Re-estimate after the first sliced pilot (P3 Eridani, 3 features).
    - The score counts API kinds, not statements, and a deep helper can inflate it, so the 8+ bucket is an upper bound.
      The callee lists in the per-mod output allow a re-score.
  - Tests: `tests/test_gene_census.py`:
    - a compiled plugin's hook followed one level, with its counts;
    - no plugin and a source-only plugin;
    - each mod once, the archive preferred, `_` folders skipped;
    - an interrupted run resumes from its checkpoint, which goes only once the result is written;
    - the CLI;
    - `method_targets` parallels `method_calls`.

    Mutation-checked: the registration exclusion, in-class following, the archive preference, the `_` skip and the
    checkpoint finish each fail a test when removed.
  - **GR-3 (closure benchmark), checked the same day:** both machines hold at most eight `REMOVALS.json` records and
    eight `PROVENANCE.md` files with SUSPECT decisions, too few for a benchmark. Recommendation, not yet decided: build
    GR-3 from G2's own subtraction and isolation proofs as they accumulate, starting with P1-P3.
  Next: GR-5 (Java probe spike; it needs live testing, paused by the owner 2026-11-19), then 94.G2 starting with P1.
- 94.G2 **Sequencing and proof**: closure for campaign features and registration slicing; subtraction and isolation proofs per
  gene. Project Go exports a gene's strings as one unit. Acceptance adds (WP5): every proof file carries the evidence header
  and passes `gene evidence check` against its gene with `--root`. Started 2026-11-19 on the owner's "Sounds good continue",
  with P1 offline; the boot halves of the proofs wait for live testing (paused by the owner the same day).
  **Slice 1 Done 2026-11-19: `gene.json` schema 3 and P1's closure.**
  - Describing P1 (Scrapyard Armories `hullmod:sa_lobster_tanks`) showed two gaps:
    - the seven `sa_lobster_tanks_*` settings keys its script reads were only a SUSPECT covering the whole
      `settings.json`;
    - the vanilla lobster and food commodities it handles were not needs.
  - Schema 3 adds one general member kind, `json-entry`: `<file>#<JSON Pointer>`, hashed as the parsed value in canonical
    JSON, so `5` and `5.0` are one allele. It is general so that later pilots need no schema 4: `sounds.json`,
    `strings.json`, the part of a `.faction` a gene adds to.
  - For now it covers only object keys. A pointer to an array element or `-` is refused, and array membership stays an
    unknown. Schemas 1 and 2 are withdrawn (`WITHDRAWN_VERSIONS`, one list that `contract.py` and `evidence.py` import).
    `gene sisters` confirmed that no sister had pinned either. The new pin is `fea8aa10…`.
  - `bridgeforge/genome/closure.py` adds two rules, both on evidence only:
    - **Settings keys.** A key is a member when a member script passes it to a SettingsAPI getter: as a literal or a
      `static final String` constant in a `.java` file, or as the call's string argument in a jar class. It becomes
      `setting:<key>` in `needs.vanilla` when only the core has it, and missing when neither does. A key that only
      mentions a closure id stays SUSPECT at key level, never by prefix, and the whole-file SUSPECT goes.
    - **Commodities.** `Commodities.X` resolves against the core's own `Commodities` class constants, giving
      `commodity:<id>` when the core's `commodities.csv` has it. An unresolvable constant, or an id the core lacks, is
      missing, never dropped.
  - **P1 now:**
    - members: the row, the script, the sprite and the 7 settings keys;
    - `needs.vanilla`: `commodity:food` and `commodity:lobster`;
    - no SUSPECT and no missing.

    Its identity changed, as intended. Its `persistent_state` stays empty: `DATA_KEY` lives in the combat engine's
    `getCustomData()`, which is transient. The P1 proof files record that as evidence.
  - Tests: `tests/test_gene_closure.py`:
    - keys from literals and constants, not mentions;
    - the canonical value hash;
    - a fixture mod's keys sorted into members, a vanilla need, missing and key-level suspects;
    - commodities resolved against a compiled core class, with a retired id and an unknown constant missing;
    - keys from bytecode, only on SettingsAPI.

    Also new contract fixtures: `valid-settings-entries.json`, plus three invalid `json-entry` paths, each breaking
    one rule. Mutation-checked: 8 mutants killed. Two survived at first and showed real holes, now fixed: a commodity
    id the core lacks was dropped silently, and the bytecode owner filter was untested.
  **Slice 2 Done 2026-11-19: the static halves of the proofs, and P1 passes both.**
  - `bridgeforge gene prove MOD KIND:ID --out DIR` (`bridgeforge/genome/proof.py`) writes `gene.json` and two WP5
    evidence files into a fresh folder outside the repository, the first producer of the header. Each file carries
    `half: static`, and `boot: NOT_RUN` until live testing runs the boot halves.
  - **Subtraction:** a copy of the donor without the gene's members is scanned and compared with the donor's scan. The
    comparison is by the references each finding names, not by finding keys: `content-reference-unresolved` gathers all
    of a mod's unresolved references, so a key diff would hide a new one inside an old finding. Each new reference is
    one of:
    - a **dependent**, which names an id the gene provides: another feature uses the gene, an edge recorded in the proof;
    - a **leak**, which names another part of the gene (its class, a settings key, a sprite): the closure took something
      shared;
    - **unexplained**.

    PASS when every new reference is a dependent (advisor review 2026-11-19, which also set this acceptance).
  - **Isolation:** a carrier mod holding only the gene's members is scanned. A finding the donor has for the same file is
    inherited, and one about the carrier's own `mod_info.json` is the carrier's. Anything else fails it, as does a
    reference left unresolved outside the gene's provides and needs. The rule was chosen against P1's real carrier scan.
  - The copies leave what the gene does not own untouched. A CSV row is cut from the table's text, with the id column
    found from the header. A settings key's line is cut from `settings.json`. A value that spans lines means re-writing
    the file, and the proof says so. Jar members are zip-copied for these static scans only; the boot halves will use the
    JDK `jar` tool.
  - **P1 (`hullmod:sa_lobster_tanks`, gene `bb64ad41…`): subtraction PASS with one dependent, `data/hulls/sa_lobster.ship`
    (the Ebirah's built-in hull mod), no leak and nothing unexplained. Isolation PASS: an inherited Janino risk and the
    carrier's `mod_info` version.** Both files pass `gene evidence check --root` with 4 inputs re-hashed. The record is in
    `In operation/Scrapyard-Armories/genes/p1-sa_lobster_tanks-20261119/`.
  - The licence ledger's `member_file` now knows schema 3's `json-entry` form. Without that, a local-only path
    exception on `settings.json` would have missed the gene's settings keys.
  - Tests: `tests/test_gene_proof.py`:
    - CSV and settings-key cuts byte for byte, including a multi-line cell, the id column found from the header, and a
      refused multi-line value;
    - dependent, leak and unexplained;
    - a new reference inside a finding the donor already had;
    - isolation's inherited, carrier and failing cases;
    - `prove` end to end, leaving the donor untouched and refusing a used folder;
    - the CLI.

    Two bugs were caught before merge: a multi-line array's first line was cut, and a dotted class name hid a leak.
    Mutation-checked: 8 mutants killed.
  **Slice 3 Done 2026-11-19: a gene names the class the game loads.**
  - Describing P2 (`hullmod:tania_junkyard_spawner`) gave `src/data/hullmods/tania_Placebo_For_IDs.java` as a member.
    The game never loads a file under `src/`; it loads `jars/tania.jar!data/hullmods/tania_Placebo_For_IDs.class`.
  - vendor-plan prefers a class's source on purpose: RevenantLib rebuilds what it vendors from source, so `vendor-copy`
    and its copy plan are left unchanged. `gene describe` applies the load rule instead:
    - a loaded jar's class wins, and the source path goes into the member's reason;
    - otherwise a `.java` is a member only at its package path, where the loose-script loader looks;
    - otherwise it is missing ("the game never loads it").

    Members reached twice are one member.
  - P1's identity is unchanged (`bb64ad41…`). P2's member is the jar class.
  - Tests: `tests/test_gene_loaded_class.py`:
    - a jar class beats a source under `src/`, and a loose script of the same name;
    - a loose script at its package path is the member;
    - a source only under `src/` with no jar is missing.

    Mutation-checked: 3 mutants killed. vendor-plan's and vendor-copy's own tests still pass.
  **Slice 4 Done 2026-11-19: gene.json schema 4, combat plugins, and P2's first proofs (static FAIL, causes known).**
  - Schema 4 is meant to be the last bump G2 needs (advisor review). `GENE_KINDS` names every kind G2 will use, each with
    a phenotype obligation: the six content kinds plus faction, star-system, market, industry, condition, ability, rule,
    combat-plugin, campaign-plugin and custom-start. `describe` closes the content kinds and `combat-plugin`. The others
    are refused ("cannot be closed yet") until their pilot closes them. Schemas 1-3 are withdrawn; `gene sisters` showed no
    sister had pinned any. The new pin is `0878a8ed…`.
  - A `combat-plugin:<key>` gene is anchored on a key of `settings.json`'s `plugins` map:
    - that registration is a `json-entry` member, `data/config/settings.json#/plugins/<key>`;
    - it is also the gene's first `registrations` element;
    - vendor-plan gains a `classes=` seed, so the closure starts from the plugin class.
  - **Ids named by code:** a string literal in a gene's code that is exactly an id the mod or the core defines joins the
    closure, and vendor-plan runs again until no new id is named. A plugin's `spawnShipOrWing("x_Var1", …)` and
    `getHullMods().contains("x_spawner")` are its gene. P1's identity is unchanged.
  - **`proof.py`:**
    - nested JSON Pointers: a nested key is removed by re-writing the file, and the proof records it;
    - a jar that loses classes is written fresh from the donor's jar, never copied and then rewritten. A just-copied jar
      was locked on Windows during P2's first run;
    - the donor's users are found from the gene's content ids and registered classes.
  - **P2 = the whole `tania_CombatHandlerSpawner`:** 52 members (9 jar classes, the registration, 21 rows, 21 files) and
    28 provided ids. Those are all three spawner hull mods, the four amalgam hulls and their variants, and
    `tania_no_dp_cost`. The three spawner modes share one jar class, so a junkyard-only gene would need bytecode edits.
    That is a correct refusal, recorded here, not a hand-built narrower gene.
  - **P2's static proofs: both FAIL. The causes are known, and they are the proof tool's, not leaks in the gene:**
    - Subtraction removed the plugin's 9 classes from the jar copy but left their build sources in `src/`, so the scanner
      reports `bundled-source-stale` and `jar-source-not-rebuilt`. The fix: also remove a removed class's build source.
    - Some "unexplained" lines are the scanner's own aggregates (`differ:0`, `source-only:9`, `common prefix: tania_ (3
      ids)`) and name nothing. The fix: classify by the ids a line names and ignore pure counts, with a test.
    - Isolation: the carrier declares every donor dependency, but the plugin's code never touches MagicLib, giving
      `declared-library-unreferenced`. The fix: `needs.mods` lists only the libraries the gene's code references.
    - Subtraction did find three real dependents: `tania_invictus_Standard` (church revenge spawner and
      `tania_addsmods_norefit_luddic`) and `tania_redemption_Holy_Boss` (asteroid spawner).

    The evidence is in `In operation/Navarchy-of-Tania/genes/p2-tania_CombatHandlerSpawner-20261119/`.
  - Tests: `tests/test_gene_schema4.py`:
    - every G2 kind has a phenotype, and unclosable kinds are refused;
    - a plugin gene holds its registration, class and the ids its code names, and not an unrelated row;
    - an unregistered key is refused;
    - pointer tokens unescape;
    - the proofs remove and carry a nested registration;
    - a jar that loses classes is never copied and is written fresh without them.

    Mutation-checked: 8 mutants. Two survived and were handled: one is equivalent (the nested-key guard, which the cut
    regex already covers), and one exposed a test that patched the wrong function and is now fixed.
  **Slice 5 Done 2026-11-19: the three causes fixed; P2 passes both static proofs.**
  - **Build sources:** subtraction also removes the build source of each class it takes out of a jar, found by package
    and name, and the proof lists each one. The donor is untouched.
  - **`reports/` copied:** the subtraction copy keeps `reports/`. The scanner reads `src-to-jar`'s build record there,
    and leaving it out made every edited source read as "not rebuilt". This was a fourth cause, found while fixing the
    first.
  - **Summaries:** a scanner's own totals inside a finding (`differ:0`, `source-only:9`, `common prefix: x_ (3 ids)`)
    are set aside as `summaries` when they name nothing the gene provides. A count line that names a provided id is
    still judged.
  - **`needs.mods`:** only the declared dependencies the gene's code references, by library package (the atlas
    census table; loose-script imports and qualified names, jar class references). A dependency with no known package
    stays, since it cannot be shown unused. P2's needs are now `lw_lazylib`, without MagicLib.
  - **P2 (`combat-plugin:tania_CombatHandlerSpawner`, gene `30b25f83…`): subtraction PASS with three dependents (the
    `tania_invictus_Standard` and `tania_redemption_Holy_Boss` variants) and one summary. Isolation PASS.** Both pass
    `gene evidence check --root` with 26 inputs re-hashed. The record is in
    `In operation/Navarchy-of-Tania/genes/p2-tania_CombatHandlerSpawner-20261119-v2/`; the first FAIL run stays beside
    it. P1 still passes both.
  - Tests: `tests/test_gene_proof_fixes.py`:
    - a removed class takes its build source and keeps the other sources and `reports/`;
    - scanner totals are summaries while a real reference is still judged;
    - a count line naming the gene is not set aside;
    - a known library stays only when referenced, and an unknown one stays.

    Mutation-checked: 5 mutants killed.
  - Next: P3 (Eridani's Pantheon system, the first registration slice). Its `onNewGame` builds `ECE_StarSystem` and
    sets faction relations and a bounty entry in one helper, three features in one hook. The boot halves of P1's and
    P2's proofs wait for live testing.
- 94.G3 **Gene bank**: content-addressed store, alleles across the corpus, lineage, licence state; RevenantLib distributes genes
  from vanished authors (GD-3). The store's payloads live under `data_root()`, like `Done/`, never in this public
  repository; only manifests of the owner's own or permitted content become committed fixtures (2026-11-19).
- 94.G4 **Adaptation**: target-impact, gated fixers and `src-to-jar` at gene scope; Project Go carries translations; SpriteForge
  validates sprites and slots.
- 94.G5 **Insertion**: carrier mod first, then integration on workspace copies (GD-5); collision checks; XStream aliases
  (`ModPlugin.configureXStream`, 0.98.5a API) proven with Salvor; VoidSmith variants and faction-knowledge proposals;
  SpriteForge restyles on request.
- 94.G6 **Expression qualification**: per-kind probe obligations (S3), live runs on the 0.98.5a rig (item 93), SPW per-gene cost,
  Salvor add and remove on save copies.
- 94.G7 **Engineering**: composed carriers (VoidSmith checks fleet roles), agent-edited genes with independent verification,
  recipes; owner designs labelled as departures.
- Pilots (GD-4): P1 Scrapyard Armories `sa_lobster_tanks`, P2 Navarchy of Tania junkyard spawner, P3 Eridani Combine Pantheon
  system, P4 Bultach Coalition custom start. Local-only under GD-2.
- Multi-agent mode (owner asked 2026-11-17 "should we turn on ultracode for the genome phase?"; recommendation, not a decision): an
  eight-agent read-only assessment (two readers, two opposing assessors, a judge, a fact check and a policy check, a synthesis; 32
  corrections applied) recommends no standing ultracode: the track's pace is set by its one-at-a-time rig runs and the owner's
  hours, which workflows do not shorten. Use a workflow for single steps instead: 94.G2's per-donor reference hunts and the
  refutation round before a gene's first proof boot, and 94.G5's collision gap hunt before a carrier's first boot; owner decisions,
  rig runs and the other phases stay solo. Revisit after measuring the first 94.G2 workflow on pilot P1. It also found the
  unbounded jar reads of 93.33.

**93. Test rigs, probe targets and library dependencies (owner 2026-11-17: "yes, also bridgeforge is supposed to check for undeclared libraries and add them. If not implement it and continue to make suggestions").**
**Approved; 93.1-93.2 and 93.26 done, the rest queued after the six live tests.** Found preparing Test1 for the six-mod live run (2026-11-17).
**Live tests paused by the owner 2026-11-17** ("lets pause live testing for now. I will sort that out later"): Test1 has no
licence key stored (93.20). 93.20-93.25 were found that day and added under the owner's standing instruction to keep adding
findings (2026-11-16); queued with the rest. **Resumed the same day** once the owner supplied the key; all four groups reached
LIVE_DONE on Test1 through `bridgeforge-state/live-wrappers/` (direct start at 1920x1440, window client top -200), after the first-run
fixes of 93.28. 93.26-93.35 are that day's findings.
- 93.1 **Done 2026-11-17.** **Optional library use misread as required.** Undeclared-library detection and its fixer already existed
  (`undeclared-library-dependency`, unguarded use declared from `LIBRARY_DEPENDENCY_IDS`; guarded use left alone, Exigency
  2026-09-28), and the batch's mods declare their libraries. But Navarchy of Tania's and Bultach Coalition's Nexerelin use became
  REVIEW agent packets that failed twice each: Tania because two jar classes import Nexerelin types they never use, Bultach because
  it mixes an isModEnabled-guarded plugin with a custom start registered in `customStarts.json`. Built: a source whose shipped
  class (in the mod's jar) references nothing of the library is not counted (judged from bytecode: a loose script the game
  compiles can fail on an unused import, so it still counts); a registered custom-start class counts as guarded. Both mods now
  get the SAFE `optional-library-integration` note. Tests: `tests/test_batch_lessons.py` (incl. the loose-script counter-case).
- 93.2 **Done 2026-11-17.** **Libraries the check did not know.** BoxUtil (id `BoxUtil`, `org/boxutil/`; Eridani depends on it)
  and AshLib (id `ashlib`, `ashlib/`) were in neither table, read from zz BoxUtil-1.4.9 and Ashlib-2.2.3. Added to
  `BUNDLED_LIBRARY_PACKAGE_PREFIXES` and `LIBRARY_DEPENDENCY_IDS`, so an undeclared use is found and declared. Tests:
  `tests/test_batch_lessons.py`.
- 93.3 **One command to make a test rig.** `_rig-0985a` on Test1 was built by hand (junction to the core, launcher copied, four
  folders, six libraries copied). `rig-create-test --core <starsector-core> --libs-from <mods folder> --name _rig-<build>`: create
  the folders and junction, write launchers, record the core's build in `rig_up_state.json`, never touch an existing rig.
- 93.4 **Every rig states its build and refuses the wrong one.** Test1's `_rig` pointed at RC8 while the target was 0.98.5a, and
  `C:\Games\Starsector-0.98.5a-RC3` turned out to be RC3 (92.40). `rig-doctor`, `probe-group install|smoke|live` print the build
  the rig's core reports and refuse when it is not the target build (override with a flag and a reason).
- 93.5 **Rig libraries from the mods' dependencies.** BoxUtil was missing from the rig and noticed only by reading Eridani's
  mod_info. `probe-group install` resolves each declared (and 93.1-detected undeclared) dependency by id from a libraries folder,
  copies it, picks one version when several exist (MagicLib 1.5.6 and 1.6.1 side by side), and flags a library whose own
  `gameVersion` predates the target.
- 93.6 **Name-faithful copies.** `tar | ssh tar` turned Eridani's CJK file names into code-page mojibake (92.40); file counts and
  content hashes still matched. Rig sync and any cross-machine copy compare names byte for byte.
- 93.7 **Run where there is a desktop, or refuse.** A game started from an SSH command lands in a non-interactive session.
  `smoke`/`live` detect it and either refuse with the remedy or launch through an interactive scheduled task in the logged-on
  user's session (`schtasks /IT`), streaming the log back. Delete the task after its run: a one-off task created with
  `/SC ONCE /ST 23:59` and started at once with `/Run` also fires by itself at 23:59 that day (three such tasks were found and
  deleted on Test1, 2026-11-17).
- 93.8 **Pre-flight before clicks.** User logged on and unlocked, expected resolution, no other Starsector/java process
  (`who-locks`), rig not held by another run manifest; today all by hand.
- 93.9 **Launchers that travel with the rig.** `run-j25-direct.bat` hard-codes `_rig\jdk-25...`; a new rig works only by borrowing
  it. Resolve the JDK relative to the rig or from one shared JDK location.
- 93.10 **Probe targets from the applied fixes.** Generate probe checks from the revive ledger: Tania's junk-fleet spawn in combat
  with an AI-replacement mod (the captain fix), Lobster tanks on two ships, Bultach's per-ship hull mods, KoC's `dual_apmg` load
  line, Eridani's translated rules lines, crafted descriptions present in the codex.
- 93.11 **AI-replacement compat set.** The owner runs AI Tweaks, and the module/spawned-ship captain crash is AI-replacement specific
  (RC8 report pending confirmation); a standard compat set with it turns that risk into a tested one.
- 93.12 **Paired before/after runs.** The same probe scenario on the RC8 rig with the original mod and on the 0.98.5a rig with the
  revived one, diffed (`behavior-diff` exists; nothing pairs the runs).
- 93.13 **Known-noise baseline per build.** Log lines a clean rig with only the libraries produces on each build, so `log-triage`
  reports what the mods add.
- 93.14 **One command for a batch.** The six-mod batch ran intake -> revive -> standard approvals -> agent packets -> src-to-jar ->
  descriptions -> translation -> revive by hand, per mod. `revive-queue` chains it and stops only at owner decisions, gathered
  into one decisions sheet for the batch (`escalation sheet` builds one).
  **Closed 2026-11-19 (roadmap review): superseded by 95.3.**
- 93.15 **Rebuild the jar right after an agent fix.** `src-to-jar` runs only in an approved revive. `escalation run --apply` runs it
  when a jar mod's source fix verifies, taking library jars from the reference install's `mods/` so `--lib` is not needed.
- 93.16 **Packets say the source is jar-backed.** Bultach's agents also removed `readResolve` and moved unlisted fields
  (`rightArm`, `nearbyShips`); a packet for a jar-backed source says "compiled into jars/X.jar and rebuilt by src-to-jar" and
  lists every field the fix may move.
- 93.17 **Parallel agent packets.** Bultach's 33 packets ran one after another (about 40 minutes); packets on different files are
  independent and can run a few at a time (bounded, item 76's E3).
- 93.18 **A machine-independent workspace bundle.** Move workspaces as a zip with UTF-8 names (zip's language-encoding flag; tar
  through the Windows console mangled them, 92.40), and keep paths in workspace reports relative: Test1's packets and REVIVE.json
  still name White_Legion paths.
- 93.19 **Warn about a stale installed copy.** The project `.venv` holds an old non-editable `bridgeforge` in `site-packages`; a
  script run outside the checkout imported it and got old code (2026-11-17). `doctor` warns when the installed copy and the
  checkout differ.
  **Closed 2026-11-19 (roadmap review): already built.** `hygiene.py` `installed_package` check (96.5 A2).
- 93.20 **No licence key on the rig machine (owner to sort out).** Group 1's smoke on Test1 (G1-SMOKE-0985a-20261117) sat at
  the launcher for 240 s (its log ends at the launcher's fonts) and was reported SUSPECT_FATAL_DIALOG. Test1's Java preferences
  for the game (`HKCU\Software\JavaSoft\Prefs\com\fs\starfarer`) are empty: no `serial`, and none of the values a played game
  leaves (`first/Game/Run`, `controls1`, `resolution`); White_Legion's hold them. RC7's launcher-preferences class reads the key
  there (`Preferences.userRoot().node("/com/fs/starfarer").get("serial", null)`, javap 2026-11-17), and both the launcher and the
  direct start (93.21) check it. `rig-doctor` and `smoke`/`live` check that the value exists (never read out, print or copy it)
  and refuse at once with the remedy: start the launcher on that machine once and enter the key.
- 93.21 **Start the game without the launcher.** RC7's `StarfarerLauncher.main` checks the system property `launchDirect`; when
  it is set and the stored key validates, it starts the game at `startRes` (`WxH`), `startFS` and `startSound` and never builds
  the launcher (javap 2026-11-17; RC8's jar has the same four names in the same classes, not disassembled). The launcher's own
  JVM restart uses the same properties: on Play, when `GLLauncher` gets true from `shouldRestartOnLaunch` (settings.json
  `allowJVMRestartFromLauncher` on and the launcher's memory above the running JVM's), `Utils` rebuilds the command line (the
  running JVM's arguments with `-Xms`/`-Xmx` replaced, plus `-DlaunchDirect` and `-DstartRes=... -DstartFS=...
  -DstartSound=...`), runs it from a shutdown hook (`Utils$2`, `Runtime.exec`) and calls `System.exit`, which would end the
  process the harness watches and leave the new JVM's console output in pipes, not the run's log. RC7 ships the setting false,
  so Play normally starts the game in the same JVM (`goToState("launch_game")`); a mod that turns it on would bring the restart
  back. `launch.start_game` passes the four properties through `JAVA_TOOL_OPTIONS` when the core has them and keeps the click
  for cores without: no click to miss and no restart. `startSound=true`, because the main-menu marker is a music line. Test1
  2026-11-17 (G1-DIRECT-0985a-20261117): the JVM picked the properties up and exited with 0 right after "Loading settings", the
  key check having failed (93.20). Proven live 2026-11-17 once the key was stored: G1-SMOKE-direct-0985a-20261117 reached the main
  menu in 96 s, and every group's live run started this way through `bridgeforge-state/live-wrappers/`; the harness itself still
  clicks the launcher until this is built.
  **Closed 2026-11-19 (roadmap review): superseded by 95.4.**
- 93.22 **The rig window must fit the desktop.** The live click fractions were measured in a 1920x1440 window
  (`rig_prefs.RIG_RESOLUTION`); Test1's desktop is 1920x1080 at 96 DPI (2026-11-17), so that window runs off the screen.
  Pre-flight (93.8) compares the desktop with the pinned size and refuses with the remedy (a larger desktop mode, or click
  fractions measured at another size).
- 93.23 **A launcher click that misses is retried and recorded.** `launcher_click.click_launcher_once` posts one click at
  50%/68% of the window (measured on RC8's launcher) and never again; on Test1 the run then waited out its timeout. Retry until
  the log moves past the launcher and capture the launcher window at each try. Lower priority once 93.21 lands.
  **Closed 2026-11-19 (roadmap review): culled.** The item itself says lower priority once 93.21 lands; 95.4's direct start removes the launcher click.
- 93.24 **Captures that show the game window.** On Test1 the full-screen capture (`window_watch.save_screenshot`) showed the
  scheduled task's console where the launcher was, although the launcher was the foreground window and set topmost, and the
  taskbar clock in both captures was 12 hours old (G1-SMOKE-0985a-20261117-no-main-menu.png and the G1-PEEK-0985a-20261117
  experiment, 2026-11-17). Capture the game's own window (`PrintWindow` with `PW_RENDERFULLCONTENT`), start the task's console
  minimised, and record the desktop size with each capture.
- 93.25 **Two stale notes.** `probe_group.smoke_group` says `run-j25-direct.bat` starts java "so there is no launcher to
  click"; the bat starts `StarfarerLauncher`, which shows the launcher ("direct" means without `starsector.exe`). The
  `signature_rewrites`/`jar_call_rewrites` notes that 0.98.5a has only `ShipAIConfig(ShipAPI)` hold for RC3: `api-diff` RC3 ->
  RC7 (2026-11-17: 3172 classes, none added or removed, two changed) shows RC7 restored the public `ShipAIConfig()` and added
  `SettingsAPI.getAllMissileSpecs()`, so the gated `ShipAIConfig` rules stay closed on RC7, as designed (`_gate_open`). The same
  diff keeps RevenantLib's RC3 target (its PR #4, merged 2026-11-17) valid for RC7: `ShipAPI` is identical (312 methods).
  **Done 2026-11-17.** Corrected: `smoke_group`'s docstring now says the bat shows the launcher and the boot clicks Play; the
  `signature_rewrites` and `jar_call_rewrites` notes now say "0.98.5a-RC3", with RC7's restored constructor. Test:
  `tests/test_signature_rewrites.py` `test_a_core_with_both_ship_ai_config_constructors_keeps_that_gate_closed` (RC7's shape:
  `new ShipAIConfig()` left alone, `isBeingIgnored()` still rewritten).
- 93.26 **Done 2026-11-17.** **Owner acceptances reach content parity.** `probe_accepted.json` entries never applied to
  content-parity lines (`group_report` added `parity_failure_lines` after the per-line acceptance), so Musashi's four CSV rows with
  no .ship/.wpn file (owner: "keep them and ignore warning if it doesn't affect anything"), Bultach's two and Tania's two stayed
  FAIL. An entry `{"check": "content-parity", "subject": "<kind>:<id>"}` now removes exactly that id
  (`live_content_parity.apply_acceptances`); a bare kind accepts nothing, a capped list keeps failing for the ids it did not list,
  and the verdict lists what was accepted. The expected ids also skip a CSV row whose first cell starts with `#`, as the game does
  (Tania 1.0.1's `#Weapon Name,id,...` template had been expected as a weapon "id"). Tests: `tests/test_live_content_parity.py`.
  Extended the same day to `probe-group record --accept`: `group_accept.assess_group` keys the probe's raw line as
  `content-parity|mod=<id>`, which no per-id entry matched, so Tania's passing re-run G4B-LIVE-0985a-20261117 still stopped
  ("findings no earlier acceptance of the same mod version covers"). `group_accept._parity_entries` covers that key when every id of
  the mod's content-parity FAIL lines is accepted and no list was capped. Tests: `tests/test_group_accept.py`.
- 93.27 **Reuse run-manifest hashes.** Every live run hashed each enabled mod folder whole before the game started (about 5 minutes
  on Test1: wrapper 08:14:20, game 08:19:16 for group 1, with GraphicsLib and Scrapyard) and again at release. Keep (path, size,
  mtime, hash) per rig, re-read only changed files, hash in parallel. Owner 2026-11-17 followed the recommendation to build it after
  the six live tests, so the batch's evidence stays one method.
  **Closed 2026-11-19 (roadmap review): superseded by 95.5.**
- 93.28 **First-run game preferences.** A Windows user who never played shows "Key configuration options have changed" over the
  main menu and cannot skip the tutorial (rules.csv `ngcSkipTutorialNoSkip`, "Need to start at least one game with the tutorial in
  order to be able to skip it"; `NGCCanSkipTutorial` is `!isNewPlayer()`, backed by the Java preference `canSkipTutorial`). Test1
  needed both besides the licence key (93.20). Pre-flight lists them; `rig_prefs` pins `canSkipTutorial=true` for an unattended New
  Game and restores it.
  **Done 2026-11-17 (code; first live run with it still to come).**
  - `rig_prefs.LIVE_PINNED` adds `can/Skip/Tutorial=true` to the resolution pins. Java stores each capital as "/" plus the letter;
    the names were read from both machines' registries. `probe-group live` pins it and restores the owner's state, absent included.
  - `rig-doctor` has a `launcher_prefs` check: FAIL with no licence key, WARN with no stored controls (`controls/Version`, the
    key-configuration dialog), a note when canSkipTutorial is unset.
  - `rig_prefs.has_pref` asks the registry for a value's size only, so the licence key is checked for presence and never read.
  - Tests: `tests/test_rig_prefs.py` (the pin and restore, `FirstRunPreflightTests`) and `tests/test_one_launcher.py` (the live run
    passes `LIVE_PINNED`).
  - Review fixes, the same day: rig-doctor's tests no longer depend on the Windows user's preferences (a CI runner has none,
    which would FAIL the check). `HasPrefTests` runs the presence check against a throwaway registry key and fails if any value
    is read.
- 93.29 **A report reads its own run's probe config.** `probe-group report` uses the rig's current config, so group 3's report after
  `install 4` named Tania instead of KoC (2026-11-17). Keep the config, or its hash, with the run manifest and read that.
  **Closed 2026-11-19 (roadmap review): superseded by 95.4.**
- 93.30 **Scenario testbed (owner design 2026-11-17).** Hidden mission factions whose fleets the code builds by hand (Tania's Blood
  Trail and Frost Fire: `createEmptyFleet` then `addFleetMember("tania_blood_stork_main_Death_Special")`, spawned by
  `tania_mission_unlocker_per_rep` at WELCOMING/FRIENDLY standing) cannot be exercised by `faction-fleet-gen`. Owner: "start a new
  game as usual but then save then modify save to either advance in time or modify it to trigger shortly after start", instead of
  waiting in-game days; and (approved) field such fleets' named variants in the probe's combat rounds. Not only Tania: find
  `createEmptyFleet`/`addFleetMember` calls and their triggers, propose the save edit (Salvor), reload, check the spawned fleet.
  Tania was archived before this exists (owner: "For now archive Tania and we can create the testbed after").
- 93.31 **Sound files the game cannot load.** Bultach 1.1.7's `melta_fire.ogg` is FLAC in an Ogg container and the game decodes only
  Vorbis ("This Ogg bitstream does not contain Vorbis audio data"); re-encoded with ffmpeg libvorbis on the owner's word ("Fix it"),
  explained in SHIPPED_CHANGES.json (no file of the mod plays it). Add a scanner check for non-Vorbis and empty `.ogg` files and a
  fixer that re-encodes when ffmpeg is present.
- 93.32 **Fewer acceptances: content the game cannot load is information.** CSV rows with no .ship/.wpn/.system file (Musashi 4,
  Bultach 2) and systems a mod creates only under a condition (Tania's `Zufalliger Krieg`, Nexerelin random mode only) are not
  shortfalls: report them as INFO with the reason, so the owner rules only on what can matter.
  **Closed 2026-11-19 (roadmap review): superseded by 95.1.**
- 93.33 **Bounded jar reads (hardening gap, found 2026-11-17).** `scan_classfile.iter_class_files_in_jars` (`archive.open(item)`
  then `.read()`) and `behavior_discovery.py` line 182 (`archive.read(member)`) read class entries of untrusted jars unbounded, against
  the `zipsafe.read_limited` rule, and `tests/test_safeio_ratchet.py` does not count zip reads. Found by the 2026-11-17 ultracode
  assessment and verified.
  **Done 2026-11-17.** A check over the whole package found 35 such reads in 25 modules, not two. Each now goes through
  `zipsafe.read_limited` (class entries at `MAX_CLASS_BYTES`) or `zipsafe.entry_sha256`, a streamed hash used by intake's
  written-file check and by done-audit. Tests: `tests/test_safeio_ratchet.py` `BoundedZipReadTests` fails on any new
  `ZipFile.read`, or `.open(...).read()` without a size (an AST check over the package, with detector cases);
  `tests/test_untrusted_input.py` covers the streamed hash and an oversize class.
  An independent review the same day found three more problems, fixed in the same PR:
  - Per-entry skips had gone into `unreadable`, which made verify-shadow's `jars_checked` wrong. They now go to their own
    `skipped_entries` list (verify-shadow reports `skipped_classes`).
  - `supersession.py` still read a corpus zip entry whole: its handle came from `cache.get(s) or cache.setdefault(s, ZipFile(...))`.
    The detector now follows such expressions, checks each function separately, and covers chained `.open(x).read()`.
  - Seven walks catch errors per jar, so one oversize class ended the walk of its jar. They use `zipsafe.read_class`, which
    returns None for that class, and read on.
- 93.34 **Findings that are already so on the previous build.** UAF 0.8.4c runs in the owner's RC8 game, yet its first revive listed
  115 findings: most (over-budget variants, oversized weapons, missing descriptions, unused weapon files, hull-mod instance state,
  the `fearless` personality no vanilla build defines) are identical on RC8. Mark each finding the reference build shares as
  "pre-existing, unchanged on <build>" and separate it from what the target build changes, so a mod that works does not read as
  broken (owner 2026-11-17: "UAF works fine under RC8, I'm surprised these are all detected issues?"). Check the
  `script-sandbox-forbidden-api` rule against UAF's live boot: its mod plugin loads on RC8.
  **Closed 2026-11-19 (roadmap review): superseded by 95.2.**
- 93.35 **Fast Rendering and Prepatcher on 0.98.5a.** The installed Fast Rendering v1.0.0rc1 (readme: "Starsector 0.98a-RC8 Windows")
  and StarsectorPrepatcher 0.18.4 (gameVersion 0.98a-RC8) are RC8 builds; Fast Rendering patches game classes with an ASM agent.
  `java-matrix setup` already has the `fr` launcher and `--prepatcher`; add them to the 0.98.5a rig once 0.98.5a builds exist and a
  smoke boot proves them.
  **Closed 2026-11-19 (roadmap review): superseded by 93.42.**
- 93.36 **The report draft cannot be told where the libraries are.** `revive --draft-report` checks the compile against the queue
  folder and `_rig/mods` only; White_Legion has no rig, so Sunrider's draft stayed BLOCKED on "5 javac error(s)" that were only
  LazyLib and MagicLib not found, although `revive --providers` named a mods folder holding both (it feeds missing-content packets,
  not the compile check). `revival-report-draft --providers <RC8 mods>` then drafted READY_FOR_LIVE_TEST (compile-check: 0 errors in
  14 loose scripts, Janino 14/14). Pass the providers through, or fall back to the reference install's `mods/`.
  **Done 2026-11-17.** Both: `revive._provider_roots` now serves revive's scan and `--draft-report` alike (rig, queue,
  `PROVIDER_SOURCES.json`, the reference install's `mods/`), and the draft adds the `--providers` folders. Test:
  `tests/test_revive.py` `test_the_report_draft_resolves_libraries_where_the_scan_does_and_in_named_providers` (fails on the old code).
- 93.37 **The live harness misses the probe mission in a long mission list.** United Aurora Federation adds its own missions; in
  UAF-LIVE-0985a-20261117 combat round 1 started and ended, round 2's line was logged ("hulls 61-86 of 86; restart the mission"), and
  no `combat|START` followed, so the click back into the mission list did not start the probe mission. Read the list from the screen
  before each round's click (as the main menu already is), and re-run UAF's round 2 once fixed.
  SR3-LIVE-0985a-20261117 (Bultach Coalition alone) stopped the same way: round 1 ended at 231.7 s, the game defined round 2 at 234.1 s,
  and no battle followed in the next 220 s. So a long list is not established as the cause.
  **Done 2026-11-17 (95.12(a); the cause is still not shown).** After its clicks each round waits for the probe's `combat|START`
  (`COMBAT_START_TIMEOUT`, 45 s). If none comes it saves `<TESTID>.round<N>-no-start.png` beside the log (`Hands.capture`), clicks
  Continue again for a later round, and plays the mission once more. A second miss ends as LIVE_STUCK at `combat-round-<N>`, with
  "also after one retry" and the screenshot's path. After a battle, Continue now waits for the game's own re-definition of the mission
  (its combat-round line, 1.8 to 2.4 s after END in the 2026-11-17 runs) instead of clicking into the transition. Tests:
  `tests/test_live_run.py` `test_a_restart_that_starts_nothing_is_retried_once_after_a_screenshot`,
  `test_a_mission_that_never_starts_is_stuck_at_its_round_naming_the_retry`,
  `test_a_first_round_that_starts_nothing_is_retried_without_a_continue_click`,
  `test_continue_waits_for_the_game_to_define_the_mission_again` (each fails on the old loop). Screen-reading the list stays open if
  a screenshot shows the click itself misses. Next: re-run UAF and Bultach.
- 93.39 **The second of two combat rounds re-ran the first, so its hulls never fought.** Probe 0.2.13 advanced its round counter on
  every `defineMission`. The game calls that once when a battle ends as well as when the next one starts, so the counter rose twice
  per battle, and with two rounds every second battle was round 1 again. Every two-round live run on Test1 shows it:
  - G1-LIVE3 (Eridani Combine, Scrapyard Armories, Musashi Manufactorum): hulls 61-113 never fought; both battles logged 28 ships;
  - G2 and G2B (Bultach Coalition): hulls 61-105 never fought.
  Runs of one round are unaffected (Tania, KoC, the Sunrider group, Templars). Found 2026-11-17 from the order of the logs' round
  lines: round 1, END, round 2, round 1, START.
  **Done 2026-11-17 (probe 0.3.3).** `MissionDefinition` only reads the counter (`ProbeFiles.currentCombatRound`), and the battle's
  end advances it (`ProbeDone.combatEnded` → `ProbeFiles.advanceCombatRound`); the last-round check uses the round that ended.
  Rebuilt jar: 6 of 54 classes differ, the 3 edited ones and 3 that inline `ProbeLog.VERSION`. `probe-group report` now carries
  `combat_rounds` (`planned`, `started`, `missing`, `missing_hulls`: the round the game defined last before each START) and prints
  a WARN for a round that never started a battle. This is coverage, not a verdict. Tests: `tests/test_probe_group.py`
  `CombatRoundsTests` (G1-LIVE3's and SR3's shapes, 0.3.3's, the report field) and `tests/test_probe_config.py`
  `CombatRoundCounterTests` (source, release copy and both jars). Owner's call: re-run Eridani and Scrapyard (archived 2026-11-17 on
  "archive all") so their round-2 hulls fight, and re-run Bultach before it is recorded.
  An independent review the same day found two problems, fixed in the same PR:
  - `combat_rounds` raised `KeyError` for a round the game never defined (a run stuck or crashed in an earlier round). Such a
    round now shows `?` for its hulls. Test: `test_a_run_stopped_before_a_round_was_defined_names_no_hulls_for_it`.
  - A game that exited while a round loaded was retried, and the retry clicked into the closed window (`RuntimeError`). It now
    ends as LIVE_STUCK "the game exited before the probe mission's battle started", with no retry. Test:
    `test_a_game_that_exits_while_a_round_loads_is_stuck_without_a_retry` (fails on the first version).
  **Live-validated 2026-11-17 on Test1's 0.98.5a-RC7 rig.** In both runs below, the post-battle definition and the restart
  both defined round 2, and `report` showed no combat WARN:
  - G1R-LIVE-0985a-20261117 (Eridani, Musashi and Scrapyard; 113 hulls; JDK 25 direct): round 1 fought hulls 1-60
    (29 ships), round 2 fought hulls 61-113 (53 ships). FATAL 0, MOD-ERROR 0, all three PASS; recorded LIVE_VALIDATED in the
    workspaces. Eridani's and Scrapyard's 2026-11-17 archives predate this run. Owner 2026-11-17: keep them as they are ("No" to
    refreshing them with this run).
  - SR5-LIVE-0985a-20261117 (Bultach Coalition; 105 hulls; Fast Rendering + Prepatcher, 93.42): round 1 fought hulls 1-60
    (30 ships), round 2 fought hulls 61-105 (41 ships). PASS, with the owner's two accepted content-parity ids; recorded
    LIVE_VALIDATED. Archive refused (93.41, 93.44).
- 93.40 **A battle that starts and never ends leaves no evidence.** SR4-LIVE-0985a-20261117 (Bultach Coalition alone, probe
  0.3.3, the first run after 93.39):
  - round 1 was defined at 241.9 s; the probe logged `combat|START` at 244.6 s and battle music started at 245.8 s;
  - the log then stayed silent for six minutes: no ship logged, no END. The run ended LIVE_STUCK at `combat-round-1`.

  SR3 fought the same slice normally. A deployment dialog left open (the battle stays paused) and a frozen game look the same
  in the log.
  **Done 2026-11-17 (evidence only; the cause is not shown).** When no END comes, the harness now saves
  `<TESTID>.round<N>-no-end.png` beside the log and names it in the stuck detail. A game that exited mid-battle is named as
  such, with no screenshot. Tests: `tests/test_live_run.py` `test_a_battle_that_never_ends_leaves_a_screenshot`,
  `test_a_game_that_exits_mid_battle_is_named_and_not_photographed` (both fail on the old driver).
  Next: re-run Bultach and read the screenshot if it stops again. Check that Test1's desktop is idle before a run
  (GetLastInputInfo), since a person using it takes the clicks and key presses.
  The next Bultach run (SR5, with Fast Rendering) fought both rounds, so SR4's stall has not recurred and its cause is unknown.
- 93.41 (S) **A run under Prepatcher records as UNBOUND.**
  - SR5-LIVE-0985a-20261117 passed, but its evidence was REFUSED: "staged inputs drifted during the run: staged files of
    starsector_prepatcher changed since launch".
  - The Prepatcher agent writes `mods/StarsectorPrepatcher/logs/prepatcher.log` while the game runs, so the run manifest's
    staged-input check sees its own mod change. The live result reads UNBOUND and the archive gate refuses.
  - Fix: leave a mod's known runtime output out of the staged fileset (a per-mod ignore list, Prepatcher's `logs/` first),
    or move Prepatcher's log out of the mod folder if `prepatcher.properties` allows it.
  - Then re-record SR5; the run itself needs no repeat.
  **Done 2026-11-17 (code).** `run_manifest.RUNTIME_OUTPUT_DIRS` (`starsector_prepatcher`: `logs`) keeps a mod's own runtime
  output out of that mod's staged hash. Every other mod hashes exactly as before, so older manifests stay valid. SR5's
  manifest hashed the old log, so it cannot be re-recorded under this fix. Bultach needs one re-run once live testing
  resumes (93.44 first). Test: `tests/test_run_manifest.py` `test_a_mods_own_runtime_log_is_not_drift_but_its_payload_is`
  (fails on the old hash).
- 93.42 (M) **Fast Rendering and Prepatcher in every live test, built in.**
  - Owner 2026-11-17: "please copy, send and setup the following with each live test" (StarsectorPrepatcher 0.18.8,
    fast_rendering v1.0.2rc1).
  - Done by hand on Test1:
    - Prepatcher in the rig's `mods/`;
    - Fast Rendering rig-local in `_rig-0985a/fast_rendering/`, because the rig's `starsector-core` is a junction to the
      real install, which stays read-only;
    - `fast_rendering/fr.rig.vmparams`: FR's own file, with absolute agent and classpath paths, logs in the rig, the
      Prepatcher agent last and `ShowMessageBoxOnError` dropped;
    - `run-j25-frpp.bat`;
    - the local live wrappers default to it, and each install gets `--also-enable starsector_prepatcher`;
    - `bridgeforge-state/live-wrappers/setup_frpp.py` re-creates the setup.
  - Observed:
    - FR v1.0.2rc1 loads from the rig-local path (SR5's smoke reached the main menu in 21 s).
    - Prepatcher 0.18.8 refuses RC7 ("Unknown Starsector bytecode namespace; refusing guessed names") and the game runs
      unpatched. Its release notes list RC8, 0.98.5a-RC3 and RC5 only, so RC7 needs a Prepatcher release that knows its
      names.
  - To do in BridgeForge: `java-matrix setup --launcher fr` reads `fr.vmparams` and `fr.jar` from the install's core. It
    should accept a rig-local FR folder, and `probe-group smoke|live` should use the FR + Prepatcher launcher when the rig
    has one (with 95.4's direct start).
- 93.43 (S) **JDK 27 on the rig** (owner asked 2026-11-17 "Should we add java 27?"; recommended; waits while live testing
  is paused).
  - Prepatcher 0.18.8 supports "Java 17 or Java 27+", so the rig's JDK 25 is outside its range.
  - `fr.jar` is compiled for Java 17 (class major 61, no preview), so Fast Rendering runs on 27.
  - Add a rig-local Temurin 27 beside `_rig/jdk-25.0.4.1+1` and a `run-j27-frpp.bat` without `--enable-preview` (nothing needs
    it; 88.24's save crash came with it on a newer JDK).
  - Make one comparison run against JDK 25, then switch, keeping JDK 25 as the fallback.
  **Set up 2026-11-17; the comparison run waits on live testing.**
  - Owner 2026-11-17: "yes you can copy Java 27 from" the `jdk-27+22` folder of White_Legion's RC8 install. It was copied at
    22:32 UTC.
  - At 22:37-22:38 UTC that install's JDK folders changed: `jdk-27+22` was gone, replaced by `jdk-27.0.2+0` and `jdk-28+24`
    (`28-beta`, early access).
  - Owner, the same evening: replace the rig's copy with `jdk-27.0.2+0` ("yes since its newer"). Later the owner will add
    JDK 28 and the Mikohime setup, so both can be tested.

  On Test1:
  - `In operation\_rig\jdk-27.0.2+0`, beside JDK 25, is a copy of that folder: 415 files, each checked against a SHA-256
    manifest after the copy.
    - `java -version` reports `27.0.2-beta`, Temurin-27.0.2+0 (build `27.0.2-beta-ea`, a nightly of 2026-11-14). It is an
      early-access build, not a general release.
    - The first copy, `jdk-27+22` (`27-beta+22-ea`), was moved to `_rig-0985a\_addons\retired\`.
  - `_rig-0985a\fast_rendering\fr.rig.j27.vmparams` is `fr.rig.vmparams` without two flags:
    - `--enable-preview`;
    - `-XX:+UseVectorStubs`, which 27.0.2 refuses and 27+22 accepted. `java_matrix.flags_to_drop` found it.
  - `_rig-0985a\run-j27-frpp.bat` launches it.
    - The live wrappers still default to `run-j25-frpp.bat`; `BF_RIG_BAT=run-j27-frpp.bat` selects JDK 27.
    - `bridgeforge-state/live-wrappers/setup_j27.py [JDK folder]` re-creates both files.
  - BridgeForge's own tools still use JDK 25: `java_toolchain.find_jdk` takes the first `In operation\_rig\jdk-*` by name, and
    `jdk-25.0.4.1+1` sorts first.
- 93.44 (S) **Bultach's archive: an unexplained `star_gen_data.csv`.** `audit-shipped` lists
  `data/campaign/procgen/star_gen_data.csv` as added and UNEXPLAINED (not in the original). Find the step that added it (the
  RC7 revive's records, an escalation, or a hand edit) and explain it from that record. Then re-record SR5 (after 93.41) and
  archive on the owner's "archive all".
  **Done 2026-11-17 (tooling).** The record exists: Bultach's escalation ledger has
  `{"finding": "procgen-star-row-missing", "files": ["data/campaign/procgen/star_gen_data.csv"], "runner": "fixer", "outcome":
  "APPLIED"}`. The fixer added the `bt_divine_star` row that the mod's planets.json star and campaign code need. The
  shipped-copy audit read only a ledger entry's single `file`, never a fixer run's `files` list; KoC's moved work files had
  the same shape. `live_trust._recorded_changes` now reads both, explaining a fixer entry as
  "fixer <finding> (escalation ledger)", and it skips ledger lines that are not objects (the old code raised on them). Test:
  `tests/test_live_trust.py` `test_a_fixer_run_in_the_escalation_ledger_explains_the_files_it_lists` (fails on the old
  reader). Bultach's archive now waits only on its re-run (93.41).
- 93.45 (S) **A jar entry's name reached javap's JVM as an option.** Found 2026-11-17 while batching javap for 96.5 P1.
  - **Where:** `settings_keys.jar_reads` (the settings-key check) and `procgen_args.jar_suspects` (the procgen-argument check)
    gave javap each selected class as `entry[:-6].replace("/", ".")`.
  - **The problem:** javap's launcher reads an argument starting with `-J` as a JVM option, wherever it stands. So a mod's
    jar could put any JVM option on the command line, including ones that load an agent or run a command.
  - **Shown with a harmless option:** a jar whose entry `-J-version.class` holds the SettingsAPI marker made the JVM print its
    version instead of running javap (JDK 25). javap also reads `@file` as an argument file, `x.class` as a path and `a:b` as
    a URL.
  - **Reach:** a scan runs javap whenever `find_jdk` finds a JDK, which is always the case on both machines. Both call sites
    came with items 34.34-34.36 (2026-10-04), so the published v0.4.0 has the problem, and v0.2.0 does not.

  **Done 2026-11-17.** `zipsafe.javap_class_name` returns an entry's class name only when it is a plain binary name: ASCII
  letters, digits, `_` and `$`, separated by single dots, and not ending in `.class`. Both walks skip any other entry.
  Tests: `tests/test_untrusted_input.py` `JavapClassNameTests`:
  - the name rule, including U+FF0D, which reached javap as "?" on cp1252;
  - both walks give javap only `a.B` from a jar full of hostile names.

  Each test fails with its guard removed (mutation-checked).
- 93.46 (S) **A line break in a mod's jar path reached javac's argument file, and javac ran the mod's annotation
  processor.** Found 2026-11-17 by the independent security review of 93.45. Reproduced with the real
  `compile_check.compile_loose_scripts` on JDK 25.0.5.
  - **Where:** two pieces of code combined:
    - `java_toolchain._mod_jars` kept any mod_info.json `"jars"` entry whose joined path passed `is_file()`;
    - `run_javac` and `build.run_compile` wrote each argument quoted into a javac `@` file, escaping only `\` and `"`.
  - **The problem:** javac's argument-file reader ends a token at a line break, even inside quotes.
    - The entry `"x\n-proc:full\n-Afoo=/../jars/lib.jar"` passed `is_file()` on Windows, because the `..` cancels the
      line-break component.
    - It put `-proc:full` on the command line after the default `-proc:none`.
    - compile-check then ran an annotation processor from the mod's own jar: the test processor wrote its marker file, and
      compile-check reported PASS.
  - **Reach:** everything that assembles a mod's classpath:
    - compile-check, so also `scan --compile-check`, the portfolio worker, `corpus-recheck` and the revival report draft;
    - `patch-jar-class` and `rebuild-jar`;
    - a declared dependency's mod_info.json.
  - **Related:** on Linux a `.java` or jar file name may hold a line break itself. `build` and the probe's javac runner
    passed no `-proc:none`, so a JDK 17 or 21 javac would run a processor that a classpath jar declares (the probe's classpath
    holds MagicLib, the raid check's Nexerelin).

  **Done 2026-11-17.**
  - `java_toolchain.javac_argument_line` writes one argument-file line and refuses (ValueError) an argument with a line
    break. `run_javac` and `build.run_compile` use it before writing anything.
  - `_mod_jars` leaves out a declared or found jar whose path holds a control character.
  - `build-plan` writes `-proc:none` into the javac command. `run_compile` adds it to an older profile that names no `-proc:`
    option, and the probe's `_run_javac` passes it too.

  Tests: `tests/test_untrusted_input.py` `JavacArgumentFileTests`:
  - the line rule;
  - both writers refuse before starting javac;
  - `_mod_jars` leaves the entry out;
  - `build` turns processing off, also for an older profile, and so does the probe build;
  - the reviewer's case end to end, which ran the processor before the fix.

  Each guard's test fails with the guard removed (mutation-checked).
- 93.47 (S) **A mod's id reached cmd.exe and PowerShell.** Found 2026-11-17 by the security review of 93.45, which ran an
  injected command through each in a copy of the code; the flow was then confirmed in the source.
  - **Where:** `mass_test` named each boot's log `mass-<mod id>`, taken from the mod's mod_info.json. Through `java_matrix`
    and `boot_test` that name reached:
    - `launch.command_line`, which builds the raw `cmd.exe /c ""bat" > "log" 2> "err""` line. An id such as
      `x" & <command> & rem ` runs the command;
    - the window watcher's screenshot path, written into a PowerShell single-quoted string that doubled only `'`.
      PowerShell also ends such a string at U+2018-U+201B.
  - **Reach:** `mass-test` over archives in `Done/`. Every other launch passes a test id from the command line.

  **Done 2026-11-17.**
  - `mass_test.log_name_for` keeps only ASCII letters, digits, `.`, `_` and `-` of the id.
  - `launch.command_line` refuses a path holding `"`, `%`, `!` or a control character. These are what cmd.exe acts on inside
    the quotes.
  - `window_watch.save_screenshot` and `game_click.capture_client` give PowerShell the path in an environment variable
    (`BF_IMAGE_PATH`), never inside the script.

  Tests: `tests/test_command_line_names.py`:
  - the launch line refuses such paths;
  - `start_game` starts nothing;
  - a hostile id becomes a plain log name;
  - both screenshot scripts carry no path.

  All 5 fail on the old code.
- 93.48 (S) **`src-to-jar` could write a mod's bytes over any existing file.** A lead from the 93.45 security review,
  reproduced 2026-11-17.
  - **Where:** `src_to_jar.prove_authoritative` compares the jar's classes with those the original sources compile to. It
    wrote each shipped inner class to `<scratch>/shipped/<entry name>`, checking only that `<scratch>/ref/<entry name>`
    existed. Both paths climb out by the same number of `..`.
  - **With `/` separators,** javac refused the jar ("cannot access data.scripts": Java's zip reader rejects `..` parts), so
    the proof stopped before writing.
  - **Stored with backslashes** (`data/scripts/Spawner$\..\..\..\..\..\..\victim.class`), the entry is a plain file name to
    javac, which compiled. Python's zipfile on Windows reads `\` as `/`, so the write left the scratch folder and replaced
    an existing file with the entry's bytes. The proof reported no problem.
  - **Reach:** `src-to-jar` on a mod whose jar ships such an entry. Any existing file the user can write, at a guessable
    place relative to the temp folder, was in reach, such as BridgeForge's cached helper classes there, which it runs
    later.

  **Done 2026-11-17.**
  - `_class_entries` counts only entries with a plain binary class name (`zipsafe.javap_class_name`).
  - The write loop also refuses a path that resolves outside the scratch folder.

  Tests: `tests/test_src_to_jar.py`:
  - `test_a_jar_entry_cannot_write_outside_the_proofs_folder`: the backslash entry, end to end;
  - `test_the_proof_writes_nothing_outside_its_folder_even_past_the_name_filter`: the second guard alone;
  - `test_only_plain_class_entries_are_read_for_the_proof`.

  Each fails with its guard removed. The first failed on the old code with `b'hostile bytes' != b'untouched'`.
  The review's other leads, read 2026-11-17:
  - `research_decompile` already refuses `..` and `:` in entry names, and on Windows zipfile turns `\` into `/` before
    that check;
  - `corpus-index` checks 7-Zip members, and `corpus_releases` extracts them into memory;
  - `sibling-assets` refuses `..`, and its escape cases copy a file onto itself;
  - `delegate-method` takes its class names from the user's own spec.
- 93.49 (S/M) **A probe battle can stall, so its round never ends.** SR6-LIVE-0985a-20261117 (Bultach Coalition, probe 0.3.3,
  Fast Rendering + Prepatcher, JDK 25, the setup SR5 passed with) ended LIVE_STUCK at `combat-round-1`.
  - **Timeline:** round 1 started at 203.6 s. For about 100 s after that the log shows only repeated LunaLib settings errors
    (shaderLib's `enableFullExplosionEffects`), then nothing until the harness gave up.
  - **93.40's screenshot** (`SR6-LIVE-0985a-20261117.round1-no-end.png`) shows the game running, not frozen. The HUD says
    "NO ENEMY PRESENCE" and "SHUTTLE READY FOR COMMAND TRANSFER": the player's flagship is gone, and no enemy is near.
  - **Coverage:** `report` showed FATAL 0 and MOD-ERROR 0, with ORK PASS and the owner's two accepted ids, but round 2's hulls
    (61-105) never fought. The run was not recorded.
  - **Reading:** nothing in the probe mission ends a battle whose remaining ships never meet. This is likely what SR4 hit
    too (93.40). Which ships were left is not shown; the log does not name them.
  - **Proposal:** the probe's combat plugin ends a battle after a quiet spell (no hull damaged or destroyed for N seconds).
    It logs `combat|END` with the reason and the ships still alive per side, so the run goes on to the next round; `report`
    shows such a round as fought with a WARN. This needs probe 0.3.4 and a live run.
- 93.50 (S) **A vanished game window ends a live run with an exception.** SR7-LIVE-0985a-20261117 (Bultach again, after SR6)
  passed its smoke. Then, during New Game:
  - the game read the newest save (log line 30197 at 120.4 s: `Reading save data from [..\saves\save_HekaWillis_...]`,
    written by SR6);
  - the log then ends with the JVM's code-cache summary; there is no hs_err file, and `windows.txt` lists no dialog;
  - the harness raised `RuntimeError: the game window is gone` from `new_game`'s click, with no verdict.
  - **Two parts:**
    - The harness should end any stage whose window is gone as LIVE_STUCK, naming the stage and the log's last lines, as
      93.37 does for a battle.
    - Why a save was read during New Game is not shown. The rig's `saves/` held 14 saves from the day's runs, and
      `probe-group install` leaves them. Moving the rig's saves aside before each run would make every run start the same
      way.
- 93.58 (S) **The display goes dark mid-run.** Test1's power plan turns the display off after 180 s without input
  (`powercfg` VIDEOIDLE 0xb4, read 2026-11-19). The 96.2 runs P962KR and P962KR2 (Kadur Remnant) reached the campaign, then the
  harness's Escape and menu clicks never reached the game: LIVE_STUCK at the first combat round, the log silent after the
  probe's checks. P962KR3 passed with a background process holding the display on.
  **Done 2026-11-19.** `live_run` holds the display and system on for the whole run (`live/display_awake.py`,
  `SetThreadExecutionState` with ES_DISPLAY_REQUIRED, reset to the plan's timeouts afterwards; a no-op off Windows).
  This is the likely cause, not a proven one: Broken Star still stalled at the same step with the display held on
  (P962BS4), so that one has another cause, under 96.2. Tests: `tests/test_display_awake.py` (held inside and released
  after, also on error; nothing released when nothing was held; `live_run` holds it around the game; Windows accepts the
  request).
- 93.59 (S) **The harness leaves the campaign while the probe saves.** With `--save-after-checks` the probe calls `cmdSave()`
  right after its first `campaign END`, and the harness pressed Escape about a second after that line. From END to the probe's
  `save|campaign|cmdSave returned true`: P962KR3 (Kadur Remnant, passed) 2.3 s; P962BS4 (Broken Star) 27.8 s and P962YC2
  (YunruCore, display held on by 93.58) 20.3 s, both LIVE_STUCK at combat round 1 with the game still on the campaign map and
  the fleet moved by the Exit click (screenshot `P962YC2-...round1-no-start.png`). The keys and clicks sent during the save
  were lost. P962KR and P962KR2 (93.58) may have been the same.
  **Done 2026-11-19.** When the rig's probe config has `save_after_checks: true` (`live_run.probe_saves_after_checks`), `drive`
  waits up to 180 s for the probe's save line (INFO or FAIL), settles 3 s, then leaves the campaign; stage `probe-saved`. No
  line: LIVE_STUCK at `probe-save`, with nothing pressed. Tests: `tests/test_live_run.py` (a fake game that loses input during
  the save: the run waits and loses nothing; without the wait the Escape is lost; a save that never reports is stuck at
  probe-save; the config flag read strictly). Without the wait two tests fail (mutation-checked). Live confirmation: the
  YunruCore and Broken Star re-runs on Test1 (96.2).
  Confirmed live 2026-11-19: P962VY (Vayra's Sector, YunruCore), P962BS5/BS6 (Broken Star) and P962NC (Neutrino) all
  reached `probe-saved` before `combat-1` and ended LIVE_DONE.
- 93.60 (S) **GraphicsLib's cache read as drift.** P962NC-LIVE-0985a-20261119 (Neutrino Corporation, PASS) was refused at
  record: "staged files of shaderLib changed since launch". GraphicsLib 1.12.1 writes generated normal maps into its own
  `cache/` while the game runs: 182 files, all under `cache/`, dated during the run. The same class as Prepatcher's
  `logs/` (93.41).
  **Done 2026-11-19.** `run_manifest.RUNTIME_OUTPUT_DIRS` gains `"shaderLib": ("cache",)`, so `cache/` stays out of
  GraphicsLib's staged hash. Any other change to GraphicsLib is still drift. Tests: `tests/test_run_manifest.py`: a cache
  file written during the run is not drift, a changed shader is. Without the entry the test fails (mutation-checked). Live
  confirmation: the Neutrino re-run on Test1 (96.2).
- 93.51 (S) **Two lower-risk leads from the 93.45 security review,** read 2026-11-17, not yet fixed:
  - BridgeForge's helper classes are cached in the temp folder and reused without a check (`bytecode.py`, `java_ast.py`,
    `delegate_method.py`). On a shared POSIX `/tmp` another local user could plant one. Windows' temp folder is per user.
  - `decompiler-review --execute` with a `.bat` adapter: Python quotes an argument only when it holds a space, so an input
    path without spaces reaches cmd.exe unquoted, and an `&` in it would act. The owner's paths all hold spaces.

  **Done 2026-11-19.**
  - `bridgeforge/bytecode/helper_cache.py` gives the four compiled helpers (AST, bytecode, bytecode rewrite, delegate
    method) one private folder per user, `<temp>/bridgeforge-helpers-<uid or user>/<kind>/<digest>`. On POSIX it is
    created with mode 0700 and refused when it is a link, another user's, or open to others; Windows' temp folder is
    already per user. The helpers recompile once into the new folder. An unsafe folder raises the caller's own
    `AstUnavailable`/`BytecodeUnavailable`, so a scan degrades as it does without a JDK instead of ending.
  - `decompiler-review --execute` with a `.bat` or `.cmd` adapter (a trailing dot or space included, which Windows strips)
    refuses any argument, the adapter's own path included, holding `& | < > ^ " % !` or a control character, before
    anything runs. An `.exe` adapter is not run through cmd.exe and is unchanged.
  Tests: `tests/test_security_93_51.py` (the per-user root, 0700 on POSIX; another user's, an open and a linked folder
  refused, faked so they run on Windows too, plus a real symlink and a real 0755 folder on POSIX; every helper uses it;
  an unsafe folder is the caller's unavailable error; every metacharacter refused in any argument without running;
  a plain path and an `.exe` adapter still run). Removing either check fails its tests. An independent security review
  found both holes closed; its points (the scan-ending error, the message, the trailing dot, more tests) are taken.
- 93.61 (S) **`descriptions draft` crashed on a CSV row with extra cells.** Station Augments' 96.2 port (owner 2026-11-19:
  "Accept 1-3, draft descriptions") stopped with `AttributeError: 'list' object has no attribute 'strip'` in
  `sibling_assets._read_rows`: a sibling mod's descriptions.csv had a row with more cells than its header, which
  `csv.DictReader` puts in a list under the None key.
  **Done 2026-11-19.** `_read_rows` keeps only named columns and reads a missing cell as blank. Cells past the header are
  not part of the row the game reads, the rule `gene.py` already follows for CSV members. Tests:
  `tests/test_descriptions_draft.py` (a row with extra cells and a short row are read, trimmed). Without the fix the test
  errors as above.
- 93.52 (S) **save-doctor reported equal versions as changed.** Found testing Salvor's provider on real saves (owner
  2026-11-17: "improve/test Salvor" between CI waits). `save_doctor.installed_mods`, the provider contract Salvor imports,
  stored mod_info's `{"major", "minor", "patch"}` version as its Python repr. A save made with 1.20.0 then read as
  VERSION_CHANGED against the same 1.20.0.
  - 16 of 61 VERSION_CHANGED on one of the owner's RC8 saves were this.
  - 32 of 43 on the 16 saves Test1's 0.98.5a rig wrote on 2026-11-17 were this. The other 11 are real: probe 0.3.2 saves
    against the installed 0.3.3.

  **Done 2026-11-17.** The version goes through `corpus_releases.version_text`.
  - With it, the rig saves' diagnosis matches the runs that wrote them:
    - each save's enabled mods match its run's manifest;
    - no false MOD_MISSING or CLASS_UNRESOLVED;
    - the 0.98.5a-RC7 game version is read.
  - The owner's seven RC8 saves were read in place and not changed.

  Test: `tests/test_save_doctor.py` (an object version against the dotted one, and a real change still reported);
  mutation-checked.
- 93.53 (S) **save-doctor called three loadable saves WILL_LIKELY_FAIL.** Three of the owner's seven RC8 saves (Warren
  Koyamatsu) had six CLASS_UNRESOLVED packages each with no mod missing.
  - **Aliases:** the names are XStream aliases. Star Lords' `LordsModPlugin.configureXStream` registers
    `faction.LawProposal`, `ai.LordAI` and more for its `starlords.*` classes, and the game writes the alias into the
    save. The class index knew only jar entry names.
  - **Loose scripts:** in two more saves, Emergent Threats' loose `.java` scripts (`data/scripts/vice/listeners`) read as
    unresolved, because loose scripts the game compiles at load were not indexed.

  **Done 2026-11-17.** `save_compat.ModClassIndex` now indexes two more kinds of name:
  - the aliases a mod's `modPlugin` class declares when it overrides `configureXStream`: its string literals shaped like
    dotted class names, read with a bounded read of that one class. A plugin that registers them in a helper class is
    not seen.
  - each loose `.java` script's class, by its package line, for mods and the core alike.

  Result: the Warren Koyamatsu saves read NO_KNOWN_PROBLEM. The two saves still WILL_LIKELY_FAIL list mods that really are
  missing (`Starlight1130`, `QualityCaptains`, `Red_stripe`), and their remaining unresolved packages belong to no
  installed mod.

  - The rule that skips the game's own aliases (`WSR.V`) skipped every name starting with a capital. That also hid a
    mod package that starts with one (`Jaydee8652.JaydeePiracy`). Only an all-capitals first part is skipped now; found
    porting the rule to Salvor's version-check.

  Tests: `tests/test_save_doctor.py`:
  - a plugin compiled with javac whose aliases, and their package, resolve;
  - a mod whose loose script's class resolves;
  - a capital-led package that is reported while `WSR.V` is not.

  Each fails with its guard removed (mutation-checked).
- 93.54 (S) **The main menu reader counted two buttons twice at 1920x1080.** Found by Salvor's rig step R2 on Test1
  (0.98.5a-RC7, fullscreen 1920x1080): the automatic Continue click opened the Missions screen. `screen_read.main_menu_buttons`
  samples four columns and keeps the one with the most button rows. At x 0.70 the text of New Game and Load Game breaks
  their fill into two short bands each, so that column read 11 rows and won. The names are counted from the bottom, so
  Continue resolved to Missions. Columns 0.66 and 0.68 read all nine rows.
  **Done 2026-11-17.** A band shorter than 0.8 of its column's tallest band is a cut button and no longer counts, unless it
  touches an end of the scanned rows (clipped there, not cut). The run's screenshot now reads nine rows, with Continue at
  y 372 and Missions at y 452, which matches the screen. Test: `tests/test_screen_read.py`
  `test_a_column_where_text_cuts_buttons_in_two_is_not_chosen` (fails without the fix: 11 rows).
- 93.55 (S) **save-doctor passed a save holding a faction no enabled mod defines.** Salvor's RC7 rig run on Test1
  (2026-11-17), once 93.54 let the Continue click land: the candidate was a Templars save with Templars removed (Salvor
  dropped `TemCrusadeManager` and the mod entry; static checks said NO_KNOWN_PROBLEM). The game stopped loading in
  `com.fs.starfarer.campaign.Faction.readResolve()` with `this.spec` null, at the `templars` Faction (campaign.xml line
  2485; 94 Templars references, the Antioch system among them).
  Evidence (RC7 `starfarer_obf.jar`, javap): `spec` is transient and looked up by `id` in `readResolve`, and
  `readResolve` always calls `updateDoctrineAndKnown`, whose `isPlayerFaction()` calls `spec.getId()` with no null check.
  So any Faction element with no spec stops the load.
  **Done 2026-11-17.** `save_doctor.diagnose` reports FACTION_UNDEFINED (blocking) for each Faction id that no `.faction`
  file defines, in the core or an enabled installed mod, subfolders included (Roider Union keeps
  `roider_mining/roider_dust.faction`). A Faction element is an element with an `id` leaf beside a
  `secondaryColorSegmentsOverride` leaf: a byte search of every RC7 core jar found that field name only in `Faction`.
  The check needs the core; without it the result lists the check as skipped.
  Results:
  - Salvor's candidate: `templars` only, in 0.8 s for 11 MB.
  - The owner's seven RC8 saves (read-only, RC8 core and mods): two read NO_KNOWN_PROBLEM as before.
    - The three Warren Koyamatsu saves name `eidolon`. Wide Horizons Content defines it, and those saves no longer
      enable that mod. By the bytecode above they would not load with today's mod set; no run has shown that either way.
    - The two saves that already list missing mods also name `Azure_Federation`, `cinis_of_crusaders`, `red_stripe` and
      `red_stripe_vower`.
  Tests: `tests/test_save_doctor.py`:
  - an undefined faction is reported, while a core faction and an enabled mod's faction one folder down are not, and
    neither are nested `id` leaves;
  - with no core, the check is skipped and the result says so;
  - an installed but disabled mod's faction is undefined.
- 93.56 (S) **save-doctor passed a save whose vanilla factions still list a removed mod's content.** Salvor's R4 run
  7890f07c on Test1 (2026-11-18), the first with a removal that adds no faction: LeonardCallisto's save without Scrapyard
  Armories, repaired to NO_KNOWN_PROBLEM with 0 objects removed. The launch was observed; the load stopped at "Fatal: Ship
  hull spec [sa_manticore_remnant] not found!". The candidate still names Scrapyard hulls, weapons and wings in vanilla
  factions' `knownShips`, `shipsWhenImporting`, `knownWeapons`, `knownFighters` and `priorityShips`: id strings inside
  `Faction` objects, put there by the mod's `default_ship_roles.json` and faction merges, not objects of the mod.
  Evidence (RC7 `starfarer_obf.jar`, javap): `readResolve` calls `updateDoctrineAndKnown(for.new() && !isPlayerFaction())`;
  it clears and rebuilds those lists from the faction spec only when the argument is true, so in play the saved ids stay
  (RC8_BEHAVIOUR RC8-43).
  **Done 2026-11-18.** `save_doctor.diagnose` reports FACTION_LIST_UNDEFINED (blocking), per faction and list, for the ids
  in a Faction's content lists (`FACTION_LISTS`: the ship, weapon, fighter and hull mod lists, known and priority) that
  neither the core nor an enabled mod defines. `substitutes.data_ids` (factored out of `provider_for`) reads the ids from a
  `data/` folder: the CSV rows and the .ship/.skin/.wpn specs. `knownIndustries` and the weighted `e` map entries are not
  checked: the run did not show how the game resolves them. Needs the core, like FACTION_UNDEFINED.
  Results on Test1: the failed candidate reports 50 lists in 14 factions, 65 distinct ids, every one Scrapyard's `sa_`; the
  original save, Scrapyard present, stays NO_KNOWN_PROBLEM (no false positive across the other mods' lists).
  Tests: `tests/test_save_doctor.py` (each list kind, a skin's hull id and a mod's hull defined, `knownIndustries` and a
  non-faction element ignored, the check skipped without a core). Collecting nothing, or collecting outside a Faction, fails
  it (mutation-checked). Next: Salvor's `repair` drops those ids from the lists, and the candidate is run again.
- 93.57 (S) **A MagicLib bounty line went to the group, not its mod.** YunruCore's 96.2 live run (P962YC-LIVE-0985a-20261119)
  read UNCLEAR: its eight bounty lines (`bounty|yunrucore/<id>|MagicLib has no bounty data for this id (not loaded)`) were
  attributed to no member, because `group_report` matches a line's subject against content ids and a bounty names
  `<mod id>/<bounty id>`. Each of the eight lists `required_mods_id` naming sibling Yunru mods the solo run did not enable,
  so MagicLib was right not to load them, but the mod's own `probe_accepted.json` could not apply to a group line.
  **Done 2026-11-19.** A bounty line whose subject starts with a member's mod id belongs to that member, so it fails that
  member or is cleared by its acceptance. Tests: `tests/test_probe_group.py`
  (`test_a_bounty_line_belongs_to_the_mod_it_names_and_its_acceptance_applies`; fails without the change).
- 93.38 **A group record describes another run's save.** `record_group` takes `save_made_with` from the rig's newest save
  (`_newest_save_made_with`, by modification time), so G3-LIVE-0985a-20261117 (Everybody loves KoC), recorded after group 4's live
  run, lists `navarchy_of_tania` and not KoC among its save's mods. Take the save the run's own log names, or none, and correct
  G3's record on the owner's word.
  **Done 2026-11-17 (code; G3's record not yet corrected, owner's call).** `probe_group.run_save_made_with` reads the last folder
  the run's log says the game saved to (`CampaignGameManager - Saving to ..\saves/save_X...`, from G3's own log), only a plain
  `save_*` name inside the rig's `saves/`, and None when the run saved nothing. Test: `tests/test_probe_group.py`
  `test_record_describes_the_save_its_own_log_wrote` (another run's newer save present; no save; a name escaping `saves/`).

**92. Less hand work found reviving six mods against 0.98.5a-RC7 (owner 2026-11-16: "add these improvements to roadmap we will implement in queue after these mods are revived but not yet live tested").**
**Approved, queued: start once Scrapyard Armories, Bultach Coalition, Eridani Combine, Everybody loves KoC, Musashi
Manufactorum and Navarchy of Tania are revived (UNATTENDED_DONE), before their live tests.** Found 2026-11-16 by running
`intake` + `revive --vanilla-core <Starsector985a core>` on those six (findings 107/128/24/46/63/119). Ordered by hand work saved.
- 92.1 **Done 2026-11-16.** **`description-missing` cascades from an undecodable descriptions.csv.** `scan/scan_references.py`
  `_scan_description_missing` reads vanilla's file leniently (`_read_csv_rows_lenient`) but the mod's own with `_read_csv_rows`,
  so one cp1252 byte (0x92, line 57) made ~34 Scrapyard hulls with rows read as undescribed; after the approved
  `data-file-not-utf8` fix only `emp_station` (genuinely blank) remained. Musashi shows the same pair. Read the mod's file
  leniently too, or suppress `description-missing` on that file while `data-file-not-utf8`/`csv-encoding-unverified` is open.
  Test: a cp1252 descriptions.csv with a described hull yields no `description-missing`.
  Built: the mod's descriptions.csv is read leniently like vanilla's (`scan_references.py`). Tests: `tests/test_false_positives_92.py`.
- 92.2 **Done 2026-11-16.** **Fixer for return-type-only jar linkage when source ships.** Navarchy of Tania: 3 `jar-linkage-unresolved` classes
  (`tania_mustafar_system`, `tania_requiem_system`, `tania_random_mode_fodder`) all call
  `StarSystemGenerator.addStableLocations(StarSystemAPI, int)`, `V` before, `List` in 0.98.5a. The packet itself says recompiling
  relinks with no source change, and the mod ships `src/`. When every unresolved member differs only in return type and a
  matching source exists, recompile (`jar-packets` + `patch-jar-class`) as a gated fixer instead of a code-tier packet.
  Built: subsumed by 92.25: `src-to-jar --relink path/Class` rebuilds return-type-only classes from shipped source after the same proof (Tania's three systems).
- 92.3 **Done 2026-11-16.** **One packet per hullmod for jar + src duplicates.** Bultach Coalition: 6 hullmods flagged `hullmod-instance-state` twice,
  once as `jars/ORKS.jar!…class` and once as `src/….java` (33 agent packets). Merge into one packet ("fix the source, rebuild the
  jar class") so the two copies cannot be fixed differently.
  Built: `revive.build_packets` drops a jar-class finding when the same finding is raised on that class's shipped source; `jar-source-not-rebuilt` then holds the mod until `src-to-jar` runs. Tests: `tests/test_small_fixes_92.py`.
- 92.4 **Done 2026-11-16.** **`intake --strip-junk`.** 2 of 6 intakes (Scrapyard: 4 `*.png~`; Tania: 2 `*.png~` + `desktop.ini`) were blocked by
  `archive-junk-member` and needed a hand-rebuilt `-clean.zip`. Drop exactly the members that finding names into a derived zip,
  keep the raw zip, record the dropped list in `intake.json`.
  Built: `intake --strip-junk` writes `<name>-clean.zip` without exactly the members `archive-junk-member` names (only when those are the sole blocking hazards; never over an existing file), keeps the raw archive, records `raw_archive`, its sha256 and `stripped_members` in intake.json; the blocked message now names the hazards and suggests the flag. Tests: `tests/test_intake_strip_junk.py`.
- 92.5 **Done 2026-11-16.** **Batch intake by mod-folder name.** `intake` takes one archive; six mods meant six calls, each needing the exact folder name
  ("koch" was `Everybody loves KoC-1.05.49a`, "eridiani" `Eridani Combine-1.0.3.6`). Accept several sources and
  `--from-mods DIR NAME...` with fuzzy matching that shows the match and refuses ambiguity.
  Built: `intake` takes several sources; `--from-mods DIR` resolves loose names by word similarity (`intake.resolve_mod_folder`: all six batch names resolve on the real mods folder, MagicLib x2 and 'navarchy' alone are refused as ties); one failing source does not stop the rest. Tests: `tests/test_intake_strip_junk.py`.
- 92.6 **Done 2026-11-16.** **Dry-run diffs for owner approvals.** `revive` lists owner packets but not what each approval would write; the Scrapyard
  `variant-op-over-budget` trim (dropped `heavyarmor` and all 13 flux capacitors, 98 -> 72 OP) was only visible by diffing
  afterwards. Show the per-file diff each approvable fixer would apply, and give `variant-op-over-budget` a trim strategy
  (capacitors/vents first vs hullmods first).
  Built: correction, each owner packet's markdown already carried the ready fixer's diff (`render_packet`, a ```diff block the session's summaries had stripped); REVIVE.md now points to it with the changed-file count. Trim strategy not added: 92.17 leaves only regression trims. Tests: `tests/test_small_fixes_92.py`.
- 92.7 **Done 2026-11-16.** **Approve fixer families across the queue at once.** The same auto-tier owner packets recur across the five queued mods
  (`variant-op-over-budget`, `variant-wings-exceed-bays`, `variant-weapon-slot-mismatch`, `shippable-work-file`,
  `data-file-not-utf8`, `procgen-star-row-missing`). One command to approve chosen families for chosen workspaces, previewing 92.6's
  diffs, then revive each.
  Built: correction, already present: `escalation rule <finding> <queue> --approve-fixer` records a standing approval in AUTOMATION_POLICY.json and `revive-queue` applies it. Nothing new built.
- 92.8 **Done 2026-11-16.** **`escalation run --agent` discovery.** No `claude` on PATH on this machine (sessions run in the VS Code extension); the
  first `--all` run failed with only the shell's error. Fall back to the extension's `resources/native-binary/claude.exe`, or fail
  before starting with what is missing. Also: `--watch-dir` reported the parent session's own memory writes as the agent's
  (same folder, concurrent); attribute by process or warn that concurrent writers are included.
  Built: correction, BridgeForge already resolves a `claude` missing from PATH to the extension's bundled binary (`escalation.resolve_agent_command`, P15 20.13); the first run failed because the session prefixed its own `which claude &&`. `escalation run --agent` now defaults to `claude -p --permission-mode acceptEdits`. The --watch-dir attribution part is open. Tests: `tests/test_small_fixes_92.py`.
- 92.9 **Done 2026-11-16.** **Local target set-up and target-aware wording.** `target show` is empty here and CLAUDE.md names
  `C:\Games\Starsector-0.98.5a-RC3`, absent on this machine; the installed 0.98.5 core is
  `C:\Program Files (x86)\Fractal Softworks\Starsector985a` (`starfarer_obf.jar`: 0.98.5a-RC7), so `@target` does not resolve.
  `target set` it (RC7 > RC3) and update CLAUDE.md; have `revive` warn when `--vanilla-core`'s build differs from the registry's.
  Packet text still says "RC8" when the target is RC7; name the build from the target.
  Built (part): `target show` prints `target_core_reports`, the build read from the core, and a warning when it differs from the registry (no local path printed). Open: finding texts that say "RC8" for reference behaviour. Tests: `tests/test_revive_target_92.py`.
- 92.10 **Done 2026-11-16.** **Readme files in the mod root are information only.** Scrapyard's `Changelog.json` and `Special Thanks.json` (prose, never
  loaded by the game) became UNKNOWN `unverified-json-syntax` agent packets; the agent could only wrap the prose in JSON arrays
  (its note: renaming to `.txt` would be natural but was outside the allowed files). Classify root files other than
  `mod_info.json` as information, or let the packet allow a rename.
  Built: `scan_mod` ends with `_demote_root_readme_json`: any JSON-syntax finding on a mod-root file (not mod_info.json) that no .java/.jar/.json/.csv/.kt in the mod names becomes SAFE with evidence `root-file-unreferenced`, so revive treats it as a note. Real data: Scrapyard's Changelog.json and Special Thanks.json -> SAFE. Tests: `tests/test_false_positives_92.py` (a root file the mod's code loads keeps its classification).
- 92.11 **Done 2026-11-16.** **Say what still blocks UNATTENDED_DONE.** After every fix Scrapyard's only remaining packet was one cosmetic
  `description-missing` (`emp_station`), which alone holds back the `gameVersion` bump and the live probe; the output did not say
  so. Print the remaining blockers and the one action that clears each (draft text, `baseline-accept`).
  Built: REVIVE.md gains `## Blocking UNATTENDED_DONE (N)` with one action per packet (`revive.next_action`). Tests: `tests/test_small_fixes_92.py`.
- 92.12 **Done 2026-11-16.** **`psutil` imported at module load.** `case_qualification.py` (and `portfolio*.py`) import `psutil` at top level, so with
  system Python (no psutil) even `bridgeforge intake --help` dies in `register_all`. Import it lazily in the functions that need
  it, or have `cli.main` name the `.venv` when a dependency is missing.
  Built: `cli.main` names the missing module and the fix (`.venv` or `pip install -e .`) instead of a traceback; psutil stays a declared dependency. Tests: `tests/test_small_fixes_92.py`.
- 92.13 **Done 2026-11-16.** **`revive` scans with `0.98.x`, so `gameVersion` is never bumped (highest priority of 92).** `revive --vanilla-core
  <985a>` resolves its target to `0.98.5a-RC7` (REVIVE.json `target`) but its scans record `target.starsector: "0.98.x"`
  (`reports/scan-*-revive/bridgeforge.compat.json`). `scan/scan_libraries.py` `_scan_mod_info_game_version` returns early when
  the declared series equals the generic target's, so Scrapyard's `"gameVersion": "0.98"` reached UNATTENDED_DONE unchanged,
  although that check's own text says the launcher unchecks a mod whose base version differs (`0.98` vs `0.98.5a`). Fixed by hand
  with `fix --finding mod-info-game-version-inexact --target-game-version 0.98.5a-RC7 --apply`. Pass revive's resolved target into
  every scan it runs; test: a `"0.98"` mod revived against an 0.98.5a core gets `mod-info-game-version-inexact` and the bump.
  Built: every revive scan uses `TargetProfile(starsector=<resolved target>)` (`revive._target_profile`). Tests: `tests/test_revive_target_92.py`.
- 92.14 **Done 2026-11-16.** **`fix` rescan ignores `--target-game-version`.** The same fix reported "Finding 'mod-info-game-version-inexact' STILL
  PRESENT after rescan" although `mod_info.json` then read `0.98.5a-RC7`: the verifying rescan does not use the option the fix
  was given. Rescan with the fix's own target options.
  Built: `fix` rescans with its `--target-game-version` and `--vanilla-core`. Tests: `tests/test_fixers_92.py`.
- 92.15 **Done 2026-11-16.** **Crafted descriptions must be grounded in the spec.** `descriptions draft` crafted for Scrapyard's `emp_station` "a
  short-range electromagnetic pulse ... shields, weapons, and engines disrupted ... draws on flux reserves"; the `.system` is
  `"type":"EMP"` (vanilla's arc emitter), range 800, 700 EMP + 300 energy per arc, used only by the station `sa_tesla_spike`.
  Rewritten by hand from vanilla's `emp` SHIP_SYSTEM row. Put the spec's key fields, the user hulls/tags (e.g. `HIDE_IN_CODEX`
  station) and vanilla's row for the same system/weapon `type` into the crafting prompt; flag claims about mechanics absent from
  the spec.
  Built: see 92.30.
- 92.16 **Done 2026-11-16.** **Credits text names the old target.** `descriptions.py` `_credits` writes "Revival for Starsector 0.98a-RC8" into
  `BRIDGEFORGE_CREDITS.txt` regardless of target (Scrapyard, revived for 0.98.5a-RC7). Use the workspace's revive target (ties in
  with 92.9).
  Built: `_credits` writes the revived mod_info gameVersion. Tests: `tests/test_small_fixes_92.py`.
- 92.17 **Done 2026-11-16.** **`revive --approve variant-op-over-budget` bypasses the owner ruling without `--reference-core` (high priority).**
  RC8-06 / owner ruling 2026-09-27 option 2: trim only what the new game's costs pushed over; variants authored over budget stay.
  `fixers/variants.py` applies that filter only `if reference`, and `revive` passes no reference core unless given one, so the
  first batch run trimmed everything over budget: Navarchy of Tania's boss `tania_redemption_Holy` lost 43 of 49 vents, Scrapyard's
  `sa_trocar_rammer` lost `heavyarmor` and 13 caps, 0-OP armour plates lost their vents (50 variant files over five mods).
  Reverted from `original/` and re-run with `--reference-core <RC8 core>`. Resolve the reference core from the mod's declared
  `gameVersion` (all six declare 0.98a/RC8; RC8 is the registry's previous build) and refuse to apply this fixer when none
  resolves. Test: an over-budget variant that is over budget on the reference core too is left alone by `revive`.
  Built: `game_version.reference_core_for` / `revive._resolve_reference_core` find the installed core whose own version has the original mod_info's base version among the installs beside the target core; `revive` passes it to fixers, records it in REVIVE.json, and refuses `variant-op-over-budget` without one (the standalone `fix` path is unchanged). Tests: `tests/test_revive_target_92.py`.
- 92.18 **Done 2026-11-16.** **`shippable-work-file` creates its own `fixer-backup-orphaned`.** Musashi: the fixer moved `graphics/mm/ships/isetsu/debug.log`
  to `scratch/work-files/` (by design) and left `debug.log.pre-bf-fix-shippable-work-file.bak` (0 bytes) beside the now-absent
  file; the next scan raised `fixer-backup-orphaned` (inspect, "archive refuses until resolved"). A fixer that removes a file on
  purpose should not leave a backup in `working/` (scratch holds the copy), or the check should skip backups whose fixer removes.
  Built: root cause was an empty file: Musashi's `isetsu/debug.log` was 0 bytes, got no scratch copy, and the removal fell back to a 0-byte .bak; `apply_fix` keeps no backup of an empty removed file. Tests: `tests/test_fixers_92.py`.
- 92.19 **Done 2026-11-16.** **`data-file-not-utf8` refuses unambiguous cp1252.** Musashi `data/strings/descriptions.csv`: the only high bytes are
  0xA0 (NBSP), 0xAB/0xBB (« »), 8 lines, none valid multi-byte UTF-8, yet the fixer wants `fix --encoding FILE=ENC` by hand
  because they are not "CP-1252 punctuation". When no line is valid multi-byte UTF-8 and every bad byte maps to a printable
  cp1252/Latin-1 character, apply cp1252.
  Built: 0xAB/0xBB count as CP-1252 typography when they appear in matched pairs (an unpaired one is still refused: Shift-JIS/Mac Roman). Tests: `tests/test_fixers_92.py`.
- 92.20 **Audit archived OP trims against the ruling (after 92.17; needs the machine with the full `Done/`).** On this machine
  `Done/` holds six empty `original/` stubs (checked 2026-11-16), so nothing could be checked here. Archives trimmed via
  `fix --reference-core` followed the ruling; ones trimmed by `revive` without a reference core may not have (92.17). A read-only
  sweep: for every archive whose records show a `variant-op-over-budget` fix, rescan each trimmed variant's `original/` copy
  against the mod's reference core (from its declared `gameVersion`) and classify REGRESSION (fits on the reference, over on the
  target: trim stays) or AUTHORED (over on the reference too: the trim broke the ruling). Then, per mod with AUTHORED trims:
  restore those variant files from `original/`, `revise prepare`/`finalize` as `+bf.N`, `mod-changelog add`, and
  `archive --refresh` (old archive to `Done/_replaced-<date>/`). Batch the live checks into one probe session per group.
  Done when the sweep lists every archive as CLEAN/RESTORED with its counts.
- 92.21 **Done 2026-11-16.** **92.13 also inverts once the version is right.** After `fix --target-game-version 0.98.5a-RC7` set the correct value,
  the next `revive` scan (generic `0.98.x`, normalised to `0.98a`) raised `mod-info-game-version-inexact` on all six mods
  ("declared 0.98.5a-RC7 ... target 0.98a"), while the fixer, given revive's real target, refused ("already '0.98.5a-RC7'").
  Worked around with `escalation accept ... --reason "... 92.13"` per mod; drop those acceptances when 92.13 lands.
  Also confirmed `revive --reference-core` is used only for substitution proposals (`revive.py:278`), never passed to fixers.
  Built: covered by 92.13 (a correctly bumped mod is not flagged). Tests: `tests/test_revive_target_92.py`.
- 92.22 **Done 2026-11-16.** **`baseline-accept-finding` scans without the vanilla core.** `baseline_accept_finding.py:107` calls
  `scan_mod(working)` with no `vanilla_core`, so findings that need vanilla data (`variant-op-over-budget` priced with vanilla
  weapons/hull mods) do not exist for it: "no finding matches" on 4 of 5 mods, while Bultach (own-weapon variants) matched 3 of 15.
  `escalation accept` on the packet worked. Take `--vanilla-core` (default `@target`) or reuse the latest stored revive scan.
  Built: `baseline-accept-finding --vanilla-core` (works with @target). Tests: `tests/test_small_fixes_92.py`.
- 92.23 **Done 2026-11-16.** **Revive reference scan as a report, every run.** The decisive evidence for the OP question (per mod: over on RC8 vs over on
  0.98.5a, regressions = the difference; this batch 1/22/15/3/1 authored, 0 regressions) took an ad-hoc script over
  `_scan_variant_validity`. Have `revive` write that comparison for each value-type finding (OP, wings, slots) when a reference core
  is known, and use it for 92.17.
  Built: REVIVE.json `reference_comparison` (variant-op-over-budget on the reference vs the target, regressions = the difference), shown in REVIVE.md. Real data: Tania 22/22/0, auto-resolved RC8 reference. Tests: `tests/test_revive_target_92.py`.
- 92.24 **Done 2026-11-16.** **Detect empty workspace skeletons.** On this machine `Done/` (6 mods) and the older `In operation/` projects (Scy-Nation,
  Hiigaran-Descendants, ...) are directory trees with zero files, all created 2026-11-02 11:51-12:01 (a copy that carried folders
  but no files); nothing reported it. `board`/`hygiene`/`done-audit` should flag a workspace or archive with no files (and a
  `working/` without `mod_info.json`) as BROKEN, not unknown.
  Built: `board` stage `EMPTY_SKELETON` for a folder tree with no files (real repo: 12 In operation projects and the Done/ stubs). Tests: `tests/test_board_92.py`.
- 92.25 **Done 2026-11-16.** **CRITICAL: agent fixes to `src/` never reach the jar the game loads.** `escalation run --apply` edits `src/**/*.java` and
  verifies by rescanning the source; nothing rebuilds the jar. Navarchy of Tania: 8 applied agent fixes (hull-mod state, hard-coded
  entity/system references, orbit guard) were inert in `jars/tania.jar`; the scan still flagged the jar copy
  (`jars/tania.jar!data/hullmods/tania_Cautious_Personality.class`). Eridani: 1 (`ECE_StarSystem`). Done by hand 2026-11-16 with a
  scratch `src_to_jar.py`: (1) changed sources = `working/src` vs `original/.../src`, plus relink-only classes; (2) prove `src/`
  is authoritative: each ORIGINAL source compiled against the reference core at the jar class's own release (Tania 61/Java 17,
  Eridani 52/Java 8) gives bytecode identical to the jar's (javap -c -p, constant-pool indexes stripped), else refuse (it refused
  Eridani until the release matched, and refused a class already patched until given the pre-patch jar); (3) compile the fixed
  sources against the target; (4) back up the jar to `scratch/jar-patch-<date>/`, `jar uf` all produced classes (inner classes
  too), check entries. Productize as `bridgeforge src-to-jar` and run it inside `escalation run --apply` / `revive` whenever an
  applied change touches a jar-backed source; the packet is not done until the jar class is rebuilt. Subsumes 92.2's relink and
  92.3's dedupe. Test: an agent edit to `src/X.java` of a jar mod changes `X.class` in the jar.
  Built: `bytecode/src_to_jar.py` and `bridgeforge src-to-jar` (changed sources vs original/, javap proof against the reference core at the shipped release, `patch_jar_classes` install, ledger `working/reports/src-to-jar.json`); check `jar-source-not-rebuilt` (tier code, like jar-linkage-unresolved: an approved revive step, not a SUPPORTED_FINDINGS fixer); `revive` runs it when `jar-source-not-rebuilt` is approved (`--lib` for undeclared libraries). Real data, dry run: Tania 9 sources/15 classes PASS, Eridani (Java 8) PASS, proof against an already-patched jar REFUSED. Tests: `tests/test_src_to_jar.py`.
  Open: sources are compiled as UTF-8; an author who built with a platform default (cp1252 on Windows with JDK 8-17) would be
  refused by the proof (safe, but a manual step). Try the platform encodings after UTF-8 and compile the patch with the one that
  matched. Found by CI 2026-11-17: the non-ASCII test's own javac read its source as cp1252 on the Windows runner.
- 92.26 **Done 2026-11-16.** **`patch-jar-class` cannot compile against library mods or old class versions.** Tania's spawner imports LazyLib; there is
  no option for dependency jars ("package org.lazywizard.lazylib does not exist"). Resolve dependency jars from `mod_info.json`
  dependencies via the provider index / mods folder (Tania: LazyLib, MagicLib, Nexerelin `ExerelinCore.jar`; Eridani: LazyLib,
  MagicLib, GraphicsLib `Graphics.jar`, BoxUtil `BoxUtilMod.jar`); compile at the jar class's major version, not always 17; pass
  `-implicit:none -sourcepath ""` (MagicLib.jar ships `.java` sources that javac otherwise compiles and fails on).
  Built: `patch-jar-class --lib`, `run_javac(release=)`, `jar_patch.shipped_release` (class major version -> --release); `-sourcepath ""` was already in DEFAULT_JAVAC_ARGS. Tests: `tests/test_src_to_jar.py` (Java 8 jar stays 52).
- 92.27 **Done 2026-11-16.** **`spawned-ship-captain-personality-risk` fixer refuses jar sources.** Tania had 16 3-argument `spawnShipOrWing` calls in a
  jar-backed source (11 amalgam ships, 5 neutral giant asteroids); the fixer's own template (5-argument overload with
  `bfSpawnCaptain()`, STEADY; javap confirms the overload in 0.98.5a) applied cleanly by hand. Allow it on `src/` once 92.25 rebuilds
  the jar. The packet excerpt showed 2 of the 16 calls; print the count.
  Built: the captain fixer edits a jar mod's `src/` (still refuses `jars/...`); its backup raises `jar-source-not-rebuilt`. Real data: Tania's original source gets the 16 calls rewritten as done by hand. Tests: `tests/test_fixers_92.py`.
- 92.28 **Done 2026-11-16.** **False positives found in this batch** (each accepted with evidence; fix the check, add a test per case):
  `csv-vanilla-row-override` counts commented rows: all 27 "overrides" (Musashi 17 ship_data + 6 weapon_data, Eridani 4) are
  `#Name,id,...` rows the loader skips. `star-type-undefined` matched a faction id: Tania's `star_federation` is
  `setRelationship("star_federation", ...)`. `system-generation-unguarded` misses a caller-level guard: Tania's ModPlugin calls
  `TaniaGen.generate` only when `getEntityById("carina_system") == null` (the star `Carinasystem.initStar` creates), yet it reported
  four systems "called from onGameLoad" unguarded.
  Built: `csv-vanilla-row-override` skips rows whose first cell starts with '#'; `star-type-undefined` blanks faction-call arguments; `system-generation-unguarded` (caller-level guard) not yet. Tests: `tests/test_false_positives_92.py`.
  Built (2026-11-16, second pass): `system-generation-unguarded` treats a generation call inside `if (... getEntityById("x") == null ...) { }` or getStarSystem in the plugin method as guarded (`scan_campaign._inside_existence_check`); Tania's original now has no finding, an unguarded plugin is still reported. Tests: `tests/test_false_positives_92.py`.
- 92.29 **Done 2026-11-16.** **Acceptances keyed by evidence lapse when an agent edits the file.** Tania's accepted `system-generation-unguarded` came
  back after the Carinasystem agent fix changed the finding's evidence list; it had to be accepted again. Key mod-level
  acceptances by finding id + subject (system name, file), not the full evidence.
  Built: baseline keys drop line numbers from the evidence part (`baseline.stable_evidence`), applied to stored keys on load so older baselines still match; a different subject still counts as new. Tests: `tests/test_small_fixes_92.py`; 1111 baseline/escalation/archive tests pass.
- 92.31 **Done 2026-11-16.** **`player-text-non-english` counts JSON `#` comments.** Eridani Combine after `translate-batch` (59 units translated,
  2189 -> 761 CJK characters): 753 of the 761 were `#` comments in `EridaniCombine.faction`, `engine_styles.json`,
  `hull_styles.json` (Starsector JSON allows `#` comments) and a `designTypeColors` key that is never displayed. Blank `#`
  comments (as `_load_lenient_json_file` does) and skip JSON keys before counting.
  Built: JSON-style data files are counted without trailing `#`/`//` comments and object keys (`scan_text._json_player_part`). Real data: Eridani working copy now clean, the untranslated original still flagged (1431 characters, was 2189 with comments). Tests: `tests/test_fixers_92.py`.
- 92.32 **Done 2026-11-16.** **Full-width punctuation fixer.** The real leftovers were `：` (U+FF1A, x2 in the `mod_info.json` author line) and `，`
  (U+FF0C, a hull-mod tooltip in `hull_mods.csv`), outside the game font; replaced by hand with `:` and `, `. A SAFE fixer for
  full-width ASCII punctuation (U+FF01-FF5E, U+3001/3002) in English player text, after translation.
  Built: check `fullwidth-punctuation-in-text` (SAFE, auto) and its fixer (`fixers.encoding._fix_fullwidth_punctuation`, shared rule `scan_text.fullwidth_punctuation_fixed`): lines still holding other CJK are left to translation, line endings and BOM kept. Real data: Eridani's pre-fix files give exactly the two hand-fixed lines. Tests: `tests/test_fixers_92.py`.
- 92.33 **Done 2026-11-16.** **Translating jar strings leaves `src/` untranslated.** `translate-batch --in-place` patched 18 strings in Eridani's
  `ECE.jar` (19:49) but `src/` keeps the Chinese, so a later `src-to-jar` rebuild of such a class would revert the
  translation; the 92.25 proof now refuses (the jar no longer matches the source), which is safe but blocks the rebuild.
  Apply translations to the matching `src/` string literals too, and record the jar classes changed in the src-to-jar ledger.
  Built: `translate-apply` mirrors each translated jar string into the matching `src/<class>.java` literal (raw or \u-escaped form); `src-to-jar` proves against the jar in `original/` by default, so neither a translated nor an already-patched working jar blocks the proof. Tests: `tests/test_translation_92.py`, `tests/test_src_to_jar.py`.
- 92.34 **Done 2026-11-16.** **`hullmod-instance-state` misses fields set only at declaration but mutated.** Bultach Coalition: the agents also (rightly)
  moved `bt_puncher.rightArm` (`new bt_SinuousSegment[2]`, filled per ship) and `bt_stolen_blastdampeners.nearbyShips`
  (`new HashSet<>()`, add/remove per ship), and removed `readResolve` (it only re-created a moved field), but the packets did not list
  them, so `src-to-jar`'s automatic allowance (the packets' `field:` names) refused until `--allow-removed` named them. Flag a
  collection/array field whose elements are written in `advanceInCombat`/`applyEffects*`, and allow `readResolve` when every field it
  touches moved. The same run showed `javap` output must be read as bytes (cp1252 'è' constants left `_javap_stats` stdout None);
  fixed in `jar_patch._javap_stats` and `src_to_jar._javap_text` (test: `test_non_ascii_string_constants_do_not_break_the_proof`).
  Built (part): the evidence cap of 12 fields is gone (bt_puncher.rightArm was the 13th; real data now lists 16). Collections stay excluded on purpose (a Map keyed by ship is the correct per-ship pattern), so `nearbyShips` and `readResolve` still need `--allow-removed`. Tests: existing hullmod-instance-state suites (159).
- 92.35 **Done 2026-11-16.** **Library-provided classes in the vanilla namespace.** Bultach's `jar-linkage-unresolved` on `bt_murtach_start` named
  `rulecmd.newgame.NGCAddStartingShipsByFleetType.generateFleetFromVariantIds` "class missing"; Nexerelin 0.12.2d's
  `ExerelinCore.jar` ships that class (javap), and the start extends Nexerelin's `CustomStart`, registered only in
  `data/config/exerelin/customStarts.json`. Resolve linkage against the jars of libraries the mod uses even when undeclared (here
  via its `exerelin` imports), and treat classes only reachable through a library's config as optional.
  Built: `_scan_jar_linkage`/`_scan_jar_interface_methods` take the scan's provider roots (incl. queue workspaces' working/), and `revive` adds the reference install's `mods/`. Real data: Bultach's NGCAddStartingShipsByFleetType resolves through Nexerelin. Tests: `tests/test_jar_linkage.py`.
- 92.30 **Done 2026-11-16.** **Crafted descriptions, second and third samples (extends 92.15).** Bultach: 8 of 14 crafted rows contradicted their spec (a TELEPORTER/PHASE_DISPLACER system described as a weapons overdrive, a BURN_DRIVE given blast damage, an ENGINE_MOD given a fuel cost, a Bultach hull called Gestalt); corrected by hand. Musashi: 5 of 9 crafted rows contradicted the data: Tadaiji Lance
  (2800 energy/shot, range 1200, hints STRIKE, LARGE) and Bushi Rift Cannon (1300/shot, STRIKE) as "general combat" weapons; a
  phase cloak given an unsupported flux claim; a "slow" torpedo the spec does not show; the Raidsuit's class (ship_data
  designation Destroyer vs `.ship` hullSize FRIGATE). Feed `weapon_data` damage/shot, range, size, hints and tags, the system
  `.system` type, and hull designation/size into the prompt; reject rows that state a role contradicting STRIKE/PD hints.
  Built: facts now carry damage/shot, damage/second, range, hints, bays, speed, defense, active/cooldown, and the spec files' hullSize, weapon type/size/specClass, system type/aiType; the prompt reads STRIKE/PD/system types literally; `check_against_facts` rejects STRIKE-as-general, PD without defence, a wrong hull class and a system text not describing its spec type. Replayed on the batch's real drafts it rejects 5 of the 13 hand-found errors (the rest were judgement calls the richer facts and prompt address). Tests: `tests/test_descriptions_draft.py`.
- 92.36 **Done 2026-11-16.** **Prune escalation sandboxes after verification.** Bultach Coalition's workspace was 2.1 GB, 1.7 GB of it
  `scratch/escalations` (one full working copy per agent attempt, 33 packets). Once a packet is APPLIED or FAILED, keep the note,
  the diff against the first backup and the verify result, and drop the sandbox copy (or hard-link unchanged files); report the
  bytes freed.
  Built: `escalation prune WS [--apply]` (`escalation/prune.py`): only attempts the ledger shows finished; changed files kept under attempt-N/changed/, PRUNED.json written, `working/` removed via safe_rmtree within scratch/. Real data (dry run): Bultach 21 attempts, 1722.9 MB. Tests: `tests/test_escalation_prune.py`.
- 92.37 **Done 2026-11-16.** **Workspaces with no backup, and a supported copy to the main machine.** On White_Legion `bridgeforge-state/snapshot.json`
  is absent, so `state-snapshot` never ran after the six revivals; the only copy was the working disk (and this machine's `Done/`
  had already lost its files, 92.24). The six workspaces and zips were copied to Test1 by hand (`tar | ssh tar`, refusing existing
  names; 2.7 GB). `hygiene`/`board` should warn when revived workspaces have no snapshot destination, and a `sync-to HOST:PATH`
  (or `state-snapshot --to` over SSH) should copy named workspaces, refuse to overwrite, and verify file counts and hashes.
  Built (part): `board` has a Backup section listing UNATTENDED_DONE workspaces when no snapshot destination is configured. `sync-to` dropped (owner 2026-11-16: sync means GitHub; the six workspaces were copied to Test1 once, 52,252 files, counts and key hashes verified). Tests: `tests/test_board_92.py`.
- 92.38 **Done 2026-11-16.** **CLAUDE.md names the target install by folder, not build.** CLAUDE.md says revivals target 0.98.5a-RC3 at
  `C:\Games\Starsector-0.98.5a-RC3`; on Test1 that folder holds RC7 (owner 2026-11-16), White_Legion's is `Starsector985a` (also
  RC7, read from `starfarer_obf.jar`). State the build as `target show` reports it, and make `target show` print the version read
  from the core beside the registry entry so a stale folder name cannot mislead (with 92.9).
  Built: CLAUDE.md states the build (0.98.5a, RC7 per `target show`) and warns that Test1's RC3-named folder holds RC7; see 92.9 for `target_core_reports`.
  Correction 2026-11-17 (92.40): that claim was wrong; Test1's RC3 folder reports RC3. CLAUDE.md now says so.
- 92.39 **Done 2026-11-17.** **Acceptances did not travel between machines.** Everybody loves KoC's accepted
  `vanilla-path-shadowing` came back on Test1: its evidence names the absolute core path
  (`vanilla-path:C:/Program Files (x86)/.../Starsector985a/starsector-core/...` here, `C:\Games\...` there), so the baseline key
  differed. Built: `baseline.stable_evidence` cuts any absolute path up to a `starsector-core` folder (either slash, drive or POSIX)
  to `starsector-core/...`, for new keys and stored ones as they load. Tests: `tests/test_small_fixes_92.py`.
- 92.40 **Test1's "RC7" was RC3; and a copy mangled non-ASCII names.** Live-test preparation on Test1 (2026-11-17):
  `core_game_version` read `0.98.5a-RC3` from `C:\Games\Starsector-0.98.5a-RC3` and its `starfarer_obf.jar` differed from
  White_Legion's RC7 (sha256 1d8301ec... vs 8b917602...), contradicting 92.38's note; Bultach raised an RC3-only
  `rc8-signature-changed` there. The RC7 install was copied to `C:\Games\Starsector-0.98.5a-RC7` (6143 files, same jar hash, reports
  RC7) and a separate test rig `_rig-0985a` points at it (the RC8 `_rig` is untouched). Separately, the `tar | ssh tar` workspace
  copy (92.37) turned Eridani's `图层 173.png`/`图层 174 拷贝.png` into code-page mojibake in all six places (fixed by renaming from
  code points; content hashes matched). Open: any cross-machine copy BridgeForge offers must compare names byte for byte, not
  only file counts and content hashes; `target show` should be run on each machine before a live session (92.9 makes it say the
  build).

**91. Side by side: the old and the new build together (owner 2026-11-15: "for the side to side ideas, go ahead and implement. apply same process for other repos").**
- 91.1 **Done 2026-11-15.** `vanilla-migration OLD_CORE NEW_CORE [--write DIR]`: for every member `api-diff` lists as removed and every
  same-signature parameter rename, vanilla's call sites in both builds' `starfarer.api.zip`, paired by file, with what the new code
  passes in the new positions, and each gated fixer rule checked against it (BACKED / DIFFERS / NO_VANILLA_CALLS). `target-bump`
  writes it into `targets/<build>/`. RC8 -> 0.98.5a: BACKED 3, DIFFERS 3 (vanilla passes the ship it has where `ShipAIConfig(null)`
  keeps RC8's defaults), NO_VANILLA_CALLS 1. It showed `pickPortraitPreferNonDuplicate(f, g)` -> `(f, g, null)` is exact: 0.98.5a's
  body is RC8's plus `if (random != null) return picker.pick(random)`, and vanilla's `PromoteOfficerIntel` passes null. New gated
  rule in `signature_rewrites.TARGET_RULES` and `jar_call_rewrites.RULES` (INVOKESTATIC): Kadur Remnant (both copies) is now
  fixers-only. `reportSuccess(int)` stays a hand port: the int changes the result and vanilla passes the bounty's level.
- 91.2 **Done 2026-11-15.** `target-impact` records `touches` (changed API classes a mod uses: references, descriptors, supertypes,
  imports; and calls to a changed name). The catalogue's "Live-test order for CLEAN mods" ranks them: 61 CLEAN mods touch changed
  classes (most: `DModManager.addDMods`, `BaseIndustry.getSupply`).
- 91.3 **Done 2026-11-15.** `new-vanilla-id-collision` (REVIEW): a content id the mod defines that the new vanilla defines for the
  first time (the mod's row silently replaces vanilla's new content). Found YunruCore's `low_maintenance` hull mod (3 copies).
  `resolved_on_new`: links that fail on the old core and resolve on the new.
- 91.4 **Done 2026-11-15.** `vanilla-now-provides` (information only): a static helper whose name and arity match a method the new
  API added under a new name; 3 leads (Exotica `getWidth/getHeight`, Void-Tec `getScript`, likely name coincidences).
- Real run RC8 -> 0.98.5a (471 folders): BREAKS 35, RELINK 4, REVIEW 4, CLEAN 428; fixers alone clear 25 of 43.
- Sister repos, same idea (agents, 2026-11-15): Salvor PR #13 `salvor version-check SAVE --core NEW` (classes a save names that
  the new core lacks; an RC8 save: none vanilla, 64 mod classes unresolved -> UNKNOWN); VoidSmith PR #15 `vanilla-diff` (39 hulls,
  21 weapons, 9 hull mods changed; 977 generated files name a changed id); Project Go PR #13 `string-diff` (94 added, 2 removed, 308
  changed of 5,822 strings; carry-over of a translation pack). RevenantLib: nothing to add (its dual-build check is 90.4).
- Tests: `tests/test_target_delta.py` (7), `test_signature_rewrites` (portrait rule), existing target tests.

**90. A new game build in one run (owner 2026-11-15: "Go ahead with item 90"; design `docs/MULTI_VERSION_COMPAT_DESIGN.md`, owner decisions the same day).**
The RC8 -> 0.98.5a move (item 89) took a dozen hand-run commands, each given the core path again, and a scratch script to merge
their results.
- 90.1 **Done 2026-11-15.** `bridgeforge-state/target.json` names the target build and core; `target show|set CORE [--status]|export
  --to FILE`. `targets/<build>/build.json` is the registry entry (build read from the core, SHA-256 of its three jars, the
  `gameVersion` strings meaning the build, save versions, status QUALIFIED/OBSERVED/RETIRED, previous build); a different install
  claiming a recorded build is refused. `export` drops local paths. `--vanilla-core @target` (any argument that is exactly
  `@target`, also in lists) resolves in `cli.main`; nothing resolves without the token. Local state: RC8 QUALIFIED, 0.98.5a-RC3
  OBSERVED and the target.
- 90.2 **Done 2026-11-15.** `target-bump NEW_CORE [roots] [--from OLD] [--stats FINDING_STATS.json] [--no-set] [--restart --quiet]`:
  api-diff, target-impact (checkpoint in `targets/<build>/impact/`), `CATALOGUE.md/.json` (the item 89 scratch merge made
  permanent, joined to a full scan by folder name), registry entry, then the target moves. Real run RC8 -> 0.98.5a over `Done/` and
  `In operation/` (471 folders): BREAKS 35, RELINK 4, REVIEW 1, CLEAN 431; fixers alone clear 23 of 40. Item 89's v3 had BREAKS
  36: RevenantLib 1.3.0+bf.2 (RevenantLib PR #4) is now clean. Listed in `progress.LONG_RUNNING_COMMANDS`.
- 90.3 **Done 2026-11-15.** `retarget [--impact FILE] [--apply]`: every CLEAN workspace not yet on the target gets `gameVersion`
  (the `mod-info-game-version-inexact` edit) and `bump_version` (`+bf.N`, a revival-report section ending READY_FOR_LIVE_TEST, a
  MOD_CHANGELOG line). Archives, non-CLEAN and already-moved mods are listed with the reason. Plans only without `--apply`;
  the 0.98.5a plan lists 287 workspaces, not applied (owner to decide).
- 90.4 Open: a `dormant` verdict for dual-build mods (a call the old core lacks, made only in a method the old core's interfaces do
  not declare, as RevenantLib's forwards). Needs a per-method call-site listing from the ASM helper; linkage reads only the
  constant pool.
- 90.5 Open (design step 1 rest): per-build behaviour-fact states (CARRIED/RECHECK/PROVEN) classified by `target-bump`.
- Tests: `tests/test_target_bump.py` (10: registry, fingerprint refusal, status kept, token resolution in paths/strings/lists,
  bump end to end with checkpoint removal, catalogue join, retarget plan and apply).

**89. 0.98.5a-RC3 as the target (owner 2026-11-15: "check against api of latest starsector ... find conflict with current mods and revive mods ... adding new automation, checks and fixers"; then "for now target the newer version unless possible to refactor so they can target both with a simple mod_info version change").**
The owner installed 0.98.5a-RC3 at `C:\Games\Starsector-0.98.5a-RC3` (Java 17, Zulu 17.0.10; its `jre\bin` has `javac`/`javap`).
A dual target through `mod_info.json` alone is not possible for mods that break: a class compiled for 0.98.5a's
`ShipAIConfig(ShipAPI)` cannot link on RC8. Outputs of the measurements below are in `bridgeforge-state/api-diff/` and
`bridgeforge-state/target-impact/0.98.5a-RC3/` (local, gitignored).
- 89.1 Measured: `api-diff` RC8 -> 0.98.5a-RC3: 3076 -> 3172 classes, none removed, 20 methods and 2 fields removed; `ShipAPI`
  gained six methods, `CampaignTerrainPlugin`, `WeaponAPI`, `MissileAPI` more. One same-descriptor meaning change, found by
  comparing parameter names in the two `starfarer.api.zip` sources: `Misc.getOfficerSalary(PersonAPI, boolean)` was `mercenary`,
  is `checkIfInPopulatedSystem`. Content: no hull, weapon, wing, hull mod or ship system removed; 115 story and dev `rules.csv`
  ids removed; new `ship_data.csv` columns `parts/dmod`, `salary`, `salMult`; `settings.json` drops
  `factionCommissionStipendPerLevel` and gains a `rules` list of rule files and about 180 `ext_*` keys.
- 89.2 Built `target-impact OLD_CORE NEW_CORE [roots] --write DIR`: per mod, what fails on the new core and not the old (jar
  linkage, interface contracts, dropped call forms; data: rule ids a mod overrides that were removed, replaced CSVs lacking new
  columns, settings keys read and removed), with progress and a checkpoint. First run (471 mod folders in `Done/` and
  `In operation/`, before the data layer): BREAKS 36, RELINK 4, CLEAN 431; `Done/` archives: 10 break, 2 need a relink.
  `tests/test_target_impact.py`.
- 89.3 Gated rules (applied only when the target core's own API jar lacks the old member and has the new one):
  `new ShipAIConfig()` -> `(null)` (RC8's defaults exactly, both sources), `isBeingIgnored()` -> `(false)`,
  `Misc.getOfficerSalary(p)` -> `(p, Misc.isMercenary(p), false, false)` and `(p, b)` -> `(p, b, false, false)`; the
  `rc8-signature-changed` check and fixer pass the core (`TargetGatedRewriteTests`).
- 89.4 Finding `jar-call-signature-changed` (auto, REVIEW) and fixer: the same calls rewritten in jar bytecode (ASM
  `append-constant-argument`, a fresh constant pool so no stale Methodref remains for linkage); `jar-linkage-unresolved` no longer
  repeats them. Polaris Prime's and RevenantLib's jars rewrite as expected (dry run); the test runs the rewritten class with
  `-Xverify:all` (`tests/test_jar_call_rewrites.py`).
- 89.5 Finding `forwarding-class-method-missing` (auto, REVIEW) and fixer: a class implementing a game interface by forwarding to
  one field gets forwards for the methods the target added and loses `@Override` on methods no supertype has any more. RevenantLib's
  `dl_DroneAPI` compiles against 0.98.5a after it and 89.3 (6 forwards, 1 call, 1 `@Override`; scratch copy, working copy untouched)
  (`tests/test_forwarding_methods.py`).
- 89.6 Fixes: `linkage._resolve` walked a constructor up to `Object.<init>()V`, so a removed no-argument constructor was never
  reported; `linkage` reads jar entries with `zipsafe.read_limited` and indexes `txw2-3.0.2.jar`; `compile-check` built the full
  provider index for every mod with dependencies (74 of AI-War's 130 s), now ids map to folders from `mod_info.json`, cached;
  `finding-stats` scans `Done/` archives (shipped copy, `workspace/baseline.json`, `_` folders skipped); eight test files use
  `tests.support.javac_path()` so JDK tests run where the only JDK is the rig's.
- 89.7 Open: the archive-wide `finding-stats --scan` against 0.98.5a (running after this merge); revival of the breaking mods
  (fixers above, then `patch-jar-class --vanilla-core <0.98.5a core>` where source exists); hand ports for
  `PersonBountyEventData.reportSuccess(int)` and `pickPortraitPreferNonDuplicate(..., Random)`; obfuscated internals in Station
  Augments and Neutrino 1.8.9; a 0.98.5a rig and live runs; whether a `rules.csv` row overriding a vanilla id behaves as on RC8
  under the new `rules` list (live). Proposed: a target profile so finding text says "the target" instead of "RC8".
- 89.8 **Done 2026-11-15.** Same signature, other meaning: `api_sources.parameter_renames` compares parameter names of every
  public/protected method in the two `starfarer.api.zip` bundles; `api-diff` adds `parameters_renamed` to its catalogue (and
  prints them) whenever both zips sit beside the jars, as the game ships them; `target-impact` reports a mod calling such a
  member (jar reference by owner, name and arity; source call by name and arity in a file naming the class) as
  `parameter-meaning-changed` (REVIEW). RC8 -> 0.98.5a-RC3 gives exactly the one 89.1 found by hand, `getOfficerSalary`.
  `tests/test_api_sources.py`.
- 89.9 **Done 2026-11-15.** `revive --target` defaults to the `--vanilla-core`'s own version (`game_version.core_game_version`, the newest
  version string in its `starfarer_obf.jar`: 0.98.5a-RC3 there, 0.98a-RC8 in RC8), else 0.98a-RC8; reviving against 0.98.5a no longer
  writes RC8 into `mod_info.json`. With 89.3-89.5 the gated fixers run inside `revive --vanilla-core <0.98.5a core>` (approval as
  for any fixer). `tests/test_game_version.py`.
- 89.10 Measured 2026-11-15: a replaced CSV missing columns is tolerated. Ironclads replaces three data CSVs lacking 13-17 of RC8's
  columns each and was LIVE_VALIDATED on RC8, so `target-impact` lists `replace-lacks-new-columns` as information (no REVIEW verdict
  by itself) and no blank-column fixer was added (it would change nothing).
- 89.11 **Done 2026-11-15.** `target-impact` writes a worklist: per mod that breaks, the next steps in order (the gated `fix`
  commands with the new core, a relink through `jar-packets`/`patch-jar-class`, a hand port, a review) and `fixers_only` when the
  gated fixers alone clear it, with a count in the report. Also fixed: the ASM and AST helpers were cached by source hash only, so a
  helper compiled by the rig's Java 25 failed under the game's Java 17 (UnsupportedClassVersionError); they are now compiled
  with `--release 17` and cached by that. `tests/test_target_impact.py`.
- 89.12 **Done 2026-11-15.** The forwarding check's declaration pattern backtracked for 1,000 s of CPU on Angry Periphery 4 and stalled
  the archive scan; types now match without free spaces or commas, and a generic method's `<T>` is allowed.
- 89.13 **Done 2026-11-15.** Guards: with no JDK found, `helper_java_tools` falls back to bare names and their FileNotFoundError
  ended a whole scan; the AST and ASM helper launches now raise `AstUnavailable`/`BytecodeUnavailable` (the scan reports
  `source-ast-unavailable`). `tests/test_scan_robustness.py` also gives the whole scanner a time budget on a mod with very long
  lines, with and without a core, so a backtracking pattern fails the suite (it fails with 89.12's old pattern).

**88. Hand work from the Exotica RC4 and New Galactic Order sessions, made routine (owner-approved 2026-10-26: "all
approved for now set in roadmap").** Each entry names the hand work it replaces. Suggested order: 88.1-88.2, 88.3, then
88.4-88.5; 88.6 waits for a second mod with the same CSV layout problem. Nothing below is built yet.
- 88.1 `probe-group record` writes who ran the session: "Owner ran New Game..." is printed even for unattended
  `probe-group live` runs (NGO-LIVE-20261026; corrected by hand). Take it from the live run record.
  **Closed 2026-11-19 (roadmap review): already built.** 96.5 A1: the record credits the run, not the owner (`tests/test_build_labels.py`).
- 88.2 The live harness treats "the game window is gone" after the probe's `done` marker and a graceful close as LIVE_DONE
  (87.9, EXO-RC3-LIVE-20261026).
- 88.3 `rig-check`: scaffold, build, install and collect rig-only check mods. Today two were hand-made (`bf_exotica_check`,
  `bf_csv_quote_probe`): mod_info, plugin, javac against the jar and RC8, jar, copy into the rig, edit
  enabled_mods.json, grep `BF-*` lines. They produced the strongest evidence of the day (RC3 vs RC4; RC8-38/39).
  Collected lines go into the run record and `probe-group report`.
- 88.4 A/B live runs: `probe-group live --variant NAME=FOLDER` runs the same group against two builds of one mod and
  reports both (RC3 vs RC4 needed a hand swap of the rig folder, and the probe's class list then named the wrong build).
- 88.5 `intake` reads .rar/.7z itself (7-Zip CLI, py7zr) and takes `--drop-junk` to remove desktop.ini/Thumbs.db with a
  record; both of today's archives were extracted by hand and NGO was blocked by a desktop.ini.
- 88.6 87.11's CSV layout check plus a `fix` that re-maps rows written in a reference core's layout by column name,
  refusing when a dropped column holds a value (hand script for NGO's ship_systems.csv, 2026-10-26).
- 88.7 `test_guard` fails fast with "environment incomplete" when a declared dependency (psutil) is missing, instead of
  running into 141 import errors and replacing `bridgeforge-state/last-suite.json` with that result.
- 88.8 **Done 2026-10-26.** The project `.venv` has `setuptools` 84.2.1 (`uv pip install --python .venv/Scripts/python.exe
  setuptools`); `tests.test_package_discovery` now passes locally (S branch).
- 88.9 `bridgeforge ci-local --linux`: the WSL recipe (vendored manylinux wheels, tracked-file tarball, git repo,
  `set -e` and literal paths) as a command, run before pushing; the S branch passed every local check and failed 17
  tests on Ubuntu CI.
- 88.10 A "maintainer RC" workspace kind for third-party test builds (Exotica 2.1.1-RC4): no archive, the outputs are a
  diagnosis report and a test build, and `probe-group plan` keeps it out of revival groups.
- 88.11 Merge order: the S branch carries all of B0-B6; item 87 merges on top of it with three import fixes and a
  regeneration, done and verified in `integration/s-series-with-87` (87 affected tests OK). Merge S first, then that
  branch, rather than item 87 onto main directly.
  **Closed 2026-11-19 (roadmap review): culled.** A merge order for branches merged long ago.
- 88.12 **Done 2026-10-26.** `probe-group live` presses SPACE again after each 90 s without the probe's "combat END" (the round runs
  about 60 s once unpaused). The single press 2 s after deploying could leave the mission paused (EXO-RC4B-LIVE-20261026 stopped
  logging after deployment; the owner had been unpausing combat by hand). Five later unattended runs finished combat on their own.
  Test: `tests/test_live_run.py` (`test_combat_left_paused_by_the_first_space_is_unpaused_by_a_retry`).
- 88.13-88.18 below come from the Exotica #76 Refit-screen sessions (EXO-MANUAL-20261027B-H) and the three upstream PRs
  (RkShaRkz/ExoticaTechnologies #77-#79); owner-approved 2026-10-27 ("yes add to roadmap"). Suggested order: 88.14, 88.16,
  88.15, 88.17, 88.13; 88.18 is deferred.
- 88.13 Kotlin compile check for a mod's source checkout (`kotlin-compile-check`), from the hand script that compile-checked
  the PRs. Current LazyLib/LunaLib/MagicLib jars carry Kotlin 2.1 metadata, which kotlinc 1.6.21 cannot read, so use kotlinc
  2.1.x. LunaLib's inline functions need `-jvm-target 17`, and `-language-version 1.9` (the K1 frontend) matches code written in
  the IDE. Unit tests whose mocks implement an older API are left out. Errors are compared with the unpatched checkout, so
  library drift (4 baseline javac errors from LazyLib 3.0 hiding `DrawableString.setColor`) is told apart from breakage.
- 88.14 The script sandbox refuses `java.lang.reflect` in mod code ("File access and reflection are not allowed to scripts",
  EXO-MANUAL-20261027F; a fix that used it never ran). Add the RC8_BEHAVIOUR row, and have `delegate-method` and
  `patch-jar-class` refuse a helper class whose constant pool names `java/lang/reflect/*` or `java/io/File`; the safe form is
  MethodHandles with the reflect objects typed as Object (how Exotica's RefitButtonAdder does it).
- 88.15 `save-slots SAVE [SAVE2]`: per fleet member and per module slot, the mod tags (a prefix such as `$$EXOTICA$$`) and
  hull mods from a campaign.xml, and the difference between two saves. The saves were the decisive evidence in every #76 run;
  each was read with a hand script (`save_slots.py`).
- 88.16 An `-Interactive` session copies its evidence when the game closes: the save folder(s) written during the session
  (campaign.xml and .bak), the stdout log and the triage, into the workspace's `reports/.../evidence/<TESTID>/`. Done by hand
  after each of seven runs.
- 88.17 Manual-run protocol: a checklist names the build (jar sha), starts from New Game per build, and records the starting
  state. Runs D-G "reproduced" an AlphaSubcore bug only because they started from a save that already carried it; the
  maintainer's build from New Game was clean (run H).
- 88.18 Deferred: a Refit-screen driver that records the owner's clicks once (fixed resolution and ship) and replays them per
  build with screenshot checks, so before/after runs need no person. Module positions and LunaLib panels make it fragile.
  **Closed 2026-11-19 (roadmap review): culled.** Deferred as fragile (a Refit-screen click replay); the probe and scenarios cover the same ground.
- 88.19-88.23 below come from the Ironclads v.11+bf.2 runs of 2026-10-30 (RC8-41, RC8-42). Proposed, not started.
- 88.19 `live --save-reload` calls a reload LIVE_DONE at the compare line, before the load ends: ICBF2-J28FR's Fatal came 243 ms
  later, was reported as LIVE_DONE, and `log-triage` said FATAL=0. Stay up after the compare line and fail on a dialog.
- 88.20 Fast Rendering launchers set `-XX:+ShowMessageBoxOnError`. The box outlives the killed java (owner becomes csrss) and blocks
  every click of later runs; the watcher does not list it (two false LIVE_STUCK at new-game, CTL30-J28FR). Detect and record its
  text, press No, and refuse to start while one is open. The scratch driver did this with EnumWindows and BM_CLICK.
- 88.21 A total conversion that replaces `mission_list.csv` can never bind a combat run: `install` adds the probe's row, so the staged
  hash differs from the candidate (ICBF2C-J25 REFUSED). bf.2 needed a second run on exact bytes with no combat expected. Let the
  manifest name that one probe-row change, or add combat evidence that carries the staged difference openly.
- 88.22 `drive_reload` clicked Continue and started a New Game on Java 28 direct (ICBF2C-J28): the log shows a new sector and a new
  save, and the run ended as no compare line. FR096-IC7-J25FR hit the reverse: the New Game flow opened the load screen and loaded an
  old save, reported as stuck at new-game. Confirm the save-load log line after the click. Also: REMOVALS.json needs its `files`
  category (77.19), since bf.2 needed `--allow-unexplained` for four files known to be fine, and that path writes "recorded by the
  owner" into ARCHIVE_NOTE.md even when an agent wrote the reason on the owner's instruction.
- 88.23 `fleet-presence` WARN "0 fleets" is mostly false: route fleets spawn only near the player (RC8-41 evidence). Count routes per
  faction from the save or the API instead. `faction-known-lists` should be read with hull bays: 0 known fighters matters on a carrier.
  Window screenshots (`*-window1.png`) can catch the desktop when the game is not in front; keep them out of shared evidence.
- 88.24 **Done 2026-11-01.** `java_matrix.flags_to_drop` leaves `--enable-preview` out of every generated JDK 28+ launcher (direct, FR, Mikohime) and
  records it in `dropped_flags`; on jdk-28+13 it corrupts save loads (RC8-42). Stock `fr.vmparams` is only read, and its line 41 still carries the flag.
  Tests: `tests/test_java_matrix.py` `EnablePreviewOnJava28`. Live: `J28DX-j28-base-1` and `J28DX-j28-fr-stock` -20261101b on regenerated launchers.

**87. Kotlin jars and module identity, from the Exotica 2.1.1-RC3 diagnosis (owner 2026-10-26: "fix mod and create a RC4
version of Exotica", "apply lessons learned and handwork to bridgeforge").** Exotica's RC3 test build lost exotics on
multi-module ships: it keyed modules by hull variant id, which RC8-37 shows is not unique within a ship (11 of 12 RC8
stations repeat a module id; 598 of 2,023 local multi-module variants). The jar is Kotlin without public source, so RC4 was
built by delegating eight method bodies to a Java helper (`In operation/Exotica-Technologies-2.1.1-RC4/`, report in
`In operation/Exotica-Technologies/reports/EXOTICA_2.1.1-RC3_MULTIMODULE_DIAGNOSIS.md`). LIVE TEST NOT PERFORMED.
- 87.1 **Done 2026-10-26.** `delegate-method`: replace chosen method bodies with one static call into a separately compiled
  helper class (ASM, `bridgeforge/java/BridgeforgeDelegateMethod.java`); verified by bytecode that exactly the named methods
  changed and none were added or removed; the output is a new jar patched with the JDK `jar` tool. Tests:
  `tests/test_delegate_method.py` (runs the patched jar under `-Xverify:all`; refusals).
- 87.2 **Done 2026-10-26.** `decompile-jar` counts Kotlin sources (`.kt`, which `rebuild-jar` cannot compile) apart from Java
  and says so in `next`; Exotica's jar gave 319 `.kt` beside 56 `.java`, reported as "56 source files". Test:
  `tests/test_decompile.py`.
- 87.3 **Done 2026-10-26.** BridgeForge's own Java helpers (bytecode inspect/rewrite, Java AST) compile and run with one JDK
  (`JdkInfo.java`, `helper_java_tools`). On the owner's machine PATH has Java 8's `java` beside JDK 25's `javac`: the helpers
  compiled a version-69 class the runtime refused, so bytecode inspection and Java AST analysis failed there. Tests:
  `tests/test_java_toolchain.py`.
- 87.4 **Done 2026-10-26.** `patch-jar-class` no longer refuses the loss of IntelliJ's `$$$reportNull$$$N` (`@NotNull`
  instrumentation javac never emits), like `lambda$`/`access$`. Test: `tests/test_jar_patch.py`.
- 87.5 RC8-37 (module ids are not unique within a ship) and RC8-38 (`HullVariantSpec` identity; an unset module slot returns
  `SpecStore`'s shared spec) added to `docs/RC8_BEHAVIOUR.md`.
  **Closed 2026-11-19 (roadmap review): already built.** `docs/RC8_BEHAVIOUR.md` RC8-37 and RC8-38.
- 87.6 Proposed, not built: a REVIEW scan finding for jar code that keys per-module state by `getHullVariantId()` while the
  mod (or a mod it supports) ships variants that repeat a module id (RC8-37). Needs owner approval.
  **Closed 2026-11-19 (roadmap review): culled.** Proposed, never approved; the Exotica fix it came from is upstream (PRs #80-#82).
- 87.7 Exotica RC4 live, 2026-10-26: smoke PASS; EXO-RC4-LIVE-20261026 LIVE_DONE with the rig-only `bf_exotica_check`
  13 PASS/0 FAIL/1 SKIP, while RC3-fix2 (EXO-RC3-LIVE-20261026) fails the two predicted checks (identical-module
  clobbering, prefix-sibling bleed). Results in the RC4 workspace's `working/reports/REVIVAL_REPORT.md`. Still pending:
  the owner's hands-on refit session (`docs/LOCAL_HANDOFF.md`, "Exotica 2.1.1-RC4").
- 87.8 **Done 2026-10-26.** `intake`'s publish rename waits about a minute (backoff capped at 8 s) instead of ~14 s. Exotica RC4
  (8 MB) and New Galactic Order (35 MB) both failed with "Access is denied" after the old retries and passed on an immediate
  rerun of the same bytes, as a first antivirus scan of new bytes would (the Yunru pack hit it on 2026-10-04). Test:
  `tests/test_raw_intake_and_lunalib_rule.py`.
- 87.10 **Done 2026-10-26.** `csv-field-bare-quote` (REVIEW, low): a row that Python's `csv` reads as too wide but RC8
  reads whole because of a bare quote pair inside a quoted field (RC8-39, proven on the rig with a quote probe mod) is no
  longer reported as a MANUAL `csv-row-extra-columns` spill; the quote marks vanish in game. Found on New Galactic Order's
  descriptions.csv. Test: `tests/test_revival_lessons.py`.
- 87.11 Proposed, not built: a check for CSV rows written in another layout than their file's header (New Galactic
  Order's ship_systems.csv: three rows in vanilla 0.9a's 26-column layout under the mod's 24-column header, so every value
  after column 8 loaded one column off, e.g. EMP active 0.5 s instead of 4). Detection: a too-wide row whose values line up
  with vanilla's header for that file (any reference core) once the missing columns are empty. Fixed by hand in NGO.
  **Closed 2026-11-19 (roadmap review): superseded by 88.6.**
- 87.9 Observation, not fixed: `probe-group live` raised "the game window is gone" on EXO-RC3-LIVE-20261026 after the probe's
  `done` marker (campaign, combat) and the graceful close, while `drive` still navigated to the mission list. The run was
  complete; the harness should treat a window that closes after `done` as LIVE_DONE.
  **Closed 2026-11-19 (roadmap review): superseded by 88.2.**

**86. Re-check the archive across environments and against AoTD (owner 2026-10-22; after item 83, uses 85.1).** Everything
archived was live-validated on Java 25 direct, alone or in small groups. Scope (Done/ 2026-10-22): 112 archives carry code (jars
or loose scripts) and are re-checked; 42 are data-only (portraits, sprites, CSV) and are skipped, since launcher, Java and the
pre-patcher only change how code loads and runs. Runs are grouped (`probe-group regress` grouping: no shared mod or content
ids, dependencies present), about 15-25 groups per environment; a failing group is split with `probe-group bisect`. Order:
- 86.1 Forecast first, offline: `atlas sweep aotd` over every indexed archive (Mod Atlas, item 67's first use) ranks each mod's
  predicted conflicts with Ashes of the Domain (Vaults of Knowledge, Theory of Toolbox fork, Building Menu Overhaul, Ashlib)
  and refreshes the census. Done when every code archive has a forecast and a risk rank.
  **Closed 2026-11-19 (roadmap review): culled.** AoTD passes; owner 2026-11-17: AoTD is under an overhaul and can be ignored for now.
- 86.2 AoTD alone: the `aotd` set with the probe on the pre-patcher launchers (AoTD's Toolbox fork needs the Prepatcher
  javaagent), Java 25 direct-prep and FR Java 28 prep. Its own FAIL lines become the AoTD baseline, so later group runs only
  report what a revived mod adds. Done when the AoTD baseline is recorded.
  **Closed 2026-11-19 (roadmap review): culled.** AoTD passes; owner 2026-11-17: AoTD is under an overhaul and can be ignored for now.
- 86.3 Environment pass 1, Java 28 direct (furthest from the original validation), code archives in groups, no AoTD. Done when
  every group is PASS or bisected to named mods.
  **Closed 2026-11-19 (roadmap review): superseded by 95.11 and 93.42.**
- 86.4 Environment pass 2, FR Java 28, same groups.
  **Closed 2026-11-19 (roadmap review): superseded by 95.11 and 93.42.**
- 86.5 AoTD pass: the code archives grouped with `--also-enable aotd` on Java 25 direct-prep; mods 86.1 ranks high-risk run
  first, in small groups (2-3), the rest in normal groups. Then FR Java 28 prep for the groups that passed. Done when every
  code archive has an AoTD verdict (PASS, FAIL with a named cause, or an accepted incompatibility recorded in its workspace).
  **Closed 2026-11-19 (roadmap review): culled.** AoTD passes; owner 2026-11-17: AoTD is under an overhaul and can be ignored for now.
- 86.6 Pre-patcher variants of passes 1-2 only for archives that patch game classes or depend on the Prepatcher.
  **Closed 2026-11-19 (roadmap review): superseded by 95.11 and 93.42.**
- Results go into each workspace's live record and gates.json; an archive is re-archived (`revise`) only when a fix is needed.
  New and revised mods are not part of this item: they get the `standard` bundle before archiving (85.1).
**S-series implementation (owner 2026-10-24: "plan S series implementation then proceed to start S1").**
[Implementation plan](docs/S_SERIES_IMPLEMENTATION_PLAN.md) translates S1-S4 into dependency-ordered slices. **S1 is complete and owner-accepted 2026-10-25 for the bounded RC8 local-new-game workflow**; [completion evidence](docs/S1_COMPLETION_REVIEW.md) and [progress/handoff](docs/S1_PROGRESS.md) retain the limits. Human active-review time is NOT_MEASURED in the accepted baseline. S2 baseline and S3 initial work retain their separate open delivery/acceptance gates; save upgrades, publication and S4 human/support commitments are not included.
**Owner 2026-11-17: "I'm not sure the S series is worthwhile now as the second user seems a bit extreme."** The "second
user" is S4's goal: a second operator who installs, reproduces, restores and supports the workflow
(docs/STRATEGIC_ROADMAP.md). Proposed for the owner's decision:
- Park S4.
- Stop treating S2 and S3 as gates.
- Keep the parts that serve the owner alone through the numbered items that already carry them: 95 (re-validating a new build
  from a catalogue), 93.30 (the scenario testbed), 94 (the feature genome) and the recipe and precedent work in 92 and 96.5.
- S1's accepted baseline stands as it is.
**Decided 2026-11-17 (owner: "Park S4. Stop treating S2 and S3 as gates.").** S4.1-S4.4 are parked. The local profile,
the private exchange kit and the fresh-workstation trial kit stay as they are, unused, and no second-operator trial is
awaited. S2 and S3 gate nothing. Their remaining work that serves the owner is queued as ordinary items in item 97.

**85. Automation and fewer tokens per task (owner-approved 2026-10-22).** From this session's hand work. Nothing below is
built yet; LIVE TEST NOT PERFORMED.
- 85.1 Live-batch command: `live-batch plan` turns LIVE_PENDING gates (`gates.json` needs, `board --live-pending` blocks) into
  a run plan; `live-batch run` performs it unattended (rig-up, probe-group live with the gate's launcher, report); `live-batch
  summary` writes a compact per-run verdict file with the next `record` / `baseline-accept` / `revise finalize` commands, and
  can notify when done. Replaces hand-written PowerShell runners (the 2026-10-22 runner skipped every run through a
  return-value bug). Done when the 2026-10-22 batch can be reproduced from gates.json alone.
  Environment bundles (owner 2026-10-22: "going forward we will need to bundle the various environments in live testing"):
  a named bundle is a list of launch environments (launcher, Java, pre-patcher on/off), e.g. `standard` = FR Java 25, FR Java
  28 and direct Java 28, each with and without the pre-patcher (the six-launch Ironclads matrix of 2026-10-22). A gate names
  a bundle instead of one launcher; `live-batch plan` expands it, stages each candidate once and runs it through every
  environment before moving on, and records the gate PASS only when every environment passes (per-environment results kept
  in the run records). Archive-eligible runs use the `standard` bundle unless the gate says otherwise.
  **Closed 2026-11-19 (roadmap review): superseded by 95.3.**
- 85.2 Refactor-review evidence: one command that produces item 83 section 6's evidence for a PR as JSON (test counts
  before/after, skips, coverage, CLI golden hash, rename similarity, wheel file list, Salvor suite against the branch). Done
  when a refactor PR's review reads that one file.
  **Closed 2026-11-19 (roadmap review): culled.** Evidence tooling for item 83's refactor, which is finished.
- 85.3 Workspace brief: one page per workspace (versions, changed files, open findings, accepted baselines, past live runs,
  earlier reviews and decisions such as reports/ASTRA_LIVE_REVIEW.md), printed before any investigation. Done when the EPTA
  Alicerce/narcepolis question would have been answered from the brief.
- 85.4 Crash intake: given a player's starsector.log and enabled_mods.json, name the failing mod and stack, match it to a
  workspace and propose the gate that reproduces it. Done when a recorded crash log is matched to its workspace and gate.
- Harness fixes from the same batch: BUGS.md LIVE-001 (report attribution), LIVE-002 (total conversions and the combat
  stage), LIVE-003 (pre-patcher drift), LIVE-004 (stale extras in rig copies).

**84. Feature tracing and transplanting (owner-approved 2026-10-22; long term).** Goal: BridgeForge can pick a mod apart and
trace every feature end to end (data ids, assets, code, hooks, runtime behaviour), and can transplant a named feature from one
mod into another with its dependencies, id remapping, conflict and save checks, live validation and recorded provenance. Design
note: [docs/FEATURE_TRANSPLANT_PLAN.md](docs/FEATURE_TRANSPLANT_PLAN.md). Rules: bytecode stays authoritative and decompiled
code is a reading aid; no research finding becomes a migration or transplant rule automatically (item 82's sequence: finding ->
validated pattern -> candidate -> approved rule); a gate is never upgraded without recorded evidence; starts after item 83's
refactor (B3 at least), because T0 depends on the package layout. Nothing below is built; LIVE TEST NOT PERFORMED.
- T0 Feature graph. Builds one queryable per-mod graph joining every id (hull, weapon, hullmod, ship system, faction, market,
  rules.csv entry, sprite, sound, string) to the code that creates, reads or registers it, and to what calls that code.
  Reuses Atlas (census, classfile, exemplars), the D-series (archaeology, behavior-map) and scanner facts, merged per concept
  as item 82.2's reconciliation decides; the 82.8 method map. Done when `research report` answers questions from the graph
  instead of by re-scanning.
- T1 Feature boundaries. Builds the named-feature record: its files, classes, ids, memory keys, scripts, listeners and hook
  points, produced by `research report` and stored as a reviewable record. Reuses T0, `research report` (82.1), REMOVALS
  records. Done when the Templar Crusade and SEEKER station modules each have a boundary record a person agrees with.
- T2 Runtime trace. Builds probe stages that confirm a feature's entry points and hooks fire, with the evidence linked back
  into the graph (STATIC -> OBSERVED). Reuses the probe mod, `probe-group live`, live records, gates.json scheduling and
  `board --live-pending`. Done when one feature's hooks are OBSERVED in a recorded run.
- T3 Data-only transplant. Builds dependency closure (assets, CSV rows, settings keys, library dependencies), id and
  namespace remap, a collision check against the target, and install into a target workspace through `revise`. Reuses
  scanner id indexes, content parity, `revise prepare/finalize`, the archive gate. Done when one EPTA ship line moves into a
  test mod, then builds, boots and passes a live gate.
- T4 Code transplant planning. Builds the plan for code-backed features: decompile the feature's classes, remap packages,
  list the hook points to adapt (ModPlugin onNewGame/onGameLoad, listeners, rules.csv, economy) and rebuild against the
  target's classpath. Reuses `decompile-jar`, 82.7-82.9 (readable code, method map, `research diff`), `rebuild-jar`,
  `bytecode-inspect`. Adapting the hooks is human or agent work that BridgeForge checks; never automatic. Done when one
  code-backed feature is transplanted into a test mod and passes a live gate.
- T5 Save safety. Builds the answer to what an existing save needs when a feature is added or removed. Reuses the save tools
  (save-doctor, save compatibility, fingerprints), migration packs (docs/MIGRATION_PACK_CONTRACT.md), REMOVALS and
  `revise migration`. Done when adding and removing the T4 feature both load an existing save cleanly in a live run.
- T6 Provenance and permission. Builds a provenance record for every transplanted file: source mod, version, file hash,
  author and licence. Reuses release_policy.json and the archive gate; without the author's permission the result stays
  LOCAL_ONLY. Done when the archive gate refuses a transplant with missing provenance.

**83. Structural refactor across the repos (owner-approved 2026-10-22).** Reorganisation only, no behaviour change: BridgeForge's
flat 291-module package into subpackages, `fixers.py` split, docs/roadmaps consolidated, command audit and grouping with aliases,
test-speed split; Project Go GUI shell split; optional VoidSmith splits; Salvor import updates. Plan, rules and review evidence:
[docs/REFACTOR_PLAN_2026-10.md](docs/REFACTOR_PLAN_2026-10.md). Executed by a separate agent; each PR reviewed against its section 6.

B0 implementation checkpoint 2026-10-22 (merged in PR #64, `f252b033`): recursive source inventories, package-relative
audit/fingerprint identities and nested test selection are implemented. Covered by
[tests/test_source_paths.py](tests/test_source_paths.py) and the existing audit/registry/merge-train tests;
2,602 tests, OK (12 skips unchanged), hermeticity PASS, coverage 83.06% (baseline 82.46%).
CLI golden/generated docs unchanged. Search inventory, fingerprint refresh and later move obligations:
[docs/REFACTOR_B0_AUDIT.md](docs/REFACTOR_B0_AUDIT.md). B1 onward remains pending; LIVE TEST NOT PERFORMED.

B1 implementation checkpoint 2026-10-22 (owner-approved after review fixes; merge pending CI): earlier roadmap pages and the completed October 18
audit moved to [docs/archive/](docs/archive/README.md); ROADMAP-3 is the active backlog. Archive navigation and current
entry points are repaired; the still-cited architecture assessment stays current. Legacy roadmap-lint paths still check
all 336 item keys with the unchanged evidence baseline, covered by tests/test_roadmap_lint.py.
Validation: 2,603 tests, OK (12 skips unchanged), hermeticity PASS; coverage 83.07%; gates lint has zero contradictions.
Companion citation PRs: [VoidSmith #13](https://github.com/Exxec/Project-VoidSmith/pull/13),
[Salvor #12](https://github.com/Exxec/Project-Salvor/pull/12), [Go #10](https://github.com/Exxec/Project-Go/pull/10).
Review fix: root numbering resumes after the archived page count, preserving future ROADMAP-4.md and later pages;
the relocation test detects an unevidenced Done claim on page 4. Companion follow-ups use the stable hardening plan
and merge after B1 (the original citation PRs were already merged).
No pending owner/live/research gate is closed by this archive step.

B3 checkpoint 2026-10-23: research independently rechecked (78 tests); Atlas continued in an isolated
review worktree, 2612 tests, 12 unchanged skips, coverage 83.1088957%, hermeticity PASS.
See [Atlas evidence](docs/REFACTOR_B3_ATLAS_AUDIT.md) and [stack](docs/REFACTOR_STACK.md).
Review/merge and remaining B3 families are pending; LIVE TEST NOT PERFORMED.

B3 corpus checkpoint 2026-10-23: six modules moved with import-only AST changes, 2612 tests,
12 unchanged skips, coverage 83.1088957%, hermeticity PASS; Salvor 208 tests (4 unchanged skips).
See [corpus evidence](docs/REFACTOR_B3_CORPUS_AUDIT.md). Local dependent branch only; escalation
is the next family. B3 and owner review/merge remain open; LIVE TEST NOT PERFORMED.

**B3 implementation checkpoint 2026-10-23:** all planned families now live in subpackages on the local stacked branches,
with consumer facades and preserved history. Full per-family suites, coverage, CLI, wheel and installed Salvor checks pass.
See [completion evidence](docs/REFACTOR_B3_COMPLETION.md) and [stack](docs/REFACTOR_STACK.md).
Owner review/merge, B4-B6 and all live gates remain open; LIVE TEST NOT PERFORMED.

B4/B5 checkpoint 2026-10-23: owner chose to retain the current CLI; grouping/deprecations declined. B5 fast/slow unittest CI partitions implemented and locally validated; [evidence](docs/REFACTOR_B5_TEST_SPEED.md). Owner review/merge, hosted CI and B6 remain open.

**82. Research that serves revivals: consolidate, compare, promote (owner-approved 2026-10-21).** Not a new research
architecture. S1 stays the critical path; runtime evidence is the limiting resource. Guiding rule: every research
capability must resolve a question from an active revival, eliminate repeated manual investigation, or improve the
reliability of existing evidence. Success criterion: a real question that previously needed manual inspection of several
mods is answered by `research report` with the relevant evidence, contradictions and next test, without invented
conclusions.
- P0 82.1 Comparative research report, read-only, with a question contract:
  `research report FEATURE --case WORKSPACE --question TEXT`. Answers: what feature, which mods implement it and how,
  which similarities/differences are supported, which conclusions remain hypotheses, which experiment (or existing gate)
  would resolve the important unknowns. Every claim carries STATIC / OBSERVED / VALIDATED and its evidence location.
- P0 82.2 Evidence reconciliation before any merge of code: the report consumes Atlas (census, exemplars, migrations)
  and the D-series (archaeology, behavior-map, hypotheses, probe-baseline/behavior-diff) independently and tabulates
  agreement: both detect (corroborating static evidence, not independent validation: same code), Atlas only
  (D-series coverage gap?), D-series only (Atlas blind spot?), both but different (semantic disagreement). Disagreements
  stay as evidence; the counts become the basis for deciding later which stack is authoritative per concept.
  - 82.1 and 82.2 progress 2026-10-22: `research report FEATURE --case WORKSPACE --question TEXT [--write DIR]` implemented
    (`bridgeforge/cmd_research.py`, `research_*.py`; `tests/test_research_report.py`, synthetic fixtures only). Read-only (the atlas
    database is opened `mode=ro`, `--write` inside the workspace is refused). Reuses `atlas.index_mod`, `atlas_migrations.mine`,
    `lookup.load_graph`, `behavior_discovery.build_behavior_model`, `dropped_sweep.check_workspace`, `removals`, `live_ledger.read_runs`
    and `gates.load_gates`. Missing inputs are listed with the producing command; archaeology is built in memory (about 25 s per tree)
    unless `--no-build`. A root-level `reports/` folder of a tree is BridgeForge's own output and is excluded from concept evidence.
    First pilot (Templar Crusade, 82.3 groundwork): `bridgeforge-state/research/templar-crusade/` (git-ignored).
- P1 82.3 Active-case pilots: Templar Crusade first (removed vs replaced vs redistributed vs re-created: the
  semantic-classification problem behind the dropped-feature false positives), then SEEKER station modules (does the
  workflow generalize). Stopping condition per investigation, e.g. Templar is complete when the report identifies the
  relevant Crusade implementations, explains the apparent feature changes, lists unresolved differences and ties each
  needed runtime test to an existing gate. No need to explain every class.
- P1 82.4 Knowledge promotion: extend existing records (R4 standing rulings, the RC8 behaviour facts, REMOVALS,
  exemplars) with status STATIC / OBSERVED / VALIDATED, an applicability predicate, supporting evidence, counterexamples
  and invalidation conditions, so the question "does this still apply here?" can be answered. The statuses are not a
  ladder: an API-signature claim can be VALIDATED from authoritative static evidence; a fleet-spawning claim needs
  runtime evidence. VALIDATED means a defined acceptance test, including negative cases, within a declared scope.
- P2 82.5 Runtime scheduling: research experiments are gates in `gates.json` (needs.scenario), so `board
  --live-pending` batches them with revival gates in the same rig sessions.
  **Closed 2026-11-19 (roadmap review): already built.** `gates.py` takes `scenario` needs.
- Later 82.6 Active research selection, once there is enough empirical data to measure uncertainty against; corpus
  acquisition (multiple releases of the same mods) for version timelines.
  **Closed 2026-11-19 (roadmap review): culled.** Speculative ('once there is enough empirical data'); no consumer.
- P1 82.7 Readable code in research reports (2026-10-22). `decompile-jar` (Vineflower 1.12.0) and `rebuild-jar` exist but
  serve revisions only; research reads class files directly (`atlas_classfile`). `research report` decompiles the classes
  a question touches into git-ignored `bridgeforge-state/research/<case>/decompiled/<jar-sha256>/`, records the jar hash
  and Vineflower version, and quotes the relevant methods. Bytecode stays authoritative; decompiled Java is a derived
  reading aid (STATIC), never evidence of runtime behaviour, never copied into a mod.
- P2 82.8 Method link: run Vineflower with bytecode-source mapping so each decompiled line range maps to the
  `class#method descriptor` that `bytecode-inspect` and Atlas use; a finding made in readable code points at the exact
  bytecode method, and vice versa.
- P2 82.9 Readable version diffs: for a migration pair, diff the decompiled text only of methods whose bytecode changed
  (`bytecode-diff` decides what changed; the decompiled diff explains it). No second decompiler (CFR) until two readings
  of one method disagree in a way that matters; Recaf stays a manual tool.
  - 82.8 and 82.9 progress 2026-10-22: Vineflower 1.12.0 options `-bsm=1` (bytecode-source-mapping) and `-dcl=1` (dump-code-lines) give
    (original line, decompiled line) pairs, but only in the extra field of an archive entry and only when the input is an archive too, so
    `research_decompile.run_vineflower` packs, decompiles and unpacks a temporary jar. `research_methods.py` joins the pairs with the bytecode
    helper's per-method line tables into `<class>.methods.json` (`a/b/C#name descriptor` -> decompiled range, else UNMAPPED with the reason) beside
    the cached `.java`; `lookup_line` and `lookup_identity` go both ways. `research diff OLD NEW` (a `research` subcommand: it shares the
    decompiler cache and `--write` rules of `research report`) uses `bytecode_diff.changed_methods` (per-method body digest) to pick the methods
    and diffs only their decompiled text. Tests: `tests/test_research_diff.py`. Limits found: a constructor Vineflower hides, or a method without a
    line table, is UNMAPPED; a compiler or debug-info change shows as a bytecode change whose decompiled text is identical (SAME_TEXT) or differs in
    local variable names only.
- P1 82.10 Release inventory as a command: `corpus releases ROOT...` scans folders and .zip/.7z/.rar archives for
  mod_info.json, writes releases.csv and RELEASES.md (copies per mod id, versions, game versions, forum thread and repo
  links from .version files) and a pairs queue for `atlas migrations --pairs-from`. Replaces the 2026-10-22 one-off
  script (`bridgeforge-state/release-inventory/`: 718 mod ids, 200 with two or more versions) and starts 82.6's corpus
  acquisition now.
  **Closed 2026-11-19 (roadmap review): already built.** `corpus/corpus_releases.py`, `bridgeforge corpus releases`.
- P2 82.11 Author changelogs as hints: parse the changelog shipped in each mod release (CHANGELOG.txt, changelog.md and
  similar) per version; `research report` quotes lines naming the feature, labelled AUTHOR CLAIM (weaker than STATIC:
  what the author says changed, not what the code shows). For Templar, a changelog line saying the Crusade moved or was
  cut is the fastest hint to confirm or refute in code.
  **Closed 2026-11-19 (roadmap review): already built.** `research/research_changelog.py` (AUTHOR CLAIM).
- P2 82.12 Old game API: `api-diff` and `api how` need an older `starfarer.api.jar`. Owner: locate old starsector-core
  installs (0.95.1a, 0.96a, 0.97a); then run `api-diff` once per step to RC8 and let `research report` and `atlas
  migrations --old-api/--new-api` use the results, so migration proposals rest on the authoritative API change, not
  only on mod-pair co-occurrence.
- Prohibited: a research conclusion never turns into a migration rule automatically. Sequence: research finding ->
  validated pattern (conditions) -> migration candidate (can it safely guide an intervention?) -> approved deterministic
  rule (explicit approval, safety checks, regression evidence). Learn API patterns from other mods, never copy their code
  without the usual attribution and permission rules.

**80. Less hand work across the projects (owner 2026-10-21: "work them all in your preferred order").** Order: 80.1, then
80.2 with 80.6, 80.3, 80.5, 80.4, 80.7, 80.8.
- 80.1 **Built offline, merged (#41, #47, #51, #53); live pending where it needs the rig.** Merge-friendly changes: `changelog.d/` fragments assembled at release (no PR edits CHANGELOG.md); generated files
  (CLI golden, COMMANDS.md, CHECKS.md) regenerated on conflict or by CI; pre-push runs the cross-cutting tests (probe
  contract, safeio ratchet, docs index, CLI golden) plus the tests of touched modules; a `merge-train` command.
- 80.2 **Built offline, merged (#43); live pending where it needs the rig.** Rig-session planner: `board --live-pending` gathers pending live gates from every repo, groups them by rig
  configuration and prints one session plan with commands; results are written back as PASS/FAIL/NOT_TESTED (with 79.7).
- 80.3 **Built offline, merged (#45); live pending where it needs the rig.** Archive gate wired: `archive` and `revise finalize` run dropped-features, content parity and the orphaned-backup
  check and refuse unexplained drops; a passing live run with probe 0.3.x offers `archive --refresh`.
- 80.4 **Built offline, merged (#44); live pending where it needs the rig.** `decision apply DRAFT` (77.20): ticked boxes become baseline keys, REMOVALS entries, roadmap lines and rig steps.
- 80.5 **Built in Salvor, merged (Project-Salvor PR #7); first nightly pin PR not yet observed.** Pin autopilot: Salvor tests nightly against BridgeForge main and opens a pin-bump PR when green; shared-fixture
  drift with Project Go turns blocking once Project Go updates.
- 80.6 **Built offline, merged (#43); live pending where it needs the rig.** Status generated from `gates.json` per repo (R7): status tables and the rig plan come from it; a lint fails CI when
  a status doc contradicts it.
- 80.7 **Built offline, merged (#46); live pending where it needs the rig.** Review triage: VoidSmith's 726 calibration rows and BridgeForge's escalation packets grouped by the reason they
  wait, so one decision clears a group.
- 80.8 **Built offline, merged (#48); live pending where it needs the rig.** Agent hygiene preflight (77.13): untracked code, unexpected edits to tracked files and broken builds listed before an
  agent session ends or a commit is made.
- 80.9 **Built (PR pending merge, pairs with Project Go H3); hosted CI proof is this PR's own run.** Real-manifest contract check (2026-10-22): next to the shared-fixture comparison, CI imports
  an actual coverage manifest exported by Project Go from a fixture mod, so a producer change that breaks the consumer
  fails CI instead of being found by hand.
  **Done (merged as #60); closed 2026-11-19.** Found by the live-pending sweep: the PR this line waited for is merged, and its
  CI run was the hosted proof.

**81. Dissection: research from current mods (owner 2026-10-21: "throw current mods at bridgeforge and see if we can
glean more research").** Read-only over the player's installed mods and any folder given, built on `atlas`, `api-diff`,
`corpus-index` and `provider-index`; every result is labelled STATIC (what code references, not what runs).
- 81.1 **Built offline, merged (#42); live pending where it needs the rig.** API usage census: which RC8 API classes/methods each mod's jars and loose scripts call; `api how SYMBOL` links an
  `api-diff` removal to the replacements working mods use, with example files.
- 81.2 **Built offline, merged (#50); live pending where it needs the rig.** Migration mining: where two versions of a mod exist, cluster the API replacements between them into candidate
  rewrite rules with a count of independent mods (R4 needs three before a ruling).
- 81.3 **Built offline, merged (#42); live pending where it needs the rig.** Save-risk census: persistent-data keys, scripts added on every load (duplicate-script risk), readResolve, transient
  fields, per mod.
- 81.4 **Built offline, merged (#42); live pending where it needs the rig.** Library census: LazyLib, MagicLib, GraphicsLib and other library calls and the versions they need.
- 81.5 **Built offline, merged (#50); live pending where it needs the rig.** Feature exemplar index: working implementations of raids/FGIs, intel, custom entities, rings, station modules,
  for recreation work.

**Hygiene review 2026-10-19 (owner: "perform hygiene check then check roadmap for any worthwhile additions. implement if able then commit/push").** Item 77.3's lock-test timeout is implemented: the three live psutil scans query only their real fixture PIDs in a disposable subprocess with a 30-second timeout; fixture-child shutdown also has a deadline and kill/reap fallback. A regression verifies timeout propagation as a failure. Focused validation: 11 tests pass. This bounds test execution, not the production `who-locks` command, and supplies no game evidence. See `tests/test_locks.py`.

**78. Probe enhancements (owner 2026-10-20: "add and work them all").** The probe proves boot, id resolution and
combat, but missed a whole missing rules.csv (FIX-001), never proves a save reloads (R6 has no emitter, Project Go's
SAVE_RELOAD stays NOT_TESTED) and needs hand-written hooks per feature. In work 2026-10-20, offline (LIVE TEST NOT
PERFORMED until the next rig session):
- 78.1 Manifest id echo: the probe logs the run manifest id first; the evaluator refuses a mismatch (R1 trust).
  **Closed 2026-11-19 (roadmap review): already built.** the probe echoes the run's manifest id first (`graceful_exit.py`, `probe-mod`).
- 78.2 Save-and-reload fingerprint: per-mod sector fingerprint before `cmdSave()` and after reload, compared; sets
  `milestones.reload_after_save` only when observed equal; becomes R6's in-game evidence emitter and covers SEEKER SK-6c
  and part of Salvor R4.
  **Closed 2026-11-19 (roadmap review): already built.** `save/save_fingerprint.py`; `reload_after_save` in `probe/cmd_probe_group.py`.
- 78.3 Live content parity (77.17): per-mod loaded counts against counts taken from the candidate before launch.
  **Closed 2026-11-19 (roadmap review): already built.** `live/live_content_parity.py`.
- 78.4 Declarative per-mod scenarios: `reports/PROBE_SCENARIO.json` (settings for the rig copy, steps, expected log
  lines with deadlines), so rig steps 13-15 and future recreations need no probe code.
  **Closed 2026-11-19 (roadmap review): already built.** `probe/probe_scenario.py` (`reports/PROBE_SCENARIO.json`).
- 78.5 One probe: fold Salvor's `salvor_rig_probe` load/save/day stages into this probe as a `salvor` profile (after
  78.2 lands); Salvor's `rig-build-probe` builds that profile.
  **Closed 2026-11-19 (roadmap review): already built.** `probe/probe_salvor_profile.py` and the probe's `SalvorProfile`.
- 78.6 Clean exit: the probe writes a done marker; the harness closes the window and records a natural exit by default.
  **Closed 2026-11-19 (roadmap review): already built.** `graceful_exit.py`: done marker, then WM_CLOSE, natural exit recorded.
- 78.7 "What was exercised" per mod; a mod with nothing exercised is flagged HOLLOW.
  **Closed 2026-11-19 (roadmap review): already built.** `exercised.py` (HOLLOW).
- 78.8 Campaign frame time under load per day (`campaign_perf`), for the Crusade and SPW.
  **Closed 2026-11-19 (roadmap review): already built.** `campaign_perf.py`.

**79. Same treatment for other components (proposed 2026-10-20).** The probe gaps have counterparts elsewhere:
- 79.1 Scanner coverage report: per mod, which checks actually ran on which files (a scan can be as hollow as a probe
  run); unread file types listed instead of silently skipped.
- 79.2 Offline save fingerprint: Salvor and VoidSmith compute the same fingerprint sections from a save's XML, so a
  repaired or edited save can be compared with the probe's in-game fingerprint (78.2) and with its own original.
  **Closed 2026-11-19 (roadmap review): already built.** `save/save_fingerprint_offline.py`.
- 79.3 VoidSmith Save Workshop: every written copy carries an expected-fingerprint file; the probe's reload compares
  against it, closing "one Workshop copy loaded in game" and the capacity recompute question in one run.
  **Closed 2026-11-19 (roadmap review): culled.** A VoidSmith feature; belongs in that repository's plan.
- 79.4 Duel, raid and capacity sub-mods: the same manifest echo, done marker and scenario format as the main probe.
- 79.5 Project Go assurance import: read the new record blocks (fingerprint, content parity, scenario, exercised) as
  gate evidence; a HOLLOW member never passes CAMPAIGN.
  **Closed 2026-11-19 (roadmap review): culled.** A Project Go feature; belongs in that repository's plan.
- 79.6 SPW: map `campaign_perf` and combat-perf into `performance-report.json` so revivals carry a performance
  baseline (SPW roadmap item 5).
  **Closed 2026-11-19 (roadmap review): culled.** An SPW feature; belongs in that repository's plan.
- 79.7 **Built offline, merged (#49); live pending where it needs the rig.** Rig harness: one launcher path (probe-group live, bf-test.ps1, boot-test) with the same manifest, exit and
  done-marker handling, instead of three.

**Owner follow-ups 2026-10-20 ("add both to roadmap. We should reassess other mods to see if they dropped any features").**

**77.14 Accept a single finding outside a packet.** `escalation accept` only matches findings already in an escalation
packet, and `scan --write-baseline` accepts every current finding at once. The Templars 0.9.8f `port-dropped-feature`
acceptance had to add its three keys by hand with `baseline.finding_dict_baseline_key`. Add `baseline-accept-finding
<workspace> <FINDING_ID[:FILE_PART[:EVIDENCE_PART]]> --reason` that adds only the matching keys, writes the reason to
`reports/ESCALATION_REVIEW.md` like `escalation accept`, and refuses when nothing or more than the named findings match.

**77.15 Templars Requisitions submarket (proposed recreation).** `TEM_MarketPlugin` ("Requisitions": the Templar
requisitions center, a MilitarySubmarketPlugin with Templar-only stock and commission rules) existed in 0.9.8f and was
removed upstream in 0.9.9e together with its `submarkets.csv` row, so the Templars 0.9.8f port lost it by inheriting the
newer base, not by a BridgeForge change. Owner decision pending: re-create it for RC8 (like the Crusade, a separate
`jars/` class plus the data row) or accept the upstream removal. `TEM_Radiated` (the Irradiated World condition) was
removed the same way and has no gameplay worth restoring unless a world uses it.

**77.16 Dropped-feature sweep across the queue (2026-10-20, report-only).** `scan_port.dropped_features(old, new)` was run
against each workspace's `original/` download (308 of 316 had one; local report in the session scratch,
`dropped-sweep/SWEEP.md`). Results: 19 workspaces with dropped items, 38 with port wording but no drops, 59 with only
strip/remove wording, 200 with nothing. Reviewed so far:
- **All the Domain Drones: real loss, shipped (BUGS.md FIX-001).** The whole `rules.csv` (430 triggers) is missing
  from `working/` and from both archived zips; only the fixer backup remains.
- **Yunru family (7 workspaces, 119 classes each): false positive.** Each `original/` holds the whole 9-part Yunru Core
  pack, so one part's working copy looks like it dropped the other eight. The sweep must compare with the matching
  sub-folder.
- **Templars 0.9.8f:** the known Crusade loss, which confirms the check works.
- Still to review by a person: Xenoargh AI Overhaul (53 classes) and FX Core (52), likely the owner-approved fold into
  RevenantLib; Ironclads (4 classes, 25 rules.csv triggers); SEEKER (5 classes); Better Deserving S-mods (4 classes);
  Mirfak Parcel Service (3 settings, 1 rule); and the remaining rows. Next: make the sweep a command (`dropped-features
  --queue`) that matches sub-folders, records intended removals (strip plans, RevenantLib folds) so they stop showing,
  and runs before `archive`; then review the remaining rows. Every confirmed loss gets a BUGS.md entry and a recreation
  or restore item.
- Built 2026-10-20: `dropped-features WORKSPACE | --queue DIR [--write DIR]` (old tree: PORT_SOURCE, else the
  `original/` mod root with the same mod id, else the only root, else UNDETERMINED) and `reports/REMOVALS.json` (77.19).
  Real queue: 11 DROPS_UNEXPLAINED, 9 UNDETERMINED, 296 CLEAN; all Yunru parts CLEAN; All the Domain Drones CLEAN after
  the FIX-001 restore. Unexplained to review: Xenoargh AI Overhaul (53 classes), Xenoargh FX Core (52), Templars 0.9.8f
  (31, decided), Ironclads (4 classes, 25 rules), SEEKER (5), Better Deserving S-mods (4), Mirfak Parcel Service (4),
  AI-War (2), Blackrock Drive Yards (2 settings), Maelstrom Imperium Unofficial Expansion (2). Not yet run before
  `archive`; strip and fold emission into REMOVALS.json waits for the code that applies a strip or retires a folded mod.

**Automation, gap coverage and hand-work reduction (proposed 2026-10-20, owner: "if there is further automation, gap
coverage or things to make hand work easier please add to roadmap").** Each closes a gap this session hit by hand.

**77.17 Live content parity (gap that let FIX-001 ship).** A LIVE_VALIDATED run proved boot and campaign load while the
mod's whole `rules.csv` was missing. Extend the probe's `content-ids` milestone to count what the game loaded per mod
(rules triggers, hulls, weapons, wings, industries, conditions, submarkets, planets/systems added) and compare with
counts taken from the candidate's `working/` data before launch; a shortfall FAILs the run with the missing ids.

**77.18 Archive content parity.** `archive-preflight` compares the archive's file list with `working/` and with
`original/` (by sub-folder for multi-mod packs): a data or script file in `original/` and absent from the archive needs a
recorded removal (77.19) or the archive is refused. Run `done-audit --content-parity` once over all 160 `Done/`
archives; each confirmed loss becomes a BUGS.md entry.
- Windows portability follow-up, 2026-10-20: resolve tool-owned materialization paths before guarded cleanup, and mark
  comparison errors UNDETERMINED rather than CLEAN. Both aliased-temp and failed-comparison regressions were reproduced
  before the fix; `tests.test_content_parity` covers them. Full suite: 2,314 tests, zero failures, 13 skips; hermeticity PASS.
- First pass done by hand 2026-10-20 (owner: "run a scan over all archived mods including ironclad"; static, offline;
  each shipped zip against its own `original/`; local report `done-audit/DONE_AUDIT.md` in the session scratch).
  154 folders: 124 CLEAN, 20 REVIEW, 5 LOSS_SUSPECTED, 5 UNDETERMINED; no `.bak` or orphaned fixer backup shipped.
  - **All the Domain Drones 0.6: real loss** (FIX-001; restore done in `working/`, live run and refresh pending).
  - **Templars 0.9.8f:** decided 2026-10-20 (Crusade re-created; reports/submarkets/console CSVs follow 0.9.9e).
  - **Roider Armatura 0.2: intended retirement, unrecorded.** The Dragline (ship, variant, `ship_data.csv` row,
    IndEvo whitelists, title-screen variant) was moved together to `scratch/retired/`; nothing shipped references it;
    its sprite was left in `graphics/`. Needs a REMOVALS.json entry with the reason, and the sprite removed or kept.
  - **SEEKER 0.3.0: owner decision needed.** The shipped mod lacks the "twig" campaign subsystem (5 classes:
    `SKR_PersistentRoot`, `SKR_PersistentRootShip`, `SKR_CampaignTWIGEntity`, `SKR_TwigCampaignTracker`, `MemKeys`), the
    `ART_dimention_armor` weapon and `data/config/twig/`. The workspace escalation flagged the persistent-root class as
    save-risky; no record says the removal was decided. Compare with `Done/SEEKER-0.6` before deciding.
  - **Ironclads v.11+bf.1: intended (REVIEW).** SystemBountyEvent replaced by RC8's SystemBountyManager (owner's
    faithful-route decision 2026-10-04); FleetSpawner/TimeManager dead code reachable only through Barnard, whose
    generation was already commented out in the original. The 25 rules.csv triggers come from cutting a 0.7 vanilla
    copy of rules.csv down to Ironclads' own 170 rows; most have the same id in RC8, about 16 do not (comm-relay
    sniffer, `dialogHegRelayInterference_*`, `cargoScanSuspicious`, `flavorTextMarketUmbra`) and were not reviewed one
    by one: owner confirmation advised. REVIVAL_PLAN says FleetSpawner/TimeManager were "left as shipped" but they are
    not in the zip (doc fix). The zip ships a stale `jars/IroncladsEcon - копия.jar` (remove on the next refresh).
  - REVIEW, likely intended: Xenoargh AI Overhaul (53 classes) and FX Core (52), the RevenantLib fold; EPTA Consortium
    (36) and 2.1.3 (14), Nomads (3), Neutrino 1.8.9 and Nostalgia (2 each), Another Random SWP and Tritachyon (1);
    source-only omissions (Flu-X, Bricky Construction, RevenantLib `.java`); junk shipped (`.old`, copy files) in
    Broken Star, Exigency 0.8, Jackundor's Advanced Arms, Leon Heavy Industries, Maelstrom Superweapons (older), Sylphon,
    Neutrino 1.8.9.
  - UNDETERMINED: Arkgneisis (`ArkLeg_dev`), BF-Legacy-Fleets, Nightcross, Omega Trauma (no original with the shipped
    id); Station Augments 2.4.3+bf.1 has no zip and no ARCHIVE_NOTE.
  - Next: write REMOVALS.json entries for the intended rows so they stop showing; add the junk-file and
    copy-of-jar check to `archive-preflight`; turn this pass into `done-audit --content-parity --write DIR`.
  - **Resolved the same day (owner decisions 2026-10-20; REMOVALS.json written in each `working/reports/`, local):**
    - SEEKER: the "twig" classes were adapters for the external Twig Library, which no longer exists; the Betelgeuse was
      already rebuilt on vanilla station modules (`docs/fable-solutions/SEEKER-twig-to-ship-modules.SOLUTION.md`,
      2026-09-09). Owner accepted it as re-created; per-segment supply drain, repair rates and 50% revive left out
      (can be re-added later; `In operation/SEEKER/working/reports/TWIG_RECREATION_PLAN.md`). Module save/reload check
      is LOCAL_HANDOFF 0b item 15.
    - Ironclads: all 25 dropped triggers (161 rows) verified as the 0.7 vanilla copy, 0 Ironclads-specific, none
      restored; the 33 per-system world scripts were never generated in the original either (its SectorGen.java
      comments out all but Lomonosov, Shington, Nexus and Centronom). The stray `IroncladsEcon - копия.jar` moved out
      of `working/`. Now EXPLAINED 87/87.
    - Xenoargh AI Overhaul and FX Core: lombok runtime classes stripped (no shipped class references `lombok/`), and AI
      Overhaul's own TravelDriveStats replaced by vanilla's. Not a RevenantLib fold.
    - Better Deserving S-mods (dead code upstream), AI-War (superseded upstream by AIW_*), Maelstrom Imperium Unofficial
      Expansion (copies of its dependency's classes), Mirfak/Blackrock/Seafood (design-type keys renamed by the English
      translation; Mirfak's "rule" was a comment row): all EXPLAINED. Roider's Dragline is file-level, which REMOVALS
      does not cover yet (77.19 extension: a `files` category).
    - Queue now: 1 DROPS_UNEXPLAINED (Templars 0.9.8f: exactly the open C4 reputation stages and the console command),
      9 UNDETERMINED (no original with the shipped id), the rest EXPLAINED or CLEAN.

**77.19 Recorded removals.** Strip plans, RevenantLib folds, renamed ids and upstream removals (Templars 0.9.9e) write one
line each to `reports/REMOVALS.json` (item, reason, decision source). The dropped-feature sweep (77.16), archive parity
(77.18) and the escalation sheet read it, so intended removals stop showing and unexplained ones stand out.

**77.20 Apply an owner decision draft.** Decisions are drafted as Markdown with checkboxes and then applied by hand
(baseline keys, the reason in ESCALATION_REVIEW.md, ROADMAP_STATUS and LOCAL_HANDOFF lines). `decision apply DRAFT`
reads the ticked boxes from a structured block in the draft and performs the matching actions (77.14 accept, schedule a
roadmap line, add a rig step), printing what it changed. Unticked boxes do nothing.

**77.21 Natural exit everywhere.** `tools/bf-test.ps1 launch` and `boot_test` still end the game with `taskkill /T /F`;
route them through `exit_observation` so every live record can carry NATURAL/KILLED, not only `probe-group live
--natural-exit`.

**77.22 Evidence queue and rig-session planner.** `board --live-pending` gathers every LIVE PENDING / NOT_RUN gate from
BridgeForge, Salvor, VoidSmith, SPW and Project Go status files (via a small machine-readable gate list per repo, R7),
groups them by rig configuration (install, Java, launcher, LunaLib, enabled set) and prints one session checklist with
the exact commands. Today the checklist is assembled by hand from five roadmaps.

**77.23 Shared fixtures stay identical and line-ending proof.** The runtime-context fixture hash failed on Ubuntu CI
because the Windows working copy had CRLF. Mark hashed fixture trees `-text` in `.gitattributes` (both here and in
Project Go), and add a CI job that fetches Project Go at a pinned commit and fails when the shared
`fixtures/translation-conformance` and `fixtures/runtime-context` differ by a byte.

**77.24 Post-write verification for every backing-up writer.** FIX-001's guard (a written file must exist with the planned
bytes, else stop with the backup kept) applies to `relink`, `patch-jar-class`, `translate-apply`, `revise finalize` and
archive staging too; one shared helper in `safeio` and a ratchet test like the safe-write one.

**77.25 Pre-commit lints what is committed.** The pre-commit hook runs `ruff check .` over the whole folder, so untracked
agent scratch blocks unrelated commits (2026-10-20 needed `.gitignore` entries). Lint the staged and tracked files in the
hook and leave whole-directory lint to 77.13's preflight report. Also track `tools/precommit-check.ps1` and
`tools/prepush-check.ps1`: `/tools/*.ps1` ignores them, so worktrees and fresh clones get hooks that call a missing script.

**77.26 Test hermeticity: reference-rig manifests.** `test_shadow_triage...test_without_a_reference_core_the_fixer_behaves_as_before`
passes in a fresh worktree and fails in the owner's checkout, because `reference_rigs.reference_core_for_game_version`
reads the repository's local, ignored reference-rig manifests. Tests must pass `repo_root` (or a fixture root) so local
rigs cannot change their result; the suite's existing "Test hermeticity FAIL" check should catch this class.

**77.27 Hand removals leave a record (FIX-001's cause).** Files moved into hand-made `scratch/removed/` folders
(All the Domain Drones' repaired rules.csv, Aivon's special_items.csv, Yellowjackets' tpc.wpn) carry no reason, so a
mistaken move shipped. Add `remove WORKSPACE PATH --reason` that moves the file to `scratch/removed/<date>/`, writes a
`REMOVALS.json` entry (77.19) and refuses when the path is a data file the mod's own content references without a
replacement; `fixer-backup-orphaned`'s sibling check flags any `scratch/removed/` file without a REMOVALS entry.

**77.13 Proposed hygiene preflight (S4 supportability; scope/design still pending).** This audit found 21 Ruff errors in pre-existing untracked agent scripts, including syntax errors, while the isolated tracked checkout passed Ruff. Add a read-only preflight that reports tracked modifications, untracked code, ignored local evidence, interpreter/dependency availability and separate tracked-tree versus whole-directory lint results. It must never delete/move files, suppress whole-directory failures, stage unrelated work, or traverse private mod/save inputs. Reuse Git's file inventory and Ruff rather than inventing a second linter. Validate on synthetic dirty/untracked/ignored fixtures, filenames with spaces and Unicode, and missing tools; unavailable checks report INCOMPLETE. A future cleanup needs explicit file-level scope. This supports item 77.7's worktree rule without discarding agent work or hiding failing scripts.

## Translation-schema slice of 77.3 (owner continuation, 2026-10-19)

Further owner continuation: "Repeat for all next phases if able." Runtime-context fields in `run_manifest` and
`write_run_record` are now implemented and fixture-tested against Go, with unknown exits null. Actual interactive exit
observation and a BOUND live run remain pending. Project Go gained an opt-in copied real-mod measurement task and safe
explicit evidence capture; FlowerGod requires 712 reviews after 908 policy approvals. GUI owner review and JSON-key
consumer evidence remain open. No release or archive is authorized by these implementation receipts.

Owner: "If able continue same process in next phase." Implemented the next Project Go schema-alignment slice of 77.3;
this does not schedule the other recommendations or change S1-S4. It supplies a source-bound, fixture-tested translation
contract that a later reproducible revival case can consume.

Schema v1 is retained with additive text-line/class kinds and optional role/group metadata. The original conformance
corpus stays intact; two new shared JSON fixtures cover exact text/class bytes and protected/linked behaviour. BridgeForge
validates identities before application and stages linked copies; linked in-place use is refused. Project Go validates the
metadata and tests both shared fixtures. See `fixtures/translation-conformance/SCHEMA_V1_EXTENSIONS.md` for boundaries.
Tests: `test_translation_extended_kinds`, `test_translation_roles`, `test_translation_extension_conformance` plus the
existing translation/conformance/batch tests; Project Go `TranslationExtensionConformanceTest` and full Gradle build.
Source/static/package validation is separate from runtime: LIVE TEST NOT PERFORMED. No schema-2 migration, release,
real-mod acceptance or runtime-record change is included.

<!-- page-nav:start -->
> Page 3 of 3 of the BridgeForge roadmap. Previous: [ROADMAP-2.md](docs/archive/ROADMAP-2.md). Newest entries: [ROADMAP-3.md](ROADMAP-3.md).
<!-- page-nav:end -->

## Proposed ideas (2026-10-06, owner asked for per-project ideas; proposed, not approved) (continued)

70. **Hardening BridgeForge overall (owner 2026-10-12: 'plan any possible hardening').** **Partly implemented; original plan: `docs/HARDENING_PLAN.md`.** Grounded in measurements (cli.main() is 2,852 lines; 182 non-atomic `write_text` sites against one atomic writer; 47 delete sites; 186 workspace accepted-finding baselines; ruff checks only syntax and pyflakes) and in the defect classes of 2026-10-11/12: shared generated launcher files and an agent flag after the main class, `merge_configs` silently dropping keys, accepted baselines hiding Zorg's port bugs, archives not tied to the tested files, stale Atlas cache key, predictions treated as findings. Five phases: H1 small and high value (atomic writes, guarded deletes, launcher self-test, config contract tests, baseline hygiene, archive guard, rig control, known-failure baseline), H2 (split cli.py and scanner.py behind golden snapshots, lint and types, untrusted-input limits, test reliability), H3 evidence discipline (prediction ledger, live ledger, roadmap-lint, base-rate checks), H4 portability (line endings, long paths, pip-audit, snapshots), H5 agent guardrails. Four owner decisions listed in the plan.
    - 70 progress 2026-10-12 (H1.1, H1.2, H1.4, H1.5, H1.6, plus regression findings): `bridgeforge/safeio.py` (`atomic_write_text/json`, `safe_rmtree/safe_unlink` refusing paths outside the stated roots, the roots themselves and links out of them); 11 state writers use it (mod changelog, group config, enabled_mods, workspace manifest, baselines, archive note, group plan) and 12 tree deletes (3 left, in escalation and java_matrix); `tests/test_safeio_ratchet.py` with `tests/safeio_baseline.json` lets bare `write_text` (171 left, was 182) and `shutil.rmtree` only shrink. `tests/test_probe_contract.py`: every probe config key Python writes is read by `ProbeConfig.java` (or listed Python-only), every key it reads is written, `merge_configs` keeps every member key, setup kinds match both sides. `bridgeforge/baseline_audit.py`: baselines carry a stamp (mod version, date) and per-key reasons; `baseline-audit` lists OK/STALE_VERSION/UNSTAMPED/NO_BASELINE (real queue: 189 unstamped, 124 none); `baseline-accept` re-stamps with a written reason; `archive_gate` refuses a stale or unstamped baseline unless `reports/SHIPPED_CHANGES.json` has a written `baseline` reason (owner decision 2026-10-12). `archive_mod` writes `Changes since the previous archive` (files and, inside changed jars, classes) into every ARCHIVE_NOTE (the live-result-current gate, 36.11, already covered 'shipped files are the tested ones'). Regression pass REG-20261012 findings: with mission-fleets and class-sweep now merged into group configs, their FAIL lines had no owner and whole groups read UNCLEAR; group_members now carries missions and classes, summary lines are skipped, a class-sweep NoClassDefFoundError naming a disabled well-known library (Console Commands, LunaLib, MagicLib, LazyLib, Radar) is an optional integration, not a failure, and `probe-group regress --rejudge SOURCE` re-judges saved logs with no game. Real results so far: Aivon-Republic's missions name two variants that do not exist (aiv_marabeth_standard, aiv_rostell_FS). Tests: `tests/test_safeio.py`, `test_safeio_ratchet.py`, `test_probe_contract.py`, `test_baseline_audit.py`, `test_archive.py`, `test_probe_group.py`, `test_regress.py`.
    - 70 H1.3 and H1.8 built 2026-10-12: `env_check.verify_rig_launchers` reads what every rig launcher really passes to java and fails `java-matrix setup` on `agent-after-main-class` (a `-javaagent` after the main class is an application argument), `prepatcher-not-last-agent`, `argfile-missing`, `prep-launcher-without-agent`, `plain-launcher-with-agent` and `argfile-shared-between-variants`; `env-check` now counts only agents before the main class and resolves `%RT%` argument files for a relative launcher path (it did not). `tests/known_failures.json` + `test_guard`: a known environmental failure (`test_child_with_cwd_inside_target_is_found`, expires 2026-11-12, reason recorded) no longer fails the full run, a second failure, an expired entry or an unnamed failure still does, a now-passing entry is reported, and `--suite-line` names it. Tests: `tests/test_launcher_selftest.py`, `tests/test_test_guard.py`.
    - 70 H3.2 and H3.3 built 2026-10-12: `bridgeforge live-ledger [--mod M] [--attention]` reads the existing run records (`In operation/_live/*.json`) and regression passes (`_regress/*.json`) into one list per mod (last PASS with version, last run, mods whose latest run was not a PASS); `bridgeforge roadmap-lint` fails when a ROADMAP item marked Done names no test file, `Tests:` line, live test id or docs/ evidence file (329 items; 3 given evidence, 1 stub tolerated in `tests/roadmap_lint_baseline.json`, which may only shrink). Tests: `tests/test_live_ledger.py`, `tests/test_roadmap_lint.py`.
    - 70 H3.1 and H3.4 built 2026-10-12: `docs/atlas_predictions.json` (committed evidence) records what live runs showed about forecast findings; `bridgeforge atlas outcome RULE --mod M --id ID --outcome confirmed|refuted|inconclusive --run TEST --note ...` appends one (a run id and a note are required), `atlas precision` reports the hit rate per rule, and `atlas forecast` annotates matching findings `[prediction confirmed by RUN: ...]`. Seeded with the two decided cases: ATLAS-READS-REPLACED DNEEP x AoTD `farming` confirmed (GRP-DNEEP-SUPPLY-BEFORE-20261011) and Arkgneisis x AoTD `orbitalworks` refuted (GRP-ARK-AOTD-J28FRP-20261012): 1 of 2 held so far. `save-doctor --cycles` now reports the base rate with every MEMORY_CYCLE (cycles among N condition markets, how many share a memory), so a culprit is not named from one cycle alone. Tests: `tests/test_atlas_predictions.py`, `tests/test_save_cycles.py`.
    - 70 H1.7, H2.3, H2.4, H5 built 2026-10-12: `install --also-enable` and `rig-reset` (`tests/test_rig_control.py`); ruff now also runs flake8-bugbear (`B`, four noisy rules ignored in pyproject); `bridgeforge/zipsafe.py` `read_limited` bounds every jar entry read in the atlas, scanner and archive (`tests/test_untrusted_input.py`, including hostile-jar atlas build); `bridgeforge agent-diff-check BRANCH` lists files a branch deleted or cut by more than a fifth before merge (`tests/test_agent_diff_check.py`).
    - 70 H5.4 done 2026-10-12 (owner request): `CLAUDE.md` (layout after the cli.py and scanner.py splits, a Hardening rules section, the mission-variant lesson), the local `AGENTS.md` mirror, `docs/LOCAL_HANDOFF.md` section 0 and the memory index were brought up to date; each named command, file and count was checked against the repo that day.
    - 70 H4 part built 2026-10-12: `rig-doctor` gains an `environment` check (WARN when Windows `LongPathsEnabled` is off or the rig or repository path is non-ASCII; `tests/test_rig_doctor_environment.py`); CI gains a `Dependency audit` job (`pip-audit`). Still open in H4: LF policy and renormalize (done later the same day) and the snapshot trigger.
    - 70 H2.5 part built 2026-10-12: `.github/workflows/weekly.yml` runs the whole suite in reverse order every Monday (`tests/run_reversed.py`) and writes the time to the job summary; first result not yet seen. The `test_locks` failure stays in `tests/known_failures.json` with its expiry.
    - 70 regression pass REG-20261012 done 2026-10-12 (all 39 groups of the validated mods, Java 25 direct launcher, probe 0.2.27): the first judge read 71 items as needing a look, 16 after `--rejudge`, 6 after the judge fixes (sweep artefacts, Nexerelin and Second-in-Command integrations, `Cloak AI` debug prints as chatter; `tests/test_probe_group.py`). Real findings: Aivon-Republic, Sylphon-RnD and The Silent Armada had missions naming variants RC8 lacks (Fatal when the mission starts); fixed (`+bf.1`, `+bf.1`, `+bf.2`), live PASS (REG2/REG5/REG6) and re-archived. Two harness faults behind LIVE_STUCK, both fixed in `bridgeforge/live_run.py`: a probe row listed by the replacer and the probe mod counted twice (Ironclads, rerun REG3 PASS) and 40 wheel ticks short of the bottom of a 58-mission list (group 10, rerun REG4: 7 PASS plus the Silent Armada finding; `tests/test_live_run.py`). Open: Vayra's Ship Pack (`ii_*` variants) and Kadur Remnant (SWP and SEEKER variants) report missing mission variants that look like references to mods not in their group; not yet confirmed. `baseline-accept --all-unstamped` started the 90-day clock for 189 baselines. `audit-explain` now refuses a path without `working/` (it had created a stray folder).
    - 70 H4 (snapshot) and H2.1 (part) built 2026-10-12: `bridgeforge state-snapshot --to DIR` is an append-only copy of `Done/`, `bridgeforge-state/`, every `In operation/*/working` and the Claude memory folder (changed files keep the older version under `versions/<stamp>/`, nothing is deleted, per-source progress, resumable; `tests/test_state_snapshot.py`); `bridgeforge/cli_commands.py` registers commands that live in their own module and `tests/test_cli_golden.py` pins the `--help` hash of all 220 commands before the rest of the `cli.py` split (full suite before it: 1858 tests, OK (skipped=1), 322 s).
    - 70 H2.1 done 2026-10-12: `bridgeforge/cli.py` is 60 lines; every command's parser and handler moved verbatim into 12 `cmd_*.py` modules (253-640 lines) registered in `cli_commands.COMMAND_MODULES`, by an agent in a worktree, merged after `agent-diff-check` showed only the intended shrink. `tests/test_cli_golden.py` hashes the `--help` of all 220 commands and passed after every group; the two dead `*-local` argv rewrites (their parsers were removed in a565e81b) were deleted. Full suite on the merged tree: 1865 tests, OK (skipped=1), 276 s.
    - 70 H2.2 done 2026-10-12: `bridgeforge/scanner.py` is 615 lines (`scan_mod`, `_scan_jars` and a re-export block); 20 `scan_*.py` modules (213-737 lines) hold the checks, cut by AST so no code was retyped. A behaviour golden over 60 `In operation/*/original` mods (about 2,500 findings, order included) was identical after each of three commits. `_scan_jars` stays because tests rebind the jar-limit constants on `scanner`. 210 finding ids across 24 modules.
    - 61/62 first live run 2026-10-12: the matrix had never clicked the launcher (added 2026-10-11), so three of four variants hung at it; fixed (`auto_click=True`, asserted in `tests/test_java_matrix.py`). `java-matrix mass --preset compare --bundle 4` over the 150 archives (6,148 s): 137 SCREEN_PASS, 13 NEEDS_LUNALIB (Fast Rendering variants only; RC8-33), none environment-sensitive between Java 25 and 28 or direct and Fast Rendering, none failing everywhere. The Fast Rendering race hypothesis from the tester's log is not supported by this run.
    - 60g(5) measured 2026-10-12 with a temporary copy of the Seeker workspace carrying the pre-fix jar from `SEEKER-0.3.0-0.98a+bf.4.zip` (copy deleted afterwards, rig restored): the probe mission and the `seeker` duel did not reproduce the wreck re-dying (peak hulks 1, frame 17 ms), but the `overwhelm` duel (forced kill at 45 s) did: frames 17 ms before the kill and 2,875 ms on average after it, worst 7,748 ms, 2,340 hulks and 2,403 ships by the time the duel plugin's `real-time-after-kill` cap ended it at 98 s real (`PROOF-DUEL2-20261012`). So the bf.4 jar reproduces RC8-27 under the duel; the probe's own combat-perf runaway stop was not exercised, because the probe's mission never destroys Bone-Breaker. **Closed 2026-10-12 (second run):** `probe-group duel` gained `ubique` (SEEKER's Ubique, ART_vectorCruiser_prototype, overwhelmed; Phased Mainframe) and `probestop` (the overwhelm duel with the probe's own `BfProbeCombatPlugin` attached). Pre-fix bf.4 jar: Ubique after its destruction 658 ms frames, 722 ships and 2,089 projectiles (`UBQ-PREFIX-20261012`); bf.5 jar: 18.9 ms, 8 ships, 41 projectiles (`UBQ-FIXED-20261012`); the Bone-Breaker overwhelm on bf.5: 17 ms, 8 hulks. `probestop` on the bf.4 jar: the probe logged `combat-perf|FAIL|runaway|hulks=441 ships=475` and ended the combat at 46 s, where the duel plugin alone had let it reach 2,340 hulks at 98 s (`PROBESTOP-20261012`). So 0.2.24's runaway stop is proven live and both patched hull mods are confirmed fixed. Rig restored; the duel mod's mission list now has five rows.
    - Mission guards 2026-10-12 (owner: a mission that is player-facing must require its dependency, be guarded, or be hidden): a mod's variants inside `if (otherModEnabled) { }` are no longer reported as missing references (`probe_config._mission_fleet_refs`, `tests/test_mod_guarded_missions.py`); Vayra's Ship Pack's `bearsfruit` case blocks are guarded by its faction picker (accepted in `reports/probe_accepted.json` with the evidence). Real defects found and fixed: Kadur Remnant `vayra_k006` pooled Vayra's Ship Pack cruisers unconditionally (now guarded, 3.2.3support6+bf.1), and Vayra's Ship Pack declared no dependencies although its plugin stops at load without LazyLib (1.2.3+bf.1, which a solo run exposed because groups share libraries). The scanner now reads `getScriptClassLoader().loadClass(<library class>)` with a throwing catch as a required library. A sweep of every working copy found the same pattern in four unarchived mods (Concordance of Protection Syndicate, Foundation of Borken, Pearson Exotronics; Neutrino tomatopaste gets LazyLib through MagicLib), to be declared when they are revived. Both mods live PASS and re-archived.
    - Zorg18 V18+bf.9 (owner screenshots 2026-10-12): bf.8's Zeta change was wrong. ZorgGen's two constants (star corona -10000; Zeta I radius 0, orbit 100, 5000 days) are bf.7's again, so the ring bands, which orbit Zeta I, circle the star ball and not a planet 5000 units away (only those two constants differed between bf.7 and bf.8, javap diff). With Nexerelin the Zorg started neutral to everyone because its New Game resets relations after `onNewGameAfterEconomyLoad`: the Bf plugin now also runs after the time pass and `data/config/exerelinFactionConfig/zorg.json` sets `hostileToAll` 3 (Nexerelin `DiplomacyManager.handleHostileToAllFaction`: -1.0 to all, including the player); live day-1 log `BF-ZORG|relations` 23 of 23 hostile, player -1.0 (ZBF9C-NEX-20261012). Zeta I and II had never had markets in any version (only the Unimatrix station did); owner asked for the same market as Unimatrix, so the Bf plugin turns each planet's condition-only market into a size 10 Zorg colony (population, spaceport, Hive Exchange), new games only; the first attempt created nothing because a planet's `getMarket()` is already a condition-only market (live ZBF9D), the second works (ZBF9E-NEX-20261012: three Zorg markets, submarket stock OK). Same version, re-archived. Not live-tested: a player commissioned with the Zorg through Nexerelin.
    - Crash report 2026-10-13 (owner, Epta Consortium 2.0.3 in a modpack with Starpocalypse and Crab Shack): opening a market sorts its stock, RC8 runs each ship's hull mods' `advanceInCampaign`, and a stocked ship has `getFleetData().getFleet() == null`, so `seven_AIcoreRefunder_alphacore` (and beta, gamma) threw a NullPointerException at `member.getFleetData().getFleet().equals(...)`. The three classes in `jars/ChangingNexus.jar` were patched with the null guard the mod's own `seven_AIcoremod_*` already use (`patch-jar-class`; patched jar copied to the owner's Downloads as `ChangingNexus-refunder-fix.jar`; Epta is not archived). New check `hullmod-fleet-dereference-unguarded` (REVIEW, tier mechanical, `scan_combat.py`, `tests/test_hullmod_fleet_dereference.py`) finds the pattern in a hull mod's `advanceInCampaign`; it flags the original Epta (3 files) and nothing else in the 300 working copies. Not live-tested: opening a market with the patched jar.
    - 2026-10-13 (owner: Templars 0.9.8f through BridgeForge, archive it and 0.9.9e, and Epta Consortium too). **Epta Consortium 2.0.3 archived** (EPTA2-20261013): besides the refunder fix, the three combat spawns (defense funnels, NAS phase and gregariousness copies) now give the spawned ship a captain with a personality (the existing fixer's change, applied to the jar's sources and patched in); the remaining findings were accepted with evidence; the live run's two probe FAILs (a hidden faction with no ships or markets, a system 2.0.3 never generates) are accepted in the mod's `probe_accepted.json`. The owner's modpack runs Epta 2.1.2 with `EptaConsortium.jar`, so the refunder fix was also built for that jar (`Downloads/EptaConsortium-2.1.2-refunder-fix.jar`); the first Downloads jar is for 2.0.3 only (renamed `ChangingNexus-2.0.3-refunder-fix.jar`). **The patcher had let a class change its superclass**: with `import ...combat.*` and another rig mod's `data/hullmods/BaseHullMod` on the compile classpath, javac chose the same-package class and the patched `seven_defensefunnels` failed to load (EPTA-20261013); `patch-jar-class` now refuses a changed superclass or interface list (`tests/test_jar_patch.py`), and the source names the type explicitly. **Templars 0.9.9e archived** (TEM099E-20261013, PASS; was set aside on 2026-09-28 as superseded by Templars 2.5.1, archived now at the owner's word). Two scanner false positives fixed: `setCustomDescriptionId("star_antioch")` is not a star type (`tests/test_total_conversion_scans.py`), and RC8 still has the `StarAge` overload of `Misc.addNebulaFromPNG` (`tests/test_signature_rewrites.py`). **Templars 0.9.8f** (April 2018, the 0.8.1a era) **ported onto 0.9.9e's code and archived** (owner choice; TEM098F2-20261013 PASS; the first run built empty Templar patrols until 0.9.9e's `default_ship_roles.json` came along, and the hull, weapon and wing rows needed 0.9.9e's tags). It needed a real port: `relink` reports NEEDS_PORT with 12 members RC8 removed (old economy connections and demand, `FleetFactoryV2`, `getCompositionDoctrine`, the 0.7 `addMarket`/`addCondition`/`RepActionEnvelope` forms) plus the removed event system its Crusades use. Zorg in a Nexerelin random sector (ZRAND-NEX-20261013, `corvusMode` false preset in the rig's Nexerelin setup file, restored afterwards): Zeta is generated with all three markets and 23 of 23 factions hostile, player -1.0, at the sector's edge (10 light-years from the nearest market); Templars instead skips its own system there and Nexerelin builds Antioch for it (`enableAntioch`).
    - CI was red on every push from 2026-10-12 to 2026-10-13 and nobody looked (owner: 'add to queue a look at GitHub CI errors'). Causes, all CI-only: the `--help` golden hashed argparse's formatted text (laid out differently per Python), then defaults holding this machine's home folder and the checkout path, then Python 3.10/3.11 marking a `nargs='*'` positional required; `docs/COMMANDS.md` carried the home folder and a Windows path; `safeio` missed junctions on Python 3.10/3.11 (no `Path.is_junction`). The golden now compares each parser as data with paths normalised, the docs render `~` and forward slashes, and junctions are read from the reparse-point attribute. CI green on all twelve jobs (run after commit 'Fix CI golden: a nargs=* positional'). Lesson: after a push, `gh run watch` the run; a local suite on one Python does not prove the matrix.
    - **Epta Consortium 2.1.2+bf.1 archived** 2026-10-13 (owner: 'package epta for now'; folder labelled 2.1.3, embedded version 2.1.2), from the workspace another session prepared (refunder guards and spawned-captain patches, five jar classes replaced, all else byte-identical; checked with javap). Brought into the standard path: report and baseline moved into `working/reports` by revive, 22 escalations re-checked against 2.1.2 sources and accepted with evidence (14 carried from 2.0.3; new: cosmetic frame counters in seven_FluxOverwhelmingCompensation, the unreachable Alicerce generator, carrier bays from seven_fllightdeck_overhauling, the seven_megfunnel CSV tail, officer list in memory, three saved scripts holding a market); the '[BF r1]' name tag dropped (2.0.3 keeps the original name). Live EPTA213-20261013 PASS with probe_accepted Narcepolis patrol and Alicerce (as 2.0.3); the probe's save checked with `save-doctor --cycles`: no cycle. Open, not proven: the Artifact 667 bounty generated live, a save reload, a Nexerelin run. Found on the way: `save-doctor`/`save-compat` read XStream element names literally, so a class with `_` in its name (saved as `__`) was CLASS_UNRESOLVED and the save WILL_LIKELY_FAIL; element names are now decoded (`_decode_element_name`, `tests/test_save_doctor.py`).
    - 63 step 5 (re-prove item 38 against the Toolbox Scheduler Fork: javap and live checks of the six overridden industries and the temporary-market pattern) is deferred to later by the owner (2026-10-12); `docs/AOTD_COMPAT_PLAN.md` step 5 stays the spec. Steps 6 and 7 are done or recorded; 60g(5) is closed above.
71. **Templar Holy Crusade re-created for RC8 (owner 2026-10-13: 'is it possible to re-create the Templar crusade system in terms of RC8? design plan').** **Plan only: `docs/TEMPLAR_CRUSADE_PLAN.md`.** Feasible: RC8's `GenericRaidFGI` (fleet-group intel with prepare, travel, payload and return stages) is what vanilla's Persean League and Sindrian Diktat punitive expeditions and the Knights of Ludd takeover use; `RecentUnrest`, market accessibility, `FleetFactoryV3`/`FleetCreatorMission` and the RC8 `RepActionEnvelope` replace the removed 0.8 event system, `RecentUnrestEvent`, trade connections and `FleetFactoryV2` (javap 2026-10-13). Proposed as a separate companion mod (`tem_crusade_bf`) so no Templars archive changes; 0.9.8f's scheduler, target pick, timings, morale formula, six endings, unrest table and player reputation rules are kept. Phases C1 to C5 (about two days) and five owner decisions are in the plan. Not started.
    - Owner decisions 2026-10-13 (plan section 6): built into the Templars versions, not a companion: the 0.9.8f port, 0.9.9e and the newer Maelstrom Templars Expanded 2.5.1 (0.98 modpack V6.2), through one RC8-API-only jar `jars/TEM_Crusade.jar` that each version lists and calls from `TEMModPlugin.onGameLoad`; accessibility -20%; stability -3 plus a 5 to 10% chance per target market of one industry disrupted on a Templar victory; defenders: response fleets by default, `MilitaryResponseScript` behind `defenderMode`, both tried live.
    - C1 to C3 and the debug mode built 2026-10-13 (plan section 5a): `jars/TEM_Crusade.jar` (source in `In operation/_shared/TEM_Crusade`, shipped in each version's `jars/src`), wired into Templars 0.9.8f port, 0.9.9e and the newer Maelstrom Templars Expanded 2.5.1 (taken in from the 0.98 modpack V6.2 as workspace `Templars-Maelstrom-Expanded`; revive UNATTENDED_DONE after its nine escalations were re-checked against the 2.5.1 sources and accepted with the 0.9.9e reasons). Design change found reading `FGRaidAction`: vanilla already moves, fights, autoresolves and calls the target's patrols; the Crusade's effects sit in `doCustomRaidAction`, so `defenderMode military` is vanilla alone. Live, short stages, both clean in `log-triage` (FATAL 0, MOD-ERROR 0, no attributed exception): **TEMCRUSADE-099E-R1** (0.9.9e, `response`): launched from Ascalon on day 0 against Westernesse (4 Persean markets, 8 fleets), 4 response fleets (178 to 200 points, 20 to 29 ships), condition on 4 markets, 3 of 4 carried, no disruption (8% roll), `end_bad`, unrest 2, condition off. **TEMCRUSADE-251-R1** (2.5.1, `military`, probe save with the Crusade running: `cmdSave returned true`): Naraka (2 markets, 6 fleets), both carried, crusaders lost 21%, `end_crushed`, unrest 3, condition off. Run 1 showed the crusaders are an unspawned route away from the player (`crusaderFleets=0`), so the crushed/defeat split now reads the route's damage (`damageTaken`). One run per mode on different targets cannot say whether the response fleets matter; 200-point response fleets look strong for a balance pass. Open: loading a save with a Crusade in it, player reputation (C4), a run with the player present (spawned fleets), version bumps (`+bf.N`) and re-archive of the two archived versions, live run and archive of 2.5.1.
72. **Lost-feature detection and a re-creation escalation (owner 2026-10-13: 'can we add some sort of fixer/automation or an escalation protocol for things like this in terms of other mods?').** The Crusade was lost without any error: RC8's `starfarer.api.jar` still has `CampaignEventManagerAPI`, `CampaignEventPlugin`, `BaseEventPlugin`, `RecentUnrestEvent` and `SectorAPI.reportEventStage` (javap 2026-10-13, RC8 vs 0.8.1a: the events package went from 90 to 60 entries), so a mod built on the 0.8 event system compiles and links, while RC8's `data/campaign/events.json` runs only `rep_tracker` and `nearby_events` (all other vanilla events commented out). `FleetFactoryV2` is gone (FleetFactoryV3 replaces it). Planned:
    - (a) Finding `legacy-event-system` (MANUAL, never auto-applied): a mod that registers events in `data/campaign/events.json`, subclasses `BaseEventPlugin`/implements `CampaignEventPlugin`, or calls `startEvent`/`primeEvent`/`reportEventStage`; evidence names each event id and class. Its explanation gives the RC8 replacement table (`GenericRaidFGI`/`BaseIntelPlugin` for staged events and reports, `RecentUnrest` for unrest, `FleetFactoryV3`, market accessibility for trade effects), from `docs/TEMPLAR_CRUSADE_PLAN.md` section 2. Needs a live proof first: does RC8 still advance a mod-registered event plugin (probe check, row in `docs/RC8_BEHAVIOUR.md`)? The finding's wording depends on it ("never runs" or "runs, but its messages and reports have no UI").
    - (b) Finding `port-dropped-feature` (REVIEW): when a workspace is ported onto another version's code (as Templars 0.9.8f onto 0.9.9e), list what the old version had and the new lacks: classes by package, `events.json` ids, `reports.csv` ids, settings and options keys, `rules.csv` triggers. A dropped feature is reported, not restored.
    - (c) Escalation packet kind `recreation`: for (a) or (b), a plan skeleton in the shape of the Crusade plan (old mechanics, RC8 replacement for each, design, tests, phases, owner decisions), filled from the finding's evidence; the owner decides whether to build it. A sweep over `Done/` lists every archived mod with either finding.
    - **Status 2026-10-18: E4 built, E3 not built; live pending.** (b) `port-dropped-feature` (REVIEW) is `bridgeforge/scan_port.py`, driven by a per-mod `working/reports/PORT_SOURCE.json` (format: `docs/PORT_SOURCE_FORMAT.md`) and covering classes by package, `events.json` and `reports.csv` ids, settings keys and rules triggers; (c) the `recreation` escalation packet skeleton is implemented with it (item 73 E4). Tests: `tests/test_scan_port.py`. No real port record has been written yet, so no archived mod has been reported by this check; writing Templars 0.9.8f's record and rescanning is LOCAL_HANDOFF 0b item 9 (OBSERVED result still to come). (a) `legacy-event-system` (E3) is not built: it waits on the live proof of whether RC8 advances a mod-registered event plugin, and on the owner choosing per mod after the E4 sweep (AUTOMATION_PLAN decision 5).
73. **Less hand work: fixers, checks and automation (owner 2026-10-14: 'design a roadmap plan for further automation, fixers, checks and anything that would let bridgeforge do more in terms of hand work').** **Plan: `docs/AUTOMATION_PLAN.md`; implemented offline 2026-10-18 except B3 and E3 (status entry below).** Measured with `finding-stats` over stored scans (300 of 316 workspaces): hardest tier none 94, auto 21, input 37, decision 56, inspect 3, code 89; 115 unattended, and applying every mechanical fixer adds none, so the gain is now in the input, decision and code tiers. Largest blockers: `description-missing` (86 mods, the only blocker for 27), `content-reference-unresolved` (7), `obfuscated-internal-api-use` (5), `preset-entry-drops-vanilla-fields` and `settings-json-override-breadth` (4 each); 662 escalation packets and 102 hand-written escalation reviews. Many stored scans predate later fixes, so phase A re-measures first. Phases: A measure (fresh scan, stale-scan report, why auto-tier findings stay open, ledger promotion report), B fixers from verified agent fixes (generation guards, compile rewrites, detach-before-save template, preset merge, wing OP and weapon rows, import resolution from the provider index), C decisions answered once across the queue (decision sheet, precedent in packets, substitution proposals, settings classification), D drafted input (descriptions from other versions and sibling mods first, translation memory, shadowing triage), E self-reviewing escalation (generated review sheet, auto-accept when every gate passes, item 72's `recreation` and `port-dropped-feature`), F checks for hand-found crash classes (hyperspace market, saved live references, provider renames beyond industries, out-of-group mission variants, mission maps, obfuscated members), G live testing without a person (generic New Game driver, overnight regression, `rig-up`, watchdog, group accept, raid scenario mod), H archive chores (rest of 60b, `revise` for `+bf.N`, migration packs). Owner decisions 2026-10-14: crafted description drafts yes, standing approvals from agreeing rulings yes, auto-accept of agent changes that pass every gate yes; and (owner: 'follow your recommendations') overnight unattended runs on the dedicated rig yes, reporting only; lost-feature plans chosen per mod after the E4 sweep. Same day: `AGENTS.md` rewritten as version 2 (the old one kept in `bridgeforge-state/agents-md-history/`): the current `revive`/escalation/`accept`/`archive` pipeline, confidence vs tier vs complexity, what may run without a person, escalation-agent rules from the review flags, sister projects; it points to `CLAUDE.md` instead of mirroring it. The plan was rewritten the same day as an implementation spec (files, behaviour, tests, done-when per item) so any AI can build it. (Status when written: not started; see the 2026-10-18 entry below.)
    - **Specification revised 2026-10-17 (owner: 'ok add/modify roadmap with these recommendations and if possible a plan on how to implement for other agent.').** Item 75's `docs/ROADMAP_IMPLEMENTATION_HANDOFF.md` refines A2, B1/B4/B6, C1, D3, E2, G5 and H2. Content fingerprints precede authoritative A1 measurement; R1-R4 precede E2 activation. Existing supporting commands do not mean these extensions are built. Current summary: `docs/ROADMAP_STATUS.md`.
    - **Implemented offline 2026-10-18; live pending.** Built and unit-tested without the game; no rig run, no real-queue `revive` and no archive of a changed mod has happened, so every "done when" that names the queue or a live run is still open (they are LOCAL_HANDOFF 0b items 1-12). A: A3 `auto-open` (one reason per open auto-tier finding, first match wins, read-only; `tests/test_auto_open.py`); A4 `finding-stats --promotion DIR` (promotion shapes with a before/after example; `tests/test_promotion.py`); A2 is superseded by item 75 R2. A1's fresh scan was run 2026-10-14 (100 of 316 workspaces unattended, local `bridgeforge-state/finding-stats/2026-10-14`) and has not been repeated. B: B1 generation and orbit guards (`tests/test_fixers_guards.py`), B4 preset field merge (`tests/test_fixers_presets.py`, approval-only after the merge fix), B5 `value-proposals` (`tests/test_value_proposals.py`), B6 evidenced or approved weapon rows, B7 import resolution from the provider index in `revive` packets (`tests/test_revive_imports.py`); **B2 Done 2026-10-18** as a decision: no rewrite rule was added because no RC8 member was involved (reason in `signature_rewrites.py`, `tests/test_signature_rewrites.py`); B3 (detach-before-save template) is not built. C: C1 `escalation sheet` with precedent and standing rulings that need a versioned semantic predicate (`tests/test_escalation_sheet.py`), C2 precedent in packets (`tests/test_escalation_sheet.py`), C3 `substitution-proposals` and the `content-reference-substitute` fixer (`tests/test_substitution_proposals.py`, `tests/test_substitutes.py`), C4 settings override classification (`tests/test_settings_keys.py`). D: D1 `descriptions draft` (`tests/test_descriptions_draft.py`), D2 translation memory reuse in `translate-batch` (`tests/test_translate_batch.py`), D3 `shadow-triage` with removal only on owner approval (`tests/test_shadow_triage.py`). E: E1/E2 report-only eligibility in `escalation review`, `--auto-accept` refuses (`ENABLED = False` in `escalation_policy.py`; `tests/test_escalation_auto_accept.py`, `tests/test_escalation_review.py`), E4 as under item 72, E3 not built. F: F1 `market-on-hyperspace-entity`, F2 compiled saved-object references, F3 provider renames for hull mods, commodities and conditions, F4 `mission-variant-not-defined`, F5 `mission-map-reference-missing`, F6 obfuscated members classified against RC8's core jars (`obfuscated-internal-api-resolved`) (`tests/test_market_on_hyperspace_entity.py`, `tests/test_saved_object_compiled.py`, `tests/test_provider_renamed_ids.py`, `tests/test_mission_variant_not_defined.py`, `tests/test_mission_map_reference_missing.py`, `tests/test_obfuscated_members.py`). G: G1 generic New Game fallback (`tests/test_new_game_generic.py`), G2 `probe-group regress --changed-since` (`tests/test_regress_changed.py`), G3 `rig-up` (`tests/test_rig_up.py`), G4 launch watchdog `LAUNCH_NO_PROCESS` (`tests/test_launch_watchdog.py`), G5 `probe-group record --accept` (`tests/test_probe_group.py`), G6 the `bf_raid` mod and `raid_run.py` (`tests/test_raid_run.py`); H2 is superseded by item 75 R5. H: H1 aggregate proof test for `audit-explain --auto` (`tests/test_explain_proofs.py`; the real-queue run is LOCAL_HANDOFF 0b item 10), H3 migration evidence required when a revision drops ids or classes (`revision_renames.py`, `tests/test_revision_renames.py`, `revise migration`). B-fixer sweeps over all 316 workspaces are recorded in the commit bodies (PREDICTED effect on the queue until `revive` runs on it). Open owner decision: whether `revive` should try the REVIEW-only fixers (B1, B4) before packeting. Merged suite 2026-10-18: 2211 tests, only the known `test_locks` intermittent failing.

74. **Zorg18 and EPTA owner follow-up (2026-10-17).** Owner decisions and acceptance steps: docs/OWNER_MOD_FOLLOWUP_2026-10-17.md. Scope: unhide Zorg Zeta planets and provide their markets in existing saves as well as new games; replace EPTA campaign-map station with the standard orbital station and correct its base version from 2.1.2 to 2.1.3. Working revisions only; live acceptance and archiving pending.

75. **Trust prerequisites and long-term roadmap refinement (owner 2026-10-17: 'ok add/modify roadmap with these recommendations and if possible a plan on how to implement for other agent.').** **Specification; R1-R6 and R8 implemented offline 2026-10-18 (entry below), every live gate pending.** Agent-ready plan: `docs/ROADMAP_IMPLEMENTATION_HANDOFF.md`; current summary: `docs/ROADMAP_STATUS.md`. Extends items 70/73, preserving their scope and evidence gates.
    - R1: pre-launch staged mod/dependency/probe/launcher identity, log binding and drift refusal across standalone/group acceptance.
    - R2: registered scans with content/context fingerprints; legacy/unknown and incomplete evidence cannot be current.
    - R3: explicit validation applicability and outcomes before auto-acceptance; missing checks remain incomplete; protect application against stale/concurrent edits.
    - R4: semantic standing-ruling predicates, conflicts/revocations and narrow fixer refusal cases; balance and save changes remain owner decisions.
    - R5: prepare once, test exact candidate, finalize without changing tested bytes; recoverable journal and preserved archives.
    - R6: reusable copied-save upgrade/save/reload/repeat scenarios, including ownership and removed-colony cases; proxy checks stay separate from live proof.
    - R7: reconcile current statuses and per-level evidence while preserving history; report mechanical throughput, review burden and live-qualified/shipped outcomes separately. Initial summary added; detailed audit pending.
    - R8: isolated snapshot restore, hash/environment checks and CLI/rig qualification before machine cutover.
    - **Order:** schemas/current-state audit; R2/A2 then A1/A3, with R1 independently; R4 and R3 report-only, then E2 only after R1-R4 pass; R5/R6 before automated revision or migration acceptance; R8 before snapshot-based cutover. Continue safe draft/report work meanwhile. Each contract names files, negative tests, acceptance and live handoff requirements. Planning approval does not authorize publication or untested archives.
    - **Implemented offline 2026-10-18; live pending.** R1: `run_manifest.py` and `run-manifest prepare|release|check` bind a run to the files staged in the rig; `accept` needs `--rig` and a manifest, group and standalone acceptance share one evaluator, legacy runs read provenance UNKNOWN; the startup-marker echo of the manifest id is not built (`tests/test_run_manifest.py`, 22 tests). R2: `scan_registry.py`, `scan-registry.json`, CURRENT/STALE/UNKNOWN/INCOMPLETE by input content, `finding-stats --rescan-stale` (`tests/test_scan_registry.py`, 16); the real queue reads UNKNOWN until that has run. R3: `escalation_policy.py` gates with PASS/FAIL/INCOMPLETE/NOT_APPLICABLE, report-only, `--auto-accept` refuses until R1/R2/R4 have live evidence and an `AUTO_ACCEPT_POLICY.json` exists (`tests/test_escalation_auto_accept.py`, 20). R4: versioned semantic predicates for standing rulings (three independent mods) and fixer refusals for C1, B1, B4, B5, B6, D3; proposals never edit mod data; stale approvals are refused. R5: `revise prepare|finalize|status|migration` with a journal; never edits tested bytes, no push (`tests/test_revise.py`, 14). R6: `save-upgrade plan|evaluate`, eight cases, PROXY_ONLY and LIVE_PENDING kept distinct from VERIFIED, no in-game evidence emitter yet (`tests/test_save_upgrade.py`, 13). R7: initial table in `docs/ROADMAP_STATUS.md`, updated 2026-10-18; the per-sub-item audit of item 70 is still open. R8: `snapshot-restore-check`, best verdict RESTORED_OFFLINE, `recoverable` stays false without the rig step (`tests/test_snapshot_restore.py`, 8). Live acceptance of each is LOCAL_HANDOFF 0b, R1 first (items 1-5); the Zorg bf.9 to bf.10 save-upgrade run and a real restore remain unrun.

**Documentation/source audit 2026-10-18 (S1 / item 75 R7):** `docs/archive/DOCS_AUDIT_2026-10-18.md` records the owned-document/GitHub checks and corrected entry points/status claims. **Open S1 blocker DOC-001:** current `archive --refresh` deletes the prior archive despite the preservation contract. Do not use standalone/group refresh on known-good artifacts until preservation and failure/retry tests are fixed. See `BUGS.md`; documentation changes do not close the implementation issue.
**Update 2026-10-18: DOC-001 fixed** (`3304c1d1`): `archive --refresh` and `probe-group record --archive --refresh` move the old archive to `Done/_replaced-<date>/<Mod>[-N]` and restore it if the new write fails (`tests/test_archive_preserves.py`, 5 tests, plus the group-path assertion in `tests/test_probe_group.py`). Not yet exercised on a real `Done/` archive: the first real refresh is the check. The paragraph above is kept as the record of what the audit found.

76. **Bounded execution and analysis reuse (S2; owner 2026-10-18: 'add to roadmap. Anything else like this we can improve or add?').** **Plan only:** `docs/EXECUTION_EFFICIENCY_PLAN.md`. Extend existing `revive-queue --jobs` and Java matrix `--parallel`, not a new distributed platform. E1 measures bottlenecks/resources; E2 reuses content/context-bound facts and recomputes affected work; E3 runs independent analysis under bounded resource/write ownership; E4 integrates cancellation, input-bound resume and bottleneck reporting. S1 supplies case identities, ownership and serial timing; S2 owns throughput delivery. Compare serial/cold/warm/parallel results and recovery controls before changing defaults; preserve qualification, owner review and live limits. Proposed adjacent improvements are analysis reuse, selective recomputation, backpressure, duplicate-work coalescing and observable recovery. No application implementation, expanded live concurrency or new policy is authorized by this planning entry.

77. **Recommendations after items 73 and 75 (2026-10-18; owner: "take a look at roadmaps and add recommendations as well as long term recommendations").** **Proposed, not approved; nothing here is scheduled.** Grounded in the state recorded in `docs/ROADMAP_STATUS.md` (items 73/75 implemented offline, every live gate pending) and the proposed S1-S4 strategy (`docs/STRATEGIC_ROADMAP.md`, `docs/VISION.md`); it does not change that strategy or any owner decision.
    - **Near term, in order (turn offline work into evidence):**
      - 77.1 **R1 live proof first** (`docs/LOCAL_HANDOFF.md` 0b item 1). Acceptance now fails closed without a bound run, so until one bound run passes and one edited candidate is refused, no new archive can be accepted. This is the single most valuable next hour of rig time.
      - 77.2 **Register the queue** (`finding-stats --rescan-stale --vanilla-core ...`, 0b item 2) and publish the first authoritative counts as CURRENT / STALE / UNKNOWN buckets. Every later measure (unlocks, review burden, auto-open reasons) depends on fresh, fingerprinted scans.
      - 77.3 **Small code follow-ups** that unblock the sister projects: `manifest.java_version` and `process_exit_code` in run records (Project Go's runtime gates); accept Project Go's new schema-v1 unit kinds and fields, or agree a schema 2 with Go and shared conformance fixtures; a public installed-mods function for Salvor; a hard timeout for `test_locks` so a hung `open_files()` fails instead of stalling a suite (`docs/ROADMAP_STATUS.md`, cross-project follow-ups).
      - 77.4 **Owner decisions waiting:** whether `revive` should try REVIEW-only fixers (B1 guards, B4 preset merge) before packeting; a command and approval flow for B6 weapon-row drafts; whether to build B3's detach-before-save template now that F2 finds 29 compiled cases.
      - 77.5 **First revision through `revise prepare` -> bound live run -> `revise finalize`**, on Zorg bf.10 or EPTA 2.1.3+bf.2 (item 74), with the R6 save-upgrade scenario for Zorg. That one run exercises R1, R5 and R6 together and closes item 74.
      - 77.6 **Release 0.4.0 after 77.1-77.5.** Source is 0.3.0 with 300+ commits since `v0.3.0` and no GitHub release for it; 0.4.0 is warranted by items 73/75, but tag it only once R1 has live evidence. Salvor pins `bridgeforge>=0.3,<0.4`: widen its range in the same change, after its provider contract test passes on 0.4.0.
      - 77.7 **Local agent hygiene.** Agents work in a git worktree, never in the main checkout; run `agent-diff-check` before merging; leave no untracked scripts in the checkout (the 2026-10-18 leftovers made the pre-commit hook fail for every commit there). Keep every document under 64k tokens, paged with next-page notes (owner 2026-10-18; `ROADMAP.md` and VoidSmith's work log were split that day).
    - **Long term, by proposed release:**
      - 77.8 **S1, reproducible revival case.** Build the case record on what now exists: R1 manifests (what ran), R2 registry (what was scanned), the escalation ledger and rulings (what was decided), R5 journals (what shipped). The gap is one object that ties them per mod version; `docs/ARCHITECTURE_GAPS.md` G1/G2 describe it. Measure S1 by "a second person can replay why this archive is what it is".
        **Done 2026-10-25 for the owner-accepted bounded S1 scope** (owner: "Approve the controlled repair pilot"; "Accept the bounded S1 baseline"). [S1 completion review](docs/S1_COMPLETION_REVIEW.md) records artifact-only independent agent resume, requalification, correct stale-evaluator refusal, fresh local archive/exact retry, and current P3-P6 refusal controls. The exact-subject controlled comment-encoding repair has review PASS and full javac/RC8 Janino PASS (1/1), with executable code unchanged; unrelated whole-mod findings remain refused. Owner review time is "not measured", retained as NOT_MEASURED in the accepted baseline. Tests: `tests/test_case_identity.py`, `tests/test_case_workspace.py`, `tests/test_case_qualification.py`, `tests/test_case_operations.py`, `tests/test_case_cli.py`; fresh guarded suite 2,717 tests, OK (12 unchanged skips), hermeticity PASS. No production code or safety baseline changed in closeout; prior whole-case failures, save upgrades/publication and S2-S4 gates remain separate.
      - 77.9 **S2, bounded production lane.** Item 76's measured parallelism plus item 73's metrics: track review minutes per mod, false-positive and refusal rates per check and fixer, and promotion of recurring agent fixes, not just cleared finding counts. A fixer or check that never fires on real data, or always refuses, should be retired or narrowed. **2026-10-25 continuation:** opt-in pure-parsing reuse measured on the approved eight training cases, three rounds/96 equal complete responses; approximately 8.9% first-scan/28.0% repeated-scan reduction, with measured memory tradeoff and unchanged defaults. Owner 2026-10-25: "Accept the opt-in tradeoff", for this local parsing slice only. Guarded 2,723 tests/12 skips PASS, 83.1469862% coverage; isolated wheel checks PASS. See `docs/S2_ANALYSIS_REUSE.md`. Subsequent private serial/two-worker portfolio trial: three equal/preserved rounds, 43.2% median elapsed reduction, narrow cancel/crash/context/altered-response/existing-lock controls PASS; `docs/S2_PORTFOLIO_TRIAL.md`. Production portfolio/resource/recovery integration, governed recipe promotion and overall S2 acceptance remain open; defaults unchanged.
      - 77.10 **S3, behaviour and upgrade qualification.** Make R6 scenarios and soak runs routine for every revision that touches campaign state; grow `docs/RC8_BEHAVIOUR.md` only from observed runs; give the probe a startup marker that echoes the manifest id (R1 slice 2, not built) so log identity stops depending on paths and timestamps.
      - 77.11 **S4, supportable kit.** Prove a restore on a second machine with R8 before any cutover (item 64); move the rig harness behind a documented, scripted setup so the live gates are not tied to one workstation; keep the agent contract (`AGENTS.md`) and `CLAUDE.md` current with each release.
      - 77.12 **One evidence model across the four projects.** BridgeForge's run records, RC8 behaviour rows and translation method are already consumed by Project Go, Salvor and VoidSmith. Version those contracts (run record, translation schema, save-module API), give each a shared fixture that both sides test against, and change them only in both repositories at once. That is what keeps the sister tools from drifting apart as each grows.

<!-- page-nav:start -->
> End of the last page.
<!-- page-nav:end -->

Item 83 B6 documentation checkpoint 2026-10-23: current package map, module placement, shim retirement and CLAUDE paths documented in [ARCHITECTURE.md](ARCHITECTURE.md); [B6 evidence](docs/REFACTOR_B6_CLOSEOUT.md) records validation/publication and remaining gates. B0/B1/B2/research are merged (#64/#65/#72/#73). The rest of the stack and applicable cross-repository work remain open; item 83 is not Done.

Item 83 publication checkpoint 2026-10-23: remaining B3 families, B4 audit and B5 are pushed with green hosted push CI; B6 documentation passes the full local suite (2,619 tests, 12 skips). [Stack ledger](docs/REFACTOR_STACK.md) records exact tips/runs. Draft PR creation requires owner approval; review/merge and item 83 completion remain pending.
