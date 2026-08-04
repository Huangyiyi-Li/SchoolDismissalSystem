package cn.xxt.dismissal.led;

import java.io.File;
import java.util.ArrayList;
import java.util.List;

import onbon.bx06.Bx6GEnv;
import onbon.bx06.Bx6GScreen;
import onbon.bx06.Bx6GScreenClient;
import onbon.bx06.area.DynamicBxArea;
import onbon.bx06.area.page.ImageFileBxPage;
import onbon.bx06.cmd.dyn.DynamicBxAreaRule;
import onbon.bx06.message.global.ACK;
import onbon.bx06.series.Bx6E;
import onbon.bx06.utils.DisplayStyleFactory;
import onbon.bx06.utils.DisplayStyleFactory.DisplayStyle;

/**
 * Small process bridge between the Python desktop app and ONBON's Java SDK.
 *
 * Commands:
 *   ping    --ip 192.168.100.1 --port 5005
 *   display --ip 192.168.100.1 --port 5005 --stay 500 --images a.bmp b.bmp
 *   clear   --ip 192.168.100.1 --port 5005
 */
public final class OnbonLedBridge {
    private OnbonLedBridge() {
    }

    public static void main(String[] args) {
        Bx6GScreenClient screen = null;
        try {
            Arguments options = Arguments.parse(args);
            Bx6GEnv.initial(15000);
            screen = new Bx6GScreenClient("XXT-Dismissal-LED", new Bx6E());
            if (!screen.connect(options.ip, options.port)) {
                fail("无法连接控制卡 " + options.ip + ":" + options.port);
            }

            if ("ping".equals(options.command)) {
                Bx6GScreen.Result<?> result = screen.ping();
                requireOk(result, "控制卡连接测试失败");
                ok("已连接 BX-6E 控制卡 " + options.ip + ":" + options.port);
            } else if ("display".equals(options.command)) {
                writeImages(screen, options);
                ok("已发送 " + options.images.size() + " 个 LED 页面");
            } else if ("clear".equals(options.command)) {
                Bx6GScreen.Result<?> result = screen.deleteDynamic(0);
                requireOk(result, "清除动态区失败");
                ok("已清除 LED 动态区");
            } else {
                fail("不支持的命令: " + options.command);
            }
        } catch (Exception error) {
            System.err.println("ERR " + safeMessage(error));
            System.exit(2);
        } finally {
            if (screen != null && screen.isConnected()) {
                try {
                    screen.disconnect();
                } catch (Exception ignored) {
                    // The command outcome is more useful than a disconnect error.
                }
            }
        }
    }

    private static void writeImages(Bx6GScreenClient screen, Arguments options) throws Exception {
        DynamicBxAreaRule rule = new DynamicBxAreaRule();
        rule.setId(0);
        rule.setImmediatePlay((byte) 1);
        rule.setRunMode((byte) 0);

        DynamicBxArea area = new DynamicBxArea(
            0,
            0,
            options.width,
            options.height,
            screen.getProfile()
        );
        for (String imagePath : options.images) {
            File image = new File(imagePath);
            if (!image.isFile()) {
                throw new IllegalArgumentException("LED 页面不存在: " + imagePath);
            }
            ImageFileBxPage page = new ImageFileBxPage(image.getAbsolutePath());
            DisplayStyle[] styles = DisplayStyleFactory.getStyles().toArray(new DisplayStyle[0]);
            // SDK index 1 is static display; page switching is controlled by stay time.
            page.setDisplayStyle(styles[1]);
            page.setSpeed(1);
            // SDK unit is 10ms; Python converts seconds to this value.
            page.setStayTime(options.stay);
            area.addPage(page);
        }

        Bx6GScreen.Result<ACK> result = screen.writeDynamic(rule, area);
        requireOk(result, "发送动态区失败");
    }

    private static void requireOk(Bx6GScreen.Result<?> result, String message) {
        if (result == null || !result.isOK()) {
            String error = result == null ? "无返回结果" : String.valueOf(result.getError());
            throw new IllegalStateException(message + ": " + error);
        }
    }

    private static String safeMessage(Exception error) {
        String message = error.getMessage();
        return message == null || message.trim().isEmpty()
            ? error.getClass().getSimpleName()
            : message.replace('\n', ' ').replace('\r', ' ');
    }

    private static void ok(String message) {
        System.out.println("OK " + message);
    }

    private static void fail(String message) {
        throw new IllegalStateException(message);
    }

    private static final class Arguments {
        private String command;
        private String ip;
        private int port = 5005;
        private int width = 1024;
        private int height = 96;
        private int stay = 500;
        private final List<String> images = new ArrayList<String>();

        private static Arguments parse(String[] args) {
            if (args.length == 0) {
                throw new IllegalArgumentException("缺少命令");
            }
            Arguments parsed = new Arguments();
            parsed.command = args[0];
            for (int index = 1; index < args.length; index++) {
                String value = args[index];
                if ("--ip".equals(value)) {
                    parsed.ip = requireValue(args, ++index, "--ip");
                } else if ("--port".equals(value)) {
                    parsed.port = Integer.parseInt(requireValue(args, ++index, "--port"));
                } else if ("--stay".equals(value)) {
                    parsed.stay = Integer.parseInt(requireValue(args, ++index, "--stay"));
                } else if ("--width".equals(value)) {
                    parsed.width = Integer.parseInt(requireValue(args, ++index, "--width"));
                } else if ("--height".equals(value)) {
                    parsed.height = Integer.parseInt(requireValue(args, ++index, "--height"));
                } else if ("--images".equals(value)) {
                    for (index = index + 1; index < args.length; index++) {
                        parsed.images.add(args[index]);
                    }
                    break;
                } else {
                    throw new IllegalArgumentException("未知参数: " + value);
                }
            }
            if (parsed.ip == null || parsed.ip.trim().isEmpty()) {
                throw new IllegalArgumentException("缺少 --ip");
            }
            if (parsed.port < 1 || parsed.port > 65535) {
                throw new IllegalArgumentException("端口超出范围");
            }
            if (parsed.width < 1 || parsed.height < 1) {
                throw new IllegalArgumentException("LED 像素尺寸必须大于 0");
            }
            if (parsed.width > 2048) {
                throw new IllegalArgumentException("BX-6E1XP 单色屏宽度不能超过 2048 像素");
            }
            if (parsed.height > 1024) {
                throw new IllegalArgumentException("BX-6E1XP 屏幕高度不能超过 1024 像素");
            }
            if ((long) parsed.width * parsed.height > 524288L) {
                throw new IllegalArgumentException("BX-6E1XP 单色屏总像素不能超过 524288");
            }
            if ("display".equals(parsed.command) && parsed.images.isEmpty()) {
                throw new IllegalArgumentException("缺少 --images");
            }
            return parsed;
        }

        private static String requireValue(String[] args, int index, String option) {
            if (index >= args.length) {
                throw new IllegalArgumentException(option + " 缺少值");
            }
            return args[index];
        }
    }
}
