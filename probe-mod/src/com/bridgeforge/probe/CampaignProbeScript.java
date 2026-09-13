package com.bridgeforge.probe;

import com.fs.starfarer.api.EveryFrameScript;
import com.fs.starfarer.api.Global;
import com.fs.starfarer.api.campaign.CampaignClockAPI;
import com.fs.starfarer.api.campaign.CampaignFleetAPI;
import com.fs.starfarer.api.campaign.FactionAPI;
import com.fs.starfarer.api.campaign.LocationAPI;
import com.fs.starfarer.api.campaign.OrbitAPI;
import com.fs.starfarer.api.campaign.PlanetAPI;
import com.fs.starfarer.api.campaign.PlanetSpecAPI;
import com.fs.starfarer.api.campaign.RingBandAPI;
import com.fs.starfarer.api.campaign.SectorEntityToken;
import com.fs.starfarer.api.campaign.StarSystemAPI;
import com.fs.starfarer.api.campaign.SubmarketPlugin;
import com.fs.starfarer.api.campaign.econ.MarketAPI;
import com.fs.starfarer.api.campaign.econ.SubmarketAPI;
import com.fs.starfarer.api.impl.campaign.ids.Submarkets;

import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/**
 * Runs the campaign checks from REVIVAL_ASSURANCE_PLAN.md P3, once after
 * about one in-game day (real time is irrelevant under time compression, so
 * this is measured off the campaign clock, not off {@code advance}'s
 * seconds argument), then again every {@code campaign_interval_days} from
 * {@link ProbeConfig}.
 *
 * Registered as a transient script (not saved into the player's save) by
 * {@link BfProbeModPlugin}, which only does so behind {@link RigGate}.
 *
 * Every check is wrapped in try/catch(Throwable) so one broken check never
 * stops the others from running or reporting.
 */
public class CampaignProbeScript implements EveryFrameScript {

    // Well-known RC8 vanilla faction ids. The public API has no
    // "isVanillaFaction" query, so this small, explicit list stands in for
    // one; it only narrows which markets/fleets get flagged by the
    // non-vanilla-faction checks below, never which get skipped entirely.
    private static final Set<String> VANILLA_FACTIONS = new HashSet<String>(Arrays.asList(
            "hegemony", "tritachyon", "persean", "luddic_church", "luddic_path",
            "pirates", "independent", "derelict", "neutral", "player"
    ));

    private boolean done = false;
    private ProbeConfig config;
    // A boolean, not a -1 sentinel: campaign clock timestamps can be negative, and the old
    // "startTimestamp < 0" test re-armed the script every frame so no check ever ran
    // (live bug PRB-CAMPAIGN-01: 1519 campaign-armed lines in one session).
    private boolean started = false;
    private long startTimestamp = 0L;
    private long lastRunTimestamp = 0L;
    private boolean firstRunDone = false;

    @Override
    public boolean isDone() {
        return done;
    }

    @Override
    public boolean runWhilePaused() {
        return false;
    }

    @Override
    public void advance(float amount) {
        if (done) {
            return;
        }
        if (config == null) {
            try {
                config = ProbeConfig.load();
            } catch (Exception e) {
                ProbeLog.emit("config", ProbeLog.STATUS_FAIL, "bf_probe_config", "Could not load: " + e);
                done = true;
                return;
            }
        }

        CampaignClockAPI clock = Global.getSector().getClock();
        if (!started) {
            started = true;
            startTimestamp = clock.getTimestamp();
            // Heartbeat, so a log shows the probe was running even if no check window was reached.
            ProbeLog.emit("campaign-armed", ProbeLog.STATUS_INFO, "campaign",
                    "first checks after 1 in-game day, then every " + config.campaignIntervalDays
                    + " days; clockTimestamp=" + startTimestamp);
            // Setups apply after this first real campaign tick (roadmap P3b-C, extended by P3c-1)
            // -- deliberately not gated behind the 1-day threshold below, so rep/credits/ships/
            // fleets/jump are in place before the day-1 checks (and any human observation) happen.
            // This also runs on every load (transient scripts, including this one, are never
            // saved, so a fresh instance's first tick fires again after a save/reload), which is
            // what makes bf_probe_profile's "apply = every-load" work without any extra hook.
            runCheck("setup", new Runnable() {
                public void run() {
                    applyConfiguredSetups();
                }
            });
            return;
        }

        if (!firstRunDone) {
            if (clock.getElapsedDaysSince(startTimestamp) < 1f) {
                return;
            }
            firstRunDone = true;
            lastRunTimestamp = clock.getTimestamp();
            runAllChecks();
            return;
        }

        if (clock.getElapsedDaysSince(lastRunTimestamp) >= config.campaignIntervalDays) {
            lastRunTimestamp = clock.getTimestamp();
            runAllChecks();
        }
    }

