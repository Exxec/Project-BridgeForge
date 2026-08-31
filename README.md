# Project Bridgeforge

An offline, read-only compatibility scanner for legacy Starsector mods. Bridgeforge V0.1 inventories a mod and produces explainable compatibility findings; it does not modify the mod, rewrite source, or alter bytecode.

Bridgeforge is intentionally separate from the proposed [Starsector Performance Workbench](docs/PERFORMANCE_WORKBENCH_DESIGN.md), which profiles runtime behavior and attributes cost to mods/classes.

## Run

Requires Python 3.10+.

```powershell
py -3 -m bridgeforge scan C:\path\to\OldMod --output .\artifacts
```

The command writes `MODERNIZATION_REPORT.md` and `bridgeforge.compat.json` to the output directory. Use `--target-starsector` and `--target-java` to change the default `0.98.x` / Java 17 target profile.

## V0.2 working-copy workflow

```powershell
py -3 -m bridgeforge workspace C:\path\to\OldMod --output C:\work\OldMod-bridgeforge
py -3 -m bridgeforge plan C:\work\OldMod-bridgeforge --target-starsector 0.98a-RC8
py -3 -m bridgeforge apply C:\work\OldMod-bridgeforge --approve metadata-target-starsector-version
```

`workspace` makes an immutable reference and a separate working copy. `plan` creates a diff-backed plan; `apply` modifies only the working copy and only for rule IDs explicitly approved on the command line. `rollback` restores the working copy from a named checkpoint.

## Safety

Scanning is read-only with respect to the selected mod directory. Generated artifacts are written only to `--output`.
