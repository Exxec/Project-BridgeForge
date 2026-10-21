package com.bridgeforge.probe;

import com.fs.starfarer.api.Global;
import org.json.JSONArray;
import org.json.JSONObject;

/**
 * Clean exit when done: once the configured run is complete (the campaign checks ran and the last round of the combat mission
 * ended) the probe writes the {@code bf_probe_done} common file with the manifest id and a summary, and logs
 * {@code BF-PROBE|<version>|done|manifest_id=<id>|stages=campaign,combat}. The harness watches for the file and closes the game
 * window gracefully instead of killing the process. Only the SettingsAPI common-file methods are used (javap RC8
 * starfarer.api.jar, 2026-10-20: readTextFileFromCommon, writeTextFileToCommon, fileExistsInCommon).
 */
final class ProbeDone {

    static final String FILE = "bf_probe_done";
    private static final int DEFAULT_CAP = 30; // as bfprobe_combat's MissionDefinition

    private static boolean campaignDone = false;
    private static boolean combatDone = false;
    private static boolean written = false;

    private ProbeDone() {
    }

    static void campaignEnded() {
        ProbeExercised.emitAll();
        campaignDone = true;
        writeIfComplete();
    }

    /** Called when a combat round ends; only the last round of the configured slices completes the run. */
    static void combatEnded() {
        ProbeExercised.emitAll();
        if (isLastRound()) {
            combatDone = true;
        }
        writeIfComplete();
    }

    private static boolean isLastRound() {
        try {
            ProbeConfig config = ProbeConfig.load();
            int cap = config.combatCapPerSide > 0 ? config.combatCapPerSide : DEFAULT_CAP;
            int total = config.variantByHull.size();
            int rounds = total == 0 ? 1 : (total + 2 * cap - 1) / (2 * cap);
            // ProbeFiles.nextCombatRound() has already advanced the counter for the round that just ended.
            int started = Integer.parseInt(Global.getSettings().readTextFileFromCommon(ProbeFiles.COMBAT_ROUND).trim());
            return (started - 1) % rounds == rounds - 1;
        } catch (Throwable t) {
            return true; // an unreadable counter must not leave the harness waiting for a marker that never comes
        }
    }

    private static void writeIfComplete() {
        if (written || !campaignDone || !combatDone) {
            return;
        }
        written = true;
        try {
            String id = ProbeRun.manifestId();
            JSONObject marker = new JSONObject();
            marker.put("manifest_id", id);
            marker.put("version", ProbeLog.VERSION);
            marker.put("stages", new JSONArray().put("campaign").put("combat"));
            marker.put("summary", "campaign checks and the last combat round ended");
            marker.put("timestampMillis", System.currentTimeMillis());
            Global.getSettings().writeTextFileToCommon(FILE, marker.toString());
            Global.getLogger(ProbeDone.class).info(
                    "BF-PROBE|" + ProbeLog.VERSION + "|done|manifest_id=" + id + "|stages=campaign,combat");
        } catch (Throwable t) {
            written = false; // a later stage end may try again
        }
    }
}
