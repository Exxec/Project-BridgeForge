# Changelog fragments

Every change adds one file here, `changelog.d/<slug>.md`, holding one bullet (the text that would have gone into
`CHANGELOG.md`; a leading `- ` is optional). Pull requests never edit `CHANGELOG.md` itself, so two branches never
conflict on it.

At release time (or any time) `bridgeforge release-notes assemble [--version V]` moves the fragments, sorted by file
name, under the top `## <version> (unreleased)` heading of `CHANGELOG.md` and deletes them. `release-notes --check` lists
the pending fragments (exit 1 when there are any, so a release can refuse to go out with unassembled notes).
