package com.bridgeforge.probe;

import com.fs.starfarer.api.Global;
import com.fs.starfarer.api.campaign.PlanetAPI;
import com.fs.starfarer.api.campaign.RingBandAPI;
import com.fs.starfarer.api.campaign.StarSystemAPI;
import com.fs.starfarer.api.campaign.econ.MarketAPI;
import com.fs.starfarer.api.combat.ShipHullSpecAPI;
import com.fs.starfarer.api.loading.HullModSpecAPI;
import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * "What was exercised": per mod id, how many items each stage touched, logged at the end as one
 * {@code BF-PROBE|<version>|exercised|mod=<id>|stage=count,...} line per mod. A mod whose counts are all zero ran through the
 * checks without anything of its own being looked at, which a PASS verdict alone cannot show (the harness flags it HOLLOW).
 *
 * Attribution is the one the content-ids and all-* stages use: the ids in {@code bf_probe_config}. A single-mod config belongs to
 * {@code target_mod_id}; a group config names each member's ids under {@code group_members}. Hull mods and combat ships also use
 * {@code getSourceMod()} of their spec ({@code ShipHullSpecAPI} and {@code HullModSpecAPI} extend {@code WithSourceMod};
 * {@code ModSpecAPI.getId()}; javap RC8 starfarer.api.jar, 2026-10-20). Systems, planets and rings of a group are not told apart per
 * member (the config merges them) and are counted for {@code (group)}. Counts are set, not added, so a stage that runs on every
 * campaign interval does not inflate them.
 */
final class ProbeExercised {

    static final String GROUP = "(group)";
    static final List<String> STAGES = Arrays.asList("hulls_built", "variants_resolved", "wings_resolved", "items", "planets", "rings",
            "markets", "submarkets", "missions", "fleets", "classes", "hullmods", "combat_ships");

    private static final Map<String, Map<String, Integer>> TALLY = new LinkedHashMap<String, Map<String, Integer>>();
    private static Owners owners;
    private static String lastEmitted = "";

    private ProbeExercised() {
    }

    /** Which mod owns which id, per kind of id (hulls, variants, wings, items, factions, missions, classes). */
    static final class Owners {
        final String target;
        final boolean group;
        final Map<String, Map<String, String>> byKind = new HashMap<String, Map<String, String>>();
        final List<String> mods = new ArrayList<String>();

        Owners(JSONObject root) {
            String id = root.optString("target_mod_id", "");
            JSONObject members = root.optJSONObject("group_members");
            group = members != null && members.length() > 0;
            target = group ? GROUP : id;
            if (!group) {
                if (id.length() > 0) {
                    mods.add(id);
                }
                return;
            }
            Iterator<?> keys = members.keys();
            while (keys.hasNext()) {
                String mod = (String) keys.next();
                mods.add(mod);
                JSONObject member = members.optJSONObject(mod);
                if (member == null) {
                    continue;
                }
                Iterator<?> kinds = member.keys();
                while (kinds.hasNext()) {
                    String kind = (String) kinds.next();
                    JSONArray ids = member.optJSONArray(kind);
                    for (int i = 0; ids != null && i < ids.length(); i++) {
                        Map<String, String> map = byKind.get(kind);
                        if (map == null) {
                            map = new HashMap<String, String>();
                            byKind.put(kind, map);
                        }
                        if (!map.containsKey(ids.optString(i))) {
                            map.put(ids.optString(i), mod);
                        }
                    }
                }
            }
        }

        /** The owner of an id of this kind, or null when it belongs to no probed mod (a group names every member's ids). */
        String ownerOf(String kind, String id) {
            if (!group) {
                return target.length() == 0 ? null : target;
            }
            Map<String, String> map = byKind.get(kind);
            return map == null ? null : map.get(id);
        }

        boolean isProbed(String mod) {
            return mods.contains(mod);
        }
    }

    private static Owners owners() {
        if (owners == null) {
            try {
                owners = new Owners(new JSONObject(Global.getSettings().readTextFileFromCommon(ProbeFiles.CONFIG)));
            } catch (Throwable t) {
                owners = new Owners(new JSONObject());
            }
            for (String mod : owners.mods) {
                bucket(mod);
            }
        }
        return owners;
    }

    private static Map<String, Integer> bucket(String mod) {
        Map<String, Integer> stages = TALLY.get(mod);
        if (stages == null) {
            stages = new LinkedHashMap<String, Integer>();
            TALLY.put(mod, stages);
        }
        return stages;
    }

    private static void add(Map<String, Map<String, Integer>> into, String mod, String stage) {
        if (mod == null) {
            return;
        }
        Map<String, Integer> stages = into.get(mod);
        if (stages == null) {
            stages = new LinkedHashMap<String, Integer>();
            into.put(mod, stages);
        }
        Integer now = stages.get(stage);
        stages.put(stage, now == null ? 1 : now + 1);
    }

