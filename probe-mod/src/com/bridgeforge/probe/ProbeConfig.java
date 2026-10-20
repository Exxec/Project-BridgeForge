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
    // Vanilla factions the mod patches (a .faction file with no "id"), 0.2.9: their fleets are built too.
    public final List<String> patchedFactions = new ArrayList<String>();
    public float campaignIntervalDays = 5f;
    public float combatSeconds = 60f;
    public int combatCapPerSide = 12;
    public final List<String> setups = new ArrayList<String>();
    // Every variant/wing id the mod defines (ROADMAP P14 item 49). "ship" variants are built as SHIP
    // fleet members; "other" variants (fighter/module/wreck or non-mod hulls) only get an existence check.
    public final List<String> contentShipVariants = new ArrayList<String>();
    public final List<String> contentOtherVariants = new ArrayList<String>();
    public final List<String> contentWings = new ArrayList<String>();
    // variant id -> the hullId its .variant file names, for the "ship" variants (0.2.4).
    // Special item ids from data/campaign/special_items.csv (0.2.5).
    public final List<String> contentSpecialItems = new ArrayList<String>();
    // Star systems the mod creates, and its own planets.json types with their procgen weight (0.2.6).
    public final List<String> modSystems = new ArrayList<String>();
    public final Map<String, Float> modBodyTypes = new LinkedHashMap<String, Float>();
    public final Map<String, String> contentShipHulls = new LinkedHashMap<String, String>();
    // 0.2.12 (ROADMAP 46): fleet members the mod's missions name, and the target jar's top-level classes.
    public final List<String> missionShips = new ArrayList<String>();
    public final List<String> missionWings = new ArrayList<String>();
    public final List<String> classSweep = new ArrayList<String>();
    // 0.2.25: commodity ids the mod adds (data/campaign/commodities.csv minus vanilla's), and supply expectations
    // "commodity@industry" a test asks for (DNEEP food through AoTD farms, 2026-10-11).
    public final List<String> modCommodities = new ArrayList<String>();
    public final List<String> expectSupply = new ArrayList<String>();
    // 0.2.26: save the game once after the first day's checks, so a test can read and reload what a mod writes into a save
    // (Station Augments' market references, 2026-10-11).
    public boolean saveAfterChecks = false;
    // next version (ROADMAP 75 R6): opt-in save-and-reload fingerprint, save_reload: {after_days: N, slot_note: ...}; 0 = off.
    public int saveReloadAfterDays = 0;
    public String saveReloadSlotNote = "";

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

        JSONArray patched = root.optJSONArray("patched_factions");
        if (patched != null) {
            for (int i = 0; i < patched.length(); i++) {
                config.patchedFactions.add(patched.getString(i));
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

        JSONObject contentVariants = root.optJSONObject("content_variants");
        if (contentVariants != null) {
            addAll(contentVariants.optJSONArray("ship"), config.contentShipVariants);
            addAll(contentVariants.optJSONArray("other"), config.contentOtherVariants);
        }
        addAll(root.optJSONArray("content_wings"), config.contentWings);
        addAll(root.optJSONArray("content_special_items"), config.contentSpecialItems);
        addAll(root.optJSONArray("mod_systems"), config.modSystems);
        JSONObject missionFleets = root.optJSONObject("mission_fleets");
        if (missionFleets != null) {
            addAll(missionFleets.optJSONArray("ship"), config.missionShips);
            addAll(missionFleets.optJSONArray("wing"), config.missionWings);
        }
        addAll(root.optJSONArray("class_sweep"), config.classSweep);
        addAll(root.optJSONArray("mod_commodities"), config.modCommodities);
        addAll(root.optJSONArray("expect_supply"), config.expectSupply);
        config.saveAfterChecks = root.optBoolean("save_after_checks", false);
        JSONObject saveReload = root.optJSONObject("save_reload");
        if (saveReload != null) {
            config.saveReloadAfterDays = saveReload.optInt("after_days", 0);
            config.saveReloadSlotNote = saveReload.optString("slot_note", "");
        }
        JSONObject bodyTypes = root.optJSONObject("mod_body_types");
        if (bodyTypes != null) {
            JSONArray typeNames = bodyTypes.names();
            for (int i = 0; typeNames != null && i < typeNames.length(); i++) {
                String type = typeNames.getString(i);
                config.modBodyTypes.put(type, (float) bodyTypes.optDouble(type, 0.0));
            }
        }
        JSONObject shipHulls = root.optJSONObject("content_ship_hulls");
        if (shipHulls != null) {
            JSONArray names = shipHulls.names();
            for (int i = 0; names != null && i < names.length(); i++) {
                String variantId = names.getString(i);
                config.contentShipHulls.put(variantId, shipHulls.getString(variantId));
            }
        }

        JSONArray setups = root.optJSONArray("setups");
        if (setups != null) {
            for (int i = 0; i < setups.length(); i++) {
                config.setups.add(setups.getString(i));
            }
        }
        return config;
    }

    private static void addAll(JSONArray array, List<String> into) throws Exception {
        if (array == null) {
            return;
        }
        for (int i = 0; i < array.length(); i++) {
            into.add(array.getString(i));
        }
    }
}
