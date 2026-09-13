package com.bridgeforge.probe;

import com.fs.starfarer.api.Global;
import org.json.JSONException;
import org.json.JSONObject;

/**
 * Emits every probe result BOTH as a {@code BF-PROBE|...} log line and as a
 * JSON line appended to the {@code bf_probe_report} common file, so
 * {@code log-triage} (parsing starsector.log) and BridgeForge's own report
 * reader (parsing the common file directly) see the same facts.
 *
 * Format: {@code BF-PROBE|<version>|<check>|<status>|<subject>|<detail>}
 * where status is one of OK / FAIL / WARN / INFO.
 */
public final class ProbeLog {

    public static final String VERSION = "0.2.1";

    public static final String STATUS_OK = "OK";
    public static final String STATUS_FAIL = "FAIL";
    public static final String STATUS_WARN = "WARN";
    public static final String STATUS_INFO = "INFO";

    private ProbeLog() {
    }

    public static void emit(String check, String status, String subject, String detail) {
        String safeSubject = subject == null ? "" : subject.replace("|", "/");
        String safeDetail = detail == null ? "" : detail.replace("|", "/").replace("\n", " ");
        String line = "BF-PROBE|" + VERSION + "|" + check + "|" + status + "|" + safeSubject + "|" + safeDetail;
        try {
            Global.getLogger(ProbeLog.class).info(line);
        } catch (Throwable t) {
            // Logging must never be allowed to crash the probe itself.
        }
        appendReport(check, status, safeSubject, safeDetail);
    }

    public static void start(String label) {
        emit("probe", STATUS_INFO, label, "START");
    }

    public static void end(String label) {
        emit("probe", STATUS_INFO, label, "END");
    }

    private static void appendReport(String check, String status, String subject, String detail) {
        try {
            JSONObject entry = new JSONObject();
            entry.put("version", VERSION);
            entry.put("check", check);
            entry.put("status", status);
            entry.put("subject", subject);
            entry.put("detail", detail);
            entry.put("timestampMillis", System.currentTimeMillis());
            String existing = "";
            if (Global.getSettings().fileExistsInCommon(ProbeFiles.REPORT)) {
                try {
                    existing = Global.getSettings().readTextFileFromCommon(ProbeFiles.REPORT);
                } catch (java.io.IOException readFailure) {
                    existing = "";
                }
            }
            String updated = existing + entry.toString() + "\n";
            Global.getSettings().writeTextFileToCommon(ProbeFiles.REPORT, updated);
        } catch (JSONException | java.io.IOException reportFailure) {
            try {
                Global.getLogger(ProbeLog.class).warn("BF-PROBE report append failed: " + reportFailure);
            } catch (Throwable ignored) {
                // Nothing further we can do.
            }
        }
    }
}
