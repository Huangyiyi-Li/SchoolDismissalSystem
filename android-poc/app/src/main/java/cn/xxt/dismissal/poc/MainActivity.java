package cn.xxt.dismissal.poc;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.graphics.Bitmap;
import android.media.AudioManager;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
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
import java.util.concurrent.atomic.AtomicBoolean;

import org.json.JSONObject;

/** Test client: settings come from the Mac platform; class and schedule data use live APIs. */
public final class MainActivity extends Activity {
    private static final long CONFIG_POLL_MS = 30_000;
    private static final long DATA_SYNC_MS = 10 * 60_000;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final ExecutorService io = Executors.newSingleThreadExecutor();
    private final SerialCardProbe cardProbe = new SerialCardProbe();
    private final AnnouncementSpeaker speaker = new AnnouncementSpeaker();
    private final OnbonLedClient led = new OnbonLedClient();
    private final AtomicBoolean ledSendQueued = new AtomicBoolean();
    private final AtomicBoolean ledResendRequested = new AtomicBoolean();
    private final Map<String, String> spokenWindows = new HashMap<>();
    private PlatformEndpoint endpoint;
    private DeviceConfigClient configClient;
    private RemoteControlClient remote;
    private UpdateManager updates;
    private ClassCatalog classes;
    private ScheduleCatalog schedules;
    private DismissalBoard board;
    private volatile DeviceConfig config;
    private boolean readerRunning;
    private boolean visible;
    private long lastDataSyncAt;
    private int lastAppliedLedVersion = -1;
    private volatile int page;
    private long lastHeartbeatAt;
    private long lastAutoLedEventAt;
    private String lastAutoLedEventKey = "";
    private JSONObject updateOffer;
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
    private TextView updateStatus;
    private Button updateButton;

    private final Runnable poll = new Runnable() {
        @Override public void run() {
            if (!visible) return;
            fetchFromPlatform(false);
            pollRemote();
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
        endpoint = new PlatformEndpoint(this);
        configClient = new DeviceConfigClient(this, endpoint);
        remote = new RemoteControlClient(this, endpoint);
        updates = new UpdateManager(this, endpoint);
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
        addText(content, "远程联调与升级", 20);
        updateStatus = addText(content, "当前版本 " + BuildConfig.VERSION_NAME
                + " · 平台 " + endpoint.hostForDisplay(), 16);
        updateButton = addButton(content, "下载并安装新版", v -> installUpdate());
        updateButton.setVisibility(View.GONE);
        addText(content, "话机通话、请假和留言的冲突处理尚需接入原话机应用；当前联调版只验证放学链路。", 14);
        setContentView(scroll);

        speaker.start(this, message -> runOnUiThread(() -> voiceStatus.setText(message)));
        showConfig("本机缓存，正在检查平台");
        renderPreview();
        handlePairIntent(getIntent());
    }

    @Override protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        handlePairIntent(intent);
    }

