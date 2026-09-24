package cn.xxt.dismissal.poc;

import android.app.Activity;
import android.graphics.Bitmap;
import android.media.AudioManager;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.widget.Button;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.time.LocalDateTime;
import java.util.ArrayDeque;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Test client: settings come from the Mac platform; class and schedule data use live APIs. */
public final class MainActivity extends Activity {
    private static final long CONFIG_POLL_MS = 30_000;
    private static final long DATA_SYNC_MS = 10 * 60_000;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final ExecutorService io = Executors.newSingleThreadExecutor();
    private final SerialCardProbe cardProbe = new SerialCardProbe();
    private final AnnouncementSpeaker speaker = new AnnouncementSpeaker();
    private final OnbonLedClient led = new OnbonLedClient();
    private final Map<String, String> spokenWindows = new HashMap<>();
    private DeviceConfigClient configClient;
    private ClassCatalog classes;
    private ScheduleCatalog schedules;
    private DismissalBoard board;
    private volatile DeviceConfig config;
    private boolean readerRunning;
    private boolean visible;
    private long lastDataSyncAt;
    private int lastAppliedLedVersion = -1;
    private int page;
    private Bitmap currentPreview;
    private final ArrayDeque<PendingSpeech> pendingSpeech = new ArrayDeque<>();
    private PendingSpeech activeSpeech;
    private static final class PendingSpeech {
        final String text;
        final String classId;
        final String window;
        final DeviceConfig settings;
        PendingSpeech(String text, String classId, String window, DeviceConfig settings) {
            this.text = text;
            this.classId = classId;
            this.window = window;
            this.settings = settings;
        }
    }
    private TextView configStatus;
    private TextView dataStatus;
    private TextView readerStatus;
    private TextView cardStatus;
    private TextView voiceStatus;
    private TextView ledStatus;
    private TextView pageStatus;
    private ImageView preview;

    private final Runnable poll = new Runnable() {
        @Override public void run() {
            if (!visible) return;
            fetchFromPlatform(false);
            handler.postDelayed(this, CONFIG_POLL_MS);
        }
    };
    private final Runnable rotate = new Runnable() {
        @Override public void run() {
            if (!visible) return;
            DeviceConfig current = config;
            if (current != null) {
                page = (page + 1) % LedBoardRenderer.pageCount(classes.classes(), current.ledStyle);
                renderPreview();
                if (current.ledEnabled) sendLedPage(current);
                handler.postDelayed(this, current.ledStyle.pageSeconds * 1000L);
            }
        }
    };
    private final Runnable checkPending = new Runnable() {
        @Override public void run() {
            if (!visible) return;
            boolean callBusy = isCallBusy();
            if (callBusy && activeSpeech != null) {
                speaker.stop();
                pendingSpeech.addFirst(activeSpeech);
                activeSpeech = null;
                voiceStatus.setText("通话开始，已暂停播报；待通话结束后重播");
            } else if (!callBusy && !pendingSpeech.isEmpty() && !speaker.isBusy()
                    && speaker.isReady()) {
                startSpeech(pendingSpeech.removeFirst());
            }
            handler.postDelayed(this, 2000);
        }
    };

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        configClient = new DeviceConfigClient(this);
        classes = new ClassCatalog(this);
        schedules = new ScheduleCatalog(this);
        board = new DismissalBoard(this);
        config = configClient.cached();

        ScrollView scroll = new ScrollView(this);
        LinearLayout content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        int pad = (int) (20 * getResources().getDisplayMetrics().density);
        content.setPadding(pad, pad, pad, pad);
        scroll.addView(content);
        addText(content, "放学模块 · 联调版", 23);
        addText(content, "配置由 Mac 测试平台下发；班级绑卡和放学时间从现有平台读取。本页只显示状态，不修改设置或通知家长。", 14);
        configStatus = addText(content, "等待平台配置…", 17);
        dataStatus = addText(content, "等待班级与放学时间同步…", 16);
        addButton(content, "立即重新同步", v -> fetchFromPlatform(true));

        addText(content, "刷卡识别", 20);
        readerStatus = addText(content, "读卡器等待配置", 16);
        cardStatus = addText(content, "尚未刷卡", 19);
        addText(content, "语音播报", 20);
        voiceStatus = addText(content, "语音初始化中…", 16);

        addText(content, "LED 运行状态", 20);
        ledStatus = addText(content, "等待平台配置", 16);
        preview = new ImageView(this);
        preview.setAdjustViewBounds(true);
        preview.setScaleType(ImageView.ScaleType.FIT_CENTER);
        preview.setBackgroundColor(android.graphics.Color.DKGRAY);
        content.addView(preview, new LinearLayout.LayoutParams(-1, -2));
        pageStatus = addText(content, "", 14);
        addButton(content, "检查 LED 连接", v -> checkLed());
        addText(content, "话机通话、请假和留言的冲突处理尚需接入原话机应用；当前联调版只验证放学链路。", 14);
        setContentView(scroll);

