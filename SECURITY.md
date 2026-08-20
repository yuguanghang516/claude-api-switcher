# 安全说明

## API Key 与本机数据

Claude 启动器使用 Windows 凭据管理器保存 API Key。导出的配置文件不包含 API Key、内部凭据 ID 或认证 Token。

独立 AI Gateway 的运行数据保存在本机数据目录。请不要把 `%LOCALAPPDATA%\ClaudeAPISwitcher`、源码目录中的 `data/`、日志、数据库或个人配置上传到公开仓库。

## 默认安全边界

- V3 Web 服务默认只监听 `127.0.0.1`。
- 首次管理员密码随机生成，不使用公开的固定密码。
- MCP Shell 工具默认关闭，必须显式配置才能启用。
- API 连通性测试禁止携带凭据跟随 HTTP 重定向。

## 报告安全问题

请不要在公开 Issue 中粘贴 API Key、Token、完整配置、数据库或日志。报告问题时请删除个人路径和凭据，只保留复现步骤、版本号与经过脱敏的错误信息。
