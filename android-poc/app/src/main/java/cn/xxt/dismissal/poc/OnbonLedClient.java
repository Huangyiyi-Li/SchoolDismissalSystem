package cn.xxt.dismissal.poc;

import android.graphics.Bitmap;

import java.io.File;
import java.io.FileOutputStream;

import onbon.bx06.Bx6GScreen;
import onbon.bx06.Bx6GScreenClient;
import onbon.bx06.area.DynamicBxArea;
import onbon.bx06.area.page.TextBxPage;
import onbon.bx06.area.page.ImageFileBxPage;
import onbon.bx06.cmd.dyn.DynamicBxAreaRule;
import onbon.bx06.series.Bx6E;

/** BX-6E1XP probe using the vendor's Android Ethernet SDK. Call off the UI thread. */
final class OnbonLedClient {
    private static final int DYNAMIC_AREA_ID = 0;
    private static Bx6GScreenClient connect(String ip, int port) throws Exception {
        if (ProbeApplication.sdkFailure != null) {
            throw new IllegalStateException("仰邦 SDK 初始化失败", ProbeApplication.sdkFailure);
        }
        Bx6GScreenClient screen = new Bx6GScreenClient("XXT-Android-Probe", new Bx6E());
        if (!screen.connect(ip, port)) {
            throw new IllegalStateException("无法连接控制卡 " + ip + ":" + port);
        }
        return screen;
    }

    String ping(String ip, int port) throws Exception {
        Bx6GScreenClient screen = connect(ip, port);
        try {
            Bx6GScreen.Result<?> result = screen.ping();
            requireOk(result, "控制卡连接测试失败");
            return "已连接 BX-6E1XP，屏幕 " + screen.getProfile().getWidth()
                    + "×" + screen.getProfile().getHeight();
        } finally {
            screen.disconnect();
        }
    }

    String sendTestText(String ip, int port) throws Exception {
        Bx6GScreenClient screen = connect(ip, port);
        try {
            DynamicBxAreaRule rule = new DynamicBxAreaRule();
            rule.setId(DYNAMIC_AREA_ID);
            rule.setImmediatePlay((byte) 1);
            rule.setRunMode((byte) 0);
            DynamicBxArea area = new DynamicBxArea(0, 0,
                    screen.getProfile().getWidth(), screen.getProfile().getHeight(),
                    screen.getProfile());
            area.addPage(new TextBxPage("安卓联调测试"));
            requireOk(screen.writeDynamic(rule, area), "发送测试画面失败");
            return "测试文字已发送到 LED；完成后请点击清除测试画面";
        } finally {
            screen.disconnect();
        }
    }

    String sendBoardPage(String ip, int port, Bitmap page, File cacheDir) throws Exception {
        File image = File.createTempFile("led-page-", ".png", cacheDir);
        try {
            try (FileOutputStream output = new FileOutputStream(image)) {
                if (!page.compress(Bitmap.CompressFormat.PNG, 100, output)) {
                    throw new IllegalStateException("LED 画面编码失败");
                }
            }
            Bx6GScreenClient screen = connect(ip, port);
            try {
                int width = screen.getProfile().getWidth();
                int height = screen.getProfile().getHeight();
                if (page.getWidth() != width || page.getHeight() != height) {
                    throw new IllegalArgumentException("平台画面尺寸 " + page.getWidth() + "×"
                            + page.getHeight() + " 与控制卡 " + width + "×" + height + " 不一致");
                }
                DynamicBxAreaRule rule = new DynamicBxAreaRule();
                rule.setId(DYNAMIC_AREA_ID);
                rule.setImmediatePlay((byte) 1);
                rule.setRunMode((byte) 0);
                DynamicBxArea area = new DynamicBxArea(0, 0, width, height,
                        screen.getProfile());
                area.addPage(new ImageFileBxPage(image.getAbsolutePath()));
                requireOk(screen.writeDynamic(rule, area), "发送班级画面失败");
                return "平台班级画面已发送到 LED，请核对实体屏内容";
            } finally { screen.disconnect(); }
        } finally {
            if (!image.delete()) image.deleteOnExit();
        }
    }

    String clearTestText(String ip, int port) throws Exception {
        Bx6GScreenClient screen = connect(ip, port);
        try {
            requireOk(screen.deleteDynamic(DYNAMIC_AREA_ID), "清除测试画面失败");
            return "已清除动态区 0，请核对 LED 是否恢复原节目";
        } finally {
            screen.disconnect();
        }
    }

    private static void requireOk(Bx6GScreen.Result<?> result, String error) {
        if (result == null || !result.isOK()) {
            String detail = result == null ? "SDK 未返回结果"
                    : String.valueOf(result.getError()) + "，" + result;
            throw new IllegalStateException(error + "：" + detail);
        }
    }
}
