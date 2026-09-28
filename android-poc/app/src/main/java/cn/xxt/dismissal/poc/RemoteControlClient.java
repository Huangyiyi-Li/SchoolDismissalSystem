package cn.xxt.dismissal.poc;

import android.content.Context;
import android.content.SharedPreferences;
import android.util.Log;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.UUID;

/** Polls one-time test commands and durably retries small diagnostic events. */
final class RemoteControlClient {
    private static final String TAG = "DismissalRemote";
    private final PlatformEndpoint endpoint;
    private final SharedPreferences prefs;

    RemoteControlClient(Context context, PlatformEndpoint endpoint) {
        this.endpoint = endpoint;
        prefs = context.getSharedPreferences("remote_control", Context.MODE_PRIVATE);
    }

    JSONObject fetch() throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL(
                endpoint.baseUrl() + "/api/device-control").openConnection();
        try {
            connection.setConnectTimeout(4000);
            connection.setReadTimeout(4000);
            connection.setRequestProperty("X-Device-Token", endpoint.token());
            if (connection.getResponseCode() != 200) {
                throw new IllegalStateException("远程控制 HTTP " + connection.getResponseCode());
            }
            JSONObject result = new JSONObject(readLimited(connection.getInputStream(), 16384));
            if (result.optInt("code") != 200 || result.optJSONObject("data") == null) {
                throw new IllegalStateException("远程控制返回格式错误");
            }
            return result.getJSONObject("data");
        } finally {
            connection.disconnect();
        }
    }

    boolean alreadyExecuted(String commandId) {
        return commandId.equals(prefs.getString("lastCommandId", ""));
    }

    void clearForNewPlatform() {
        prefs.edit().clear().commit();
    }

    void report(String type, boolean success, String message, DeviceConfig config) {
        enqueue(type, success, message, config, null);
    }

    void reportCommand(String type, boolean success, String message,
                       DeviceConfig config, String commandId) {
        enqueue(type, success, message, config, commandId);
    }

    private void enqueue(String type, boolean success, String message,
                         DeviceConfig config, String commandId) {
        try {
            JSONObject event = new JSONObject();
            event.put("eventId", UUID.randomUUID().toString().replace("-", ""));
            event.put("type", type);
            event.put("success", success);
            event.put("message", message == null ? "" : message.substring(0, Math.min(500, message.length())));
            event.put("appVersion", BuildConfig.VERSION_NAME);
            event.put("versionCode", BuildConfig.VERSION_CODE);
            event.put("configVersion", config == null ? 0 : config.version);
            event.put("controller", config == null ? "" : config.ledIp + ":" + config.ledPort);
            event.put("commandId", commandId == null ? JSONObject.NULL : commandId);
            JSONArray old = pending();
            JSONArray next = new JSONArray();
            for (int i = Math.max(0, old.length() - 99); i < old.length(); i++) {
                next.put(old.getJSONObject(i));
            }
            next.put(event);
            SharedPreferences.Editor edit = prefs.edit().putString("pendingEvents", next.toString());
            if (commandId != null) edit.putString("lastCommandId", commandId);
            if (!edit.commit()) throw new IllegalStateException("诊断结果缓存失败");
            flushPending();
        } catch (Exception error) {
            Log.w(TAG, "诊断回传暂未完成", error);
        }
    }

    void flushPending() throws Exception {
        JSONArray queue = pending();
        for (int index = 0; index < queue.length(); index++) {
            JSONObject event = queue.getJSONObject(index);
            post(event);
            JSONArray remaining = new JSONArray();
            for (int later = index + 1; later < queue.length(); later++) {
                remaining.put(queue.getJSONObject(later));
            }
            if (!prefs.edit().putString("pendingEvents", remaining.toString()).commit()) {
                throw new IllegalStateException("诊断回传队列更新失败");
            }
            queue = remaining;
            index = -1;
        }
    }

    private JSONArray pending() throws Exception {
        return new JSONArray(prefs.getString("pendingEvents", "[]"));
    }

    private void post(JSONObject event) throws Exception {
        byte[] body = event.toString().getBytes(StandardCharsets.UTF_8);
        HttpURLConnection connection = (HttpURLConnection) new URL(
                endpoint.baseUrl() + "/api/device-events").openConnection();
        try {
            connection.setRequestMethod("POST");
            connection.setConnectTimeout(4000);
            connection.setReadTimeout(4000);
            connection.setDoOutput(true);
            connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
            connection.setRequestProperty("X-Device-Token", endpoint.token());
            connection.setFixedLengthStreamingMode(body.length);
            try (OutputStream output = connection.getOutputStream()) {
                output.write(body);
            }
            if (connection.getResponseCode() != 200) {
                throw new IllegalStateException("诊断回传 HTTP " + connection.getResponseCode());
            }
        } finally {
            connection.disconnect();
        }
    }

    private static String readLimited(InputStream input, int limit) throws Exception {
        try (InputStream stream = input; ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[2048];
            int count;
            while ((count = stream.read(buffer)) != -1) {
                output.write(buffer, 0, count);
                if (output.size() > limit) throw new IllegalStateException("平台返回数据过大");
            }
            return new String(output.toByteArray(), StandardCharsets.UTF_8);
        }
    }
}
