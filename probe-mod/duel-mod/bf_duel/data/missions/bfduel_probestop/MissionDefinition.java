package data.missions.bfduel_probestop;

import com.bridgeforge.probe.BfProbeCombatPlugin;
import com.fs.starfarer.api.fleet.FleetGoal;
import com.fs.starfarer.api.fleet.FleetMemberType;
import com.fs.starfarer.api.mission.FleetSide;
import com.fs.starfarer.api.mission.MissionDefinitionAPI;
import com.fs.starfarer.api.mission.MissionDefinitionPlugin;

import data.scripts.bfduel.BfDuelPlugin;

/** The overwhelm duel with the probe's own combat plugin attached: proves that the probe's runaway stop (400 hulks or a 2 s frame) fires and ends the combat when a hull mod repeats a death effect on its wreck. Needs the probe mod enabled. Rig only. */
public class MissionDefinition implements MissionDefinitionPlugin {

    public void defineMission(MissionDefinitionAPI api) {
        api.initFleet(FleetSide.PLAYER, "hegemony", FleetGoal.ATTACK, true, 1);
        api.initFleet(FleetSide.ENEMY, "pirates", FleetGoal.ATTACK, true, 1);
        api.setFleetTagline(FleetSide.PLAYER, "Bone-Breaker");
        api.setFleetTagline(FleetSide.ENEMY, "Overwhelming fleet");
        api.addBriefingItem("BridgeForge duel: AI-controlled, ends by itself; the probe's runaway stop is attached");
        api.addToFleet(FleetSide.PLAYER, "ART_shockwave_shockwave", FleetMemberType.SHIP, "Bone-Breaker", false);
        api.addToFleet(FleetSide.ENEMY, "onslaught_Standard", FleetMemberType.SHIP, "Overwhelm 1", false);
        api.addToFleet(FleetSide.ENEMY, "onslaught_Standard", FleetMemberType.SHIP, "Overwhelm 2", false);
        api.addToFleet(FleetSide.ENEMY, "conquest_Standard", FleetMemberType.SHIP, "Overwhelm 3", false);
        api.addToFleet(FleetSide.ENEMY, "conquest_Standard", FleetMemberType.SHIP, "Overwhelm 4", false);
        api.initMap(-4000f, 4000f, -3000f, 3000f);
        api.addPlugin(new BfDuelPlugin("probestop", 45f));
        api.addPlugin(new BfProbeCombatPlugin(240f));
    }
}
