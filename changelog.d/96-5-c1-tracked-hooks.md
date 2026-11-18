- The git hooks are tracked in `tools/githooks/` and run once enabled with `git config core.hooksPath tools/githooks`
  (ROADMAP-3 96.5 C1). Before, they lived in an ignored folder and never ran. The pre-commit check also refuses a stale
  `docs/CHECKS.md` or `docs/COMMANDS.md`, and `bridgeforge hygiene` reports hooks that are off.
