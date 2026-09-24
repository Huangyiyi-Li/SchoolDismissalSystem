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
        CardFrameAssembler frames = new CardFrameAssembler();
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
                    int incomplete = frames.expire(android.os.SystemClock.elapsedRealtime());
                    if (incomplete > 0) {
                        listener.onStatus("本次只收到 " + incomplete
                                + "/4 字节，超时未补齐；请再刷一次并记录现象");
                    }
                    Thread.sleep(100);
                    continue;
                }
                int count = stream.read(buffer);
                if (count > 0) {
                    byte[] chunk = Arrays.copyOf(buffer, count);
                    if (BuildConfig.DEBUG) {
                        android.util.Log.d("DismissalCardFrame", "read=" + count
                                + " at=" + android.os.SystemClock.elapsedRealtime()
                                + " raw=" + describe(chunk).replace('\n', ' '));
                    }
                    java.util.List<byte[]> complete = frames.accept(chunk,
                            android.os.SystemClock.elapsedRealtime());
                    if (frames.pendingSize() > 0) {
                        listener.onStatus("收到 " + count + " 字节，本张卡已累计 "
                                + frames.pendingSize() + "/4 字节，等待补齐");
                    }
                    for (byte[] card : complete) listener.onBytes(card);
                    if (!complete.isEmpty()) listener.onStatus("读卡器已打开；本次卡号已按 4 字节组帧");
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
        return "卡号：" + cardNumber(bytes) + "\n原始数据：" + hex;
    }

    static String cardNumber(byte[] bytes) {
        if (bytes.length != 4) {
            throw new IllegalArgumentException("卡号必须恰好为四字节");
        }
        long card = 0;
        for (int i = 3; i >= 0; i--) {
            card = (card << 8) | (bytes[i] & 0xff);
        }
        return Long.toString(card);
    }
}
