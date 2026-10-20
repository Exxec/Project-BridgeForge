package com.bridgeforge.probe;

import com.fs.starfarer.api.EveryFrameScript;
import com.fs.starfarer.api.Global;
import com.fs.starfarer.api.campaign.CampaignFleetAPI;
import com.fs.starfarer.api.campaign.LocationAPI;
import org.json.JSONObject;

import java.util.Arrays;

/**
 * ROADMAP 77.17b (Templar Crusade plan section 4 point 4): campaign frame time under load. Each in-game day it logs
 * {@code BF-PROBE|ver|campaign-perf|INFO|day=N|frames=..,mean_ms=..,p95_ms=..,max_ms=..,fleets_here=..,fleets_busiest=..,busiest=..}.
 *
 * A frame is the wall-clock gap between two consecutive {@code advance(amount)} calls of this script ({@code System.nanoTime()};
 * {@code amount} is campaign seconds and says nothing about how long a frame took). The script does not run while the game is
 * paused, so a gap over {@link #PAUSE_GAP_MS} is a pause or a dialog and is counted in {@code gaps}, not as a frame. Days come from
 * the campaign clock like the other probe stages. Optional config {@code campaign_perf_p95_ms} (default 0 = off): a day whose p95
 * exceeds it is logged as WARN instead of INFO.
 *
 * API (javap, RC8, 2026-10-20): CampaignClockAPI.getTimestamp()/getElapsedDaysSince(long); SectorAPI.getPlayerFleet(),
 * getAllLocations(); CampaignFleetAPI.getContainingLocation(); LocationAPI.getFleets()/getId().
 */
public class CampaignPerfScript implements EveryFrameScript {

    private static final double PAUSE_GAP_MS = 2000.0;
    private static final int MAX_SAMPLES = 20000;

    private boolean started = false;
    private long startTimestamp = 0L;
    private int currentDay = 0;
    private long lastNanos = 0L;
    private double[] samples = new double[MAX_SAMPLES];
    private int sampleCount = 0;
    private int frames = 0;
    private int gaps = 0;
    private double sum = 0.0;
    private double max = 0.0;
    private double slowP95Ms = -1.0;

    @Override
    public boolean isDone() {
        return false;
    }

    @Override
    public boolean runWhilePaused() {
        return false;
    }

    @Override
    public void advance(float amount) {
        long now = System.nanoTime();
        if (slowP95Ms < 0.0) {
            slowP95Ms = loadThreshold();
        }
        if (!started) {
            started = true;
            startTimestamp = Global.getSector().getClock().getTimestamp();
            lastNanos = now;
            return;
        }
        double gapMs = (now - lastNanos) / 1.0e6;
        lastNanos = now;
        if (gapMs > PAUSE_GAP_MS) {
            gaps++;
        } else {
            record(gapMs);
        }
        int day = (int) Global.getSector().getClock().getElapsedDaysSince(startTimestamp);
        if (day > currentDay) {
            try {
                report(currentDay + 1);
            } catch (Throwable t) {
                ProbeLog.emit("campaign-perf", ProbeLog.STATUS_FAIL, "day=" + (currentDay + 1), t.getClass().getName() + ": " + t.getMessage());
            }
            currentDay = day;
            reset();
        }
    }

    private void record(double ms) {
        frames++;
        sum += ms;
        max = Math.max(max, ms);
        if (sampleCount < MAX_SAMPLES) {
            samples[sampleCount++] = ms;
        }
    }

    private void reset() {
        sampleCount = 0;
        frames = 0;
        gaps = 0;
        sum = 0.0;
        max = 0.0;
    }

    private void report(int day) {
        if (frames == 0) {
            return;
        }
        double[] sorted = Arrays.copyOf(samples, sampleCount);
        Arrays.sort(sorted);
        double p95 = sorted.length == 0 ? 0.0 : sorted[Math.min(sorted.length - 1, (int) Math.ceil(sorted.length * 0.95) - 1)];
        CampaignFleetAPI player = Global.getSector().getPlayerFleet();
        int here = player == null || player.getContainingLocation() == null ? 0 : player.getContainingLocation().getFleets().size();
        int busiest = 0;
        String busiestName = "";
        for (LocationAPI location : Global.getSector().getAllLocations()) {
            int count = location.getFleets().size();
            if (count > busiest) {
                busiest = count;
                busiestName = location.getId();
            }
        }
        boolean slow = slowP95Ms > 0.0 && p95 > slowP95Ms;
        ProbeLog.emit("campaign-perf", slow ? ProbeLog.STATUS_WARN : ProbeLog.STATUS_INFO, "day=" + day,
                "frames=" + frames + ",mean_ms=" + format(sum / frames) + ",p95_ms=" + format(p95) + ",max_ms=" + format(max)
                + ",gaps=" + gaps + ",fleets_here=" + here + ",fleets_busiest=" + busiest + ",busiest=" + busiestName);
    }

    private static String format(double value) {
        return String.format(java.util.Locale.ROOT, "%.2f", value);
    }

    /** The optional slow-day threshold from the probe config; 0 (off) when absent or unreadable. */
    private static double loadThreshold() {
        try {
            if (Global.getSettings().fileExistsInCommon(ProbeFiles.CONFIG)) {
                JSONObject root = new JSONObject(Global.getSettings().readTextFileFromCommon(ProbeFiles.CONFIG));
                return Math.max(0.0, root.optDouble("campaign_perf_p95_ms", 0.0));
            }
        } catch (Throwable t) {
            // no threshold means no WARN, never a failed run
        }
        return 0.0;
    }
}
