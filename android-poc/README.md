# 安卓 9 硬件联调版

这是独立于现有 Windows 客户端的最小验证工程。它可手动读取 GT-10M 设备 `/dev/ttyS1` 的原始刷卡数据和小端十进制卡号，并手动从 `get-classes-v2` 只读同步班级卡、显示卡片对应班级；另可用仰邦 Android Ethernet SDK 对 BX-6E1XP 做手动连接、动态区测试文字和清除。**当前不包含放学语音、通知推送或正式放学业务，不是可交付的放学客户端。**

## 当前证据

- 本机开发包位于 `~/Downloads/BX_05_06_SDK_20241105/JAVA/Android/Android_Ethernet/bx.dual.android`。其示例项目 `minSdkVersion 21`，包含 `Bx6E`、`DynamicBxAreaRule`、`ImageFileBxPage`；安卓 9 是 API 28。
- Windows 客户端用 `Bx6E`、动态区 0、控制卡默认端口 5005。这里按相同控制卡系列编写，但安卓 SDK 版本不同，真实控制卡行为仍需现场核对。
- `device_qingju` 分支提供了 `SerialPortManage`：从 `/dev/ttyS1` 以 9600 波特率读取，将收到的字节按小端序转十进制。本联调版只把恰好四字节的一次读取显示为候选卡号，其他长度仅显示原始字节，等待实机核对协议。
- 2026-09-24 已通过 Wi-Fi ADB 连接 GT-10M（安卓 9，`arm64-v8a`）。设备上存在 `/dev/ttyS1`；联调版成功读取四字节刷卡数据，用户确认小端十进制卡号与系统入库一致。学校 40125 的 `get-classes-v2` 接口返回 38 个班级，安卓端 0.3.1 同步得到 72 张班级卡，并在实机上把测试卡显示为“行政班：5.2班”；用户确认测试无误。0.3.0 曾将空播报名称显示为 `null`，0.3.1 已修复并复测。

## 在 Android Studio 中打开

1. 安装 Android Studio，并在 SDK Manager 中安装 Android SDK Platform 35。工程最低系统版本是 Android 9（API 28）。本机 SDK 目录为 `~/Andriod`。
2. 在本目录运行 `bash setup-vendor-sdk.sh`，从本机已有的仰邦示例复制依赖。依赖文件被 Git 忽略，不会提交到仓库。
3. 用 Android Studio 打开本目录，等待 Gradle 同步后运行到目标安卓机。`gradlew` 使用 Gradle 8.9，Android Gradle Plugin 为 8.7.3，需要 JDK 17。
4. 执行 `JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home ./gradlew assembleDebug` 后，APK 位于 `app/build/outputs/apk/debug/app-debug.apk`。这是仅供联调的 debug 包。
5. 在安卓机输入现场控制卡 IP 和端口，先点“测试连接”。确认现场允许更改画面后，再测试发送与清除；核对原节目是否恢复。

## 待实机验证和后续接入

1. 安装联调版后，打开“放学系统安卓联调”，确认学校编号，点击“同步班级卡（只读取）”，等待成功提示。然后点击“开始刷卡测试”，贴近刷一张测试卡，核对显示的班级。若显示非四字节，则先确认读卡帧格式。现有终端 App 也会读取该串口，刷卡测试时请勿同时让两个 App 监听。
2. Android SDK 与 BX-6E1XP 实机是否能连接、发送、清除动态区，单色和双色屏是否正常，是否恢复原节目。
3. 上述两项通过后，接入完整读卡监听、数据同步、放学时段、语音播报和图片分页渲染。

2026-09-24 已在本机使用 JDK 17、Android Platform 35、Build Tools 36 和仰邦 Android SDK 构建成功；APK 的 ZIP 完整性、最低 API 28 和 v2 签名已核对。目标安卓机和 LED 仍未进行实机测试。
