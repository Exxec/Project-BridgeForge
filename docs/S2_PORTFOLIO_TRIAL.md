# S2 bounded read-only portfolio trial

Subsequent production implementation and validation are recorded in
[S2_PRODUCTION_PORTFOLIO.md](S2_PRODUCTION_PORTFOLIO.md). This document retains the earlier
private harness results and their narrower timing scope; its production-open notes are historical.

The approved [cohort](S2_COHORT_PROPOSAL.md) permits bounded read-only portfolio measurement
with unchanged defaults. The owner accepted the [local parsing tradeoff](S2_ANALYSIS_REUSE.md)
on 2026-10-25; that approval does not approve portfolio concurrency or overall S2 acceptance.

This is a private measurement harness, not a production portfolio command or a generic workflow
engine. It uses the same eight frozen training cases, explicit providers, copied core, JDK,
Python, engine and opt-in parsing limits as the prior experiment. No holdout selects tuning.
No repair, compile, game, save, qualification, archive or release action is performed.

Three alternating-order serial/two-worker rounds run one application-cold scan per case in
fresh subprocesses. Maximum pending/running workers is two; there is no pre-submitted whole
queue or nested worker executor. Existing scan helper Java subprocesses can overlap up to two
analysis workers; no game slots or compilation jobs are assigned. The experimental aggregate
worker/descendant RSS stop threshold is 768 MiB, sampled every 25 ms. This is a cooperative
measurement stop threshold, not a hard OS memory guarantee or new command default.

One coordinator owns shared checkpoint/result publication. Every worker writes only unique
private attempt files. Canonical frozen workspace paths must be distinct. An exclusive private
lock refuses a second coordinator for the same run folder; crash recovery of that lock is not
automated. Completed responses bind the request digest and raw response digest, and the
checkpoint header binds the exact input manifest, engine, helper, parsing capacities and worker
count. The existing `progress.Checkpoint` handles completed-item resume. Final result ordering
is independent of worker finish order. Whole-trial restart automation is not a product feature.

Prespecified controls interrupt after one successful scan while a planted worker and its child
are running, then resume completed receipts; terminate one worker with exit 17 while others
complete, then retry only the failed case; and change context on an interrupted run to refuse
its old receipts. Faults are confined to the private harness, never mod code or payload bytes.
All worker launches are owned; cancellation/timeout reaps only their process trees.

Complete raw responses must agree across all rounds, controls and the preserved prior current-
engine reference. Source/copy/provider/core/JDK/Python/engine preservation is checked before
and after. Actual failed/cancelled attempts and partial results remain available. Measurements
and controls do not establish production orchestration, mutation safety, qualification yield,
governed recipe promotion or S2 completion. Raw root: ignored
`bridgeforge-state/s2-portfolio-20261025-a1/`; terminal results are recorded below when available.

## Terminal results, 2026-10-25

All three rounds completed with eight cases each. Results are sorted by workspace independently
of finish order. Every complete response matches across serial/parallel modes and the preserved
current-engine parsing reference. Source, copy, providers, core, JDK, Python and engine
preservation PASS. No qualified-candidate yield was evaluated.

| Round | One worker elapsed seconds | Two workers elapsed seconds |
|---|---:|---:|
| 1 | 32.151 | 17.735 |
| 2 | 31.413 | 17.878 |
| 3 | 31.019 | 17.834 |

Median portfolio elapsed reduction: **43.2%**. Timings include worker startup, analysis,
private result publication and coordinator polling, but exclude pre/post preservation hashing.
They are not comparable to prior summed scan-only timings without that distinction. OS caches
remain uncontrolled; mode order alternates and this remains one local historical training cohort.

Maximum observed active workers: one/two, exactly the configured limits. Maximum sampled
aggregate worker/descendant RSS: **255.660 MiB serial / 460.605 MiB parallel**, below the
experimental 768 MiB stop threshold. Coordinator memory is additional. Sampling can miss
short-lived peaks; this is not an owner-approved default or a guaranteed OS memory ceiling.

Controls PASS:

- Cancelled after one completed receipt, stopped the other owned worker tree and its planted
  child, retained the completed receipt, then resumed without rerunning it.
- One worker exited 17 without a successful receipt; two others completed. Retry reused those
  two receipts and reran only the failed case.
- A changed checkpoint context reused zero old receipts and recomputed all three selected cases.
  This is a synthetic context-key control, not a claim that real provider/rule drift was tested.
- A syntactically valid altered raw response was refused before any worker launch. Its original
  bytes were backed up; explicit restoration of that control response allowed resume. Automatic
  corrupt-record repair is not implemented.
- A pre-existing self-authored coordinator lock was refused before any worker launch, retaining
  its bytes. This tests the lock refusal, not a real second-operator or stale-lock recovery trial.

Artifacts: `portfolio-result.json`, `summary.json`, `refusal-controls.json`, `pilot.log`,
per-run attempt receipts/raw responses and preserved partial results. Cancel/crash checkpoints
were removed after their successful resumed final result; failed attempt stderr and planted-child
markers remain. The private harness is not a supported production scheduler. It does not yet
provide automatic stale-coordinator recovery, selective per-input invalidation, production alias
ownership tests, real changed-provider/rule controls or machine-portability evidence.

No production/test source changed in this continuation; engine identity still matches the
previous guarded **2,723 tests/12 unchanged skips PASS**, 83.1469862% coverage and isolated wheel
validation. Those checks were not rerun or re-dated. Current private controls are fresh executions.
Ruff, generated docs, roadmap/gates lint and links are checked separately after this report.

Next: integrate an explicit bounded read-only portfolio operation with input ownership,
recoverable coordinator state and resource reporting, then validate its production refusal and
recovery contracts. Reuse the existing executors/checkpoints rather than introduce a generic job
service. Governed recipe/ruling promotion remains separate. Defaults remain unchanged;
S2-S4 are incomplete. LIVE TEST NOT PERFORMED.
