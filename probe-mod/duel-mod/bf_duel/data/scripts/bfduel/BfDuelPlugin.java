package data.scripts.bfduel;

import com.fs.starfarer.api.Global;
import com.fs.starfarer.api.combat.CombatEngineAPI;
import com.fs.starfarer.api.combat.DamageType;
import com.fs.starfarer.api.combat.EveryFrameCombatPlugin;
import com.fs.starfarer.api.combat.ShipAPI;
import com.fs.starfarer.api.combat.ViewportAPI;

import java.util.HashSet;
import java.util.List;
import java.util.Set;

/**
 * BridgeForge duel meter (rig only). Logs one "BF-DUEL|..." line per second of real time with the frame period
 * (System.nanoTime between advance calls, so it includes rendering), a wall-clock timer and what is on the field; a FIGHT line
 * when the first ship that was alive on the player's side is destroyed (game seconds and real seconds from the start); and an END
 * line a fixed number of real seconds after that, or when a side is gone, or at the game-time cap. Loose script: Janino, no
 * generics, no lambdas. Public API only.
 *
 * The same story runs in several missions (SEEKER's hulls against each other, overwhelmed, and a vanilla pair as the baseline)
 * so the cost of fragmenting hulls shows against hulls that do not.
 */
public class BfDuelPlugin implements EveryFrameCombatPlugin {

    private static final float OBSERVE_GAME_SECONDS = 12f; // game seconds after a side is gone
    private static final float OBSERVE_REAL_SECONDS = 45f; // real seconds after the first kill (the game may be at one frame a second)
    private static final float MAX_GAME_SECONDS = 420f;

    private final String label;
    private final float forceKillAfter;
    private boolean forcedKill = false;
    private CombatEngineAPI engine;
    private long startNanos = 0L;
    private long lastNanos = 0L;
    private long windowStart = 0L;
    private int frames = 0;
    private int calls = 0;
    private int pausedCalls = 0;
    private int forcedUnpauses = 0;
    private double sumMs = 0;
    private double maxMs = 0;
    private float sideGoneAt = -1f;
    private boolean ended = false;
    private final Set seenAlive = new HashSet();
    private boolean sawEnemy = false;
    private long killNanos = 0L;
    private double worstOverall = 0;
    private double sumAll = 0;
    private int framesAll = 0;
    private int peakHulks = 0;
    private int peakShips = 0;
    private double worstAfterKill = 0;

    public BfDuelPlugin(String label) {
        this(label, -1f);
    }

    /** forceKillAfter: game seconds after which the player's side is destroyed by a huge hit if it is still alive (an overwhelmed hull, deterministic); -1 for none. */
    public BfDuelPlugin(String label, float forceKillAfter) {
        this.label = label;
        this.forceKillAfter = forceKillAfter;
    }

    public void init(CombatEngineAPI engine) {
        this.engine = engine;
        this.startNanos = System.nanoTime();
        log("START", "label=" + label);
    }

    public void processInputPreCoreControls(float amount, List events) {
    }

