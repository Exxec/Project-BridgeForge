package data.scripts.bfraid;

import org.json.JSONObject;

import com.fs.starfarer.api.EveryFrameScript;
import com.fs.starfarer.api.Global;
import com.fs.starfarer.api.campaign.FactionAPI;
import com.fs.starfarer.api.campaign.econ.MarketAPI;

import exerelin.campaign.intel.raid.NexRaidIntel;

/**
 * Forces one Nexerelin raid on the market named in data/config/bf_raid.json and logs BF-RAID lines:
 *   BF-RAID|idle|reason            no target configured, or the config could not be used
 *   BF-RAID|raid-start|...         the intel was created and registered (attacker, from, target, fleet points)
 *   BF-RAID|raid-end|...           the intel ended: outcome, days since start
 *   BF-RAID|raid-timeout|...       maxDays passed without the intel ending
 *   BF-RAID|error|...              creating the intel threw; the message names the cause
 * Uses NexRaidIntel(FactionAPI attacker, MarketAPI from, MarketAPI target, float fp, float orgDur) then init(), the way
 * exerelin.campaign.fleets.InvasionFleetManager does (javap of Nexerelin 0.12.2d ExerelinCore.jar, 2026-10-14).
 * Loose script: no lambdas, no generics-dependent calls (the game's Janino).
 */
public class BfRaidScript implements EveryFrameScript {

    static final String CONFIG = "data/config/bf_raid.json";
    static final String MOD_ID = "bf_raid";

    private boolean done = false;
    private boolean started = false;
    private float days = 0f;
    private float startedAt = 0f;
    private float startAfterDays = 3f;
    private float maxDays = 120f;
    private boolean loaded = false;
    private JSONObject config;
    private NexRaidIntel intel;

    public boolean isDone() {
        return done;
    }

    public boolean runWhilePaused() {
        return false;
    }

    public void advance(float amount) {
        if (done || Global.getSector().getPlayerFleet() == null) {
            return;
        }
        days += Global.getSector().getClock().convertToDays(amount);
        if (!loaded) {
            loaded = true;
            if (!loadConfig()) {
                finish();
                return;
            }
        }
        if (!started) {
            if (days >= startAfterDays) {
                started = true;
                startedAt = days;
                start();
            }
            return;
        }
        if (intel == null) {
            finish();
            return;
        }
        if (intel.isEnded() || intel.isEnding()) {
            log("raid-end|outcome=" + intel.getOutcome() + "|days=" + (days - startedAt));
            finish();
        } else if (days - startedAt >= maxDays) {
            log("raid-timeout|days=" + (days - startedAt) + "|outcome=" + intel.getOutcome());
            finish();
        }
    }

    private boolean loadConfig() {
        try {
            config = Global.getSettings().loadJSON(CONFIG, MOD_ID);
        } catch (Throwable t) {
            log("idle|config unreadable: " + t);
            return false;
        }
        if (config.optString("targetMarket", "").length() == 0) {
            log("idle|no targetMarket in " + CONFIG);
            return false;
        }
        startAfterDays = (float) config.optDouble("startAfterDays", 3.0);
        maxDays = (float) config.optDouble("maxDays", 120.0);
        return true;
    }

    private void start() {
        try {
            MarketAPI target = Global.getSector().getEconomy().getMarket(config.getString("targetMarket"));
            if (target == null) {
                log("error|target market not found: " + config.getString("targetMarket"));
                finish();
                return;
            }
            MarketAPI from = pickSource(target);
            if (from == null) {
                log("error|no source market (set fromMarket, or attackerFaction with a market that is not the target)");
                finish();
                return;
            }
            String factionId = config.optString("attackerFaction", "");
            FactionAPI attacker = factionId.length() > 0 ? Global.getSector().getFaction(factionId) : from.getFaction();
            float fp = (float) config.optDouble("fleetPoints", 120.0);
            float orgDur = (float) config.optDouble("organizeDays", 2.0);
            intel = new NexRaidIntel(attacker, from, target, fp, orgDur);
            intel.init();
            if (config.optBoolean("forceSpawn", false)) {
                intel.forceSpawnFleets();
            }
            log("raid-start|attacker=" + attacker.getId() + "|from=" + from.getId() + "|target=" + target.getId()
                + "|targetFaction=" + target.getFactionId() + "|fp=" + fp + "|ended=" + intel.isEnded());
        } catch (Throwable t) {
            log("error|creating the raid threw: " + t);
            intel = null;
            finish();
        }
    }

    private MarketAPI pickSource(MarketAPI target) {
        String fromId = config.optString("fromMarket", "");
        if (fromId.length() > 0) {
            return Global.getSector().getEconomy().getMarket(fromId);
        }
        String factionId = config.optString("attackerFaction", "");
        if (factionId.length() == 0) {
            return null;
        }
        MarketAPI best = null;
        float bestSize = -1f;
        java.util.List markets = Global.getSector().getEconomy().getMarketsCopy();
        for (int i = 0; i < markets.size(); i++) {
            MarketAPI market = (MarketAPI) markets.get(i);
            if (market != target && factionId.equals(market.getFactionId()) && market.getSize() > bestSize) {
                best = market;
                bestSize = market.getSize();
            }
        }
        return best;
    }

    private void finish() {
        done = true;
        Global.getSector().getMemoryWithoutUpdate().set(BfRaidPlugin.DONE_KEY, true);
    }

    private void log(String line) {
        Global.getLogger(BfRaidScript.class).info("BF-RAID|" + line);
    }
}
