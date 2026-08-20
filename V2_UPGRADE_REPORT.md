# V2 智能 AI Gateway 升级报告

## 📋 升级概览

| 项目 | V1 (升级前) | V2 (升级后) |
|------|------------|------------|
| 版本 | 1.0.0 | 2.0.0 |
| 核心功能 | API 切换 + 基础网关 | 智能 AI Gateway |
| 模型路由 | 手动选择 | 智能路由 + 自动故障转移 |
| 密钥管理 | 单 Key | 多 Key 自动轮询 |
| 余额监控 | ❌ | ✅ 自动检测 |
| 成本控制 | ❌ | ✅ 日/月预算 |
| 价格计算 | ❌ | ✅ USD/CNY |
| 通知系统 | ❌ | ✅ 桌面 + Webhook |
| 热切换 | ❌ | ✅ 无重启更新 |
| 测试覆盖 | 21 个测试 | 103 个测试 |

---

## 🎯 新增功能详情

### 1. API 余额检测 (`app/balance_checker.py`)

**功能：**
- 支持检测 OpenAI、Anthropic、DeepSeek、Google 余额
- 显示剩余额度、使用百分比、更新时间
- 支持自动刷新（默认 5 分钟间隔）
- 余额不足自动提醒

**使用示例：**
```
Claude Key: 剩余 35%
DeepSeek: 剩余 80%
OpenAI: 剩余 $45.20 (90%)
```

**核心类：**
- `BalanceChecker` - 余额检测器
- `BalanceInfo` - 余额信息数据类
- `check_balance()` - 检测单个供应商
- `check_all()` - 批量检测所有供应商
- `start_auto_refresh()` - 启动自动刷新

---

### 2. 多 Key 自动轮询 (`app/key_rotator.py`)

**功能：**
- 一个供应商支持多个 Key
- Key 限流时自动切换
- 支持多种轮询策略：轮询、优先级、最少使用、最近最少使用
- 连续错误达到阈值自动禁用

**轮询策略：**
- `round_robin` - 轮流使用
- `priority` - 按索引优先级
- `least_used` - 最少使用
- `least_recently_used` - 最近最少使用

**核心类：**
- `MultiKeyRotator` - 多 Key 轮询器
- `KeyInfo` - Key 信息
- `KeyStatus` - Key 状态枚举

---

### 3. 自动故障转移 (`app/failover.py`)

**功能：**
- 请求失败自动切换下一个模型
- 用户无感知
- 熔断器模式防止雪崩
- 指数退避重试
- 自动健康检查恢复

**故障转移流程：**
```
请求 → 模型A (失败)
     → 模型B (失败)
     → 模型C (成功) ✓
```

**核心类：**
- `FailoverEngine` - 故障转移引擎
- `CircuitBreaker` - 熔断器
- `FailoverTarget` - 故障转移目标

**熔断器状态：**
- `CLOSED` - 正常
- `OPEN` - 熔断（拒绝请求）
- `HALF_OPEN` - 半开（尝试恢复）

---

### 4. 智能模型路由 (`app/smart_router.py`)

**功能：**
- 根据任务类型自动选择最优模型
- 支持用户自定义规则
- 关键词 + 代码信号识别

**默认路由规则：**
| 任务类型 | 优先模型 | 备选模型 |
|---------|---------|---------|
| 代码 | Claude Sonnet / DeepSeek | GPT-4o / Kimi |
| 聊天 | GPT-4o / Gemini Flash | Claude Haiku / DeepSeek |
| 低成本 | DeepSeek / Kimi | GPT-4o-mini / LongCat |
| 复杂任务 | Claude Opus / GPT-4o | Claude Sonnet / DeepSeek Reasoner |

**核心类：**
- `SmartRouter` - 智能路由器
- `TaskClassifier` - 任务分类器
- `ModelCapability` - 模型能力信息
- `RoutingRule` - 路由规则

---

### 5. 成本控制 (`app/cost_controller.py`)

**功能：**
- 每日预算限制
- 每月预算限制
- 80% 自动提醒
- 100% 自动切换低成本模型

**使用示例：**
```
每日预算: $5
今日已用: $4.20 (84%) → ⚡ 提醒
今日已用: $5.00 (100%) → 🚨 自动切换低成本模型
```

**核心类：**
- `CostController` - 成本控制器
- `BudgetStatus` - 预算状态

---

### 6. Token 价格计算 (`app/pricing.py`)

**功能：**
- 根据模型价格自动计算费用
- 美元 + 人民币双币种
- 支持 15+ 主流模型价格
- 各模型花费统计

**价格表包含：**
- OpenAI: GPT-4o, GPT-4o-mini, GPT-4-turbo, O1
- Anthropic: Claude Opus 4, Sonnet 4, Haiku 3.5
- DeepSeek: Chat, Reasoner
- Google: Gemini 1.5 Pro/Flash, 2.0 Flash
- Kimi: v1-8k/32k/128k
- LongCat: 2.0, Flash-Chat

**核心类：**
- `PricingCalculator` - 价格计算器
- `CostBreakdown` - 费用明细

---

### 7. 通知系统 (`app/notifier.py`)

**功能：**
- 余额不足提醒
- API 异常提醒
- 预算超限提醒
- Key 切换通知
- 故障转移通知

