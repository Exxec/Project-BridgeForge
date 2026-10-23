package data.scripts.bfprobe;

import com.bridgeforge.probe.BountyCheck;
import com.bridgeforge.probe.ProbeLog;
import com.fs.starfarer.api.campaign.CampaignFleetAPI;
import com.fs.starfarer.api.fleet.FleetMemberAPI;
import java.util.Iterator;
import java.util.List;
import org.magiclib.bounty.ActiveBounty;
import org.magiclib.bounty.MagicBountyCoordinator;
import org.magiclib.bounty.MagicBountyLoader;
import org.magiclib.bounty.MagicBountySpec;

/**
 * Probe 0.3.2, loose script compiled by the game (Janino) only when MagicLib is enabled; loaded by BountyProbe. Logs
 * BF-PROBE|ver|bounty|OK|mod/id|faction=.. flagship=.. presets=n/expected members=n fp=n minFp=n, FAIL when no fleet is
 * created, the faction differs from the spec or the spec's flagship is missing. No generics: Janino compiles this file.
 * API (javap, MagicLib 1.5.7, 2026-10-22): MagicBountyLoader.getBountyData(String); MagicBountyCoordinator.getInstance(),
 * createActiveBounty(String, MagicBountySpec), resetBounty(String); ActiveBounty.getFleet(), getPresetShipsInFleet();
 * MagicBountySpec fields fleet_faction, fleet_flagship_variant, fleet_preset_ships, fleet_min_FP.
 */
public class MagicBountyCheck implements BountyCheck {

    public void check(String modId, String bountyId) {
        String subject = modId + "/" + bountyId;
        MagicBountySpec spec = MagicBountyLoader.getBountyData(bountyId);
        if (spec == null) {
            ProbeLog.emit("bounty", ProbeLog.STATUS_FAIL, subject, "MagicLib has no bounty data for this id (not loaded)");
            return;
        }
        int expectedPresets = 0;
        if (spec.fleet_preset_ships != null) {
            Iterator counts = spec.fleet_preset_ships.values().iterator();
            while (counts.hasNext()) {
                Object count = counts.next();
                if (count instanceof Integer) {
                    expectedPresets += ((Integer) count).intValue();
                }
            }
        }
        MagicBountyCoordinator coordinator = MagicBountyCoordinator.getInstance();
        ActiveBounty active = coordinator.createActiveBounty(bountyId, spec);
        CampaignFleetAPI fleet = active == null ? null : active.getFleet();
        if (fleet == null) {
            ProbeLog.emit("bounty", ProbeLog.STATUS_FAIL, subject, "createActiveBounty returned no fleet (faction=" + spec.fleet_faction + ")");
            coordinator.resetBounty(bountyId);
            return;
        }
        List presets = active.getPresetShipsInFleet();
        FleetMemberAPI flagship = fleet.getFlagship();
        String flagshipId = flagship == null || flagship.getVariant() == null ? "none" : flagship.getVariant().getHullVariantId();
        String fleetFaction = fleet.getFaction() == null ? "none" : fleet.getFaction().getId();
        boolean factionOk = spec.fleet_faction == null || spec.fleet_faction.length() == 0 || spec.fleet_faction.equals(fleetFaction);
        boolean flagshipOk = spec.fleet_flagship_variant == null || spec.fleet_flagship_variant.length() == 0 || flagship != null;
        String detail = "faction=" + fleetFaction + " flagship=" + flagshipId
                + " presets=" + (presets == null ? 0 : presets.size()) + "/" + expectedPresets
                + " members=" + fleet.getFleetData().getNumMembers() + " fp=" + fleet.getFleetPoints() + " minFp=" + spec.fleet_min_FP;
        String status = factionOk && flagshipOk ? ProbeLog.STATUS_OK : ProbeLog.STATUS_FAIL;
        String prefix = !factionOk ? "faction " + fleetFaction + " expected " + spec.fleet_faction + "; "
                : !flagshipOk ? "flagship " + spec.fleet_flagship_variant + " missing; " : "";
        ProbeLog.emit("bounty", status, subject, prefix + detail);
        fleet.despawn();
        coordinator.resetBounty(bountyId);
    }
}
