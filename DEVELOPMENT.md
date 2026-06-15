# 数智家校放学系统开发与发布规范

本规范用于统一 Windows 客户端的产品名称、版本展示、品牌图标、构建产物和 GitHub Release 发布流程。

## 1. 生效范围

- 本规范自下一次版本迭代开始正式启用。
- 已发布的 `v1.0.0` 正式版和 `v2.0.0-beta.1` 测试版不追溯重命名或重新打包。
- 后续所有 1.x 修复版本、2.0 测试版本及正式版本均须遵守本规范。

## 2. 产品与可执行文件命名

- 产品统一名称：`数智家校放学系统`。
- Windows 可执行文件统一名称：`数智家校放学系统.exe`。
- PyInstaller、GitHub Actions、Release 附件及相关脚本不得继续使用 `SchoolDismissalSystem.exe` 作为新版本产物名称。
- Release 压缩包采用以下命名格式：
  - 正式版：`数智家校放学系统-vX.Y.Z-windows-x64.zip`
  - 测试版：`数智家校放学系统-vX.Y.Z-beta.N-windows-x64.zip`

## 3. 版本号规范

- 版本号遵循语义化版本格式：`主版本.次版本.修订版本`。
- 正式版示例：`v2.0.0`、`v2.0.1`。
- 测试版示例：`v2.0.0-beta.2`。
- 从 2.0 版本开始，客户端必须在设置页或主界面的固定位置显示完整版本号。
- 界面显示格式统一为：`版本 vX.Y.Z` 或 `版本 vX.Y.Z-beta.N`。
- 界面版本号、Git Tag、Release 版本号和构建产物文件名必须保持一致，不允许手工维护多套不同版本号。
- 后续实现时应建立单一版本号来源，由界面展示和构建脚本共同读取。

## 4. 品牌图标规范

- 品牌源图统一使用 [`assets/branding/logo-vertical.png`](assets/branding/logo-vertical.png)。
- 未经产品负责人确认，不得替换、裁剪、变色或添加其他文字。
- Windows EXE 构建前须由该 PNG 生成包含常用尺寸的 `.ico` 文件，至少包含 `16x16`、`32x32`、`48x48`、`64x64`、`128x128` 和 `256x256`。
- PyInstaller 构建必须显式指定生成后的 `.ico` 文件。
- 构建验收时须检查资源管理器、任务栏和窗口标题栏中的图标显示是否正常。
- Logo 源图必须纳入 Git 管理，不得依赖个人电脑、企业微信缓存或网盘路径完成构建。

## 5. Windows 构建规范

- 正式 Release 产物必须由 GitHub Actions 的 Windows Runner 构建，不得上传无法追溯来源的本地临时包。
- 构建必须绑定明确的 Git Tag 和 Commit。
- 构建输出必须包含：
  - `数智家校放学系统.exe`
  - 带版本号的 Windows x64 ZIP 压缩包
  - ZIP 文件对应的 SHA256 校验文件
- 构建完成后至少验证：
  - EXE 文件名正确。
  - EXE 图标正确。
  - 客户端显示的版本号与 Git Tag 一致。
  - Windows x64 环境可正常启动。
  - ZIP 可以完整解压。
  - SHA256 校验值与上传文件一致。

## 6. GitHub Release 规范

- 构建验证通过后，必须更新或创建对应版本的 GitHub Release。
- 正式版 Release 使用正式 Git Tag，并设置为稳定版本。
- 测试版 Release 使用预发布 Tag，并标记为 `Pre-release`，不得覆盖稳定版的 `Latest` 状态。
- Release 必须上传带版本号的 Windows ZIP 和 SHA256 校验文件。
- GitHub Release API 会清洗中文资产物理文件名，因此 Release 下载文件名允许使用
  `school-dismissal-vX.Y.Z-windows-x64.zip`，但必须设置完整中文显示标签；GitHub Actions
  Artifact 和构建目录中的原始 ZIP 仍须使用“数智家校放学系统”中文命名。
- Release 说明至少包含：
  - 版本类型：正式版或测试版
  - 对应 Commit
  - 主要变更
  - 安装或升级方式
  - 已知风险和回退说明
- Release 发布后须核对 Tag 指向、附件数量、附件摘要、预发布状态及 Latest 状态。

## 7. 发布验收清单

每次发布前逐项确认：

- [ ] 产品名称为“数智家校放学系统”。
- [ ] EXE 名称为 `数智家校放学系统.exe`。
- [ ] 2.0 及以上版本在界面或设置页显示版本号。
- [ ] 版本号与 Git Tag、Release 和文件名一致。
- [ ] EXE 使用指定品牌 Logo 图标。
- [ ] GitHub Actions 构建成功。
- [ ] Windows 启动和核心功能验证通过。
- [ ] ZIP 完整性和 SHA256 校验通过。
- [ ] 对应 GitHub Release 已创建或更新。
- [ ] 测试版已标记为 `Pre-release`。
- [ ] 正式版与测试版均保留独立下载和回退入口。
