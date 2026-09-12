package com.bridgeforge.probe;

import java.util.ArrayList;
import java.util.List;

/**
 * Hand-parses the {@code bf_probe_profile} common file (roadmap P3c-1) into an {@code apply} mode
 * plus a {@code setups} list, mirroring {@code bridgeforge/probe_config.py}'s {@code parse_profile}
 * grammar exactly. The two are kept in parity by a shared fixture
 * (tests/test_probe_profile_parity.py on the Python side; this class's javadoc restates the same
 * rules so a change to one side is easy to notice against the other).
 *
 * Deliberately no {@code java.util.regex}, matching the "no regex-heavy code" rule for this parser,
 * and no reflection or file APIs (both forbidden by RC8's script sandbox in any case) -- this reads
 * only the {@code String} already handed to it by {@link ProbeFiles#PROFILE} via
 * {@code SettingsAPI.readTextFileFromCommon}.
 *
 * Grammar, one instruction per non-blank/non-comment line (case-insensitive keywords, extra
 * spaces tolerated):
 * <pre>
 *   apply = once-per-save | every-load
 *   rep &lt;faction&gt; = &lt;RepLevel-or-number&gt;
 *   credits = &lt;N&gt;
 *   ship &lt;variant_id&gt; [xN]
 *   spawn &lt;faction&gt; &lt;fleet_points&gt;
 *   jump &lt;star_system_name&gt;
 * </pre>
 * {@code '#'} starts a comment anywhere on the line (inline comments included). A leading
 * {@code '-'} disables a line: it is still parsed and validated for shape, but excluded from the
 * returned {@code setups}. Unlike the Python side (which fully re-validates every constructed spec
 * through {@code validate_setup_spec}), this parser only checks line *shape* -- each produced spec
 * string is handed to {@link ProbeSetup#applyOnce} / {@link ProbeSetup#applyAlways} exactly like a
 * {@code --setup} spec from {@code bf_probe_config}, which already applies its own per-spec
 * try/catch(Throwable) and logs a {@code setup} FAIL for anything it can't apply (e.g. an unknown
 * faction id or an invalid rep value) -- so semantic validation is not duplicated here.
 */
final class ProbeProfile {

    static final String APPLY_ONCE_PER_SAVE = "once-per-save";
    static final String APPLY_EVERY_LOAD = "every-load";

    String apply = APPLY_ONCE_PER_SAVE;
    final List<String> setups = new ArrayList<String>();

    private ProbeProfile() {
    }

    /**
     * Parses profileText. Returns null (after logging one
     * {@code BF-PROBE|<ver>|profile|FAIL|<line_no>|<reason>} line) on the first malformed line, so
     * a broken profile never applies a partial setups list. On success logs
     * {@code BF-PROBE|<ver>|profile|OK|<n setups>|<apply>}.
     */
    static ProbeProfile parse(String profileText) {
        ProbeProfile profile = new ProbeProfile();
        String[] lines = splitLines(profileText);
        for (int i = 0; i < lines.length; i++) {
            int lineNo = i + 1;
            String raw = lines[i];

            boolean disabled = false;
            String line = raw;
            String leftTrimmed = leftTrim(line);
            if (leftTrimmed.length() > 0 && leftTrimmed.charAt(0) == '-') {
                disabled = true;
                int consumed = line.length() - leftTrimmed.length();
                line = line.substring(0, consumed) + leftTrimmed.substring(1);
            }

            String body = stripComment(line).trim();
            if (body.length() == 0) {
                continue;
            }

            String keyword = firstToken(body).toLowerCase();
            String spec;
            if (keyword.equals("apply")) {
                String mode = parseApply(body, lineNo);
                if (mode == null) {
                    return null;
                }
                if (!disabled) {
                    profile.apply = mode;
                }
                continue;
            } else if (keyword.equals("rep")) {
                spec = parseRep(body, lineNo);
            } else if (keyword.equals("credits")) {
                spec = parseCredits(body, lineNo);
            } else if (keyword.equals("ship")) {
                spec = parseShip(body, lineNo);
            } else if (keyword.equals("spawn")) {
                spec = parseSpawn(body, lineNo);
            } else if (keyword.equals("jump")) {
                spec = parseJump(body, lineNo);
            } else {
                ProbeLog.emit("profile", ProbeLog.STATUS_FAIL, String.valueOf(lineNo),
                        "Unrecognized profile line: " + body);
                return null;
            }
            if (spec == null) {
                return null;
            }
            if (!disabled) {
                profile.setups.add(spec);
            }
        }
        ProbeLog.emit("profile", ProbeLog.STATUS_OK, String.valueOf(profile.setups.size()), profile.apply);
        return profile;
    }

    // ---- line parsers, one per grammar form ------------------------------------------------

    private static String parseApply(String body, int lineNo) {
        int eq = body.indexOf('=');
        if (eq < 0) {
            ProbeLog.emit("profile", ProbeLog.STATUS_FAIL, String.valueOf(lineNo), "Missing '=' in apply line");
            return null;
        }
        String keyword = body.substring(0, eq).trim();
        if (!keyword.equalsIgnoreCase("apply")) {
            ProbeLog.emit("profile", ProbeLog.STATUS_FAIL, String.valueOf(lineNo), "Unrecognized profile line: " + body);
            return null;
        }
        String mode = body.substring(eq + 1).trim().toLowerCase();
        if (!mode.equals(APPLY_ONCE_PER_SAVE) && !mode.equals(APPLY_EVERY_LOAD)) {
            ProbeLog.emit("profile", ProbeLog.STATUS_FAIL, String.valueOf(lineNo),
                    "Unrecognized apply mode: " + mode + "; expected once-per-save or every-load");
            return null;
        }
        return mode;
    }