    /**
     * Roadmap P3c-1: if the rig-editable {@code bf_probe_profile} common file exists, parse it
     * and use ITS setups and apply mode INSTEAD of {@code bf_probe_config}'s own {@code setups}
     * (a present profile fully replaces the config's setups, never merges with them -- the
     * rationale is that the owner edits the rig file directly and expects it to be authoritative).
     * A missing or unparseable profile file falls back to the config's setups under the default
     * once-per-save mode, exactly like before P3c-1 existed.
     */
    private void applyConfiguredSetups() {
        List<String> setupsToApply = config.setups;
        String applyMode = ProbeProfile.APPLY_ONCE_PER_SAVE;
        if (Global.getSettings().fileExistsInCommon(ProbeFiles.PROFILE)) {
            String text = null;
            try {
                text = Global.getSettings().readTextFileFromCommon(ProbeFiles.PROFILE);
            } catch (java.io.IOException e) {
                ProbeLog.emit("profile", ProbeLog.STATUS_FAIL, "0",
                        "Could not read " + ProbeFiles.PROFILE + ": " + e);
            }
            if (text != null) {
                ProbeProfile profile = ProbeProfile.parse(text);
                if (profile != null) {
                    setupsToApply = profile.setups;
                    applyMode = profile.apply;
                }
            }
        }
        if (ProbeProfile.APPLY_EVERY_LOAD.equals(applyMode)) {
            ProbeSetup.applyAlways(setupsToApply);
        } else {
            ProbeSetup.applyOnce(setupsToApply);
        }
    }

    private void runAllChecks() {
        ProbeLog.start("campaign");
        runCheck("rings-orbits", new Runnable() {
            public void run() {
                checkRingsAndOrbits();
            }
        });
        runCheck("faction-known-lists", new Runnable() {
            public void run() {
                checkFactionKnownLists();
            }
        });
        runCheck("submarket-stock", new Runnable() {
            public void run() {
                checkSubmarketStock();
            }
        });
        runCheck("fleet-presence", new Runnable() {
            public void run() {
                checkFleetPresence();
            }
        });
        runCheck("tracked-entities", new Runnable() {
            public void run() {
                checkTrackedEntities();
            }
        });
        runCheck("planet-specs", new Runnable() {
            public void run() {
                checkPlanetSpecs();
            }
        });
        ProbeLog.end("campaign");
    }

    private void runCheck(String name, Runnable check) {
        try {
            check.run();
        } catch (Throwable t) {
            ProbeLog.emit(name, ProbeLog.STATUS_FAIL, name,
                    t.getClass().getName() + ": " + t.getMessage());
        }
    }

    // ---- ring bands / orbits ---------------------------------------------------------

    private void checkRingsAndOrbits() {
        int checked = 0;
        int bad = 0;
        for (StarSystemAPI system : Global.getSector().getStarSystems()) {
            for (SectorEntityToken entity : system.getAllEntities()) {
                OrbitAPI orbit = entity.getOrbit();
                if (orbit == null) {
                    continue;
                }
                checked++;
                float period = orbit.getOrbitalPeriod();
                if (!isFinite(period)) {
                    bad++;
                    ProbeLog.emit("rings-orbits", ProbeLog.STATUS_FAIL,
                            system.getBaseName() + "/" + entity.getId(),
                            "Non-finite orbital period: " + period);
                }
            }
            List<RingBandAPI> ringBands = system.getEntities(RingBandAPI.class);
            for (RingBandAPI ring : ringBands) {
                checked++;
                float middleRadius = ring.getMiddleRadius();
                float bandWidth = ring.getBandWidthInEngine();
                float orbitDays = ring.getOrbitDays();
                if (!isFinite(middleRadius) || !isFinite(bandWidth) || !isFinite(orbitDays)) {
                    bad++;
                    ProbeLog.emit("rings-orbits", ProbeLog.STATUS_FAIL,
                            system.getBaseName() + "/" + ring.getId(),
                            "Non-finite ring values: middleRadius=" + middleRadius
                                    + " bandWidth=" + bandWidth + " orbitDays=" + orbitDays);
                }
            }
        }
        if (bad == 0) {
            ProbeLog.emit("rings-orbits", ProbeLog.STATUS_OK, "sector", checked + " orbits/rings checked, all finite");
        }
    }

