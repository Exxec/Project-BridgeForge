# BridgeForge revival toolkit: how to use it

This guide covers the commands built for reviving old Starsector mods: what each one does, when to use it, and the workflows that chain them together. Revivals target **0.98.5a-RC9** (Java 17), the 0.98.5a hotfix (owner 2026-11-25). 0.98.5a-RC7 is the previous target, and 0.98a-RC8 the reference build before it: archives validated before each move rest on the build they were validated on. For the design behind the commands, see `docs/REVIVAL_ASSURANCE_PLAN.md`. For progress, see `ROADMAP-3.md`. Claude sessions also have the project skills in `.claude/skills/`: `bridgeforge-revive` (one mod from intake to archive), `bridgeforge-catalogue` (`Done/` against a new game build) and `bridgeforge-pr` (commits and pull requests).

All commands run from the repo root, the checkout that also holds `In operation/`, `Done/` and `bridgeforge-state/` (on Test1, the project folder):

```powershell
.venv\Scripts\python.exe -m bridgeforge <command> ...
```

Use `python -m` from the checkout, not the `bridgeforge.exe` script: the `.venv` can hold an older installed copy, and the script runs that one (ROADMAP-3 93.19). Defaults written `<repo>/...`, and `@target`, resolve beside the checkout the package runs from, not the current folder; from another checkout, pass the paths.

Three shorthands used below, adjust to your machine:

```powershell
$core = "C:\Program Files (x86)\Fractal Softworks\Starsector985a\starsector-core"  # the target, 0.98.5a-RC9; read-only
$ref  = "C:\Program Files (x86)\Fractal Softworks\Starsector\starsector-core"      # 0.98a-RC8, the reference; read-only
$rig  = "In operation\_rig-0985a"                                                 # the isolated 0.98.5a test rig, from the repo root
```

On Test1 the target core is `C:\Games\Starsector-0.98.5a-RC9\starsector-core`; RC7 stays beside it at `C:\Games\Starsector-0.98.5a-RC7` (the previous target). `In operation\_rig-0985a` is the 0.98.5a rig (its core links to RC7 until it is repointed to RC9, ROADMAP-3 98.5) and `In operation\_rig` the RC8 rig.

**`@target`.** A core argument written exactly `@target` (`--vanilla-core @target`, or a core given to `target-impact`) resolves to the target core recorded in `<repo>/bridgeforge-state/target.json`. `target set <core>` records it on a machine; `target show` prints the target, every recorded build and `target_core_reports`, the build the core itself reports. Trust that, not a folder name: Test1's `C:\Games\Starsector-0.98.5a-RC3` holds RC3. Without a recorded target the token is refused; name the core path instead.

## 0. Safety rules (read once)

**Archive refresh (DOC-001, fixed 2026-10-18):** `archive --refresh` and `probe-group record --archive --refresh` move the
old archive to `Done/_replaced-<date>/<Mod>[-N]` and put it back if the new write fails; nothing is deleted. This is tested
offline (`tests/test_archive_preserves.py`) and has not yet been exercised on a real `Done/` archive, so check
`_replaced-*` after the first real refresh. The long-term S1 convergence remains proposed, and the trust gates of
section 12 are offline-tested with their live runs still pending (`docs/LOCAL_HANDOFF.md` section 0b).

- **Your real Starsector install is read-only.** BridgeForge only ever reads it (`--vanilla-core`, `--source-mods`).
- **Test rigs must be isolated.** A rig is a folder with `run-java25.bat`, `mods/`, `logs/`, `saves/` and a `starsector-core` **junction** to the real install. The junction is what keeps saves inside the rig. `boot-test`, `probe-config` and `compat-set` refuse to run when it's missing.
- **Work on working copies** under `In operation/`. Never edit a mod's original archive, or an archive in `Done/`. Finished mods go to `Done/` only after a passing live test, and only on the owner's word.
- **The owner decides acceptances and archiving.** Present each finding with its evidence and a recommendation, and quote the owner's words in the reason you record.
- **The game's licence key is never read, printed or copied.** `rig-doctor` only checks that one is stored (section 0b).
- **Every command that changes files keeps backups** (`*.pre-*.bak`), or previews first (`fix` and `build-tag --dry-run`).
- A Starsector **Fatal error shows only as a dialog box**, never in the log. If the game is still running but no main menu appears, suspect that dialog.

## 0a. One mod from intake to archive

The order that worked for the six-mod batch, United Aurora Federation and Sunrider (2026-11-16/17). Each step names the section with the details.

**1. Intake** a copy; the input mod is never edited.

```powershell
python -m bridgeforge intake "<mod zip or folder>" --repo-root . --name <Workspace-Name> --strip-junk
```

A raw mod folder is zipped into `In operation/_raw-zips/` first and left alone. `--strip-junk` takes in `<name>-clean.zip` when
junk members (`*~`, `desktop.ini`, copies) are the only hazards; the raw archive is kept and the dropped list goes into
`intake.json`. One call takes several sources (then without `--name`), and `--from-mods <mods folder>` matches loose names to
that folder's mods ("koch" -> `Everybody loves KoC-1.05.49a`; a tie is refused).

**2. Revive** against the target (section 2b).

```powershell
python -m bridgeforge revive "In operation/<Name>" --vanilla-core @target --apply --draft-report [--approve <fixer-id> ...] [--providers "<mods folder>"]
```

**3. Finish what revive leaves.** Input-tier fixers do not run inside revive: `fix "In operation/<Name>/working" --finding <id>
--apply` (section 2). A jar that ships its source is rebuilt with `src-to-jar`, and calls whose game method now only returns a
value with `relink` (section 2c). Agent packets go to `escalation run` (section 2b).

**4. The owner's decisions.** Group what is left for the owner: real (fix now), as authored (accept, with the evidence),
setup-dependent (for example an optional integration behind an `isModEnabled` guard), and already so on the previous build. A
mod that runs on RC8 can still list many findings that are identical there (ROADMAP-3 93.34): say so plainly. Recommend one
option per group. After the owner rules, record each finding with their words:

```powershell
python -m bridgeforge escalation accept "In operation/<Name>" <finding-id>[:<file part>] --reason "<evidence>; owner <date>: '<their words>'"
```

`baseline-accept-finding` does the same for a finding outside a packet. Run `revive` again until it ends UNATTENDED_DONE and
the drafted `working/reports/REVIVAL_REPORT.md` reads READY_FOR_LIVE_TEST: `probe-group plan` takes only such workspaces.

**5. Live test** on the 0.98.5a rig: `rig-doctor` (section 0b), then `probe-group plan`, `install`, `smoke`, `live` and
`report` (section 6b).

**6. Record and archive**, on the owner's word only (sections 6b and 12c):

```powershell
python -m bridgeforge probe-group record <TESTID> --rig $rig --accept --archive --note "<the owner's words; what ran>"
```

A mod changed after archiving goes back through `restore-from-done`, a fix, `bump-version` and a new live test (section
12c). A new game build starts with `target-impact` over `Done/` (section 12d).

## 0b. Before every test session: rig-doctor

```powershell
python -m bridgeforge rig-doctor $rig --real-install "C:\Program Files (x86)\Fractal Softworks\Starsector" [--write-saves-baseline]   # first time: record the baseline
python -m bridgeforge rig-doctor $rig --real-install "C:\Program Files (x86)\Fractal Softworks\Starsector"                           # every session
```

