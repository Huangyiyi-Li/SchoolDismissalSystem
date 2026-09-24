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
    private EditText ipInput;
    private EditText portInput;
    private TextView result;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
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
        hint.setText("仅验证 BX-6E1XP 控制卡。发送测试文字会暂时覆盖 LED 当前画面，请在现场人员知情时操作。");
        content.addView(hint);

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
        result.setText("等待手动测试。串口刷卡将在取得现有项目的读卡类后接入。");
        content.addView(result);
        setContentView(scroll);
    }

    private void addButton(LinearLayout parent, String label, View.OnClickListener listener) {
        Button button = new Button(this);
        button.setText(label);
        button.setOnClickListener(listener);
        parent.addView(button);
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
    protected void onDestroy() {
        io.shutdownNow();
        super.onDestroy();
    }
}
