package com.bridgeforge.probe;

import com.fs.starfarer.api.Global;
import com.fs.starfarer.api.campaign.CampaignFleetAPI;
import com.fs.starfarer.api.campaign.CargoAPI;
import com.fs.starfarer.api.campaign.LocationAPI;
import com.fs.starfarer.api.campaign.RingBandAPI;
import com.fs.starfarer.api.campaign.StarSystemAPI;
import com.fs.starfarer.api.campaign.econ.Industry;
import com.fs.starfarer.api.campaign.econ.MarketAPI;
import com.fs.starfarer.api.campaign.econ.MarketConditionAPI;
import com.fs.starfarer.api.campaign.econ.SubmarketAPI;
import com.fs.starfarer.api.combat.ShipVariantAPI;
import com.fs.starfarer.api.fleet.FleetMemberAPI;
import com.fs.starfarer.api.fleet.FleetMemberStatusAPI;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

/**
 * Save-and-reload fingerprint (ROADMAP item 75 R6 evidence emitter): a stable, sorted, canonical text of sector state in
 * named sections, each with a deterministic 64-bit FNV-1a digest (no java.security: the script sandbox may forbid it).
 *
 * Public API only (javap RC8 starfarer.api.jar). Floats are written as integer hundredths so the text does not depend on a
 * locale. Armor per module is NOT exposed to campaign code: FleetMemberStatusAPI has only getHullFraction(int) per
 * module (index 0 is the ship, then the module slots in order) and one aggregate getArmorDamageTaken(), so those are recorded.
 */
public final class FingerprintSections {

    public static final String[] ORDER = {"markets", "systems", "rings", "fleets", "player", "cargo", "mod", "totals"};
    private static final long FNV_OFFSET = 0xcbf29ce484222325L;
    private static final long FNV_PRIME = 0x100000001b3L;

    private FingerprintSections() {
    }

    /** Section name -> canonical text (lines sorted, joined with a newline). */
    public static Map<String, String> compute(ProbeConfig config) {
        Map<String, List<String>> lines = new LinkedHashMap<String, List<String>>();
        for (String name : ORDER) {
            lines.put(name, new ArrayList<String>());
        }
        List<String> modFactions = new ArrayList<String>(config.factions);
        modFactions.addAll(config.patchedFactions);
        int[] totals = new int[5]; // markets, systems, planets, fleets, player members
        markets(lines, modFactions, totals);
        systems(lines, config, totals);
        fleets(lines, modFactions, totals);
        player(lines, totals);
        lines.get("totals").add("markets=" + totals[0] + ";systems=" + totals[1] + ";planets=" + totals[2]
                + ";fleets=" + totals[3] + ";playerMembers=" + totals[4]);
        Map<String, String> out = new LinkedHashMap<String, String>();
        for (Map.Entry<String, List<String>> entry : lines.entrySet()) {
            List<String> sorted = new ArrayList<String>(entry.getValue());
            Collections.sort(sorted);
            out.put(entry.getKey(), join(sorted, "\n"));
        }
        return out;
    }

    private static void markets(Map<String, List<String>> lines, List<String> modFactions, int[] totals) {
        for (MarketAPI market : Global.getSector().getEconomy().getMarketsCopy()) {
            totals[0]++;
            List<String> conditions = new ArrayList<String>();
            for (MarketConditionAPI condition : market.getConditions()) {
                conditions.add(condition.getId());
            }
            List<String> industries = new ArrayList<String>();
            for (Industry industry : market.getIndustries()) {
                industries.add(industry.getId());
            }
            List<String> submarkets = new ArrayList<String>();
            for (SubmarketAPI submarket : market.getSubmarketsCopy()) {
                submarkets.add(submarket.getSpecId());
            }
            Collections.sort(conditions);
            Collections.sort(industries);
            Collections.sort(submarkets);
            String line = market.getId() + ";faction=" + market.getFactionId() + ";size=" + market.getSize()
                    + ";cond=" + join(conditions, ",") + ";ind=" + join(industries, ",") + ";sub=" + join(submarkets, ",");
            lines.get("markets").add(line);
            if (modFactions.contains(market.getFactionId())) {
                lines.get("mod").add("market:" + line);
            }
        }
    }

    private static void systems(Map<String, List<String>> lines, ProbeConfig config, int[] totals) {
        for (StarSystemAPI system : Global.getSector().getStarSystems()) {
            totals[1]++;
            int planets = system.getPlanets().size();
            totals[2] += planets;
            String line = system.getId() + ";planets=" + planets + ";entities=" + system.getAllEntities().size();
            lines.get("systems").add(line);
            if (config.modSystems.contains(system.getId())) {
                lines.get("mod").add("system:" + line);
            }
            for (Object band : system.getEntities(RingBandAPI.class)) {
                RingBandAPI ring = (RingBandAPI) band;
                lines.get("rings").add(system.getId() + ";band=" + ring.getBandIndex() + ";mid=" + hundredths(ring.getMiddleRadius())
                        + ";width=" + hundredths(ring.getBandWidthInEngine()) + ";days=" + hundredths(ring.getOrbitDays()));
            }
        }
    }

