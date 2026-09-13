package com.bridgeforge.probe;

import com.fs.starfarer.api.Global;
import com.fs.starfarer.api.campaign.CampaignFleetAPI;
import com.fs.starfarer.api.campaign.FactionAPI;
import com.fs.starfarer.api.campaign.LocationAPI;
import com.fs.starfarer.api.campaign.RepLevel;
import com.fs.starfarer.api.campaign.SectorEntityToken;
import com.fs.starfarer.api.campaign.StarSystemAPI;
import com.fs.starfarer.api.campaign.rules.MemoryAPI;
import com.fs.starfarer.api.fleet.FleetMemberAPI;
import com.fs.starfarer.api.fleet.FleetMemberType;
import com.fs.starfarer.api.impl.campaign.ids.ShipRoles;

import java.util.List;

/**
 * Applies {@code bf_probe_config}'s {@code setups} list (roadmap P3b-C) exactly once per save,
 * through the public API only, after the first campaign tick.
 *
 * Guarded by a sector memory key ({@code $bfprobe_setup_applied_<hash>}, hash of the whole setups
 * list joined) so a saved-and-reloaded game never re-applies (which would, e.g., double credits or
 * spawn a second pirate fleet). A different setups list (different mod/scenario run against the same
 * save) gets a different key and so still applies once.
 *
 * Every setup spec is applied independently inside its own try/catch(Throwable): one malformed or
 * failing spec never blocks the rest, matching {@link CampaignProbeScript}'s existing per-check
 * isolation. Uses no reflection, no java.io.File*, no java.nio.file (all forbidden by RC8's script
 * sandbox) -- only the public campaign API.
 */
final class ProbeSetup {

    // The vanilla player faction id string ("player"); a named constant rather than a magic
    // literal repeated at each call site.
    private static final String PLAYER_FACTION_ID = "player";

    private ProbeSetup() {
    }

    static void applyOnce(List<String> setups) {
        if (setups == null || setups.isEmpty()) {
            return;
        }
        StringBuilder joined = new StringBuilder();
        for (String setup : setups) {
            joined.append(setup).append('|');
        }
        String key = "$bfprobe_setup_applied_" + Integer.toHexString(joined.toString().hashCode());
        MemoryAPI memory = Global.getSector().getMemoryWithoutUpdate();
        if (memory.contains(key) && memory.getBoolean(key)) {
            return;
        }
        for (String setup : setups) {
            applyOne(setup);
        }
        memory.set(key, Boolean.TRUE);
    }

    /**
     * Applies every setup unconditionally, with no persistent-memory guard (roadmap P3c-1's
     * {@code apply = every-load}): the caller (CampaignProbeScript, via a freshly re-parsed
     * bf_probe_profile) decides when this runs, once per game load.
     */
    static void applyAlways(List<String> setups) {
        if (setups == null || setups.isEmpty()) {
            return;
        }
        for (String setup : setups) {
            applyOne(setup);
        }
    }

    private static void applyOne(String setup) {
        try {
            if (setup.startsWith("rep:")) {
                applyRep(setup);
            } else if (setup.startsWith("credits:")) {
                applyCredits(setup);
            } else if (setup.startsWith("ship:")) {
                applyShip(setup);
            } else if (setup.startsWith("spawn-fleet:")) {
                applySpawnFleet(setup);
            } else if (setup.startsWith("jump:")) {
                applyJump(setup);
            } else {
                ProbeLog.emit("setup", ProbeLog.STATUS_FAIL, setup, "Unrecognized setup kind");
            }
        } catch (Throwable t) {
            ProbeLog.emit("setup", ProbeLog.STATUS_FAIL, setup, t.getClass().getName() + ": " + t.getMessage());
        }
    }

    // ---- rep:<faction>=<RepLevel-or-number> -------------------------------------------

