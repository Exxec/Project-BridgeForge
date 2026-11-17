- `archive` first does what `probe-group record --archive` does (ROADMAP-3 96.6). It records what the files prove
  (`audit-explain --auto`), and a refusal lists what it proved. For a live-validated mod with no licence decision it
  applies the owner's standing local-only decision, and writes it to `release_policy.json` only once the archive is
  written. A waived live result gets no automatic decision.
- The translation proof checks each file. It applies only to CSV and JSON-like files, and only when every difference
  replaces Chinese display text. `audit-explain --auto` also sees a `translate-batch` work folder's records.
- Release-policy decisions are written with LF line endings.
