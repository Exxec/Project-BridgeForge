package data.scripts.bfraid;

import com.fs.starfarer.api.BaseModPlugin;
import com.fs.starfarer.api.Global;

/**
 * Rig-only raid scenario (BridgeForge ROADMAP item 73, G6). Does nothing unless the BridgeForge rig marker exists in saves/common, and
 * starts its script once per game. Loose script: compiled by the game's own Janino, so no lambdas and no generics-dependent calls.
 */
public class BfRaidPlugin extends BaseModPlugin {

    static final String RIG_MARKER = "bf_probe_rig";
    static final String DONE_KEY = "$bfraid_done";

    public void onGameLoad(boolean newGame) {
        boolean rig;
        try {
            rig = Global.getSettings().fileExistsInCommon(RIG_MARKER);
        } catch (Throwable t) {
            rig = false;
        }
        if (!rig || Global.getSector().getMemoryWithoutUpdate().getBoolean(DONE_KEY)) {
            return;
        }
        Global.getSector().addTransientScript(new BfRaidScript());
    }
}
