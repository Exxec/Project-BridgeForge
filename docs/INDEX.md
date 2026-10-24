# Documentation entry points and authority

Audited 2026-10-18. This index supports strategic S1 and item 75 R7 by separating current operating guidance,
proposed work and dated evidence. It does not implement the case lifecycle or renew any mod's live acceptance.

## Start here

- [README](../README.md): installation, checkout versus published version, workflow distinction and known limitations.
- [Architecture](../ARCHITECTURE.md): source-audited module/command/workspace map.
- [Revival guide](BRIDGEFORGE_REVIVAL_GUIDE.md): current operator commands; use `--help` for exact options.
- [Commands](COMMANDS.md) and [checks](CHECKS.md): generated references; validate with `python -m bridgeforge docs-index --check`.
- [Current status](ROADMAP_STATUS.md) and [local handoff](LOCAL_HANDOFF.md): evidence state and local tasks, not blanket completion claims.
- [Bug ledger](../BUGS.md): DOC-001 (archive refresh deleted the old archive) was fixed 2026-10-18 and moves it to `Done/_replaced-<date>/`; not yet exercised on a real `Done/` archive.

## Direction, governance and implementation plans

- [Charter](PROJECT_CHARTER.md) and [CLAUDE.md](../CLAUDE.md): purpose and committed repository/agent rules.
  The local `AGENTS.md` additionally governs owner decisions/model routing; it is intentionally not shipped in Git.
- [Vision](VISION.md), [strategic roadmap](STRATEGIC_ROADMAP.md), [next milestone](NEXT_MILESTONE.md) and
  [architecture gaps](ARCHITECTURE_GAPS.md): S1-S4 direction and dated evidence; current S1 authorization/scope is recorded in the implementation plan, while later acceptance and publication remain gated.
- [Active roadmap](../ROADMAP-3.md): the only current tactical backlog. Earlier decisions/history remain in
  [archived page 1](archive/ROADMAP.md) and [page 2](archive/ROADMAP-2.md). [docs/ROADMAP.md](ROADMAP.md) and
  [completion log](ROADMAP_COMPLETION_LOG.md) are historical tranche records, not competing current backlogs.
- [Automation plan](AUTOMATION_PLAN.md), [item 75 implementation handoff](ROADMAP_IMPLEMENTATION_HANDOFF.md),
  [hardening plan](HARDENING_PLAN.md): tactical specifications. Items 73 and 75 were implemented offline on 2026-10-18 (per-item
  status lines in each; table in [ROADMAP_STATUS](ROADMAP_STATUS.md)); their live acceptance is pending.
- [Feature tracing and transplant plan](FEATURE_TRANSPLANT_PLAN.md): ROADMAP-3 item 84 design note (long term,
  not built; starts after item 83 B3).
- [Execution efficiency plan](EXECUTION_EFFICIENCY_PLAN.md): S2 bounded concurrency, analysis reuse, resource budgets
  and recovery; extends implemented workers without changing qualification or live-run policy.
- Local `docs/REVIVAL_WORKFLOW.md` and revival/escalation templates: complexity, routing and plan requirements.
  Some workflow/templates are local-only; GitHub readers must not infer that their missing local evidence exists.

## Evidence and domain contracts

- [RC8 facts](RC8_BEHAVIOUR.md), [bug classes](BUG_CLASSES.md), [scanner evidence](SCANNER_EVIDENCE_MODEL.md),
  [JSON policy](JSON_COMPATIBILITY_POLICY.md), [bytecode boundary](BYTECODE_BOUNDARY.md).
- [Dependency strategy](DEPENDENCY_STRATEGY.md), [migration-pack contract](MIGRATION_PACK_CONTRACT.md),
  [expected changes](EXPECTED_CHANGES_FORMAT.md), [live trust design](LIVE_TEST_TRUST_DESIGN.md).
- [D-series status](D_SERIES_IMPLEMENTATION_STATUS.md), [reference-rig status](P10_REFERENCE_RIG_STATUS.md),
  [P12 layout](P12_LAYOUT_TOOLING.md), [promotion](P12_PROMOTION.md): implemented tooling and its distinct pending gates.
- [Sister-project contracts](SISTER_REPO_INTEROPERABILITY_DESIGN.md): proposed artifact exchange, not a shared runtime.

## Historical designs, proposals and receipts

The dates and original measurements in these documents are preserved. Recheck implementation/runtime facts before reuse.

