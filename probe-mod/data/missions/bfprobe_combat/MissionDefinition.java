package data.missions.bfprobe_combat;

import com.bridgeforge.probe.BfProbeCombatPlugin;
import com.bridgeforge.probe.ProbeConfig;
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

    private static final int DEFAULT_CAP = 12;

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

        float width = 16000f;
        float height = 12000f;
        api.initMap(-width / 2f, width / 2f, -height / 2f, height / 2f);

        api.addPlugin(new BfProbeCombatPlugin(config.combatSeconds));
    }
}
