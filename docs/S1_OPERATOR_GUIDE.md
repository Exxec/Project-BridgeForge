# S1 local case operator guide

Status: operator commands implemented; real pilot and independent handoff acceptance are not yet established. Scope is RC8 local-maintainer **new-game** qualification and a local archive. Existing-save upgrades and publication require separate evidence/authority. Original sources, primary saves and prior archives are preserved. `CURRENT_INPUTS`, `CAPTURED`, `PREPARED` and `RUN_PREPARED` do not mean qualified.

## Inputs and setup

Use the same Python environment for every command. Install BridgeForge and its documented optional Java analysis prerequisites. Find its exact interpreter with `python -c "import sys; print(sys.executable)"`; that file is `tools.python`. Select the physical RC8 core directory (resolve the rig junction), the configured JDK home, an explicit release policy entry, an existing target/core reference, applicable provider mod roots and the rig launcher/configuration. Every context path is absolute. Source files are read; all generated records belong outside them.

Write a schema-1 inputs JSON file, replacing these placeholders with selected absolute paths:

```json
{
  "schema_version": 1,
  "inputs": {
    "core": {"starsector": "ABSOLUTE_PHYSICAL_RC8_CORE"},
    "dependencies": {},
    "tools": {"python": "ABSOLUTE_PYTHON_EXE", "jdk": "ABSOLUTE_JDK_HOME", "probe": "ABSOLUTE_SELECTED_PROBE_MOD"},
    "rules": {},
    "policy": {"target": "ABSOLUTE_TARGET_REFERENCE_JSON", "release": "ABSOLUTE_RELEASE_POLICY_JSON"},
    "launcher": {"game": "ABSOLUTE_LAUNCHER", "vmparams": "ABSOLUTE_VM_PARAMETERS", "probe_config": "ABSOLUTE_PROBE_CONFIG"},
    "source_authority": {}
  }
}
```

Remove optional file bindings that do not exist. Use explicit `{}` for an evidenced empty group; `null`/missing groups remain unknown. Dependency keys are metadata IDs; each value is the selected provider root, including transitive providers. Extra or version-constrained unresolved providers cannot qualify. Include every recorded VM-parameter file and probe configuration. The launcher's Java command must explicitly select the bound external JDK. The analysis worker also requires that JDK to match configured discovery; configure JAVA_HOME/PATH for this process, never change the global installation merely to pass.

`policy.target` is an explicit local reference: `{"schema_version":1,"target":"0.98a-RC8","core_sha256":"..."}`. Its SHA is the all-regular tree digest from `case_identity.tree_digest(tree_files(core))`, not a ZIP/API-JAR digest. A declaration is not independent version evidence: select a known RC8 reference and retain its provenance. `policy.release` uses the existing release policy format with an explicit mod entry, boolean local_only and reason. Neither file grants publication approval. Changed inputs/mixed source authority require the bound owner decision described in [S1_CASE_RECORDS](S1_CASE_RECORDS.md); do not manufacture an approval from scanner PASS. Save/persistence changes remain routed to their separate upgrade obligations.

## Capture and prepare

The following PowerShell variables are operator-selected paths, not hardcoded installation assumptions:

```powershell
$bfPython = 'ABSOLUTE_PYTHON_EXE'
$workspace = 'ABSOLUTE_WORKSPACE'
$state = 'ABSOLUTE_CASE_STATE_OUTSIDE_INPUTS'
$inputs = 'ABSOLUTE_INPUTS_JSON'
$archives = 'ABSOLUTE_LOCAL_ARCHIVE_ROOT_OUTSIDE_STATE_AND_INPUTS'
$rig = 'ABSOLUTE_ISOLATED_RIG'
$runId = 'UNIQUE_RUN_ID'
$opened = & $bfPython -m bridgeforge case open $workspace --store $state --inputs $inputs --json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'Open failed; inspect the error and stored case identity before retrying' }
$caseId = $opened.case_id
$candidateId = $opened.candidate_id
& $bfPython -m bridgeforge case status $caseId --store $state --json
$prepared = & $bfPython -m bridgeforge case prepare $caseId $candidateId --store $state --archive-root $archives --json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'Preparation failed; preserve partial attempts and inspect the error' }
$operationId = $prepared.operation_id
```

Both manifest and convention/intake workspaces are supported. A nested legacy original without an intake selection needs `open --original-relative MOD_WITHIN_ORIGINAL`. The command references that original; it does not relocate it. Record IDs from the JSON output. If open is interrupted after the case record is created, the error prints its ID; resume with `open --case-id ID` and the same inputs. If the process disappears before printing, inspect `<state>/cases/*.json`; do not guess from modification order or delete partial state.

Choose the final version **before capture** using the existing reviewed build/revision workflow. Prepare keeps that version; finalize never bumps it. `capture CASE_ID --inputs FILE --predecessor OLD_CANDIDATE_ID --store STATE --json` captures reviewed changes and preserves lineage. It does not approve those changes. Status lists all historical candidates; an old stale candidate remains visible even when a newer one is current. It checks input identity and lists historical operation checkpoints/IDs for resume; a recorded COMPLETE is not current qualification. Use qualify/finalize to revalidate current evidence.

## Stage, bind and run