        speaker.start(this, message -> runOnUiThread(() -> voiceStatus.setText(message)));
        showConfig("本机缓存，正在检查平台");
        renderPreview();
    }

    private TextView addText(LinearLayout parent, String value, int size) {
        TextView text = new TextView(this);
        text.setText(value);
        text.setTextSize(size);
        int space = (int) (8 * getResources().getDisplayMetrics().density);
        text.setPadding(0, space, 0, space);
        parent.addView(text);
        return text;
    }

    private void addButton(LinearLayout parent, String label, View.OnClickListener click) {
        Button button = new Button(this);
        button.setText(label);
        button.setOnClickListener(click);
        parent.addView(button);
    }

    private void fetchFromPlatform(boolean forceData) {
        io.execute(() -> {
            DeviceConfig next;
            String source;
            try {
                next = configClient.fetch();
                source = "平台已连接";
            } catch (Exception error) {
                next = configClient.cached();
                source = "平台连接失败：" + error.getMessage();
            }
            DeviceConfig resolved = next;
            String origin = source;
            runOnUiThread(() -> {
                config = resolved;
                showConfig(origin);
                updateReader();
                renderPreview();
                scheduleRotation();
                if (resolved != null && resolved.ledEnabled
                        && resolved.version != lastAppliedLedVersion) {
                    lastAppliedLedVersion = resolved.version;
                    sendLedPage(resolved);
                }
            });
            if (next == null) return;
            if (forceData || !next.schoolId.equals(classes.schoolId())
                    || System.currentTimeMillis() - lastDataSyncAt > DATA_SYNC_MS
                    || classes.classes().length() == 0) {
                try {
                    int cards = classes.sync(next.schoolId);
                    int scheduleGroups = schedules.sync(next.schoolId).length();
                    lastDataSyncAt = System.currentTimeMillis();
                    runOnUiThread(() -> {
                        dataStatus.setText("现有平台同步成功：" + classes.classes().length()
                                + " 个班级、" + cards + " 张班级卡、" + scheduleGroups + " 组放学时间");
                        renderPreview();
                        DeviceConfig active = config;
                        if (active != null && active.ledEnabled) sendLedPage(active);
                    });
                } catch (Exception error) {
                    runOnUiThread(() -> dataStatus.setText("班级/时间同步失败："
                            + error.getMessage() + "；继续使用已缓存的数据"));
                }
            }
        });
    }

    private void showConfig(String source) {
        DeviceConfig current = config;
        if (current == null) {
            configStatus.setText("无可用平台配置；放学功能未启用。" + source);
            ledStatus.setText("LED 未启用");
            return;
        }
        configStatus.setText(source + " · 配置 v" + current.version + " · 学校 "
                + current.schoolId + " · 放学模块" + (current.dismissalEnabled ? "启用" : "停用")
                + (current.testMode ? " · 测试模式（不限时段）" : ""));
        ledStatus.setText(current.ledEnabled
                ? "平台已启用 LED：" + current.ledIp + ":" + current.ledPort
                : "平台未启用 LED；设备不会发送画面");
    }

    private void updateReader() {
        if (!visible) return;
        DeviceConfig current = config;
        if (current == null || !current.dismissalEnabled) {
            if (readerRunning) cardProbe.stop();
            readerRunning = false;
            readerStatus.setText("放学模块未启用，读卡器已停用");
            return;
        }
        if (readerRunning) return;
        readerRunning = true;
        readerStatus.setText("正在打开内置读卡器…");
        cardProbe.start(new SerialCardProbe.Listener() {
            @Override public void onStatus(String message) {
                runOnUiThread(() -> {
                    readerStatus.setText(message);
                    if (message.startsWith("读卡器打开或读取失败")) {
                        readerRunning = false;
                        handler.postDelayed(() -> {
                            if (visible) updateReader();
                        }, 3000);
                    }
                });
            }
            @Override public void onBytes(byte[] bytes) {
                runOnUiThread(() -> handleCard(bytes));
            }
        });
    }

    private void handleCard(byte[] bytes) {
        String cardId = SerialCardProbe.cardNumber(bytes);
        DeviceConfig current = config;
        if (current == null || !current.schoolId.equals(classes.schoolId())) {
            cardStatus.setText("卡号 " + cardId + " · 平台班级数据尚未同步，暂不识别");
            return;
        }
        String className = classes.classForCard(cardId);
        if (className == null) {
            cardStatus.setText("卡号 " + cardId + " · 未找到绑定班级");
            return;
        }
        if (current == null || !current.dismissalEnabled) {
            cardStatus.setText("卡号 " + cardId + " · " + className + " · 放学模块未启用");
            return;
        }
        int classType = classes.classTypeForCard(cardId);
        String window = current.testMode ? "test" : schedules.activeWindowSignature(
                current.schoolId, classType, LocalDateTime.now());
        if (window == null) {
            cardStatus.setText("卡号 " + cardId + " · " + className + " · 非放学时段");
            return;
        }
        String classId = classes.classIdForCard(cardId);
        String voiceName = classes.voiceNameForCard(cardId);
        String text = VoiceText.announcement(voiceName);
        cardStatus.setText("卡号 " + cardId + " · " + className + " · " + text);
        board.setStatus(classId, DismissalBoard.DISMISSING);
        renderPreview();
        if (!current.testMode && (window.equals(spokenWindows.get(classId))
                || activeSpeech != null && activeSpeech.classId.equals(classId)
                && activeSpeech.window.equals(window)
                || pendingSpeech.stream().anyMatch(item -> item.classId.equals(classId)
                && item.window.equals(window)))) {
            voiceStatus.setText("本放学时段已播报过 " + className);
            return;
        }
        if (current.ledEnabled) sendLedPage(current);
        boolean callBusy = isCallBusy();
        PendingSpeech announcement = new PendingSpeech(text, classId, window, current);
        if (callBusy || speaker.isBusy() || !speaker.isReady() || !pendingSpeech.isEmpty()) {
            pendingSpeech.addLast(announcement);
            voiceStatus.setText((callBusy ? "通话占用音频"
                    : !speaker.isReady() ? "语音引擎未就绪" : "上一条正在播报")
                    + "，已排队 " + pendingSpeech.size()
                    + " 条；结束后播报：" + text);
            return;
        }
        startSpeech(announcement);
    }

    private boolean isCallBusy() {
        AudioManager audio = (AudioManager) getSystemService(AUDIO_SERVICE);
        return audio != null && (audio.getMode() == AudioManager.MODE_IN_CALL
                || audio.getMode() == AudioManager.MODE_IN_COMMUNICATION);
    }

    private void startSpeech(PendingSpeech announcement) {
        activeSpeech = announcement;
        speaker.speak(announcement.text, announcement.settings,
                message -> runOnUiThread(() -> {
                    voiceStatus.setText(message);
                    if (message.startsWith("播报完成") && activeSpeech == announcement) {
                        spokenWindows.put(announcement.classId, announcement.window);
                        activeSpeech = null;
                    } else if (message.startsWith("播报失败")
                            && activeSpeech == announcement) {
                        activeSpeech = null;
                    }
                }));
    }

    private void renderPreview() {
        if (preview == null) return;
        DeviceConfig current = config;
        LedStyle style = current == null ? LedStyle.defaults() : current.ledStyle;
        int count = LedBoardRenderer.pageCount(classes.classes(), style);
        if (page >= count) page = 0;
        Bitmap next = LedBoardRenderer.render(classes.classes(), board, style, page);
        preview.setImageBitmap(next);
        if (currentPreview != null) currentPreview.recycle();
        currentPreview = next;
        pageStatus.setText("平台 LED 画面预览 " + (page + 1) + "/" + count + " 页 · "
                + style.width + "×" + style.height);
    }

    private void scheduleRotation() {
        handler.removeCallbacks(rotate);
        DeviceConfig current = config;
        if (visible && current != null) {
            handler.postDelayed(rotate, current.ledStyle.pageSeconds * 1000L);
        }
    }

    private void checkLed() {
        DeviceConfig current = config;
        if (current == null || !current.ledEnabled) {
            ledStatus.setText("平台未启用 LED，无法测试连接");
            return;
        }
        ledStatus.setText("正在连接平台配置的控制卡…");
        io.execute(() -> {
            String result;
            try { result = led.ping(current.ledIp, current.ledPort); }
            catch (Exception error) { result = "控制卡连接失败：" + error.getMessage(); }
            String message = result;
            runOnUiThread(() -> ledStatus.setText(message));
            configClient.reportLed(result.startsWith("已连接"), "连接检测", result, current);
        });
    }

    private void sendLedPage(DeviceConfig current) {
        int selectedPage = page;
        io.execute(() -> {
            Bitmap image = LedBoardRenderer.render(classes.classes(), board,
                    current.ledStyle, selectedPage);
            try {
                String message = led.sendBoardPage(current.ledIp, current.ledPort,
                        image, getCacheDir());
                runOnUiThread(() -> ledStatus.setText(message));
                configClient.reportLed(true, "发送班级画面", message, current);
            } catch (Exception error) {
                runOnUiThread(() -> ledStatus.setText("LED 发送失败：" + error.getMessage()));
                configClient.reportLed(false, "发送班级画面", String.valueOf(error.getMessage()), current);
            } finally { image.recycle(); }
        });
    }

    @Override protected void onResume() {
        super.onResume();
        visible = true;
        updateReader();
        handler.post(poll);
        handler.post(checkPending);
        scheduleRotation();
    }

    @Override protected void onPause() {
        visible = false;
        handler.removeCallbacks(poll);
        handler.removeCallbacks(rotate);
        handler.removeCallbacks(checkPending);
        if (activeSpeech != null) {
            speaker.stop();
            pendingSpeech.addFirst(activeSpeech);
            activeSpeech = null;
            voiceStatus.setText("离开放学联调页，播报已暂停；返回后重播");
        }
        if (readerRunning) cardProbe.stop();
        readerRunning = false;
        super.onPause();
    }

    @Override protected void onDestroy() {
        cardProbe.stop();
        speaker.close();
        io.shutdownNow();
        if (currentPreview != null) currentPreview.recycle();
        super.onDestroy();
    }
}