- [Revival assurance design](REVIVAL_ASSURANCE_PLAN.md), [Atlas design](MOD_ATLAS_PLAN.md),
  [AoTD design](AOTD_COMPAT_PLAN.md), [save-tool proposal](SAVE_TOOL_PROPOSAL.md),
  [performance workbench design](PERFORMANCE_WORKBENCH_DESIGN.md), and `docs/proposals/` describe plans or earlier scopes.
- [D-series pilot](D_SERIES_PILOT_REPORT.md), [AoTD sweep](AOTD_SWEEP_2026-10-12.md),
  [Vacuum layout record](P12_VACUUM_LAYOUT.md), [0.2.0 publication](RELEASE_0_2_0.md),
  [Zorg/EPTA follow-up](OWNER_MOD_FOLLOWUP_2026-10-17.md) record their own bounded evidence, not current universal acceptance.
- [CHANGELOG](../CHANGELOG.md) and [mod changelog](../MOD_CHANGELOG.md) retain historical command names/versions where
  relevant; use the live CLI reference rather than executing a superseded example from release history.
- Probe/profile/fixture READMEs explain their particular artifacts. Test logs, mission text and synthetic fixtures are
  not operator policy and are not rewritten to reflect current prose conventions.

## GitHub and local-only scope

GitHub default branch was `main` at `3342654d` when checked on 2026-10-18 (source package 0.3.0 then; 0.4.0 on 2026-10-21, probe 0.3.1); latest
published tool release is v0.2.0 **pre-release**. Its GitHub asset digests match the publication receipt. No open GitHub
issues/PRs were returned; root roadmap/local reports still contain unresolved work. Latest main CI was successful.

The checks above describe the pre-publication audit snapshot. The owner authorized publication of the documentation
corrections and proposed strategy on 2026-10-18. The strategy documents are included in that documentation commit;
ignored local helper documentation remains local. This does not approve strategy implementation or a new runtime
release, and historical release assets/tags remain unchanged.

B1 archive checkpoint (2026-10-22): the two earlier root roadmap pages and the completed October 18 audit are
under [archive/](archive/README.md). Archiving preserves pending owner/live/research obligations; it does not mark
those gates complete. The architecture assessment remains current supporting evidence for S1-S4 and stays here.

The bounded audit scope, exceptions and source-backed corrections are recorded in [DOCS_AUDIT_2026-10-18.md](archive/DOCS_AUDIT_2026-10-18.md).


## Structural refactor execution

- [PR stack and owner merge order](REFACTOR_STACK.md)
- [B3 research validation](REFACTOR_B3_RESEARCH_AUDIT.md)

- [B3 Atlas review evidence](REFACTOR_B3_ATLAS_AUDIT.md): package moves and fresh validation; live gates unchanged.

- [B3 corpus evidence](REFACTOR_B3_CORPUS_AUDIT.md): package moves and full validation; live gates unchanged.

- [B3 escalation evidence](REFACTOR_B3_ESCALATION_AUDIT.md): structural move and regression/consumer validation.

- [B3 probe evidence](REFACTOR_B3_PROBE_AUDIT.md): structural move and regression/consumer validation.

- [B3 rig evidence](REFACTOR_B3_RIG_AUDIT.md): structural move and regression/consumer validation.

- [B3 live evidence](REFACTOR_B3_LIVE_AUDIT.md): structural move and regression/consumer validation.

- [B3 bytecode evidence](REFACTOR_B3_BYTECODE_AUDIT.md): structural move and regression/consumer validation.

- [B3 scan evidence](REFACTOR_B3_SCAN_AUDIT.md): structural move and regression/consumer validation.

- [B3 save evidence](REFACTOR_B3_SAVE_AUDIT.md): structural move and regression/consumer validation.

- [B3 completion evidence](REFACTOR_B3_COMPLETION.md): local implementation complete; owner review/merge pending.

- [B4 command-reference audit](REFACTOR_B4_COMMAND_AUDIT.md): complete parser inventory and bounded static consumer references; grouping/deprecation decisions remain with the owner.

- [B5 test-speed evidence](REFACTOR_B5_TEST_SPEED.md): measured unittest markers, complete CI partitions and local validation.

- [B6 close-out evidence](REFACTOR_B6_CLOSEOUT.md): current architecture/companion paths and the explicit distinction between documentation implementation and remaining item-83 review/merge gates.

- [S-series implementation plan](S_SERIES_IMPLEMENTATION_PLAN.md): owner-authorized S1 start, S1-S4 dependency order and acceptance gates.
- [S1 contract map](S1_CONTRACT_MAP.md) and [progress/handoff](S1_PROGRESS.md): existing policy compatibility, read-only workspace adapter and next implementation slice.
