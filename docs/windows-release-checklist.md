# Windows 发布与验收清单

本清单面向最终部署到学校现场的 Windows 主机，目标是确认当前版本符合以下约束：

- 原生桌面客户端，不依赖浏览器运行
- 低配主机可长期值守
- 默认进入值守看板
- 维护模式受保护，并且会自动回退

## 1. 打包前检查

在 Windows 目标环境中确认：

- 已安装 Python 3.10+
- 已安装项目依赖：`pip install -r requirements.txt`
- `pyttsx3` 在目标机器可正常调用系统语音
- Windows 防火墙已允许 UDP 监听端口

建议先执行：

```bash
python -m compileall main.py src tests build_exe.py
```

如果要先跑测试，可执行：

```bash
set QT_QPA_PLATFORM=offscreen
python -m unittest tests.test_main_window_smoke tests.test_maintenance_session tests.test_dashboard_presenter tests.test_udp_parser tests.test_broadcast_policy tests.test_dismissal_window tests.test_system_status -v
```

## 2. 打包命令

在 Windows 环境执行：

```bash
python build_exe.py
```

预期结果：

- 在 `dist/` 下生成 `SchoolDismissalSystem.exe`
- 不引入额外浏览器运行时
- 保持单文件 GUI 客户端形态

## 3. 首次启动验收

启动 `dist/SchoolDismissalSystem.exe` 后，逐项确认：

1. 默认以最大化窗口打开
2. 默认进入 `值守看板`，而不是配置/管理页面
3. 页面顶部能看到：
   - 当前状态横幅
   - 在线设备
   - 当前播报时段
   - 最近日志
4. 程序没有弹出控制台窗口
5. `logs/runtime.log` 和 `logs/crash.log` 已自动生成

## 4. 维护模式验收

按以下步骤检查：

1. 在主窗口按 `Ctrl+Shift+M`
2. 输入 4 位 `PIN`
3. 成功进入维护模式
4. 维护模式中可访问：
   - 学校设置
   - 放学时间
   - 设备管理
   - 设备管理中的刷卡器网络配置
   - 卡号映射
   - 立即同步
   - 测试模式
   - 语音语速与音量设置
5. 输入错误 `PIN` 时不能进入维护模式
6. 空闲超过超时时间后，自动退回值守看板
7. 超时后再次点击维护操作，应被拦截并要求重新验证

## 5. 核心业务验收

### UDP 监听

确认：

- 程序能成功监听配置端口
- 刷卡设备发包后，日志区出现新记录
- 无效包不会导致程序崩溃

### 刷卡器网络配置

确认：

- 可从 `维护模式 -> 设备管理 -> 配置网络` 进入配置弹窗
- 可以手动输入设备当前 IP 与命令端口
- 可以生成推荐固定 IP
- 写入固定 IP、子网掩码、网关、主机 IP、主机端口后，设备会重启
- 设备重启后可按新的 IP 恢复联网
- 如果现场要求 DHCP，界面会明确提示当前需借助厂家工具

### 语音播报

确认：

- 合法卡号在播报时段内会触发播报
- 同一班级在同一时间窗内不会重复播报
- `broadcast_count` 配置生效
- `tts_rate` 和 `tts_volume` 保存后重新播报即可生效
- TTS 异常不会导致程序整体退出

### 数据同步

确认：

- 学校 ID 正确时可以同步班级和时间表
- 同步失败时界面能看到状态变化
- 卡号字段带空格或逗号时不会产生空映射

## 6. 测试模式验收

在维护模式中开启 `测试模式` 后确认：

1. 本地播报仍然有效
2. 日志仍然记录
3. API 推送不会实际发送
4. 关闭测试模式后恢复正常推送行为

## 7. 长时间值守验收

建议至少挂运行 30 分钟到 2 小时，观察：

- 在线设备数不会只增不减
- 日志表不会无限增长
- 维护模式超时后能稳定回退
- 内存占用没有明显持续爬升
- UI 不会卡死
- 崩溃或异常前后的上下文可在 `logs/runtime.log` 查看

## 8. 交付前建议

建议最终交付前保留以下资料：

- 当前 `exe` 文件
- 对应 commit SHA
- `config/settings.json` 示例
- 现场使用说明（至少包含 `Ctrl+Shift+M`、PIN、测试模式说明）

当前分支可用提交历史可通过以下命令查看：

```bash
git log --oneline --decorate -10
```
