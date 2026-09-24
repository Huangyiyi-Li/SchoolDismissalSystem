package cn.xxt.dismissal.poc;

import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Rect;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Renders a monochrome grade/class/status page for preview and the Onbon SDK. */
final class LedBoardRenderer {
    private LedBoardRenderer() {}

    static int pageCount(JSONArray classes, LedStyle style) {
        int grades = grouped(classes).size();
        return Math.max(1, (grades + style.gradesPerPage - 1) / style.gradesPerPage);
    }

    static Bitmap render(JSONArray classes, DismissalBoard board, LedStyle style, int page) {
        Bitmap bitmap = Bitmap.createBitmap(style.width, style.height, Bitmap.Config.ARGB_8888);
        Canvas canvas = new Canvas(bitmap);
        canvas.drawColor(Color.BLACK);
        Paint text = new Paint(Paint.ANTI_ALIAS_FLAG);
        text.setColor(Color.WHITE);
        text.setTypeface(android.graphics.Typeface.DEFAULT_BOLD);
        float titleBand = Math.min(style.height / 3f, style.textSize + 8f);
        text.setTextSize(Math.min(style.textSize, titleBand - 4));
        canvas.drawText(style.title, 8, titleBand - 4, text);
        text.setTextSize(Math.max(10, style.textSize * 0.7f));
        String counter = (page + 1) + "/" + pageCount(classes, style);
        canvas.drawText(counter, style.width - text.measureText(counter) - 8, titleBand - 4, text);
        canvas.drawLine(0, titleBand, style.width, titleBand, text);

        List<Map.Entry<String, List<JSONObject>>> grades = new ArrayList<>(grouped(classes).entrySet());
        int start = page * style.gradesPerPage;
        if (grades.isEmpty()) {
            text.setTextSize(Math.min(style.textSize, 24));
            canvas.drawText("请先同步班级数据", 8, titleBand + 28, text);
            return bitmap;
        }
        int rows = Math.min(style.gradesPerPage, Math.max(0, grades.size() - start));
        if (rows == 0) return bitmap;
        float rowHeight = (style.height - titleBand) / rows;
        for (int rowIndex = 0; rowIndex < rows; rowIndex++) {
            Map.Entry<String, List<JSONObject>> grade = grades.get(start + rowIndex);
            float top = titleBand + rowIndex * rowHeight;
            float bottom = top + rowHeight;
            if (rowIndex > 0) canvas.drawLine(0, top, style.width, top, text);
            float gradeWidth = Math.max(64, Math.min(style.width * 0.14f, 130));
            float gradeFont = Math.min(style.textSize, rowHeight * 0.42f);
            text.setTextSize(gradeFont);
            drawFitted(canvas, text, grade.getKey(), 7, top + (rowHeight + gradeFont) / 2f,
                    gradeWidth - 12);
            canvas.drawLine(gradeWidth, top, gradeWidth, bottom, text);
            List<JSONObject> classesInGrade = grade.getValue();
            int cols = Math.max(1, classesInGrade.size());
            float cellWidth = (style.width - gradeWidth) / cols;
            for (int col = 0; col < classesInGrade.size(); col++) {
                JSONObject item = classesInGrade.get(col);
                float left = gradeWidth + col * cellWidth;
                if (col > 0) canvas.drawLine(left, top, left, bottom, text);
                String name = item.optString("displayName", item.optString("name"));
                String status = board.status(item.optString("classId"));
                float labelSize = Math.min(style.textSize, rowHeight * 0.34f);
                text.setTextSize(labelSize);
                drawFitted(canvas, text, name, left + 4, top + rowHeight * 0.43f,
                        cellWidth - 8);
                text.setTextSize(Math.min(labelSize * 0.86f, rowHeight * 0.28f));
                if (DismissalBoard.DISMISSING.equals(status)) {
                    text.setStyle(Paint.Style.FILL);
                    canvas.drawRect(new Rect((int) (left + 2), (int) (top + rowHeight * 0.52f),
                            (int) (left + cellWidth - 2), (int) (bottom - 2)), text);
                    text.setColor(Color.BLACK);
                    drawFitted(canvas, text, status, left + 5, bottom - 5, cellWidth - 10);
                    text.setColor(Color.WHITE);
                } else {
                    drawFitted(canvas, text, status, left + 5, bottom - 5, cellWidth - 10);
                }
            }
        }
        return bitmap;
    }

    private static void drawFitted(Canvas canvas, Paint paint, String value, float x, float y,
                                   float maxWidth) {
        String text = value == null ? "" : value;
        if (maxWidth <= 0) return;
        while (paint.measureText(text) > maxWidth && text.length() > 1) {
            text = text.substring(0, text.length() - 1);
        }
        canvas.drawText(text, x, y, paint);
    }

    private static LinkedHashMap<String, List<JSONObject>> grouped(JSONArray classes) {
        LinkedHashMap<String, List<JSONObject>> groups = new LinkedHashMap<>();
        for (int i = 0; i < classes.length(); i++) {
            JSONObject item = classes.optJSONObject(i);
            if (item == null) continue;
            String grade = item.optString("gradeName", "").trim();
            if (grade.isEmpty()) grade = item.optInt("type", 1) == 2 ? "社团" : "其他";
            List<JSONObject> items = groups.get(grade);
            if (items == null) {
                items = new ArrayList<>();
                groups.put(grade, items);
            }
            items.add(item);
        }
        return groups;
    }
}
