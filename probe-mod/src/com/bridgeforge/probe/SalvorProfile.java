package com.bridgeforge.probe;

import com.fs.starfarer.api.Global;
import org.apache.log4j.Logger;

/**
 * The {@code salvor} profile (BridgeForge ROADMAP-3 item 78.5): Salvor's rig stages folded into this probe, so one mod is built
 * for both tools. Salvor's own probe (tools/java/salvor_rig_probe) is deprecated in favour of this.
 *
 * Selection: the mod folder contains {@link #MARKER} (a JSON file with {@code "profile":"salvor"}); only Salvor's
 * {@code rig-build-probe} adds it, the BridgeForge builds never do. It is read with {@code SettingsAPI.loadJSON(path, modId)}, a
 * read of the mod's own file through the public API (no file APIs, no common files). When selected, every BridgeForge check is
 * skipped (no campaign probe, perf script, scenario or save-and-reload fingerprint), so the game stays quiet: the marker file is
 * itself the rig gate, and Salvor's probe was rig-only by its mod_info in the same way.
 *
 * Settings stay JVM properties, as Salvor's {@code rig_auto} passes them: {@code -Dsalvor.rig.mode=save|reload} (default reload)
 * and {@code -Dsalvor.rig.days=N} (default 3).
 *
 * Log lines, written raw through the game logger (the harness matches by substring, so the logger prefix does not matter):
 * <pre>
 *   salvor-rig|INFO|load|newGame=false|ts=&lt;clock timestamp&gt;
 *   salvor-rig|INFO|days|&lt;n&gt;
 *   salvor-rig|INFO|save|requested
 *   salvor-rig|INFO|save|done|ts=&lt;clock timestamp&gt;       (afterGameSave)
 *   salvor-rig|INFO|session|complete                       (reload mode)
 * </pre>
 */
final class SalvorProfile {

    static final String MARKER = "data/config/bf_probe_profile.json";
    static final String PROFILE_NAME = "salvor";
    static final String MOD_ID = "bridgeforge_probe";
    static final String MODE_PROPERTY = "salvor.rig.mode";
    static final String DAYS_PROPERTY = "salvor.rig.days";
    static final String MODE_SAVE = "save";
    static final String MODE_RELOAD = "reload";
    static final int DEFAULT_DAYS = 3;

    private static final Logger LOG = Global.getLogger(SalvorProfile.class);
    private static Boolean selected;

    private SalvorProfile() {
    }

    /** True when the built mod folder carries the salvor marker. Never throws; a missing or unreadable marker means not selected. */
    static boolean isSelected() {
        if (selected == null) {
            boolean value = false;
            try {
                value = PROFILE_NAME.equals(Global.getSettings().loadJSON(MARKER, MOD_ID).optString("profile", ""));
            } catch (Throwable t) {
                value = false;
            }
            selected = Boolean.valueOf(value);
        }
        return selected.booleanValue();
    }

    static void onGameLoad(boolean newGame) {
        try {
            long ts = Global.getSector().getClock().getTimestamp();
            LOG.info("salvor-rig|INFO|load|newGame=" + newGame + "|ts=" + ts);
            final boolean save = MODE_SAVE.equals(System.getProperty(MODE_PROPERTY, MODE_RELOAD));
            final int days = Integer.getInteger(DAYS_PROPERTY, DEFAULT_DAYS).intValue();
            Global.getSector().addTransientScript(new DayCountScript(ts, days, "salvor", new DayCountScript.Action() {
                @Override
                public void run() {
                    LOG.info("salvor-rig|INFO|days|" + days);
                    if (save) {
                        LOG.info("salvor-rig|INFO|save|requested");
                        Global.getSector().getCampaignUI().cmdSave(); // RC8-30
                    } else {
                        LOG.info("salvor-rig|INFO|session|complete");
                    }
                }
            }));
        } catch (Throwable t) {
            LOG.info("salvor-rig|FAIL|load|" + t);
        }
    }

    static void afterGameSave() {
        try {
            LOG.info("salvor-rig|INFO|save|done|ts=" + Global.getSector().getClock().getTimestamp());
        } catch (Throwable t) {
            LOG.info("salvor-rig|FAIL|save|" + t);
        }
    }
}
