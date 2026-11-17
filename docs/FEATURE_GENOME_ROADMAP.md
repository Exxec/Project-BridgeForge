# Feature genome: extracting and inserting mod features

**Status: approved by the owner 2026-11-17 ("all approved"), not yet implemented.** Requested 2026-11-17: "design roadmap from
now to endgoal of being able to extract and insert features like DNA"; "factor in the other repos as well"; then "all approved.
Please make sure everything is traceable and each repo gets a copy of its roadmap specific portion." This is a strategy addition
under CLAUDE.md's development policy, recorded here with its decisions (section 11). It extends, and must not weaken,
[VISION.md](VISION.md) and the S1-S4 [strategic roadmap](STRATEGIC_ROADMAP.md).

**Identifiers used everywhere (commits, PRs, sister roadmaps):** the track is BridgeForge ROADMAP-3 item **94**; phases are
**94.G1-94.G7**; owner decisions are **GD-1-GD-5** (section 11); refinements are **GR-1-GR-6** (section 13, approved 2026-11-17). A commit
or pull request implementing a phase names its id in the subject (for example "Add item 94.G1: gene.json contract"). Each
sister repository carries its portion in its own roadmap, citing these ids; section 12 lists those entries.

## 1. The end goal

An operator can say "take *this feature* from mod A (its version, its game build) and put it into mod B, or into a new
carrier mod, on the target build" and get, in one reviewed pipeline:

- the feature's complete, minimal set of parts, proven complete rather than guessed;
- its provenance, author credit and licence state travelling with it, and a refusal when the licence does not allow the use;
- the parts adapted to the target build and the host's libraries;
- collisions with the host (ids, classes, shadowed files, registrations, balance) found and resolved, or refused;
- existing saves kept loadable, and a way to add the feature to, and remove it from, a running save;
- live evidence that the feature *works* in the host (its observable behavior), its performance cost, and its strings.

Done means a pilot set of features, of different kinds, has gone through that pipeline with no hand edits outside reviewed
decisions, and the result is reproducible from the recorded inputs. A correct refusal ("this feature cannot be lifted out:
its state lives in a monolithic plugin") counts as a successful outcome, as it does for revivals.

## 2. Vocabulary

The DNA picture is useful because each term maps to something BridgeForge can check:

| Term | Meaning here | Checkable as |
|---|---|---|
| Genome | One mod: files, CSV/JSON rows, classes, assets, strings, registrations, persistent state | the archaeology graph (`reports/discovery/archaeology`) |
| Gene | The minimal closed set of parts that produces one player-observable capability (a hull, weapon, hull mod, ship system, wing, faction, star system, market or industry, ability, rules.csv dialog, bounty, custom start, combat or campaign plugin) | a gene manifest with members, interfaces, registrations and state |
| Locus (binding site) | Where a gene attaches in a host: a table row, a settings list, a faction's known lists, a ModPlugin hook, a procgen tag, the codex | the manifest's `registrations` |
| Regulator | What switches a gene on or off: `isModEnabled` guards, memory flags, settings toggles, library presence | the manifest's `conditions` (see 93.1's guard analysis) |
| Allele | The same feature in another version of the mod, or copied into another mod | content identity across the corpus (`sibling-assets`, `supersession`) |
| Phenotype | What the player sees the gene do | probe obligations (S3) and live observations |
| Mutation | A game-build or library change the gene must survive | `target-impact`, `api-diff`, the gated fixers |
| Plasmid | The gene inserted as its own small mod that depends on the host; the host is not edited | a carrier mod |
| Integration | The gene merged into the host's own files | host edits on a workspace copy |
| Heredity | Origin, author, licence and every transformation applied | provenance and receipts (S1 contracts) |

## 3. What already exists

The proposal builds on working parts. Each row is a command that exists today (checked 2026-11-17):