    /** Called after a campaign stage ran without throwing. Never lets a tally failure reach the probe. */
    static void afterCheck(String stage, ProbeConfig config) {
        try {
            Owners o = owners();
            Map<String, Map<String, Integer>> fresh = new LinkedHashMap<String, Map<String, Integer>>();
            if ("content-ids".equals(stage)) {
                for (String id : config.contentShipVariants) {
                    add(fresh, o.ownerOf("variants", id), "hulls_built");
                }
                for (String id : config.contentOtherVariants) {
                    add(fresh, o.ownerOf("variants", id), "variants_resolved");
                }
                for (String id : config.contentWings) {
                    add(fresh, o.ownerOf("wings", id), "wings_resolved");
                }
                for (String id : config.contentSpecialItems) {
                    add(fresh, o.ownerOf("items", id), "items");
                }
            } else if ("mission-fleets".equals(stage)) {
                for (String id : config.missionShips) {
                    add(fresh, o.ownerOf("missions", id), "missions");
                }
                for (String id : config.missionWings) {
                    add(fresh, o.ownerOf("missions", id), "missions");
                }
            } else if ("class-sweep".equals(stage)) {
                for (String id : config.classSweep) {
                    add(fresh, o.ownerOf("classes", id), "classes");
                }
            } else if ("faction-fleet-gen".equals(stage)) {
                for (String id : config.factions) {
                    add(fresh, o.ownerOf("factions", id), "fleets");
                }
                for (String id : config.patchedFactions) {
                    add(fresh, o.ownerOf("factions", id), "fleets");
                }
            } else if ("hullmod-descriptions".equals(stage)) {
                for (HullModSpecAPI spec : Global.getSettings().getAllHullModSpecs()) {
                    if (spec.getSourceMod() != null && o.isProbed(spec.getSourceMod().getId())) {
                        add(fresh, spec.getSourceMod().getId(), "hullmods");
                    }
                }
            } else if ("submarket-stock".equals(stage)) {
                for (MarketAPI market : Global.getSector().getEconomy().getMarketsCopy()) {
                    String mod = o.ownerOf("factions", market.getFactionId());
                    add(fresh, mod, "markets");
                    int subs = market.getSubmarketsCopy().size();
                    for (int i = 0; mod != null && i < subs; i++) {
                        add(fresh, mod, "submarkets");
                    }
                }
            } else if ("rings-orbits".equals(stage) || "planet-specs".equals(stage)) {
                tallySystems(config, o, fresh, "rings-orbits".equals(stage));
            }
            for (Map.Entry<String, Map<String, Integer>> entry : fresh.entrySet()) {
                Map<String, Integer> stages = bucket(entry.getKey());
                for (Map.Entry<String, Integer> count : entry.getValue().entrySet()) {
                    Integer old = stages.get(count.getKey());
                    stages.put(count.getKey(), old == null ? count.getValue() : Math.max(old, count.getValue()));
                }
            }
        } catch (Throwable t) {
            // A tally problem must never become a probe problem.
        }
    }

    private static void tallySystems(ProbeConfig config, Owners o, Map<String, Map<String, Integer>> fresh, boolean rings) {
        for (StarSystemAPI system : Global.getSector().getStarSystems()) {
            boolean modSystem = config.modSystems.contains(system.getBaseName()) || config.modSystems.contains(system.getName());
            if (rings && modSystem) {
                List<RingBandAPI> bands = system.getEntities(RingBandAPI.class);
                for (int i = 0; i < bands.size(); i++) {
                    add(fresh, o.target, "rings");
                }
            }
            if (!rings) {
                for (PlanetAPI planet : system.getPlanets()) {
                    if (modSystem || config.modBodyTypes.containsKey(planet.getTypeId())) {
                        add(fresh, o.target, "planets");
                    }
                }
            }
        }
    }

    /** A combat ship was deployed: its hull's source mod when that is a probed mod, else the hull id's owner. */
    static void combatShip(ShipHullSpecAPI hull) {
        try {
            Owners o = owners();
            String mod = null;
            if (hull != null && hull.getSourceMod() != null && o.isProbed(hull.getSourceMod().getId())) {
                mod = hull.getSourceMod().getId();
            } else if (hull != null) {
                mod = o.ownerOf("hulls", hull.getHullId());
            }
            if (mod != null) {
                Map<String, Integer> stages = bucket(mod);
                Integer now = stages.get("combat_ships");
                stages.put("combat_ships", now == null ? 1 : now + 1);
            }
        } catch (Throwable t) {
            // see afterCheck
        }
    }

    /** One line per mod, when anything changed since the last time. */
    static void emitAll() {
        try {
            owners();
            StringBuilder all = new StringBuilder();
            List<String> lines = new ArrayList<String>();
            for (Map.Entry<String, Map<String, Integer>> entry : TALLY.entrySet()) {
                StringBuilder line = new StringBuilder();
                for (String stage : STAGES) {
                    Integer count = entry.getValue().get(stage);
                    line.append(line.length() == 0 ? "" : ",").append(stage).append('=').append(count == null ? 0 : count);
                }
                String text = "BF-PROBE|" + ProbeLog.VERSION + "|exercised|mod=" + entry.getKey().replace("|", "/") + "|" + line;
                lines.add(text);
                all.append(text).append('\n');
            }
            if (all.toString().equals(lastEmitted)) {
                return;
            }
            lastEmitted = all.toString();
            for (String text : lines) {
                Global.getLogger(ProbeExercised.class).info(text);
            }
        } catch (Throwable t) {
            // see afterCheck
        }
    }
}
