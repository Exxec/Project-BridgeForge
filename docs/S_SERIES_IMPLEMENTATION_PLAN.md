# S-series implementation plan

Owner instruction, 2026-10-24: "plan S series implementation then proceed to start S1". This authorizes planning S1-S4 and starting S1 implementation; later release acceptance, real-asset selection, game/save changes and publication retain their existing gates. The 2026-10-17 strategy remains the outcome definition. No calendar dates or version numbers are promised.

Implementation base: `docs/b6-closeout` (`8736e13a`), branch `feat/s1-workspace-contracts`. The B stack is published/validated but not all merged; this is a dependent implementation branch, not a change to main. Keep main, originals and unrelated worktrees intact. No PR creation, push or merge is included in this slice.

## Delivery order

| Slice | Deliverable and existing seams | Acceptance / dependency |
|---|---|---|
| S1.1 | Compatibility/policy map; bounded qualification profile design | Record differences among workspace/intake, validate, archive CLI/primitive, release and promotion before adapting them; profile enforcement waits for explicit supported-flow review |
| S1.2 | Read-only workspace view over both dialects | Open valid layouts without writes; refuse mixed layouts, traversal, junctions, overlapping roles and unsupported schemas; original selection is explicit or referenced, never guessed from a first match |
| S1.3 | Versioned case, candidate and receipt records | Stable case ID; exact selected bytes plus dependency/core/tool/policy context; changed inputs invalidate receipts; legacy provenance remains unknown; reuse scan registry/run-manifest/revise identities where semantics match |
| S1.4 | Shared qualification evaluator and selected caller adapters | Same declared profile/inputs give identical obligations/results; missing obligations remain INCOMPLETE; existing legacy APIs retain their meanings; compile/static/package/dependency/API/live/save dimensions remain separate |
| S1.5 | Prepare/run/finalize operation receipts | Exact staged identities; refuse post-test mutation; no final version bump; failure injection preserves originals/prior archives; retry/concurrent/stale operations cannot duplicate writes |
| S1.6 | Minimal operator flow, guide and pilot | Review CLI spelling before adding it; cover P1-P6 in NEXT_MILESTONE, both workspace forms, real eligible rig positive and drift negative; measure operator steps/active review/elapsed wait; independent resume and owner acceptance |
| S2.1 | Fresh cohort baseline and resolution snapshots | S1 accepted contracts; owner-selected training/holdout cohort, source/provider authority and denominators; no historical stored scan treated as fresh measurement |
| S2.2 | Content-bound analysis reuse | Explicit cache keys over all relevant inputs/tool versions; cold/warm equality, changed-input refusal and bounded memory; existing indexes remain rebuildable views |
| S2.3 | Governed recipe/ruling reuse | Executable preconditions, positive/refusal/idempotence tests, revocation and held-out review; MANUAL/UNKNOWN/save/balance gates unchanged; E2 stays disabled absent its independent gates |
| S2.4 | Resumable portfolio orchestration | Follow EXECUTION_EFFICIENCY_PLAN; read-only work parallel first, ordered mutation/ledgers/archives; three repeatable runs, cancellation/worker failure recovery; owner sets worthwhile measured improvement before defaults expand |
| S3.1 | Feature/behavior obligations and reference observations | S1 identities plus S2 provenance; known baseline versus unavailable reference explicit; expected deviations need scope/authority |
| S3.2 | Scenario families and impact selection | New-game/campaign/combat/integration families each have healthy and known-bug controls; uncertain impact widens tests or remains unresolved; reuse D-series/probe/scenario tools |
| S3.3 | Copied-save upgrade lineage | Explicit owner-authorized old-save load/migration/save/restart/reload/repeat; primary saves untouched; persistent identity/idempotence assertions; static XML/class checks never become runtime proof |
| S3.4 | Maintained qualification and regression feedback | Changed provider/rule/candidate reopens affected obligations; residual human test list; runtime findings become tested checks/recipes with healthy controls |
| S4.1 | Supported version/configuration contracts | S1-S3 outcomes; explicit offline/live tiers, migration/refusal behavior and declared toolchain; additional game target is a separate support investment |
| S4.2 | Private-payload exchange and recovery | License/local-only/credits survive export/import; corrupt/interrupted restore refuses safely; rebuild indexes and reproduce qualification in an isolated destination |
| S4.3 | Second-operator clean-machine trial | Independent setup/resume/recovery without hidden paths/hooks/chat; measure manual setup and operational limits |
| S4.4 | Support/release acceptance | Owner approves supported environments, retention, maintenance commitment and publication scope; CI portability and real live qualification reported independently |

```mermaid
flowchart LR
  A[S1.1 contracts] --> B[S1.2 workspace view]
  B --> C[S1.3 identities and receipts]
  C --> D[S1.4 qualification]
  D --> E[S1.5 operations]
  E --> F[S1.6 pilot acceptance]
  F --> G[S2 bounded production]
  G --> H[S3 lifecycle and upgrades]
  H --> I[S4 supportable kit]
```

