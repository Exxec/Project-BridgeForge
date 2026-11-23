# Gene bank design (94.G3)

**Status:** design for ROADMAP-3 item 94.G3, written 2026-11-23 after 94.G2 was accepted. The phase is approved under GD-1
(owner 2026-11-17, "all approved"); this page fixes its keys and slices. The advisor reviewed the approach the same day.

**Accept (FEATURE_GENOME_ROADMAP, G3):**
- the bank holds the pilots and every allele of them in the corpus;
- every gene has a licence state;
- the bank can be rebuilt from its sources.

Payloads live under the data root, like `Done/`, never in this public repository. Only manifests of the owner's own or
permitted content may become committed fixtures (2026-11-19).

## What the bank is

The bank is a rebuildable index over sources, not a second archive. Every record names the source it was described from,
and `gene bank rebuild` must give the same root hash from those sources on any machine.

- **Allele:** the same feature in another version of a mod, or copied into another mod (FEATURE_GENOME_ROADMAP's
  vocabulary). The match uses content identity across the corpus, the machinery behind `sibling-assets` and
  `supersession`.
- **Lineage:** which mod copied which feature. It comes from blob hashes that several mod ids share. A copy whose ids were
  renamed is out of reach, and is recorded as such.

## Keys

1. **Manifest hash.** Each stored manifest is keyed by the SHA-256 of its canonical bytes (`gene.dumps`), and an index
   maps each identity to its records.
   - Identity alone is not enough: needs are not part of it. P3's set kept one anchor identity through slices 20 to 23
     while what it carried changed.
   - `describe` is byte-stable: run twice on P1 and P4, it gave identical bytes, with no timestamps or machine paths
     (checked 2026-11-23).
2. **Record id.** A record is filed under the hash of (manifest hash, source, build): the same manifest from two releases
   keeps two records. Each record holds the BridgeForge version and the gene-contract pin it was described under, and is
   rewritten on every put, so it carries the describer that last produced it.
3. **Core build.** The closure depends on what the core defines, so one mod described against two cores gives two
   identities. Each record names the core it was described against, by the build that core reports (`target show`), and
   the bank indexes by it. The first slices use the target core (0.98.5a-RC7).
4. **Current and history.** `entries.json` holds, for each line of `sources.json`, the records its last put produced. A
   record no line holds any more is history: it stays in the bank and is verified, but it is outside the ROOT. A re-described
   gene whose manifest changed therefore never overwrites the old record, and a source changed and changed back makes its
   first record current again (review 2026-11-23).

## Store layout (under `data_root()/Genes/`, gitignored like `Done/`)

```
Genes/
  blobs/<sha[:2]>/<sha>          member and needs.donor bytes. Files are stored as bytes; json-entry values as canonical
                                  JSON, the way members are hashed.
  manifests/<mh[:2]>/<mh>.json    canonical gene.json bytes
  records/<id>.json               one per (manifest, source, build): the same manifest from two sources keeps two records.
                                  Holds the manifest hash, identity, kind, anchor, source (mod id, version, folder kind
                                  working or original, path relative to the data root), core build, describer stamp,
                                  licence, member and donor-need blob hashes, needed genes and the reasons any were refused
  sources.json                    the replay list: path, folder, anchor and build of each put
  entries.json                    derived: each sources.json line with the record ids its last put produced
  index.json                      derived over the current records: by identity, anchor, kind, build and licence
  ROOT                            SHA-256 over entries.json, the bytes of each current record, and the manifests and blobs
                                  the current records name (taken from the records, not from a listing of the disk)
  put.partial.jsonl, rebuild.partial.jsonl   checkpoints of an interrupted put or rebuild
```

A bank folder holds nothing else: `put` and `rebuild` refuse a folder with any other entry, so `--bank` naming the data
root, a workspace or `Done/` writes nothing (review 2026-11-23). Nothing in the bank code deletes a file or a tree.

What stays out:
- **Carriers, jars and proofs.** A proof can be rebuilt from its gene and source; carrier jars are not byte-stable.
- **Timestamps and machine paths,** which would break the root hash. A refusal reason names the source, the core and the
  data root as `<source>`, `<core>` and `<data root>`.
- **For a later slice:** the source's tree hash and links to evidence files by manifest hash.

## Commands (`gene bank ...`)

- `put MOD ANCHOR --vanilla-core CORE [--folder working|original] [--quiet]`: describe the gene and every gene its needs
  name (the walk of `prove-set`, with its checkpoint), and store the manifests, records and blobs. A workspace resolves to
  its `working/`, which is refused as `original`.
