# Port source record: `working/reports/PORT_SOURCE.json`

ROADMAP item 73 E4 (finding `port-dropped-feature`, `bridgeforge/scan_port.py`). Before 2026-10-18 a port was recorded only as
free text in `reports/SHIPPED_CHANGES.json` (Templars 0.9.8f ported onto 0.9.9e's RC8 code, 2026-10-13), so nothing could list
what the older version had that the ported one lost. A mod that is a port records it here:

```json
{
  "schema_version": 1,
  "old_version": "0.9.8f",
  "onto": "0.9.9e (Kind Stranger) RC8 code",
  "date": "2026-10-13",
  "old_tree": "scratch/port-0.9.9e-code/before",
  "reason": "0.9.8f used the removed event system and 12 removed methods; code and the data it reads came from 0.9.9e."
}
```

- `old_tree` (required): a folder of the OLD version's files, relative to the workspace folder (the parent of `working/`). It may
  hold the whole old version (`original/extracted/Templars`; a folder holding one mod below it is descended to the `mod_info.json`)
  or only the files the port replaced (Templars: `scratch/port-0.9.9e-code/before`, which has `data/` and `jars/`). An absolute
  path, or one that leaves the workspace, is ignored: the record sits inside a mod and must not point the scanner elsewhere.
- `old_version`, `onto`, `date`, `reason`: shown in the finding's explanation.
- No record, an unreadable one or a missing `old_tree` means no finding.

The check compares the old tree with `working/` and reports, one finding per category with something dropped (the first evidence
line is `<category>: ...`, so each category has its own baseline key):

| Category | Compared |
|---|---|
| `classes` | top-level classes from `.java` files (package declaration plus file name) and `.class` entries of jars, grouped by package |
| `events.json` | top-level event ids of `data/campaign/events.json` |
| `reports.csv` | `event_type/event_stage` pairs of `data/campaign/reports.csv` |
| `settings` | `settings.json` keys two levels deep (`plugins.X`); the `graphics` and `sounds` asset maps are left to `asset-reference-missing` |
| `rules.csv` | the `trigger` column of `data/campaign/rules.csv` |

The finding is REVIEW, tier `decision`. A dropped feature is reported, never restored. `revive` makes a packet of kind
`recreation` for it and writes `reports/RECREATION_PLAN.md`, a skeleton with the sections of `docs/TEMPLAR_CRUSADE_PLAN.md`
(never over an existing file). Whether a mod gets a plan is the owner's decision; accepting the loss uses
`escalation accept WORKSPACE port-dropped-feature --reason ...`.

Local step for the real queue (not done in the implementation session): write this record into
`In operation/Templars-0.9.8f/working/reports/PORT_SOURCE.json` with `old_tree` `scratch/port-0.9.9e-code/before` and rescan.