Checks, each with its fix command:
- the rig is isolated (junction)
- no rig game is running, and no other process holds the rig's files (`who-locks`)
- the probe is installed and matches its release copy
- every enabled mod resolves, with its dependencies and a matching base `gameVersion`. The base version comes from the rig core's own build, so on the 0.98.5a rig a mod still at `0.98a` warns and one revived to `0.98.5a` does not (96.5 A8).
- every known working copy matches its rig copy (`--working ID=PATH` adds more)
- your real install's saves haven't changed since the recorded baseline
- the rig core's jars hash as recorded (`--write-core-baseline` records them from a known-good core)
- if RevenantLib is installed, it still provides every `bf.*` method `fix --finding removed-api-call` rewrites calls to (`revenantlib-check` runs the same check on any RevenantLib folder or jar, and also catches a jar missing a class for one of its source files)
- `launcher_prefs` (ROADMAP-3 93.28): what an unattended run needs from this Windows user's Java preferences. FAIL when no licence key is stored: neither the launcher nor a direct start can begin a game, and the owner enters the key once in that machine's launcher. WARN when no game controls are stored (the first start shows "Key configuration options have changed"). A note when `canSkipTutorial` is unset: `probe-group live` pins it, with the window resolution, for the run and puts the owner's values back afterwards. The key is checked for presence only, never read, printed or copied.
- long paths, ASCII paths, project-layout strays and locked workspaces

Exit code 1 means a FAIL: fix it before testing.

## 1. Look at a mod: scan and dossier

**`scan`** runs every static check (224 finding ids on 2026-11-17; the list is `docs/CHECKS.md`) and writes a report.

```powershell
python -m bridgeforge scan "<mod_dir>" --vanilla-core $core --output .\scan-out
python -m bridgeforge scan "<mod_dir>" --vanilla-core $core --write-baseline .\baselines\<mod>.json   # accept the current findings
python -m bridgeforge scan "<mod_dir>" --vanilla-core $core --baseline .\baselines\<mod>.json         # later: show only new ones
```

Always pass `--vanilla-core`. Without it, checks that need vanilla data report `UNKNOWN`, not a verdict. Keep baselines **outside** the mod folder so they never end up in a package.

**`dossier`** is the triage packet, for a person or an agent.

```powershell
python -m bridgeforge dossier "<mod_dir>" --vanilla-core $core --output .\dossier-out\<mod> `
    [--baseline .\baselines\<mod>.json] [--original-jar "<original.jar or .bak>"] [--rig "$rig\mods\<mod>"] [--log "$rig\logs\<run>.stdout.log"]
