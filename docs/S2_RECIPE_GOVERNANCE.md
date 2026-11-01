# S2.3 recipe trials and promotion gate

Initial slice, 2026-11-01. S2.3 stays open: this measures recipes and reports a gate. It approves nothing, and no default,
policy, ruling or `revive` behaviour changed.

## What it does

`bridgeforge recipe-trial COHORT --output OUT [--core CORE] [--policy POLICY] [--queue QUEUE]` reads a schema-1 cohort
(`{"schema_version": 1, "cases": [{"name", "path", "split"}]}`, split `training` or `holdout`). For each case it scans a
physical mod tree. Then, for every finding with a fixer, it tries the recipe on its own private copy.

| Outcome | Meaning |
|---|---|
| `VERIFIED` | Applied; a rescan no longer reports the finding; no actionable finding appeared; a second run changes nothing |
| `PARTIAL` | Applied, but the finding remains with changed evidence, or some targets were refused. Not a positive |
| `REFUSED` | The fixer declined. Abstention, not failure |
| `ABSTAINED` | Not attempted: tier is not `auto`, or the finding is MANUAL/UNKNOWN, gameplay, balance or save (`person_only`) |
| `FAILED` | Crashed, wrote outside the workspace, was not idempotent, introduced an actionable finding, or left the finding unchanged |

A Java edit is compile-checked with `--core`, before and after. The input tree is hashed before and after each case, and a
linked tree is refused. The second run rescans first, as a real second pass would.

| Gate state | Rule |
|---|---|
| `REVOKED` | The newest `approve-fixer` ruling was revoked or has expired |
| `BLOCKED` | Any failed trial, in either split |
| `NEEDS_MORE_EVIDENCE` | Under 3 verified training cases (the standing-ruling bar), or no verified holdout case |
| `READY_FOR_OWNER_REVIEW` | Otherwise. Report only: a person still records any approval through `escalation rule` |

Holdouts can confirm or block, and never supply positives. The report records the engine and policy digests, and
`selection_digest` identifies the selected work. The command checkpoints per case and writes no input, policy or ruling.

## First real result

Cohort: the 12 owner-approved S2 mods (`S2_COHORT_PROPOSAL.md`, 8 training, 4 holdout), using their preserved `original/`
trees rather than fixed working copies, with RC8 core and no extra provider roots. Three consecutive runs gave the same
digest `756c2404...` and the same gate, with every input unchanged. The private reports are under
`bridgeforge-state/s23-recipe-trial/`.

60 recipe attempts: 33 verified, 2 partial, 4 refused, 19 abstained, 2 failed. 2 trials were compile-checked. Of 27 recipes:

| State | Count | Recipes |
|---|---:|---|
| `READY_FOR_OWNER_REVIEW` | 2 | `mod-info-game-version-inexact` (7 training, 4 holdout), `shippable-work-file` (3, 1). Both already approved |
| `BLOCKED` | 1 | `data-file-not-utf8` (approved): on 2 mods, fixing the encoding exposes `rules-csv-curly-quote-unreadable`, which needs a person's input |
| `NEEDS_MORE_EVIDENCE` | 24 | Mostly too few cohort cases, including 10 approved recipes |

Two things the gate exposed for the owner:

- `target-interface-method-missing` is an approved fixer whose findings are all `MANUAL` on these 3 mods. The trial abstains, as
  the non-negotiables require, so it has no evidence here. `revive` still applies it, because `approved_fixers` permits any
  classification (`revive.py` `_try_fixers`). That is the owner's dated standing approval, not changed here, but the two rules
  should be reconciled deliberately.
- `undeclared-library-dependency` (approved) has 2 verified training cases plus 1 partial, and 2 verified holdout cases, so it
  sits one case short.

## Limits

- Static trial only: no game launched, so `VERIFIED` means the mechanics held, not that behaviour is preserved.
- A first harness version reported false failures: stale scan data in the second pass, purely informational new findings, and a
  deliberately kept `null-guarded` finding. Those corrections apply to every recipe, but they were made after seeing results that
  included holdout cases (`variant-op-over-budget`, `undeclared-library-dependency`). So this cohort's holdouts are no longer
  unseen for the harness itself. They selected no recipe.
- These are already-revived corpus members, not globally unseen mods. With no provider roots, provider-dependent findings can differ.
- No resolved-provider run, per-recipe contract record, affected-case invalidation or independent sampled review yet.

## Next

1. Run a larger, freshly reserved holdout, with explicit provider roots, for the recipes one case short.
2. Owner decision on `data-file-not-utf8` chaining and the MANUAL standing approval above.
3. Add affected-case invalidation when a recipe's approval is revoked, then the owner's sampled independent review (S2 objective 5).
