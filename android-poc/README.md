# 安卓 9 硬件联调版

这是独立于现有 Windows 客户端的最小验证工程，使用仰邦提供的 Android Ethernet SDK 对 BX-6E1XP 做手动连接、动态区测试文字和清除。**当前不包含串口刷卡、云端同步或正式放学业务，不是可交付的放学客户端。**

## 当前证据

- 本机开发包位于 `~/Downloads/BX_05_06_SDK_20241105/JAVA/Android/Android_Ethernet/bx.dual.android`。其示例项目 `minSdkVersion 21`，包含 `Bx6E`、`DynamicBxAreaRule`、`ImageFileBxPage`；安卓 9 是 API 28。
- Windows 客户端用 `Bx6E`、动态区 0、控制卡默认端口 5005。这里按相同控制卡系列编写，但安卓 SDK 版本不同，真实控制卡行为仍需现场核对。
- 用户提供的其他项目代码已从 `/dev/ttyS1`、9600 波特率收到 `cardNo`，但 `SerialPortManage` 实现和设备型号尚未找到。

## 在 Android Studio 中打开

1. 安装 Android Studio，并在 SDK Manager 中安装 Android SDK Platform 35。工程最低系统版本是 Android 9（API 28）。本机 SDK 目录为 `~/Andriod`。
2. 在本目录运行 `bash setup-vendor-sdk.sh`，从本机已有的仰邦示例复制依赖。依赖文件被 Git 忽略，不会提交到仓库。
3. 用 Android Studio 打开本目录，等待 Gradle 同步后运行到目标安卓机。`gradlew` 使用 Gradle 8.9，Android Gradle Plugin 为 8.7.3，需要 JDK 17。
4. 执行 `JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home ./gradlew assembleDebug` 后，APK 位于 `app/build/outputs/apk/debug/app-debug.apk`。这是仅供联调的 debug 包。
5. 在安卓机输入现场控制卡 IP 和端口，先点“测试连接”。确认现场允许更改画面后，再测试发送与清除；核对原节目是否恢复。

## 待实机验证和后续接入

1. 目标机能否打开 `/dev/ttyS1`，以及同一张校园卡的 `cardNo` 是否等于后台卡号。当前 Windows 近距离读卡器从四个字节按小端序得到十进制卡号；安卓串口类可能已做转换，不能再盲目转换一次。
2. Android SDK 与 BX-6E1XP 实机是否能连接、发送、清除动态区，单色和双色屏是否正常，是否恢复原节目。
3. 上述两项通过后，接入完整读卡监听、数据同步、放学时段、语音播报和图片分页渲染。

2026-09-24 已在本机使用 JDK 17、Android Platform 35、Build Tools 36 和仰邦 Android SDK 构建成功；APK 的 ZIP 完整性、最低 API 28 和 v2 签名已核对。目标安卓机和 LED 仍未进行实机测试。