| Capability | Existing tool | Gap for genes |
|---|---|---|
| Whole-mod map | `archaeology` (nodes, typed edges, lifecycle hooks/registrations, persistent state, unreferenced classes; Navarchy of Tania: 2537 nodes, 10110 edges) | not cut into features |
| Closure of a content piece | `vendor-plan` (hull mod, weapon, wing, hull, variant, ship system: CSV rows, named classes, sprites/sounds, projectiles, built-ins, imports, same-package classes; lists SUSPECTS such as RevenantLib's `FormShieldPlugin`) | six kinds only; no campaign features; no registration slicing |
| Copy under licence | `vendor-copy` (licence policy, standing local-only licence) | copies into one destination layout |
| Removal | `strip-plan`, Salvor `save-removal-plan` | not framed as "gene excision" with proof |
| Identity across mods | `sibling-assets`, `supersession`, `provider-index`, `corpus-index`, `content-diff` | no feature-level identity |
| Renaming | `renamed-ids`, `new-vanilla-id-collision` (91.3) | no relocation with save aliases |
| Build adaptation | `retarget`, `target-impact`, gated fixers, `src-to-jar` (92.25) | applied to whole mods |
| Behavior | `behavior-map`, S3 obligations and comparisons, the probe | no obligations generated per feature kind |
| Saves | `configureXStream(XStream)` is in the 0.98.5a `ModPlugin` API (javap 2026-11-17); Salvor diagnoses and repairs copies | aliases not generated for moved classes |

## 4. Sister projects

| Project | Role in the genome pipeline |
|---|---|
| **RevenantLib** | The gene bank's distribution home for content from vanished authors, under its fold-in and licence policy (already `vendor-copy`'s destination) |
| **Salvor** | Save safety: does a donor save still load after a gene moves; add a gene to a running save; remove one cleanly (excision) |
| **VoidSmith** | Expression in the economy and fleets: which factions know the gene, legal fits and variants for an inserted hull or weapon, autofit roles, knowledge packs |
| **SpriteForge** | Visual adaptation: slot and geometry checks for an inserted hull, restyling a hull to the host faction's style |
| **Project Go** | The gene's strings as one unit: extraction, translation carry-over, `string-diff` across builds |
| **SPW** | Expression cost: performance attributed to the gene in a live session |

Each keeps its own scope (VISION.md, "Product and repository boundaries"): BridgeForge owns the gene contract, extraction,
adaptation, insertion and qualification evidence; the others consume and return versioned evidence through files, as they do
today.

## 5. Guardrails

1. **Licence travels with the gene and can stop it.** Third-party genes default to local, personal use (the standing
   local-only licence); distribution needs recorded permission or the owner's own content. Author credit is part of the gene.
2. **Insertion is an authorized departure, never a fix.** VISION.md excludes autonomous gameplay redesign; every insertion is
   an owner request, recorded as a deliberate departure from restoration, with its own acceptance.
3. **Prove the closure or abstain.** A gene is extractable only when the subtraction and isolation tests (G2) pass. Reflection,
   string-built class names and runtime-built ids are listed as unknowns, not assumed away.
4. **Plasmid before integration.** Insert as a carrier mod first; merge into a host only when the owner asks and the carrier
   result is qualified.
5. **Save-stable by default.** Keep the donor's class names and ids unless a collision forces a change; then generate XStream
   aliases and prove with Salvor that donor saves still load.
6. **One gene, one reviewed change set**, with receipts, rollback and requalification scoped to what the gene touches.

## 6. Phases

```mermaid
flowchart LR
    G0[G0 Genome map: exists] --> G1[G1 Gene contract]
    G1 --> G2[G2 Sequencing and proof]
    G2 --> G3[G3 Gene bank]
    G2 --> G4[G4 Adaptation]
    G3 --> G5[G5 Insertion]
    G4 --> G5
    G5 --> G6[G6 Expression qualification]
    G6 --> G7[G7 Engineering]
    S3[S3 behavior obligations] --> G6
    I93[Item 93 rigs and probe targets] --> G6
```

**G0. Genome map (exists).** Archaeology, `vendor-plan`, the corpus indexes and the live probe. Nothing to build; G1 starts
from their outputs.

**G1. Gene contract and identity (read-only).** A versioned `gene.json`: kind; anchors (the ids it provides); members (files,
table rows, JSON entries, classes, assets, strings) with hashes; needs (libraries, vanilla ids, other genes); registrations
(loci); conditions (regulators); persistent state (classes and fields that reach saves); build (game version, API surface used);
provenance and licence; phenotype obligations. Identity is a hash of the normalized members, so the same feature in two mods is
recognized as one allele. `gene describe MOD ID` writes the manifest from `vendor-plan` and archaeology output.
*Accept:* manifests for the six content kinds on three batch mods; identical input gives identical hash; schema tests.

**G2. Sequencing and proof (read-only on originals, writes copies).** Extend closure to campaign features: factions, star
systems (procgen generators), markets, industries and conditions, abilities, rules.csv dialog trees (follow triggers,
conditions and script commands), intel and events, bounties, custom starts, combat and campaign plugins, settings entries,
sounds, descriptions, codex entries, portraits. The hard part is **registration slicing**: one ModPlugin method often registers
several features, so the gene records the exact statements it needs and the tool refuses when they cannot be separated. Two
proofs per gene: *subtraction* (donor minus gene: no dangling references, still boots) and *isolation* (gene plus its needs in
an empty carrier: scans clean, boots).
*Accept:* both proofs pass for the G-pilots; every SUSPECT resolved by a person or listed as an unknown.