Inspect rig ownership and running processes before staging. Use the existing isolated `rig-up`/`probe-group` workflow and the selected launcher/probe configuration; consult their `--help` and rig guide. Preserve existing instances, configurations and saves. Stage exactly the candidate plus its selected provider/probe closure, with no unbound enabled mods. `case prepare-run` intentionally does not overwrite staged files or launch the game:

```powershell
& $bfPython -m bridgeforge case prepare-run $caseId $operationId --store $state --rig $rig --run-id $runId --compile --json
if ($LASTEXITCODE -ne 0) { throw 'Run preparation refused; do not launch until the reported obligations are resolved' }
```

This records the R1 manifest and owns the rig until release. Execute the already prepared run with the selected launcher's filename (within this rig). Leave mouse/keyboard available to the automated driver for the duration; this creates a fresh rig-only new game and combat scenario, not a primary-save upgrade:

```powershell
$launcherName = 'SELECTED_LAUNCHER_FILENAME'
& $bfPython -m bridgeforge probe-group live $runId --rig $rig --bat $launcherName --json
if ($LASTEXITCODE -ne 0) { throw 'Live harness failed; inspect the recorded verdict, stage, log and process state' }
```

Case preparation uses the harness's exact scenario and milestones (including content IDs) and requires staging state to select only this candidate. The harness reuses that identical manifest; retain its exact stdout log and completion record. A returned harness verdict is not case qualification; always run the qualification step below. Main-menu, campaign-load and combat observations, a matching manifest echo and clean target/probe/error checks are required. A startup-only log is insufficient. Real pilot execution details and measurements must be recorded separately from synthetic tests. Do not use this new-game profile to claim save-upgrade support. If the process stops unexpectedly, inspect its actual handle/exit and R1 owner before recovery; never infer that a lock alone means the game is still running, and never steal ownership automatically.

## Qualify and finalize

```powershell
& $bfPython -m bridgeforge case qualify $caseId $candidateId --store $state --rig $rig --run-id $runId --compile --json
if ($LASTEXITCODE -ne 0) { throw 'Qualification incomplete/refused; inspect each dimension' }
& $bfPython -m bridgeforge case finalize $caseId $operationId --store $state --rig $rig --run-id $runId --compile --json
if ($LASTEXITCODE -ne 0) { throw 'Finalization incomplete/refused; preserve artifacts and inspect recovery state' }
```

Omit `--compile` only when fresh inventory proves no applicable active loose source; otherwise compile stays INCOMPLETE. Qualify reruns static/API checks and applicable full javac/RC8 Janino compilation. A generic stored PASS or unavailable Janino cannot qualify. Finalize independently requalifies, runs existing archive gates in a private workspace, verifies original/mod/ZIP bytes and publishes `<archives>/<operation_id>`. No refresh/delete/publication occurs. The archive carries CASE_QUALIFICATION.json outside the mod. Existing local-only/licence restrictions remain in its note.

Exit codes: 0 for a successful requested operation; 1 for an incomplete/refused qualification or non-current aggregate status; 2 for invalid input, unavailable/malformed records or operational errors. JSON retains per-dimension reasons; stderr carries actionable errors. Without `--json`, commands print the state, relevant IDs and qualification dimensions.

## Resume and intentional refusals

Persist case/candidate/operation/run IDs and selected input paths outside chat. Repeat prepare/finalize with the same IDs; do not edit checkpoint labels. PREPARED partial attempts remain in case state; private archive attempts remain under `<archives>/.bridgeforge-attempts`. PACKAGED records exact output before publication, allowing an interrupted move to reconcile only matching bytes. A damaged/missing completed archive, unknown destination collision, changed candidate/context/evaluator or changed run artifacts refuses. Preserve it for diagnosis; create an explicitly rebound candidate/operation when inputs change. Abandoned/foreign locks require an operator investigation, not automatic takeover.

Pilot acceptance remains open: P1 data-only baseline, P2 narrow reviewed loose-Java repair, P3 uncertain jar/source authority refusal, P4 unresolved/conflicting provider refusal, P5 save/persistence routing, P6 changed-after-qualification refusal; both layouts; real positive and drift negative; measured operator steps/review/wait and independent resume. Synthetic command/rig tests are implementation evidence only. See [progress](S1_PROGRESS.md), [contracts](S1_CASE_RECORDS.md), and [pilot requirements](NEXT_MILESTONE.md).


## Real pilot findings (2026-10-24)

Fresh rigs do not enumerate existing save descriptors. The driver now accepts the same actual main-menu playback marker as log triage, retaining the historical descriptor signal; preload-only and unrelated music do not qualify as readiness. Private probe packaging must use `probe_mod_build.install_release(..., core_dir=...)` (the `build-probe-mod --install-release` path), which supplies the local vanilla mission icon. Copying only tracked probe files omits that ignored asset and causes a startup fatal. Do not commit or fabricate that vanilla asset.

The first real P1 session after the readiness fix reached main-menu/campaign/combat and performed a rig-only save, with zero fatal/mod/probe/caught-exception failures and unchanged primary inputs. Its process exit was KILLED, not naturally observed. Current profile v1 still refuses it because it requires saved-campaign `campaign_load`, which this new-game session never emitted. Do not override/relabel that result. A versioned new-game campaign obligation and renewed bound run are needed; existing-save load/upgrade semantics must remain separate. S1 operational pilot acceptance remains open.