```

- `dossier.md` is the index: identity and build tag, inventory, the open questions (your to-do list), artifact summaries, and a table of parts.
- `dossier.part-01.md`, `-02`, … hold the findings with code context. The most serious are in part 1. Nothing is ever cut; the output splits into more parts instead.
- **Typical use:** read the index, open part 1, and read only the files a question points at.

Classifications: **MANUAL** means likely broken, act on it. **REVIEW** needs judgment. **UNKNOWN** means BridgeForge can't tell. **SAFE** is informational or has a mechanical fix.

**"Defined nowhere"? content-diff.** If `content-reference-unresolved` lists ids no dependency explains,
check whether vanilla itself dropped them:

```powershell
python -m bridgeforge content-diff "<old install>\starsector-core" $core --output "In operation\_reference\removed-content-<old>-to-0985a.json"
python -m bridgeforge scan "<mod_dir>" --vanilla-core $core --removed-content "In operation\_reference\removed-content-<old>-to-0985a.json" --output "<reports>"
```

Ids vanilla removed then appear as `content-reference-removed-in-vanilla`, each with any current vanilla id of the
same display name (a lead, not a confirmed rename). RevenantLib may already carry the old content.

**Stripping content nothing provides? strip-plan.** When `dependency-substitutes` says STRIP_FROM_MOD:

```powershell
python -m bridgeforge strip-plan "<mod_dir>" --vanilla-core $core [--id weapon:vayra_gun]
```

Lists each file and field every unresolved id sits in, and for an emptied weapon slot the vanilla
weapons of the same type and size. Nothing is edited; make the changes in the working copy yourself.

**Only one piece of a big abandoned mod is needed? vendor-plan.** Instead of reviving the whole provider:

```powershell
python -m bridgeforge vendor-plan "In operation\Xenoargh-Rebal" --id hullmod:shields_formshield --vanilla-core $core
```

`INCLUDE` lines are the piece's closure (rows, specs, sprites, animation frames, classes as source).
Decide every `SUSPECT` (code that mentions the piece but nothing references: it may implement its effect)
and every `MISSING`, then fold the result into RevenantLib by hand and record it in its PROVENANCE.md.

## 1b. Which API changed? api-diff

```powershell
python -m bridgeforge api-diff "<old install>\starsector-core" $core --output "In operation\_reference\api-diff-<old>-to-0985a.json"
python -m bridgeforge compile-check "<mod_dir>" --vanilla-core $core --api-diff "In operation\_reference\api-diff-<old>-to-0985a.json"
```

`api-diff` compares two `starfarer.api.jar`s (a jar, or the `starsector-core` folder holding one) once,
and lists every public class, method and field the newer one removed or changed. For each removed method
it names the new overloads in the same class and other classes that now declare the same name and
signature (the `SectorAPI.addMessage` -> `CampaignUIAPI.addMessage` kind). When both cores' `starfarer.api.zip`
sit beside the jars, as the game ships them, it also lists methods whose parameters were renamed under the same
signature (`parameters_renamed`: `Misc.getOfficerSalary`'s `mercenary` became `checkIfInPopulatedSystem`). With
`--api-diff`, `compile-check` prints those leads under each javac error they explain (`API CHANGE ...`). They are
leads to verify, not rewrites. The catalogue holds only API names; keep the game jars themselves out of
the repository. For the step from one target build to the next, `target-impact` does this per mod (section 12d).

## 1c. What did the mod actually change? diff-data

```powershell
python -m bridgeforge diff-data "<mod_dir>\data\weapons\lightmg.wpn" "$core\data\weapons\lightmg.wpn"
python -m bridgeforge diff-data "<mod_dir>\data\weapons\weapon_data.csv" "$core\data\weapons\weapon_data.csv"
```

Compares by value: key, row and column order, comments, trailing commas and `10` vs `10.0` never
show up. `~` changed, `+` only in the second file, `-` only in the first, `^` the same list values in
another order. Exit code 1 means they differ.

**Many shadowed vanilla files? rebuild-from-reference.** When a mod ships edited copies of vanilla
files (the `vanilla-path-shadowing` finding) and you have the install it was made for:

```powershell
python -m bridgeforge rebuild-from-reference "<mod_dir>" --reference-core "<old install>\starsector-core" --vanilla-core $core --class wpn --output "In operation\<Mod>\scratch\rebuilt-wpn"
```

Per file: **MERGED** (the current core's version plus the mod's edits, written to `--output`), **CONFLICT** (the mod
and the current core changed the same value; the core's is kept and the path listed for you to decide),
**UNCHANGED_COPY** (the mod never edited it: delete it from the mod). Review the merged files with
`diff-data`, then copy them into the working copy yourself. Repeat per `--class`.

**Where else is this id used? corpus-index.** Index your Downloads (or any mod archive) once, then
search it instead of running `grep` with a timeout:

```powershell
python -m bridgeforge corpus-index build "C:\Users\exxec\Downloads"          # first run reads everything; later runs only changes
python -m bridgeforge corpus-index search shieldbypass                          # content, case-insensitive, 3+ characters
python -m bridgeforge corpus-index search FormShield --names                    # file paths only
```

**Which releases of each mod do I have? corpus releases.** `corpus releases ROOT... [--write DIR]` scans folders and
`.zip`/`.7z`/`.rar` archives for `mod_info.json` (plus the `.version` file beside it) and groups the copies by mod id: versions,
game versions, forum thread and repository links. `--write DIR` writes `releases.csv`, `RELEASES.md` (ids with one version first,
revival targets from `--repo-root`'s `In operation/*/working` and `Done/*/*` marked, then ids with two or more versions, then what
could not be read) and `pairs.json`, which `atlas migrations --pairs-json DIR/pairs.json` mines. Archives are read in memory
(never extracted), only those two member types, with a size cap; `.rar` needs 7-Zip's `7z.exe` and `.7z` the `archives` extra,
otherwise they are listed as not read. A pair needs two folders: versions that exist only inside an archive are listed as not
pairable, so extract them and run the command again.

Every result ends with a `Coverage:` line. Anything listed under `NOT searched` (for example `.7z`
archives) was not looked inside, so "No hits" only covers the rest.

**Is this loose script really jar-shadowed? verify-shadow.** Never decide from "the same path exists
in vanilla" (E12). Ask the jars:

```powershell
python -m bridgeforge verify-shadow "<mod_dir>\data\hullmods\Armor.java" --against "<mod_dir>" --against $core
```

`SHADOWED` names the jar that supplies the class (the loose file is never compiled); `NOT_SHADOWED`
means the loose file is live code.

## 2. Fix the mechanical things: fix

```powershell
python -m bridgeforge fix "<mod_dir>" --finding <id>            # preview (diff only)
python -m bridgeforge fix "<mod_dir>" --finding <id> --apply    # write + backup + re-scan
```

Only supported finding ids are accepted; any other id is refused with the full list (`fix --help` prints it too, 64 ids on
2026-11-17). In a workspace, `<mod_dir>` is its `working/` folder. Some fixers with their extra options:

| Finding | Extra options |
|---|---|
| `mod-info-game-version-inexact` | `--target-game-version 0.98.5a-RC9` (`revive` sets it from the core) |
| `csv-row-extra-columns` | none (refuses if any extra field has content) |
| `csv-missing-design-type-column` | `--design-type NAME --id-prefix P [--id-prefix P2] --design-color R,G,B` |
| `procgen-planet-row-missing` / `procgen-star-row-missing` | `--vanilla-core $core --type-id <custom_type> --from-vanilla-id <closest_vanilla_type>` (clones vanilla's row with spawn frequency 0) |
| `faction-known-lists-missing` | `--vanilla-core $core --faction-file <data/world/factions/x.faction>`; refuses if any id is unresolved |
| `mod-info-triage-banner` | none |
| `variant-op-over-budget` | `--reference-core $ref`: trims only the variants the target's costs pushed over (owner ruling 2026-09-27) |
| `data-file-not-utf8` | `--encoding FILE=ENC` once a person has read the file and named its encoding |

**Fixers of the `input` tier** (`bridgeforge/automation_tiers.json`, for example `rules-csv-curly-quote-unreadable`) never
run inside `revive`: apply them here with `--apply`.

**Gated fixers for a new build (ROADMAP-3 item 89).** `rc8-signature-changed` (source calls),
`jar-call-signature-changed` (the same calls in jar bytecode) and `forwarding-class-method-missing` (a class that forwards
a game interface gets the methods the new build added) apply a rule only when the core you pass lacks the old member and
has the new one, so pass the target: `fix "<working>" --finding jar-call-signature-changed --vanilla-core @target --apply`.
A changed member whose new argument changes the result (`PersonBountyEventData.reportSuccess(int)`) stays a hand port.

Fixers added by item 73 (offline-tested 2026-10-18) refuse whatever they cannot prove. These are REVIEW tier, so they run
only with an approval: `system-generation-unguarded` and `orbit-period-computed-unguarded` (guards),
`preset-entry-drops-vanilla-fields` (field-specific approval, three-way evidence, stale approvals refused),
`wing-op-cost-blank` and `carrier-bays-proposal` (values come from `value-proposals`, section 12),
`local-weapon-spec-unregistered` (a row from evidence or an approved sibling) and `content-reference-substitute`
(from `substitution-proposals`). `--reference-core`, `--substitutions` and `--providers` carry their extra inputs.

Anything else (REVIEW or MANUAL) needs a human or agent decision. Use the dossier.

## 2b. Let it run: revive, escalation packets and finding-stats

`revive` does the mechanical part of a revival in one go and hands you (or an AI agent) only
what is left:

```powershell
python -m bridgeforge revive "In operation/MyMod" --vanilla-core @target          # dry run (reports and packets are still written)
python -m bridgeforge revive "In operation/MyMod" --vanilla-core @target --apply  # write fixes
```

It scans, applies every fixer it may, rescans, and repeats until nothing changes. A fixer runs
unattended only when all its findings are SAFE. Approve others per run with `--approve ID`, or
once for every mod in `In operation/AUTOMATION_POLICY.json`, where `escalation rule <finding> "In operation"
--approve-fixer --reason "..."` records a standing approval on the owner's word. What remains is in
`reports/escalations/`, with a summary in `reports/revive/REVIVE.md`. A run ends UNATTENDED_DONE, FIXES_PENDING (approve
the listed fixers, or rerun with `--apply`) or ESCALATED; REVIVE.md then lists what still blocks UNATTENDED_DONE, with the
one action that clears each.

- **agent packets** hold a finding a program can't fix yet. Each is a complete prompt: evidence,
  the only files that may change, a numbered excerpt, rules, and the check that decides "done".
- **owner packets** hold a decision (a dependency, a missing value, a fixer awaiting approval
  with its diff). A packet for missing content also lists the three ways out, computed for you:
  swap or revive a provider, copy just the piece (`vendor-plan`, then `vendor-copy --plan`), or
  strip the references (with vanilla weapons that fit each emptied slot).

Against the target core, revive:
- writes the core's own build into `mod_info.json` (`--target` overrides);
- uses a reference core, by default the installed core matching the original `gameVersion` (`--reference-core`
  overrides): `variant-op-over-budget` trims only what the target pushed over and is refused without one, `src-to-jar`
  proves against it, and REVIVE.md compares the over-budget variants on both builds;
- resolves libraries for its scan in the queue's `_rig/mods`, the queue, `PROVIDER_SOURCES.json` and the reference
  install's `mods/`; `--providers` folders add to the report draft's compile check and to the options in missing-content
  packets.

When `revive` leaves nothing to do, `--draft-report` (with `--apply` and `--vanilla-core`) drafts
the mod's REVIVAL_REPORT.md and REVIVAL_PLAN.md so it goes straight to the live test. Its compile check resolves
libraries where the scan does (ROADMAP-3 93.36). On its own: `revival-report-draft "In operation/MyMod/working"
--vanilla-core @target --providers "<mods folder>" --apply`.

A whole queue: `revive-queue "In operation" --vanilla-core @target [--never-revived | --only-status ESCALATED] [--apply]
[--draft-report] [--jobs N]` revives each workspace with progress lines, resumes after an interruption (`--restart` starts
over) and writes `REVIVE_QUEUE.json`.

To copy a piece of an abandoned mod into RevenantLib:

```
python -m bridgeforge vendor-plan "In operation/OldMod" --id weapon:old_gun --json > plan.json
python -m bridgeforge vendor-copy --plan plan.json --to "In operation/RevenantLib"            # dry run
python -m bridgeforge vendor-copy --plan plan.json --to "In operation/RevenantLib" --apply
```

It refuses a stale plan, a conflict with what the target already has, or a plan with open
SUSPECT/MISSING entries (`--allow-partial` to copy the rest), and prints each file's SHA-256 for
PROVENANCE.md.

```
python -m bridgeforge escalation list "In operation/MyMod"
python -m bridgeforge escalation show "In operation/MyMod" <packet>
python -m bridgeforge escalation run  "In operation/MyMod" <packet> --agent "claude -p --permission-mode acceptEdits"
python -m bridgeforge escalation run  "In operation/MyMod" --all --agent "..." --apply
```

The agent works in a copy under `scratch/escalations/`. BridgeForge rejects edits outside the
packet's files, rescans the copy, and keeps the change only if the finding is gone and nothing new
appeared. Kept changes are REVIEW: they still need the live test. Every attempt is logged in
`reports/escalations/ledger.jsonl`. `--auto-accept` is not enabled: it refuses and names its prerequisites (item 75 R1, R2, R4).
`escalation review WORKSPACE` writes the review sheet, including a report-only ELIGIBLE / NOT ELIGIBLE verdict.
A `claude` missing from PATH resolves to the binary bundled with the VS Code extension. `escalation prune WORKSPACE
[--apply]` drops the mod copy inside each finished attempt and keeps the prompt, note, output and changed files.

The owner's rulings: `escalation accept WORKSPACE FINDING_ID[:FILE_PART] --reason "..."` accepts a mod's packet findings as
authored (into its baseline; the reason goes to `reports/ESCALATION_REVIEW.md`), and `baseline-accept-finding WORKSPACE
FINDING_ID[:FILE_PART[:EVIDENCE_PART]] --reason "..." --vanilla-core @target` does the same for findings outside a packet.
Both record a decision the owner made; quote their words in the reason.

`finding-stats` looks across the whole queue. It shows how many mods could run unattended, which
finding would unlock the most mods if it had a fixer, and which fixes agents keep making (write
those as fixers next):

```
python -m bridgeforge finding-stats "In operation" --write "In operation"
```

## 2c. Jars: src-to-jar and relink

**A jar that ships its source** (`src/`, `jars/src/`). Fixers, agent packets and translations edit the source, but the game
loads the jar: `jar-source-not-rebuilt` holds the mod until the classes are rebuilt.

```powershell
python -m bridgeforge src-to-jar "In operation\<Mod>" --jar jars/<Name>.jar --vanilla-core @target --source-root jars/src --lib "<library jar>"           # proof and build only
python -m bridgeforge src-to-jar "In operation\<Mod>" --jar jars/<Name>.jar --vanilla-core @target --source-root jars/src --lib "<library jar>" --apply   # patch the jar
```

It takes the sources that differ from `original/` and first proves that the original sources, compiled against the
reference core at the jar class's own release, give the bytecode of the author's jar in `original/`; otherwise it refuses.
Then it compiles the changed sources against the target and patches the jar (backup in `scratch/jar-patch-<date>/`, ledger
`working/reports/src-to-jar.json`). `--lib` names each library jar the code compiles against (LazyLib, MagicLib, Nexerelin,
...); `--reference-core` defaults to the installed core matching the original `gameVersion`; `--relink path/Class` also
rebuilds an unchanged class; `--allow-removed` names a member whose removal is intended beyond the fields the
`hullmod-instance-state` packets list. A mod with two jars is rebuilt one jar at a time. `revive --approve
jar-source-not-rebuilt` runs it inside revive (with `--lib` there too). With no source: bytecode packets (`jar-packets`,
`patch-jar-class`) or an owner-approved patch.

**Return-type-only calls: relink.** A class whose game call now differs only in its return type (`jar-linkage-unresolved`)
needs only a recompile, unedited:

```powershell
python -m bridgeforge relink "In operation\<Mod>" --vanilla-core @target            # report only
python -m bridgeforge relink "In operation\<Mod>" --vanilla-core @target --apply    # install; backups in scratch/jar-patch-<date>/
```

It recompiles from the shipped source, or decompiled source, and patches only when nothing else changes. Given the queue
folder it walks every workspace with progress lines and a checkpoint (`--restart` ignores it). Example: RC7's
`StarSystemGenerator.addStableLocations(StarSystemAPI, int)` returns a `List` where RC8's returned nothing; Broken Star,
Nightcross, AoTD Vaults of Knowledge and Sunrider call it.

## 3. Build numbers: build-tag

```powershell
python -m bridgeforge build-tag "<mod_dir>" [--dry-run]    # "Mod" -> "Mod [BF r1]", version -> "+bf.1"; next run r2, …
```

Bump on every change you want tested, so the launcher shows which build is running. It edits only `name` and `version` in `mod_info.json`, never the `id` (saves depend on it) and never `.version` files. `--set N` forces a number.

## 4. Get a change into the test rig: prepare-test and copy-drift

```powershell
python -m bridgeforge copy-drift "<working_mod_dir>" "$rig\mods\<mod>"                   # are they identical?
python -m bridgeforge prepare-test "<working_mod_dir>" "$rig\mods\<mod>" --bump --sync   # tag, then copy the changes to the rig
```

`prepare-test` copies only working → rig, never the reverse. It never deletes files in the rig (it lists extras), and it requires 0 drift afterwards. A rig mod folder that's a junction to the working copy is reported as "same folder" (e.g. Flu-X, Vacuum).

## 5. Does it boot? boot-test

```powershell
python -m bridgeforge boot-test $rig --mods lw_lazylib MagicLib <mod_id> [--timeout 240] [--log-name EX-1] [--keep-mods]
```

It sets `enabled_mods.json`, launches the rig, waits for the main menu, closes the game and triages the log. Results:

| Result | Meaning |
|---|---|
| **PASS** | Reached the main menu. |
| **FAIL** | The process exited before the menu. |
| **SUSPECT_FATAL_DIALOG** | The game is still running but no menu appeared. Look at the screen for an error dialog. |
| **REFUSED** | The rig isn't isolated, or a rig game is already running. |

`enabled_mods.json` is restored afterwards unless you pass `--keep-mods`. With a companion pack (P4), see §9.

## 6. Test inside the game: probe-config and the probe mod

The **probe mod** (`bridgeforge-probe`) runs checks inside the game and logs the results. It does nothing unless the rig marker exists, so it can't affect a normal install.

```powershell
python -m bridgeforge build-probe-mod --jdk "<JDK 17+ home>" --core $ref --install-release   # only after editing probe-mod/; the release copy is built against RC8's API
python -m bridgeforge probe-config "<mod_dir>" --runtime $rig --install [--track <entity_id>] [--seconds 60] [--combat-cap 12]
```

Then:

1. Enable `bridgeforge_probe` together with the mod under test and launch the rig (e.g. `boot-test … --keep-mods`, then start the game yourself).
2. **New Game.** Wait about 1 in-game day. The campaign probe checks rings and orbits, faction known lists, market stock, fleet presence, custom planet specs and tracked entity positions. It re-runs every few in-game days. Once per session it also asks the game to resolve every variant and wing id the mod defines, and builds each of the mod's own ship variants as a fleet member (`content-ids`); a FAIL there names the id and the game's own error.
3. **Missions → BridgeForge Probe: Combat.** The mod's ships fight under AI. It logs every ship deployed and flags any captain with no personality.
4. Run `log-triage` (§7) and check its **probe** section.

Save and load can't be scripted. Saving and reloading remains a manual step.

**Skip the setup grind with `--setup`** (repeatable; applied once per save, a day after New Game, through the public API only):

```powershell
python -m bridgeforge probe-config "<mod_dir>" --runtime $rig --install `
    --setup "rep:exipirated=FRIENDLY" --setup "credits:500000" --setup "ship:ART_dimention_manipulator:1" `
    --setup "spawn-fleet:pirates:120" --setup "jump:Corvus"
