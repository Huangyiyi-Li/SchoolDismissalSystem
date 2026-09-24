package cn.xxt.dismissal.poc;

import android.app.Activity;
import android.app.AlertDialog;
import android.os.Bundle;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Manual hardware probe. No card or LED operation starts automatically. */
public final class MainActivity extends Activity {
    private final ExecutorService io = Executors.newSingleThreadExecutor();
    private final OnbonLedClient led = new OnbonLedClient();
    private final SerialCardProbe cardProbe = new SerialCardProbe();
    private ClassCatalog catalog;
    private EditText schoolIdInput;
    private TextView syncResult;
    private String lastCardId;
    private EditText ipInput;
    private EditText portInput;
    private TextView result;
    private TextView cardResult;
    private Button cardButton;
    private boolean cardListening;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        catalog = new ClassCatalog(this);
        ScrollView scroll = new ScrollView(this);
        LinearLayout content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        int pad = (int) (20 * getResources().getDisplayMetrics().density);
        content.setPadding(pad, pad, pad, pad);
        scroll.addView(content);

        TextView title = new TextView(this);
        title.setText("放学系统 · 安卓硬件联调");
        title.setTextSize(22);
        content.addView(title);
        TextView hint = new TextView(this);
        hint.setText("先验证设备内置刷卡器。LED 控制卡连接后再测试屏幕；发送测试文字会暂时覆盖 LED 当前画面。");
        content.addView(hint);

        cardButton = addButton(content, "开始刷卡测试", view -> toggleCardProbe());
        cardResult = new TextView(this);
        cardResult.setTextSize(18);
        cardResult.setText("刷卡测试尚未开始。只显示卡号，不会查询用户、推送消息或触发放学播报。");
        content.addView(cardResult);

        schoolIdInput = new EditText(this);
        schoolIdInput.setSingleLine(true);
        schoolIdInput.setInputType(android.text.InputType.TYPE_CLASS_NUMBER);
        schoolIdInput.setHint("学校编号");
        String savedSchoolId = catalog.schoolId();
        schoolIdInput.setText(savedSchoolId.isEmpty() ? "40125" : savedSchoolId);
        content.addView(schoolIdInput);
        addButton(content, "同步班级卡（只读取）", view -> syncClassCatalog());
        syncResult = new TextView(this);
        syncResult.setText("本地已有 " + catalog.cardCount() + " 张班级卡。同步只读取班级数据，不会通知家长。");
        content.addView(syncResult);

        ipInput = new EditText(this);
        ipInput.setSingleLine(true);
        ipInput.setHint("控制卡 IP");
        ipInput.setText("192.168.100.1");
        content.addView(ipInput);
        portInput = new EditText(this);
        portInput.setSingleLine(true);
        portInput.setInputType(android.text.InputType.TYPE_CLASS_NUMBER);
        portInput.setHint("端口");
        portInput.setText("5005");
        content.addView(portInput);

        addButton(content, "1. 测试连接", view -> runLedOperation("测试连接", led::ping));
        addButton(content, "2. 发送测试文字", view -> confirm(
                "LED 当前画面会暂时被测试文字覆盖。确认发送？",
                () -> runLedOperation("发送测试文字", led::sendTestText)));
        addButton(content, "3. 清除测试画面", view -> confirm(
                "将清除动态区 0。确认清除？",
                () -> runLedOperation("清除测试画面", led::clearTestText)));

        result = new TextView(this);
        result.setTextSize(16);
        result.setText("LED 测试尚未开始。");
        content.addView(result);
        setContentView(scroll);
    }

    private Button addButton(LinearLayout parent, String label, View.OnClickListener listener) {
        Button button = new Button(this);
        button.setText(label);
        button.setOnClickListener(listener);
        parent.addView(button);
        return button;
    }

    private void toggleCardProbe() {
        if (cardListening) {
            cardProbe.stop();
            cardListening = false;
            cardButton.setText("开始刷卡测试");
            cardResult.setText("刷卡测试已停止。");
            return;
        }
        cardListening = true;
        cardButton.setText("停止刷卡测试");
        cardResult.setText("正在打开 /dev/ttyS1…");
        cardProbe.start(new SerialCardProbe.Listener() {
            @Override
            public void onStatus(String message) {
                runOnUiThread(() -> cardResult.setText(message));
            }

            @Override
            public void onBytes(byte[] bytes) {
                runOnUiThread(() -> {
                    String message = SerialCardProbe.describe(bytes);
                    if (bytes.length == 4) {
                        lastCardId = SerialCardProbe.cardNumber(bytes);
                        String className = catalog.classForCard(lastCardId);
                        message += className == null
                                ? "\n当前同步数据未找到对应班级"
                                : "\n对应班级：" + className;
                    }
                    cardResult.setText(message);
                });
            }
        });
    }

    private void syncClassCatalog() {
        String schoolId = schoolIdInput.getText().toString().trim();
        syncResult.setText("正在读取学校 " + schoolId + " 的班级卡…");
        io.execute(() -> {
            String message;
            try {
                int count = catalog.sync(schoolId);
                message = "同步成功：学校 " + schoolId + " 有 " + count + " 张班级卡";
            } catch (Exception error) {
                message = "同步失败：" + error.getMessage();
            }
            String finalMessage = message;
            runOnUiThread(() -> {
                syncResult.setText(finalMessage);
                if (lastCardId != null) {
                    String className = catalog.classForCard(lastCardId);
                    if (className != null) {
                        cardResult.setText("上次卡号：" + lastCardId + "\n对应班级：" + className);
                    }
                }
            });
        });
    }

    private void confirm(String message, Runnable action) {
        new AlertDialog.Builder(this)
                .setMessage(message)
                .setNegativeButton("取消", null)
                .setPositiveButton("确认", (dialog, which) -> action.run())
                .show();
    }

    private void runLedOperation(String label, LedOperation operation) {
        final String ip = ipInput.getText().toString().trim();
        final int port;
        try {
            port = Integer.parseInt(portInput.getText().toString().trim());
            if (ip.isEmpty() || port < 1 || port > 65535) {
                throw new IllegalArgumentException();
            }
        } catch (IllegalArgumentException error) {
            result.setText("请输入控制卡 IP 和 1–65535 端口");
            return;
        }
        result.setText(label + "中…");
        io.execute(() -> {
            String message;
            try {
                message = operation.run(ip, port);
            } catch (Exception error) {
                message = label + "失败：" + error.getMessage();
            }
            final String finalMessage = message;
            runOnUiThread(() -> result.setText(finalMessage));
        });
    }

    private interface LedOperation {
        String run(String ip, int port) throws Exception;
    }

    @Override
    protected void onPause() {
        // The original terminal also reads /dev/ttyS1. Release it as soon as
        // this diagnostic screen is no longer visible.
        if (cardListening) {
            cardProbe.stop();
            cardListening = false;
            cardButton.setText("开始刷卡测试");
            cardResult.setText("刷卡测试已停止。返回本页后可再次开始。");
        }
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        cardProbe.stop();
        io.shutdownNow();
        super.onDestroy();
    }
}
