package cn.xxt.dismissal.poc;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

/** Pulls test-only settings from this Mac. Production will use the platform URL. */
final class DeviceConfigClient {
    private final SharedPreferences prefs;

    DeviceConfigClient(Context context) {
        prefs = context.getSharedPreferences("platform_config_cache", Context.MODE_PRIVATE);
    }

    DeviceConfig cached() {
        try {
            String raw = prefs.getString("data", "");
            return raw.isEmpty() ? null : new DeviceConfig(new JSONObject(raw));
        } catch (Exception ignored) {
            return null;
        }
    }

    DeviceConfig fetch() throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL(
                BuildConfig.TEST_PLATFORM_URL + "/api/device-config").openConnection();
        try {
            connection.setConnectTimeout(4000);
            connection.setReadTimeout(4000);
            if (connection.getResponseCode() != 200) {
                throw new IllegalStateException("平台配置 HTTP " + connection.getResponseCode());
            }
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            try (InputStream input = connection.getInputStream()) {
                byte[] buffer = new byte[2048];
                int count;
                while ((count = input.read(buffer)) != -1) {
                    bytes.write(buffer, 0, count);
                    if (bytes.size() > 16384) throw new IllegalStateException("平台配置过大");
                }
            }
            JSONObject response = new JSONObject(new String(bytes.toByteArray(),
                    StandardCharsets.UTF_8));
            if (response.optInt("code") != 200 || response.optJSONObject("data") == null) {
                throw new IllegalStateException("平台配置格式错误");
            }
            JSONObject data = response.getJSONObject("data");
            DeviceConfig parsed = new DeviceConfig(data);
            if (!prefs.edit().putString("data", data.toString())
                    .putLong("fetchedAt", System.currentTimeMillis()).commit()) {
                throw new IllegalStateException("平台配置缓存失败");
            }
            return parsed;
        } finally {
            connection.disconnect();
        }
    }

    void reportLed(boolean success, String stage, String message, DeviceConfig config) {
        if (BuildConfig.DEVICE_REPORT_TOKEN.isEmpty()) return;
        HttpURLConnection connection = null;
        try {
            JSONObject data = new JSONObject();
            data.put("success", success);
            data.put("stage", stage);
            data.put("message", message);
            data.put("appVersion", BuildConfig.VERSION_NAME);
            data.put("configVersion", config.version);
            data.put("controller", config.ledIp + ":" + config.ledPort);
            byte[] body = data.toString().getBytes(StandardCharsets.UTF_8);
            connection = (HttpURLConnection) new URL(
                    BuildConfig.TEST_PLATFORM_URL + "/api/led-diagnostic").openConnection();
            connection.setRequestMethod("POST");
            connection.setConnectTimeout(2500);
            connection.setReadTimeout(2500);
            connection.setDoOutput(true);
            connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
            connection.setRequestProperty("X-Device-Token", BuildConfig.DEVICE_REPORT_TOKEN);
            connection.setFixedLengthStreamingMode(body.length);
            try (OutputStream output = connection.getOutputStream()) {
                output.write(body);
            }
            if (connection.getResponseCode() != 200) {
                android.util.Log.w("DismissalLed", "诊断回传 HTTP " + connection.getResponseCode());
            }
        } catch (Exception error) {
            android.util.Log.w("DismissalLed", "诊断回传失败", error);
        } finally {
            if (connection != null) connection.disconnect();
        }
    }
}
