package data.scripts.bfcap;

import java.util.ArrayList;
import java.util.List;

import com.fs.starfarer.api.EveryFrameScript;
import com.fs.starfarer.api.Global;
import com.fs.starfarer.api.campaign.CampaignFleetAPI;
import com.fs.starfarer.api.campaign.CargoAPI;
import com.fs.starfarer.api.fleet.FleetLogisticsAPI;
import com.fs.starfarer.api.fleet.FleetMemberAPI;
import com.fs.starfarer.api.fleet.FleetMemberType;

/**
 * Walks three player fleets through cargo, fuel and crew at 0, 0.5, 1, 1.5 and 2 times capacity (the other two at half) and logs the
 * fleet's speed, burn level and daily supplies after each change as BF-CAP lines. One state per STATE_FRAMES frames so the game's own
 * per-frame fleet update has run. Ends with a save taken in the same frame as a capacity change, to see whether the saved capacity is
 * what the game held then or is worked out later.
 */
public class BfCapScript implements EveryFrameScript {

    static final String[][] FLEETS = {
        {"A-freighter", "tarsus_Standard"},
        {"B-warships", "hammerhead_Balanced", "hammerhead_Balanced", "buffalo_Standard"},
        {"C-mixed", "atlas_Standard", "onslaught_Standard", "colossus_Standard"},
    };
    static final String[] RESOURCES = {"cargo", "fuel", "crew"};
    static final float[] LEVELS = {0f, 0.5f, 1f, 1.1f, 1.25f, 1.5f, 1.75f, 2f};
    /** After the one-at-a-time walk: cargo / fuel / crew together, to see how penalties combine. */
    static final float[][] COMBOS = {{1.5f, 1.5f, 0.5f}, {1.25f, 1.5f, 0.5f}, {1.5f, 1.5f, 1.5f}, {0.5f, 1.25f, 1.75f}};
    static final int STATE_FRAMES = 10;
    static final int WARMUP_FRAMES = 120;
    static final String FILLER = "organics";

    private int frames = 0;
    private int stage = 0;          // 0 warm-up, 1 walking the plan, 2 save test, 3 done
    private int fleetIndex = 0;
    private int resourceIndex = -1; // -1: the fleet was just built
    private int levelIndex = 0;
    private int waited = 0;
    private boolean done = false;

    public boolean isDone() {
        return done;
    }

    public boolean runWhilePaused() {
        return true;
    }

    public void advance(float amount) {
        if (done) {
            return;
        }
        CampaignFleetAPI fleet = Global.getSector().getPlayerFleet();
        if (fleet == null) {
            return;
        }
        frames++;
        if (stage == 0) {
            if (frames >= WARMUP_FRAMES) {
                log("START|paused=" + Global.getSector().isPaused() + "|frames=" + frames + "|fleetMembers=" + fleet.getFleetData().getNumMembers());
                stage = 1;
                buildFleet(fleet, fleetIndex);
                waited = 0;
            }
            return;
        }
        if (stage == 1) {
            waited++;
            if (waited < STATE_FRAMES) {
                return;
            }
            waited = 0;
            if (resourceIndex < 0) {
                logState(fleet, FLEETS[fleetIndex][0], "built", 0f);
            } else if (resourceIndex < RESOURCES.length) {
                logState(fleet, FLEETS[fleetIndex][0], RESOURCES[resourceIndex], LEVELS[levelIndex]);
            } else {
                float[] combo = COMBOS[levelIndex];
                logState(fleet, FLEETS[fleetIndex][0], "combo", combo[0] * 10000f + combo[1] * 100f + combo[2]);
            }
            // next state
            int count = resourceIndex < RESOURCES.length ? LEVELS.length : COMBOS.length;
            if (resourceIndex < 0) {
                resourceIndex = 0;
                levelIndex = 0;
            } else {
                levelIndex++;
                if (levelIndex >= count) {
                    levelIndex = 0;
                    resourceIndex++;
                }
            }
            if (resourceIndex > RESOURCES.length) {
                fleetIndex++;
                resourceIndex = -1;
                if (fleetIndex >= FLEETS.length) {
                    stage = 2;
                    return;
                }
                buildFleet(fleet, fleetIndex);
                return;
            }
            applyLevel(fleet, resourceIndex < RESOURCES.length ? RESOURCES[resourceIndex] : "combo", resourceIndex < RESOURCES.length ? LEVELS[levelIndex] : 0f);
            return;
        }
        if (stage == 2) {
            saveTest(fleet);
            stage = 3;
            return;
        }
        log("END|frames=" + frames);
        Global.getSector().getMemoryWithoutUpdate().set(BfCapPlugin.DONE_KEY, true);
        done = true;
    }

    /** The fleet becomes exactly these ships, with cargo, fuel and crew at half of the new capacity once it has settled. */
    private void buildFleet(CampaignFleetAPI fleet, int index) {
        List old = new ArrayList(fleet.getFleetData().getMembersListCopy());
        for (int i = 0; i < old.size(); i++) {
            fleet.getFleetData().removeFleetMember((FleetMemberAPI) old.get(i));
        }
        String[] spec = FLEETS[index];
        for (int i = 1; i < spec.length; i++) {
            FleetMemberAPI member = Global.getFactory().createFleetMember(FleetMemberType.SHIP, spec[i]);
            member.getRepairTracker().setCR(0.7f);
            fleet.getFleetData().addFleetMember(member);
        }
        fleet.getFleetData().sort();
        fleet.getFleetData().syncMemberLists();
        CargoAPI cargo = fleet.getCargo();
        cargo.clear();
        cargo.updateSpaceUsed();
        applyAll(fleet, 0.5f, 0.5f, 0.5f);
    }

