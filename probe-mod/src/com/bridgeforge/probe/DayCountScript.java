package com.bridgeforge.probe;

import com.fs.starfarer.api.EveryFrameScript;
import com.fs.starfarer.api.Global;

/**
 * Transient script that waits until {@code days} in-game days have passed since the campaign clock timestamp {@code start}, runs
 * its action once, and ends. Shared by {@link SaveReloadStage} (fingerprint and save) and {@link SalvorProfile} (Salvor's rig
 * stages) so the day counting lives in one place.
 */
final class DayCountScript implements EveryFrameScript {

    interface Action {
        void run() throws Exception;
    }

    private final long start;
    private final int days;
    private final Action action;
    private final String failureCheck;
    private boolean done;

    DayCountScript(long start, int days, String failureCheck, Action action) {
        this.start = start;
        this.days = days;
        this.failureCheck = failureCheck;
        this.action = action;
    }

    @Override
    public void advance(float amount) {
        if (done || Global.getSector().getClock().getElapsedDaysSince(start) < days) {
            return;
        }
        done = true;
        try {
            action.run();
        } catch (Throwable t) {
            ProbeLog.emit(failureCheck, ProbeLog.STATUS_FAIL, "day-action", "failed: " + t);
        }
    }

    @Override
    public boolean isDone() {
        return done;
    }

    @Override
    public boolean runWhilePaused() {
        return false;
    }
}
