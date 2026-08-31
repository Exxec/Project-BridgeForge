# Project Bridgeforge

An offline, read-only compatibility scanner for legacy Starsector mods. Bridgeforge V0.1 inventories a mod and produces explainable compatibility findings; it does not modify the mod, rewrite source, or alter bytecode.

## Run

Requires Python 3.10+.

```powershell
py -3 -m bridgeforge scan C:\path\to\OldMod --output .\artifacts
```

The command writes `MODERNIZATION_REPORT.md` and `bridgeforge.compat.json` to the output directory. Use `--target-starsector` and `--target-java` to change the default `0.98.x` / Java 17 target profile.

## Safety

Scanning is read-only with respect to the selected mod directory. Generated artifacts are written only to `--output`.

