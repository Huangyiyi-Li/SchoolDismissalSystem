package cn.xxt.dismissal.poc;

import org.json.JSONException;
import org.json.JSONObject;

/** LED display style received from the platform. There is no local editor. */
final class LedStyle {
    final String title;
    final int width;
    final int height;
    final int gradesPerPage;
    final int pageSeconds;
    final int textSize;

    LedStyle(String title, int width, int height, int gradesPerPage, int pageSeconds,
             int textSize) {
        if (title == null || title.trim().isEmpty() || title.length() > 20) {
            throw new IllegalArgumentException("标题需为 1–20 字");
        }
        if (width < 64 || width > 2048 || height < 32 || height > 512
                || (long) width * height > 524288) {
            throw new IllegalArgumentException("LED 分辨率超出支持范围");
        }
        if (gradesPerPage < 1 || gradesPerPage > 4 || pageSeconds < 3
                || pageSeconds > 60 || textSize < 10 || textSize > 48) {
            throw new IllegalArgumentException("每页年级 1–4、切页 3–60 秒、字号 10–48");
        }
        this.title = title.trim();
        this.width = width;
        this.height = height;
        this.gradesPerPage = gradesPerPage;
        this.pageSeconds = pageSeconds;
        this.textSize = textSize;
    }

    static LedStyle defaults() {
        return new LedStyle("放学信息", 1024, 96, 2, 8, 20);
    }

    static LedStyle fromJson(JSONObject json) {
        LedStyle fallback = defaults();
        return new LedStyle(json.optString("title", fallback.title),
                json.optInt("width", fallback.width),
                json.optInt("height", fallback.height),
                json.optInt("gradesPerPage", fallback.gradesPerPage),
                json.optInt("pageSeconds", fallback.pageSeconds),
                json.optInt("textSize", fallback.textSize));
    }

    JSONObject toJson() {
        try {
            return new JSONObject().put("title", title).put("width", width)
                    .put("height", height).put("gradesPerPage", gradesPerPage)
                    .put("pageSeconds", pageSeconds).put("textSize", textSize);
        } catch (JSONException impossible) {
            throw new IllegalStateException(impossible);
        }
    }

}
