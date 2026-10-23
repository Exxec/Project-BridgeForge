package com.bridgeforge.probe;

import com.fs.starfarer.api.Global;
import com.fs.starfarer.api.campaign.CustomEntitySpecAPI;
import com.fs.starfarer.api.campaign.SectorEntityToken;
import com.fs.starfarer.api.campaign.econ.MarketAPI;
import org.json.JSONArray;
import org.json.JSONObject;

import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Probe 0.3.2: state a person would otherwise check by eye (2026-10-22: Zorg's Zeta planets no longer hidden, EPTA's
 * Proelefsi station back on its original sprite). Config {@code entity_checks: [CHECK, ...]}, from the candidate workspace's
 * PROBE_EXPECTATIONS.json:
 * <ul>
 *   <li>{@code {"entity": id, "expect": {...}}} with keys {@code discoverable}, {@code has_sensor_profile},
 *   {@code detected_range_bonuses} (number of flat bonuses), {@code market_hidden}, {@code market_size},
 *   {@code market_faction};</li>
 *   <li>{@code {"custom_entity_spec": id, "expect": {...}}} with keys {@code sprite}, {@code sprite_width},
 *   {@code sprite_height}.</li>
 * </ul>
 * Logs {@code BF-PROBE|ver|entity-state|OK|<id>|key=value ...} or FAIL listing each mismatch as key=actual (expected X).
 * Only expected keys are compared. API (javap, RC8 starfarer.api.jar, 2026-10-22): SectorAPI.getEntityById,
 * SectorEntityToken.isDiscoverable/hasSensorProfile/getDetectedRangeMod/getMarket, StatBonus.getFlatBonuses,
 * MarketAPI.isHidden/getSize/getFactionId, SettingsAPI.getCustomEntitySpec, CustomEntitySpecAPI.getSpriteName/
 * getSpriteWidth/getSpriteHeight.
 */
public final class EntityStateProbe {

    private EntityStateProbe() {
    }

    public static void run() throws Exception {
        if (!Global.getSettings().fileExistsInCommon(ProbeFiles.CONFIG)) {
            return;
        }
        JSONObject root = new JSONObject(Global.getSettings().readTextFileFromCommon(ProbeFiles.CONFIG));
        JSONArray checks = root.optJSONArray("entity_checks");
        for (int i = 0; checks != null && i < checks.length(); i++) {
            JSONObject check = checks.optJSONObject(i);
            if (check == null) {
                continue;
            }
            JSONObject expect = check.optJSONObject("expect");
            if (check.has("entity")) {
                String id = check.getString("entity");
                SectorEntityToken entity = Global.getSector().getEntityById(id);
                compare(id, entity == null ? null : entityState(entity), expect);
            } else if (check.has("custom_entity_spec")) {
                String id = check.getString("custom_entity_spec");
                CustomEntitySpecAPI spec = Global.getSettings().getCustomEntitySpec(id);
                compare("spec:" + id, spec == null ? null : specState(spec), expect);
            }
        }
    }

    private static Map<String, Object> entityState(SectorEntityToken entity) {
        Map<String, Object> state = new LinkedHashMap<String, Object>();
        state.put("discoverable", entity.isDiscoverable());
        state.put("has_sensor_profile", entity.hasSensorProfile());
        state.put("detected_range_bonuses", entity.getDetectedRangeMod().getFlatBonuses().size());
        MarketAPI market = entity.getMarket();
        state.put("market_hidden", market == null ? null : market.isHidden());
        state.put("market_size", market == null ? null : market.getSize());
        state.put("market_faction", market == null ? null : market.getFactionId());
        return state;
    }

    private static Map<String, Object> specState(CustomEntitySpecAPI spec) {
        Map<String, Object> state = new LinkedHashMap<String, Object>();
        state.put("sprite", spec.getSpriteName());
        state.put("sprite_width", (int) spec.getSpriteWidth());
        state.put("sprite_height", (int) spec.getSpriteHeight());
        return state;
    }

    private static void compare(String subject, Map<String, Object> state, JSONObject expect) {
        if (state == null) {
            ProbeLog.emit("entity-state", ProbeLog.STATUS_FAIL, subject, "not found in the running game");
            return;
        }
        StringBuilder seen = new StringBuilder();
        StringBuilder wrong = new StringBuilder();
        Iterator<?> keys = expect == null ? null : expect.keys();
        while (keys != null && keys.hasNext()) {
            String key = (String) keys.next();
            Object actual = state.get(key);
            Object wanted = expect.isNull(key) ? null : expect.opt(key);
            seen.append(' ').append(key).append('=').append(actual);
            if (!same(actual, wanted)) {
                wrong.append(' ').append(key).append('=').append(actual).append(" (expected ").append(wanted).append(')');
            }
        }
        ProbeLog.emit("entity-state", wrong.length() == 0 ? ProbeLog.STATUS_OK : ProbeLog.STATUS_FAIL, subject,
                (wrong.length() == 0 ? seen : wrong).toString().trim());
    }

    private static boolean same(Object actual, Object wanted) {
        if (actual == null || wanted == null) {
            return actual == wanted;
        }
        if (actual instanceof Number && wanted instanceof Number) {
            return ((Number) actual).doubleValue() == ((Number) wanted).doubleValue();
        }
        return actual.toString().equals(wanted.toString());
    }
}
