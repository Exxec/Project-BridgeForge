# Runtime context interop, synthetic fixture version 1

These neutral candidate files and run records test BridgeForge's `write_run_record` output against Project Go's importer.
They are not live evidence. `test_runtime_context_interop.py` reproduces both JSON records with the real producer using
synthetic manifest/milestone inputs, a fixed clock and a synthetic core digest. No game or mod code is executed.

- `observed-zero.synthetic.json` supplies an explicit integer zero; it exercises synthetic boot/campaign gates only.
- `unknown-exit.synthetic.json` supplies no exit observation; it must leave every runtime gate NOT_TESTED.
- The consumer also checks nonzero and malformed exits. SAVE_RELOAD stays NOT_TESTED without explicit reload evidence.

The producer obtains Java version from the selected runtime's release file, with bounded `java -version` fallback.
Absent/unresolvable runtime context stays unknown. Batch-variable and bare-PATH commands do not borrow the host JDK's
version because the batch may change that environment. The exit field is never inferred from a clean log or successful
translation. The current interactive launcher kills the game process tree and does not supply an observed natural
Java exit: adding fields does not close the real bound-run acceptance gate.
