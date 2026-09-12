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

    private ProbeFiles() {
    }
}
