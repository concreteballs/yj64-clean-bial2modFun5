package org.blackmirror.blackmirror;

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

public final class DiagnosticMonitorProvider extends ContentProvider {
    private static final String MONITOR_PACKAGE = "org.blackmirror.yj64monitor";
    private static final String PERMISSION =
        "org.blackmirror.blackmirror.permission.MONITOR_COMMAND";
    private static final String AUTHORITY = "org.blackmirror.blackmirror.diagnostics";
    private static final String PROTOCOL = "yj64.monitor-command.v1";
    private static final int MAX_BYTES = 16 * 1024;
    private static final Set<String> COMMANDS = new HashSet<>(Arrays.asList(
        "get_status", "request_report_flush", "request_diagnostic_snapshot"
    ));
    private static final Set<String> TOP_KEYS = new HashSet<>(Arrays.asList(
        "protocol", "request_id", "command", "created_ms", "args"
    ));

    @Override public boolean onCreate() { return true; }

    @Override public synchronized Bundle call(String method, String arg, Bundle extras) {
        Bundle out = new Bundle();
        String requestId = "";
        try {
            if (!"execute_command".equals(method)) throw new IllegalArgumentException("unsupported_method");
            verifyCaller();
            if (extras == null) throw new IllegalArgumentException("extras_missing");
            String raw = extras.getString("request_json");
            if (raw == null || raw.getBytes(StandardCharsets.UTF_8).length > MAX_BYTES)
                throw new IllegalArgumentException("request_missing_or_oversized");
            JSONObject request = new JSONObject(raw);
            requireExactKeys(request, TOP_KEYS);
            if (!PROTOCOL.equals(request.optString("protocol")))
                throw new IllegalArgumentException("unsupported_protocol");
            requestId = request.optString("request_id");
            if (!requestId.matches("[a-f0-9]{32}"))
                throw new IllegalArgumentException("invalid_request_id");
            String command = request.optString("command");
            if (!COMMANDS.contains(command)) throw new SecurityException("command_not_allowlisted");
            JSONObject args = request.optJSONObject("args");
            if (args == null || args.length() != 0)
                throw new IllegalArgumentException("command_arguments_not_supported");
            JSONObject result = readAck(requestId);
            if (result == null) {
                result = execute(command);
                writeAck(requestId, result);
            }
            out.putBoolean("ok", true);
            out.putString("request_id", requestId);
            out.putString("result_json", result.toString());
        } catch (Exception e) {
            out.putBoolean("ok", false);
            out.putString("request_id", requestId);
            out.putString("error", e.getClass().getSimpleName() + ": " + String.valueOf(e.getMessage()));
        }
        return out;
    }

    private void verifyCaller() throws Exception {
        if (getContext().checkCallingPermission(PERMISSION) != PackageManager.PERMISSION_GRANTED)
            throw new SecurityException("signature_permission_denied");
        int uid = Binder.getCallingUid();
        String[] packages = getContext().getPackageManager().getPackagesForUid(uid);
        if (packages == null || packages.length != 1 || !MONITOR_PACKAGE.equals(packages[0]))
            throw new SecurityException("caller_uid_package_mismatch");
        String base = signerDigest(getContext().getPackageName());
        String monitor = signerDigest(MONITOR_PACKAGE);
        if (!base.equals(monitor)) throw new SecurityException("caller_signing_certificate_mismatch");
    }

    private String signerDigest(String packageName) throws Exception {
        PackageManager pm = getContext().getPackageManager();
        PackageInfo info;
        if (Build.VERSION.SDK_INT >= 28) {
            info = pm.getPackageInfo(packageName, PackageManager.GET_SIGNING_CERTIFICATES);
        } else {
            info = pm.getPackageInfo(packageName, PackageManager.GET_SIGNATURES);
        }
        Signature[] signatures;
        if (Build.VERSION.SDK_INT >= 28) {
            SigningInfo signing = info.signingInfo;
            if (signing == null) throw new SecurityException("signing_info_missing");
            signatures = signing.getApkContentsSigners();
        } else {
            signatures = info.signatures;
        }
        if (signatures == null || signatures.length != 1)
            throw new SecurityException("unexpected_signer_count");
        byte[] digest = MessageDigest.getInstance("SHA-256").digest(signatures[0].toByteArray());
        StringBuilder hex = new StringBuilder();
        for (byte b : digest) hex.append(String.format("%02x", b & 0xff));
        return hex.toString();
    }

