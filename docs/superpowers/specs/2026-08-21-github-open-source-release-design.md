# Claude API Switcher V4 GitHub 开源发布设计

## 目标

将当前 Windows 桌面项目发布为公开 GitHub 仓库 `claude-api-switcher`，并创建 `v4.0.0` Release。仓库面向需要管理 Claude Code 第三方 API、本地网关和 Claude Code 安装环境的 Windows 用户。

## 发布结构

- 默认分支：`main`
- 许可证：MIT
- 主要语言：中文；关键标题和功能名保留常见英文术语
- Release：`v4.0.0`
- Release 附件：`Claude API Switcher V4.exe`
- 源码仓库不提交 EXE；二进制文件只作为 Release 附件分发

## 仓库内容

提交以下内容：

- `app/`、`tests/`、`docs/`
- `main.py`、`build.spec`
- `requirements.txt`、`requirements-dev.txt`
- `README.md`、`LICENSE`、`.gitignore`、`.dockerignore`
- Docker 和 Windows 启动辅助文件
- V2/V3 升级报告

排除以下内容：

- API Key、Token、凭据、个人配置
- `data/`、`logs/`、`backups/`
- `build/`、`dist/`、`release/`
- `__pycache__/`、`.pytest_cache/`、覆盖率文件
- 数据库、日志、临时文件、快捷方式和编辑器配置

## README 与发布文案

README 以实际可用功能开头，包含功能列表、界面主题、Claude Code 一键安装、快速开始、安全边界、源码运行、测试、打包和贡献说明。所有主张以当前代码和测试结果为依据，不使用夸张宣传。

Release 文案列出 V4 的主要变化、安装方法、SHA256、测试结果和已知边界。安装源说明链接到 Anthropic 官方 Claude Code 文档。

## 安全检查

推送前执行文件名和内容两层扫描。发现疑似凭据时停止发布，先修复忽略规则或移除敏感数据。使用 `git status` 和 `git ls-files` 确认提交清单，确保运行数据和 EXE 不进入源码提交历史。

## 验证

- 运行完整测试套件，要求全部通过
- 确认桌面 EXE 与 Release 附件 SHA256 一致
- 推送后检查公开仓库默认分支、README、LICENSE 和文件清单
- 创建 Release 后检查标签、版本说明、附件名称、大小与下载地址

## 失败处理

- 未登录 GitHub：使用用户已登录的浏览器完成建仓或连接 GitHub 能力
- 仓库名已占用：停止并报告实际冲突，不擅自改名
- 推送或附件上传失败：保留本地提交，报告失败阶段和可重试方式
- 敏感信息扫描命中：不执行远端推送，先处理命中项
