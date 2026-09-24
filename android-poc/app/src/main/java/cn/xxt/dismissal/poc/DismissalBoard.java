package cn.xxt.dismissal.poc;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONObject;

import java.time.LocalDate;

/** Local demonstration state. Never calls the production dismissal API. */
final class DismissalBoard {
    static final String WAITING = "未放学";
    static final String DISMISSING = "放学中";
    static final String FINISHED = "已放学";
    private final SharedPreferences prefs;

    DismissalBoard(Context context) {
        prefs = context.getSharedPreferences("dismissal_board", Context.MODE_PRIVATE);
    }

    String status(String classId) {
        if (!LocalDate.now().toString().equals(prefs.getString("day", ""))) return WAITING;
        return prefs.getString(classId, WAITING);
    }

    void setStatus(String classId, String status) {
        if (classId == null || classId.isEmpty()) return;
        if (!WAITING.equals(status) && !DISMISSING.equals(status) && !FINISHED.equals(status)) {
            throw new IllegalArgumentException("未知班级状态");
        }
        SharedPreferences.Editor edit = prefs.edit();
        String today = LocalDate.now().toString();
        if (!today.equals(prefs.getString("day", ""))) edit.clear();
        if (!edit.putString("day", today).putString(classId, status).commit()) {
            throw new IllegalStateException("班级状态保存失败");
        }
    }

    int count(JSONArray classes, String wanted) {
        int count = 0;
        for (int i = 0; i < classes.length(); i++) {
            JSONObject row = classes.optJSONObject(i);
            if (row != null && wanted.equals(status(row.optString("classId")))) count++;
        }
        return count;
    }
}
