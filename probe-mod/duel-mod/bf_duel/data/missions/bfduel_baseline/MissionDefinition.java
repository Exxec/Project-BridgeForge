package data.missions.bfduel_baseline;

import com.fs.starfarer.api.fleet.FleetGoal;
import com.fs.starfarer.api.fleet.FleetMemberType;
import com.fs.starfarer.api.mission.FleetSide;
import com.fs.starfarer.api.mission.MissionDefinitionAPI;
import com.fs.starfarer.api.mission.MissionDefinitionPlugin;

import data.scripts.bfduel.BfDuelPlugin;

/** Baseline: two vanilla Onslaughts, to compare the frame cost of an ordinary destruction. Rig only. */
public class MissionDefinition implements MissionDefinitionPlugin {

    public void defineMission(MissionDefinitionAPI api) {
        api.initFleet(FleetSide.PLAYER, "hegemony", FleetGoal.ATTACK, true, 1);
        api.initFleet(FleetSide.ENEMY, "pirates", FleetGoal.ATTACK, true, 1);
        api.setFleetTagline(FleetSide.PLAYER, "Onslaught A");
        api.setFleetTagline(FleetSide.ENEMY, "Onslaught B");
        api.addBriefingItem("BridgeForge duel: AI-controlled, ends by itself; the frame period is logged as BF-DUEL lines");
        api.addToFleet(FleetSide.PLAYER, "onslaught_Standard", FleetMemberType.SHIP, "Onslaught A", false);
        api.addToFleet(FleetSide.ENEMY, "onslaught_Standard", FleetMemberType.SHIP, "Onslaught B", false);
        api.initMap(-4000f, 4000f, -3000f, 3000f);
        api.addPlugin(new BfDuelPlugin("baseline"));
    }
}
