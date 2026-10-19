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
  [architecture gaps](ARCHITECTURE_GAPS.md): proposed S1-S4 direction and evidence; no implicit implementation approval.
- [Root roadmap](../ROADMAP.md): authoritative accumulated decisions/history. [docs/ROADMAP.md](ROADMAP.md) and
  [completion log](ROADMAP_COMPLETION_LOG.md) are historical tranche records, not competing current backlogs.
- [Automation plan](AUTOMATION_PLAN.md), [item 75 implementation handoff](ROADMAP_IMPLEMENTATION_HANDOFF.md),
  [hardening plan](HARDENING_PLAN.md): tactical specifications. Items 73 and 75 were implemented offline on 2026-10-18 (per-item
  status lines in each; table in [ROADMAP_STATUS](ROADMAP_STATUS.md)); their live acceptance is pending.
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

GitHub default branch was `main` at `3342654d` when checked on 2026-10-18. Source package version is 0.3.0; latest
published tool release is v0.2.0 **pre-release**. Its GitHub asset digests match the publication receipt. No open GitHub
issues/PRs were returned; root roadmap/local reports still contain unresolved work. Latest main CI was successful.

The checks above describe the pre-publication audit snapshot. The owner authorized publication of the documentation
corrections and proposed strategy on 2026-10-18. The strategy documents are included in that documentation commit;
ignored local helper documentation remains local. This does not approve strategy implementation or a new runtime
release, and historical release assets/tags remain unchanged.

The bounded audit scope, exceptions and source-backed corrections are recorded in [DOCS_AUDIT_2026-10-18.md](DOCS_AUDIT_2026-10-18.md).
