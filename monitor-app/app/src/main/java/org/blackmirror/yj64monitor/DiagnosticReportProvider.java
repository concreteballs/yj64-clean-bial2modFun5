package org.blackmirror.yj64monitor;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.os.Binder;
import android.database.Cursor;
import android.net.Uri;
import android.os.Bundle;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

public class DiagnosticReportProvider extends ContentProvider {
    private static final String ALLOWED_CALLER = "org.blackmirror.blackmirror";
    private static final String EXPECTED_SCHEMA = "yj64.diagnostic.v1";
    private static final int MAX_REPORT_CHARS = 131072;
    private static final int MAX_ID_CHARS = 128;

    @Override public boolean onCreate() {
        return true;
    }

    @Override public Bundle call(String method, String arg, Bundle extras) {
        Bundle result = new Bundle();
        if (!"receive_report".equals(method)) {
            result.putBoolean("ok", false);
            result.putString("error", "unsupported_method");
            return result;
        }

        String reportId = "";
        try {
            enforceAllowedCaller();
            if (extras == null) throw new IllegalArgumentException("extras_missing");
            String raw = extras.getString("report_json");
            if (raw == null || raw.isEmpty() || raw.length() > MAX_REPORT_CHARS) {
                throw new IllegalArgumentException("report_missing_or_oversized");
            }

            JSONObject report = new JSONObject(raw);
            if (!EXPECTED_SCHEMA.equals(report.optString("schema", ""))) {
                throw new IllegalArgumentException("unsupported_schema");
            }
            String agent = report.optString("agent", "");
            String event = report.optString("event", "");
            long timestamp = report.optLong("timestamp_ms", 0L);
            JSONObject data = report.optJSONObject("data");
            reportId = report.optString("report_id",
                report.optString("message_id", ""));
            if (agent.isEmpty() || agent.length() > MAX_ID_CHARS
                    || event.isEmpty() || event.length() > MAX_ID_CHARS
                    || reportId.isEmpty() || reportId.length() > MAX_ID_CHARS
                    || timestamp <= 0L || data == null) {
                throw new IllegalArgumentException("invalid_report_fields");
            }

            File directory = new File(getContext().getFilesDir(), "yj64-reports");
            if (!directory.exists() && !directory.mkdirs()) {
                throw new IllegalStateException("report_directory_unavailable");
            }
            File file = new File(directory, "yj64-report.jsonl");

            // ACK retries idempotently: a report already on disk is not appended twice.
            if (containsReportId(file, reportId)) {
                result.putBoolean("ok", true);
                result.putBoolean("duplicate", true);
                result.putString("report_id", reportId);
                return result;
            }

            report.put("_external_monitor_received_at_ms", System.currentTimeMillis());
            report.put("_external_monitor_source_package", ALLOWED_CALLER);
            try (FileOutputStream out = new FileOutputStream(file, true)) {
                out.write((report.toString() + "\n").getBytes(StandardCharsets.UTF_8));
                out.flush();
                out.getFD().sync();
            }
            result.putBoolean("ok", true);
            result.putBoolean("duplicate", false);
            result.putString("report_id", reportId);
        } catch (Exception error) {
            result.putBoolean("ok", false);
            result.putString("report_id", reportId);
            result.putString("error_type", error.getClass().getSimpleName());
            result.putString("error", String.valueOf(error.getMessage()));
        }
        return result;
    }

    private void enforceAllowedCaller() {
        int callingUid = Binder.getCallingUid();
        String[] callerPackages = getContext().getPackageManager()
            .getPackagesForUid(callingUid);
        if (callerPackages == null || callerPackages.length != 1
                || !ALLOWED_CALLER.equals(callerPackages[0])) {
            throw new SecurityException("caller_package_not_allowed");
        }
    }

    private boolean containsReportId(File file, String reportId) throws Exception {
        if (!file.isFile()) return false;
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(
                new FileInputStream(file), StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                try {
                    JSONObject stored = new JSONObject(line);
                    String storedId = stored.optString("report_id",
                        stored.optString("message_id", ""));
                    if (reportId.equals(storedId)) return true;
                } catch (org.json.JSONException ignored) {
                    // Ignore a malformed historical line; continue checking later records.
                }
            }
        }
        return false;
    }

    @Override public Cursor query(Uri uri, String[] projection, String selection,
                                  String[] selectionArgs, String sortOrder) {
        return null;
    }

    @Override public String getType(Uri uri) {
        return null;
    }

    @Override public Uri insert(Uri uri, ContentValues values) {
        return null;
    }

    @Override public int delete(Uri uri, String selection, String[] selectionArgs) {
        return 0;
    }

    @Override public int update(Uri uri, ContentValues values, String selection,
                                String[] selectionArgs) {
        return 0;
    }
}