## First supported lane and unresolved choices

Start with offline, read-only adaptation of a single RC8 revival workspace, supporting manifest and convention/intake physical layouts without relocating data. The eventual initial operator lane is local-maintainer qualification, not distributable publication. The proposed `rc8-local-new-game/v1` obligation design is in S1_CONTRACT_MAP.md; it is not an enabled approval policy. P5 save/persistence changes remain human-routed and cannot pass a new-game profile as upgrade qualification.

S1 may implement offline contracts before pilot selection. Before mutating integration/finalization, settle the supported entry points, exact qualification profile and local-archive policy. Real pilot identities/licenses, rig/reviewer capacity and scope are still needed for S1.6; no private mod or save is selected by this plan. S2-S4 are planned, not started or operationally accepted.

## Status and handoff

| Slice | State | Evidence / next action |
|---|---|---|
| S1.1 | Contract map recorded; qualification profile DESIGN_PENDING | S1_CONTRACT_MAP.md; review exact obligations before enforcement |
| S1.2 | Initial read-only adapter IMPLEMENTED OFFLINE | `bridgeforge/case_workspace.py`, synthetic `tests/test_case_workspace.py`; results in S1_PROGRESS.md |
| S1.3 | Case/candidate/receipt store IMPLEMENTED OFFLINE and validated | S1_CASE_RECORDS.md and S1_PROGRESS.md; generic receipts remain unverified |
| S1.4 | Read-only evaluator IMPLEMENTED OFFLINE and validated | S1_CASE_RECORDS.md; no legacy caller policy change |
| S1.5 | Prepare/run/finalize library IMPLEMENTED OFFLINE and validated | S1_CASE_RECORDS.md; private legacy archive adapter, exact retries/preservation |
| S1.6 | V2 validated with real P1 both-layout archives and P6 drift refusal; remaining pilot OPEN | S1_OPERATOR_GUIDE.md and S1_PILOT_EVIDENCE.md; finish reviewed repair/refusal/save-routing and independent pilot gates |
| S2.1 | READ-ONLY BASELINE STARTED, owner-approved 2026-10-25 | S2_COHORT_PROPOSAL.md and S2_PROGRESS.md; three serial baseline passes verified, defaults unchanged, threshold deferred; S1 acceptance remains open |
| S2.2-S2.4 | OPEN | Baseline/profile recorded; cache/resource/parallel/owner threshold gates remain |
| S3.1 | INITIAL READ-ONLY IMPLEMENTATION, owner-directed 2026-10-25 | S3_PROGRESS.md; exact case-bound static obligations, not operational acceptance |
| S3.2 | INITIAL OBSERVATION ADAPTER | S3_PROGRESS.md and S3_OPERATOR_GUIDE.md; approved cohort eligibility, bound catalogs/named runs and real narrow callback-control pair; broader family support remains open |
| S3.3, S4 | PLANNED | Keep save/operator/support gates separate |
| S3.4 | INITIAL RULE-REVALIDATION EVIDENCE | S3_GENERATION_CONTROL_EVIDENCE.md; changed rule refuses reuse of actual passing observation; full maintained qualification remains open |

Keep S1_PROGRESS.md updated with exact branch, checks, limits and resume instructions so another maintainer can continue without this chat. Every slice gets focused acceptance/refusal tests, full guarded regression, unchanged legacy CLI goldens, coverage/no-weakened-baseline checks, lint and an evidence receipt. No minimum automation percentage or speedup is invented. LIVE TEST NOT PERFORMED.


## Active S1-S4 goal (owner instruction, 2026-10-24)

"set goal for all S series, if need be run automated live test."

The active goal now covers implementation and validation of all S1-S4 in dependency order, not only S1. Automated live testing is authorized where required, using the dedicated isolated rig with its ownership, staged-input/run-manifest and existing policy checks. Inspect current rig/process ownership before staging; serialize GUI/live resources. Preserve originals, primary saves and prior archives. Ordinary implementation/verification may continue without per-slice confirmation; gameplay/save-content decisions, licence/publication, PR creation, main merges, second-operator evidence and owner support/acceptance commitments remain distinct gates. A synthetic/automated test does not impersonate an independent human operator.

Next: S1.3's content-bound candidate/receipt spine, followed by durable case records and qualification adapters. Reuse `copy_drift._collect`/`run_manifest.FILESET_ALGORITHM` for the shipped set only after validating physical payload boundaries. Retain scan-registry's broader analysis-input identity separately; generated reports must not invalidate shipped payload identity. Bind receipts to candidate AND explicit dependency/core/tool/rule/policy context; missing context/provenance cannot become acceptance. Keep decisions and evidence outside frozen payloads and test stale inputs, same-version drift, tampering, unsupported schemas, interruptions and retries before wiring mutations.
