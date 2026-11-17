package com.bridgeforge.probe;

/**
 * Common-file names used by the BridgeForge Probe mod (rig only).
 *
 * All three live under the game's saves/common folder via the public
 * SettingsAPI common-file methods (readTextFileFromCommon /
 * writeTextFileToCommon / fileExistsInCommon), never via direct file or NIO
 * path APIs (both forbidden by RC8's script sandbox). No extension is
 * appended by the API, so the names below are the exact on-disk file names
 * BridgeForge's Python side must read and write.
 */
public final class ProbeFiles {

    /** Presence-only marker. If absent, the probe does nothing but log one line. */
    public static final String RIG_MARKER = "bf_probe_rig";

    /** JSON probe configuration written by BridgeForge before a probe run. */
    public static final String CONFIG = "bf_probe_config";

    /**
     * Notepad-editable setup profile (roadmap P3c-1), re-read by {@link ProbeProfile} at the
     * first campaign tick of every save. When present its setups replace {@code bf_probe_config}'s
     * own {@code setups} list, so the owner can edit it in the rig and start a New Game with no
     * BridgeForge CLI step.
     */
    public static final String PROFILE = "bf_probe_profile";

    /** JSON-lines report file the probe appends every check result to. */
    public static final String REPORT = "bf_probe_report";

    /** 0.2.13: the combat mission's round counter, so each start fights the next slice of hulls. */
    public static final String COMBAT_ROUND = "bf_probe_combat_round";

    /**
     * The round the next battle fights (0 when the file is absent or unreadable). Reading never advances it: 0.3.3, because
     * the game runs a mission's defineMission again when a battle ends as well as when the next one starts, and 0.2.13's
     * advance-on-read counted both. With two rounds every second battle fought round 1's hulls again (G1-LIVE3, G2,
     * G2B-LIVE-0985a-20261117), so the second slice never fought.
     */
    public static int currentCombatRound() {
        try {
            if (com.fs.starfarer.api.Global.getSettings().fileExistsInCommon(COMBAT_ROUND)) {
                return Integer.parseInt(com.fs.starfarer.api.Global.getSettings().readTextFileFromCommon(COMBAT_ROUND).trim());
            }
        } catch (Throwable t) {
            // an unreadable counter only means the first slice again
        }
        return 0;
    }

    /** Called once when a battle ends: the next definition shows the next slice. Returns the round that just ended. */
    public static int advanceCombatRound() {
        int ended = currentCombatRound();
        try {
            com.fs.starfarer.api.Global.getSettings().writeTextFileToCommon(COMBAT_ROUND, String.valueOf(ended + 1));
        } catch (Throwable t) {
            // a counter that cannot be written only means the same slice again
        }
        return ended;
    }

    private ProbeFiles() {
    }
}
