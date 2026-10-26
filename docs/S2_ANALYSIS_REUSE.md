# S2 invocation-local parsing reuse

**Owner decision, 2026-10-25:** "Accept the opt-in tradeoff" in response to the measured
8.9%/28.0% first/repeated scan reductions and +29.3 MiB worker / +80.1 MiB sampled family
peak memory tradeoff. This accepts this measured local parsing slice only. Defaults remain
unchanged; it does not accept portfolio concurrency, governed recipes or all of S2.

Owner scope: the approved training cohort and "Measurement first; keep defaults" decision in
[S2_COHORT_PROPOSAL.md](S2_COHORT_PROPOSAL.md). This implements an experimental S2.2 slice,
not S2 acceptance or a new default. S1's accepted historical evidence remains preserved.

`bridgeforge.analysis_reuse.reuse_parses` explicitly opts a synchronous read-only caller into a
fresh invocation-local cache. The caller must provide positive entry and serialized-payload-byte
limits. There is no persistent cache, automatic discovery, shared service or CLI default change.
Python container overhead and active caller objects are additional to the payload budget; process
memory must be measured separately. This scope is not a concurrent worker coordination API.

Only pure class-file and lenient JSON parsing use this facility. Keys combine exact content SHA256
with the versioned extractor namespace. Scope lifetime prevents reuse across engine invocations;
an extractor semantic change requires a namespace revision. JSON hooks bypass reuse because they
can carry state and side effects. Disabled JSON reuse does not encode/hash its input.

Internally produced facts are serialized into private in-memory payloads; a hit reconstructs a
separate object. Callers cannot mutate later results through shared parsed classes, dictionaries,
lists or tolerance sets. No pickle is loaded from a file or external record. Parse exceptions
propagate and are not cached; a class parser's existing `None` still means unknown. Oversized
facts are returned normally without retention. LRU eviction affects performance only.

The cache contains no resolved provider closure, source authority, scan result, finding decision,
approval, compile outcome, qualification, live observation or archive receipt. Provider/core/rule
and candidate changes still require the existing evaluation and freshness checks. Identical raw
class bytes may reuse syntax facts across provider paths, while resolution runs against the actual
current selected context. Existing R2 fingerprints and S1 evidence remain the authorities.

Validation includes changed content/extractor, object isolation, hook invocation, parse-error
propagation, unknown class results, nested-scope restoration, disabled behavior, LRU and payload
limits. Private training measurements are under ignored `bridgeforge-state/s2-reuse-20261025-a1`.
They compare complete current-engine responses in three alternating-order serial rounds, with
reuse disabled/enabled and first/second scans in each fresh worker. An enabled first scan starts
empty but may reuse facts within that scan. OS cache state is uncontrolled. Holdouts are excluded.
No compilation, qualification or live test is performed by that experiment.

Measurement results and the owner's slice decision are recorded below. Any default expansion
needs its own approval. S2.3 governed recipe reuse and S2.4 portfolio/recovery remain separate work.

## Training measurement, 2026-10-25

Eight approved training cases, three rounds, 48 fresh serial workers, two scans per worker:
96 complete current-engine responses. Every case's complete response matches across all modes
and rounds. Source/copy/provider inventories, core, JDK, Python and engine identity were verified
before/after. Two unresolved dependency contexts remain unresolved. This is analysis equivalence,
not qualified yield. No holdout was used for selection or promotion.

Summed scan execution seconds across the eight cases (not whole invocation time):

| Round | Disabled first | Enabled empty scope | Disabled second | Enabled second |
|---|---:|---:|---:|---:|
| 1 | 31.656 | 28.863 | 26.768 | 19.613 |
| 2 | 31.488 | 28.840 | 27.326 | 19.435 |
| 3 | 31.667 | 28.694 | 27.139 | 19.540 |

Median enabled/disabled reduction is approximately 8.9% for first scans and 28.0% for second
scans. The disabled second scans also benefit from pre-existing process caches; they are the
appropriate repeated-scan control. Alternating mode order reduces run-order bias but does not
control OS caches. This is one local host and already-revived historical training data.

Maximum Windows worker peak working set: disabled 181.918 MiB, enabled 211.250 MiB.
Maximum sampled worker-plus-descendant RSS: disabled 213.848 MiB, enabled 293.965 MiB.
Family sampling every 25 ms can miss short-lived children and is not a strict memory bound.
The experiment used one worker at a time, 32,768 cache entries and 64 MiB serialized payload
capacity. Maximum retained payload was 25.746 MiB; zero evictions or oversized results occurred.
Those experimental capacities are not new command defaults or an owner-approved resource budget.

Private evidence: `context.json`, `measurement.json`, `summary.json`, 48 worker receipts and
96 raw responses under `bridgeforge-state/s2-reuse-20261025-a1`. The helper logs progress,
checkpoints completed workers, verifies saved raw hashes on resume, and removes its checkpoint
after final result publication. This does not close production cancellation/recovery or parallel
resource tests. Human review savings were not measured. The owner accepted this measured opt-in
tradeoff as recorded above; defaults remain unchanged.

## Terminal validation

Full guarded coverage run: **2,723 tests, OK, 12 unchanged skips, 357.800 seconds**.
Checkout/probe hermeticity PASS. Coverage **83.1469862%** (previous 83.1289257%; unchanged
80% floor), new cache module 100% statement/branch coverage. The 12 focused cache/generated-index
tests pass. Ruff, generated documentation, roadmap lint, gates lint and local S2 links pass.
No test baseline, skip, qualification rule or safety policy was weakened.

An isolated temporary-source wheel build passes; the three changed/new module payloads match
the checkout byte for byte, no foreign namespace appears, and an isolated extracted-wheel import
and cache-isolation smoke passes. This is not a pip installation or second-machine trial.
Evidence: `full-suite-coverage.log`, `coverage.json`, `package-result.json`, `package.log` and
`validation.json` under the private measurement directory. An earlier regression invocation was
stopped to regenerate the function index; its interrupted log is preserved and is not passing
evidence. The terminal guarded run above started after regeneration and exited zero.

The custom coverage command was guarded directly; its full-suite log/coverage receipt is the
current validation authority for this slice. The older default `last-suite.json` remains the
historical S1 result, rather than being manually rewritten to impersonate another test run.
The production source addition changes evaluator identity. Preserved S1 receipts retain their
original identities; prepare fresh current-engine plans before any new qualification/archive
operation. Do not restamp old plans or observations to make them appear current.

The subsequent [bounded read-only portfolio trial](S2_PORTFOLIO_TRIAL.md) records serial/parallel
equality, measured resource costs and narrow private-harness cancel/failure controls. Production
portfolio integration remains next. Keep governed recipe/ruling promotion and its independent
evidence gates separate. Obtain the owner's separate decision before expanding defaults. The local opt-in tradeoff above is now
accepted; S2, S3 and S4 are not complete. LIVE TEST NOT PERFORMED in this slice.
