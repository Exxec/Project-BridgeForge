package data.scripts.bfcap;

import com.fs.starfarer.api.BaseModPlugin;
import com.fs.starfarer.api.Global;

/**
 * Rig-only capacity measurement (BridgeForge ROADMAP item 57). Does nothing unless the BridgeForge rig marker exists in saves/common,
 * and runs once per new game. Loose script: compiled by the game's own Janino, so no lambdas and no generics-dependent calls.
 */
public class BfCapPlugin extends BaseModPlugin {

    static final String RIG_MARKER = "bf_probe_rig";
    static final String DONE_KEY = "$bfcap_done";

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
        Global.getSector().addTransientScript(new BfCapScript());
    }
}
