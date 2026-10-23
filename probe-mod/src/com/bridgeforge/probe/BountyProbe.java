package com.bridgeforge.probe;

import com.fs.starfarer.api.Global;
import org.json.JSONArray;
import org.json.JSONObject;

/**
 * Probe 0.3.2: spawn each MagicLib bounty a mod defines and confirm its fleet (EPTA's Artifact 667, 2026-10-22). Its faction,
 * narcepolis, knows one hull that has no fleet role, so the generic patrol check reports an empty patrol; the bounty fleet is
 * the faction's real use and was never exercised. Config {@code bounty_checks: {modId: [bountyId, ...]}} (written by
 * BridgeForge from the mod's data/config/modFiles/magicBounty_data.json).
 *
 * The MagicLib calls live in the loose script {@code data.scripts.bfprobe.MagicBountyCheck}, which the game compiles at load
 * against every enabled mod, so the jar keeps no compile dependency on MagicLib and uses no java.lang.reflect (forbidden by
 * RC8's script class loader). It is loaded with {@code getScriptClassLoader().loadClass(..).newInstance()}, the way the game
 * instantiates plugins. API (javap, RC8 starfarer.api.jar, 2026-10-22): SettingsAPI.getScriptClassLoader(), getModManager(),
 * ModManagerAPI.isModEnabled(String).
 */
public final class BountyProbe {

    static final String CHECK_CLASS = "data.scripts.bfprobe.MagicBountyCheck";

    private BountyProbe() {
    }

    public static void run() throws Exception {
        if (!Global.getSettings().fileExistsInCommon(ProbeFiles.CONFIG)) {
            return;
        }
        JSONObject root = new JSONObject(Global.getSettings().readTextFileFromCommon(ProbeFiles.CONFIG));
        JSONObject checks = root.optJSONObject("bounty_checks");
        if (checks == null || checks.names() == null) {
            return;
        }
        if (!Global.getSettings().getModManager().isModEnabled("MagicLib")) {
            ProbeLog.emit("bounty", ProbeLog.STATUS_INFO, "magiclib", "MagicLib is not enabled; bounty checks skipped");
            return;
        }
        BountyCheck check = (BountyCheck) Global.getSettings().getScriptClassLoader().loadClass(CHECK_CLASS).newInstance();
        JSONArray mods = checks.names();
        for (int i = 0; i < mods.length(); i++) {
            String modId = mods.getString(i);
            JSONArray ids = checks.optJSONArray(modId);
            for (int j = 0; ids != null && j < ids.length(); j++) {
                String id = ids.getString(j);
                try {
                    check.check(modId, id);
                } catch (Throwable t) {
                    ProbeLog.emit("bounty", ProbeLog.STATUS_FAIL, modId + "/" + id, t.getClass().getSimpleName() + ": " + t.getMessage());
                }
            }
        }
    }
}
