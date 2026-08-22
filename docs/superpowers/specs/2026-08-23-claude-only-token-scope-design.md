# Claude 专属 Token 统计口径设计

日期：2026-08-23

## 现状

Claude 本机统计当前只扫描 `%USERPROFILE%\.claude\projects`，不会读取 `%USERPROFILE%\.codex`。本机现有 Claude 会话记录中，缓存读取 Token 远高于输入和输出 Token，而界面把四类 Token 全部合并为“合计”，因此容易被误认为混入了 Codex 用量。

本地网关统计当前没有记录客户端来源；如果 Codex 被手工配置为使用该网关，它的调用会与其他网关客户端混在一起。

## 目标

- Claude 本机统计继续只读取 `.claude/projects`，增加防回归测试，明确禁止把 `.codex` 作为默认扫描源。
- 页面标题和说明明确写为“Claude Code 本机用量（不含 Codex）”。
- 输入与输出作为“正文 Token”展示；缓存创建和缓存读取作为“缓存 Token”单独展示。
- 7 天热力图只使用输入与输出 Token，避免缓存读取量掩盖真实交互活跃度。
- 保留底层四类原始数字，不把缓存 Token 删除或伪装成正文 Token。
- 本地网关新增客户端来源字段；User-Agent 或明确客户端头识别为 Codex 的请求仍正常代理，但不进入界面用量汇总。
- 无法识别来源的历史网关记录单独标记为“历史来源未知”，不并入“Claude Code”数字。

## 数据与隐私

客户端来源只保存规范化枚举，例如 `claude_code`、`codex`、`other`、`legacy_unknown`，不保存完整 User-Agent。升级数据库时新增字段，不删除旧请求日志。

Claude 会话扫描仍只读取时间、模型、消息 ID 和 usage 数字，不读取或保留聊天内容。界面诊断信息显示扫描目录和文件数量，但不显示会话文件名。

## 展示

Claude Code 区域显示：今日调用次数、今日正文 Token、今日缓存 Token、本月正文 Token、本月缓存 Token和扫描文件数量。模型列表同样把正文与缓存分开。

网关区域继续按供应商显示调用次数和 Token，但默认排除 `client_source=codex`。页面脚注明确说明：“Codex 请求不会计入本页用量；来源未知的历史记录单列。”

## 验证

- 默认扫描器只指向 `.claude/projects`，即使 `.codex` 存在也不会枚举其中任何文件。
- 同一 Claude 流式消息仍按消息 ID 取最大 usage 快照，避免重复累计。
- 正文 Token 等于输入加输出；缓存 Token 等于缓存创建加缓存读取；热力图只累计正文 Token。
- Codex User-Agent 被规范化为 `codex`，且不进入供应商用量汇总。
- Claude、其他客户端和历史未知来源按设计展示，不删除旧数据。
- 完整测试与 EXE 界面验证通过。
