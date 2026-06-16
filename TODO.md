# 项目 TODO

## 1. 客户端在线心跳上报

- 状态：已实现（2.0 MQTT）
- 目标：软件运行期间定时向服务器上传系统心跳数据，让后台可以随时查看学校客户端是否在线。
- 说明：这里的心跳指“本软件客户端在线状态”，不是 UDP 刷卡设备心跳；刷卡设备仍然按现状，仅刷卡时发送 UDP 数据。
- 当前实现：
  - `src/services/mqtt_service.py` 启动后连接 `111.6.173.61:1883`。
  - `client-id` 与用户名均使用 `device_no`，默认由本机 MAC 生成 12 位大写十六进制编号，例如 `AABBCCDDEEFF`。
  - 默认每 60 秒向 `v1/devices/me/telemetry` 发送 `HeartBeat.deviceNo` 和 `HeartBeat.time`。
  - MQTT 连接失败后默认每 60 秒重试；服务端中断重启后，客户端会自动重连并重新订阅下发指令 topic。
- 验收标准：
  - 软件启动后会自动周期性上报心跳。
  - 断网或服务器异常不会造成界面卡死、播报中断或程序崩溃。
  - 服务器后台能看到每个学校客户端的最近在线时间和在线/离线状态。

## 2. 接收服务端放学指令

- 状态：已实现（2.0 MQTT）
- 目标：软件允许接收服务器下发的放学指令，按指令把对应班级修改为“正在放学”状态，并触发本地语音播报。
- 当前实现：
  - MQTT 订阅 `v1/devices/me/rpc/request/+`，收到 `{"method":"ManualDismissal","params":...}` 后调用 `BroadcastManager.process_manual_dismissal`。
  - 指令按 `classType` + `classId` 查找本地班级，缺省时使用消息里的 `classVoiceName` / `classShowName`。
  - 指令触发会复用现有 TTS 队列并写入日志，原因标记为“服务端指令”。
  - 处理完成后向 `v1/devices/me/rpc/response/{request_id}` 回复 `{"result":"success"}`，异常时回复 `{"result":"fail","message":"..."}`。
- 验收标准：
  - 服务端下发某个班级放学指令后，客户端能更新该班级状态并立即播报。
  - 同一指令重复到达时不会重复播报。
  - 指令接收失败、网络异常或服务器异常不会影响刷卡播报主流程。
