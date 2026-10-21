package com.bridgeforge.probe;

import com.fs.starfarer.api.EveryFrameScript;
import com.fs.starfarer.api.Global;
import com.fs.starfarer.api.campaign.CampaignClockAPI;
import com.fs.starfarer.api.campaign.CampaignFleetAPI;
import com.fs.starfarer.api.fleet.FleetMemberAPI;
import com.fs.starfarer.api.fleet.FleetMemberStatusAPI;
import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

/**
 * Executes the declarative steps of a per-mod PROBE_SCENARIO.json (written into {@code bf_probe_config} as
 * {@code scenario_steps} by BridgeForge's probe_scenario module; see docs/PROBE_SCENARIOS.md).
 *
 * The step set is closed and every step uses the public API only (javap-verified against RC8's starfarer.api.jar,
 * 2026-10-20): advance_days (waits on CampaignClockAPI.getElapsedDaysSince), damage_player_module and
 * destroy_player_module (FleetMemberStatusAPI.setHullFraction(int,float) / setDetached / setPermaDetached on the player
 * fleet's members), log_player_modules (FleetMemberStatusAPI.getHullFraction(int) / isDetached / isPermaDetached /
 * getNumStatuses / getArmorDamageTaken). Each step logs
 * {@code BF-PROBE|<ver>|scenario|<status>|step=<name>|result=...}. It also logs one {@code clock|day=N} line per elapsed
 * in-game day since it started, which is how BridgeForge's expectation evaluator measures {@code within_days}.
 *
 * It is a separate transient script so it never disturbs CampaignProbeScript. After a save and reload the mutating
 * steps are NOT repeated (a sector memory flag records the first run); only log_player_modules runs again, so a
 * before/after comparison is possible.
 */
public class ScenarioRunner implements EveryFrameScript {

    private static final String DONE_FLAG = "$bf_probe_scenario_ran";

    private boolean done = false;
    private boolean loaded = false;
    private boolean replay = false;
    private final List<JSONObject> steps = new ArrayList<JSONObject>();
    private int index = 0;
    private boolean started = false;
    private long startTimestamp = 0L;
    private int lastClockDay = -1;
    // advance_days state
    private boolean finishedLogged = false;
    private boolean waiting = false;
    private long waitStart = 0L;