    private void handlePairIntent(Intent intent) {
        if (intent == null || intent.getData() == null) return;
        try {
            String[] pair = PlatformEndpoint.parsePairUri(intent.getData());
            String host = new java.net.URI(pair[0]).getHost();
            new AlertDialog.Builder(this).setTitle("连接测试平台")
                    .setMessage("话机将连接 " + host + "，从这里获取放学配置和远程测试命令。")
                    .setNegativeButton("取消", null)
                    .setPositiveButton("连接", (dialog, which) -> {
                        endpoint.save(pair[0], pair[1]);
                        configClient.clearCache();
                        remote.clearForNewPlatform();
                        config = null;
                        lastAppliedLedVersion = -1;
                        lastHeartbeatAt = 0;
                        updateStatus.setText("正在连接 " + endpoint.hostForDisplay() + "…");
                        showConfig("已更换平台，正在拉取配置");
                        updateReader();
                        fetchFromPlatform(true);
                        pollRemote();
                    }).show();
        } catch (Exception error) {
            updateStatus.setText("平台配对失败：" + errorText(error));
        }
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

    private Button addButton(LinearLayout parent, String label, View.OnClickListener click) {
        Button button = new Button(this);
        button.setText(label);
        button.setOnClickListener(click);
        parent.addView(button);
        return button;
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

    private void pollRemote() {
        io.execute(() -> {
            try { remote.flushPending(); }
            catch (Exception error) { android.util.Log.w("DismissalRemote", "旧诊断暂未回传", error); }
            try {
                JSONObject control = remote.fetch();
                JSONObject release = control.optJSONObject("release");
                runOnUiThread(() -> showRelease(release));
                JSONObject command = control.optJSONObject("command");
                if (command != null) executeRemoteCommand(command);
                long now = System.currentTimeMillis();
                if (now - lastHeartbeatAt >= 120_000) {
                    lastHeartbeatAt = now;
                    remote.report("heartbeat", true, "话机在线", config);
                }
            } catch (Exception error) {
                runOnUiThread(() -> updateStatus.setText("远程平台暂不可达：" + error.getMessage()
                        + " · 当前版本 " + BuildConfig.VERSION_NAME));
            }
        });
    }

    private void executeRemoteCommand(JSONObject command) {
        String id = command.optString("id", "");
        String type = command.optString("type", "");
        if (!id.matches("[0-9a-f]{32}") || remote.alreadyExecuted(id)) return;
        DeviceConfig current = config;
        String result;
        boolean success;
        try {
            if (current == null || !current.ledEnabled) {
                throw new IllegalStateException("平台未启用 LED，无法执行远程检测");
            }
            if ("led_ping".equals(type)) {
                result = led.ping(current.ledIp, current.ledPort);
            } else if ("led_send_page".equals(type)) {
                Bitmap image = LedBoardRenderer.render(classes.classes(), board,
                        current.ledStyle, page);
                try {
                    result = led.sendBoardPage(current.ledIp, current.ledPort,
                            image, getCacheDir());
                } finally { image.recycle(); }
            } else {
                throw new IllegalArgumentException("未知远程命令：" + type);
            }
            success = true;
        } catch (Exception error) {
            result = errorText(error);
            success = false;
        }
        String message = result;
        boolean accepted = success;
        runOnUiThread(() -> ledStatus.setText("远程检测" + (accepted ? "成功：" : "失败：") + message));
        remote.reportCommand(type, success, result, current, id);
    }

    private void showRelease(JSONObject release) {
        updateOffer = updates.isNewer(release) ? release : null;
        updateButton.setVisibility(updateOffer == null ? View.GONE : View.VISIBLE);
        updateStatus.setText(updateOffer == null
                ? "当前版本 " + BuildConfig.VERSION_NAME + " · 平台 " + endpoint.hostForDisplay()
                : "可升级到 " + updateOffer.optString("versionName")
                + " · 下载后需在话机上确认安装");
    }

    private void installUpdate() {
        JSONObject offer = updateOffer;
        if (offer == null) return;
        if (!getPackageManager().canRequestPackageInstalls()) {
            updateStatus.setText("请允许本应用安装未知来源应用，返回后再次点击升级");
            startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                    Uri.parse("package:" + getPackageName())));
            return;
        }
        updateStatus.setText("正在下载并校验升级包…");
        io.execute(() -> {
            try {
                Uri packageUri = updates.downloadAndVerify(offer);
                remote.report("update", true, "升级包已验证，等待用户确认安装", config);
                runOnUiThread(() -> {
                    try {
                        Intent install = new Intent(Intent.ACTION_INSTALL_PACKAGE);
                        install.setDataAndType(packageUri, "application/vnd.android.package-archive");
                        install.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                        startActivity(install);
                        updateStatus.setText("请按安卓系统提示确认安装；完成后重新打开应用");
                    } catch (Exception error) {
                        updateStatus.setText("打开系统安装界面失败：" + errorText(error));
                        io.execute(() -> remote.report("update", false,
                                "打开安装界面失败：" + errorText(error), config));
                    }
                });
            } catch (Exception error) {
                remote.report("update", false, errorText(error), config);
                runOnUiThread(() -> updateStatus.setText("升级失败：" + errorText(error)));
            }
        });
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
            catch (Exception error) { result = "控制卡连接失败：" + errorText(error); }
            String message = result;
            runOnUiThread(() -> ledStatus.setText(message));
            remote.report("led_ping", result.startsWith("已连接"), result, current);
        });
    }

    private void sendLedPage(DeviceConfig current) {
        if (!ledSendQueued.compareAndSet(false, true)) {
            ledResendRequested.set(true);
            return;
        }
        int selectedPage = page;
        io.execute(() -> {
            Bitmap image = null;
            try {
                image = LedBoardRenderer.render(classes.classes(), board,
                        current.ledStyle, selectedPage);
                String message = led.sendBoardPage(current.ledIp, current.ledPort,
                        image, getCacheDir());
                runOnUiThread(() -> ledStatus.setText(message));
                reportAutoLed(true, message, current);
            } catch (Exception error) {
                String detail = errorText(error);
                runOnUiThread(() -> ledStatus.setText("LED 发送失败：" + detail));
                reportAutoLed(false, detail, current);
            } finally {
                if (image != null) image.recycle();
                ledSendQueued.set(false);
                if (ledResendRequested.getAndSet(false)) {
                    DeviceConfig active = config;
                    if (active != null && active.ledEnabled) sendLedPage(active);
                }
            }
        });
    }

    private void reportAutoLed(boolean success, String message, DeviceConfig current) {
        String key = success + ":" + message;
        long now = System.currentTimeMillis();
        if (!key.equals(lastAutoLedEventKey) || now - lastAutoLedEventAt >= 60_000) {
            lastAutoLedEventKey = key;
            lastAutoLedEventAt = now;
            remote.report("led_send_page", success, message, current);
        }
    }

    private static String errorText(Throwable error) {
        String message = error.getMessage();
        String detail = error.getClass().getSimpleName()
                + (message == null || message.trim().isEmpty() ? "" : "：" + message);
        Throwable cause = error.getCause();
        if (cause != null && cause != error) {
            String causeMessage = cause.getMessage();
            detail += "；原因 " + cause.getClass().getSimpleName()
                    + (causeMessage == null || causeMessage.trim().isEmpty() ? "" : "：" + causeMessage);
        }
        return detail;
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
