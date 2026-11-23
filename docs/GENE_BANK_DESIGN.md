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
   maps each identity to its manifests.
   - Identity alone is not enough: needs are not part of it. P3's set kept one anchor identity through slices 20 to 23
     while what it carried changed.
   - `describe` is byte-stable: run twice on P1 and P4, it gave identical bytes, with no timestamps or machine paths
     (checked 2026-11-23).
2. **Describer stamp.** Each record holds the BridgeForge version and the gene-contract pin it was described under. A
   rebuild under newer rules that yields a different manifest supersedes the old record; it never overwrites it.
3. **Core build.** The closure depends on what the core defines, so one mod described against two cores gives two
   identities. Each record names the core it was described against, by the build that core reports (`target show`), and
   the bank indexes by it. The first slices use the target core (0.98.5a-RC7).

## Store layout (under `data_root()/Genes/`, gitignored like `Done/`)

```
Genes/
  blobs/<sha[:2]>/<sha>          member and needs.donor bytes. Files are stored as bytes; json-entry values as canonical
                                  JSON, the way members are hashed.
  manifests/<mh[:2]>/<mh>.json    canonical gene.json bytes
  records/<id>.json               one per (manifest, source, build): the same manifest from two sources keeps two records.
                                  Holds the manifest hash, identity, kind, anchor, source (mod id, version, folder kind:
                                  working/original/archive, the source's tree hash), core build, describer stamp,
                                  licence, links to evidence files by manifest hash, superseded_by
  index.json                      derived: by identity, anchor, kind, build and licence; rebuilt, never edited
  ROOT                            SHA-256 over the sorted record and blob hashes
```

What stays out:
- **Carriers, jars and proofs.** A proof can be rebuilt from its gene and source; carrier jars are not byte-stable.
- **Timestamps,** which would break the root hash.

## Commands (`gene bank ...`)

- `put MOD ANCHOR --vanilla-core CORE [--set] [--provider-root ...]`: describe the gene, or the gene and every gene its
  needs name, and store the manifests, records and blobs.
- `verify`: every blob is present and matches its hash. Every `needs.genes` anchor resolves to a stored manifest from the
  same source; P3 goes in as 79 genes, P4 as 2. The root hash recomputes.
- `rebuild --sources FILE`: wipe and re-put from a sources list. The result is the same root hash.
- `list [--kind K] [--anchor A] [--build B] [--licence L]`: read the index.

Walks over a corpus follow the long-running rule (progress lines, a checkpoint, `--quiet`) and read archives only
through `zipsafe`.

## Slices

1. **Store, put, verify and rebuild for the four pilots,** from `working/`. Each pilot's `original/` goes in as its first
   second allele; check what `derived_from` already holds.
   - *Accept:* wipe, rebuild, and the same root hash on White_Legion and on Test1.
2. **Alleles across the corpus.** "Every allele" needs a denominator: each corpus mod and version that defines a pilot's
   anchor id. Each is stored, or its refusal is recorded with the reason.
   - Check what `corpus-index` already records before writing a walk.
   - It runs on Test1 as a file-only job.
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