    /** Register the runner when the config asks for one. Called from BfProbeModPlugin behind RigGate. */
    public static void maybeRegister() {
        if (Global.getSector().hasTransientScript(ScenarioRunner.class)) {
            return;
        }
        Global.getSector().addTransientScript(new ScenarioRunner());
    }

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
        if (!loaded) {
            loaded = true;
            if (!load()) {
                done = true;
                return;
            }
        }
        CampaignClockAPI clock = Global.getSector().getClock();
        if (!started) {
            started = true;
            startTimestamp = clock.getTimestamp();
            replay = Global.getSector().getMemoryWithoutUpdate().getBoolean(DONE_FLAG);
            Global.getSector().getMemoryWithoutUpdate().set(DONE_FLAG, true);
            emitClock(0);
            lastClockDay = 0;
        }
        int day = (int) clock.getElapsedDaysSince(startTimestamp);
        if (day > lastClockDay) {
            lastClockDay = day;
            emitClock(day);
        }
        runSteps(clock);
    }

    private void emitClock(int day) {
        ProbeLog.emit("scenario", ProbeLog.STATUS_INFO, "clock", "day=" + day + (replay ? " replay=true" : ""));
    }

    private boolean load() {
        try {
            if (!Global.getSettings().fileExistsInCommon(ProbeFiles.CONFIG)) {
                return false;
            }
            JSONObject root = new JSONObject(Global.getSettings().readTextFileFromCommon(ProbeFiles.CONFIG));
            JSONArray array = root.optJSONArray("scenario_steps");
            if (array != null) {
                for (int i = 0; i < array.length(); i++) {
                    steps.add(array.getJSONObject(i));
                }
            }
            // A scenario with no steps still runs the clock lines (scenario_clock) for within_days expectations.
            return array != null || root.optBoolean("scenario_clock", false);
        } catch (Throwable t) {
            ProbeLog.emit("scenario", ProbeLog.STATUS_WARN, "load", "result=error " + t);
            return false;
        }
    }

    private void runSteps(CampaignClockAPI clock) {
        while (index < steps.size()) {
            JSONObject step = steps.get(index);
            String name = step.optString("step", "");
            if ("advance_days".equals(name)) {
                if (!waiting) {
                    waiting = true;
                    waitStart = clock.getTimestamp();
                    ProbeLog.emit("scenario", ProbeLog.STATUS_INFO, "step=" + name,
                            "result=waiting days=" + step.optDouble("days", 0.0));
                }
                if (clock.getElapsedDaysSince(waitStart) < step.optDouble("days", 0.0)) {
                    return;
                }
                waiting = false;
                ProbeLog.emit("scenario", ProbeLog.STATUS_INFO, "step=" + name, "result=done");
                index++;
                continue;
            }
            runOne(name, step);
            index++;
        }
        // The script stays alive after the last step: its clock lines are what within_days expectations measure by.
        if (!finishedLogged) {
            finishedLogged = true;
            ProbeLog.emit("scenario", ProbeLog.STATUS_INFO, "steps", "result=finished count=" + steps.size());
        }
    }

    private void runOne(String name, JSONObject step) {
        String label = "step=" + name;
        boolean readOnly = "log_player_modules".equals(name);
        if (replay && !readOnly) {
            ProbeLog.emit("scenario", ProbeLog.STATUS_INFO, label, "result=skipped-after-reload");
            return;
        }
        try {
            if ("damage_player_module".equals(name)) {
                String result = changeModule(step, false);
                ProbeLog.emit("scenario", ProbeLog.STATUS_INFO, label, result);
            } else if ("destroy_player_module".equals(name)) {
                String result = changeModule(step, true);
                ProbeLog.emit("scenario", ProbeLog.STATUS_INFO, label, result);
            } else if ("log_player_modules".equals(name)) {
                logModules(step.optString("member_hull_id", ""));
            } else {
                ProbeLog.emit("scenario", ProbeLog.STATUS_WARN, label, "result=unknown-step");
            }
        } catch (Throwable t) {
            ProbeLog.emit("scenario", ProbeLog.STATUS_WARN, label, "result=error " + t);
        }
    }

    private static List<FleetMemberAPI> playerMembers(String hullId) {
        List<FleetMemberAPI> found = new ArrayList<FleetMemberAPI>();
        CampaignFleetAPI fleet = Global.getSector().getPlayerFleet();
        if (fleet == null) {
            return found;
        }
        for (FleetMemberAPI member : fleet.getFleetData().getMembersListCopy()) {
            if (hullId.length() == 0 || hullId.equals(member.getHullId())) {
                found.add(member);
            }
        }
        return found;
    }

    /** Index 0 of FleetMemberStatusAPI is the hull itself; modules start at 1 (the loader refuses module_index below 1). */
    private static String changeModule(JSONObject step, boolean destroy) {
        String hullId = step.optString("member_hull_id", "");
        int moduleIndex = step.optInt("module_index", -1);
        List<FleetMemberAPI> members = playerMembers(hullId);
        if (members.isEmpty()) {
            return "result=no-member hull=" + hullId;
        }
        StringBuilder result = new StringBuilder("result=ok");
        for (FleetMemberAPI member : members) {
            FleetMemberStatusAPI status = member.getStatus();
            if (moduleIndex < 1 || moduleIndex >= status.getNumStatuses()) {
                result.append(" hull=").append(hullId).append(" module=").append(moduleIndex)
                        .append(" out-of-range numStatuses=").append(status.getNumStatuses());
                continue;
            }
            if (destroy) {
                status.setHullFraction(moduleIndex, 0f);
                status.setDetached(moduleIndex, Boolean.TRUE);
                status.setPermaDetached(moduleIndex, Boolean.TRUE);
            } else {
                status.setHullFraction(moduleIndex, (float) step.optDouble("hull_fraction", 1.0));
            }
            result.append(" hull=").append(hullId).append(" module=").append(moduleIndex)
                    .append(" hullFraction=").append(status.getHullFraction(moduleIndex))
                    .append(" detached=").append(status.isDetached(moduleIndex))
                    .append(" permaDetached=").append(status.isPermaDetached(moduleIndex));
        }
        return result.toString();
    }

    private static void logModules(String hullId) {
        List<FleetMemberAPI> members = playerMembers(hullId);
        ProbeLog.emit("scenario", ProbeLog.STATUS_INFO, "step=log_player_modules",
                "result=members count=" + members.size() + " hull=" + hullId);
        for (FleetMemberAPI member : members) {
            FleetMemberStatusAPI status = member.getStatus();
            int count = status.getNumStatuses();
            for (int i = 0; i < count; i++) {
                ProbeLog.emit("scenario", ProbeLog.STATUS_INFO, "step=log_player_modules",
                        "result=module hull=" + member.getHullId() + " index=" + i
                        + " hullFraction=" + status.getHullFraction(i)
                        + " detached=" + status.isDetached(i)
                        + " permaDetached=" + status.isPermaDetached(i)
                        + " armorDamageTaken=" + status.getArmorDamageTaken());
            }
        }
    }
}
