- Security: a mod's id can no longer reach cmd.exe or a PowerShell script (ROADMAP-3 93.47).
  - The mass test named its logs after the mod's id. That name went into the raw cmd.exe launch line and into a quoted
    screenshot path in PowerShell.
  - Log names now keep only ASCII letters, digits, `.`, `_` and `-`.
  - The launch line refuses a path holding `"`, `%`, `!` or a control character.
  - Screenshot paths reach PowerShell in an environment variable.
