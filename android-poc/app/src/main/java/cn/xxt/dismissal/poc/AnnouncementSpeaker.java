package cn.xxt.dismissal.poc;

import android.content.Context;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.speech.tts.TextToSpeech;
import android.speech.tts.UtteranceProgressListener;

import java.util.Locale;

/** Repeats the fixed dismissal announcement using server-supplied playback settings. */
final class AnnouncementSpeaker {
    interface Listener { void onStatus(String status); }

    private final Handler handler = new Handler(Looper.getMainLooper());
    private TextToSpeech tts;
    private boolean ready;
    private boolean busy;
    private int sequence;

    void start(Context context, Listener listener) {
        if (tts != null) return;
        tts = new TextToSpeech(context.getApplicationContext(), code -> {
            if (code != TextToSpeech.SUCCESS || tts == null) {
                listener.onStatus("语音引擎启动失败，请检查中文语音引擎");
                return;
            }
            int language = tts.setLanguage(Locale.SIMPLIFIED_CHINESE);
            ready = language != TextToSpeech.LANG_MISSING_DATA
                    && language != TextToSpeech.LANG_NOT_SUPPORTED;
            listener.onStatus(ready ? "语音已就绪" : "语音引擎不支持中文");
        });
    }

    boolean isReady() { return ready; }
    boolean isBusy() { return busy; }

    void speak(String text, DeviceConfig config, Listener listener) {
        if (!ready || tts == null) {
            listener.onStatus("语音未就绪，未播放");
            return;
        }
        stop();
        busy = true;
        int current = sequence;
        tts.setSpeechRate(config.voiceSpeed);
        play(text, config, listener, current, 1);
    }

    private void play(String text, DeviceConfig config, Listener listener,
                      int current, int number) {
        if (tts == null || current != sequence) return;
        String utteranceId = "dismissal-" + current + "-" + number;
        tts.setOnUtteranceProgressListener(new UtteranceProgressListener() {
            @Override public void onStart(String id) {
                if (utteranceId.equals(id)) handler.post(() -> listener.onStatus(
                        "正在播报 " + number + "/" + config.voiceRepeatCount + "：" + text));
            }
            @Override public void onDone(String id) {
                if (!utteranceId.equals(id)) return;
                handler.postDelayed(() -> {
                    if (current != sequence) return;
                    if (number < config.voiceRepeatCount) {
                        play(text, config, listener, current, number + 1);
                    } else {
                        busy = false;
                        listener.onStatus("播报完成：" + text);
                    }
                }, number < config.voiceRepeatCount
                        ? config.voiceRepeatIntervalSeconds * 1000L : 0);
            }
            @Override public void onError(String id) {
                if (utteranceId.equals(id)) handler.post(() -> {
                    busy = false;
                    listener.onStatus("播报失败");
                });
            }
        });
        Bundle options = new Bundle();
        options.putFloat(TextToSpeech.Engine.KEY_PARAM_VOLUME,
                config.voiceVolumePercent / 100f);
        if (tts.speak(text, TextToSpeech.QUEUE_FLUSH, options, utteranceId)
                != TextToSpeech.SUCCESS) {
            listener.onStatus("播报提交失败");
        }
    }

    void stop() {
        sequence++;
        busy = false;
        if (tts != null) tts.stop();
    }

    void close() {
        stop();
        ready = false;
        if (tts != null) {
            tts.shutdown();
            tts = null;
        }
    }
}