```

| Spec | Effect |
|---|---|
| `rep:<faction>=<RepLevel or -1..1>` | Sets your reputation with a faction (e.g. `FRIENDLY`, `0.5`). |
| `credits:<N>` | Adds credits. |
| `ship:<variant_id>[:<count>]` | Adds ships to your fleet. |
| `spawn-fleet:<faction>:<fleet_points>` | Spawns a hostile fleet next to you (built from that faction's ship list). |
| `jump:<star_system_name>` | Moves your fleet into a star system. |

Each setup logs `BF-PROBE|…|setup|OK/FAIL|<spec>`, which `log-triage` shows.

**Setup profiles (P3c-1).** Instead of `--setup` flags, keep setups in a plain-text file:

```
# my Exigency test
apply = once-per-save          # or every-load
rep exipirated = FRIENDLY
credits = 500000
ship ART_dimention_manipulator x1
spawn pirates 120
-jump Corvus                   # a leading '-' switches a line off
```

- **Using it:** `probe-config … --profile exigency-rep` (bundled: `exigency-rep`, `seeker-betelgeuse`, `flux-basic`) or `--profile C:\path\my.txt`.
- **Editing in the rig:** the profile is copied to the rig as `saves\common\bf_probe_profile.data`. Starsector adds `.data` to every file a mod keeps there. Edit that file in Notepad and start a New Game; no command needed. When a profile is present it replaces the `--setup` list.
- **Leftover profiles:** running `probe-config` without `--profile` retires an old rig profile to `bf_probe_profile.data.prev`.

**Snapshots.** Keep good starting points and reuse them. Snapshots stay inside the rig; restoring never overwrites a save unless you pass `--replace`:

```powershell
python -m bridgeforge save-snapshot tag $rig <save_folder_name> exigency-r7-avesta   # copy + hash manifest + build tags
python -m bridgeforge save-snapshot list $rig
python -m bridgeforge save-snapshot restore $rig exigency-r7-avesta [--as-name <new_folder>] [--replace]
```

**Scenarios.** A scenario is a named test: the mods, setups, snapshot and **expected results**. The bundled ones are `avesta-near`, `betelgeuse-damaged` and `nex-corvus-day1`.

```powershell
python -m bridgeforge scenario list
python -m bridgeforge scenario plan avesta-near $rig --mod "exigency=<mod_dir>"      # what to enable and run (writes nothing)
python -m bridgeforge scenario check avesta-near "$rig\logs\<run>.stdout.log" [--save "<save dir>"]   # PASS/FAIL per expectation
```

## 6b. Live runs on the 0.98.5a rig: probe-group

A group run tests several READY_FOR_LIVE_TEST workspaces at once: the probe checks each mod's content in the campaign and
in combat, and `record` turns a passing run into LIVE_VALIDATED. Every `probe-group` command defaults to the RC8 rig
(`<queue>/_rig`), so pass `--rig $rig` each time, and keep this rig's plan apart from the default `PROBE_GROUPS.json`.

```powershell
python -m bridgeforge rig-doctor $rig                                                              # section 0b
python -m bridgeforge probe-group plan --rig $rig --write "$rig\PROBE_GROUPS.json" [--exclude <Workspace>] [--solo <Workspace>]
python -m bridgeforge probe-group install 1 --plan "$rig\PROBE_GROUPS.json" --rig $rig
python -m bridgeforge probe-group smoke --rig $rig --log-name G1-SMOKE-<date>                       # boot to the main menu, triage the startup log
python -m bridgeforge probe-group live G1-LIVE-<date> --rig $rig                                     # the whole live run; leave mouse and keyboard alone
python -m bridgeforge probe-group report "$rig\logs\G1-LIVE-<date>.stdout.log" --rig $rig            # per-mod verdicts, before the next install
python -m bridgeforge probe-group record G1-LIVE-<date> --rig $rig --accept --note "<what ran and was seen>"   # on the owner's word; --archive archives too
```

- **plan** takes workspaces whose revival report reads READY_FOR_LIVE_TEST and whose last revive, if any, ended
  UNATTENDED_DONE, with a `0.98` `gameVersion` and their dependencies in the rig (or providers in the queue). Members share
  no mod or content id. `--exclude` leaves a workspace out, `--solo` gives it a group of its own; large campaign mods run
  alone unless `--no-auto-solo`.
- **Libraries** a mod declares must be in the rig's `mods/` (UAF's AshLib was copied in by hand; ROADMAP-3 93.5 is open).
- **smoke** and **live** need the logged-on user's desktop: a game started from an SSH session never shows (93.7). On
  Test1, run them as one-off interactive scheduled tasks and delete each task after its run (a `/SC ONCE /ST 23:59` task
  fires again at 23:59). The harness's click positions were measured in a 1920x1440 window, larger than Test1's 1920x1080
  desktop (93.21, 93.22). So on Test1, start the game directly and move its window up (ROADMAP-3 95.4, which replaced the
  local wrapper scripts on 2026-11-19): `probe-group live TESTID --direct --client-top -200 --bat run-j25-frpp.bat`.
  `smoke` and `live-queue` take the same options.
- **live** pins the launcher resolution and `canSkipTutorial` for the run and puts the owner's values back after it (93.28).
- **report** reads the rig's current probe config, so report a group before the next `install` (93.29).
- **record** reads `<rig>/logs/<TESTID>.stdout.log` and refuses a run that is not bound to its staged inputs (the run
  manifest, section 12), for example when the probe config changed since the launch: re-install that group's config, or run
  again. `--accept` carries probe FAIL lines and caught exceptions only when an earlier acceptance of the same mod version
  covers them; anything uncovered stops the whole group and nothing is recorded. `--archive [--refresh]` archives each
  passing member (section 12c). A record names the save its own run wrote (93.38).

**Owner acceptances for probe lines.** The owner's ruling on a harmless probe FAIL line (a CSV row with no file that nothing
uses, content a mod creates only under a condition) goes into the workspace's `working/reports/probe_accepted.json`:

```json
{"accepted": [
  {"check": "content-parity", "subject": "hulls:<hull id>", "reason": "<evidence>; owner <date>: '<their words>'"},
  {"check": "faction-fleet-gen", "subject": "<faction id>", "reason": "..."}
]}
```

For `content-parity` the subject is `<kind>:<id>` and accepts exactly that missing id: a bare kind accepts nothing, and a
list the probe capped keeps failing for the ids it did not list (93.26). For other checks the subject is the FAIL line's own,
such as a faction id or a class name. `report` lists what was accepted; `record --accept` counts those lines as covered.

**One workspace: accept.** `accept` records one workspace's passing run on its own, without archiving:

```powershell
python -m bridgeforge accept "In operation\<Mod>" --log "$rig\logs\<TESTID>.stdout.log" --test-id <TESTID> --rig $rig --note "<what the owner did and saw>" [--accept-findings "<reason>"]
```

It checks the log, writes the dated evidence section and LIVE_VALIDATED to the revival report, and a run record the archive
gate reads. A run without its manifest (`<rig>/logs/<TESTID>.manifest.json`) is not accepted.

## 7. Read a log: log-triage

```powershell
python -m bridgeforge log-triage "$rig\logs\<run>.stdout.log" [--mod-prefix <mod package or id>] [--json]
```

Add `--mods-dir "$rig\mods"` to **name the culprit**. Each exception gets:
- `suspect`: the mod whose code threw
- `involved`: every mod on its stack

For example, an NPE thrown inside AI Tweaks with SEEKER's ship on the stack lists AI Tweaks as the suspect and SEEKER as involved. For a log from another mod list (e.g. a player's modpack), point `--mods-dir` at that pack's `mods` folder and add `--all-mods`.

It sorts the log into **FATAL**, **MOD-ERROR** (with the mod's own stack frame), **KNOWN-NOISE** (harmless, each with a reason) and OTHER. It also reports milestones (main menu reached, real campaign loads, saves) and the probe results. The exit code is 1 when there's a FATAL.

## 8. Check jars and saves: jar-audit and save-compat

```powershell
python -m bridgeforge jar-audit "<rebuilt.jar>" --original "<original.jar | archive.zip | *.bak>"
python -m bridgeforge save-compat "<rig save dir or campaign.xml>" "<mod_dir>" [--vanilla-core $core]
python -m bridgeforge save-compat "<save>" "<mod_dir>" --compare-old "<old jar or mod>" --compare-new "<new jar or mod>"
```

- **jar-audit** compares a rebuilt jar with the original: class counts, removed classes, library or vanilla classes that slipped in (this is how Exigency's 40 stray GraphicsLib classes were found), and any use of reflection or file APIs.
- **save-compat** answers "will this build load this save?": `LOADS`, `WILL_FAIL` (lists the missing classes) or `UNKNOWN`. Run it before handing anyone a rebuilt jar.

## 9. Test alongside other mods: compat sets (P4)

Some bugs only appear alongside other mods: this project's SEEKER crash needed AI Tweaks, and Nexerelin needs MagicLib to generate a new game. A **compat set** is a named list of popular mods to test with, defined in `bridgeforge/compat_sets/standard.json`:

| Set | Mods |
|---|---|
| `libs` | LazyLib (`lw_lazylib`), MagicLib, LunaLib (`lunalib`), GraphicsLib (`shaderLib`) |
| `standard` | `libs` + AI Tweaks (`aitweaks`), Nexerelin, Ship/Weapon Pack (`swp`), Industrial Evolution (`IndEvo`), Unknown Skies (`US`), Tahlan Shipworks (`tahlan`) |

```powershell
# Copy the set's mods from your real install into the rig (your install is only read; --dry-run shows the plan first)
python -m bridgeforge compat-set install standard --runtime $rig --source-mods "C:\Program Files (x86)\Fractal Softworks\Starsector\mods" --dry-run
python -m bridgeforge compat-set install standard --runtime $rig --source-mods "C:\Program Files (x86)\Fractal Softworks\Starsector\mods"

