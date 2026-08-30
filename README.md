# Claude API Switcher V4.5.0

一个面向 Windows 的 Claude Code API 管理器。它能切换第三方 API、启动 Claude Code、管理本地 AI Gateway，也能在没有 Claude Code 环境时完成检测、安装和 PATH 修复。

最终用户直接运行 `Claude API Switcher V4.5.0.exe`，不需要 Python。

## 能做什么

- 管理 LongCat、Anthropic、OpenAI、DeepSeek、OpenRouter 和自定义 Provider。
- 测试 API 后再启用，减少错误配置直接进入工作会话的情况。
- 只为软件新启动的 Claude Code 进程注入 API 环境，不覆盖 `~/.claude/settings.json`。
- 自动寻找 Claude Code 和最近使用的项目目录。
- 一键安装或更新 Claude Code，修复 PATH，并运行 `claude doctor`。
- 支持跟随 Windows、浅色、深色三种主题。
- 提供 OpenAI 兼容的本地 AI Gateway、模型管理、Token 统计和请求日志。
- 集成 gcli2api：个人用户使用 Antigravity，企业许可证用户可切换 Gemini CLI；支持可视化安装、启动、凭证 JSON 导入、逐模型额度、动态模型发现，并可一键加入 Claude Code 或本地网关。
- Antigravity 接入 Claude 时可走本软件 `/v1/messages` 网关：真实调用返回 429 后，优先在同系列文本模型中自动切换，最多尝试 3 个不同模型；配额快照与实测冲突时以真实 429 为准。
- 提供真实口径的额度监控：汇总 Claude Code 本机 Token、按供应商统计网关调用，并严格区分官方余额与不支持自动查询。
- 提供按本地时间统计的近 7 天 Token 热力图，按星期和小时显示活跃度。
- 使用原创蓝紫双向 API 路径图标，并同时应用到窗口、任务栏和 EXE。
- 单实例运行：重复双击只会激活现有窗口，避免配置、数据库和本地端口互相争抢。
- gcli2api 启停、额度读取和自动切换均有整体时间预算、并发保护、进程日志脱敏与部分成功提示。

## 界面分类

顶部只保留 5 个按任务划分的主入口：

| 入口 | 用途 |
|---|---|
| API 切换 | 管理 Claude 直连供应商、测试并切换 API、选择项目并启动 Claude |
| Gemini 反代 | 安装、启动、登录和接入 gcli2api |
| 本地网关 | 启停网关；通过“概览与模型 / 网关供应商 / 请求日志”管理网关功能 |
| 用量监控 | 查看本机 Claude Token、7 天热力图、网关分 API 用量和官方余额 |
| 环境设置 | 检测或安装 Claude Code，并切换跟随系统、浅色、深色主题 |

## 一键配置 Claude Code

打开“环境设置”页面后，软件会显示 Claude Code 的版本、路径、安装方式和健康状态。

如果未安装，点击“一键安装 / 更新”：

1. 优先使用 WinGet 安装 `Anthropic.ClaudeCode`。
2. WinGet 失败后，尝试 Anthropic 官方 Windows 安装器。
3. 安装完成后重新检测版本和 PATH。
4. 失败时显示网络、代理、权限、超时、文件占用或 PATH 未刷新等具体原因。

