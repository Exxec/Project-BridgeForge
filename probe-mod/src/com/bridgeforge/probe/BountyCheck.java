package com.bridgeforge.probe;

/** Probe 0.3.2: implemented by the loose script {@code data.scripts.bfprobe.MagicBountyCheck} (see {@link BountyProbe}). */
public interface BountyCheck {

    /** Spawn bounty {@code bountyId} of mod {@code modId}, log one {@code bounty} line, then remove the fleet and reset the bounty. */
    void check(String modId, String bountyId) throws Exception;
}
