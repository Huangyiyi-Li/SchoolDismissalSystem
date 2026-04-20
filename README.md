# 校园放学语音播报系统 (School Dismissal Voice Broadcast System)

这是一个基于 Python 和 PyQt6 开发的智能放学语音播报系统。该系统通过 UDP 协议接收刷卡机数据，自动识别学生班级，并通过 TTS（文字转语音）进行语音播报，同时支持对接远程 API平台进行数据同步和消息推送。

## ✨ 核心功能

* **UDP 刷卡监听**: 监听端口 `39169`，实时接收刷卡机 UDP 数据包。
* **智能协议解析**: 自动解析 UDP 数据包中的 10-13 字节（小端序）作为物理卡号。
* **本地/云端双模**:
  * 支持从云端 API 同步班级与卡号映射关系。
  * 支持从云端 API 获取每日放学时间表。
  * 所有数据本地缓存（SQLite + JSON），断网不影响基础播报。
* **语音播报 (TTS)**: 使用 `pyttsx3` 引擎，支持多线程防阻塞播报，自动重试。
* **智能去重**: 可配置去重时间窗口，避免短时间内重复刷卡造成的重复播报。
* **实时监控 UI**:
  * **设备状态**: 监控刷卡机在线/离线状态。
  * **实时日志**: 显示详细的刷卡、解析、API 交互日志。
  * **播报队列**: 可视化展示当前等待播报的班级。
* **API 集成**:
  * 自动同步学校班级数据。
  * 刷卡成功后自动向云端推送放学通知。

## 🛠 技术栈

* **编程语言**: Python 3.10+
* **GUI 框架**: PyQt6
* **语音引擎**: pyttsx3 (SAPI5 on Windows)
* **网络通讯**: socket (UDP), requests (HTTP)
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

### 3. 运行程序

```bash
python main.py
```

### 4. 使用说明

1. **启动**: 程序启动后会自动开启 UDP 监听和 API 数据同步服务。
2. **验证**:
    * 刷卡后，日志区应显示接收到的卡号。
    * 如果卡号已绑定班级且在放学时间内，音箱将播放“XX年级XX班正在放学”。
3. **管理**:
    * 点击工具栏“设置”可修改学校 ID 和系统参数。
    * 点击“卡号映射”可手动管理本地班级数据（通常由 API 自动覆盖）。

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

系统对接 `rest.xxt.cn` 接口：
* `get-classes`: 获取班级列表。
* `push-dismissal-notice`: 推送放学通知。
* `get-school-dismissal-schedule`: 获取放学时间表。

## ⚠️ 注意事项

* **TTS 问题**: 在 Windows 上，程序使用了 `pythoncom.CoInitialize()` 以确保多线程 TTS 稳定运行。
* **防火墙**: 请确保 Windows 防火墙允许 UDP 39169 端口通信。
