# Claude API Switcher V4.1 gcli2api / Gemini 反代集成设计

## 目标

为公开发布的 Windows EXE 增加 `gcli2api` 专用集成，让普通用户无需理解 Anthropic、OpenAI 和 Gemini 三套协议即可完成安装引导、服务检测、Provider 配置、模型发现、Claude Code 启动和调用示例复制。集成必须在浅色、深色和跟随系统主题下保持一致，并且不能把密码、OAuth 凭据或第三方运行数据写入仓库、日志或错误信息。

## 已确认的上游能力

`gcli2api` 默认监听 `http://127.0.0.1:7861`，同时提供：

- Claude 兼容接口：`/v1/messages`
- OpenAI 兼容接口：`/v1/chat/completions` 与 `/v1/models`
- Gemini 原生接口：`/v1/models/{model}:generateContent` 与 `:streamGenerateContent`
- Bearer、`x-goog-api-key` 和 URL `key` 等认证方式

Claude API Switcher 的“快速启动 Claude”直接使用 Claude 兼容接口；本地 AI Gateway 使用 OpenAI 兼容接口。软件不再把 `gcli2api` 当作 Google 官方 Gemini API，也不在本地重复转换协议。

## 产品结构与界面

在现有 Provider 页面加入一个克制的“Gemini CLI 反代”入口，而不是新增顶级导航。入口使用现有语义主题 token、同样的圆角和间距，并在浅色/深色主题中使用紫色作为 Gemini 身份色，绿色、黄色、红色只表示状态。

入口包含四个连续状态：

1. **未检测到**：显示“安装 gcli2api”和“查看项目”按钮。
2. **已安装、未运行**：显示安装路径、版本或提交信息，以及“启动服务”按钮。
3. **服务已运行、未完成认证**：显示“打开管理面板”，明确要求完成 Google OAuth。
4. **可以调用**：显示端点、可用模型数量，以及“一键添加到 Claude”和“一键添加到 AI Gateway”。

所有耗时操作在线程中执行。按钮进入明确的加载状态，完成后显示成功或就近错误；禁止界面无反馈冻结。字段始终保留可见标签，密码默认隐藏，复制按钮使用文本标签而不是仅图标。

## 安装与第三方许可边界

`gcli2api` 使用 CNC-1.0 非商业许可证。Claude API Switcher 保持 MIT 许可，但：

- 不复制、不修改、不打包 `gcli2api` 源码、依赖、OAuth 凭据或运行数据。
- 安装按钮只调用上游公开安装流程，并在执行前显示仓库地址、将安装的依赖、目标目录和非商业许可提示。
- 用户必须主动确认后才执行；取消不产生任何更改。
- 默认安装目录为 `%LOCALAPPDATA%\ClaudeAPISwitcher\integrations\gcli2api`，不得写入桌面或源码仓库。
- 优先使用已安装的 `git` 与 `uv`。缺失时，在同一次确认中列出将通过 WinGet 安装的依赖；用户同意后使用固定包 ID 安装，WinGet 不可用或安装失败时提供官方链接和可复制诊断。
- 不直接执行网络返回内容的 `Invoke-Expression`。下载或克隆过程使用参数数组启动受信任的可执行文件，仓库来源固定为 `https://github.com/su-kaka/gcli2api.git`。
- 安装结果属于第三方组件，用户需遵守其许可证；README 和界面均提供原项目与许可证链接。

为了公开发布的可预测性，第一版不安装或接管 Scoop，也不修改 PowerShell 执行策略。依赖引导仅使用 WinGet 的 `Git.Git` 与 `astral-sh.uv` 固定包 ID；每一步都显示进度，失败后停止后续安装并解释原因。

## 组件设计

新增独立的 `Gcli2ApiManager`，把第三方进程管理与 CustomTkinter 界面隔离。它负责：

- 查找受管安装目录和用户自定义安装目录。
- 读取本地版本/提交信息，不解析或上传凭据。
- 检查 `127.0.0.1:7861` 健康状态。
- 使用 Bearer 密码请求 `/v1/models`，区分网络、认证、OAuth/凭据和空模型错误。
- 通过参数数组直接启动受管虚拟环境中的 `.venv\Scripts\python.exe web.py`，不执行批处理、不使用 `shell=True`，并记录 PID 以便只管理本软件启动的进程。
- 打开本地管理面板，但不自动填写面板密码。
- 生成 Claude、OpenAI 和 Gemini 三种调用示例，示例中只显示占位符，不回显真实密码。

现有主 Provider 配置新增 `provider_kind`，值为 `gcli2api` 时预填：

- Base URL：`http://127.0.0.1:7861`
- 认证：Bearer Token
- 主模型：优先从 `/v1/models` 选择稳定的 Gemini Pro 模型；无服务时使用 `gemini-2.5-pro` 作为可编辑占位值
- 快速模型：从模型列表选择 Flash；找不到时留空并使用主模型

现有 Gateway Provider 新增 `gcli2api` 类型：

- Base URL：`http://127.0.0.1:7861/v1`
- 认证：Bearer Token
- 模型来自 `/v1/models`，不把上游 README 中的临时模型列表硬编码为真相