    private static String parseRep(String body, int lineNo) {
        String rest = body.substring(firstToken(body).length()).trim();
        int eq = rest.indexOf('=');
        if (eq < 0) {
            ProbeLog.emit("profile", ProbeLog.STATUS_FAIL, String.valueOf(lineNo), "Missing '=' in rep line");
            return null;
        }
        String faction = rest.substring(0, eq).trim();
        String value = rest.substring(eq + 1).trim();
        if (faction.length() == 0 || value.length() == 0) {
            ProbeLog.emit("profile", ProbeLog.STATUS_FAIL, String.valueOf(lineNo),
                    "Expected 'rep <faction> = <value>'");
            return null;
        }
        return "rep:" + faction + "=" + value;
    }

    private static String parseCredits(String body, int lineNo) {
        String rest = body.substring(firstToken(body).length());
        int eq = rest.indexOf('=');
        if (eq < 0) {
            ProbeLog.emit("profile", ProbeLog.STATUS_FAIL, String.valueOf(lineNo), "Missing '=' in credits line");
            return null;
        }
        String amount = rest.substring(eq + 1).trim();
        if (amount.length() == 0) {
            ProbeLog.emit("profile", ProbeLog.STATUS_FAIL, String.valueOf(lineNo), "Missing amount in credits line");
            return null;
        }
        return "credits:" + amount;
    }

    private static String parseShip(String body, int lineNo) {
        String rest = body.substring(firstToken(body).length()).trim();
        List<String> tokens = words(rest);
        if (tokens.isEmpty()) {
            ProbeLog.emit("profile", ProbeLog.STATUS_FAIL, String.valueOf(lineNo), "Missing variant in ship line");
            return null;
        }
        if (tokens.size() == 1) {
            return "ship:" + tokens.get(0);
        }
        if (tokens.size() == 2) {
            String countToken = tokens.get(1);
            if (countToken.length() > 1
                    && (countToken.charAt(0) == 'x' || countToken.charAt(0) == 'X')
                    && isAllDigits(countToken.substring(1))) {
                return "ship:" + tokens.get(0) + ":" + countToken.substring(1);
            }
        }
        ProbeLog.emit("profile", ProbeLog.STATUS_FAIL, String.valueOf(lineNo),
                "Expected 'ship <variant> [xN]', got: " + body);
        return null;
    }

    private static String parseSpawn(String body, int lineNo) {
        String rest = body.substring(firstToken(body).length()).trim();
        List<String> tokens = words(rest);
        if (tokens.size() != 2) {
            ProbeLog.emit("profile", ProbeLog.STATUS_FAIL, String.valueOf(lineNo),
                    "Expected 'spawn <faction> <fleet_points>', got: " + body);
            return null;
        }
        return "spawn-fleet:" + tokens.get(0) + ":" + tokens.get(1);
    }

    private static String parseJump(String body, int lineNo) {
        String rest = body.substring(firstToken(body).length()).trim();
        if (rest.length() == 0) {
            ProbeLog.emit("profile", ProbeLog.STATUS_FAIL, String.valueOf(lineNo), "Missing star system in jump line");
            return null;
        }
        return "jump:" + rest;
    }

    // ---- small hand-rolled string helpers (no java.util.regex) ------------------------------

    private static String[] splitLines(String text) {
        List<String> lines = new ArrayList<String>();
        int start = 0;
        int n = text.length();
        for (int i = 0; i < n; i++) {
            if (text.charAt(i) == '\n') {
                lines.add(stripTrailingCr(text.substring(start, i)));
                start = i + 1;
            }
        }
        lines.add(stripTrailingCr(text.substring(start)));
        return lines.toArray(new String[0]);
    }

    private static String stripTrailingCr(String line) {
        if (line.endsWith("\r")) {
            return line.substring(0, line.length() - 1);
        }
        return line;
    }

    private static String leftTrim(String s) {
        int i = 0;
        while (i < s.length() && Character.isWhitespace(s.charAt(i))) {
            i++;
        }
        return s.substring(i);
    }

    private static String stripComment(String line) {
        int hashIndex = line.indexOf('#');
        return hashIndex >= 0 ? line.substring(0, hashIndex) : line;
    }

    /** The first run of non-space, non-'=' characters, i.e. the line's leading keyword. */
    private static String firstToken(String body) {
        int end = body.length();
        for (int i = 0; i < body.length(); i++) {
            char c = body.charAt(i);
            if (c == ' ' || c == '\t' || c == '=') {
                end = i;
                break;
            }
        }
        return body.substring(0, end);
    }

    private static List<String> words(String s) {
        List<String> result = new ArrayList<String>();
        int i = 0;
        int n = s.length();
        while (i < n) {
            while (i < n && Character.isWhitespace(s.charAt(i))) {
                i++;
            }
            int start = i;
            while (i < n && !Character.isWhitespace(s.charAt(i))) {
                i++;
            }
            if (i > start) {
                result.add(s.substring(start, i));
            }
        }
        return result;
    }

    private static boolean isAllDigits(String s) {
        if (s.length() == 0) {
            return false;
        }
        for (int i = 0; i < s.length(); i++) {
            if (!Character.isDigit(s.charAt(i))) {
                return false;
            }
        }
        return true;
    }
}
