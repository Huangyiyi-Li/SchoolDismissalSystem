package cn.xxt.dismissal.poc;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;
import java.time.LocalTime;

/** Existing Windows client's get-school-dismissal-schedule-v2 contract. */
final class ScheduleCatalog {
    private static final String ENDPOINT =
            "https://rest.xxt.cn/kq-http/school-dismissal-system/get-school-dismissal-schedule-v2";
    private final SharedPreferences prefs;

    ScheduleCatalog(Context context) {
        prefs = context.getSharedPreferences("school_schedules", Context.MODE_PRIVATE);
    }

    JSONArray cached(String schoolId) {
        if (!schoolId.equals(prefs.getString("schoolId", ""))) return new JSONArray();
        try { return new JSONArray(prefs.getString("data", "[]")); }
        catch (Exception ignored) { return new JSONArray(); }
    }

    JSONArray sync(String schoolId) throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL(ENDPOINT).openConnection();
        try {
            connection.setRequestMethod("POST");
            connection.setDoOutput(true);
            connection.setConnectTimeout(10000);
            connection.setReadTimeout(10000);
            connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
            byte[] request = new JSONObject().put("schoolId", schoolId).toString()
                    .getBytes(StandardCharsets.UTF_8);
            try (OutputStream output = connection.getOutputStream()) { output.write(request); }
            if (connection.getResponseCode() != 200) {
                throw new IllegalStateException("放学时间接口 HTTP " + connection.getResponseCode());
            }
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            try (InputStream input = connection.getInputStream()) {
                byte[] buffer = new byte[2048];
                int count;
                while ((count = input.read(buffer)) != -1) {
                    bytes.write(buffer, 0, count);
                    if (bytes.size() > 1_000_000) throw new IllegalStateException("时间数据过大");
                }
            }
            JSONObject response = new JSONObject(new String(bytes.toByteArray(),
                    StandardCharsets.UTF_8));
            if (response.optInt("code") != 200 || response.optJSONArray("data") == null) {
                throw new IllegalStateException("放学时间接口未返回列表");
            }
            JSONArray rows = response.getJSONArray("data");
            if (!prefs.edit().putString("schoolId", schoolId)
                    .putString("data", rows.toString()).commit()) {
                throw new IllegalStateException("放学时间缓存失败");
            }
            return rows;
        } finally { connection.disconnect(); }
    }

    boolean isActive(String schoolId, int classType, LocalDateTime now) {
        return activeWindowSignature(schoolId, classType, now) != null;
    }

    String activeWindowSignature(String schoolId, int classType, LocalDateTime now) {
        JSONArray groups = cached(schoolId);
        for (int i = 0; i < groups.length(); i++) {
            JSONObject group = groups.optJSONObject(i);
            if (group == null || group.optInt("classType", 1) != classType) continue;
            JSONArray rules = group.optJSONArray("schedules");
            if (rules == null) continue;
            for (int j = 0; j < rules.length(); j++) {
                JSONObject rule = rules.optJSONObject(j);
                if (rule == null || rule.optInt("weekday") != now.getDayOfWeek().getValue())
                    continue;
                JSONArray ranges = rule.optJSONArray("timeRanges");
                if (ranges == null) continue;
                for (int k = 0; k < ranges.length(); k++) {
                    JSONObject range = ranges.optJSONObject(k);
                    if (range == null) continue;
                    String start = range.optString("startTime");
                    String end = range.optString("endTime");
                    if ("00:00".equals(start) && "00:00".equals(end)) continue;
                    try {
                        LocalTime from = LocalTime.parse(start);
                        LocalTime to = LocalTime.parse(end);
                        LocalTime current = now.toLocalTime();
                        if (!current.isBefore(from) && !current.isAfter(to)) {
                            return now.toLocalDate() + ":" + classType + ":" + start + "-" + end;
                        }
                    } catch (Exception ignored) {}
                }
            }
        }
        return null;
    }
}
