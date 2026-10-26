# S2 production portfolio checkpoint, 2026-10-25

Implemented `portfolio-scan` over S1 case/candidate/receipt identities; see the
[operator guide](S2_PORTFOLIO_OPERATOR_GUIDE.md). Default one worker, explicit memory budget,
optional two-worker execution and opt-in parsing reuse. No repair, compile, live, archive,
qualification or global default expansion. Existing recipe/auto-accept policies are unchanged.

The approved eight training cases were copied into isolated physical workspaces and captured
as S1 candidates. Their `original` folders are frozen already-revived analysis inputs, not
historical legacy originals or before-repair evidence. Original corpus/provider copies remain
unchanged. The four prospective holdouts did not select tuning or recipes.

## Validation and real-cohort results

Corrected guarded suite: **2,741 tests, OK, 12 unchanged skips, 381.724 seconds**; hermeticity
PASS. Coverage **83.0990481%**, versus 83.1469862% before this implementation; the 80% floor
and test baselines remain unchanged. Worker subprocess behavior is exercised by actual process
tests although the parent coverage run does not collect subprocess line coverage. Focused tests
cover native descendant cleanup, abrupt coordinator death and kernel lock release, completion
recovery, idempotent store/output publication retry, cancellation, timeout/resource stop,
changed inputs/engine/artifacts, corrupt cache recomputation, duplicate/overlapping aliases,
CLI/schema refusal, Windows path limits and compact-name collisions.

The first actual coordinator-death trial exposed a Windows current-directory length limit.
Its failed log and earlier point-in-time timing records are preserved as non-passing control
evidence. Attempt names were shortened; full content identities remain in records and are
checked even when compact directory prefixes collide. Windows paths outside the tested native
limit now refuse before work with a shorter-output instruction. The regression suite and the
entire three-round production cohort were rerun after that fix.

| Round | One worker total seconds | Two workers total seconds |
|---|---:|---:|
| 1 | 93.700 | 78.252 |
| 2 | 93.092 | 77.326 |
| 3 | 94.534 | 78.731 |

Median end-to-end elapsed reduction: **16.5%**. These totals include input verification and
receipt publication, unlike the earlier scanner-only/private-harness timings. Median preflight
was 27.5/27.7 seconds; postflight was 27.7/28.2 seconds for one/two workers. Integrity checking is
a substantial remaining bottleneck; its bytes are not silently replaced by timestamp freshness.
OS caches are uncontrolled. These are one local host and historical training cases.

Maximum sampled worker/descendant RSS: **253.719 MiB serial / 441.570 MiB parallel**, below the
explicit 768 MiB trial stop threshold; coordinator memory is additional. Maximum active workers
matched the configured one/two caps. Sampling is not a hard OS memory limit.

Every complete raw response matches across all six fresh production runs. A repeated completed
run reused all eight receipts and launched zero workers. A real production coordinator was then
killed after one durable completion; three owned descendant processes were observed and all
terminated. Kernel ownership released, and the next command recovered that completed scan and
analyzed the other seven. Its complete responses match the serial reference. Inputs and engine
are independently rechecked by every command before publication. This is an actual coordinator
death control, not just a simulated return code.

Whole-wheel validation: four added production modules and only `cli_commands.py`/`progress.py`
changed against the preceding parsing-cache wheel; all other runtime payloads are byte-identical,
every packaged Python file matches the source and no foreign namespace appears. Isolated
extracted-wheel import/help passes. Pip installation and hosted CI were not performed here.

## Outcomes and remaining gates

Eight training cases: **160 findings = 55 SAFE, 102 REVIEW, 3 MANUAL**. Six explicit dependency
closures resolve; Antediluvians and AI War retain their two known incomplete contexts. No finding
was fixed, suppressed or automatically accepted. Qualified yield is NOT_EVALUATED, active human
review time is NOT_MEASURED, and false-acceptance precision cannot be estimated from zero applied
cases. No recipe or standing ruling was promoted from this experiment.

A fresh read of the eight raw responses confirms that **31 of the 55 SAFE findings are
`json-hash-comment` observations whose scanner explanation explicitly recommends retaining the
bytes**. `SAFE` is a finding classification, not a count of approved or useful repairs. The next
most frequent SAFE id, `declared-dependencies`, occurs four times. The 61 trailing-comma
findings are REVIEW and the earlier owner ruling retained at least one metadata file unchanged.
These denominators cannot support a claimed recipe-application yield or active-review saving.
S2.3 needs an independently selected, reviewed actionable shape and consent to apply it; the
read-only cohort decision does not supply that authority.

The owner accepted the separate local parsing tradeoff ("Accept the opt-in tradeoff"); this
checkpoint does not broaden that into full S2 acceptance or a default resource policy. Remaining
S2 outcomes include governed real recipe/ruling application evidence, comparable active-review
measurements, independent review of applied cases and qualification/live yield. The cohort's
read-only permission still forbids treating this result as repair approval. S2 remains open.

Private evidence: `bridgeforge-state/s2-production-20261025-a1/` contains `validation.json`,
`production-measurement.json`, `production-summary.json`, `cohort-outcomes.json`, per-run summaries,
attempt artifacts, the corrected full-suite/coverage and wheel audit. Engine identity:
`76b797a9b72f7e85e435ffeea30edbf43bb1be91a785f9e7abbc326d5871b810`.
Later S3/S4 source changes produce a new evaluator identity; retain this checkpoint historically
and do not restamp its receipts. Preparation timing was not measured; placeholder staging progress
durations are explicitly excluded from performance evidence. LIVE TEST NOT PERFORMED.

The 2026-10-25 shared qualification-worker ownership fix postdates this benchmark. It changes
the evaluator engine identity; this table is the exact earlier read-only portfolio run and was
not remeasured after that fix. The elevated full guarded suite after the fix passed 2,761 tests
with 12 unchanged skips and hermeticity PASS; see [S2_PROGRESS.md](S2_PROGRESS.md).