# Boot the mod alone (with its libs), then with the whole set
python -m bridgeforge boot-test $rig --mods <mod_id> --pack standard
```

| Verdict | Meaning |
|---|---|
| **PASS** | Boots both alone and with the set. |
| **FAIL_ALONE** | Broken on its own. |
| **FAIL_WITH_PACK_ONLY** | Boots alone but breaks with the set: **an interaction bug.** Check the log for which mod's code is on the stack. |
| **SUSPECT_FATAL_DIALOG** | The game is still running but no menu appeared. Look for an error dialog. |

A boot only reaches the main menu. Combat interactions such as the AI Tweaks crash need the probe's combat mission (§6) run with the set enabled.

## 9b. Test only what changed: test-plan

```powershell
python -m bridgeforge test-plan "<mod_dir>" --since r3
```

Every `build-tag` (and `prepare-test --bump`) records a hash manifest of the mod's files, stored in `bridgeforge-state/build-manifests/`, outside the mod. `test-plan` compares the working copy with that tag's manifest and tells you:
- which features the changes touch
- which probe assertions to check
- which test IDs in `LIVE_TEST_INSTRUCTIONS.md` to re-run

For example, a faction file edit means re-checking markets and fleets, while a description edit only needs a text check. Files it can't classify are listed for you to review by hand.

## 9c. Performance: perf-gate and dossier --perf

```powershell
python -m bridgeforge perf-gate --perf-report "<SPW performance-report.json>" --log "$rig\logs\<run>.stdout.log" --mod-prefix loa_ [--thresholds perf.json]
```

It summarises SPW's report (CPU share per mod and startup time) and counts log spam (the same line repeated by a mod, e.g. Arkgneisis's `advance called with null engine`).

Without `--thresholds` it only reports. A thresholds file looks like `{"spam_count": {"warn": 100, "fail": 1000}, "startup_ms": {"warn": 60000}}`. `dossier … --perf <report> --log <log> --perf-mod-prefix <p>` adds the same summary to a dossier, and `dossier … --save <save>` adds the mod's footprint in a save.

## 9d. Release: release

```powershell
python -m bridgeforge release "<mod_dir>" --original "<original.jar>" --baseline .\baselines\<mod>.json --out-dir .\release-out `
    --vanilla-core $core [--rig "$rig\mods\<mod>"] [--corpus-dir "In operation\save_corpus\<mod-id>"]   # dry run
python -m bridgeforge release … --apply                                                                   # write, only if every gate passes
```