- `verify`: every blob and manifest matches its hash; every record's manifest and blobs are present. Every `sources.json`
  line has an `entries.json` row holding a record of its anchor. Every `needs.genes` anchor of a current record resolves
  to a current record from the same source, or is recorded as refused; P3 goes in as 79 genes, P4 as 2. The root hash
  recomputes.
- `rebuild --vanilla-core CORE [--quiet]`: put every `sources.json` line again, into the bank as it is: an empty folder
  holding only `sources.json` (another machine), or a bank whose history is kept. It refuses before writing anything when
  the core reports another build or a source is missing. The result is the same root hash either way.
- `list [--kind K] [--anchor A] [--build B] [--licence L] [--history]`: the current records, read from the records
  themselves; `--history` adds those no source holds any more.
- `alleles CORPUS --out PLAN [--exclude GLOB] [--quiet]`: plan only. For every mod root under the corpus, it lists which
  banked anchors the root defines and which it only mentions, plus the zips and anything it could not read (slice 2).

Walks over a corpus follow the long-running rule (progress lines, a checkpoint, `--quiet`) and read archives only
through `zipsafe`.

## Slices

1. **Store, put, verify and rebuild for the four pilots,** from `working/`. Each pilot's `original/` goes in as its first
   second allele; check what `derived_from` already holds.
   - *Accept:* the same root hash from a rebuild in place on White_Legion, from a rebuild into an empty folder there, and
     from a rebuild into an empty folder on Test1.
2. **Alleles across the corpus.** "Every allele" needs a denominator: each corpus mod and version that defines a pilot's
   anchor id. Each is stored, or its refusal is recorded with the reason.
   - Check what `corpus-index` already records before writing a walk. *Checked 2026-11-23:* it is a full-text index
     with no notion of definition, and no database of `Done/` exists. The census (`gene census`) counts items per kind
     and keeps only an archive's working copy. Neither gives the denominator, so slice 2 scans for it.
   - It runs on Test1 as a file-only job.

   Design, set with the advisor (2026-11-23):
   - **2a, `gene bank alleles CORPUS --out PLAN`, plan only.** Nothing is put, because no command removes a
     `sources.json` line.
     - *Roots:* every folder holding `mod_info.json`. In a workspace, only `working/` and the roots under `original/`
       count, never its `genes/`, `scratch/` or `reports/`. `_replaced-*` archives and originals are kept, since they
       are the likeliest alleles.
     - *Zips:* read only for their `mod_info.json`. Each is listed as a packaged copy of a folder row, or as an archive
       only, not described.
     - *The unit:* every anchor of the bank's current records. Acceptance counts the pilot anchors; hits on needed-gene
       ids elsewhere are slice 3's lineage input.
     - *Defines:* the describer's own tables. A copy describe would refuse still defines the id.
     - *Mentions:* a whole-word byte search of every text file and jar class, listing "mention only" roots and what could
       not be read. Misses are the dangerous error.
     - *Errors:* anything other than an unreadable file is an error, counted per root.
     - *Calibration:* over White_Legion's `In operation/`, the four pilot anchors give exactly the eight banked sources.
   - **2b, putting the plan.**
     - A refused anchor becomes a `sources.json` line plus an `entries.json` row with no records and the scrubbed reason.
       `verify` accepts such a row, and `rebuild` reproduces it.
     - A `Done/` working copy is folder kind `archive`. The existing source dicts are left alone, so the pilots' record
       ids and ROOT do not change.
     - The plan is put first into a scratch `--bank`, then into the real one.
   - **Test1 becomes the bank's home.** `Done/` lives there, so once it holds a `Done/` source, a rebuild on White_Legion
     refuses the missing source, as it should. Slice 2's rebuild check is in place against an empty folder, both on
     Test1.
   - **The plan names mod folders,** so it stays on the machine that made it. The roadmap records counts only.
3. **Lineage, the licence report, and `atlas` over the bank.**
   - Lineage: blob hashes shared across mod ids.
   - Licence: each manifest's `licence` (the WP4 ledger).

## Rules

- **Eridani Combine is LOCAL_ONLY.** No bank listing, index or audit output of it goes in this repository; test
  fixtures stay synthetic.
- **RevenantLib distribution (GD-3) is not part of G3's acceptance.** Nothing goes there without the owner's word.
  RevenantLib's own `gene.json` conformance test (D3, WP7) starts with this phase, in that repository.
- **The evidence header binds identity only.** The bank links evidence by manifest hash in its records. Changing the
  header would be a contract bump for the sister pins, so it is raised separately, not done here.
