package com.bridgeforge.probe;

import com.fs.starfarer.api.Global;

/**
 * Safety gate: the probe must never run outside a BridgeForge test rig.
 *
 * Checked via {@code SettingsAPI.fileExistsInCommon}, a presence-only test
 * against the game's saves/common folder (isolated inside each disposable
 * rig on our setup). No reflection, no direct file or NIO path access.
 */
final class RigGate {

    private RigGate() {
    }

    static boolean isRigEnabled() {
        try {
            return Global.getSettings().fileExistsInCommon(ProbeFiles.RIG_MARKER);
        } catch (Throwable t) {
            // A gate failure must default to disabled, never to enabled.
            return false;
        }
    }
}