| Gate | Blocks when |
|---|---|
| scan | Any new MANUAL finding against the reviewed baseline. |
| jar-audit | Library or vanilla classes are bundled, or original classes are missing. |
| build tag | No `[BF rN]` tag. |
| copy-drift | The rig copy differs (only checked with `--rig`). |
| save corpus | A kept save would no longer load (`save-compat` / `save-content`). |
| licence | `bridgeforge/release_policy.json` marks the mod `local_only` (Exigency). |

`--apply` writes a forward-slash zip and the `Done/`-style folder (no source, no backups, and no jars that `mod_info.json` doesn't load) to `--out-dir`, plus a release note from the build manifests. Save good test saves into `In operation/save_corpus/<mod-id>/`; every one of them is re-checked at each release.

## 10. Workflows

The usual path for a revival is section 0a. The workflows below are the manual route, for a mod the queue commands do not
cover.

**A. First look at a new mod**

`scan` (with `--vanilla-core`) → `dossier` → triage the open questions → `fix` for the SAFE ones → write the rest into the mod's `reports/REVIVAL_PLAN.md` → `scan --write-baseline` once reviewed.

**B. Every change you want tested**

1. Edit the working copy.
2. `scan --baseline …` (no new MANUAL findings?).
3. `prepare-test … --bump --sync`.
4. `boot-test`.
5. `probe-config … --install` → play (New Game plus the probe mission) → `log-triage`.
6. Save, quit and reload by hand; then run `save-compat` on that save.

**C. Before calling a mod done**

- Every live-test item in `In operation/LIVE_TEST_INSTRUCTIONS.md` passes. Use `test-plan --since <last tested tag>` to re-run only what changed.
- Copy good test saves into `In operation/save_corpus/<mod-id>/`.
- `release` (dry run) shows every gate passing. It covers the baseline scan, jar-audit, the build tag, copy-drift, the save corpus and the licence.
- Then run `release … --apply`. Exigency is refused by the licence gate (local-only).

## 12. The trust-gated workflow (items 73 and 75)

Everything here was built offline on 2026-10-18 and unit-tested. The live proof of each step is a numbered entry in
`docs/LOCAL_HANDOFF.md` section 0b and has not been run: treat these as IMPLEMENTED (offline), not VERIFIED (live).

**Scan freshness: scan registry, rescan-stale, auto-open.** Each scan is registered in `<workspace>/reports/scan-registry.json`
with a fingerprint of every input it read. A stored scan is CURRENT, STALE (inputs changed), UNKNOWN (legacy, no fingerprint)
or INCOMPLETE; file times never decide. Until a queue is registered, every real workspace reads UNKNOWN.

```powershell
python -m bridgeforge finding-stats --rescan-stale --write <dir> --vanilla-core $core   # long: run in the background; resumes if interrupted
python -m bridgeforge auto-open "In operation"            # why each open auto-tier finding is still open (STALE_SCAN ... UNEXPLAINED)
python -m bridgeforge finding-stats --promotion <dir>     # which verified agent edits share a shape: fixer candidates
```

**Decisions answered once.** `escalation sheet QUEUE --write SHEET.csv` lists every open decision-tier finding grouped by
question, with earlier rulings as precedent; answer the rows and run `escalation sheet --apply SHEET.csv`. An untouched
suggestion is not an answer unless `confirm=yes`. A standing ruling for other mods needs a versioned semantic predicate and
three agreeing rulings from independent mods; `escalation revoke` withdraws one together with everything derived from it.
`substitution-proposals WORKSPACE --vanilla-core $core --write FILE.json` proposes replacements for unresolved content ids
(`approved: false` until a person edits it). `value-proposals WORKSPACE --write SHEET.csv`, then `--apply SHEET.csv`
(`--dry-run` prints the diffs), fills blank wing op costs and carrier bay counts from comparable rows once a person sets
`approved`. `shadow-triage WORKSPACE --vanilla-core $core` gives a three-way view of shadowed vanilla files; removal needs
`--approve PATH --reason ...`.

**Drafted input.** `descriptions draft TARGET` writes `reports/description-drafts.md` from another version of the mod, then a
sibling mod, then (unless `--no-crafted`) an agent-crafted text marked crafted. Review it, then
`descriptions apply WORKSPACE DRAFT`. `translate-batch` reuses a translation memory.

**Preparing a rig and a live run.** Section 6b has the full sequence for the 0.98.5a rig.

```powershell
python -m bridgeforge rig-up $rig --mods <mod_id> --probe-config   # sync, enable dependencies, write the probe config; records rig_up_state.json
python -m bridgeforge probe-group plan --rig $rig
python -m bridgeforge probe-group install <group> --rig $rig        # or rig-up for an ad-hoc set of mods
python -m bridgeforge probe-group live <TESTID> --rig $rig          # plays the run; prepares and releases the run manifest itself
python -m bridgeforge probe-group record <TESTID> --rig $rig --accept --note "what was run and seen"
```

`run-manifest prepare|release|check RIG RUN_ID` is the same binding done by hand; `tools/bf-test.ps1 launch`, `boot-test` and
`probe-group live` call it for you. The manifest hashes the files staged in the rig, the enabled list, the probe config and
the launcher; the rig belongs to the run until it is released, and `rig-up` and `probe-group install` refuse meanwhile.
`accept` now needs `--rig` and the manifest: a run without one is not accepted, and legacy runs read as provenance UNKNOWN.
`record --accept` carries probe FAIL lines or caught exceptions only when an earlier acceptance of the same mod version covers
them. Changing a shipped file afterwards turns the run STALE (PREDICTED from the design; the live check is LOCAL_HANDOFF 0b
item 1).

Unattended extras, each with its own live acceptance step: `probe-group regress --changed-since COMMIT` reruns only what
changed (a regression writes `_regress/REGRESSION_HOLD.json` and blocks the next run until `--clear-hold`); the launch watchdog
ends a run with no java process as `LAUNCH_NO_PROCESS`; a generic New Game fallback drives total conversions it has no special
case for; `raid_run` and the `bf_raid` test mod force a raid on a market.

**Revising a shipped mod: revise.** An alternative to bump-and-archive (section 12c) that archives exactly the tested bytes:

```powershell
python -m bridgeforge revise prepare "In operation\<Mod>" "what changed"    # bumps the version once; journals the previous archive and the candidate hash
#   run the live test of exactly that candidate (above); baseline-accept if a baseline is stale
python -m bridgeforge revise finalize "In operation\<Mod>" --revision <ID> --test-id <TESTID>   # changelog, archive, tested-bytes check, readme copies, snapshot
python -m bridgeforge revise migration "In operation\<Mod>" --reason "..."   # or --pack FILE: needed when the revision drops ids or classes of the archived build
python -m bridgeforge revise status "In operation\<Mod>"
```

`finalize` never edits the tested bytes, refuses if they differ from the candidate, keeps the old archive in
`Done/_replaced-*`, resumes after a failed step through its journal, and does not push. If the working copy changed after
`prepare`, use `prepare --refresh-candidate`; the earlier test evidence is then invalidated.

**Saves and backups.** `save-upgrade plan SPEC` shows the ordered stages and per-case expectations of a copied-save upgrade
(eight cases). `save-upgrade evaluate SPEC EVIDENCE --run-id ID --run-hash HASH` judges a run's evidence; without EVIDENCE the
answer is LIVE_PENDING. Proxy checks stay PROXY_ONLY and are never reported as VERIFIED; there is no in-game evidence emitter
yet. `snapshot-restore-check SNAPSHOT --to <new empty folder> --source-root <repo>` restores a `state-snapshot` into a fresh
folder and hashes it: the best offline verdict is RESTORED_OFFLINE, and `recoverable` stays false until a rig scenario has run
in the copy.

## 12b. Archive checks, gates and research (ROADMAP-3 items 79-81, offline; no live run yet)

- **Dropped features.** `dropped-features WORKSPACE` (or `--queue "In operation" --write DIR`) lists what the older tree
  (`PORT_SOURCE.json`, else the matching `original/` mod) had and `working/` lacks, minus `reports/REMOVALS.json`. Remove a file on
  purpose with `remove WORKSPACE PATH... --reason "..."`: it moves to `scratch/removed/<date>/`, is recorded in `REMOVALS.json`, and
  is refused while other files still reference it (`--force-dangling` records the references).
- **Archive gate.** `archive` and `revise finalize` run that sweep plus the content-parity audit first. DROPS_UNEXPLAINED and
  LOSS_SUSPECTED refuse, UNDETERMINED warns; `--allow-unexplained REASON` (20+ characters) goes ahead and writes the reason to
  `ARCHIVE_NOTE.md`. On probe 0.3.0 or later (current 0.3.3), `probe-group record --accept` prints the archive command for each
  passing workspace.
- **Owner decisions.** `decision template port-dropped-feature` prints a draft; `decision apply DRAFT [--dry-run]` runs the ticked
  actions and is idempotent. `escalation triage QUEUE` groups open packets by what they wait on.
- **Live gates.** `gates.json` (schema 1, one per repo) lists each open rig gate with its state, `needs` and commands. `gates check`
  validates it, `gates lint` fails when a cited status line lacks the gate's state word, and `gates record` writes a result back
  (only that file). `board --live-pending --repos DIR... [--write FILE]` groups open gates into the fewest rig configurations and
  prints one session plan. Never change a gate's state without recorded evidence.
- **Agent sessions and merging.** `hygiene [REPO_DIR]` is a read-only preflight (exit 0 clean, 1 findings, 2 cannot check).
  `merge-train PR... [--worktree PR=PATH] [--dry-run]` merges pull requests in the given order, rebasing each, regenerating the
  generated files and waiting for checks; it skips a PR that is already merged.
- **Research over indexed mods (STATIC, what code references, not what runs).** After `atlas build`: `atlas api-usage PREFIX`,
  `atlas save-risk [MOD]`, `atlas libraries`, `atlas migrations OLD NEW` (or `--pairs-from QUEUE`, `--pairs-installed QUEUE
  --installed MODS_DIR`), `atlas exemplars FEATURE`, and `api how OLD_SYMBOL --old-api JAR --new-api JAR`. Findings are proposals,
  never rules.

**Not enabled or not built.** Auto-acceptance of agent changes is report-only (`--auto-accept` refuses). The
`legacy-event-system` check (item 72 E3) is not built. `port-dropped-feature` (E4, REVIEW) needs a `reports/PORT_SOURCE.json`
(`docs/PORT_SOURCE_FORMAT.md`) before it reports anything.

## 12c. Archives: archive, restore-from-done, bump-version, close

`Done/` keeps one archive per mod, the latest (owner 2026-11-17); older copies move to `Done/_replaced-<date>/`, never
deleted. Archive only on the owner's word, and never edit `Done/` in place.

```powershell
python -m bridgeforge audit-shipped "In operation\<Mod>"                                    # every shipped difference from original/ must be explained
python -m bridgeforge audit-explain "In operation\<Mod>" --auto                             # what the files prove: credits, syntax-only JSON, translation, ...
python -m bridgeforge audit-explain "In operation\<Mod>" <file> ... --reason "<evidence>"   # the rest, by hand
python -m bridgeforge archive "In operation\<Mod>" [--refresh]                              # Done/<Mod>/: mod folder, zip, original, reports, ARCHIVE_NOTE.md
```

`archive` refuses unless the shipped-copy audit passes, the live result is CURRENT and the accepted-findings baseline was
stamped at the mod's current version (`baseline-accept WORKSPACE --reason "..."` re-stamps it once the owner confirms the
findings still stand). Written exceptions live in `reports/SHIPPED_CHANGES.json`: `audit-explain` records why files differ,
`audit-explain WORKSPACE --live --reason "..."` why the mod may go without a current live result, and a `baseline` reason,
written by hand, why a stale baseline stands. It also runs the dropped-feature and content-parity gate (section 12b).
`--refresh` replaces an existing archive: the old one moves to `Done/_replaced-<date>/<Mod>[-N]` and comes back if the new
write fails. `probe-group record --archive [--refresh]` archives each passing group member the same way.

