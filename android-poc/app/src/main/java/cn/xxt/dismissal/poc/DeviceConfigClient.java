package cn.xxt.dismissal.poc;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

/** Pulls test-only settings from this Mac. Production will use the platform URL. */
final class DeviceConfigClient {
    private final SharedPreferences prefs;
    private final PlatformEndpoint endpoint;

    DeviceConfigClient(Context context, PlatformEndpoint endpoint) {
        prefs = context.getSharedPreferences("platform_config_cache", Context.MODE_PRIVATE);
        this.endpoint = endpoint;
    }

    DeviceConfig cached() {
        try {
            String raw = prefs.getString("data", "");
            return raw.isEmpty() ? null : new DeviceConfig(new JSONObject(raw));
        } catch (Exception ignored) {
            return null;
        }
    }

    void clearCache() {
        prefs.edit().clear().commit();
    }

    DeviceConfig fetch() throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL(
                endpoint.baseUrl() + "/api/device-config").openConnection();
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

}