    private static boolean isFinite(float value) {
        return !Float.isNaN(value) && !Float.isInfinite(value);
    }

    // ---- faction known lists ----------------------------------------------------------

    private Set<String> factionsWithMarkets() {
        Set<String> result = new HashSet<String>();
        for (MarketAPI market : Global.getSector().getEconomy().getMarketsCopy()) {
            String factionId = market.getFactionId();
            if (factionId != null) {
                result.add(factionId);
            }
        }
        return result;
    }

    /**
     * The target mod's own non-vanilla factions that own no market. The market-driven checks never
     * saw them: in live run EX-7, Exigency's market-less faction had 0 fleets for ~20 days, unreported.
     */
    private Set<String> modFactionsWithoutMarkets(Set<String> withMarkets) {
        Set<String> result = new HashSet<String>();
        for (String factionId : config.factions) {
            if (!VANILLA_FACTIONS.contains(factionId) && !withMarkets.contains(factionId)
                    && Global.getSector().getFaction(factionId) != null) {
                result.add(factionId);
            }
        }
        return result;
    }

    private void checkFactionKnownLists() {
        Set<String> factionsToCheck = factionsWithMarkets();
        factionsToCheck.addAll(modFactionsWithoutMarkets(factionsToCheck));
        for (String factionId : factionsToCheck) {
            FactionAPI faction = Global.getSector().getFaction(factionId);
            if (faction == null) {
                continue;
            }
            int ships = faction.getKnownShips().size();
            int weapons = faction.getKnownWeapons().size();
            int fighters = faction.getKnownFighters().size();
            if (ships == 0 || weapons == 0 || fighters == 0) {
                ProbeLog.emit("faction-known-lists", ProbeLog.STATUS_WARN, factionId,
                        "knownShips=" + ships + " knownWeapons=" + weapons + " knownFighters=" + fighters);
            } else {
                ProbeLog.emit("faction-known-lists", ProbeLog.STATUS_OK, factionId,
                        "knownShips=" + ships + " knownWeapons=" + weapons + " knownFighters=" + fighters);
            }
        }
    }

    // ---- submarket stock -----------------------------------------------------------

    private void checkSubmarketStock() {
        for (MarketAPI market : Global.getSector().getEconomy().getMarketsCopy()) {
            String factionId = market.getFactionId();
            boolean nonVanilla = factionId != null && !VANILLA_FACTIONS.contains(factionId);
            for (SubmarketAPI submarket : market.getSubmarketsCopy()) {
                SubmarketPlugin plugin = submarket.getPlugin();
                if (plugin == null) {
                    continue;
                }
                // Storage is the player's own locker, empty until used. Live runs EX-B5/B6/EX-7
                // flagged every market's storage as missing stock.
                if (Submarkets.SUBMARKET_STORAGE.equals(submarket.getSpecId())) {
                    continue;
                }
                try {
                    plugin.updateCargoPrePlayerInteraction();
                } catch (Throwable t) {
                    ProbeLog.emit("submarket-stock", ProbeLog.STATUS_FAIL,
                            market.getId() + "/" + submarket.getSpecId(),
                            "updateCargoPrePlayerInteraction threw " + t.getClass().getName() + ": " + t.getMessage());
                    continue;
                }
                boolean relevantKind = plugin.isOpenMarket() || plugin.isMilitaryMarket() || plugin.isBlackMarket();
                if (!nonVanilla || !relevantKind) {
                    continue;
                }
                com.fs.starfarer.api.campaign.FleetDataAPI mothballed = submarket.getCargo().getMothballedShips();
                int shipCount = mothballed == null ? 0 : mothballed.getNumMembers();
                int weaponStacks = submarket.getCargo().getWeapons().size();
                String subject = market.getId() + "/" + submarket.getSpecId();
                if (shipCount == 0 || weaponStacks == 0) {
                    ProbeLog.emit("submarket-stock", ProbeLog.STATUS_WARN, subject,
                            "ships=" + shipCount + " weaponStacks=" + weaponStacks + " faction=" + factionId);
                } else {
                    ProbeLog.emit("submarket-stock", ProbeLog.STATUS_OK, subject,
                            "ships=" + shipCount + " weaponStacks=" + weaponStacks);
                }
            }
        }
    }

