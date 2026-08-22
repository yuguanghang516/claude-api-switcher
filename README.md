# Claude API Switcher V4.1.1

一个面向 Windows 的 Claude Code API 管理器。它能切换第三方 API、启动 Claude Code、管理本地 AI Gateway，也能在没有 Claude Code 环境时完成检测、安装和 PATH 修复。

最终用户直接运行 `Claude API Switcher V4.1.1.exe`，不需要 Python。

## 能做什么

- 管理 LongCat、Anthropic、OpenAI、DeepSeek、OpenRouter 和自定义 Provider。
- 测试 API 后再启用，减少错误配置直接进入工作会话的情况。
- 只为软件新启动的 Claude Code 进程注入 API 环境，不覆盖 `~/.claude/settings.json`。
- 自动寻找 Claude Code 和最近使用的项目目录。
- 一键安装或更新 Claude Code，修复 PATH，并运行 `claude doctor`。
- 支持跟随 Windows、浅色、深色三种主题。
- 提供 OpenAI 兼容的本地 AI Gateway、模型管理、Token 统计和请求日志。
- 集成 gcli2api：可视化安装、启动、OAuth 状态检测、动态模型发现，并可一键加入 Claude Code 或本地网关。

## 一键配置 Claude Code

打开“设置”页面后，软件会显示 Claude Code 的版本、路径、安装方式和健康状态。

如果未安装，点击“一键安装 / 更新”：

1. 优先使用 WinGet 安装 `Anthropic.ClaudeCode`。
2. WinGet 失败后，尝试 Anthropic 官方 Windows 安装器。
3. 安装完成后重新检测版本和 PATH。
4. 失败时显示网络、代理、权限、超时、文件占用或 PATH 未刷新等具体原因。

安装流程不会修改你的 Provider API Key。Claude Code 官方安装说明见：[Claude Code setup](https://code.claude.com/docs/en/setup)。

## 快速开始

### 使用已打包的 EXE

1. 从 GitHub Releases 下载 `Claude API Switcher V4.1.1.exe`。
2. 双击运行。
3. 在“供应商”页添加或编辑 Provider。
4. 填写 API 地址、模型、API Key 和认证方式。
5. 点击“测试并使用”。
6. 选择项目目录，然后点击“快速启动 Claude”。

运行数据保存在：

```text
%LOCALAPPDATA%\ClaudeAPISwitcher
```

## Gemini 反代（gcli2api）

“供应商”页顶部提供独立的 gcli2api 控制卡：

1. 点击“一键安装”。缺少 Git 或 uv 时，软件会通过 WinGet 安装固定的软件包，然后从官方仓库克隆并运行 `uv sync`。
2. 填写你自己的 API 密码并启动服务。默认只监听 `127.0.0.1:7861`。
3. 点击“打开面板”，在 gcli2api 中完成 Google OAuth；本软件不会下载、上传或打包 OAuth 凭据。
4. 点击“检测服务”获取实际模型列表，再选择“添加到 Claude”或“添加到网关”。
5. “调用示例”提供 Anthropic、OpenAI 和 Gemini 三种可复制格式，示例只使用密码占位符。

如果已经通过终端安装，软件会自动识别 `%USERPROFILE%\gcli2api`、桌面、文档、LocalAppData、RoamingAppData 或 `GCLI2API_HOME` 指定的完整安装目录。检测到后直接显示“已安装，未运行”，启动时使用现有 `.venv`，不会要求重复安装。

常用地址：

| 用途 | 地址 |
|---|---|
| Claude / Anthropic | `http://127.0.0.1:7861` |
| OpenAI 兼容 | `http://127.0.0.1:7861/v1` |
| Gemini 原生 | `http://127.0.0.1:7861/v1/models/{model}:generateContent` |

gcli2api 是[独立第三方项目](https://github.com/su-kaka/gcli2api)，使用 CNC-1.0 非商业许可证，不属于本软件，也不会被打包进 EXE。本软件不会执行其 README 中的远程 PowerShell 安装脚本，不修改 PowerShell ExecutionPolicy；安装失败时会显示 WinGet、Git、uv、网络、权限或超时等具体原因。

### 从源码运行

```powershell
git clone https://github.com/yuguanghang516/claude-api-switcher.git
cd claude-api-switcher
python -m pip install -r requirements.txt
python main.py
```

## AI Gateway

“AI 网关”页可以启动默认监听 `http://127.0.0.1:8787` 的本地服务，提供：

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

当前 V4.1.1 基线：327 项自动化测试全部通过；Windows EXE 已实际启动，并完成终端安装识别、浅色、深色、调用示例弹窗和干净退出验证。

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
