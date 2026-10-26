# Fresh-workstation local trial

This kit contains BridgeForge code, owned probe sources and the Windows rig harness. Keep the
kit separate from private workspaces, stores, game inputs and saves. Transport is local/private;
publication and a broader support commitment are not authorized. Code verification does not
qualify a revival. The trial profile is __PROFILE_ID__ on Windows x64/Python 3.15 with the
declared RC8 core and an explicitly selected JDK. Other environments remain unqualified.

1. Choose a short, physical trial directory on the other workstation. Preserve its primary
   game, saves and existing work. Extract the code kit there; place private inputs separately.
   Compare the transferred archive SHA256 with the primary-workstation receipt before use.
2. Select Python 3.15 and create a new virtual environment outside the code kit. Install the
   tested dependency `psutil==__PSUTIL_VERSION__` using your trusted package source or supplied
   wheel. Installation can require network access; analysis after setup uses local inputs.
   Record setup commands, package source, errors and active setup minutes. Nothing installs
   automatically when the kit is opened.
3. Run `VENV_PYTHON VerifyKit.py` and save its JSON output outside the code kit. Resolve a
   missing/wrong interpreter or dependency explicitly. Use the included launcher for subsequent
   commands: `powershell -NoProfile -File BridgeForge.ps1 -Python VENV_PYTHON --help`.
   The launcher selects the included runtime and restores the prior PYTHONPATH on exit.
4. Transfer one approved private case's original/working/reports/checkpoints and required
   external context inputs from a verified snapshot or byte-exact local copy. Keep source copies
   untouched. The metadata exchange file contains historical paths for audit; import never
   follows them. Do not distribute mod/game/save payload as part of this code kit.
5. Run `case-exchange requirements PRIVATE_MANIFEST --json`. Fill its binding template with
   absolute paths on this workstation, including this virtual environment's interpreter,
   selected physical core/JDK/providers and the preserved policy/review files. New private
   workspace and case-store locations must be separate. Then run:

   Set `JAVA_HOME` to that selected JDK and put its `bin` first on this trial session's PATH;
   qualification refuses a different discovered JDK. Keep the trial's bindings and logs outside
   the code kit.

   `case-exchange import PRIVATE_MANIFEST --workspace RESTORED_WORKSPACE --store NEW_STORE --inputs NEW_BINDINGS --json`

   If external tool bytes changed, review the reported difference and explicitly use
   `--allow-context-change` to capture an unqualified new context. Policy/review authority bytes
   cannot be relaxed through that option. Missing/changed payload, credits or decisions refuse.
6. Save the import result. It must say `IMPORTED_UNQUALIFIED` and give a new case/candidate ID.
   Historical receipts remain historical. Run `case status CASE --store NEW_STORE --json`, then
   perform fresh analysis/qualification with the explicit bindings. Use `case qualify --help`
   and `portfolio-scan --help` for current spelling; portfolio COMPLETE is not qualification.
   A review decision tied to an old subject must be reviewed/reissued for the new subject.
7. To complete the live portion, use a dedicated isolated rig, a junction to the selected core,
   one game/UI owner and fresh named run preparation. Build the owned probe with
   `build-probe-mod --jdk JDK --core CORE --install-release --json`. Preserve generated game-
   owned mission assets locally. Follow `case prepare`, `prepare-run`, authorized live execution,
   `qualify` and `finalize` help. Keep old archives. Existing-save load/migration needs its
   separate approval; this trial does not grant it. If a gate refuses, keep its exact result.
8. Repeat one finished analysis/finalization, exercise a copied restore with one missing or
   altered file, and record the refusal/recovery. Never corrupt the only good copy. Rebuild
   scans/indexes from current inputs rather than copying a green status from the first machine.
9. Return the verifier/environment JSON, new case/candidate and run/operation IDs, command logs,
   refusal/restore/retry results, manual interventions and active setup/review minutes. Record
   operator identity/role and whether they used prior chat or undocumented help. Omit raw mod,
   game and save payload from the return packet. Owner-on-fresh-machine and independent-human
   evidence are separate fields; do not relabel one as the other.

Record current input hashes and remaining static/compile/API/dependency/save/live dimensions
separately. The owner decides support/release scope after reviewing actual results. A kit build,
checksum pass or automated local test does not supply the human trial or that commitment.
