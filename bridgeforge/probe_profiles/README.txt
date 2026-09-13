BridgeForge probe profiles (roadmap P3c-1)
===========================================

A profile is a plain, Notepad-editable text file with one setup instruction per line. Each line
maps 1:1 onto an existing `--setup` spec (bridgeforge/probe_config.py's validate_setup_spec), so
a profile line that parses is guaranteed to be something the in-game probe can apply.

Grammar
-------

    # a full-line comment
    apply = once-per-save        # or: every-load
    rep <faction> = <RepLevel-or-number>
    credits = <N>
    ship <variant_id> [xN]       # count defaults to 1 if omitted
    spawn <faction> <fleet_points>
    jump <star_system_name>
    -credits = 100                # a leading '-' disables a line without deleting it

Notes:
  - Keywords (`apply`, `rep`, `credits`, `ship`, `spawn`, `jump`) are case-insensitive; extra
    spaces around `=` and between words are fine.
  - `#` starts a comment anywhere on the line, including after a real instruction
    (`credits = 500000   # starting cash`).
  - Blank lines and comment-only lines are ignored.
  - A disabled line (leading `-`) is still parsed and validated -- a typo in a disabled line is
    still reported -- but it does not apply and is reported back separately (as `disabled`,
    alongside the active `setups`).
  - `apply = once-per-save` (the default) applies the profile's setups once per save, the same as
    plain --setup specs. `apply = every-load` re-applies them on every game load instead (see
    BfProbeModPlugin.onGameLoad in probe-mod).

Using a profile
----------------

From the CLI (see the lead's CLI wiring for the exact flag):

    bridgeforge probe-config <mod_dir> --runtime <rig_dir> --profile exigency-rep

`--profile` accepts either a bundled name (one of the .txt files in this folder, without the
extension) or a path to any other profile file.

Editing a profile directly in the rig
--------------------------------------

`bridgeforge probe-config --profile ...` also writes the profile's raw text into the rig itself,
as the common file `bf_probe_profile`. Starsector adds `.data` to every common file's name, so
on disk it is `bf_probe_profile.data`, next to `bf_probe_config.data`, under:

    <runtime_dir>/saves/common/bf_probe_profile.data

You can open that file directly in Notepad and edit it. The probe mod re-reads it at the first
campaign tick of a save: if present, its setups REPLACE the config's setups (so you can change
what a save applies without a CLI round trip -- just edit the file and start a New Game).

Bundled profiles
-----------------

  - exigency-rep.txt        -- Exigency: FRIENDLY rep with exipirated, credits, jump to Corvus.
  - seeker-betelgeuse.txt   -- SEEKER: dimension-manipulator ship + a nearby pirate fleet.
  - flux-basic.txt          -- Flu-X/Vacuum: basic rep/credits/jump smoke setup.
