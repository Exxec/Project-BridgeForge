package data.missions.bfprobe_combat;

import com.bridgeforge.probe.BfProbeCombatPlugin;
import com.bridgeforge.probe.ProbeConfig;
import com.bridgeforge.probe.ProbeFiles;
import com.bridgeforge.probe.ProbeLog;
import com.fs.starfarer.api.fleet.FleetGoal;
import com.fs.starfarer.api.fleet.FleetMemberType;
import com.fs.starfarer.api.mission.FleetSide;
import com.fs.starfarer.api.mission.MissionDefinitionAPI;
import com.fs.starfarer.api.mission.MissionDefinitionPlugin;

import java.util.Iterator;
import java.util.Map;

/**
 * Combat probe mission (roadmap P3). Loose source compiled by the game at
 * runtime, exactly like vanilla missions (see starsector-core's
 * data/missions/hornetsnest/MissionDefinition.java) -- the plan explicitly
 * allows this instead of a compiled class inside the mod jar. It only calls
 * public MissionDefinitionAPI methods; classes from our own mod jar
 * (com.bridgeforge.probe.*) are on the mod's own classpath like any other
 * mod script.
 *
 * Puts the target mod's ships (from {@link ProbeConfig}, written by
 * BridgeForge before this mission is launched) on BOTH sides, alternating
 * hulls so neither side is a pure mirror, up to a cap per side.
 */
public class MissionDefinition implements MissionDefinitionPlugin {

    private static final int DEFAULT_CAP = 30; // owner 2026-10-05 (was 12), matches probe_config

    public void defineMission(MissionDefinitionAPI api) {
        ProbeConfig config;
        try {
            config = ProbeConfig.load();
        } catch (Exception e) {
            ProbeLog.emit("combat-config", ProbeLog.STATUS_FAIL, "bf_probe_config",
                    "Could not load: " + e);
            config = new ProbeConfig();
        }

        int cap = config.combatCapPerSide > 0 ? config.combatCapPerSide : DEFAULT_CAP;

        // Faction ids are cosmetic here (fleet-panel rendering only); "hegemony"/"pirates"
        // are always-present vanilla factions, used so this never depends on the target
        // mod defining its own faction.
        api.initFleet(FleetSide.PLAYER, "hegemony", FleetGoal.ATTACK, true, 1);
        api.initFleet(FleetSide.ENEMY, "pirates", FleetGoal.ATTACK, true, 1);
        api.setFleetTagline(FleetSide.PLAYER, "BridgeForge probe side A");
        api.setFleetTagline(FleetSide.ENEMY, "BridgeForge probe side B");
        api.addBriefingItem("BridgeForge combat probe (rig only): AI-controlled, ends automatically");

        // 0.2.13 (owner request 2026-10-05): every hull fights. With 12 per side most hulls were skipped (group 1: 30
        // fought, 86 skipped); now each start of the mission fights the next slice of 2 x cap hulls, wrapping round,
        // so restarting the mission covers the whole group. The round counter lives in a common file.
        int total = config.variantByHull.size();
        int perRound = 2 * cap;
        int rounds = total == 0 ? 1 : (total + perRound - 1) / perRound;
        int round = ProbeFiles.nextCombatRound() % rounds;
        int sliceStart = round * perRound;
        int sliceEnd = Math.min(total, sliceStart + perRound);
        ProbeLog.emit("combat-round", ProbeLog.STATUS_INFO, "round " + (round + 1) + " of " + rounds,
                "hulls " + (sliceStart + 1) + "-" + sliceEnd + " of " + total + (rounds > 1 ? "; restart the mission for the next round" : ""));
        int position = 0;
        int index = 0;
        int deployedA = 0;
        int deployedB = 0;
        // The game compiles this loose file with Janino, which ignores generics: a for-each over
        // Map.Entry<String, String> reads as Object -> String and fails to compile (live bug
        // PRB-MISSION-02). Use a raw iterator with explicit casts, like vanilla loose scripts.
        Iterator it = config.variantByHull.entrySet().iterator();
        while (it.hasNext()) {
            Map.Entry entry = (Map.Entry) it.next();
            String hullId = (String) entry.getKey();
            String variantId = (String) entry.getValue();
            if (position < sliceStart || position >= sliceEnd) {
                position++;
                continue; // another round's slice
            }
            position++;
            FleetSide side = (index % 2 == 0) ? FleetSide.PLAYER : FleetSide.ENEMY;
            boolean sideFull = side == FleetSide.PLAYER ? deployedA >= cap : deployedB >= cap;
            if (sideFull) {
                ProbeLog.emit("combat-deploy-skip", ProbeLog.STATUS_WARN, hullId,
                        "side " + side + " already at cap " + cap);
                index++;
                continue;
            }
            try {
                api.addToFleet(side, variantId, FleetMemberType.SHIP, hullId, false);
                if (side == FleetSide.PLAYER) {
                    deployedA++;
                } else {
                    deployedB++;
                }
            } catch (Throwable t) {
                ProbeLog.emit("combat-deploy-skip", ProbeLog.STATUS_FAIL, hullId,
                        "addToFleet threw " + t.getClass().getName() + ": " + t.getMessage());
            }
            index++;
        }

        // An empty side means no fight: GRP-5 had one mod ship and no opponent, GRP-3 and sprite-only mods none
        // at all (2026-09-27). Fill an empty side with a small vanilla fleet so the combat plugin always sees a
        // battle; sized to the other side, 2 to 4 ships. Idea from Legacy of Arkgneisis's own test missions
        // (ROADMAP item 29.1). Variant ids checked in RC8 data/variants (2026-09-27).
        if (deployedA == 0) {
            fillSide(api, FleetSide.PLAYER, fillerCount(deployedB));
        }
        if (deployedB == 0) {
            fillSide(api, FleetSide.ENEMY, fillerCount(deployedA));
        }

        float width = 16000f;
        float height = 12000f;
        api.initMap(-width / 2f, width / 2f, -height / 2f, height / 2f);

        api.addPlugin(new BfProbeCombatPlugin(config.combatSeconds));
    }

    private static final String[] FILLER_VARIANTS = {
            "hammerhead_Balanced", "enforcer_Assault", "lasher_CS", "wolf_CS", "sunder_CS", "eagle_Assault"
    };

    private static int fillerCount(int otherSide) {
        return Math.max(2, Math.min(4, otherSide));
    }

    private static void fillSide(MissionDefinitionAPI api, FleetSide side, int count) {
        int added = 0;
        for (int i = 0; i < count; i++) {
            String variantId = FILLER_VARIANTS[i % FILLER_VARIANTS.length];
            try {
                api.addToFleet(side, variantId, FleetMemberType.SHIP, "BF filler " + (i + 1), false);
                added++;
            } catch (Throwable t) {
                ProbeLog.emit("combat-filler", ProbeLog.STATUS_WARN, variantId,
                        "addToFleet threw " + t.getClass().getName() + ": " + t.getMessage());
            }
        }
        ProbeLog.emit("combat-filler", ProbeLog.STATUS_INFO, String.valueOf(side),
                added + " vanilla ship(s) added: the target mod had none for this side");
    }
}