    public void advance(float amount, List events) {
        if (engine == null || ended) {
            return;
        }
        long now = System.nanoTime();
        calls++;
        if (engine.isPaused()) {
            pausedCalls++;
            // With no flagship deployed the game parks the combat at "shuttle ready for command transfer" about nine seconds in
            // (duel runs 2026-10-11); this is an AI-only duel, so keep it running once deployment is over.
            if (engine.getTotalElapsedTime(false) > 2f) {
                engine.setPaused(false);
                forcedUnpauses++;
            }
        }
        if (lastNanos != 0L && !engine.isPaused()) {
            double ms = (now - lastNanos) / 1000000.0;
            frames++;
            framesAll++;
            sumMs += ms;
            sumAll += ms;
            if (ms > maxMs) {
                maxMs = ms;
            }
            if (ms > worstOverall) {
                worstOverall = ms;
            }
            if (killNanos != 0L && ms > worstAfterKill) {
                worstAfterKill = ms;
            }
        }
        lastNanos = now;
        if (windowStart == 0L) {
            windowStart = now;
        }
        float t = engine.getTotalElapsedTime(false);
        double real = (now - startNanos) / 1000000000.0;

        int alive0 = 0;
        int alive1 = 0;
        int hulks = 0;
        List ships = engine.getShips();
        for (int i = 0; i < ships.size(); i++) {
            ShipAPI ship = (ShipAPI) ships.get(i);
            if (ship.isFighter()) {
                continue;
            }
            if (ship.isHulk()) {
                hulks++;
                if (killNanos == 0L && seenAlive.contains(ship)) {
                    markKill(ship, t, real, ships.size());
                }
                continue;
            }
            if (ship.isAlive()) {
                if (ship.getOwner() == 0) {
                    alive0++;
                    seenAlive.add(ship);
                } else {
                    alive1++;
                    sawEnemy = true;
                }
            } else if (killNanos == 0L && seenAlive.contains(ship)) {
                markKill(ship, t, real, ships.size());
            }
        }
        if (forceKillAfter > 0f && !forcedKill && t >= forceKillAfter && alive0 > 0) {
            forcedKill = true;
            for (int i = 0; i < ships.size(); i++) {
                ShipAPI victim = (ShipAPI) ships.get(i);
                if (!victim.isFighter() && !victim.isHulk() && victim.isAlive() && victim.getOwner() == 0) {
                    log("FORCED-KILL", "t=" + format(t) + " real=" + format(real) + " hull=" + victim.getHullSpec().getHullId());
                    engine.applyDamage(victim, victim.getLocation(), 10000000f, DamageType.HIGH_EXPLOSIVE, 0f, true, false, null);
                }
            }
        }
        if (hulks > peakHulks) {
            peakHulks = hulks;
        }
        if (ships.size() > peakShips) {
            peakShips = ships.size();
        }

        if (now - windowStart >= 1000000000L && calls > 0) {
            String sinceKill = killNanos == 0L ? "-" : format((now - killNanos) / 1000000000.0);
            log("SECOND", "t=" + format(t) + " real=" + format(real) + " sinceKill=" + sinceKill + " calls=" + calls + " paused=" + pausedCalls
                    + " forcedUnpauses=" + forcedUnpauses + " timeMult=" + format(engine.getTimeMult().getModifiedValue()) + " frames=" + frames
                    + " avgMs=" + format(frames == 0 ? 0 : sumMs / frames) + " maxMs=" + format(maxMs)
                    + " alive=" + alive0 + "/" + alive1 + " hulks=" + hulks + " ships=" + ships.size()
                    + " projectiles=" + engine.getProjectiles().size() + " missiles=" + engine.getMissiles().size()
                    + " beams=" + engine.getBeams().size() + " asteroids=" + engine.getAsteroids().size());
            windowStart = now;
            calls = 0;
            pausedCalls = 0;
            frames = 0;
            sumMs = 0;
            maxMs = 0;
        }

        if ((alive0 == 0 || alive1 == 0) && sideGoneAt < 0f && seenAlive.size() > 0 && sawEnemy) {
            sideGoneAt = t;
            log("SIDE-GONE", "t=" + format(t) + " real=" + format(real) + " alive=" + alive0 + "/" + alive1 + " hulks=" + hulks);
        }
        if (killNanos == 0L && seenAlive.size() > 0 && alive0 == 0) {
            // The ship was removed outright instead of staying as a hulk (Bone-Breaker after the 2026-10-11 death fix): the kill is
            // the frame its side emptied.
            killNanos = now;
            log("FIGHT", "gameSeconds=" + format(t) + " realSeconds=" + format(real) + " destroyed=removed owner=0 ships=" + ships.size()
                    + " projectiles=" + engine.getProjectiles().size());
        }
        if (engine.isCombatOver()) {
            ended = true;
            log("END", "t=" + format(t) + " real=" + format(real) + " frames=" + framesAll + " avgMs=" + format(framesAll == 0 ? 0 : sumAll / framesAll)
                    + " worstMs=" + format(worstOverall) + " worstAfterKillMs=" + format(worstAfterKill) + " peakHulks=" + peakHulks
                    + " peakShips=" + peakShips + " reason=combat-over");
            return;
        }
        boolean observedLongEnough = killNanos != 0L && (now - killNanos) / 1000000000.0 >= OBSERVE_REAL_SECONDS;
        boolean sideGoneObserved = sideGoneAt >= 0f && t - sideGoneAt >= OBSERVE_GAME_SECONDS;
        if (observedLongEnough || sideGoneObserved || t >= MAX_GAME_SECONDS) {
            ended = true;
            log("END", "t=" + format(t) + " real=" + format(real) + " frames=" + framesAll + " avgMs=" + format(framesAll == 0 ? 0 : sumAll / framesAll)
                    + " worstMs=" + format(worstOverall) + " worstAfterKillMs=" + format(worstAfterKill) + " peakHulks=" + peakHulks
                    + " peakShips=" + peakShips + " reason=" + (observedLongEnough ? "real-time-after-kill" : (sideGoneObserved ? "side-gone" : "time-cap")));
            engine.endCombat(0.5f);
        }
    }

    private void markKill(ShipAPI ship, float t, double real, int shipCount) {
        killNanos = System.nanoTime();
        log("FIGHT", "gameSeconds=" + format(t) + " realSeconds=" + format(real) + " destroyed=" + ship.getHullSpec().getHullId()
                + " owner=" + ship.getOwner() + " ships=" + shipCount + " projectiles=" + engine.getProjectiles().size());
    }

    public void renderInWorldCoords(ViewportAPI viewport) {
    }

    public void renderInUICoords(ViewportAPI viewport) {
    }

    private String format(double value) {
        return String.valueOf(Math.round(value * 100.0) / 100.0);
    }

    private void log(String what, String detail) {
        Global.getLogger(BfDuelPlugin.class).info("BF-DUEL|" + label + "|" + what + "|" + detail);
    }
}
