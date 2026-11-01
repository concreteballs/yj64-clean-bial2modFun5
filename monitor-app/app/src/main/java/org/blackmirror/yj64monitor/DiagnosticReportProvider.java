package org.blackmirror.yj64monitor;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.Signature;
import android.content.pm.SigningInfo;
import android.database.Cursor;
import android.net.Uri;
import android.os.Binder;
import android.os.Build;
import android.os.Bundle;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Iterator;
import java.util.Set;

public final class DiagnosticReportProvider extends ContentProvider {
    private static final String BASE_PACKAGE = "org.blackmirror.blackmirror";
    private static final String PERMISSION =
        "org.blackmirror.yj64monitor.permission.RECEIVE_REPORT";
    private static final String SCHEMA = "yj64.diagnostic.v1";
    private static final int MAX_BYTES = 64 * 1024;
    private static final Set<String> TOP_KEYS = new HashSet<>(Arrays.asList(
        "schema", "agent", "event", "timestamp_ms", "report_id", "data"
    ));
    private static final Set<String> FORBIDDEN = new HashSet<>(Arrays.asList(
        "api_key", "token", "access_token", "refresh_token", "authorization",
        "private_messages", "message_content", "chat_history", "prompt"
    ));

    @Override public boolean onCreate() { return true; }

    @Override public synchronized Bundle call(String method, String arg, Bundle extras) {
        Bundle result = new Bundle();
        String reportId = "";
        try {
            if (!"receive_report".equals(method)) throw new IllegalArgumentException("unsupported_method");
            verifyCaller();
            if (extras == null) throw new IllegalArgumentException("extras_missing");
            String raw = extras.getString("report_json");
            if (raw == null || raw.getBytes(StandardCharsets.UTF_8).length > MAX_BYTES)
                throw new IllegalArgumentException("report_missing_or_oversized");
            JSONObject report = new JSONObject(raw);
            requireExactKeys(report, TOP_KEYS);
            if (!SCHEMA.equals(report.optString("schema")))
                throw new IllegalArgumentException("unsupported_schema");
            reportId = report.optString("report_id");
            if (!reportId.matches("[a-f0-9]{32}"))
                throw new IllegalArgumentException("invalid_report_id");
            if (report.optString("event").trim().isEmpty())
                throw new IllegalArgumentException("event_required");
            JSONObject data = report.optJSONObject("data");
            if (data == null) throw new IllegalArgumentException("data_must_be_object");
            validateValue(report, 0);
            File directory = new File(getContext().getFilesDir(), "yj64-reports");
            if (!directory.exists() && !directory.mkdirs())
                throw new IllegalStateException("report_directory_unavailable");
            File file = new File(directory, "yj64-report.jsonl");
            if (alreadyStored(file, reportId)) {
                result.putBoolean("ok", true);
                result.putString("report_id", reportId);
                result.putBoolean("duplicate", true);
                return result;
            }
            try (FileOutputStream out = new FileOutputStream(file, true)) {
                out.write((report.toString() + "\n").getBytes(StandardCharsets.UTF_8));
                out.flush();
                out.getFD().sync();
            }
            result.putBoolean("ok", true);
            result.putString("report_id", reportId);
            result.putBoolean("duplicate", false);
        } catch (Exception error) {
            result.putBoolean("ok", false);
            result.putString("report_id", reportId);
            result.putString("error_type", error.getClass().getSimpleName());
            result.putString("error", String.valueOf(error.getMessage()));
        }
        return result;
    }

    private void verifyCaller() throws Exception {
        if (getContext().checkCallingPermission(PERMISSION) != PackageManager.PERMISSION_GRANTED)
            throw new SecurityException("signature_permission_denied");
        int uid = Binder.getCallingUid();
        String[] packages = getContext().getPackageManager().getPackagesForUid(uid);
        if (packages == null || packages.length != 1 || !BASE_PACKAGE.equals(packages[0]))
            throw new SecurityException("caller_uid_package_mismatch");
        if (!signerDigest(getContext().getPackageName()).equals(signerDigest(BASE_PACKAGE)))
            throw new SecurityException("caller_signing_certificate_mismatch");
    }

    private String signerDigest(String packageName) throws Exception {
        PackageManager pm = getContext().getPackageManager();
        PackageInfo info = Build.VERSION.SDK_INT >= 28
            ? pm.getPackageInfo(packageName, PackageManager.GET_SIGNING_CERTIFICATES)
            : pm.getPackageInfo(packageName, PackageManager.GET_SIGNATURES);
        Signature[] signatures;
        if (Build.VERSION.SDK_INT >= 28) {
            SigningInfo signing = info.signingInfo;
            if (signing == null) throw new SecurityException("signing_info_missing");
            signatures = signing.getApkContentsSigners();
        } else signatures = info.signatures;
        if (signatures == null || signatures.length != 1)
            throw new SecurityException("unexpected_signer_count");
        byte[] digest = MessageDigest.getInstance("SHA-256").digest(signatures[0].toByteArray());
        StringBuilder hex = new StringBuilder();
        for (byte b : digest) hex.append(String.format("%02x", b & 0xff));
        return hex.toString();
    }

    private boolean alreadyStored(File file, String id) throws Exception {
        if (!file.isFile()) return false;
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(
                new FileInputStream(file), StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                try { if (id.equals(new JSONObject(line).optString("report_id"))) return true; }
                catch (Exception ignored) { }
            }
        }
        return false;
    }

    private void validateValue(Object value, int depth) throws Exception {
        if (depth > 8) throw new IllegalArgumentException("payload_depth_exceeded");
        if (value instanceof JSONObject) {
            JSONObject object = (JSONObject) value;
            Iterator<String> keys = object.keys();
            while (keys.hasNext()) {
                String key = keys.next();
                if (FORBIDDEN.contains(key.toLowerCase()))
                    throw new SecurityException("sensitive_payload_field_rejected");
                validateValue(object.get(key), depth + 1);
            }
        } else if (value instanceof JSONArray) {
            JSONArray array = (JSONArray) value;
            if (array.length() > 256) throw new IllegalArgumentException("payload_list_limit");
            for (int i = 0; i < array.length(); i++) validateValue(array.get(i), depth + 1);
        } else if (value instanceof String) {
            if (((String) value).length() > 4096)
                throw new IllegalArgumentException("payload_string_limit");
        } else if (!(value == JSONObject.NULL || value instanceof Number || value instanceof Boolean)) {
            throw new IllegalArgumentException("unsupported_payload_value");
        }
    }

    private void requireExactKeys(JSONObject object, Set<String> allowed) throws Exception {
        Iterator<String> keys = object.keys();
        while (keys.hasNext()) if (!allowed.contains(keys.next()))
            throw new IllegalArgumentException("unknown_report_field");
    }

    @Override public Cursor query(Uri uri, String[] projection, String selection, String[] args, String sort) { return null; }
    @Override public String getType(Uri uri) { return null; }
    @Override public Uri insert(Uri uri, ContentValues values) { return null; }
    @Override public int delete(Uri uri, String selection, String[] args) { return 0; }
    @Override public int update(Uri uri, ContentValues values, String selection, String[] args) { return 0; }
}
