# Local fresh-workstation trial

Owner 2026-10-25: "I have another workstation i will test from." This supplies an available
environment for a future trial, not a completed run. Record actual operator identity/role,
prior knowledge/help and platform. Owner-on-fresh-machine evidence and a distinct independent
human operator are separate; no automated test impersonates either. Support/publication scope
still requires the owner's decision after actual evidence.

The implemented local-kit profile targets Windows x64/Python 3.15 and the existing RC8 local-
new-game scope. Runtime dependency is pinned to the tested builder environment in the kit.
Other environments report setup/support gaps. The code kit includes the exact runtime wheel,
owned probe sources, Windows harness, license, standalone verifier, launcher and trial guide.
Private mod/game/save inputs are transferred separately; the kit grants no publication right.
The source-backed runtime provides its required probe/harness paths relative to the kit, with
an explicit selected interpreter and no inherited owner PYTHONPATH requirement.

**Current transfer artifact, 2026-11-01:** `bridgeforge-state/BridgeForge-local-trial-e78189c6.zip`,
SHA256 `adaa81eda06383e0a062057466faf77381dd24582d93b3c05b68ed167bd5156a`,
engine `65d3460fcccd8f8f0a2dbafe52fb5515ade9586765136330de581fe759135249`. A copy, the exported E1 case manifest
and a start sheet are in the owner's local `Documents/BridgeForge-S4-Trial` folder for transfer. Owner 2026-11-01: "Save it
and i will copy/SSH and run it on Workstation"; no trial has run. Its verifier passed from a foreign working directory on
this machine, where that check also found the guide's launcher command refused by the Windows default script policy; the
guide now passes a process-only `-ExecutionPolicy Bypass`. The earlier `96182984` kit is historical; use the current
artifact and [trial return template](S4_TRIAL_RETURN_TEMPLATE.md). The full suite before the build: 2,783 tests with 1 error
(a syntax error in one new test file, fixed, with that module then passing), 8 skips, hermeticity PASS.

`local-kit build --repo CHECKOUT --wheel EXACT_WHEEL --output CHECKOUT/bridgeforge-state/NEW_NAME`
validates the wheel against loaded source, bounds archive reads, refuses traversal/foreign
namespaces and serializes output ownership. Per-file progress and the existing checkpoint
support verified interrupted-copy resume; `--quiet` suppresses progress. Source/asset drift,
unexpected partial files, missing modules and existing output refuse. The archive contains only
the verified code kit; incomplete staging and failed earlier artifacts are preserved separately.

`local-kit verify KIT` and standalone `VENV_PYTHON VerifyKit.py` check the manifest and code
files, interpreter/dependency/platform conditions. `READY_FOR_LOCAL_TRIAL` is not qualification,
human execution, a support commitment or an attestation of unlisted runtime-generated assets.
Build/verification are local actions; no installer, publication or remote machine operation runs
automatically. The included trial guide describes setup, explicit path binding, restore/refusal,
fresh qualification, authorized rig flow and the required return packet.

## Private case metadata exchange

`case-exchange export CASE CANDIDATE --store STORE --output NEW_PRIVATE_FILE` preserves the
selected case/candidate and historical receipt records, plus reports/checkpoints inventories,
without embedding payload. Export requires current inputs and a new output, with source/store
and output ownership checks. `summary` emits a path/payload-free review summary; publication
still remains unauthorized. `requirements` emits expected external input fingerprints and a
binding template with no owner source paths.

Restore the private workspace/reports/checkpoints and external inputs separately, using existing
snapshot/restore tooling or verified local copies. `case-exchange import PRIVATE_FILE --workspace
RESTORED --store NEW_STORE --inputs NEW_BINDINGS` verifies original/working/credits and decision
inventories, then creates a new **unqualified** case and candidate. It never follows historical
owner/artifact paths. Old receipts are stored only in an exchange-history namespace and cannot
become current acceptance. Repeated import is idempotent. Missing payload/decisions, invalid
identities or unsupported schemas/profiles refuse with explicit migration/rebind instructions.

Changed non-policy external bytes require `--allow-context-change` and fresh qualification.
Policy/review authority bytes cannot be relaxed by import. Relocated review decisions tied to
the old subject need renewed review for the new subject. Local/private-only restrictions and
source credits survive; no public rights or archive status are inferred from a successful import.

## Validation status

Focused new comparison/exchange/kit tests pass, including cold rebinding after source
workspace/context/artifact removal in a self-authored fixture, invalid authority, corrupt
metadata, unknown profiles, code corruption, unsafe wheel members and interrupted kit copy
resume. An actual source-backed kit's standalone verifier and PowerShell launcher pass from a
foreign working directory without inherited PYTHONPATH. The first launcher smoke exposed
PowerShell/native quote handling; the corrected launcher and fresh kit passed. These are local
automated checks, not a fresh-workstation or human trial. Full regression/package results are
recorded in the progress documents when terminal.
