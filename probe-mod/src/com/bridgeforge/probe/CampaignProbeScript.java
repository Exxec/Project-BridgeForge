package com.bridgeforge.probe;

import com.fs.starfarer.api.EveryFrameScript;
import com.fs.starfarer.api.Global;
import com.fs.starfarer.api.campaign.CargoAPI;
import com.fs.starfarer.api.campaign.CargoStackAPI;
import com.fs.starfarer.api.campaign.SpecialItemData;
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
import com.fs.starfarer.api.fleet.FleetMemberAPI;
import com.fs.starfarer.api.fleet.FleetMemberType;
import com.fs.starfarer.api.combat.ShipVariantAPI;
import com.fs.starfarer.api.impl.campaign.fleets.FleetFactoryV3;
import com.fs.starfarer.api.impl.campaign.fleets.FleetParamsV3;
import com.fs.starfarer.api.impl.campaign.ids.FleetTypes;
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
    // content-ids builds every mod variant once; repeating it each interval adds nothing.
    private boolean contentIdsChecked = false;

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
        runCheck("faction-fleet-gen", new Runnable() {
            public void run() {
                checkFactionFleetGeneration();
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
        runCheck("content-ids", new Runnable() {
            public void run() {
                checkContentIds();
            }
        });
        runCheck("campaign-layout", new Runnable() {
            public void run() {
                checkCampaignLayout();
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

    /**
     * 0.2.8 (ROADMAP item 29.2, from Legacy of Arkgneisis's loa_randtest): build one medium patrol for each of the
     * target mod's own factions with RC8's own generator, the way the game makes its fleets. That tests the
     * faction's doctrine, known ships and autofit together; hand-made variants alone do not. The fleet is never
     * spawned into the sector. FleetParamsV3 fields and FleetFactoryV3.createFleet checked with javap, 2026-09-27.
     */
    private void checkFactionFleetGeneration() {
        Set<String> toBuild = new HashSet<String>();
        for (String factionId : config.factions) {
            if (!VANILLA_FACTIONS.contains(factionId)) {
                toBuild.add(factionId);
            }
        }
        // 0.2.9 (GRP-8, 2026-09-28): a mod that only patches a faction (Amogus-Shipyards' hegemony.faction adds its
        // ships to the Hegemony) had nothing checked; build the patched factions' fleets as well.
        toBuild.addAll(config.patchedFactions);
        for (String factionId : toBuild) {
            FactionAPI generated = Global.getSector().getFaction(factionId);
            if (generated == null) {
                continue;
            }
            if (generated.getKnownShips().isEmpty()) {
                // 0.2.10: a faction with no known ships fields no fleets by design (Exigency's mysterious_contact).
                ProbeLog.emit("faction-fleet-gen", ProbeLog.STATUS_INFO, factionId, "skipped: the faction knows no ships");
                continue;
            }
            FleetParamsV3 params = new FleetParamsV3();
            params.factionId = factionId;
            params.fleetType = FleetTypes.PATROL_MEDIUM;
            params.combatPts = 60f;
            params.quality = 1f;
            params.qualityOverride = Float.valueOf(1f);
            params.ignoreMarketFleetSizeMult = Boolean.TRUE;
            params.random = new java.util.Random(1L);
            try {
                CampaignFleetAPI fleet = FleetFactoryV3.createFleet(params);
                int members = fleet == null ? 0 : fleet.getFleetData().getNumMembers();
                if (members == 0) {
                    ProbeLog.emit("faction-fleet-gen", ProbeLog.STATUS_FAIL, factionId,
                            "FleetFactoryV3 built an empty " + FleetTypes.PATROL_MEDIUM + " (doctrine or known ships unusable)");
                } else {
                    ProbeLog.emit("faction-fleet-gen", ProbeLog.STATUS_OK, factionId,
                            members + " member(s) in a generated " + FleetTypes.PATROL_MEDIUM);
                }
            } catch (Throwable t) {
                ProbeLog.emit("faction-fleet-gen", ProbeLog.STATUS_FAIL, factionId,
                        "FleetFactoryV3.createFleet threw " + t.getClass().getName() + ": " + t.getMessage());
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

    // ---- the mod's own variant and wing ids (ROADMAP P14 item 49) ---------------------
    //
    // Runtime ground truth for what the scanner can only infer: does the game itself resolve every
    // variant and wing id the mod defines? API evidence (RC8): SettingsAPI.doesVariantExist(String)
    // and getFighterWingSpec(String) are both called by RevenantLib 1.2.0+bf.1's RC8-built jar
    // (constant-pool Methodrefs, read 2026-09-24); Global.getFactory().createFleetMember(SHIP, id) is
    // ProbeSetup's own, live-run call. Building the member also resolves the variant's hull, weapons
    // and hull mods; fittedProblem then looks each fitted id up directly (0.2.3).

    private void checkContentIds() {
        if (contentIdsChecked) {
            return;
        }
        contentIdsChecked = true;
        int failed = 0;
        for (String variantId : config.contentShipVariants) {
            String problem = variantProblem(variantId, true);
            if (problem == null) {
                problem = hullProblem(variantId, config.contentShipHulls.get(variantId));
            }
            failed += reportContent("variant", variantId, problem);
        }
        for (String variantId : config.contentOtherVariants) {
            failed += reportContent("variant", variantId, variantProblem(variantId, false));
        }
        for (String wingId : config.contentWings) {
            failed += reportContent("wing", wingId, wingProblem(wingId));
        }
        for (String itemId : config.contentSpecialItems) {
            failed += reportContent("item", itemId, specialItemProblem(itemId));
        }
        int total = config.contentShipVariants.size() + config.contentOtherVariants.size() + config.contentWings.size()
                + config.contentSpecialItems.size();
        ProbeLog.emit("content-ids", failed == 0 ? ProbeLog.STATUS_OK : ProbeLog.STATUS_FAIL, "all-content",
                "checked=" + total + " failed=" + failed + " ship-variants built=" + config.contentShipVariants.size());
    }

    private static int reportContent(String kind, String id, String problem) {
        if (problem == null) {
            return 0;
        }
        ProbeLog.emit("content-ids", ProbeLog.STATUS_FAIL, kind + ":" + id, problem);
        return 1;
    }

    private static String variantProblem(String variantId, boolean build) {
        try {
            if (!Global.getSettings().doesVariantExist(variantId)) {
                return "doesVariantExist=false";
            }
            if (build) {
                FleetMemberAPI member = Global.getFactory().createFleetMember(FleetMemberType.SHIP, variantId);
                if (member == null) {
                    return "createFleetMember(SHIP) returned null";
                }
                return fittedProblem(member.getVariant(), "", 0);
            }
            return null;
        } catch (Throwable t) {
            return t.getClass().getName() + ": " + t.getMessage();
        }
    }

    // Building a member does not prove every id it lists resolves: a live run showed a variant naming a
    // missing weapon is a hard new-game fatal, but other ids may be carried or dropped quietly. Look each
    // one up directly (javap, RC8 starfarer.api.jar, 2026-09-27: ShipVariantAPI.getHullMods/
    // getFittedWeaponSlots/getWeaponId/getWings/getModuleSlots/getModuleVariant; SettingsAPI.getHullModSpec/
    // getWeaponSpec). A lookup that throws counts as missing. Modules are checked to a depth of 3.
    private static String fittedProblem(ShipVariantAPI variant, String where, int depth) {
        if (variant == null) {
            return where.isEmpty() ? "built member has no variant" : where + "no variant";
        }
        for (String modId : variant.getHullMods()) {
            if (!resolves("hullmod", modId)) {
                return where + "hull mod [" + modId + "] has no spec";
            }
        }
        for (String slot : variant.getFittedWeaponSlots()) {
            String weaponId = variant.getWeaponId(slot);
            if (weaponId != null && !resolves("weapon", weaponId)) {
                return where + "weapon [" + weaponId + "] in slot " + slot + " has no spec";
            }
        }
        for (String wingId : variant.getWings()) {
            if (wingId != null && wingProblem(wingId) != null) {
                return where + "wing [" + wingId + "] has no spec";
            }
        }
        if (depth < 3) {
            for (String slot : variant.getModuleSlots()) {
                String problem = fittedProblem(variant.getModuleVariant(slot), where + "module " + slot + ": ", depth + 1);
                if (problem != null) {
                    return problem;
                }
            }
        }
        return null;
    }

    // PRB-FIGHTER-01 (live run PRB-1b, 2026-09-13): a variant built as a SHIP came out as a vanilla Nebula,
    // because the game substitutes a default hull. Compare the built member's hull with the hullId the
    // .variant names (FleetMemberAPI.getHullId(), ShipHullSpecAPI.getBaseHullId(); javap 2026-09-27).
    private static String hullProblem(String variantId, String expectedHull) {
        if (expectedHull == null) {
            return null;
        }
        try {
            FleetMemberAPI member = Global.getFactory().createFleetMember(FleetMemberType.SHIP, variantId);
            String built = member.getHullId();
            String base = member.getHullSpec() == null ? null : member.getHullSpec().getBaseHullId();
            if (expectedHull.equals(built) || expectedHull.equals(base)) {
                return null;
            }
            return "built as hull [" + built + "] but the variant names [" + expectedHull + "] (substituted hull)";
        } catch (Throwable t) {
            return t.getClass().getName() + ": " + t.getMessage();
        }
    }

    private static boolean resolves(String kind, String id) {
        try {
            return "hullmod".equals(kind) ? Global.getSettings().getHullModSpec(id) != null : Global.getSettings().getWeaponSpec(id) != null;
        } catch (Throwable t) {
            return false;
        }
    }

    // P15 item 22.7: a special item works through its plugin class (Yunru's Unpack Blueprints). Build a
    // cargo stack of it in a throwaway cargo, which instantiates the plugin as real cargo does
    // (javap, RC8 starfarer.api.jar, 2026-09-27: SettingsAPI.getSpecialItemSpec, FactoryAPI.createCargo,
    // CargoAPI.addSpecial/getStacksCopy, CargoStackAPI.getPlugin).
    private static String specialItemProblem(String itemId) {
        try {
            if (Global.getSettings().getSpecialItemSpec(itemId) == null) {
                return "getSpecialItemSpec=null";
            }
            CargoAPI cargo = Global.getFactory().createCargo(true);
            cargo.addSpecial(new SpecialItemData(itemId, null), 1);
            List<CargoStackAPI> stacks = cargo.getStacksCopy();
            if (stacks.isEmpty()) {
                return "addSpecial produced no cargo stack";
            }
            if (stacks.get(0).getPlugin() == null) {
                return "no plugin instance for the item";
            }
            return null;
        } catch (Throwable t) {
            return t.getClass().getName() + ": " + t.getMessage();
        }
    }

    private static String wingProblem(String wingId) {
        try {
            return Global.getSettings().getFighterWingSpec(wingId) == null ? "getFighterWingSpec=null" : null;
        } catch (Throwable t) {
            return t.getClass().getName() + ": " + t.getMessage();
        }
    }

    // ---- custom planet/star spec lookups ---------------------------------------------

    // P15 item 25 (0.2.6). Zorg18 (2026-09-27): its artificial star, meant for Zorg Zeta, also appeared in random
    // systems through procgen weights. Every system the mod creates must exist; a mod body type with no procgen
    // weight must stay in those systems (FAIL otherwise), and one with a weight is reported with where it went.
    // API (javap, RC8 starfarer.api.jar, 2026-09-27): SectorAPI.getStarSystem(String)/getStarSystems(),
    // LocationAPI.getPlanets(), PlanetAPI.getTypeId(), StarSystemAPI.getBaseName().
    /** A random sector (Nexerelin's non-Corvus mode) has no vanilla Corvus system. Public API only: the script sandbox
     *  forbids reflection, so Nexerelin's SectorManager.getCorvusMode() cannot be called (0.2.10). */
    private static boolean nexerelinRandomSector() {
        return Global.getSector().getStarSystem("Corvus") == null;
    }

    private void checkCampaignLayout() {
        if (config.modSystems.isEmpty() && config.modBodyTypes.isEmpty()) {
            return;
        }
        int missing = 0;
        for (String name : config.modSystems) {
            if (Global.getSector().getStarSystem(name) == null) {
                if (nexerelinRandomSector()) {
                    // 0.2.10: in Nexerelin's random sector a mod may skip its own systems by design (Exigency skips
                    // Tasserus unless SectorManager.getCorvusMode(), EXI-SOLO 2026-09-28).
                    ProbeLog.emit("campaign-layout", ProbeLog.STATUS_WARN, "system:" + name, "not in the sector; Nexerelin random-sector mode, where mods may skip their systems");
                } else {
                    ProbeLog.emit("campaign-layout", ProbeLog.STATUS_FAIL, "system:" + name, "the mod creates this system but it is not in the sector");
                    missing++;
                }
            }
        }
        Set<String> own = new HashSet<String>(config.modSystems);
        java.util.Map<String, List<String>> elsewhere = new java.util.LinkedHashMap<String, List<String>>();
        java.util.Map<String, Integer> total = new java.util.LinkedHashMap<String, Integer>();
        for (StarSystemAPI system : Global.getSector().getStarSystems()) {
            for (PlanetAPI planet : system.getPlanets()) {
                String type = planet.getTypeId();
                if (type == null || !config.modBodyTypes.containsKey(type)) {
                    continue;
                }
                Integer count = total.get(type);
                total.put(type, count == null ? 1 : count + 1);
                if (!own.contains(system.getBaseName())) {
                    List<String> where = elsewhere.get(type);
                    if (where == null) {
                        where = new java.util.ArrayList<String>();
                        elsewhere.put(type, where);
                    }
                    if (!where.contains(system.getBaseName())) {
                        where.add(system.getBaseName());
                    }
                }
            }
        }
        int leaked = 0;
        for (String type : config.modBodyTypes.keySet()) {
            List<String> where = elsewhere.get(type);
            if (where == null || where.isEmpty() || own.isEmpty()) {
                continue;
            }
            float weight = config.modBodyTypes.get(type);
            String listed = where.size() > 8 ? where.subList(0, 8) + " ..." : where.toString();
            ProbeLog.emit("campaign-layout", weight > 0 ? ProbeLog.STATUS_WARN : ProbeLog.STATUS_FAIL, "type:" + type,
                    "in " + where.size() + " system(s) the mod did not create" + (weight > 0 ? " (procgen weight " + weight + ")" : " (no procgen weight: should not happen)") + ": " + listed);
            if (weight <= 0) {
                leaked++;
            }
        }
        ProbeLog.emit("campaign-layout", missing + leaked == 0 ? ProbeLog.STATUS_OK : ProbeLog.STATUS_FAIL, "mod-systems",
                "systems expected=" + config.modSystems.size() + " missing=" + missing + "; mod body types=" + config.modBodyTypes.size()
                        + " counts=" + total);
    }

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
