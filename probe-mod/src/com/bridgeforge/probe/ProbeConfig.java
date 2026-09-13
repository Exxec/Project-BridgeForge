package com.bridgeforge.probe;

import com.fs.starfarer.api.Global;
import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Parses the {@code bf_probe_config} common file BridgeForge writes before a
 * probe run: the target mod id, the hull ids under test (non-module,
 * non-fighter), one variant id per hull, custom entity ids to track, and the
 * check intervals.
 */
public final class ProbeConfig {

    public String targetModId = "";
    public final List<String> hulls = new ArrayList<String>();
    public final Map<String, String> variantByHull = new LinkedHashMap<String, String>();
    public final List<String> trackEntities = new ArrayList<String>();
    // The target mod's own faction ids (data/world/factions/*.faction), checked even with no markets.
    public final List<String> factions = new ArrayList<String>();
    public float campaignIntervalDays = 5f;
    public float combatSeconds = 60f;
    public int combatCapPerSide = 12;
    public final List<String> setups = new ArrayList<String>();

    public static ProbeConfig load() throws Exception {
        ProbeConfig config = new ProbeConfig();
        if (!Global.getSettings().fileExistsInCommon(ProbeFiles.CONFIG)) {
            throw new IllegalStateException(ProbeFiles.CONFIG + " common file not found");
        }
        String text = Global.getSettings().readTextFileFromCommon(ProbeFiles.CONFIG);
        JSONObject root = new JSONObject(text);

        config.targetModId = root.optString("target_mod_id", "");

        JSONArray hullsArr = root.optJSONArray("hulls");
        if (hullsArr != null) {
            for (int i = 0; i < hullsArr.length(); i++) {
                config.hulls.add(hullsArr.getString(i));
            }
        }

        JSONObject variants = root.optJSONObject("variants");
        if (variants != null) {
            Iterator<?> keys = variants.keys();
            while (keys.hasNext()) {
                String key = (String) keys.next();
                config.variantByHull.put(key, variants.getString(key));
            }
        }

        JSONArray track = root.optJSONArray("track_entities");
        if (track != null) {
            for (int i = 0; i < track.length(); i++) {
                config.trackEntities.add(track.getString(i));
            }
        }

        JSONArray factions = root.optJSONArray("factions");
        if (factions != null) {
            for (int i = 0; i < factions.length(); i++) {
                config.factions.add(factions.getString(i));
            }
        }

        config.campaignIntervalDays = (float) root.optDouble("campaign_interval_days", 5.0);
        config.combatSeconds = (float) root.optDouble("combat_seconds", 60.0);
        config.combatCapPerSide = root.optInt("combat_cap_per_side", 12);

        JSONArray setups = root.optJSONArray("setups");
        if (setups != null) {
            for (int i = 0; i < setups.length(); i++) {
                config.setups.add(setups.getString(i));
            }
        }
        return config;
    }
}
