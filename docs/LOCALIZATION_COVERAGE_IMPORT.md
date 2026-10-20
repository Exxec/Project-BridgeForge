# Project Go localization coverage import

Implemented 2026-10-20 as a read-only Python API in `bridgeforge.localization_coverage`.
This is an adapter for candidate-bound observations, relevant to S1 qualification evidence; it does not add a case lifecycle or change acceptance policy.

```python
from pathlib import Path
from bridgeforge.localization_coverage import observe

result = observe(Path("localization-coverage.json"), Path("selected-candidate"))
print(result["candidateIdentity"], result["coverageStatus"])
```

Generate the manifest with Project Go's `assess INPUT --coverage --coverage-manifest REPORT --json`.
The report must use `ssmt-localization-coverage-1`. Select the exact candidate directory yourself; manifest paths do not select files to open.
No provider, game process or mod bytecode is run, and no candidate files are written.

The importer validates bounded JSON, duplicate fields and rows, counts, portable relative paths, file statuses and hashes.
It hashes every selected file twice with Project Go's versioned inventory algorithm, including Java UTF-16 path ordering.
Links, reparse points, hardlinked files and special files are refused. Limits are 8 MiB for the manifest, 100,000 files,
200,000 pending/visited tree entries and 128 MiB of source bytes per inventory. Concurrent hostile filesystem changes between
checks are outside this static observation model.

`candidateIdentity` is MATCH, MISMATCH or UNKNOWN. A missing identity stays UNKNOWN; invalid input raises ValueError or an OS/read error.
MATCH means the report fingerprint agrees with current selected bytes. It does not establish report authorship or truth of its extraction observations.
`completeCoverageEstablished` is always false. Runtime is NOT_TESTED; approval and rights are NOT_ASSESSED;
archive identity is NOT_VERIFIED, including ZIP-origin reports joined to an extracted directory. No result is an acceptance or release permission.

Tests: `python -m unittest tests.test_localization_coverage -v` runs isolated synthetic cases by default.
For acceptance against a real Project Go export, explicitly set `PROJECT_GO_ACCEPTANCE_ROOT` to its checkout containing
`.local/roadmap-next-20261020/localization-coverage.json` and the conformance input fixture.
The source-preservation/hash acceptance was also run against that export; the observed fingerprint was
`8fedc6b762488dd280d540cf058b727ab798a74b9b968c326850637547387f04`.
The Windows symlink regression skips when the token lacks symlink privileges; hardlink refusal is tested separately.
CLI wiring and qualification-policy integration are separate work and are not implied by this API.
