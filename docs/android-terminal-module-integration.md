# 放学模块接入话机应用：接口与交互边界

本文件记录联调版验证后要接入 `device_qingju` 话机项目的边界。当前独立 APK 只负责验证串口、平台拉取、语音和 LED，尚未改动原 `cn.xxt.terminal` 应用。

## 接口复用

| 业务 | 来源 | 说明 |
| --- | --- | --- |
| 班级及绑卡 | `POST /kq-http/school-dismissal-system/get-classes-v2`，`{"schoolId":"40125"}` | 沿用 Windows 客户端；包括完整班级目录和卡号映射 |
| 放学时间 | `POST /kq-http/school-dismissal-system/get-school-dismissal-schedule-v2`，同一学校编号 | 沿用 Windows 客户端；按行政班/社团班、星期和时间段判断 |
| 设备配置 | 联调期 Mac `GET /api/device-config` | 新接口，正式平台需承接；包括模块开关、学校编号、语音设置和 LED 设置 |
| 家长通知 | 原 Windows `push-dismissal-notice-v2` | 本轮联调不调用，避免测试卡触发真实通知；待正式业务验收时决定是否接入 |

Mac 测试接口返回 `{"code":200,"data":{...}}`。`data` 至少包含 `version`、`schoolId`、`dismissalEnabled`、`testMode`、`voice`、`led`。`voice` 下含 `speed`（0.5–2）、`volumePercent`（0–100）、`repeatCount`（1–10）、`repeatIntervalSeconds`（0–30）；`led` 下含 `enabled`、`controllerIp`、`controllerPort`、`width`、`height`、`schoolTitle`、`gradesPerPage`、`pageSeconds`、`textSize`。安卓端只读取，不提供这些值的本地编辑。

## 原话机应用内的集成点

1. `HomeActivity`、`CallMainActivity`、`FaceSearchActivity` 等目前分别建立 `SerialPortManage`，且旧读取线程把单次 `read()` 结果直接换算为卡号。接入放学模块前，需要一个共享的串口所有者，在 `/dev/ttyS1` 上按完整 4 字节组帧，再根据当前业务状态分发卡片事件。不能让两个 Activity 同时读取同一串口。
2. `HomeActivity` 保持话机主页。放学时段显示“放学中”状态入口和最新识别结果；非时段显示下次放学时间。设置入口不放在话机上。
3. 建议通话和录音（请假/留言）优先占用音频。放学播报进入队列，前端明确显示“通话中，待播报 N 条”或“录音中，待播报 N 条”；音频释放后顺序播报，不能静默丢弃。这个优先级以及“当前业务认证时刷到班级卡是否同时触发放学”仍需产品确认，避免一次刷卡意外执行两项业务。
4. 播报文本只由班级名称和固定后缀生成：“三年级二班正在放学”。语速、音量、遍数由平台配置；功放/音柱的实际线路和音量范围需现场验收。
5. LED 仅在平台配置 `enabled=true` 且控制卡在线时接管动态区。通讯失败要在话机状态页显示，并保留语音和刷卡处理；控制卡恢复后刷新当前页。

## 当前验收边界

已在独立 APK 验证配置/班级/时间接口读取、中文语音引擎初始化和 LED 预览。实卡 3＋1 字节合并、固定文本播报、功放外放、实体控制卡显示，以及原话机通话/请假/留言冲突尚未完成现场验收。完成这些验证后再把相同能力合入原项目，避免用独立 APK 取代话机功能。