    private static void applyRep(String setup) {
        String body = setup.substring("rep:".length());
        int eq = body.indexOf('=');
        if (eq < 0) {
            ProbeLog.emit("setup", ProbeLog.STATUS_FAIL, setup, "Missing '=' in rep setup");
            return;
        }
        String factionId = body.substring(0, eq);
        String value = body.substring(eq + 1).trim();
        FactionAPI faction = Global.getSector().getFaction(factionId);
        if (faction == null) {
            ProbeLog.emit("setup", ProbeLog.STATUS_FAIL, setup, "Unknown faction: " + factionId);
            return;
        }
        try {
            RepLevel level = RepLevel.valueOf(value.toUpperCase());
            faction.setRelationship(PLAYER_FACTION_ID, level);
        } catch (IllegalArgumentException notALevelName) {
            float numeric = Float.parseFloat(value);
            faction.setRelationship(PLAYER_FACTION_ID, numeric);
        }
        ProbeLog.emit("setup", ProbeLog.STATUS_OK, setup, "faction=" + factionId + " value=" + value);
    }

    // ---- credits:<N> --------------------------------------------------------------------

    private static void applyCredits(String setup) {
        String body = setup.substring("credits:".length());
        float amount = Float.parseFloat(body.trim());
        CampaignFleetAPI player = Global.getSector().getPlayerFleet();
        if (player == null) {
            ProbeLog.emit("setup", ProbeLog.STATUS_FAIL, setup, "No player fleet");
            return;
        }
        player.getCargo().getCredits().add(amount);
        ProbeLog.emit("setup", ProbeLog.STATUS_OK, setup, "credits+=" + amount);
    }

    // ---- ship:<variant_id>[:<count>] -----------------------------------------------------

    private static void applyShip(String setup) {
        String body = setup.substring("ship:".length());
        String variantId;
        int count = 1;
        int colon = body.indexOf(':');
        if (colon >= 0) {
            variantId = body.substring(0, colon);
            count = Integer.parseInt(body.substring(colon + 1).trim());
        } else {
            variantId = body;
        }
        CampaignFleetAPI player = Global.getSector().getPlayerFleet();
        if (player == null) {
            ProbeLog.emit("setup", ProbeLog.STATUS_FAIL, setup, "No player fleet");
            return;
        }
        for (int i = 0; i < count; i++) {
            FleetMemberAPI member = Global.getFactory().createFleetMember(FleetMemberType.SHIP, variantId);
            player.getFleetData().addFleetMember(member);
        }
        ProbeLog.emit("setup", ProbeLog.STATUS_OK, setup, "variant=" + variantId + " count=" + count);
    }

    // ---- spawn-fleet:<faction>:<fleet_points> ---------------------------------------------