## 数据流

### Claude Code

用户选择 gcli2api Provider后，软件先以 `/v1/messages` 发送最小请求。通过后，仅向新启动的 Claude Code 子进程注入：

- `ANTHROPIC_BASE_URL=http://127.0.0.1:7861`
- `ANTHROPIC_AUTH_TOKEN=<API_PASSWORD>`
- `ANTHROPIC_MODEL=<所选 Gemini 模型>`

不修改全局 Claude 配置，不在命令行中放置密码。

### 本地 AI Gateway

客户端继续请求 `http://127.0.0.1:8787/v1/chat/completions`。Gateway 根据模型配置把 OpenAI 格式转发到 `http://127.0.0.1:7861/v1/chat/completions`，保留非流式、流式、tools 和错误状态。模型列表来自本机数据库中已启用模型。

### 直接调用说明

界面提供三个可复制示例：

- Claude Code：由软件一键启动，不要求用户手动设置环境变量。
- OpenAI SDK/curl：Base URL 为 `http://127.0.0.1:7861/v1`。
- Gemini 原生 curl：Base URL 为 `http://127.0.0.1:7861`，使用 `x-goog-api-key` 或 Bearer。

所有示例使用 `YOUR_GCLI2API_PASSWORD`，不读取剪贴板、不自动粘贴真实密码。

## 错误分类与恢复建议

- 连接拒绝：服务未启动，提供“启动服务”。
- 超时：提示检查代理、防火墙和 gcli2api 日志。
- 401：API 密码错误，说明 `API_PASSWORD` 与 `PANEL_PASSWORD` 的区别。
- 403：上游账号或 Google 项目权限不足。
- 404：Base URL、端点或模型名称错误。
- 429：凭据额度耗尽或触发限流，提示到面板检查凭据状态。
- `/v1/models` 为空：服务存在但没有可用 OAuth 凭据，提供“打开管理面板”。
- 安装失败：分别报告 Git/uv 缺失、网络/DNS、GitHub 无法访问、目录权限、文件占用和依赖同步失败；不显示密码或环境中的 Token。
- 端口占用：指出占用 PID，但不自动结束非本软件启动的进程。

## 安全要求

- gcli2api API 密码继续保存在 Windows Credential Manager。
- HTTP 只允许 `localhost`、`127.0.0.1` 和 `::1`；用户配置远程 gcli2api 时必须使用 HTTPS。
- 请求禁止携带凭据跟随重定向。
- 日志对 Authorization、API Key、URL `key` 参数和 OAuth 数据脱敏。
- 删除集成只删除本软件创建且经过路径验证的受管目录；本版不提供自动卸载，避免误删用户数据。
- 第三方进程停止只针对本软件记录的 PID；锁定、PID 不匹配或路径越界时停止操作并提示用户。

## 测试矩阵

新增自动化测试至少覆盖：

- Provider 预设、Base URL 归一化和模型选择。
- Claude `/v1/messages` 与 OpenAI `/v1/chat/completions` 的正确端点。
- `/v1/models` 成功、空列表、401、403、404、429、5xx、超时、DNS 和连接拒绝。
- 流式响应原样转发且 `[DONE]` 正确结束。
- tools/tool_choice 保留。
- 本地 HTTP 允许、远程 HTTP 拒绝、HTTPS 允许。
- 不跟随重定向、不在错误/日志/调用示例中泄露密码。
- 安装命令不使用 `shell=True` 或 `Invoke-Expression`，目标目录保持在应用数据目录内。
- WinGet 依赖安装使用固定包 ID，用户取消或任一步失败后不得继续克隆或同步依赖。
- 不停止未知 PID、不删除用户自定义目录。
- 中文、英文文案完整，浅色、深色和跟随系统主题均能渲染入口和所有状态。
- 现有完整测试套件全部通过。

发布前执行真实 Windows 验证：使用隔离测试目录安装或连接 gcli2api，完成一次 OAuth 后分别验证模型发现、Claude Code 非流式调用、OpenAI 流式调用、错误提示、主题切换和干净退出。真实 OAuth 凭据和运行数据不进入测试夹具、截图、提交或 Release。

## 发布

版本升级为 `4.1.0`，统一更新应用版本、构建元数据、README、Release 文稿和窗口显示。PyInstaller 生成新的单文件 EXE，桌面副本与 GitHub Release 附件 SHA256 必须一致。发布说明明确：

- `gcli2api` 是独立第三方项目，不属于 Claude API Switcher。
- 用户需自行遵守其非商业许可证和 Google 服务条款。
- EXE 不附带 Google OAuth 凭据，不保证第三方服务或模型长期可用。
- 模型以运行时 `/v1/models` 返回为准。

## 非目标

- 不把 gcli2api 源码或 Python 运行时打进 EXE。
- 不绕过 Google OAuth、账号限制、配额或地区限制。
- 不自动上传、下载、编辑或删除 gcli2api 凭据。
- 不承诺第三方模型名称永久有效。
- 不在本版实现远程 gcli2api 服务器部署。
