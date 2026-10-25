# S2 read-only measurement progress

## Owner scope, 2026-10-25

The owner explicitly approved S2_COHORT_PROPOSAL.md proposal 8c910c7a5c26ab3837c904b7948ad14c1fcb20c262fcdf0beaf6acbf1947df4c and selected "Measurement first; keep defaults". This authorizes the named 8 training/4 prospective holdout cases for read-only baseline/cache/portfolio measurement. It defers the worthwhile acceptance threshold until results are reviewed. No repair, live expansion, default increase, publication, support commitment or S1 acceptance is inferred.

## Baseline contract and artifacts

Raw root: ignored bridgeforge-state/s2-baseline-20261025-a1 in feat/s1-workspace-contracts. owner-decision.json records the explicit instruction; frozen-inputs.json binds all 12 exact private copies (2482 files, 69,552,605 bytes), explicit physical providers, copied core, JDK, Python, engine, target and host. Original source locations and complete file inventories remain private. The original proposal is retained unchanged. This is a fresh observation of already-revived working copies, not a before/after legacy revival or globally unseen sample.

Providers are explicit private byte-verified LazyLib 3.0.0, MagicLib and GraphicsLib copies. Antediluvians lacks selected revenantlib. AI War's GraphicsLib closure contains a version-constrained dependency that the current resolver does not establish. Both remain unresolved. No global provider fallback or metadata amendment is permitted. A resolved declared closure alone is not source authority, qualification, or runtime evidence.

The baseline uses serial fresh temporary workers with current scan_mod and compile disabled. Each case emits progress and a progress.Checkpoint record; raw scan responses are separate files. Three repeats are requested. There is no new analysis cache; application warm/cold cache modes and bounded parallel comparison are not yet measured. OS cache state is uncontrolled. Worker peak memory and human active-review time are NOT_MEASURED. Compile/live/whole-case qualification and qualified yield are NOT_EVALUATED by this scanner baseline. Finding counts do not establish correctness or acceptance.

The first 12-case scan pass produced 3196 findings without worker errors, with summed scan-worker time 150.579 seconds. Salvage Everything took 97.127 seconds; smaller cases took about 2-9 seconds each. This first pass was interrupted/resumed and is not an uninterrupted end-to-end portfolio timing. All three repeats and provider-preservation checks subsequently finished; the verification below supersedes the first-pass checkpoint. Strict private-input/context inventory capture is a separate setup cost and must not be hidden within a claimed scan speedup.

## Resume and limits

The private measurement helper is C:/Users/exxec/Documents/Project BridgeForge/scratch/s2-baseline.py. Execute it from the active worktree with the B3 research virtualenv Python and PYTHONPATH set to that worktree. It binds the recorded JDK internally. The original terminal attempt used the wrong checkpoint API; its uncheckpointed response is preserved. The corrected run then encountered a version-constrained provider dependency after seven completed cases; the next run retained that condition as unresolved and reused the completed checkpoints. Logs are s2-baseline-20261025-a1.log, -resume.log and -resume2.log. These are helper failures, not product scan crashes or successful cancellation/crash-recovery acceptance controls.

Exec session 26440 completed with exit 0; the independent verification/profile session 51222 also completed with exit 0. Neither process remains pending; do not poll or restart them as live work. Serial-N.json means that round completed and provider inventories matched. A partial JSONL alone does not prove a live process. Do not rerun on timeout. Before resuming, verify current engine, manifest, raw digests and physical inputs; preserve failed copies, raw responses and logs. The prototype is local measurement plumbing, not a new public CLI or authority store.

Next: use the verified baseline and training-only profile below to select the smallest useful reuse slice over existing R2 fingerprints. Measure worker memory/subprocess costs and maintain a serial reference before selecting any bounded parallel trial. Holdouts must not choose or promote recipes. S2.1 remains IN_PROGRESS; S2.2-S2.4 and S3-S4 are not complete. S1 reviewed compile and independent-handoff gates remain open.


## Completed serial reference and training-only profile

Three rounds each contain all 12 cases, 3196 findings, zero worker errors and the same two unresolved dependency contexts. The verifier compares every complete raw response as parsed JSON, not only finding counts, and compares input/split/selected providers/unresolved conditions/classification summaries for every row. All 36 raw-response hashes match their records. Exact equivalence PASS. Original/copy provider and mod inventories matched per round; the final verifier also rehashed core, JDK and Python and checked the current engine identity. Context preservation PASS. Manifest SHA256: ecf079598aa505196f607e23608e49ece1551269722b20ee406fa17c91b1cb36.

| Round | Summed worker seconds | Training worker seconds | Holdout worker seconds | Invocation elapsed seconds |
|---|---:|---:|---:|---:|
| 1 | 150.579 | 41.661 | 108.918 | 180.443 |
| 2 | 145.195 | 41.527 | 103.668 | 191.181 |
| 3 | 147.767 | 41.161 | 106.606 | 198.648 |

Round one's invocation elapsed covers only the final resumed invocation and is not whole-run elapsed. Summed worker durations include all checkpointed cases; rounds two and three ran uninterrupted. Invocation time also includes strict input/preservation hashing and publication, so it must not be substituted for worker-only timing. OS caches were uncontrolled; this is not an application warm-cache speedup result. No acceptance threshold or speedup conclusion is asserted.

Raw results: serial-1/2/3.json, raw-1/2/3/, baseline-verification.json. The corrected baseline-helper.py is retained with the private artifacts. The verifier/profiler is main BridgeForge scratch/s2-verify-profile.py; its log is bridgeforge-state/s2-verify-profile.log. No private payload or environment is committed.

AI War was profiled solely as a training case. cProfile produced 64,683,032 calls in 20.841 profiler seconds (21.055 command seconds), with exact raw-response equality to its unprofiled baseline. Source scanning was 7.785 cumulative seconds; JSON parsing 4.041; Java comment blanking 3.571; 14 subprocess calls 2.820; two vanilla API JAR inventory constructions 2.585; class parsing 2.533. These overlapping cumulative figures cannot be summed, and profiler overhead prevents a throughput comparison. The trace points to repeated immutable parsing/inventory work as a candidate for bounded reuse before adding workers; it does not authorize a particular cache or prove a benefit. Mutable legacy parsed-class objects must not be shared without isolation. Reuse must bind content/extractor context and preserve the existing R2 freshness authority, not turn cached facts into accepted evidence.

Training profile evidence: training-profile/scan.prof, cumulative.txt, response.json and result.json. Profile artifact SHA256: 4bf6981c124dc52d5412de8feaeac747cc7d01729ebf663e7ddcb75a1ef1d4a7. Holdouts were observed only for the prespecified baseline; no held-out recipes were selected/promoted. Peak memory, cold/warm cache equivalence, bounded parallelism and cancellation/failure controls remain open. S2.1 measurement is advanced, not operationally accepted; S2-S4 are incomplete.