    private static void fleets(Map<String, List<String>> lines, List<String> modFactions, int[] totals) {
        CampaignFleetAPI playerFleet = Global.getSector().getPlayerFleet();
        Map<String, Integer> perFaction = new TreeMap<String, Integer>();
        for (LocationAPI location : Global.getSector().getAllLocations()) {
            for (CampaignFleetAPI fleet : location.getFleets()) {
                if (fleet == playerFleet) {
                    continue;
                }
                totals[3]++;
                String faction = fleet.getFaction() == null ? "none" : fleet.getFaction().getId();
                Integer seen = perFaction.get(faction);
                perFaction.put(faction, seen == null ? 1 : seen + 1);
            }
        }
        for (Map.Entry<String, Integer> entry : perFaction.entrySet()) {
            String line = entry.getKey() + ";fleets=" + entry.getValue();
            lines.get("fleets").add(line);
            if (modFactions.contains(entry.getKey())) {
                lines.get("mod").add("fleets:" + line);
            }
        }
    }

    private static void player(Map<String, List<String>> lines, int[] totals) {
        CampaignFleetAPI fleet = Global.getSector().getPlayerFleet();
        if (fleet == null) {
            return;
        }
        for (FleetMemberAPI member : fleet.getFleetData().getMembersListCopy()) {
            totals[4]++;
            ShipVariantAPI variant = member.getVariant();
            FleetMemberStatusAPI status = member.getStatus();
            StringBuilder line = new StringBuilder(member.getId());
            line.append(";hull=").append(member.getHullId());
            line.append(";variant=").append(variant == null ? "none" : variant.getHullVariantId());
            line.append(";cr=").append(hundredths(member.getRepairTracker().getCR()));
            line.append(";hullFraction=").append(hundredths(status.getHullFraction()));
            line.append(";armorDamageTaken=").append(hundredths(status.getArmorDamageTaken()));
            List<String> slots = variant == null ? null : variant.getModuleSlots();
            if (slots != null) {
                for (int i = 0; i < slots.size(); i++) {
                    // Status index 0 is the ship itself; modules follow in slot order (FleetMemberStatusAPI.getHullFraction(int)).
                    line.append(";module").append(i).append('=').append(slots.get(i)).append('/');
                    ShipVariantAPI module = variant.getModuleVariant(slots.get(i));
                    line.append(module == null ? "none" : module.getHullVariantId());
                    line.append('/').append(i + 1 < status.getNumStatuses() ? hundredths(status.getHullFraction(i + 1)) : "n/a");
                }
            }
            lines.get("player").add(line.toString());
        }
        CargoAPI cargo = fleet.getCargo();
        lines.get("cargo").add("mC=" + hundredths(cargo.getMaxCapacity()) + ";mF=" + hundredths(cargo.getMaxFuel())
                + ";mP=" + hundredths(cargo.getMaxPersonnel()) + ";spaceUsed=" + hundredths(cargo.getSpaceUsed())
                + ";fuel=" + hundredths(cargo.getFuel()) + ";crew=" + cargo.getCrew() + ";supplies=" + hundredths(cargo.getSupplies()));
    }

    /** A float as integer hundredths, so the canonical text never depends on a locale or a float formatter. */
    static String hundredths(float value) {
        return String.valueOf(Math.round(value * 100f));
    }

    /** 64-bit FNV-1a over the UTF-16 code units (two bytes each), as 16 lowercase hex digits. */
    public static String fnv64(String text) {
        long hash = FNV_OFFSET;
        for (int i = 0; i < text.length(); i++) {
            char c = text.charAt(i);
            hash = (hash ^ (c & 0xff)) * FNV_PRIME;
            hash = (hash ^ ((c >> 8) & 0xff)) * FNV_PRIME;
        }
        String hex = Long.toHexString(hash);
        StringBuilder padded = new StringBuilder();
        for (int i = hex.length(); i < 16; i++) {
            padded.append('0');
        }
        return padded.append(hex).toString();
    }

    public static int lineCount(String text) {
        return text.length() == 0 ? 0 : text.split("\n", -1).length;
    }

    private static String join(List<String> parts, String separator) {
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < parts.size(); i++) {
            if (i > 0) {
                out.append(separator);
            }
            out.append(parts.get(i));
        }
        return out.toString();
    }
}