**G3. Gene bank.** A content-addressed store of manifests and payloads, indexed by kind, anchor, build, licence and allele;
duplicates across the 300+ mod corpus found; lineage (which mod copied which feature) recorded. RevenantLib is the
distribution channel for genes from vanished authors, per its policy. `atlas` research runs over the bank.
*Accept:* the bank holds the pilots and every allele of them in the corpus; licence state per gene; rebuildable from sources.

**G4. Adaptation (mutation repair).** Run the existing machinery at gene scope: `target-impact` on the gene's API surface, the
gated fixers, `src-to-jar` for jar-backed genes, dependency substitution, Project Go for strings, SpriteForge for sprite and
slot checks.
*Accept:* a gene from an RC8-era mod reaches the 0.98.5a target with no hand edits outside reviewed packets (pilots P1, P2).

**G5. Insertion (splicing).** Plasmid first: generate a carrier mod (mod_info with dependencies, the gene's members, a
generated registrar for its loci). Then integration into a host on a workspace copy: append table rows with header alignment
(as `vendor-copy` does), merge settings lists, add faction knowledge and roles through VoidSmith knowledge packs, generate legal
variants with VoidSmith, insert the registration statements into the host plugin. Collisions (ids, classes, shadowed files,
duplicate registrations, new vanilla ids) are found before writing; renames keep saves loadable through generated XStream
aliases, proven with Salvor.
*Accept:* P1-P3 inserted as carriers and boot on 0.98.5a; P1 integrated into a second mod (local-only test); a donor save
still loads after a forced rename.

**G6. Expression qualification (phenotype).** Probe obligations generated per gene kind (S3): a hull appears in the codex and
can be spawned; a weapon fires; a hull mod applies per ship; a star system generates once; a dialog option appears; an event
triggers. SPW records the gene's cost; Salvor adds the gene to an existing save and removes it again cleanly.
*Accept:* live PASS for P1-P3 on the 0.98.5a rig with recorded cost and save add/remove results.

**G7. Engineering.** Compose several genes into one carrier (a hull with its weapons and a faction that fields them), edit a
gene through agent packets with independent verification, and keep recipes for repeated moves. Owner-authored designs are
labelled as departures.
*Accept:* one composed carrier qualified live; one agent-edited gene verified; recipes reused for a second similar gene.

## 7. Order and placement

G1-G3 are read-only analysis and can start once the six live tests and items 92/93 settle, alongside S2. G4-G5 write only to
copies and build on S2's recipe reuse and on `src-to-jar`. G6 needs S3's behavior obligations and item 93's rig and
probe-target work. G7 comes last. This adds a track; it does not reorder S1-S4.

## 8. Pilots

From the six-mod batch, chosen to exercise different kinds and difficulties (local-only, under the standing licence):

| Pilot | Gene | Why |
|---|---|---|
| P1 | Scrapyard Armories `sa_lobster_tanks` hull mod: hull_mods.csv row, its script, the seven `sa_lobster_tanks_*` settings keys, the vanilla lobster commodity | small, data plus loose script plus settings; phenotype is visible in cargo over days |
| P2 | Navarchy of Tania's junkyard spawner: `tania_CombatHandlerSpawner`, the spawner hull mods, the amalgam hulls and variants | jar-backed, combat plugin, already fixed this batch (captains, src-to-jar) |
| P3 | Eridani Combine's Pantheon system: `ECE_StarSystem`, its planets and the two markets it creates (`addMarketplace`), and its faction ties | campaign gene; registration slicing in onNewGame; save safety |
| P4 | Bultach Coalition's custom start | a regulated gene: exists only when Nexerelin loads it |

## 9. Measures

Closure precision and recall, judged by the subtraction and isolation proofs; share of genes extracted and inserted with no
hand edits; insertion success by kind; owner minutes per gene; refusals by reason; save add/remove outcomes; cost recorded per
gene. As in VISION.md, no percentage target is promised before a measured pilot.

## 10. Risks and unknowns

**Risks.** Reflection and string-built class names (rules.csv script commands, `Class.forName`); ids built at runtime; state
shared through memory keys or statics; monolithic plugins that resist slicing; class relocation breaking saves (XStream names);
balance (OP/DP, fleet roles); library version skew; economy coupling (markets, industries); codex unlock tags; licence and
credit; performance.

