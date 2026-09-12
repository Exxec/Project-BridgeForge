package com.bridgeforge.probe;

import com.fs.starfarer.api.BaseModPlugin;
import com.fs.starfarer.api.Global;

/**
 * Entry point for the BridgeForge Probe mod (roadmap P3, RC8 in-game
 * evidence tier T2).
 *
 * This is an ordinary Starsector mod using only the public, documented
 * modding API -- the same mechanism SPW's Tick Marker uses (see that mod's
 * README for the shared build recipe; small patterns ported here with
 * attribution, both projects are GPL-3.0). It is never shipped to players:
 * {@link RigGate} makes every check below a no-op unless a rig marker
 * common-file is present, so accidentally enabling this mod outside a
 * BridgeForge test rig does nothing but log one line.
 */
public class BfProbeModPlugin extends BaseModPlugin {

    @Override
    public void onGameLoad(boolean newGame) {
        maybeStartCampaignProbe("onGameLoad");
    }

    @Override
    public void onNewGameAfterTimePass() {
        maybeStartCampaignProbe("onNewGameAfterTimePass");
    }

    private void maybeStartCampaignProbe(String hook) {
        if (!RigGate.isRigEnabled()) {
            Global.getLogger(BfProbeModPlugin.class).info("BF-PROBE disabled: no rig marker");
            return;
        }
        if (Global.getSector().hasTransientScript(CampaignProbeScript.class)) {
            return;
        }
        Global.getSector().addTransientScript(new CampaignProbeScript());
    }
}