**A shipped mod that changes after archiving:**

```powershell
python -m bridgeforge restore-from-done "Done\<Mod>" --queue "In operation"        # the workspace again: shipped folder, original/, reports, baseline
#   fix it, then:
python -m bridgeforge bump-version "In operation\<Mod>" --note "<what changed and the evidence>"   # +bf.N, a report section ending READY_FOR_LIVE_TEST, a MOD_CHANGELOG line
#   live-test it again (section 6b), then on the owner's word:
python -m bridgeforge probe-group record <TESTID> --rig $rig --accept --archive --refresh --note "<the owner's words; what ran>"
```

`restore-from-done` needs an archive that `archive` made (`Done/<Mod>/<Mod>/mod_info.json`) and refuses when the queue
already holds that workspace; name `--queue`, the `In operation` beside that `Done/`. `revise prepare|finalize` (section
12) is the stricter route.

**An archive that is no longer worked on:**

```powershell
python -m bridgeforge close "Done\<Mod>" --status SUPERSEDED --reason "<what supersedes it; owner <date>: '<their words>'>"
```

`close` takes a queue workspace or a `Done/<Mod>` archive (also the `Done/<Mod>/<Mod>` path `target-impact` prints) and writes
a dated section ending SUPERSEDED or NOT_REVIVABLE to its revival report. Queue commands skip a closed workspace; `done-audit`
and `target-impact` list a closed archive instead of checking it, and a closed library still provides its jars to the mods
that depend on it. Nothing is moved or deleted.

