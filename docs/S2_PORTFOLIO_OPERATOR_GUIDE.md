# Read-only candidate portfolio analysis

`portfolio-scan` implements S2's bounded analysis/recovery lane over existing S1 cases. It
performs no repair, compile, live launch, qualification, archive or automatic recipe application.
Scanner findings and unresolved dependency conditions remain visible. `COMPLETE` describes the
selected analysis jobs; it never means a qualified or accepted revival.

Prepare a schema-1 selection file with `cases`, each containing only `case_id` and `candidate_id`
from the existing `case open/capture/status` flow. Use physical, preserved workspaces and explicit
bound providers/core/Python/JDK. Unknown provider selection refuses; an explicitly selected but
unresolved closure remains reported as incomplete. The initial target is the existing RC8
local-new-game profile; broader qualification profiles are not inferred.

```powershell
python -m bridgeforge portfolio-scan selection.json --store CASE_STORE --output PRIVATE_OUTPUT --memory-mib 768 --jobs 1 --json
```

Default worker count is one; parsing reuse is off unless `--reuse-parses` is supplied.
`--jobs 2` is an explicit bounded option, not a global concurrency/default increase. The required
memory budget is a sampled aggregate worker/descendant RSS stop threshold; coordinator memory
is additional and brief peaks can exceed it before the next sample. The trial used 768 MiB,
not an approved default for every host. `--timeout` bounds each worker (default 900 seconds).
Parsing reuse retains at most 32,768 entries and 64 MiB serialized payload per worker, with
additional interpreter/caller/container memory. No game or compilation slots are available.

Output must be separate from all workspaces, selected inputs and the case store. Duplicate or
overlapping workspace aliases and linked physical inputs refuse before scanning. A kernel lock
allows only one coordinator for an output directory and releases on process death; its persistent
`.portfolio-lock` file is not a stale ownership claim and must not be deleted to steal a live lock.
Readonly scans in separate output directories are not governed by a machine-wide resource broker.
Windows output roots must leave room for the native worker directory limit; an overly long
root refuses with a shorter-output instruction. Compact attempt directory names are storage
labels only: full content identities and receipt subjects still prevent cross-candidate reuse.

Inputs are content-checked before work and again before receipt publication. Shared context trees
are hashed once per validation pass. A changed candidate requires a new S1 capture. Engine hashes
are checked in the coordinator and each worker. Completion/artifact digests bind exact candidate,
context and engine; neither file timestamps nor a same-version label establish freshness.

Windows workers belong to a kernel kill-on-close job before their startup gate opens. POSIX
workers use owned sessions and a parent watcher. Cancellation, timeout and resource stops close
only owned workers. Ctrl+C leaves completed artifacts and unfinished work available for recovery.
Actual Windows process-death/descendant/lock-release controls are tested; Linux execution remains
a separate platform validation gate.

Every attempt has a unique directory. Successful raw output and metrics get a durable completion
record before checkpoint publication. A stopped coordinator can recover that completion without
rerunning its scan, then revalidate current inputs and publish the existing S1 receipt. Publication
timestamps are stable across retry, including a stop between store and output publication.
No worker writes shared case receipts or checkpoints; the coordinator publishes them serially.

Repeat the same command to resume. `ANALYZED` means a fresh scan was completed, `RECOVERED` means
completed work was finalized after interruption, and `REUSED` means a prior verified analysis
receipt was selected. These all remain `qualification: NOT_EVALUATED`. Final S1 qualification
continues to run its independent checks and does not accept these generic analysis receipts as
proof of safety or live behavior. Corrupt or unavailable cached artifacts are preserved and
recomputed in a new attempt. Observed input/engine/artifact drift invalidates that attempt even
if its bytes are later restored. Failed/timed-out/cancelled/queued cases remain incomplete.

Per-item progress uses the existing progress reporter; `--quiet` suppresses it. The existing
checkpoint records partial progress; durable completion records also recover the window before
checkpoint append. Final run summaries are append-only under `runs/`, sorted by case identity,
and record preflight, postflight, total elapsed time and sampled resources separately. A complete
run removes its partial checkpoint while preserving attempts, receipts and prior run summaries.

Production validation and measured cohort results are recorded in [S2_PROGRESS.md](S2_PROGRESS.md).
The earlier private trial remains [historical measurement](S2_PORTFOLIO_TRIAL.md), not proof that
this implementation already passes all S2 outcomes. Governed recipe promotion, review burden,
qualified yield, owner support and S3/S4 gates remain separate.
