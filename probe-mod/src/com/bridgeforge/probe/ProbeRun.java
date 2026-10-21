package com.bridgeforge.probe;

import com.fs.starfarer.api.Global;
import org.json.JSONObject;

/**
 * Item 75 R1: the startup echo of the run's manifest id. The harness writes the {@code bf_probe_run} common file (JSON with
 * {@code manifest_id} and {@code run_id}) after it records the pre-launch manifest, and the probe logs the id once, right after
 * the rig gate: {@code BF-PROBE|<version>|run|manifest_id=<id>}. The id is not in {@code bf_probe_config} because the manifest
 * hashes that file. A missing or unreadable file logs {@code manifest_id=NONE}, which the evaluator reports as not echoed.
 * Only the SettingsAPI common-file methods are used (javap RC8 starfarer.api.jar, 2026-10-20).
 */
final class ProbeRun {

    static final String FILE = "bf_probe_run";
    static final String NONE = "NONE";

    private static boolean echoed = false;

    private ProbeRun() {
    }

    static String manifestId() {
        try {
            if (!Global.getSettings().fileExistsInCommon(FILE)) {
                return NONE;
            }
            String id = new JSONObject(Global.getSettings().readTextFileFromCommon(FILE)).optString("manifest_id", "");
            return id.length() == 0 ? NONE : id.replace("|", "/").replace("\n", " ");
        } catch (Throwable t) {
            return NONE;
        }
    }

    /** Logs the echo line once per game process. */
    static void echoOnce() {
        if (echoed) {
            return;
        }
        echoed = true;
        try {
            Global.getLogger(ProbeRun.class).info("BF-PROBE|" + ProbeLog.VERSION + "|run|manifest_id=" + manifestId());
        } catch (Throwable t) {
            // Logging must never crash the probe.
        }
    }
}