    private void applyAll(CampaignFleetAPI fleet, float cargoLevel, float fuelLevel, float crewLevel) {
        CargoAPI cargo = fleet.getCargo();
        setCargo(cargo, cargoLevel);
        setFuel(cargo, fuelLevel);
        setCrew(cargo, crewLevel);
        cargo.updateSpaceUsed();
    }

    private void applyLevel(CampaignFleetAPI fleet, String resource, float level) {
        float cargoLevel = 0.5f;
        float fuelLevel = 0.5f;
        float crewLevel = 0.5f;
        if ("combo".equals(resource)) {
            float[] combo = COMBOS[levelIndex];
            cargoLevel = combo[0];
            fuelLevel = combo[1];
            crewLevel = combo[2];
        } else if ("cargo".equals(resource)) {
            cargoLevel = level;
        } else if ("fuel".equals(resource)) {
            fuelLevel = level;
        } else {
            crewLevel = level;
        }
        applyAll(fleet, cargoLevel, fuelLevel, crewLevel);
    }

    private void setCargo(CargoAPI cargo, float level) {
        cargo.removeCommodity("supplies", cargo.getCommodityQuantity("supplies"));
        cargo.removeCommodity(FILLER, cargo.getCommodityQuantity(FILLER));
        cargo.updateSpaceUsed();
        float amount = Math.round(cargo.getMaxCapacity() * level);
        if (amount > 0f) {
            cargo.addCommodity(FILLER, amount);
        }
    }

    private void setFuel(CargoAPI cargo, float level) {
        float target = Math.round(cargo.getMaxFuel() * level);
        float delta = target - cargo.getFuel();
        if (delta > 0f) {
            cargo.addFuel(delta);
        } else if (delta < 0f) {
            cargo.removeFuel(-delta);
        }
    }

    private void setCrew(CargoAPI cargo, float level) {
        int target = Math.round(cargo.getMaxPersonnel() * level);
        int delta = target - cargo.getCrew();
        if (delta > 0) {
            cargo.addCrew(delta);
        } else if (delta < 0) {
            cargo.removeCrew(-delta);
        }
        cargo.removeMarines(cargo.getMarines());
    }

    private void logState(CampaignFleetAPI fleet, String fleetName, String resource, float level) {
        CargoAPI cargo = fleet.getCargo();
        FleetLogisticsAPI logistics = fleet.getLogistics();
        log(fleetName + "|" + resource + "=" + level
            + "|ships=" + fleet.getFleetData().getNumMembers()
            + "|maxCargo=" + cargo.getMaxCapacity() + "|spaceUsed=" + cargo.getSpaceUsed()
            + "|fuel=" + cargo.getFuel() + "|maxFuel=" + cargo.getMaxFuel()
            + "|crew=" + cargo.getCrew() + "|marines=" + cargo.getMarines() + "|maxPersonnel=" + cargo.getMaxPersonnel()
            + "|travelSpeed=" + fleet.getTravelSpeed() + "|burn=" + fleet.getCurrBurnLevel()
            + "|suppliesPerDay=" + logistics.getTotalSuppliesPerDay()
            + "|excessCargoCost=" + logistics.getExcessCargoCapacitySupplyCost()
            + "|excessFuelCost=" + logistics.getExcessFuelCapacitySupplyCost()
            + "|excessPersonnelCost=" + logistics.getExcessPersonnelCapacitySupplyCost()
            + "|crewSup=" + logistics.getCrewSuppliesPerDay() + "|personnelSup=" + logistics.getPersonnelSuppliesPerDay()
            + "|maintenance=" + logistics.getShipMaintenanceSupplyCost()
            + "|repair=" + logistics.getTotalRepairAndRecoverySupplyCost()
            + "|excessShips=" + logistics.getExcessShipsSupplyCost()
            + "|fuelPerLY=" + logistics.getFuelCostPerLightYear()
            + "|paused=" + Global.getSector().isPaused());
    }

    /** Fleet C at 2x cargo, then one more ship in the same frame as the save: what capacity does the save hold? */
    private void saveTest(CampaignFleetAPI fleet) {
        CargoAPI cargo = fleet.getCargo();
        applyAll(fleet, 2f, 0.5f, 0.5f);
        float beforeMax = cargo.getMaxCapacity();
        float beforeUsed = cargo.getSpaceUsed();
        FleetMemberAPI extra = Global.getFactory().createFleetMember(FleetMemberType.SHIP, "atlas_Standard");
        fleet.getFleetData().addFleetMember(extra);
        float liveMax = cargo.getMaxCapacity();
        float liveUsed = cargo.getSpaceUsed();
        boolean saved = Global.getSector().getCampaignUI().cmdSave();
        float afterMax = cargo.getMaxCapacity();
        log("SAVE|beforeMaxCargo=" + beforeMax + "|beforeSpaceUsed=" + beforeUsed
            + "|liveMaxCargoAtSave=" + liveMax + "|liveSpaceUsedAtSave=" + liveUsed
            + "|cmdSave=" + saved + "|afterMaxCargo=" + afterMax + "|ships=" + fleet.getFleetData().getNumMembers());
    }

    private void log(String line) {
        Global.getLogger(BfCapScript.class).info("BF-CAP|" + line);
    }
}
