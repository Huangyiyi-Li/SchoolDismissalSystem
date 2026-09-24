package cn.xxt.dismissal.poc;

import java.io.FileInputStream;
import java.io.IOException;
import java.util.Arrays;

/** Read-only diagnostic for the GT-10M built-in reader on /dev/ttyS1. */
final class SerialCardProbe {
    interface Listener {
        void onStatus(String message);
        void onBytes(byte[] bytes);
    }

    private volatile boolean running;
    private volatile FileInputStream input;
    private Thread thread;

    synchronized void start(Listener listener) {
        if (running) {
            return;
        }
        running = true;
        thread = new Thread(() -> readLoop(listener), "serial-card-probe");
        thread.start();
    }

    synchronized void stop() {
        running = false;
        Thread current = thread;
        if (current != null) {
            current.interrupt();
        }
        FileInputStream stream = input;
        if (stream != null) {
            try {
                stream.close();
            } catch (IOException ignored) {
            }
        }
        input = null;
        thread = null;
    }

    private void readLoop(Listener listener) {
        try {
            // Match device_qingju's serial settings. A failed stty is reported but
            // does not prevent reading if the device already has the right settings.
            Process stty = new ProcessBuilder("/system/bin/stty", "-F", "/dev/ttyS1",
                    "9600", "cs8", "-parenb", "-cstopb", "raw").start();
            int status = stty.waitFor();
            if (status != 0) {
                listener.onStatus("串口参数设置未成功，继续尝试读取（stty=" + status + "）");
            }
        } catch (Exception error) {
            listener.onStatus("串口参数设置不可用，继续尝试读取：" + error.getMessage());
        }

        try (FileInputStream stream = new FileInputStream("/dev/ttyS1")) {
            input = stream;
            listener.onStatus("读卡器已打开，请贴近刷一张测试卡");
            byte[] buffer = new byte[100];
            while (running) {
                if (stream.available() == 0) {
                    Thread.sleep(100);
                    continue;
                }
                int count = stream.read(buffer);
                if (count > 0) {
                    listener.onBytes(Arrays.copyOf(buffer, count));
                }
            }
        } catch (InterruptedException ignored) {
            Thread.currentThread().interrupt();
        } catch (Exception error) {
            if (running) {
                listener.onStatus("读卡器打开或读取失败：" + error.getMessage());
            }
        } finally {
            input = null;
            running = false;
        }
    }

    static String describe(byte[] bytes) {
        StringBuilder hex = new StringBuilder();
        for (byte value : bytes) {
            if (hex.length() > 0) hex.append(' ');
            hex.append(String.format(java.util.Locale.US, "%02X", value & 0xff));
        }
        if (bytes.length != 4) {
            return "收到 " + bytes.length + " 字节：" + hex + "\n需核对读卡数据格式，暂不当作卡号";
        }
        long card = 0;
        for (int i = 3; i >= 0; i--) {
            card = (card << 8) | (bytes[i] & 0xff);
        }
        return "卡号：" + card + "\n原始数据：" + hex;
    }
}
