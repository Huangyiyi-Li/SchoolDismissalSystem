# 数智家校放学系统

这是一个基于 Python 和 PyQt6 开发的智能放学语音播报系统。系统通过 UDP 协议接收刷卡机数据，自动识别学生班级，并通过 TTS（文字转语音）进行语音播报，同时支持远程 API 数据同步、服务端放学指令和消息回传。

## ✨ 核心功能

* **UDP 刷卡监听**: 监听端口 `39169`，实时接收刷卡机 UDP 数据包。
* **智能协议解析**: 自动解析 UDP 数据包中的 10-13 字节（小端序）作为物理卡号。
* **本地/云端双模**:
  * 支持从 2.0 云端 API 同步班级、班级类型与卡号映射关系。
  * 支持从 2.0 云端 API 获取按班级类型分组的每日放学时间表。
  * 所有数据本地缓存（SQLite + JSON），断网不影响基础播报。
* **语音播报 (TTS)**: 使用 `pyttsx3` 引擎，支持多线程防阻塞播报，自动重试。
* **智能去重**: 可配置去重时间窗口，避免短时间内重复刷卡造成的重复播报。
* **实时监控 UI**:
  * **实时日志**: 显示详细的刷卡、解析、API 交互日志。
  * **系统状态**: 显示当前放学时段与测试模式状态。
* **API 集成**:
  * 客户端启动、手动操作及每 30 分钟自动同步学校班级数据和放学时间表。
  * 每个行政班或社团班放学时段开始前 2 分钟，设置一次性定时器获取最新数据。
  * 刷卡成功后自动通过 2.0 接口向云端推送放学通知。
* **MQTT 联动**:
  * 软件启动后按设备编号每 60 秒上报客户端在线心跳。
  * 接收云端 `ManualDismissal` 指令后立即触发本地语音播报，并回复处理结果。

## 🛠 技术栈

* **编程语言**: Python 3.10+
* **GUI 框架**: PyQt6
* **语音引擎**: pyttsx3 (SAPI5 on Windows)
* **网络通讯**: socket (UDP), requests (HTTP), paho-mqtt (MQTT)
* **数据存储**: SQLite3, JSON

## 🚀 快速开始

### 1. 环境准备

确保已安装 Python 3.10 或更高版本。

```bash
pip install -r requirements.txt
```

### 2. 配置文件

系统启动后会自动生成 `config/settings.json`。初次使用请修改：

* `school_id`: 您的学校 ID (用于 API 通讯)。
* `udp_port`: UDP 监听端口 (默认 39169)。
* `api_base_url`: API 地址，测试环境为 `https://rest-test.xxt.cn`，正式环境为 `https://rest.xxt.cn`。
* `device_no`: MQTT 设备编号；留空时程序会用本机 MAC 生成 12 位大写十六进制编号并保存，例如 `AABBCCDDEEFF`。

### 3. 运行程序

```bash
python main.py
```

### 4. 使用说明

1. **启动**: 程序启动后会自动开启 UDP 监听，并立即执行一次 API 数据同步。
2. **验证**:
    * 刷卡后，日志区应显示完整年月日时分秒、卡号和处理结果。
    * 如果卡号已绑定班级且在放学时间内，音箱将播放“XX年级XX班正在放学”。
3. **管理**:
    * 点击工具栏“设置”可修改学校 ID 和系统参数。
    * 点击“卡号映射”可手动管理本地班级数据（通常由 API 自动覆盖）。
    * 点击工具栏“开机自启”可自动创建 Windows 开机启动项，登录后延迟 30 秒启动本系统；如果当前账号无权写入任务计划，会自动改用用户 Startup 启动脚本。

## 📂 目录结构

```
root/
├── config/             # 配置文件
├── PRD/                # 需求文档
├── src/
│   ├── services/       # 核心服务 (UDP, Broadcast, API, Sync)
│   ├── ui/             # 界面代码 (MainWindow, Dialogs)
│   └── database.py     # 数据库管理
├── tools/              # 调试工具
├── main.py             # 入口文件
└── requirements.txt    # 依赖列表
```

## 📝 API 接口说明

系统对接 `rest.xxt.cn` / `rest-test.xxt.cn` 的 2.0 接口：
* `get-classes-v2`: 获取班级列表。
* `push-dismissal-notice-v2`: 推送放学通知。
* `get-school-dismissal-schedule-v2`: 获取放学时间表。

MQTT 默认连接 `111.6.173.61:1883`，用户名和 client-id 均使用本机 `device_no`。心跳上行 topic 为 `v1/devices/me/telemetry`；下发放学指令订阅 `v1/devices/me/rpc/request/+`；回执 topic 为 `v1/devices/me/rpc/response/{request_id}`。启动连接失败后默认每 60 秒重试；服务端中断重启后客户端会自动重连并重新订阅下发指令 topic。

### 数据同步触发机制

* 客户端启动时立即同步一次。
* 点击“立即同步数据”时同步一次。
* 客户端运行期间每 30 分钟同步一次。
* 每个有效放学时段开始前 2 分钟精确同步一次；行政班和社团班时段都参与计算，不使用高频轮询。

## 📌 项目 TODO

后续优化项统一维护在 [TODO.md](TODO.md)。

## 📐 开发与发布规范

客户端命名、版本号展示、品牌图标、Windows 构建和 GitHub Release 发布要求统一维护在 [DEVELOPMENT.md](DEVELOPMENT.md)。

## ⚠️ 注意事项

* **TTS 问题**: 在 Windows 上，程序使用了 `pythoncom.CoInitialize()` 以确保多线程 TTS 稳定运行。
* **防火墙**: 请确保 Windows 防火墙允许 UDP 39169 端口通信。
* **刷卡记录**: 每条刷卡记录会立即写入 `data/school.db`。打包后的 exe 会把 `data` 目录放在 exe 同级目录；如果把 exe 放到不同文件夹运行，会使用对应文件夹下的数据库。