## 12d. A new game build: target-impact, target-bump, retarget

When a new build appears, catalogue `Done/` first, read-only (the `bridgeforge-catalogue` skill). It is a long-running
command: run it in the background and read its progress lines. The old core is the build the mods were validated on, the
current target; the RC8 -> RC7 catalogue was `target-impact $ref $core "Done" --write ...`.

```powershell
python -m bridgeforge target-impact @target "<new starsector-core>" "Done" --write "bridgeforge-state\target-impact-<old>-to-<new>-<date>"
```

Per mod it reports what fails on the new core and not on the old one: jar linkage, interface contracts, dropped call forms,
parameters whose meaning changed, and data the new core treats differently (rule ids a mod overrides that were removed,
settings keys read and removed; a replaced CSV without the new columns is information only). Verdicts are CLEAN, BREAKS,
RELINK (recompile only) and REVIEW. CLEAN means none of these checks changed, not that the mod works on the new build.
`TARGET_IMPACT.md` has a "By game member" table, one changed member often explaining several mods, and per mod the next
steps in order: the gated fixers (section 2), `relink` (section 2c), a hand port or a review. An archived
`Done/<Mod>/<Mod>` copy gets `restore-from-done ... --queue` first, and its steps then act on `In operation/<Mod>`. Archives
the owner closed are listed under `skipped`, not checked. RC8 -> 0.98.5a-RC7 over 175 archives took about 5 minutes on
Test1 (2026-11-17): CLEAN 167, BREAKS 4, RELINK 3, REVIEW 1.

Once the owner has decided what to port:

```powershell
python -m bridgeforge target-bump "<new starsector-core>" [roots]   # --from defaults to the current target; api-diff, vanilla-migration, target-impact, catalogue and registry entry in bridgeforge-state/targets/<build>/, then the new build becomes the target (resumable)
python -m bridgeforge retarget                                        # plan: every CLEAN workspace not yet on the target
python -m bridgeforge retarget --apply                                # gameVersion, +bf.N, a report section ending READY_FOR_LIVE_TEST, a MOD_CHANGELOG line
```

`retarget` skips archives (they move with `archive --refresh` after a live run), mods that are not CLEAN and mods already
on the build. A baseline that was current before the retarget is re-stamped at the new version, noting where it was carried
from; one that was already stale stays stale. Then come the gated fixers the catalogue lists, `relink` and a live test per
mod. `vanilla-migration OLD_CORE NEW_CORE [--write DIR]` shows how vanilla's own code moved across each changed member and
whether each gated fixer rule matches it (BACKED, DIFFERS or NO_VANILLA_CALLS). `target export --to FILE` writes the
registry the sister repos pin (`docs/MULTI_VERSION_COMPAT_DESIGN.md`).

## 11. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `boot-test` says REFUSED | The rig's `starsector-core` isn't a junction, or a rig game is already running. |
| A process is detected, but no game window | That can be VS Code's Java language server (also `java.exe`). BridgeForge matches by the executable path under the rig, not by name. |
| Game "crashed" but the log is clean | A Fatal error dialog. Look at the screen; the log never shows it. |
| `UNKNOWN` everywhere | You forgot `--vanilla-core`. |
| `@target` is refused | No target is recorded beside this checkout: `target set <core>` there, or name the core path. |
| A mod unchecked itself in the launcher | Its `gameVersion` targets a different **base** version (`0.98a` or `0.98` on 0.98.5a). `revive --vanilla-core @target` sets it; by hand, `fix --finding mod-info-game-version-inexact --target-game-version 0.98.5a-RC7`. |
| The report draft is BLOCKED on javac errors that are only missing libraries | Revive's draft resolves libraries where its scan does (93.36). On its own: `revival-report-draft "<working>" --vanilla-core @target --providers "<mods folder>" --apply`. |
| `rig-doctor` FAILs `launcher_prefs` | No licence key is stored for this Windows user. The owner starts the launcher on that machine once and enters it. BridgeForge only checks that it exists; never read, print or copy it. |
| A smoke or live run started over SSH waits and times out | The game started in a non-interactive session (93.7). Start it in the logged-on user's session, as an interactive scheduled task, and delete the task afterwards. |
| `probe-group report` names the wrong mods | It reads the rig's current probe config: report a group before the next `install` (93.29). |
| `probe-group record` refuses the run | The run is not bound to its staged inputs, for example the probe config changed since the launch: re-install that group's config, or run again. |
| `restore-from-done` refuses an archive | It needs `Done/<Mod>/<Mod>/mod_info.json` (an archive made by `archive`) and no workspace of that name in the queue. |
| Launching the bat fails with "not recognized" | The path has spaces. BridgeForge quotes it; if you launch by hand, quote the full bat path. |
