package data.missions.bfduel_seeker;

import com.fs.starfarer.api.fleet.FleetGoal;
import com.fs.starfarer.api.fleet.FleetMemberType;
import com.fs.starfarer.api.mission.FleetSide;
import com.fs.starfarer.api.mission.MissionDefinitionAPI;
import com.fs.starfarer.api.mission.MissionDefinitionPlugin;

import data.scripts.bfduel.BfDuelPlugin;

/** SEEKER's Bone-Breaker (ART_shockwave, the glass sphere that fragments) against Betelgeuse (ART_dimention). Rig only. */
public class MissionDefinition implements MissionDefinitionPlugin {

    public void defineMission(MissionDefinitionAPI api) {
        api.initFleet(FleetSide.PLAYER, "hegemony", FleetGoal.ATTACK, true, 1);
        api.initFleet(FleetSide.ENEMY, "pirates", FleetGoal.ATTACK, true, 1);
        api.setFleetTagline(FleetSide.PLAYER, "Bone-Breaker");
        api.setFleetTagline(FleetSide.ENEMY, "Betelgeuse");
        api.addBriefingItem("BridgeForge duel: AI-controlled, ends by itself; the frame period is logged as BF-DUEL lines");
        api.addToFleet(FleetSide.PLAYER, "ART_shockwave_shockwave", FleetMemberType.SHIP, "Bone-Breaker", false);
        api.addToFleet(FleetSide.ENEMY, "ART_dimention_manipulator", FleetMemberType.SHIP, "Betelgeuse", false);
        api.initMap(-4000f, 4000f, -3000f, 3000f);
        api.addPlugin(new BfDuelPlugin("seeker"));
    }
}
