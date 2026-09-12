# Guarded promotion (P12B)

`bridgeforge promote <Mod>` packages the convention-layout
`In operation/<Mod>/working` into `Done/<Mod>`. It defaults to a read-only dry run.
Supply `--original`, `--baseline`, `--behavior-diff`, `--behavior-risks`, and
`--behavior-unknowns`; add `--apply` only after reviewing the gates.
Use `--help` for optional target, policy, and expected-change evidence inputs.

The external `<Mod>/reports` plan/report takes precedence over legacy reports
inside working. The plan must contain exactly one `Total score: N` and
`Complexity level: LOW|MEDIUM|HIGH` line, consistent with workflow routing.
The report must pass revival audit and separately record affirmative source,
compile, static, package, dependency, and API validation. Completed statuses
require affirmative live-test evidence; `READY_FOR_LIVE_TEST` remains explicitly
awaiting live validation. Promotion never supplies missing gameplay evidence.
Existing release, license, and D5 behavior gates must also pass.

Apply stages the package in scratch, verifies candidate/ZIP equality and unchanged
working/report hashes, and copies plan/report plus promotion attestations into
`Done/<Mod>/reports/<release-basename>`. Previous same-id releases, their ZIPs,
release notes, and per-release reports move to `Done/<Mod>/builds/prior-<unique-id>`.
Originals, working copies, and unrelated Done contents remain untouched.

Unknown destination collisions and linked/junction paths are refused. An exclusive
`.promotion.lock` records planned moves. Ordinary publication failures reverse
completed moves; empty housekeeping directories may remain. This is not a
power-loss transaction. A surviving lock requires inspection/manual recovery;
the command never guesses how to recover an interrupted promotion.

The installed tool now includes its release policy and refuses missing, malformed,
or invalid policies. Exigency remains local-only under the bundled policy.
No actual mod promotion or new live validation is implied by tooling tests.

Remaining P12 gates: verified Vacuum layout migration and exact-commit tool
release publication. These are not completed by this promotion checkpoint.