    private JSONObject execute(String command) throws Exception {
        File root = getContext().getFilesDir();
        File reports = new File(root, "yj64-reports/yj64-report.jsonl");
        JSONObject result = new JSONObject();
        if ("get_status".equals(command)) {
            result.put("status_available", new File(root, "diagnostic-agent-status.json").isFile());
            result.put("base_package", getContext().getPackageName());
        } else if ("request_report_flush".equals(command)) {
            if (reports.isFile()) {
                try (FileOutputStream stream = new FileOutputStream(reports, true)) {
                    stream.flush();
                    stream.getFD().sync();
                }
            }
            result.put("flushed", true);
            result.put("report_bytes", reports.isFile() ? reports.length() : 0);
        } else if ("request_diagnostic_snapshot".equals(command)) {
            long lines = 0;
            if (reports.isFile()) {
                try (BufferedReader reader = new BufferedReader(new InputStreamReader(
                        new FileInputStream(reports), StandardCharsets.UTF_8))) {
                    while (reader.readLine() != null) lines++;
                }
            }
            result.put("report_lines", lines);
            result.put("report_bytes", reports.isFile() ? reports.length() : 0);
            result.put("status_available", new File(root, "diagnostic-agent-status.json").isFile());
        } else {
            throw new SecurityException("unsupported_command");
        }
        return result;
    }

    private File ackFile() { return new File(getContext().getFilesDir(), "yj64-monitor-command-acks.json"); }

    private JSONObject readAck(String id) throws Exception {
        File file = ackFile();
        if (!file.isFile()) return null;
        JSONObject all = new JSONObject(readText(file, 256 * 1024));
        JSONObject acks = all.optJSONObject("acks");
        return acks == null ? null : acks.optJSONObject(id);
    }

    private void writeAck(String id, JSONObject result) throws Exception {
        File file = ackFile();
        JSONObject all = new JSONObject();
        if (file.isFile()) {
            try { all = new JSONObject(readText(file, 256 * 1024)); }
            catch (Exception ignored) { all = new JSONObject(); }
        }
        JSONObject acks = all.optJSONObject("acks");
        if (acks == null) acks = new JSONObject();
        acks.put(id, result);
        JSONArray ids = acks.names();
        if (ids != null && ids.length() > 500) {
            for (int i = 0; i < ids.length() - 500; i++) acks.remove(ids.getString(i));
        }
        all.put("schema", "yj64.monitor-command-acks.v1");
        all.put("acks", acks);
        File temp = new File(file.getParentFile(), file.getName() + ".tmp");
        try (FileOutputStream stream = new FileOutputStream(temp, false)) {
            stream.write(all.toString().getBytes(StandardCharsets.UTF_8));
            stream.flush();
            stream.getFD().sync();
        }
        if (!temp.renameTo(file)) {
            if (file.exists() && !file.delete()) throw new IllegalStateException("ack_replace_failed");
            if (!temp.renameTo(file)) throw new IllegalStateException("ack_replace_failed");
        }
    }

    private String readText(File file, int max) throws Exception {
        if (file.length() > max) throw new IllegalArgumentException("ack_store_oversized");
        byte[] bytes = new byte[(int) file.length()];
        try (FileInputStream in = new FileInputStream(file)) {
            int offset = 0, count;
            while (offset < bytes.length && (count = in.read(bytes, offset, bytes.length - offset)) > 0)
                offset += count;
            if (offset != bytes.length) throw new IllegalStateException("short_read");
        }
        return new String(bytes, StandardCharsets.UTF_8);
    }

    private void requireExactKeys(JSONObject object, Set<String> allowed) throws Exception {
        Iterator<String> keys = object.keys();
        while (keys.hasNext()) if (!allowed.contains(keys.next()))
            throw new IllegalArgumentException("unknown_request_field");
    }

    @Override public Cursor query(Uri uri, String[] projection, String selection, String[] args, String sort) { return null; }
    @Override public String getType(Uri uri) { return null; }
    @Override public Uri insert(Uri uri, ContentValues values) { return null; }
    @Override public int delete(Uri uri, String selection, String[] args) { return 0; }
    @Override public int update(Uri uri, ContentValues values, String selection, String[] args) { return 0; }
}