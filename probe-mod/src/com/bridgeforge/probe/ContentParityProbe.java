package com.bridgeforge.probe;

import com.fs.starfarer.api.Global;
import com.fs.starfarer.api.ModSpecAPI;
import com.fs.starfarer.api.SettingsAPI;
import com.fs.starfarer.api.campaign.PlanetSpecAPI;
import com.fs.starfarer.api.campaign.StarSystemAPI;
import com.fs.starfarer.api.loading.WithSourceMod;
import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * ROADMAP 77.17 live content parity: for each mod in the config's {@code content_parity} object
 * ({@code {modId: {kind: [ids]}}}, written by BridgeForge from the candidate's working copy), counts how many of the
 * expected ids the running game actually loaded, and logs
 * {@code BF-PROBE|ver|content-parity|INFO|mod=<id>|rules=12/12,hulls=3/4,...,src_hulls=3} plus one FAIL line per kind with a
 * shortfall ({@code kind=rules missing 0/12: id,id ...}). FIX-001 (a whole rules.csv missing) is the shape this catches.
 *
 * API (javap, RC8 starfarer.api.jar, 2026-10-20): SettingsAPI.getHullSpec/getWeaponSpec/getFighterWingSpec/getHullModSpec/
 * getIndustrySpec/getMarketConditionSpec(String); getAllSubmarketSpecs(); getAllPlanetSpecs(); getAllShipHullSpecs/
 * getAllWeaponSpecs/getActuallyAllWeaponSpecs/getAllFighterWingSpecs/getAllHullModSpecs/getAllIndustrySpecs/
 * getAllMarketConditionSpecs(); getMergedSpreadsheetData(String idColumn, String path) -> JSONArray. WithSourceMod.getSourceMod()
 * (ModSpecAPI.getId()) is implemented by hull, weapon, wing, hullmod, industry, condition and planet specs, not submarkets.
 */
public final class ContentParityProbe {

    private static final int MAX_LISTED_IDS = 40;
    private static final String RULES_PATH = "data/campaign/rules.csv";

    private ContentParityProbe() {
    }

    public static void run() throws Exception {
        if (!Global.getSettings().fileExistsInCommon(ProbeFiles.CONFIG)) {
            return;
        }
        JSONObject root = new JSONObject(Global.getSettings().readTextFileFromCommon(ProbeFiles.CONFIG));
        JSONObject parity = root.optJSONObject("content_parity");
        if (parity == null || parity.names() == null) {
            ProbeLog.emit("content-parity", ProbeLog.STATUS_INFO, "mod=none", "no content_parity in the probe config");
            return;
        }
        Set<String> ruleIds = null;
        JSONArray modNames = parity.names();
        for (int i = 0; i < modNames.length(); i++) {
            String modId = modNames.getString(i);
            JSONObject kinds = parity.optJSONObject(modId);
            if (kinds == null) {
                continue;
            }
            if (kinds.has("rules") && ruleIds == null) {
                ruleIds = loadedRuleIds();
            }
            checkMod(modId, kinds, ruleIds);
        }
    }

    private static void checkMod(String modId, JSONObject kinds, Set<String> ruleIds) throws Exception {
        SettingsAPI settings = Global.getSettings();
        Map<String, Set<String>> loaded = new LinkedHashMap<String, Set<String>>();
        Map<String, Integer> fromSource = new LinkedHashMap<String, Integer>();
        loaded.put("rules", ruleIds == null ? new HashSet<String>() : ruleIds);
        loaded.put("hulls", resolved(kinds, "hulls", new Lookup() {
            public boolean has(String id) {
                return settings.getHullSpec(id) != null;
            }
        }));
        loaded.put("weapons", resolved(kinds, "weapons", new Lookup() {
            public boolean has(String id) {
                return settings.getWeaponSpec(id) != null;
            }
        }));
        loaded.put("wings", resolved(kinds, "wings", new Lookup() {
            public boolean has(String id) {
                return settings.getFighterWingSpec(id) != null;
            }
        }));
        loaded.put("hullmods", resolved(kinds, "hullmods", new Lookup() {
            public boolean has(String id) {
                return settings.getHullModSpec(id) != null;
            }
        }));
        loaded.put("industries", resolved(kinds, "industries", new Lookup() {
            public boolean has(String id) {
                return settings.getIndustrySpec(id) != null;
            }
        }));
        loaded.put("conditions", resolved(kinds, "conditions", new Lookup() {
            public boolean has(String id) {
                return settings.getMarketConditionSpec(id) != null;
            }
        }));
        Set<String> submarkets = new HashSet<String>();
        for (com.fs.starfarer.api.campaign.econ.SubmarketSpecAPI spec : settings.getAllSubmarketSpecs()) {
            submarkets.add(spec.getId());
        }
        loaded.put("submarkets", submarkets);
        Set<String> systems = new HashSet<String>();
        for (StarSystemAPI system : Global.getSector().getStarSystems()) {
            systems.add(system.getBaseName());
            systems.add(system.getName());
            systems.add(system.getId());
        }
        loaded.put("systems", systems);
        Set<String> planetTypes = new HashSet<String>();
        for (PlanetSpecAPI spec : settings.getAllPlanetSpecs()) {
            planetTypes.add(spec.getPlanetType());
            countFrom(fromSource, "planet_types", modId, spec);
        }
        loaded.put("planet_types", planetTypes);
        countSources(fromSource, modId, settings);

        StringBuilder summary = new StringBuilder();
        List<String[]> shortfalls = new ArrayList<String[]>();
        JSONArray kindNames = kinds.names();
        for (int i = 0; kindNames != null && i < kindNames.length(); i++) {
            String kind = kindNames.getString(i);
            JSONArray wanted = kinds.optJSONArray(kind);
            Set<String> have = loaded.get(kind);
            if (wanted == null || have == null) {
                continue;
            }
            List<String> missing = new ArrayList<String>();
            for (int j = 0; j < wanted.length(); j++) {
                if (!have.contains(wanted.getString(j))) {
                    missing.add(wanted.getString(j));
                }
            }
            summary.append(kind).append('=').append(wanted.length() - missing.size()).append('/').append(wanted.length()).append(',');
            if (!missing.isEmpty()) {
                shortfalls.add(new String[] {kind, (wanted.length() - missing.size()) + "/" + wanted.length(), join(missing)});
            }
        }
        for (Map.Entry<String, Integer> entry : fromSource.entrySet()) {
            summary.append("src_").append(entry.getKey()).append('=').append(entry.getValue()).append(',');
        }
        ProbeLog.emit("content-parity", ProbeLog.STATUS_INFO, "mod=" + modId, trimComma(summary));
        for (String[] shortfall : shortfalls) {
            ProbeLog.emit("content-parity", ProbeLog.STATUS_FAIL, "mod=" + modId,
                    "kind=" + shortfall[0] + " missing " + shortfall[1] + ": " + shortfall[2]);
        }
    }

    /** Rule ids the game merged from every enabled mod's rules.csv (an absent file contributes nothing). */
    private static Set<String> loadedRuleIds() {
        Set<String> ids = new HashSet<String>();
        try {
            JSONArray rows = Global.getSettings().getMergedSpreadsheetData("id", RULES_PATH);
            for (int i = 0; rows != null && i < rows.length(); i++) {
                String id = rows.getJSONObject(i).optString("id", "").trim();
                if (!id.isEmpty()) {
                    ids.add(id);
                }
            }
        } catch (Throwable t) {
            ProbeLog.emit("content-parity", ProbeLog.STATUS_WARN, "rules", "could not read merged rules.csv: " + t);
        }
        return ids;
    }

    /** The expected ids of one kind that a per-id spec lookup resolves. */
    private static Set<String> resolved(JSONObject kinds, String kind, Lookup lookup) {
        Set<String> found = new HashSet<String>();
        JSONArray wanted = kinds.optJSONArray(kind);
        for (int i = 0; wanted != null && i < wanted.length(); i++) {
            String id = wanted.optString(i, "");
            try {
                if (!id.isEmpty() && lookup.has(id)) {
                    found.add(id);
                }
            } catch (Throwable t) {
                // an id the getter throws for counts as not loaded
            }
        }
        return found;
    }

    /** Every loaded spec of each kind whose source mod is this mod, to show excess beside the expected count. */
    private static void countSources(Map<String, Integer> counts, String modId, SettingsAPI settings) {
        List<? extends WithSourceMod> hulls = settings.getAllShipHullSpecs();
        countAll(counts, "hulls", modId, hulls);
        List<WithSourceMod> weapons = new ArrayList<WithSourceMod>(settings.getActuallyAllWeaponSpecs());
        weapons.addAll(settings.getAllWeaponSpecs());
        countAll(counts, "weapons", modId, distinct(weapons));
        countAll(counts, "wings", modId, settings.getAllFighterWingSpecs());
        countAll(counts, "hullmods", modId, settings.getAllHullModSpecs());
        countAll(counts, "industries", modId, settings.getAllIndustrySpecs());
        countAll(counts, "conditions", modId, settings.getAllMarketConditionSpecs());
    }

    private static List<WithSourceMod> distinct(List<WithSourceMod> specs) {
        Set<WithSourceMod> seen = new HashSet<WithSourceMod>(specs);
        return new ArrayList<WithSourceMod>(seen);
    }

    private static void countAll(Map<String, Integer> counts, String kind, String modId, List<? extends WithSourceMod> specs) {
        counts.put(kind, 0);
        for (WithSourceMod spec : specs) {
            countFrom(counts, kind, modId, spec);
        }
    }

    private static void countFrom(Map<String, Integer> counts, String kind, String modId, WithSourceMod spec) {
        ModSpecAPI source = spec == null ? null : spec.getSourceMod();
        Integer now = counts.get(kind);
        int base = now == null ? 0 : now;
        counts.put(kind, source != null && modId.equals(source.getId()) ? base + 1 : base);
    }

    private static String join(List<String> ids) {
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < ids.size() && i < MAX_LISTED_IDS; i++) {
            out.append(i == 0 ? "" : ",").append(ids.get(i));
        }
        return ids.size() > MAX_LISTED_IDS ? out + " ..." : out.toString();
    }

    private static String trimComma(StringBuilder text) {
        return text.length() > 0 && text.charAt(text.length() - 1) == ',' ? text.substring(0, text.length() - 1) : text.toString();
    }

    private interface Lookup {
        boolean has(String id);
    }
}
