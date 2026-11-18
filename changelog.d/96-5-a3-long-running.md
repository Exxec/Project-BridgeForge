- `escalation run --all`, `auto-open` and `atlas migrations --write` print one progress line per item (`--quiet` turns it
  off) and resume from a checkpoint after an interruption (ROADMAP-3 96.5 A3). A changed input starts the run afresh:
  a packet that `revive` wrote again, another run option, a workspace revived or rescanned in between, or other API jars.
  A test now requires every command that offers `--quiet` to follow the long-running rule.