## 11. Decisions (owner, 2026-11-17: "all approved")

| Id | Decision |
|---|---|
| GD-1 | The genome track (G1-G7) is approved as a strategy addition. G1-G3 run alongside S2; G4-G7 follow their stated prerequisites. |
| GD-2 | Licence posture: genes from third-party mods are for local, personal use; distribution only with the author's recorded permission or for the owner's own content. Author credit always travels with a gene. |
| GD-3 | RevenantLib is the gene bank's distribution home for genes from vanished authors, under its fold-in and licence policy. |
| GD-4 | Pilots P1-P4 (section 8), in that order. |
| GD-5 | Integration into third-party hosts is in scope (on workspace copies, under GD-2), after the gene's carrier (plasmid) result is qualified (guardrail 4). |

## 12. Sister-repository entries

Each repository's own roadmap carries its portion and cites the ids above. Filled in when each entry lands:

| Repository | Phases | Entry | Pull request |
|---|---|---|---|
| RevenantLib | 94.G3, 94.G5 | (pending) | (pending) |
| Project-Salvor | 94.G5, 94.G6 | (pending) | (pending) |
| Project-VoidSmith | 94.G5, 94.G7 | (pending) | (pending) |
| SpriteForge | 94.G4, 94.G5 | (pending) | (pending) |
| Project-Go | 94.G2, 94.G4 | (pending) | (pending) |
| SPW | 94.G6 | (pending) | (pending) |

## 13. Effort estimate and proposed refinements (2026-11-17)

**Estimate, not a commitment** (VISION.md: no capacity baseline yet). The unit is one agent-assisted working session of two to
four hours, measured on item 92: 38 sub-items, 2,370 changed lines (1,133 product, 946 tests) in one evening, mostly targeted
fixes with known evidence. New subsystems carry more design and live verification, so the ranges are wider.

| Phase | BridgeForge sessions | Sister sessions | Rig boots / live runs | Owner hours |
|---|---|---|---|---|
| G1 contract | 1-2 | 0 | 0 | 0.5 |
| G2 sequencing and proof | 6-10 | Project Go 1-2 | 8-12 | 3-5 |
| G3 gene bank | 3-5 | RevenantLib 1-2 | 0 | 1-2 |
| G4 adaptation | 2-4 | SpriteForge 1, Project Go 1 | 2-4 | 1-2 |
| G5 insertion | 6-10 | VoidSmith 2-3, Salvor 1-2, SpriteForge 1-2 | 6-10 | 4-6 |
| G6 expression | 5-8 (includes the Java probe extension) | SPW 2-3, Salvor 2-3 | 8-12 | 4-8 |
| G7 engineering | 4-6 | VoidSmith 1-2 | 3-5 | 3-5 |
| **Total** | **27-45** | **13-21** | **27-43** | **about 17-29** |

Prerequisites outside the track: item 93's remaining rig and probe work (93.3-93.19), about 6-10 sessions, sits on G6's critical
path. At three to four sessions a week the whole track is roughly 4-6 months; G1-G3 (read-only) roughly 3-5 weeks. The largest
uncertainties are G2 (rules.csv dialog closure, slicing monolithic plugins) and G6 (new Java probe checks); correct refusals can
shrink scope.

**Refinements (approved by the owner 2026-11-17, "all approved", after the estimate):**

| Id | Refinement |
|---|---|
| GR-1 | One `gene.json` contract, exported and pinned by hash like `target export`, with a shared fixture set and conformance tests in every consuming repository, so six repositories cannot drift. |
| GR-2 | A gene census before G2: run archaeology over the 300+ mod corpus and count features by kind and how many sit in monolithic plugins, then order G2's kinds by real frequency and difficulty. |
| GR-3 | Ground truth from history: features lost in past revivals (`dropped-features`, item 72) and recorded `vendor-plan` SUSPECT decisions become G2's closure benchmark. |
| GR-4 | A cross-repository trace check: every genome entry in a sister roadmap names an existing 94.Gn, BridgeForge's section 12 names every entry, and a `trace 94.G2` command lists the commits, pull requests, tests and documents that cite an id. |
| GR-5 | Spike the Java probe extension during G2, so the probe build and rig path are proven before G5 and G6 depend on them. |
| GR-6 | One machine-readable licence ledger per mod, shared by `vendor-copy`, the gene bank and RevenantLib, so GD-2 is enforced in one place. |