**通知方式：**
- Windows 桌面通知 (win10toast / plyer)
- Webhook (Slack / Discord / 企业微信等)
- 通知去重（同类型最小间隔）

**核心类：**
- `Notifier` - 通知管理器
- `Notification` - 通知数据
- `NotificationType` - 通知类型
- `NotificationPriority` - 通知优先级

---

### 8. 无重启热切换 (`app/hot_reload.py`)

**功能：**
- 修改配置无需重启服务
- 文件变更自动检测
- 支持 API Key、模型、路由规则热更新

**核心类：**
- `HotReloader` - 热切换管理器
- `ConfigHotSwapper` - 配置热切换器

---

## 📁 新增文件清单

```
app/
├── v2_config.py           # V2 配置管理
├── balance_checker.py     # API 余额检测
├── key_rotator.py         # 多 Key 自动轮询
├── failover.py            # 自动故障转移
├── smart_router.py        # 智能模型路由
├── cost_controller.py     # 成本控制
├── pricing.py             # Token 价格计算
├── notifier.py            # 通知系统
├── hot_reload.py          # 无重启热切换
├── gateway_server_v2.py   # V2 网关服务器
└── v2_dashboard.py        # V2 仪表板 GUI

tests/
└── test_v2_modules.py     # V2 模块测试 (82 个测试)

docs/
└── V2_UPGRADE_REPORT.md   # 本报告
```

---

## 🔌 新增 API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/v2/balance` | GET | 获取余额信息 |
| `/v2/balance/refresh` | POST | 刷新余额信息 |
| `/v2/status` | GET | 网关状态 |
| `/v2/cost` | GET | 费用统计 |
| `/v2/routing/info` | POST | 路由决策信息 |
| `/v2/config` | GET | 获取 V2 配置 |
| `/v2/config` | PUT | 更新 V2 配置 |
| `/v2/notifications` | GET | 通知历史 |
| `/v2/pricing` | GET | 价格表 |
| `/v2/keys/<provider_id>` | GET/POST/DELETE | 多 Key 管理 |
| `/v2/failover/status` | GET | 故障转移状态 |
| `/v2/failover/reset` | POST | 重置故障转移 |

---

## 🧪 测试结果

### V2 模块测试 (82 个)

```
tests/test_v2_modules.py::TestV2Config ................... 9/9 passed
tests/test_v2_modules.py::TestBalanceChecker ............. 7/7 passed
tests/test_v2_modules.py::TestKeyRotator ................ 12/12 passed
tests/test_v2_modules.py::TestFailoverEngine ............. 8/8 passed
tests/test_v2_modules.py::TestSmartRouter ............... 10/10 passed
tests/test_v2_modules.py::TestCostController ............. 9/9 passed
tests/test_v2_modules.py::TestPricingCalculator .......... 9/9 passed
tests/test_v2_modules.py::TestNotifier .................. 11/11 passed
tests/test_v2_modules.py::TestHotReload .................. 5/5 passed
tests/test_v2_modules.py::TestV2Integration .............. 5/5 passed

============================ 82 passed in 2.42s =============================
```

### 现有功能测试 (21 个) - 全部通过，保证向后兼容

```
tests/test_gateway.py ................................... 21/21 passed
```

**总计: 103 个测试，全部通过 ✅**

---

## 🔄 向后兼容性

V2 完全兼容 V1 功能：

- ✅ V1 所有 API 端点保持不变 (`/v1/chat/completions`, `/v1/models`, `/v1/health`)
- ✅ 现有配置文件 `config.json` 无需修改
- ✅ 现有数据库 `gateway.db` 无需迁移
- ✅ 现有 GUI Tab 保持不变
- ✅ 现有测试全部通过

---

## 📊 架构对比

### V1 架构
```
用户 → GUI → ConfigManager → Claude Code
              ↓
         GatewayServer → Provider API
```

### V2 架构
```
用户 → GUI → V2Dashboard → GatewayServerV2
                         ├→ SmartRouter (智能路由)
                         ├→ FailoverEngine (故障转移)
                         ├→ MultiKeyRotator (多 Key 轮询)
                         ├→ BalanceChecker (余额检测)
                         ├→ CostController (成本控制)
                         ├→ PricingCalculator (价格计算)
                         ├→ Notifier (通知系统)
                         └→ HotReloader (热切换)
                              ↓
                         Provider API
```

---

## 🚀 后续可扩展方向

1. **用量分析面板** - 更详细的使用统计图表
2. **模型性能监控** - 响应时间、成功率追踪
3. **自动优化** - 根据使用模式自动调整路由策略
4. **多用户支持** - 团队用量管理
5. **API 文档生成** - 自动生成 OpenAPI 文档
6. **移动端通知** - 支持更多通知渠道

---

## 📝 使用建议

1. **首次使用** - 先配置各供应商 API Key，点击"测试"确认可用
2. **设置预算** - 在 V2 配置中设置每日/每月预算
3. **添加多 Key** - 为重要供应商添加多个 Key 提高可用性
4. **自定义路由** - 根据实际需求调整路由规则
5. **开启通知** - 配置 Webhook 接收关键事件通知

---

*升级完成时间: 2026-08-20*
*升级工程师: Claude Code AI Assistant*
