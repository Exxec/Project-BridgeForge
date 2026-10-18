# Bounded execution and analysis reuse

S2 supporting specification, 2026-10-18. Owner request: "add to roadmap. Anything else like this we can improve or add?"
This approves recording the plan, not changing source, increasing live concurrency or changing qualification policy.
Read [VISION](VISION.md), [STRATEGIC_ROADMAP](STRATEGIC_ROADMAP.md) and [NEXT_MILESTONE](NEXT_MILESTONE.md) first.

## Outcome and current evidence

Process the supported portfolio faster without changing which repairs are authorized or which candidates qualify.
Measure useful completed work, elapsed time, peak memory and repeated work; worker count is not a success measure.
These are extensions to existing tools, not a new distributed execution platform.

Source inspected at `0e5183ef`; no performance benchmark or new live test was performed for this plan:

| Capability | Verified implementation | Proposed extension |
|---|---|---|
| Workspace concurrency | `revive_queue.py` uses `ProcessPoolExecutor` with `--jobs`; parent writes queue checkpoints and orders results | Common resource limits, input-bound resume and conflict ownership across callers |
| Game-variant concurrency | `java_matrix.py` uses `ThreadPoolExecutor`, accepts 1-3 parallel variants and creates instance rigs; `mass_test.py` processes targets/bundles in turn | Capacity-aware scheduling and explicit exclusive GUI resources; do not assume all live scenarios are parallel-safe |
| Corpus analysis | `corpus_audit.py` walks selected directories sequentially | Bounded independent mod-analysis workers with deterministic aggregation |
| Atlas | `atlas.py` builds mods sequentially, tracks indexed/unchanged work and resolves references after extraction | Parallel extraction only where measured worthwhile; retain coordinated database publication and global resolution |
| Resume and impact | `progress.py` checkpoints and `check_impact.py` exist | Extend their contracts; a completed checkpoint alone does not establish current input identity |

## Work packages for the implementing agent

### E1. Establish the workload and resource contract

Depends on S1 case/candidate identities and evidence receipts. Before modifying execution, trace the existing commands,
locks, checkpoints and writes. Record per-stage elapsed time, input size, subprocess time and peak memory where measurable.
Use a fixed, owner-authorized representative cohort, including a large jar case and many small mods. Report cold and warm
runs separately and retain a serial reference. Use synthetic fixtures in Git; keep proprietary measurements local.

Define jobs by immutable input/context identity, stage, output location and required resources. Record policy/scanner/tool,
selected provider/core/JDK identities and relevant options. A decision or observation is not interchangeable with extracted
facts. Preserve existing receipt formats through adapters or explicitly version new contracts.

Done when the owner can identify the actual dominant cost and approve a worthwhile improvement threshold and resource
budget. Do not invent a speedup target or default worker count before this measurement.

### E2. Avoid repeated analysis before adding workers

Reuse immutable parsed class/data inventories and provider-resolution facts across compatible commands. Extend the S2
resolution snapshot and item 75 R2/A2 fingerprints rather than creating a second cache authority. Key reuse by content
and all relevant analysis context, including extractor schema/version; names, modification times or mod versions alone
cannot establish equivalence. Generated reports must not invalidate their own inputs.

Keep an explainable dependency map from changed input to affected analysis stages/cases. Unknown impact triggers broader
recomputation. Report reused/recomputed/unavailable work and why. A cache miss or corrupt entry recomputes safely or reports
incomplete evidence; it never manufactures a pass. An unchanged static input cannot substitute for a required new live run.
Rebuildable caches are distinct from irreplaceable logs, decisions and observation receipts; cache cleanup must preserve those.

Done when cold and warm runs produce equivalent normalized findings, changed same-version providers/core/rules invalidate
affected results, and unrelated changes preserve only demonstrably independent reuse. Cover incomplete and corrupt entries.

### E3. Run independent work within bounded local capacity

Start with read-only corpus work and Atlas extraction if E1 shows a benefit. Reuse current executors before introducing
a common abstraction. Processes are candidates for Python-heavy analysis; threads can coordinate I/O and external tools.
Measure serialization, process startup and duplicated-memory costs on Windows as well as Linux.

Use a bounded pending queue and explicit CPU, memory, disk-heavy and game-slot budgets. One coordinator publishes shared
database transactions, ledgers and checkpoints; workers return bounded stage results. Sort normalized outputs independently
of completion order. Keep one mutating owner per resolved workspace; account for aliases/junctions and shared providers.
Do not parallelize dependent fix/rescan rounds within one case or let two commands silently own the same output.

Avoid nested executor oversubscription when queue workers invoke compilation or game jobs. Game instances require isolated
writable state; shared UI/focus automation requires exclusivity unless independence is demonstrated. Start with existing
live limits and policy. More parallel launches are not authorized by this plan.

Done when serial/parallel normalized results and qualification decisions agree, configured limits are observed, worker
failure leaves other completed receipts recoverable, and overlapping writers are refused or serialized explicitly.

### E4. Resume useful work and explain bottlenecks

Build on `progress.Checkpoint`, existing case locks and S1 recovery, not a separate job service. Distinguish queued,
running, completed, failed and blocked work. Bound retries to explicitly transient operations; do not retry an ambiguous
mutation blindly. Resume only completed receipts whose input/context identity still matches. Cancellation stops new work,
reaps owned subprocesses and records incomplete stages without abandoning a shared write halfway through publication.

Report time spent executing, waiting for resources, awaiting owner decisions and awaiting live qualification separately.
Expose the slowest stages and pending critical dependencies. Coalesce duplicate compatible read-only requests where useful;
do not merge distinct policies or live scenario obligations merely because their mod name matches.

Done when crash/cancel/restart controls neither duplicate mutations nor lose accepted receipts; stale work reruns; serial
mode remains available for diagnosis. Preserve per-item progress and partial checkpoints required by `CLAUDE.md`.

## Release acceptance and sequencing

S1 records identities, write ownership and a serial timing baseline; it need not build a scheduler. In S2, implement E1,
then measured E2/E3 slices, then E4 integration. Reuse and worker scheduling can proceed independently only after their
shared contracts are agreed. Select packages from measured bottlenecks, not a requirement to build every optimization.

Acceptance requires a declared comparable cohort and hardware, repeated serial/cold/warm/parallel measurements,
unchanged normalized findings and qualification outcomes, bounded peak resources and failure/recovery controls. Report
uncertainty and cases that become slower. The owner approves the worthwhile throughput/resource tradeoff before defaults
change. Report qualified-candidate yield and review/live backlog alongside speed so faster scanning cannot hide stalled delivery.

Risks include cache invalidation mistakes, disk saturation, worker memory duplication, database contention, non-deterministic
ordering, subprocess leaks and GUI interference. Tests must include changed inputs during work, duplicate aliases, worker
crashes, corrupted reuse entries and nested resource contention. No live or save compatibility claim follows from these tests.

Deferred: cloud/distributed workers, a generic workflow engine, global mutable caches, GPU rewrites, broad asynchronous
conversion, higher game-instance caps and parallel acceptance/archive publication. Human approval remains required for
resource/default changes affecting the dedicated rig, cohort access, and any expansion of supported live scenarios.
