package com.bridgeforge.probe;

import com.fs.starfarer.api.characters.PersonAPI;
import com.fs.starfarer.api.combat.BaseEveryFrameCombatPlugin;
import com.fs.starfarer.api.combat.CombatEngineAPI;
import com.fs.starfarer.api.combat.ShipAPI;
import com.fs.starfarer.api.input.InputEventAPI;

import java.util.HashSet;
import java.util.List;
import java.util.Set;

/**
 * Combat-side half of the probe (mission {@code bfprobe_combat}): logs
 * deployment and a captain-personality check for every ship, lets AI fight
 * for {@code combat_seconds} (from {@link ProbeConfig}), then ends combat.
 *
 * The mission itself (loose {@code data/missions/bfprobe_combat/
 * MissionDefinition.java}, compiled by the game like any vanilla mission)
 * builds the fleets from the probe config and adds this plugin via
 * {@code MissionDefinitionAPI.addPlugin}.
 */
public class BfProbeCombatPlugin extends BaseEveryFrameCombatPlugin {

    private final float combatSeconds;
    // Ships spawn after init() (the first live run logged START/END and no ships at all), so each
    // ship is logged the first time advance() sees it, which also catches reinforcements.
    private final Set<ShipAPI> loggedShips = new HashSet<ShipAPI>();
    private boolean ended = false;

    public BfProbeCombatPlugin(float combatSeconds) {
        this.combatSeconds = combatSeconds;
    }

    @Override
    public void init(CombatEngineAPI engine) {
        ProbeLog.start("combat");
    }

    private void logNewShips(CombatEngineAPI engine) {
        for (ShipAPI ship : engine.getShips()) {
            // 0.2.24: wreck fragments are hulks from birth; logging each one wrote thousands of lines when SEEKER's Bone-Breaker
            // re-ran its death effect every frame (RC8-27), so only ships first seen alive are logged.
            if (ship == null || ship.isFighter() || ship.isHulk() || !loggedShips.add(ship)) {
                continue;
            }
            String hullId = ship.getHullSpec() != null ? ship.getHullSpec().getHullId() : "?";
            ProbeExercised.combatShip(ship.getHullSpec());
            ProbeLog.emit("combat-deployment", ProbeLog.STATUS_INFO, ship.getName(),
                    "hull=" + hullId + " owner=" + ship.getOwner());
            PersonAPI captain = ship.getCaptain();
            if (captain != null && captain.getPersonalityAPI() == null) {
                ProbeLog.emit("combat-captain-personality", ProbeLog.STATUS_WARN, ship.getName(),
                        "hull=" + hullId + " captain has a null personality (SK-13 class)");
            }
        }
    }

    // 0.2.23: how many drones and fighter wings each ship had out at once. The Yellowjackets live run (2026-10-11) had only the
    // owner's word that the Colony's drones launched; the log had no record of it. ShipAPI.getDeployedDrones() and
    // getAllWings() checked with javap on RC8's starfarer.api.jar, 2026-10-11.
    private final java.util.Map<ShipAPI, int[]> launches = new java.util.LinkedHashMap<ShipAPI, int[]>();

    private void trackLaunches() {
        try {
            for (ShipAPI ship : loggedShips) {
                if (ship == null) {
                    continue;
                }
                List<ShipAPI> drones = ship.getDeployedDrones();
                List<?> wings = ship.getAllWings();
                int[] seen = launches.get(ship);
                if (seen == null) {
                    seen = new int[2];
                    launches.put(ship, seen);
                }
                seen[0] = Math.max(seen[0], drones == null ? 0 : drones.size());
                seen[1] = Math.max(seen[1], wings == null ? 0 : wings.size());
            }
        } catch (Throwable t) {
            // the probe never stops combat over a launch count
        }
    }

    private void reportLaunches() {
        boolean any = false;
        for (java.util.Map.Entry<ShipAPI, int[]> entry : launches.entrySet()) {
            int[] seen = entry.getValue();
            if (seen[0] + seen[1] > 0) {
                any = true;
                ShipAPI ship = entry.getKey();
                String hullId = ship.getHullSpec() != null ? ship.getHullSpec().getHullId() : "?";
                ProbeLog.emit("combat-launch", ProbeLog.STATUS_INFO, hullId,
                        "most drones out at once=" + seen[0] + " most fighter wings out at once=" + seen[1] + " owner=" + ship.getOwner());
            }
        }
        if (!any) {
            ProbeLog.emit("combat-launch", ProbeLog.STATUS_INFO, "none", "no ship had a drone or fighter wing out");
        }
    }

    // 0.2.24: the duel meter (probe-group duel) in every probe combat. A runaway field (2,388 wreck hulks and 8 s frames after one
    // SEEKER Bone-Breaker kill, RC8-27) was only seen by a person watching; now the log says so and the combat is ended early.
    static final int RUNAWAY_HULKS = 400;
    static final double RUNAWAY_FRAME_MS = 2000.0;
    private long lastNanos = 0L;
    private double worstFrameMs = 0;
    private double sumFrameMs = 0;
    private int frames = 0;
    private int peakHulks = 0;
    private int peakShips = 0;
    private boolean runaway = false;

    private void meter(CombatEngineAPI engine) {
        long now = System.nanoTime();
        if (lastNanos != 0L) {
            double ms = (now - lastNanos) / 1000000.0;
            frames++;
            sumFrameMs += ms;
            worstFrameMs = Math.max(worstFrameMs, ms);
        }
        lastNanos = now;
        int hulks = 0;
        List<ShipAPI> ships = engine.getShips();
        for (int i = 0; i < ships.size(); i++) {
            if (ships.get(i).isHulk()) {
                hulks++;
            }
        }
        peakHulks = Math.max(peakHulks, hulks);
        peakShips = Math.max(peakShips, ships.size());
        if (!runaway && (hulks >= RUNAWAY_HULKS || worstFrameMs >= RUNAWAY_FRAME_MS)) {
            runaway = true;
            ProbeLog.emit("combat-perf", ProbeLog.STATUS_FAIL, "runaway",
                    "hulks=" + hulks + " ships=" + ships.size() + " worstFrameMs=" + Math.round(worstFrameMs)
                            + " at t=" + Math.round(engine.getTotalElapsedTime(false)) + "s; a hull mod may repeat a death effect on its wreck (RC8-27)");
        }
    }

    @Override
    public void advance(float amount, List<InputEventAPI> events) {
        if (ended) {
            return;
        }
        com.fs.starfarer.api.combat.CombatEngineAPI engine = com.fs.starfarer.api.Global.getCombatEngine();
        if (engine == null || engine.isPaused()) {
            lastNanos = 0L; // a pause is not a slow frame
            return;
        }
        meter(engine);
        logNewShips(engine);
        trackLaunches();
        if (engine.getTotalElapsedTime(false) >= combatSeconds || runaway) {
            ended = true;
            ProbeLog.emit("combat-perf", runaway ? ProbeLog.STATUS_WARN : ProbeLog.STATUS_INFO, "combat",
                    "frames=" + frames + " avgFrameMs=" + (frames == 0 ? 0 : Math.round(sumFrameMs / frames * 10) / 10.0)
                            + " worstFrameMs=" + Math.round(worstFrameMs) + " peakHulks=" + peakHulks + " peakShips=" + peakShips);
            reportLaunches();
            ProbeLog.emit("combat-summary", ProbeLog.STATUS_INFO, "combat", "ships logged=" + loggedShips.size());
            ProbeLog.end("combat");
            ProbeDone.combatEnded();
            engine.endCombat(0f);
        }
    }
}