安装流程不会修改你的 Provider API Key。Claude Code 官方安装说明见：[Claude Code setup](https://code.claude.com/docs/en/setup)。

## 快速开始

### 使用已打包的 EXE

1. 从 GitHub Releases 下载 `Claude API Switcher V4.5.0.exe`。
2. 双击运行。
3. 在“API 切换”页添加或编辑供应商。
4. 填写 API 地址、模型、API Key 和认证方式。
5. 点击“测试并使用”。
6. 选择项目目录，然后点击“快速启动 Claude”。

运行数据保存在：

```text
%LOCALAPPDATA%\ClaudeAPISwitcher
```

## Gemini 反代（gcli2api）

打开独立的“Gemini 反代”页：

1. 点击“一键安装”。缺少 Git 或 uv 时，软件会通过 WinGet 安装固定的软件包，然后从官方仓库克隆并运行 `uv sync`。
2. 本地 API 密码由你自己设置，不是 Google API Key。可以直接输入，也可以点击“生成并复制”；启动时软件把同一个密码设置为 API 和面板密码。默认只监听 `127.0.0.1:7861`。
3. 个人 Google 账户选择“Antigravity（个人用户推荐）”，打开面板完成 Antigravity 认证并确认 AG 凭证；只有企业许可证账户才选择 Gemini CLI。
4. 也可以直接点“导入凭证 JSON”选择一个或多个 Antigravity 凭证；软件会先在本机校验 JSON，再通过 gcli2api 正式上传接口导入。
5. 点击“检测服务”获取模型列表和逐模型额度。列表只显示真实文本模型，不再重复显示“假流式/”和“流式抗截断/”别名；高能力 Claude、GPT 和 Gemini Pro/Thinking 模型优先排列。
6. 每个额度模型右侧都可点击“切换使用”。选择会立即同步到 Claude 供应商和自动切换网关，并跨重启保留。
7. 选择“接入 Claude（自动切换）”或“一键接入网关”。地址、模型、认证方式和本地 API 密码会自动填写。
8. 回到“API 切换”页点击 Gemini 供应商的“测试”或“测试并使用”。软件会先自动确保 7861 gcli2api 和 8787 本地切换网关已启动，再做真实 API 测试；若缺少登录、密码不匹配或端口被占用，会直接说明下一步。
9. “调用示例”提供 Anthropic、OpenAI 和 Gemini 三种可复制格式，示例只使用密码占位符。

如果已经通过终端安装，软件会自动识别 `%USERPROFILE%\gcli2api`、桌面、文档、LocalAppData、RoamingAppData 或 `GCLI2API_HOME` 指定的完整安装目录。检测到后直接显示“已安装，未运行”，启动时使用现有 `.venv`，不会要求重复安装。

点击“启动服务”后，软件会等待 HTTP 服务真正响应再显示成功。若尚未完成 Google OAuth，成功弹窗和卡片常驻指引会逐步提示“打开面板 → 使用同一密码登录 → 完成 OAuth → 返回检测服务”；进程退出、密码不一致、端口无响应和超时会显示对应处理方法。

常用地址：

| 用途 | 地址 |
|---|---|
| Antigravity Claude / Anthropic | `http://127.0.0.1:7861/antigravity` |
| Antigravity OpenAI 兼容 | `http://127.0.0.1:7861/antigravity/v1` |
| 企业 Gemini CLI Claude / Anthropic | `http://127.0.0.1:7861` |

gcli2api 是[独立第三方项目](https://github.com/su-kaka/gcli2api)，使用 CNC-1.0 非商业许可证，不属于本软件，也不会被打包进 EXE。本软件不会执行其 README 中的远程 PowerShell 安装脚本，不修改 PowerShell ExecutionPolicy；安装失败时会显示 WinGet、Git、uv、网络、权限或超时等具体原因。

## 用量与余额

“用量监控”页把不同来源的数据分开显示：

- **Claude Code 本机用量**：只读取 `%USERPROFILE%\.claude\projects` 会话文件中的时间、模型、消息 ID 和 `usage` 数字，不读取或保存聊天内容，也不扫描 Codex；正文 Token（输入 + 输出）和缓存 Token 分开展示，热力图只统计正文 Token。
- **各 API 本地网关用量**：按供应商汇总经过本软件网关的调用次数、成功/失败和输入/输出 Token；新记录会识别粗粒度客户端来源，并从 Claude 用量显示中排除 Codex。
- **供应商账户余额与模型额度**：只有官方公开、稳定的余额接口才显示“官方余额”。DeepSeek 使用官方余额接口；gcli2api Antigravity 显示 Google 返回的逐模型配额快照；LongCat、Anthropic、OpenAI 和普通 Google API Key 显示不支持自动查询的原因与平台入口。配额快照不等于实时可调用状态。

LongCat 公共文档目前没有账户余额 API，因此软件会显示本机统计到的 LongCat Token，但真实剩余必须点击“打开平台”到 LongCat Usage 页面查看。软件不会把调用成功或密钥有效伪装成“余额 100%”。

### 从源码运行

```powershell
git clone https://github.com/yuguanghang516/claude-api-switcher.git
cd claude-api-switcher
python -m pip install -r requirements.txt
python main.py
```

## 本地网关

“本地网关”页可以启动默认监听 `http://127.0.0.1:8787` 的本地服务，提供：

| 接口 | 方法 | 说明 |
|---|---|---|
| `/v1/chat/completions` | POST | OpenAI 兼容聊天补全 |
| `/v1/models` | GET | 获取可用模型 |
| `/v1/health` | GET | 健康检查 |

客户端示例：

```json
{
  "apiBase": "http://127.0.0.1:8787/v1",
  "apiKey": "any-value",
  "model": "gpt-4o"
}
```

网关会使用本机配置的真实 Provider 凭据。不要把运行数据目录、数据库或日志上传到 GitHub。

## 安全边界

- Claude 启动器的 API Key 保存在 Windows 凭据管理器中。
- 独立 AI Gateway 的 Key 保存在本机 SQLite 运行数据库中；请勿分享 `%LOCALAPPDATA%\ClaudeAPISwitcher`、数据库或日志。
- API Key 通过子进程环境传递，不生成含 Key 的临时脚本。
- API 测试禁止携带凭据跟随 HTTP 重定向。
- 导出配置不包含 API Key、内部凭据 ID 或认证 Token。
- V3 Web 默认只监听 `127.0.0.1`，首次管理员密码随机生成。
- MCP Shell 工具默认关闭。

独立 AI Gateway 的运行配置属于本机数据。更完整的说明见 [SECURITY.md](SECURITY.md)。

## 开发与测试

系统要求：

- Windows 10/11
- Python 3.10+（仅源码运行和开发需要）

安装开发依赖并运行测试：

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest tests -q
```

打包单文件 EXE：

```powershell
pyinstaller --noconfirm --distpath release build.spec
```

V4.5.0 重点提升可靠性与日常舒适度：修复 Claude 云路由环境污染、gcli2api 并发启停与额度长时间阻塞、自动切换跨配置串线、损坏配置覆盖、Provider 优先级导入丢失、路由开关假状态和更新链接边界；同时改善暗色对比度、热力图字号、帮助提示、编辑对话框与中英文动态状态。完整说明见 [`docs/releases/v4.5.0.md`](docs/releases/v4.5.0.md)。

## 仓库边界

以下内容不会进入源码仓库：

- `data/`、`logs/`、`backups/`
- `build/`、`dist/`、`release/`
- API Key、Token、数据库、个人配置和编辑器缓存

EXE 只通过 GitHub Release 附件发布，不提交进 Git 历史。

## 参与贡献

提交前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。Bug 报告请删除 API Key、Token、个人路径和完整日志中的敏感内容。

## License

[MIT](LICENSE)
