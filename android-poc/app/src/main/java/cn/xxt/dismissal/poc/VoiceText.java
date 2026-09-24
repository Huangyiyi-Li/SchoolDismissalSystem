package cn.xxt.dismissal.poc;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Matches the Windows client's fixed “class name + 正在放学” announcement. */
final class VoiceText {
    private static final Pattern COMPACT = Pattern.compile("(\\d{1,2})\\s*[.．]\\s*(\\d{1,2})\\s*班");
    private static final String DIGITS = "零一二三四五六七八九";

    private VoiceText() {}

    static String announcement(String className) {
        String source = className == null ? "" : className.trim();
        if (source.isEmpty()) throw new IllegalArgumentException("班级名称为空");
        Matcher matcher = COMPACT.matcher(source);
        StringBuffer result = new StringBuffer();
        while (matcher.find()) {
            String replacement = chinese(Integer.parseInt(matcher.group(1))) + "年级"
                    + chinese(Integer.parseInt(matcher.group(2))) + "班";
            matcher.appendReplacement(result, Matcher.quoteReplacement(replacement));
        }
        matcher.appendTail(result);
        return result + "正在放学";
    }

    private static String chinese(int value) {
        if (value < 10) return DIGITS.substring(value, value + 1);
        int tens = value / 10;
        int ones = value % 10;
        return (tens == 1 ? "" : DIGITS.substring(tens, tens + 1)) + "十"
                + (ones == 0 ? "" : DIGITS.substring(ones, ones + 1));
    }
}
