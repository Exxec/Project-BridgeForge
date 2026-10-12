package data.missions.bfduel_overwhelm;

import com.fs.starfarer.api.fleet.FleetGoal;
import com.fs.starfarer.api.fleet.FleetMemberType;
import com.fs.starfarer.api.mission.FleetSide;
import com.fs.starfarer.api.mission.MissionDefinitionAPI;
import com.fs.starfarer.api.mission.MissionDefinitionPlugin;

import data.scripts.bfduel.BfDuelPlugin;

/** SEEKER's Bone-Breaker overwhelmed by a vanilla fleet, so it is destroyed early (a huge hit finishes it at 45 s if the fleet has not): times the fight and the cost of its fragments. Rig only. */
public class MissionDefinition implements MissionDefinitionPlugin {

    public void defineMission(MissionDefinitionAPI api) {
        api.initFleet(FleetSide.PLAYER, "hegemony", FleetGoal.ATTACK, true, 1);
        api.initFleet(FleetSide.ENEMY, "pirates", FleetGoal.ATTACK, true, 1);
        api.setFleetTagline(FleetSide.PLAYER, "Bone-Breaker");
        api.setFleetTagline(FleetSide.ENEMY, "Overwhelming fleet");
        api.addBriefingItem("BridgeForge duel: AI-controlled, ends by itself; the frame period is logged as BF-DUEL lines");
        api.addToFleet(FleetSide.PLAYER, "ART_shockwave_shockwave", FleetMemberType.SHIP, "Bone-Breaker", false);
        api.addToFleet(FleetSide.ENEMY, "onslaught_Standard", FleetMemberType.SHIP, "Overwhelm 1", false);
        api.addToFleet(FleetSide.ENEMY, "onslaught_Standard", FleetMemberType.SHIP, "Overwhelm 2", false);
        api.addToFleet(FleetSide.ENEMY, "conquest_Standard", FleetMemberType.SHIP, "Overwhelm 3", false);
        api.addToFleet(FleetSide.ENEMY, "conquest_Standard", FleetMemberType.SHIP, "Overwhelm 4", false);
        api.initMap(-4000f, 4000f, -3000f, 3000f);
        api.addPlugin(new BfDuelPlugin("overwhelm", 45f));
    }
}