    private static void applySpawnFleet(String setup) {
        String body = setup.substring("spawn-fleet:".length());
        int colon = body.indexOf(':');
        if (colon < 0) {
            ProbeLog.emit("setup", ProbeLog.STATUS_FAIL, setup, "Missing ':' in spawn-fleet setup");
            return;
        }
        String factionId = body.substring(0, colon);
        float targetFp = Float.parseFloat(body.substring(colon + 1).trim());
        FactionAPI faction = Global.getSector().getFaction(factionId);
        if (faction == null) {
            ProbeLog.emit("setup", ProbeLog.STATUS_FAIL, setup, "Unknown faction: " + factionId);
            return;
        }
        CampaignFleetAPI player = Global.getSector().getPlayerFleet();
        if (player == null) {
            ProbeLog.emit("setup", ProbeLog.STATUS_FAIL, setup, "No player fleet");
            return;
        }
        LocationAPI location = player.getContainingLocation();
        if (location == null) {
            ProbeLog.emit("setup", ProbeLog.STATUS_FAIL, setup, "Player fleet has no containing location");
            return;
        }

        // Public API has no FleetFactoryV3/FleetParamsV3 (both class-not-found via javap on this
        // build's starfarer.api.jar) -- FactionAPI.pickShipAndAddToFleet(role, params, fleet) is the
        // public substitute: it fills an (initially empty, per FactoryAPI.createEmptyFleet) fleet
        // toward a role's ship pool, returning the FP each pick added. Looped (capped) toward the
        // requested budget rather than trusting a single call to hit it exactly.
        CampaignFleetAPI fleet = Global.getFactory().createEmptyFleet(faction, true);
        FactionAPI.ShipPickParams params = FactionAPI.ShipPickParams.all();
        // Real role ids (ShipRoles constants in starfarer.api.jar). The first live run asked for a
        // role named "combat", which no faction has, so no fleet ever spawned (PRB-FLEET-01).
        String[] roles = { ShipRoles.COMBAT_SMALL, ShipRoles.COMBAT_MEDIUM, ShipRoles.COMBAT_LARGE, ShipRoles.COMBAT_CAPITAL };
        // Size by the fleet's real fleet points: pickShipAndAddToFleet's return value is not FP (the
        // SK13-1b run asked for 120 FP and got a 40-ship fleet, "actualFP=40") (PRB-FLEET-02).
        int misses = 0;
        for (int i = 0; i < 60 && fleet.getFleetPoints() < targetFp && misses < roles.length * 2; i++) {
            int before = fleet.getFleetData().getMembersListCopy().size();
            faction.pickShipAndAddToFleet(roles[i % roles.length], params, fleet);
            if (fleet.getFleetData().getMembersListCopy().size() <= before) {
                misses++;
            }
        }
        float accumulated = fleet.getFleetPoints();
        if (fleet.getFleetData().getMembersListCopy().isEmpty()) {
            ProbeLog.emit("setup", ProbeLog.STATUS_FAIL, setup,
                    "No ships could be added for faction=" + factionId + " (roles combatSmall/Medium/Large/Capital all empty)");
            return;
        }
        location.addEntity(fleet);
        fleet.setContainingLocation(location);
        org.lwjgl.util.vector.Vector2f playerLoc = player.getLocation();
        fleet.setLocation(playerLoc.x + 500f, playerLoc.y + 500f);
        ProbeLog.emit("setup", ProbeLog.STATUS_OK, setup,
                "faction=" + factionId + " requestedFP=" + targetFp + " actualFP=" + accumulated
                        + " members=" + fleet.getFleetData().getMembersListCopy().size());
    }

    // ---- jump:<star_system_name> ----------------------------------------------------------

    private static void applyJump(String setup) {
        String systemName = setup.substring("jump:".length()).trim();
        CampaignFleetAPI player = Global.getSector().getPlayerFleet();
        if (player == null) {
            ProbeLog.emit("setup", ProbeLog.STATUS_FAIL, setup, "No player fleet");
            return;
        }
        StarSystemAPI target = null;
        for (StarSystemAPI system : Global.getSector().getStarSystems()) {
            if (system.getBaseName().equalsIgnoreCase(systemName)) {
                target = system;
                break;
            }
        }
        if (target == null) {
            ProbeLog.emit("setup", ProbeLog.STATUS_FAIL, setup, "Unknown star system: " + systemName);
            return;
        }
        // No dedicated public "teleport"/jump-point-transition API exists on this build (per
        // REVIVAL_ASSURANCE_PLAN.md P3b-C); this is the public substitute: move the fleet's
        // containing location via LocationAPI.addEntity/removeEntity plus
        // SectorEntityToken.setContainingLocation/setLocation, the same primitives vanilla and mods
        // use to relocate entities between systems.
        LocationAPI current = player.getContainingLocation();
        if (current != null) {
            current.removeEntity(player);
        }
        target.addEntity(player);
        player.setContainingLocation(target);
        SectorEntityToken center = target.getCenter();
        if (center != null) {
            org.lwjgl.util.vector.Vector2f loc = center.getLocation();
            player.setLocation(loc.x + 600f, loc.y + 600f);
        } else {
            player.setLocation(0f, 0f);
        }
        ProbeLog.emit("setup", ProbeLog.STATUS_OK, setup, "system=" + systemName);
    }
}
