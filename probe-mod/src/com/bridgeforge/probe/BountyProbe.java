package com.bridgeforge.probe;

import com.fs.starfarer.api.Global;
import com.fs.starfarer.api.campaign.CampaignFleetAPI;
import com.fs.starfarer.api.fleet.FleetMemberAPI;
import org.json.JSONArray;
import org.json.JSONObject;

import java.lang.reflect.Method;
import java.util.List;
import java.util.Map;

/**
 * Probe 0.3.2: spawn each MagicLib bounty a mod defines and confirm its fleet (EPTA's Artifact 667, 2026-10-22). Its faction,
 * narcepolis, knows one hull that has no fleet role, so the generic patrol check reports an empty patrol; the bounty fleet is
 * the faction's real use and was never exercised. Config {@code bounty_checks: {modId: [bountyId, ...]}} (written by
 * BridgeForge from the mod's data/config/modFiles/magicBounty_data.json). Per bounty logs
 * {@code BF-PROBE|ver|bounty|OK|<mod>/<id>|faction=.. flagship=.. presets=n/expected members=n fp=n minFp=n}, FAIL when no
 * fleet is created, the faction differs from the spec or the spec's flagship is missing. The fleet is despawned and the
 * bounty reset afterwards.
 *
 * MagicLib is called by reflection through the script class loader so the probe keeps no compile dependency on it. API
 * (javap, MagicLib 1.5.7 in the rig, 2026-10-22): MagicBountyLoader.getBountyData(String) -> MagicBountySpec (public fields
 * fleet_faction, fleet_flagship_variant, fleet_preset_ships Map<String,Integer>, fleet_min_FP);
 * MagicBountyCoordinator.getInstance().createActiveBounty(String, MagicBountySpec) -> ActiveBounty; resetBounty(String);
 * ActiveBounty.getFleet() -> CampaignFleetAPI, getPresetShipsInFleet() -> List. RC8 (javap starfarer.api.jar):
 * SettingsAPI.getScriptClassLoader(), CampaignFleetAPI.getFlagship/getFleetPoints/despawn/getFaction,
 * FleetMemberAPI.getVariant().getHullVariantId().
 */
public final class BountyProbe {

    private static final String LOADER = "org.magiclib.bounty.MagicBountyLoader";
    private static final String COORDINATOR = "org.magiclib.bounty.MagicBountyCoordinator";
    private static final String SPEC = "org.magiclib.bounty.MagicBountySpec";

    private BountyProbe() {
    }

    public static void run() throws Exception {
        if (!Global.getSettings().fileExistsInCommon(ProbeFiles.CONFIG)) {
            return;
        }
        JSONObject root = new JSONObject(Global.getSettings().readTextFileFromCommon(ProbeFiles.CONFIG));
        JSONObject checks = root.optJSONObject("bounty_checks");
        if (checks == null || checks.names() == null) {
            return;
        }
        ClassLoader loader = Global.getSettings().getScriptClassLoader();
        Class<?> loaderClass;
        Class<?> coordinatorClass;
        Class<?> specClass;
        try {
            loaderClass = loader.loadClass(LOADER);
            coordinatorClass = loader.loadClass(COORDINATOR);
            specClass = loader.loadClass(SPEC);
        } catch (ClassNotFoundException e) {
            ProbeLog.emit("bounty", ProbeLog.STATUS_INFO, "magiclib", "MagicLib bounty classes not loaded; bounty checks skipped");
            return;
        }
        Object coordinator = coordinatorClass.getMethod("getInstance").invoke(null);
        Method getData = loaderClass.getMethod("getBountyData", String.class);
        Method create = coordinatorClass.getMethod("createActiveBounty", String.class, specClass);
        Method reset = coordinatorClass.getMethod("resetBounty", String.class);
        JSONArray mods = checks.names();
        for (int i = 0; i < mods.length(); i++) {
            String modId = mods.getString(i);
            JSONArray ids = checks.optJSONArray(modId);
            for (int j = 0; ids != null && j < ids.length(); j++) {
                String id = ids.getString(j);
                try {
                    check(modId, id, getData.invoke(null, id), coordinator, create, reset);
                } catch (Throwable t) {
                    Throwable cause = t.getCause() != null ? t.getCause() : t;
                    ProbeLog.emit("bounty", ProbeLog.STATUS_FAIL, modId + "/" + id, cause.getClass().getSimpleName() + ": " + cause.getMessage());
                }
            }
        }
    }

    private static void check(String modId, String id, Object spec, Object coordinator, Method create, Method reset) throws Exception {
        String subject = modId + "/" + id;
        if (spec == null) {
            ProbeLog.emit("bounty", ProbeLog.STATUS_FAIL, subject, "MagicLib has no bounty data for this id (not loaded)");
            return;
        }
        String faction = (String) spec.getClass().getField("fleet_faction").get(spec);
        String flagshipVariant = (String) spec.getClass().getField("fleet_flagship_variant").get(spec);
        Map<?, ?> presets = (Map<?, ?>) spec.getClass().getField("fleet_preset_ships").get(spec);
        int minFp = spec.getClass().getField("fleet_min_FP").getInt(spec);
        int expectedPresets = 0;
        if (presets != null) {
            for (Object count : presets.values()) {
                expectedPresets += count instanceof Number ? ((Number) count).intValue() : 0;
            }
        }
        Object active = create.invoke(coordinator, id, spec);
        CampaignFleetAPI fleet = active == null ? null : (CampaignFleetAPI) active.getClass().getMethod("getFleet").invoke(active);
        if (fleet == null) {
            ProbeLog.emit("bounty", ProbeLog.STATUS_FAIL, subject, "createActiveBounty returned no fleet (faction=" + faction + ")");
            reset.invoke(coordinator, id);
            return;
        }
        List<?> presetMembers = (List<?>) active.getClass().getMethod("getPresetShipsInFleet").invoke(active);
        FleetMemberAPI flagship = fleet.getFlagship();
        String flagshipId = flagship == null || flagship.getVariant() == null ? "none" : flagship.getVariant().getHullVariantId();
        String fleetFaction = fleet.getFaction() == null ? "none" : fleet.getFaction().getId();
        boolean factionOk = faction == null || faction.isEmpty() || faction.equals(fleetFaction);
        boolean flagshipOk = flagshipVariant == null || flagshipVariant.isEmpty() || flagship != null;
        String detail = "faction=" + fleetFaction + " flagship=" + flagshipId
                + " presets=" + (presetMembers == null ? 0 : presetMembers.size()) + "/" + expectedPresets
                + " members=" + fleet.getFleetData().getNumMembers() + " fp=" + fleet.getFleetPoints() + " minFp=" + minFp;
        ProbeLog.emit("bounty", factionOk && flagshipOk ? ProbeLog.STATUS_OK : ProbeLog.STATUS_FAIL, subject,
                factionOk ? (flagshipOk ? detail : "flagship " + flagshipVariant + " missing; " + detail)
                        : "faction " + fleetFaction + " expected " + faction + "; " + detail);
        fleet.despawn();
        reset.invoke(coordinator, id);
    }
}
