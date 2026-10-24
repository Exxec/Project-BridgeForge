# S1.3 case, candidate and receipt contracts

2026-10-24. Implementation: `case_identity.py` (content/byte binding) and `case_store.py` (durable, append-only local records). This continues S1 on `feat/s1-workspace-contracts`; it does not activate a qualification profile or modify existing commands.

## Persisted records

Every record has a strict `bridgeforge.<kind>` schema/version-1 envelope, canonical JSON content and SHA-256 record ID. Case IDs are independent UUIDs and remain stable across candidates; the immutable case metadata records selected workspace paths, target profile and declared scope. Scope is always `DECLARED_NOT_APPROVED`, not permission to apply, archive or publish.

A candidate binds:

- Case ID, declared target profile and optional predecessor candidate.
- Original selected tree identity under `all-regular/1`.
- Exact shipped relative-path/file-SHA map and `copy_drift.collect+sha256/1` payload digest, matching the existing run-manifest/live-trust algorithm.
- A separate broader analysis digest using scan-registry exclusion version 1. Generated root reports do not change the candidate; an unshipped source edit still does.
- Explicit core, dependencies, tools, rules, policy, launcher and source-authority context groups. Each selected file/tree has a physical source location and byte digest; omitted groups stay visible in `missing_roles`. An explicit empty dependency group is a declaration of no selected providers, not a dependency-resolution proof.

Context locations are persisted for artifact-only resume and are part of context identity. Relocation/rebinding can therefore create a new candidate rather than silently making old environment evidence current. Context provenance is `BYTE_BOUND_NOT_QUALIFIED`: file readability and hashes do not prove semantic authority, closure, licensing or correct tool use.

Capture performs two complete observations and refuses changed file sets/content/context; per-file stat comparisons detect mutation during a read. It is a local pre/post integrity check, not a filesystem transaction or tamper-proof attestation. Revalidate immediately before qualification/finalization. Physical traversal refuses links/junctions, special files and case-colliding paths before the legacy collector is used. The initial supported cohort requires physical input trees, including otherwise excluded metadata paths; unsupported linked trees refuse rather than being silently truncated.

Receipts bind the case, exact candidate and context, observation kind, outcome, reason, explicit tool identity, timezone-aware timestamp/run ID and evidence file digests. PASS needs an artifact; NOT_APPLICABLE needs a reason. Schema/content forgeries, subject/context replay and unavailable/changed evidence refuse or remain UNKNOWN/INCOMPLETE/STALE. A current generic receipt remains `RECORDED_NOT_VERIFIED`; a supplied PASS label is not approval. S1.4 must use independently verified caller-specific evidence adapters and a complete obligation profile.

## Storage, recovery and concurrency

`CaseStore` lives outside the workspace/frozen inputs. Create with an optional caller-known case ID for idempotent retry, then `add_candidate`, `add_receipt` and load records by their IDs. State directories cannot be context trees; individual immutable state artifacts may be referenced. `assess_candidate` reloads the workspace and stored context paths to detect drift without chat-supplied paths.

One exclusively created, token-owned store lock serializes writes; immutable readers remain available. Atomic safeio publication prevents partial records from becoming accepted state. Identical retries return the same record; different content is never written over an existing immutable path. Interrupted/malformed records are preserved and refused. Failed pre-publication writes leave no accepted case and can retry. Abandoned/changed-owner locks are not automatically stolen/deleted: explicit recovery belongs to S1.5. No mutable latest-candidate index is authoritative and no timestamp chooses an accepted candidate.

Digests detect accidental changes, not a malicious author capable of rewriting records and recomputing hashes. Persisted records confer no trust/signature, owner approval, live provenance or mutation authority. Existing run-manifest, archive/acceptance and policy gates remain independent.

## Validation and next work

25 new identity/store tests cover existing shipped-hash equality, same-version and context drift, generated reports versus source changes, original/target binding, missing context, directory inputs, junctions, concurrent mutation, strict schemas, replay, evidence tampering, retry, lock conflicts, partial/foreign records, persisted-input resume and scope/provenance forgeries. Full suite: 2,660 tests, 12 unchanged skips, hermeticity PASS; branch coverage 83.1940548%. Wheel/installed consumer checks pass; detailed receipts and raw-log locations are in S1_PROGRESS.md.

Next is S1.4: profile/obligation evaluation and evidence adapters. Do not let generic receipt labels satisfy live/compile/owner obligations. No live test was needed for this pure identity/storage slice. LIVE TEST NOT PERFORMED.
