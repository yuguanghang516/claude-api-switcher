# gcli2api 启动隔离、测试诊断与额度排版修复设计

## 问题

V4.3.1 的 Gemini 供应商测试可能只显示通用 HTTP 400；用户级 Claude 设置中保存的 LongCat 环境又可能被复用的 Windows Terminal 会话带入新标签页，导致选择 Gemini 后终端仍显示 LongCat，并同时出现 `ANTHROPIC_AUTH_TOKEN` 与 `ANTHROPIC_API_KEY` 警告。额度列表还混用了 Consolas 与微软雅黑，视觉不统一。

## 设计

### 启动环境

- 启动子进程前删除全部供应商地址、模型和两套认证环境变量，再只写入当前供应商需要的变量。
- 不再把未使用的认证变量设置为空字符串；空值仍会被 Claude Code 判断为“已设置”。
- Gemini Antigravity 经过 8787 本地网关时，Claude 侧统一使用 Bearer Token；网关继续用 `x-api-key` 调用上游 gcli2api。这样可由进程环境中的单一 `ANTHROPIC_AUTH_TOKEN` 覆盖用户设置里的旧 LongCat Token。
- Windows Terminal 使用独立新窗口，并把供应商名称写入窗口标题，避免复用旧 LongCat 标签页或环境。
- 测试失败时不启动 Claude；快速启动只读取当前明确选中的供应商，不静默回退到列表中的第一个供应商。

### API 测试

- gcli2api 测试使用更接近 Claude Code 的内容块请求和足够的输出 Token，减少 thinking 模型的参数兼容问题。
- HTTP 400 显示经过长度限制和敏感字段过滤的上游错误；没有安全详情时才显示通用状态。
- 401、403、429 和超时的现有引导保持不变。

### 额度页排版

- 模型名、额度、重置时间和按钮统一使用 `Microsoft YaHei UI`。
- 模型名 13px semibold；状态与说明 12px，保持一致的垂直基线和行高。
- 运行日志继续使用等宽字体，因为它属于可复制诊断文本，不与额度卡混排。

## 验证

- 单元测试检查只注入一种认证变量、清除旧模型环境、Windows Terminal 强制新窗口。
- 单元测试检查 gcli 测试请求结构和 HTTP 400 脱敏错误。
- 回归测试保证测试失败不会启动 Claude，当前供应商缺失时不会自动回退到 LongCat。
- 实机用已保存 Gemini 配置启动 7861/8787，完成真实测试请求并检查新 Claude 进程环境。
- 全量测试、EXE 冒烟启动与正常关闭通过后，只替换本机桌面文件；本轮不推送 GitHub。
