package cn.xxt.dismissal.poc;

import org.json.JSONObject;

/** Read-only snapshot downloaded from the platform. */
final class DeviceConfig {
    final int version;
    final String schoolId;
    final boolean dismissalEnabled;
    final boolean testMode;
    final float voiceSpeed;
    final int voiceVolumePercent;
    final int voiceRepeatCount;
    final int voiceRepeatIntervalSeconds;
    final boolean ledEnabled;
    final String ledIp;
    final int ledPort;
    final LedStyle ledStyle;

    DeviceConfig(JSONObject data) {
        version = data.optInt("version", 0);
        schoolId = data.optString("schoolId", "");
        dismissalEnabled = data.optBoolean("dismissalEnabled", false);
        testMode = data.optBoolean("testMode", false);
        JSONObject voice = data.optJSONObject("voice");
        JSONObject led = data.optJSONObject("led");
        if (version < 1 || !schoolId.matches("[0-9]+") || voice == null || led == null) {
            throw new IllegalArgumentException("平台配置缺少必要字段");
        }
        voiceSpeed = (float) voice.optDouble("speed", 1.0);
        voiceVolumePercent = voice.optInt("volumePercent", 80);
        voiceRepeatCount = voice.optInt("repeatCount", 1);
        voiceRepeatIntervalSeconds = voice.optInt("repeatIntervalSeconds", 0);
        if (voiceSpeed < 0.5f || voiceSpeed > 2f || voiceVolumePercent < 0
                || voiceVolumePercent > 100 || voiceRepeatCount < 1
                || voiceRepeatCount > 10 || voiceRepeatIntervalSeconds < 0
                || voiceRepeatIntervalSeconds > 30) {
            throw new IllegalArgumentException("平台语音配置超出范围");
        }
        ledEnabled = led.optBoolean("enabled", false);
        ledIp = led.optString("controllerIp", "").trim();
        ledPort = led.optInt("controllerPort", 5005);
        ledStyle = new LedStyle(led.optString("schoolTitle", "放学信息"),
                led.optInt("width", 1024), led.optInt("height", 96),
                led.optInt("gradesPerPage", 2), led.optInt("pageSeconds", 8),
                led.optInt("textSize", 20));
        if (ledPort < 1 || ledPort > 65535 || (ledEnabled && ledIp.isEmpty())) {
            throw new IllegalArgumentException("平台 LED 配置无效");
        }
    }
}
