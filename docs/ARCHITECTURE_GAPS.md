# Architecture assessment and strategic gaps

Inspected 2026-10-17 at `3342654d`. This is a bounded architectural review, not an exhaustive semantic audit of every
check or every private mod. No application source changes or new game runs were performed for this review.

Evidence labels used below:

- **Inspected:** directly read implementation or performed a bounded read-only check in this review.
- **Verified automation:** relevant code/tests exist and the inspected baseline has passing automated evidence.
  This does not establish that all supported scenarios ran in a real game.
- **Recorded live:** a dated local report/roadmap cites a run; this review did not replay it or independently requalify
  its original artifacts. It is stronger than a plan, but its scope and provenance limits must remain visible.
- **Partial:** useful implementation exists, but the end-to-end capability or acceptance is incomplete.
- **Planned:** specification exists; the desired behavior was not established by inspected code.
- **Inference/proposal:** architectural conclusion or future design, not an implementation claim.

## Evidence ledger

Links identify concrete inspection points; identifiers E01-E15 are local to this assessment.

| ID | Finding and evidence | Limit |
|---|---|---|
| E01 | [Charter](PROJECT_CHARTER.md), `CLAUDE.md`, local `AGENTS.md`: evidence-first legacy Starsector revival; copy-only work, classification, rig and owner boundaries | Product intent and authorization, not runtime proof |
| E02 | [Package metadata](../pyproject.toml), [CLI registry](../bridgeforge/cli_commands.py), tracked-file inventory: version 0.3.0, 204 Python package modules, 200 `tests/test_*.py` files, 164 registered top-level commands | Nested commands are not counted; command count is not useful workflow coverage |
| E03 | [Scanner](../bridgeforge/scanner.py), [models](../bridgeforge/models.py), `scan_*.py`, [report writer](../bridgeforge/report.py): rich inventory/findings and shared scan facade | Top-level `ScanResult.manifest()` has a tool version but no `schema_version`; bounded read-only check confirmed this |
| E04 | [Manifest workspace](../bridgeforge/workspace.py), [pipeline](../bridgeforge/pipeline.py), [validation](../bridgeforge/validate.py) use `workspace-manifest.json`, `original-reference` and `working-copy`; [intake](../bridgeforge/intake.py)/[revive](../bridgeforge/revive.py) use `original` and `working` | Real Zorg workspace has `working/mod_info.json` and no workspace manifest. Existing adapters do not establish a single workflow contract |
| E05 | [Revive](../bridgeforge/revive.py), [fixers](../bridgeforge/fixers.py), [tiers](../bridgeforge/automation_tiers.json), `tests/test_revive.py`/`test_fixers.py`: bounded scan/fix/rescan and agent/owner packets | UNATTENDED_DONE explicitly hands off to live testing; it is not an overall compatibility verdict |
| E06 | [Escalation](../bridgeforge/escalation.py), [review](../bridgeforge/escalation_review.py), their tests: sandbox copies, allowed files, scan delta, attempt ledger and reviewed application | `verify` returns scan-relative PASS/FAIL and a compile-checked flag; general semantic correctness and planned E2 applicability gates are not supplied by that result |
| E07 | [Provider proposals](../bridgeforge/substitutes.py), [library registry](../bridgeforge/library_registry.py), [lineage](../bridgeforge/lineage.py), `cmd_corpus.py`: dependency/provider/authority tools exist | Provider symbol coverage and a greedy proposal are not complete interoperability or runtime load-order proof |
| E08 | [Behavior discovery](../bridgeforge/behavior_discovery.py), [D-series status](D_SERIES_IMPLEMENTATION_STATUS.md), `tests/test_behavior_discovery.py`: archaeology, hypotheses, expected changes, imported baselines and differential gates | Code explicitly distinguishes checked domains from runtime registration/generated references/external integration; D2 imports observations, not proof that a game ran |
| E09 | [Live driver](../bridgeforge/live_run.py), [probe groups](../bridgeforge/probe_group.py), [Java matrix](../bridgeforge/java_matrix.py), `probe-mod/`: controlled boot/new-game/combat/duel mechanisms | Fixed client-area coordinates and expected log markers constrain supported UI flows; Windows rig execution is different from portable Python tests |
| E10 | [Live acceptance](../bridgeforge/live_accept.py), [trust](../bridgeforge/live_trust.py), [scan statistics](../bridgeforge/finding_stats.py): acceptance/record hashes and stored scans exist | Run member hashes are computed from working files at record time; `_latest_scan` discovers only `scan-*` folders. Planned item 75 R1/R2 address stronger provenance |
| E11 | [Release](../bridgeforge/release.py), [promotion](../bridgeforge/promote.py), [archive](../bridgeforge/archive.py), [archive CLI](../bridgeforge/cmd_archive.py): several packaging/release paths with tests | `release_mod` defaults behavior evidence off; CLI release/promotion request it. Archive CLI/group callers apply `archive_gate`; the archive primitive has a different contract. These are not one qualification policy |
| E12 | [Save compatibility](../bridgeforge/save_compat.py), [inspection](../bridgeforge/save_inspect.py), [scenarios](../bridgeforge/scenarios.py), [impact plan](../bridgeforge/test_plan.py): read-only save evidence and rule-based scenario/test selection | Class/ID resolution is not full serialized-state or gameplay compatibility; path-pattern impact selection is not a complete behavioral dependency model |
| E13 | [Packs](../bridgeforge/packs.py), [migration contract](MIGRATION_PACK_CONTRACT.md), `tests/test_packs.py`: versioned pack discovery and evidence requirements exist | Existence of a pack/target string is not a tested target-support matrix |
| E14 | [CI](../.github/workflows/ci.yml), [test guard](../bridgeforge/test_guard.py), [goldens](../tests/test_cli_golden.py): cross-platform Python checks, Java setup, coverage floor, hermeticity and CLI compatibility tests | Recorded local baseline validation: 1,886 tests, OK, five skips; local-only record `bridgeforge-state/validation/roadmap75-20261017/last-suite.json`. [CI run 39093112172](https://github.com/Exxec/Project-BridgeForge/actions/runs/39093112172) was rechecked successful for `3342654d`, all 12 jobs. Full suite not rerun for this documentation-only review |
| E15 | Git history from initial `dad3aeb8` (2026-08-31) through `3342654d` (2026-10-17): scanner/workflow growth, CLI/scanner splits, per-mod fixes, CI corrections, automation specs | Recent commit frequency is not a staffing or 24-month delivery forecast. Live history is mostly local/operator-specific |

GitHub queries on 2026-10-17 returned zero open issues and zero open pull requests (limits 100/50). That is not a claim
that there is no backlog: `ROADMAP.md`, `docs/LOCAL_HANDOFF.md`, private reports and owner packets carry unresolved work.
Local state and corpus totals were not rescanned; the 2026-10-14 figures in the automation plan remain historical.

## Capability assessment

| Capability | Current assessment | What is still needed |
|---|---|---|
| Offline scan, bytecode/data/reference inspection | Implemented with automated evidence (E03/E14) | Stable input/context identities and explicit supported analysis domains |
| Copy-preserving intake and manifest workspace | Both implemented/tested, mutually different workflow forms (E04) | One logical case view; non-destructive compatibility adapters |
| Mechanical revival and escalation | Implemented/tested; full owner-independent lifecycle partial (E05/E06) | Durable decisions, final-candidate receipts and policy-checked continuation |
| Provider/source-authority diagnosis | Implemented tools; environment qualification partial (E07) | A reusable resolution snapshot consumed by build, scan, test and acceptance |
| Behavioral discovery and differential evaluation | Implemented offline tooling; runtime coverage partial (E08) | Curated observation/scenario families and original-to-revived qualification |
| Boot/probe/duel/matrix execution | Implemented/tested plus recorded local live use (E09) | Stable run provenance, lifecycle coverage and explicitly supported drivers |
| Qualification, release and archive | Implemented paths; unified semantics partial (E10/E11) | A shared applicability/policy contract and unchanged tested candidate |
| Existing-save support | Useful inspection tools; qualification partial (E12) | Reusable upgrade/reload and persistent-state invariants; human-authorized migrations |
| Self-reviewing E2 automation and R1-R8 refinements | Planned extensions (items 73/75) | Implementation, negative controls, independent acceptance; not inferred from existing commands |
| Portable maintained product operation | Portable offline CI; operational support partial (E13-E15) | Clean-machine setup/restore and a declared support policy |

Recorded live examples include the 2026-10-12 environment screen and selected probe/duel runs in the roadmap.
The latest Zorg/EPTA revisions explicitly remain LIVE PENDING in [their handoff](OWNER_MOD_FOLLOWUP_2026-10-17.md).
Neither historical archives nor a passing Python suite establish that these current revisions were played.

## Strategic gaps, rather than a list of cleanup tasks

### G1. No single revival case across the implemented workflows

**Inspected:** E04/E11. Workspace dialects, report locations and completion concepts differ. Some APIs accept a mod
root, others a workspace or rig. The operator supplies much of the integration through command sequence and local knowledge.

**Consequence:** more commands can increase operator burden; future automation could coordinate incompatible notions
of READY. **Proposal:** a case descriptor and stable candidate/evidence references over existing tools. Preserve physical
layouts and low-level APIs; introduce adapters and one operator-facing qualification flow. This is S1's central capability.

### G2. Evidence is rich but does not yet form one reusable decision record

**Inspected:** E03/E06/E10/E11. Artifacts mix dictionaries, strings, versioned records and unversioned manifests.
Evidence freshness and gate applicability are encoded differently. Some policy is enforced by callers rather than a
shared boundary. This is an architectural limitation, not proof that every current release can bypass its CLI gate.

**Consequence:** automated reuse or cross-project consumption may overstate what was checked. **Proposal:** a small
versioned envelope for input identities, tool/profile identity, evidence kind, applicability, outcome, subject and
supersession. Adapt existing artifacts; do not replace every schema or introduce a universal event platform. S1-S2.

### G3. Environment resolution is distributed across subsystems

**Inspected:** E05/E07/E09/E13. Libraries may be discovered from the queue, rig and outside provider sources; compiled
classes can shadow loose source; target behavior includes core, launcher and dependencies beyond `TargetProfile`'s two fields.

**Consequence:** a build/scan result can depend on ambient machine state that another operator cannot reproduce.
**Proposal:** a candidate-scoped resolution snapshot with provider provenance, exact selected versions/hashes, authority
and conflicts/unknowns. Reuse indexes as lookup aids, not an unchecked source of truth. Start explicit manifests in S1;
deepen shared analysis/resolution in S2. A general package solver is not required initially.

### G4. The automation loop measures syntactic progress better than preserved intent

**Inspected:** E05/E06/E08/E12. Verifiers can confirm disappearance of a finding and absence of selected new findings;
they cannot infer functional equivalence from that alone. Counts-only coverage is intentionally conservative.

**Consequence:** optimizing cleared findings can reward feature removal or hiding the symptom. **Proposal:** bounded
recipe eligibility, benchmark/holdout cohorts, explicit before/after behavior obligations, regression/abstention feedback,
and reviewed promotion to deterministic rules. S2 grows automation only within demonstrated domains; S3 expands qualification.

### G5. Lifecycle and upgrade qualification are not a reusable product capability

**Inspected:** E08-E12; recorded missing reload/raid/player-present paths in local handoffs. New-game boot, combat probe,
long campaign, modded integration and save upgrade exercise different states. A known save class is necessary but insufficient.

**Consequence:** a revived mod can work initially yet fail after saving, loading, raiding or interacting with another mod.
**Proposal:** reusable scenario families with preconditions, expected invariants, lineage, negative/healthy controls and
recorded residual human work. Original runtimes may be unavailable: preserve uncertainty rather than fabricate parity. S3.

### G6. Knowledge is durable locally, but not yet a governed reusable compatibility capability

**Inspected:** E07/E08/E13 and dated `RC8_BEHAVIOUR.md`. Rules, owner rulings, API facts and per-mod fixes exist, but the
new promotion/semantic-predicate mechanisms remain planned. Library symbol availability does not establish intent or license.

**Proposal:** versioned recipes/rulings with provenance, tested preconditions, revocation and affected-case requalification.
Maintain exact original credits, the RevenantLib boundary and local-only restrictions. Automatic learned behavior or
cross-mod inference without evidence is excluded. S2-S3; build on item 73 rather than a separate AI memory service.

### Audit addendum: S1 archive-preservation blocker (2026-10-18)

Direct source inspection found that `archive_mod(..., refresh=True)` invokes `_remove_previous_archive`, which
calls `safe_rmtree`, while the owner contract requires preserving the old artifact. DOC-001 in `BUGS.md` records
the affected standalone/group refresh paths. This is a current implementation conflict, not merely a future
enhancement. Do not use refresh on known-good archives; S1 finalization must correct and test preservation before
relying on that path. The distinct non-refresh `move_aside=True` path does not establish safe refresh behavior.

**Update 2026-10-18:** DOC-001 was fixed the same day: `refresh=True` now moves the old archive to
`Done/_replaced-<date>/` and restores it if the new write fails (`tests/test_archive_preserves.py`). The text above
records the state at audit time. It has not been exercised on a real `Done/` archive.

### G7. Operation still depends materially on one workstation and local state

**Inspected:** E04/E09/E15, absolute local setup/hook conventions, private corpus and ignored rig/state files.
Offline CI portability does not qualify live execution on every OS. Snapshot implementation exists, but restore
qualification and transferability are separate requirements.

**Proposal:** stable installation/configuration, profile support tiers, compatible artifact readers, restore exercises
and a second-operator acceptance. First freeze a useful supported surface; do not promise all historical game builds. S4.

## Technical debt and supporting decisions

Measured module sizes: `fixers.py` 3,899 lines, `behavior_discovery.py` 1,272, `dossier.py` 1,076 and `probe_group.py` 935.
CLI dispatch is already separated, and scanning has family modules behind a facade. These are useful seams.
Targeted extraction of code touched by a milestone is justified; another repository-wide rewrite is not.

Other debt includes dynamic dict/string contracts, overlapping lifecycle/status conventions, direct writes remaining
behind a safe-I/O ratchet, accumulated local configuration, and historical plans mixed with current status. Existing
item 70/75 work addresses parts of this. Treat the debt as constraints on strategic outcomes, not an unlimited release
backlog. Keep public CLI/artifact compatibility tests while converging internals.

## What is assumed, unknown or requires an owner decision

- **Assumption:** maintainers remain the primary users and offline operation remains a product requirement.
- **Proposal pending approval:** S1-S4 scope and the initial supported cohort, not a promise to port every queued mod.
- **Unknown:** sustainable development/reviewer capacity, available rig hours, acceptable evidence storage and owner time.
- **Unknown:** automation success/precision on a fresh representative cohort and causes of current manual effort.
- **Unknown:** which original runtimes/mod versions can legally and practically supply differential live baselines.
- **Owner decisions:** permissible feature deviations, licensing/distribution, save-changing repairs, new target/OS support,
  and release policy exceptions. No strategic document grants blanket approval for these.

No conclusion here depends on an exhaustive corpus scan, exact present archive count, or an assumed inference that
unreferenced code is dead. Follow the reference/evidence rules in `AGENTS.md` for any future implementation.

Recommended response: [S1-S4 roadmap](STRATEGIC_ROADMAP.md), beginning with
[one reproducible revival case](NEXT_MILESTONE.md), not another disconnected tranche of scanner rules.
