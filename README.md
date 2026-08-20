# Claude API Switcher V4

一个面向 Windows 的 Claude Code API 管理器。它能切换第三方 API、启动 Claude Code、管理本地 AI Gateway，也能在没有 Claude Code 环境时完成检测、安装和 PATH 修复。

最终用户直接运行 `Claude API Switcher V4.exe`，不需要 Python。

## 能做什么

- 管理 LongCat、Anthropic、OpenAI、DeepSeek、OpenRouter 和自定义 Provider。
- 测试 API 后再启用，减少错误配置直接进入工作会话的情况。
- 只为软件新启动的 Claude Code 进程注入 API 环境，不覆盖 `~/.claude/settings.json`。
- 自动寻找 Claude Code 和最近使用的项目目录。
- 一键安装或更新 Claude Code，修复 PATH，并运行 `claude doctor`。
- 支持跟随 Windows、浅色、深色三种主题。
- 提供 OpenAI 兼容的本地 AI Gateway、模型管理、Token 统计和请求日志。

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

1. 从 GitHub Releases 下载 `Claude API Switcher V4.exe`。
2. 双击运行。
3. 在“供应商”页添加或编辑 Provider。
4. 填写 API 地址、模型、API Key 和认证方式。
5. 点击“测试并使用”。
6. 选择项目目录，然后点击“快速启动 Claude”。

运行数据保存在：

```text
%LOCALAPPDATA%\ClaudeAPISwitcher
```

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

当前 V4 基线：285 项自动化测试全部通过，EXE 已在 Windows 本机实际启动验证。

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
