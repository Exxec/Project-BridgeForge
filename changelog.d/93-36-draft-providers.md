- Item 93.36: `revive --draft-report` checks the compile against the same libraries as revive's own scan, including the reference
  install's `mods/`, plus the `--providers` folders. A mod whose only "errors" were missing libraries is no longer drafted BLOCKED.
