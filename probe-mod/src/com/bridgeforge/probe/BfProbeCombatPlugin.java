package com.bridgeforge.probe;

import com.fs.starfarer.api.characters.PersonAPI;
import com.fs.starfarer.api.combat.BaseEveryFrameCombatPlugin;
import com.fs.starfarer.api.combat.CombatEngineAPI;
import com.fs.starfarer.api.combat.ShipAPI;
import com.fs.starfarer.api.fleet.FleetMemberAPI;
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
        raiseDeploymentLimits(engine, "init");
    }

    // 0.3.5 (ROADMAP-3 93.67): every planned hull must fight, but a battle deploys only up to each side's deployment limit and
    // the rest wait in reserve. P034-BULTACH-20261122 put 60 hulls in a round and 34 deployed, all in the first 1.6 s; the
    // battle ended at combatSeconds with ships still in reserve. So each side's limit is raised past any fleet the probe builds,
    // through CombatFleetManagerAPI.modifyFlatMax(String, int) (javap of RC7's starfarer.api.jar 2026-11-22): at init, before
    // the opening deployment, and again when both sides are first seen. Each raise is logged with the side's strength and
    // reserves, so the next live run shows which one brought the reserves in.
    private static final String LIMIT_SOURCE = "bf_probe_deploy_all";
    private static final int LIMIT_BONUS = 100000;
    private boolean limitsRaisedInBattle = false;

    // Review of 0.3.5: an exception escaping a combat plugin is a Fatal dialog (SK13-1), and one in finish() would leave the
    // battle running with no END, so both helpers catch everything and log it, as trackLaunches does.
    private static void raiseDeploymentLimits(CombatEngineAPI engine, String when) {
        for (int owner = 0; owner <= 1; owner++) {
            try {
                com.fs.starfarer.api.combat.CombatFleetManagerAPI manager = engine == null ? null : engine.getFleetManager(owner);
                if (manager == null) {
                    ProbeLog.emit("combat-deploy-limit", ProbeLog.STATUS_WARN, "owner=" + owner, "at " + when + ": no fleet manager");
                    continue;
                }
                int before = manager.getMaxStrength();
                manager.modifyFlatMax(LIMIT_SOURCE, LIMIT_BONUS);  // keyed by source: a second call replaces the first
                List<FleetMemberAPI> reserves = manager.getReservesCopy();
                ProbeLog.emit("combat-deploy-limit", ProbeLog.STATUS_INFO, "owner=" + owner,
                        "at " + when + ": max " + before + " -> " + manager.getMaxStrength() + " curr=" + manager.getCurrStrength()
                                + " reserves=" + (reserves == null ? 0 : reserves.size()));
            } catch (Throwable t) {
                ProbeLog.emit("combat-deploy-limit", ProbeLog.STATUS_WARN, "owner=" + owner,
                        "at " + when + ": " + t.getClass().getName() + ": " + t.getMessage());
            }
        }
    }

    /** Each side's reserves when the battle ends, by hull id: planned hulls that never deployed (93.67). */
    private static void reportReserves(CombatEngineAPI engine) {
        for (int owner = 0; owner <= 1; owner++) {
            try {
                com.fs.starfarer.api.combat.CombatFleetManagerAPI manager = engine.getFleetManager(owner);
                List<FleetMemberAPI> reserves = manager == null ? null : manager.getReservesCopy();
                StringBuilder hulls = new StringBuilder();
                if (reserves != null) {
                    for (FleetMemberAPI member : reserves) {
                        hulls.append(hulls.length() == 0 ? "" : ",").append(member == null ? "?" : member.getHullId());
                    }
                }
                ProbeLog.emit("combat-reserves", hulls.length() == 0 ? ProbeLog.STATUS_INFO : ProbeLog.STATUS_WARN, "owner=" + owner,
                        hulls.length() == 0 ? "none left" : "never deployed: " + hulls);
            } catch (Throwable t) {
                ProbeLog.emit("combat-reserves", ProbeLog.STATUS_WARN, "owner=" + owner, t.getClass().getName() + ": " + t.getMessage());
            }
        }
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

    // 0.3.4 (ROADMAP-3 96.13): when one side has no ships left, or the engine says combat is over (CombatEngineAPI.isCombatOver(),
    // javap of RC7's starfarer.api.jar 2026-11-22), the END lines are written at once: P962SA2-LIVE-0985a-20261119's one frigate
    // won early, the game closed the battle and the probe wrote none of them. Every battle still ends at combatSeconds of
    // running combat (93.49's stall was the harness's short wait, fixed by 93.62, not a battle that could not end).

    /** "player=a,b enemy=c": the hull ids still alive per side (owner 0 is the player's side, 1 the enemy's). */
    private static String aliveBySide(CombatEngineAPI engine, int[] counts) {
        StringBuilder player = new StringBuilder();
        StringBuilder enemy = new StringBuilder();
        for (ShipAPI ship : engine.getShips()) {
            if (ship == null || ship.isFighter() || ship.isHulk() || ship.getHullSpec() == null) {
                continue;
            }
            int owner = ship.getOwner();
            if (owner == 0 || owner == 1) {
                StringBuilder side = owner == 0 ? player : enemy;
                side.append(side.length() == 0 ? "" : ",").append(ship.getHullSpec().getHullId());
                counts[owner]++;
            }
        }
        return "player=" + (player.length() == 0 ? "none" : player) + " enemy=" + (enemy.length() == 0 ? "none" : enemy);
    }

    // Review of 0.3.4: ships appear one per frame (SR6-LIVE-0985a-20261117 logged them about 20 ms apart, owner 0 first), so on
    // the first frame with a ship the other side has none. A side counts as wiped only once BOTH sides have had a live ship, and
    // only when that side has nothing left in reserve (CombatFleetManagerAPI.getReservesCopy(), javap of RC7 2026-11-22):
    // ships beyond the deployment limit come in later. The engine's own end needs both sides seen as well, since a mission
    // opens paused on its deployment screen.
    private boolean seenPlayer = false;
    private boolean seenEnemy = false;

    private boolean bothSidesSeen(int[] counts) {
        seenPlayer |= counts[0] > 0;
        seenEnemy |= counts[1] > 0;
        return seenPlayer && seenEnemy;
    }

    private static boolean noReserves(CombatEngineAPI engine, int owner) {
        com.fs.starfarer.api.combat.CombatFleetManagerAPI manager = engine.getFleetManager(owner);
        return manager == null || manager.getReservesCopy() == null || manager.getReservesCopy().isEmpty();
    }

    /** Why the battle should end now, or null: a runaway field, the configured time, a side wiped out with no reserves. */
    private String endReason(CombatEngineAPI engine) {
        if (runaway) {
            return "runaway";
        }
        if (engine.getTotalElapsedTime(false) >= combatSeconds) {
            return "time";
        }
        int[] counts = new int[2];
        aliveBySide(engine, counts);
        if (!bothSidesSeen(counts)) {
            return null;
        }
        boolean playerWiped = counts[0] == 0 && noReserves(engine, 0);
        boolean enemyWiped = counts[1] == 0 && noReserves(engine, 1);
        return playerWiped || enemyWiped ? "side-wiped" : null;
    }

    private void finish(CombatEngineAPI engine, String reason) {
        ended = true;
        logNewShips(engine);  // review of 0.3.5: a ship first seen on the last frame still gets its deployment line
        ProbeLog.emit("combat-perf", runaway ? ProbeLog.STATUS_WARN : ProbeLog.STATUS_INFO, "combat",
                "frames=" + frames + " avgFrameMs=" + (frames == 0 ? 0 : Math.round(sumFrameMs / frames * 10) / 10.0)
                        + " worstFrameMs=" + Math.round(worstFrameMs) + " peakHulks=" + peakHulks + " peakShips=" + peakShips);
        reportLaunches();
        reportReserves(engine);
        ProbeLog.emit("combat-summary", ProbeLog.STATUS_INFO, "combat", "ships logged=" + loggedShips.size());
        // Why the battle ended and who was left (96.13): a side wiped out or the engine's own end is a battle won early.
        ProbeLog.emit("combat-end", runaway ? ProbeLog.STATUS_WARN : ProbeLog.STATUS_INFO, reason,
                "t=" + Math.round(engine.getTotalElapsedTime(false)) + "s " + aliveBySide(engine, new int[2]));
        ProbeLog.end("combat");
        ProbeDone.combatEnded();
        if (!"engine-ended".equals(reason)) {
            engine.endCombat(0f);
        }
    }

    @Override
    public void advance(float amount, List<InputEventAPI> events) {
        if (ended) {
            return;
        }
        com.fs.starfarer.api.combat.CombatEngineAPI engine = com.fs.starfarer.api.Global.getCombatEngine();
        if (engine == null) {
            return;
        }
        if (seenPlayer && seenEnemy && engine.isCombatOver()) {  // 96.13: the game ended it, maybe paused on its own end screen
            finish(engine, "engine-ended");
            return;
        }
        if (engine.isPaused()) {
            lastNanos = 0L; // a pause is not a slow frame
            return;
        }
        meter(engine);
        logNewShips(engine);
        trackLaunches();
        String reason = endReason(engine);
        if (reason != null) {
            finish(engine, reason);
            return;
        }
        if (!limitsRaisedInBattle && seenPlayer && seenEnemy) {
            limitsRaisedInBattle = true;
            raiseDeploymentLimits(engine, "both sides seen");
        }
    }
}