    // ---- fleet presence per faction -------------------------------------------------

    private void checkFleetPresence() {
        Set<String> factionsWithMarkets = factionsWithMarkets();
        java.util.Map<String, Integer> counts = new java.util.HashMap<String, Integer>();
        for (LocationAPI location : Global.getSector().getAllLocations()) {
            for (CampaignFleetAPI fleet : location.getFleets()) {
                FactionAPI faction = fleet.getFaction();
                if (faction == null) {
                    continue;
                }
                Integer current = counts.get(faction.getId());
                counts.put(faction.getId(), current == null ? 1 : current + 1);
            }
        }
        for (String factionId : factionsWithMarkets) {
            Integer count = counts.get(factionId);
            int n = count == null ? 0 : count;
            if (n == 0) {
                ProbeLog.emit("fleet-presence", ProbeLog.STATUS_WARN, factionId, "0 fleets in the sector");
            } else {
                ProbeLog.emit("fleet-presence", ProbeLog.STATUS_OK, factionId, n + " fleets in the sector");
            }
        }
        // INFO, not WARN: some mod factions legitimately field no fleets (contacts, story factions).
        // The count is the evidence; a scenario or the reviewer decides whether 0 is wrong.
        for (String factionId : modFactionsWithoutMarkets(factionsWithMarkets)) {
            Integer count = counts.get(factionId);
            int n = count == null ? 0 : count;
            ProbeLog.emit("fleet-presence", ProbeLog.STATUS_INFO, factionId,
                    n + " fleets in the sector (mod faction, no markets)");
        }
    }

    // ---- tracked custom entities -----------------------------------------------------

    private void checkTrackedEntities() {
        for (String entityId : config.trackEntities) {
            SectorEntityToken entity = Global.getSector().getEntityById(entityId);
            if (entity == null) {
                ProbeLog.emit("tracked-entities", ProbeLog.STATUS_WARN, entityId, "not found in sector");
                continue;
            }
            org.lwjgl.util.vector.Vector2f loc = entity.getLocation();
            ProbeLog.emit("tracked-entities", ProbeLog.STATUS_INFO, entityId,
                    "x=" + loc.x + " y=" + loc.y);
        }
    }

    // ---- custom planet/star spec lookups ---------------------------------------------

    private void checkPlanetSpecs() {
        // Planet types are keyed by PlanetSpecAPI.getPlanetType() and listed by getAllPlanetSpecs().
        // SettingsAPI.getSpec(PlanetSpecAPI.class, typeId, ...) never resolves them: it reported all
        // 1,010 vanilla planets as FAIL on the first working live run (PRB-PLANET-01).
        Set<String> knownTypes = new HashSet<String>();
        for (PlanetSpecAPI spec : Global.getSettings().getAllPlanetSpecs()) {
            if (spec != null && spec.getPlanetType() != null) {
                knownTypes.add(spec.getPlanetType());
            }
        }
        int checked = 0;
        int unresolved = 0;
        for (StarSystemAPI system : Global.getSector().getStarSystems()) {
            for (PlanetAPI planet : system.getPlanets()) {
                checked++;
                String typeId = planet.getTypeId();
                if (planet.getSpec() == null || typeId == null || !knownTypes.contains(typeId)) {
                    unresolved++;
                    ProbeLog.emit("planet-specs", ProbeLog.STATUS_FAIL, system.getBaseName() + "/" + planet.getId(),
                            "planet type [" + typeId + "] has no planet spec (getSpec()=" + (planet.getSpec() == null ? "null" : "set") + ")");
                }
            }
        }
        ProbeLog.emit("planet-specs", unresolved == 0 ? ProbeLog.STATUS_OK : ProbeLog.STATUS_FAIL, "all-systems",
                "planets checked=" + checked + " unresolved=" + unresolved + " known types=" + knownTypes.size());
    }
}
