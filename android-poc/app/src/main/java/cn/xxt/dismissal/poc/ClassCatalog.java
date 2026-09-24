package cn.xxt.dismissal.poc;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

/** Read-only class-card catalog from the desktop client's get-classes-v2 API. */
final class ClassCatalog {
    private static final String ENDPOINT =
            "https://rest.xxt.cn/kq-http/school-dismissal-system/get-classes-v2";
    private static final String PREFS = "class_catalog";
    private static final String KEY_SCHOOL = "school_id";
    private static final String KEY_CARDS = "cards";
    private static final String KEY_CLASSES = "classes";
    private final SharedPreferences prefs;

    ClassCatalog(Context context) {
        prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    String schoolId() {
        return prefs.getString(KEY_SCHOOL, "");
    }

    int cardCount() {
        try {
            return new JSONObject(prefs.getString(KEY_CARDS, "{}")).length();
        } catch (Exception ignored) {
            return 0;
        }
    }

    JSONArray classes() {
        try {
            return new JSONArray(prefs.getString(KEY_CLASSES, "[]"));
        } catch (Exception ignored) {
            return new JSONArray();
        }
    }

    int sync(String schoolId) throws Exception {
        String cleanSchoolId = schoolId.trim();
        if (!cleanSchoolId.matches("[0-9]+")) {
            throw new IllegalArgumentException("请输入正确的学校编号");
        }

        HttpURLConnection connection = (HttpURLConnection) new URL(ENDPOINT).openConnection();
        try {
            connection.setRequestMethod("POST");
            connection.setConnectTimeout(10000);
            connection.setReadTimeout(10000);
            connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
            connection.setDoOutput(true);
            byte[] request = new JSONObject().put("schoolId", cleanSchoolId)
                    .toString().getBytes(StandardCharsets.UTF_8);
            try (OutputStream output = connection.getOutputStream()) {
                output.write(request);
            }
            if (connection.getResponseCode() != 200) {
                throw new IllegalStateException("班级接口返回 HTTP " + connection.getResponseCode());
            }
            byte[] response;
            try (InputStream input = connection.getInputStream()) {
                response = readAll(input);
            }
            JSONObject body = new JSONObject(new String(response, StandardCharsets.UTF_8));
            if (body.optInt("code") != 200) {
                throw new IllegalStateException("班级接口未成功：" + body.optString("message"));
            }
            JSONArray rows = body.optJSONArray("data");
            if (rows == null) {
                throw new IllegalStateException("班级接口未返回班级列表");
            }

            JSONObject cards = new JSONObject();
            JSONArray classes = new JSONArray();
            for (int i = 0; i < rows.length(); i++) {
                JSONObject row = rows.optJSONObject(i);
                if (row == null) continue;
                String name = usableName(row, "classVoiceName");
                if (name.isEmpty()) name = usableName(row, "className");
                if (name.isEmpty()) continue;
                String displayName = usableName(row, "classShowName");
                if (displayName.isEmpty()) displayName = usableName(row, "className");
                if (displayName.isEmpty()) displayName = name;
                classes.put(new JSONObject()
                        .put("classId", row.optString("classId"))
                        .put("name", name)
                        .put("displayName", displayName)
                        .put("gradeName", usableName(row, "gradeName"))
                        .put("type", row.optInt("classType", 1)));
                Object rawCards = row.opt("cardId");
                if (rawCards == null || rawCards == JSONObject.NULL) continue;
                if (rawCards instanceof JSONArray) {
                    JSONArray array = (JSONArray) rawCards;
                    for (int j = 0; j < array.length(); j++) {
                        addCard(cards, array.optString(j), row, name);
                    }
                } else {
                    for (String card : String.valueOf(rawCards).split(",")) {
                        addCard(cards, card, row, name);
                    }
                }
            }
            if (cards.length() == 0) {
                throw new IllegalStateException("未取得可用的班级卡号，原有本地数据已保留");
            }
            if (!prefs.edit().putString(KEY_SCHOOL, cleanSchoolId)
                    .putString(KEY_CARDS, cards.toString())
                    .putString(KEY_CLASSES, classes.toString()).commit()) {
                throw new IllegalStateException("班级数据保存失败");
            }
            return cards.length();
        } finally {
            connection.disconnect();
        }
    }

    String classForCard(String cardId) {
        try {
            JSONObject cards = new JSONObject(prefs.getString(KEY_CARDS, "{}"));
            JSONObject row = cards.optJSONObject(cardId);
            if (row == null) return null;
            String name = row.optString("name");
            int type = row.optInt("type", 1);
            return (type == 2 ? "社团班：" : "行政班：") + name;
        } catch (Exception ignored) {
            return null;
        }
    }

    String classIdForCard(String cardId) {
        try {
            return new JSONObject(prefs.getString(KEY_CARDS, "{}"))
                    .optJSONObject(cardId).optString("classId", "");
        } catch (Exception ignored) {
            return "";
        }
    }

    String voiceNameForCard(String cardId) {
        try {
            return new JSONObject(prefs.getString(KEY_CARDS, "{}"))
                    .optJSONObject(cardId).optString("name", "");
        } catch (Exception ignored) {
            return "";
        }
    }

    int classTypeForCard(String cardId) {
        try {
            return new JSONObject(prefs.getString(KEY_CARDS, "{}"))
                    .optJSONObject(cardId).optInt("type", 1);
        } catch (Exception ignored) {
            return 1;
        }
    }

    private static void addCard(JSONObject cards, String rawCard, JSONObject row, String name)
            throws Exception {
        String card = rawCard.trim();
        if (card.isEmpty()) return;
        JSONObject previous = cards.optJSONObject(card);
        if (previous != null && !previous.optString("classId").equals(row.optString("classId"))) {
            throw new IllegalStateException("同一张卡绑定了多个班级，已保留原有本地数据");
        }
        JSONObject value = new JSONObject()
                .put("name", name)
                .put("type", row.optInt("classType", 1))
                .put("classId", row.optString("classId"));
        cards.put(card, value);
    }

    private static String usableName(JSONObject row, String key) {
        if (row.isNull(key)) return "";
        String value = row.optString(key, "").trim();
        return "null".equalsIgnoreCase(value) ? "" : value;
    }

    private static byte[] readAll(InputStream input) throws Exception {
        java.io.ByteArrayOutputStream output = new java.io.ByteArrayOutputStream();
        byte[] buffer = new byte[4096];
        int count;
        while ((count = input.read(buffer)) != -1) {
            output.write(buffer, 0, count);
            if (output.size() > 4_000_000) {
                throw new IllegalStateException("班级数据过大");
            }
        }
        return output.toByteArray();
    }
}
