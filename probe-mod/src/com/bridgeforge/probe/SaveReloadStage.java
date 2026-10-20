package com.bridgeforge.probe;

import com.fs.starfarer.api.EveryFrameScript;
import com.fs.starfarer.api.Global;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * Opt-in save-and-reload fingerprint stage ({@code save_reload: {after_days, slot_note}} in bf_probe_config).
 *
 * Before: at in-game day N a transient EveryFrameScript logs {@code fingerprint|phase=before} lines, calls
 * CampaignUIAPI.cmdSave() (RC8-30, as Salvor's rig probe does) and, when the save returned true, stores the fingerprint in the
 * common file {@code bf_probe_fingerprint}. After: on the next game load whose campaign clock equals the stored timestamp the
 * fingerprint is recomputed, the stored one is logged again (source=file, so that log is self-contained), then
 * {@code phase=after} lines and {@code fingerprint|compare|equal=...;diff=<sections>} are logged.
 */
public final class SaveReloadStage {

    public static final String FILE = "bf_probe_fingerprint";
    private static final int STORED_TEXT_CAP = 40000;
    private static final int DIFF_LINE_CAP = 300;

    private SaveReloadStage() {
    }

    /** Called from BfProbeModPlugin.onGameLoad after the rig gate. Never throws. */
    public static void onGameLoad() {
        try {
            ProbeConfig config = ProbeConfig.load();
            if (config.saveReloadAfterDays <= 0) {
                return;
            }
            long now = Global.getSector().getClock().getTimestamp();
            JSONObject stored = readStored();
            if (stored != null && stored.optLong("ts", -1L) == now) {
                compareAfterReload(config, stored);
                return;
            }
            if (stored != null) {
                ProbeLog.emit("fingerprint", ProbeLog.STATUS_INFO, "skip",
                        "stored fingerprint is for ts=" + stored.optLong("ts", -1L) + ", this load is ts=" + now);
            }
            Global.getSector().addTransientScript(new BeforeScript(config, now));
        } catch (Throwable t) {
            ProbeLog.emit("fingerprint", ProbeLog.STATUS_FAIL, "stage", "load hook failed: " + t);
        }
    }

    private static JSONObject readStored() {
        try {
            if (!Global.getSettings().fileExistsInCommon(FILE)) {
                return null;
            }
            return new JSONObject(Global.getSettings().readTextFileFromCommon(FILE));
        } catch (Throwable t) {
            ProbeLog.emit("fingerprint", ProbeLog.STATUS_WARN, "skip", "stored fingerprint unreadable: " + t);
            return null;
        }
    }

    private static void logComputed(String phase, Map<String, String> sections) {
        for (String name : FingerprintSections.ORDER) {
            String text = sections.get(name);
            ProbeLog.emit("fingerprint", ProbeLog.STATUS_INFO, "phase=" + phase, "section=" + name
                    + ";count=" + FingerprintSections.lineCount(text) + ";len=" + text.length() + ";fnv=" + FingerprintSections.fnv64(text));
        }
    }

    private static JSONObject digestOf(String text) throws Exception {
        JSONObject digest = new JSONObject();
        digest.put("count", FingerprintSections.lineCount(text));
        digest.put("len", text.length());
        digest.put("fnv", FingerprintSections.fnv64(text));
        digest.put("truncated", text.length() > STORED_TEXT_CAP);
        digest.put("text", text.length() > STORED_TEXT_CAP ? text.substring(0, STORED_TEXT_CAP) : text);
        return digest;
    }

    private static void compareAfterReload(ProbeConfig config, JSONObject stored) throws Exception {
        Map<String, String> after = FingerprintSections.compute(config);
        JSONObject sections = stored.getJSONObject("sections");
        Map<String, JSONObject> before = new LinkedHashMap<String, JSONObject>();
        for (String name : FingerprintSections.ORDER) {
            JSONObject digest = sections.optJSONObject(name);
            if (digest != null) {
                before.put(name, digest);
                ProbeLog.emit("fingerprint", ProbeLog.STATUS_INFO, "phase=before", "section=" + name + ";count=" + digest.optInt("count")
                        + ";len=" + digest.optInt("len") + ";fnv=" + digest.optString("fnv") + ";source=file");
            }
        }
        logComputed("after", after);
        List<String> differing = new ArrayList<String>();
        for (String name : FingerprintSections.ORDER) {
            JSONObject digest = before.get(name);
            if (digest == null || !digest.optString("fnv").equals(FingerprintSections.fnv64(after.get(name)))) {
                differing.add(name);
                ProbeLog.emit("fingerprint", ProbeLog.STATUS_WARN, "diff",
                        "section=" + name + ";" + firstDifferences(digest == null ? "" : digest.optString("text"), after.get(name)));
            }
        }
        boolean equal = differing.isEmpty();
        StringBuilder diff = new StringBuilder();
        for (int i = 0; i < differing.size(); i++) {
            diff.append(i > 0 ? "," : "").append(differing.get(i));
        }
        ProbeLog.emit("fingerprint", equal ? ProbeLog.STATUS_INFO : ProbeLog.STATUS_FAIL, "compare",
                "equal=" + equal + ";diff=" + diff + ";sections=" + FingerprintSections.ORDER.length
                        + ";slot_note=" + stored.optString("slot_note"));
    }

    private static String firstDifferences(String beforeText, String afterText) {
        Set<String> beforeLines = new HashSet<String>(Arrays.asList(beforeText.split("\n")));
        Set<String> afterLines = new HashSet<String>(Arrays.asList(afterText.split("\n")));
        return "only_before=" + firstMissing(beforeText, afterLines) + ";only_after=" + firstMissing(afterText, beforeLines);
    }

    private static String firstMissing(String text, Set<String> other) {
        for (String line : text.split("\n")) {
            if (!other.contains(line)) {
                return (line.length() > DIFF_LINE_CAP ? line.substring(0, DIFF_LINE_CAP) : line).replace(';', ',');
            }
        }
        return "none";
    }

    /** Counts in-game days from the load, then fingerprints, saves and stores. Runs once. */
    private static final class BeforeScript implements EveryFrameScript {
        private final ProbeConfig config;
        private final long start;
        private boolean done;

        BeforeScript(ProbeConfig config, long start) {
            this.config = config;
            this.start = start;
        }

        @Override
        public void advance(float amount) {
            if (done || Global.getSector().getClock().getElapsedDaysSince(start) < config.saveReloadAfterDays) {
                return;
            }
            done = true;
            try {
                fingerprintAndSave();
            } catch (Throwable t) {
                ProbeLog.emit("fingerprint", ProbeLog.STATUS_FAIL, "save", "before-phase failed: " + t);
            }
        }

        private void fingerprintAndSave() throws Exception {
            long ts = Global.getSector().getClock().getTimestamp();
            Map<String, String> sections = FingerprintSections.compute(config);
            logComputed("before", sections);
            boolean saved = Global.getSector().getCampaignUI().cmdSave(); // RC8-30
            ProbeLog.emit("fingerprint", saved ? ProbeLog.STATUS_INFO : ProbeLog.STATUS_FAIL, "save",
                    "cmdSave returned " + saved + ";ts=" + ts + ";slot_note=" + config.saveReloadSlotNote);
            if (!saved) {
                return;
            }
            JSONObject root = new JSONObject();
            root.put("v", 1);
            root.put("ts", ts);
            root.put("slot_note", config.saveReloadSlotNote);
            root.put("probe", ProbeLog.VERSION);
            JSONObject stored = new JSONObject();
            for (Map.Entry<String, String> entry : sections.entrySet()) {
                stored.put(entry.getKey(), digestOf(entry.getValue()));
            }
            root.put("sections", stored);
            Global.getSettings().writeTextFileToCommon(FILE, root.toString());
            ProbeLog.emit("fingerprint", ProbeLog.STATUS_INFO, "stored", "file=" + FILE + ";ts=" + ts);
        }

        @Override
        public boolean isDone() {
            return done;
        }

        @Override
        public boolean runWhilePaused() {
            return false;
        }
    }
}
