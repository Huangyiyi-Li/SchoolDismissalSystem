# ONBON Java LED Bridge

该目录使用仰邦 `BX_05_06_SDK_20241105` 中的六代 Java SDK，目标控制卡为
BX-6E1XP。

## Windows 构建

1. 安装 JDK 8（或使用具备 Java 8 兼容编译能力的 JDK）。
2. 双击或在命令行运行 `build.bat`。
3. 生成的 `led-bridge.jar` 与 `lib` 目录必须保持在一起。

macOS/Linux 开发机可设置 `JAVA_HOME` 后运行 `sh build.sh` 做编译验证。

## 手工测试

```bat
java -Djava.awt.headless=true -cp "led-bridge.jar;lib/*" cn.xxt.dismissal.led.OnbonLedBridge ping --ip 192.168.100.1 --port 5005
```

推送由 Python 客户端生成的图片：

```bat
java -Djava.awt.headless=true -cp "led-bridge.jar;lib/*" cn.xxt.dismissal.led.OnbonLedBridge display --ip 192.168.100.1 --port 5005 --width 1024 --height 96 --stay 500 --images page-01.bmp page-02.bmp
```

`--stay` 的单位是 10ms，`500` 即 5 秒。
`--width`、`--height` 使用实际屏幕像素，不强制为 8/16/32 的倍数，但必须与控制卡屏参完全一致。

正式 Windows 构建会在 `runtime` 目录附带 Java 8 运行时，客户端会优先使用它；
直接从源码运行且没有该目录时，系统会使用 PATH 中的 `java`。
