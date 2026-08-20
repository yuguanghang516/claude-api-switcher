# 参与贡献

欢迎提交 Bug 修复、文档改进和范围明确的功能。开始前请先确认：

1. 不提交 API Key、Token、日志、数据库或个人配置。
2. UI 改动同时检查浅色和深色主题。
3. 网络操作必须有超时、错误说明，并避免凭据跟随重定向。
4. 修改后运行完整测试：

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest tests -q
```

提交信息建议使用简短的英文类型前缀，例如：

```text
fix: resolve provider dialog routing
feat: add Claude Code environment diagnostics
docs: clarify release installation
```

Pull Request 请说明改动目的、验证方式，以及是否涉及凭据、网络请求或本机文件。
