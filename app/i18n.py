"""
国际化模块 (i18n)
提供中英文界面文本切换
所有 UI 字符串集中在此，方便维护和扩展
"""

# 支持的语言
LANGUAGES = [
    ("中文", "zh"),
    ("English", "en"),
]

# 翻译字典：key -> {lang_code: text}
TEXTS = {
    # === 通用 ===
    "app_title": {
        "zh": "Claude Code API Switcher",
        "en": "Claude Code API Switcher",
    },
    "app_subtitle": {
        "zh": "管理并一键切换 Claude Code 使用的 API",
        "en": "Manage & switch Claude Code API with one click",
    },
    "export": {
        "zh": "导出配置",
        "en": "Export",
    },
    "import": {
        "zh": "导入配置",
        "en": "Import",
    },

    # === gcli2api / Gemini 反代 ===
    "gcli_title": {
        "zh": "Gemini 反代 · gcli2api",
        "en": "Gemini Proxy · gcli2api",
    },
    "gcli_subtitle": {
        "zh": "安装、检测并连接独立的 gcli2api 服务；支持 Claude、OpenAI 与 Gemini 三种调用格式。",
        "en": "Install, detect, and connect the independent gcli2api service with Claude, OpenAI, and Gemini-compatible APIs.",
    },
    "gcli_password": {"zh": "API 密码", "en": "API Password"},
    "gcli_model": {"zh": "默认模型", "en": "Default Model"},
    "gcli_detect": {"zh": "检测服务", "en": "Check"},
    "gcli_install": {"zh": "一键安装", "en": "Install"},
    "gcli_start": {"zh": "启动服务", "en": "Start"},
    "gcli_panel": {"zh": "打开面板", "en": "Open Panel"},
    "gcli_add_claude": {"zh": "添加到 Claude", "en": "Add to Claude"},
    "gcli_add_gateway": {"zh": "添加到网关", "en": "Add to Gateway"},
    "gcli_examples": {"zh": "调用示例", "en": "Examples"},

    # === 当前状态 ===
    "current_status": {
        "zh": "当前状态",
        "en": "Current Status",
    },
    "status_provider_label": {
        "zh": "Provider",
        "en": "Provider",
    },
    "status_model_label": {
        "zh": "模型",
        "en": "Model",
    },
    "status_url_label": {
        "zh": "API 地址",
        "en": "API URL",
    },
    "status_state_label": {
        "zh": "状态",
        "en": "Status",
    },
    "status_project_label": {
        "zh": "项目目录",
        "en": "Project Dir",
    },
    "status_ready": {
        "zh": "● 已就绪",
        "en": "● Ready",
    },
    "status_not_selected": {
        "zh": "未选择",
        "en": "Not selected",
    },
    "status_not_set": {
        "zh": "未设置",
        "en": "Not set",
    },

    # === Provider 区域 ===
    "api_providers": {
        "zh": "API Providers",
        "en": "API Providers",
    },
    "add_provider": {
        "zh": "+ 添加 Provider",
        "en": "+ Add Provider",
    },
    "no_providers_hint": {
        "zh": "暂无 Provider，请点击上方按钮添加",
        "en": "No providers yet. Click the button above to add one.",
    },
    "current_badge": {
        "zh": "当前",
        "en": "Active",
    },
    "fallback_badge": {
        "zh": "备用",
        "en": "Backup",
    },
    "priority_label": {
        "zh": "优先级 {}",
        "en": "Priority {}",
    },
    "key_prefix": {
        "zh": "Key: {}",
        "en": "Key: {}",
    },
    "set_current": {
        "zh": "设为当前",
        "en": "Set Active",
    },
    "is_current": {
        "zh": "✓ 当前使用",
        "en": "✓ Active",
    },
    "test": {
        "zh": "测试",
        "en": "Test",
    },
    "edit": {
        "zh": "编辑",
        "en": "Edit",
    },
    "delete": {
        "zh": "删除",
        "en": "Delete",
    },
    "testing": {
        "zh": "测试中...",
        "en": "Testing...",
    },

    # === 启动区域 ===
    "launch_title": {
        "zh": "启动 Claude Code",
        "en": "Launch Claude Code",
    },
    "project_dir": {
        "zh": "项目目录",
        "en": "Project Dir",
    },
    "project_placeholder": {
        "zh": "选择你的项目目录...",
        "en": "Select your project directory...",
    },
    "browse": {
        "zh": "浏览",
        "en": "Browse",
    },
    "launch_button": {
        "zh": "▶  使用当前 API 启动 Claude Code",
        "en": "▶  Launch Claude Code with Current API",
    },

    # === 设置区域 ===
    "settings": {
        "zh": "设置",
        "en": "Settings",
    },
    "auto_failover": {
        "zh": "自动故障切换",
        "en": "Auto Failover",
    },
    "sync_claude": {
        "zh": "同步更新 Claude Code 配置",
        "en": "Sync Claude Code Config",
    },
    "language": {
        "zh": "语言",
        "en": "Language",
    },
    "run_log": {
        "zh": "运行日志",
        "en": "Log",
    },
    "clear": {
        "zh": "清空",
        "en": "Clear",
    },

    # === 对话框 ===
    "dialog_add_title": {
        "zh": "添加 Provider",
        "en": "Add Provider",
    },
    "dialog_edit_title": {
        "zh": "编辑 Provider - {}",
        "en": "Edit Provider - {}",
    },
    "provider_config": {
        "zh": "Provider 配置",
        "en": "Provider Configuration",
    },
    "field_name": {
        "zh": "Provider 名称 *",
        "en": "Provider Name *",
    },
    "field_name_placeholder": {
        "zh": "例如：LongCat",
        "en": "e.g. LongCat",
    },
    "tooltip_name": {
        "zh": "Provider 就是你给这个 API 配置起的名字。\n"
              "比如 LongCat、DeepSeek、Anthropic 等。\n"
              "起个好记的名字就行，方便你在多个 API 之间切换。\n"
              "Provider = 服务商，就是提供 AI 能力的那一方。",
        "en": "A Provider is a name you give to this API setup.\n"
              "e.g. LongCat, DeepSeek, Anthropic, etc.\n"
              "Just pick a memorable name — it helps you switch between APIs.\n"
              "Provider = the service that gives you AI access.",
    },
    "field_url": {
        "zh": "API Base URL *",
        "en": "API Base URL *",
    },
    "field_url_placeholder": {
        "zh": "https://api.example.com/anthropic",
        "en": "https://api.example.com/anthropic",
    },
    "field_model": {
        "zh": "主模型名称 *",
        "en": "Primary Model *",
    },
    "field_model_placeholder": {
        "zh": "例如：claude-sonnet-4-20250514",
        "en": "e.g. claude-sonnet-4-20250514",
    },
    "field_fast_model": {
        "zh": "快速模型（可选）",
        "en": "Fast Model (optional)",
    },
    "field_fast_model_placeholder": {
        "zh": "不填则使用主模型",
        "en": "Defaults to primary model if empty",
    },
    "field_key": {
        "zh": "API Key *",
        "en": "API Key *",
    },
    "field_key_placeholder": {
        "zh": "你的 API Key",
        "en": "Your API Key",
    },
    "field_priority": {
        "zh": "优先级",
        "en": "Priority",
    },
    "field_priority_placeholder": {
        "zh": "数字越小优先级越高",
        "en": "Lower number = higher priority",
    },
    "enable_provider": {
        "zh": "启用此 Provider",
        "en": "Enable this Provider",
    },
    "set_as_fallback": {
        "zh": "作为故障备用 API",
        "en": "Use as failover backup",
    },
    "cancel": {
        "zh": "取消",
        "en": "Cancel",
    },
    "save": {
        "zh": "保存",
        "en": "Save",
    },

    # === Tooltip 小白解释 ===
    "tooltip_url": {
        "zh": "API 服务的网址地址。\n"
              "Claude Code 通过这个地址发送对话请求。\n"
              "通常以 https:// 开头，以 /anthropic 结尾。\n"
              "每个服务商都会提供这个地址。",
        "en": "The API server URL.\n"
              "Claude Code sends chat requests here.\n"
              "Usually starts with https:// and ends with /anthropic.\n"
              "Your provider gives you this address.",
    },
    "tooltip_model": {
        "zh": "你要使用的 AI 模型名称。\n"
              "例如 claude-sonnet-4-20250514、LongCat-2.0 等。\n"
              "需要和 API Key 对应的账号支持的模型一致。\n"
              "填错可能导致 404 或 403 错误。",
        "en": "The AI model name you want to use.\n"
              "e.g. claude-sonnet-4-20250514, LongCat-2.0, etc.\n"
              "Must match a model your API key has access to.\n"
              "Wrong name may cause 404 or 403 errors.",
    },
    "tooltip_fast_model": {
        "zh": "快速但稍弱的模型，用于简单任务。\n"
              "比如自动补全、小回答等。\n"
              "不填就会用同一个主模型处理所有任务。",
        "en": "A faster but weaker model for simple tasks.\n"
              "Used for autocomplete, short replies, etc.\n"
              "If empty, the primary model handles everything.",
    },
    "tooltip_key": {
        "zh": "你的 API 密钥，相当于账号密码。\n"
              "从服务商官网申请获得。\n"
              "程序会安全保存在 Windows 凭据管理器中。\n"
              "不会明文写在配置文件里。",
        "en": "Your API key — like a password.\n"
              "Get it from your provider's website.\n"
              "Stored securely in Windows Credential Manager.\n"
              "Never saved as plain text in config files.",
    },
    "tooltip_priority": {
        "zh": "数字越小优先级越高。\n"
              "当开启「自动故障切换」时，\n"
              "程序会按优先级顺序尝试可用的 Provider。",
        "en": "Lower number = higher priority.\n"
              "When Auto Failover is enabled,\n"
              "the program tries providers in priority order.",
    },
    "tooltip_fallback": {
        "zh": "勾选后，此 Provider 会被当作备用。\n"
              "当主 Provider 出问题时，\n"
              "自动切换到这个备用 API。",
        "en": "If checked, this provider is used as backup.\n"
              "When the main provider fails,\n"
              "the app switches to this backup automatically.",
    },
    "tooltip_enable": {
        "zh": "取消勾选可以禁用此 Provider。\n"
              "禁用的 Provider 不会出现在切换列表中。",
        "en": "Uncheck to disable this provider.\n"
              "Disabled providers won't appear in the switch list.",
    },

    # === 主界面 Tooltip ===
    "tooltip_status_provider": {
        "zh": "当前正在使用的 API 服务商名称。\n"
              "所有请求都会发给这个 Provider。",
        "en": "The currently active API provider.\n"
              "All requests go to this provider.",
    },
    "tooltip_status_model": {
        "zh": "当前使用的 AI 模型。\n"
              "不同的模型有不同的能力和价格。",
        "en": "The currently active AI model.\n"
              "Different models have different capabilities and pricing.",
    },
    "tooltip_status_url": {
        "zh": "当前 API 的服务地址。\n"
              "请求会被发送到这个网址。",
        "en": "The current API server address.\n"
              "Requests are sent to this URL.",
    },
    "tooltip_status_state": {
        "zh": "Provider 的就绪状态。\n"
              "绿色表示已配置好可以正常使用。",
        "en": "Provider readiness status.\n"
              "Green means it's configured and ready to use.",
    },
    "tooltip_status_project": {
        "zh": "启动 Claude Code 时使用的项目目录。\n"
              "Claude 会在这个目录下工作。",
        "en": "Project directory used when launching Claude Code.\n"
              "Claude will work in this directory.",
    },
    "tooltip_set_current": {
        "zh": "点击把这个 Provider 设为当前使用。\n"
              "之后启动 Claude Code 就会用这个 API。",
        "en": "Click to set this provider as active.\n"
              "Claude Code will use this API when launched.",
    },
    "tooltip_test": {
        "zh": "测试这个 Provider 是否可用。\n"
              "会发送一个简单的请求检查连通性。\n"
              "建议添加新 Provider 后先测试一下。",
        "en": "Test if this provider is reachable.\n"
              "Sends a simple request to check connectivity.\n"
              "Recommended after adding a new provider.",
    },
    "tooltip_edit": {
        "zh": "修改这个 Provider 的配置。\n"
              "可以改名称、地址、模型、Key 等。",
        "en": "Edit this provider's configuration.\n"
              "Change name, URL, model, key, etc.",
    },
    "tooltip_delete": {
        "zh": "删除这个 Provider。\n"
              "删除后无法恢复，请谨慎操作。",
        "en": "Delete this provider.\n"
              "Cannot be undone. Please be careful.",
    },
    "tooltip_add_provider": {
        "zh": "添加一个新的 API Provider。\n"
              "你需要填写名称、API 地址、模型和 Key。",
        "en": "Add a new API provider.\n"
              "You'll need to fill in name, URL, model, and key.",
    },
    "tooltip_priority_badge": {
        "zh": "数字越小优先级越高。\n"
              "自动故障切换时会按这个顺序尝试。",
        "en": "Lower number = higher priority.\n"
              "Auto failover tries providers in this order.",
    },
    "tooltip_fallback_badge": {
        "zh": "这个是备用 Provider。\n"
              "主 Provider 出问题时会自动切过来。",
        "en": "This is a backup provider.\n"
              "Automatically used when the main one fails.",
    },
    "tooltip_current_badge": {
        "zh": "这个 Provider 正在使用中。\n"
              "启动 Claude Code 会用它。",
        "en": "This provider is currently active.\n"
              "It will be used when launching Claude Code.",
    },
    "tooltip_auto_failover": {
        "zh": "开启后，如果当前 Provider 请求失败，\n"
              "程序会自动切换到下一个可用的 Provider。\n"
              "切换顺序按「优先级」数字从小到大。",
        "en": "If enabled and the current provider fails,\n"
              "the app auto-switches to the next available one.\n"
              "Switches in priority order (lowest number first).",
    },
    "tooltip_sync_claude": {
        "zh": "开启后，切换 Provider 时\n"
              "会自动把配置写入 Claude Code 的\n"
              "settings.json 文件。\n"
              "建议保持开启。",
        "en": "If enabled, switching providers\n"
              "auto-updates Claude Code's settings.json.\n"
              "Recommended to keep this on.",
    },
    "tooltip_launch_btn": {
        "zh": "用当前选中的 Provider 启动 Claude Code。\n"
              "Claude 会在你选择的项目目录下工作。",
        "en": "Launch Claude Code with the current provider.\n"
              "Claude will work in your selected project directory.",
    },
    "tooltip_browse_btn": {
        "zh": "选择你的项目文件夹。\n"
              "Claude Code 会在这个目录中执行。",
        "en": "Choose your project folder.\n"
              "Claude Code will operate in this directory.",
    },
    "tooltip_export": {
        "zh": "把配置导出为 JSON 文件。\n"
              "注意：不包含 API Key！\n"
              "可以用来备份或迁移到其他电脑。",
        "en": "Export configuration to a JSON file.\n"
              "Note: API keys are NOT included!\n"
              "Use for backup or migrating to another PC.",
    },
    "tooltip_import": {
        "zh": "从 JSON 文件导入配置。\n"
              "会覆盖当前所有 Provider 设置。\n"
              "注意：API Key 需要重新手动填写。",
        "en": "Import configuration from a JSON file.\n"
              "Will overwrite all current provider settings.\n"
              "Note: API keys must be re-entered manually.",
    },
    "tooltip_project_dir": {
        "zh": "Claude Code 的工作目录。\n"
              "文件读写、命令行操作都会在这个目录下进行。",
        "en": "Claude Code's working directory.\n"
              "File operations and commands run in this folder.",
    },

    # === 消息框 ===
    "msg_confirm_delete": {
        "zh": "确定要删除 Provider '{}' 吗？\n\n此操作不可撤销。",
        "en": "Delete Provider '{}'?\n\nThis cannot be undone.",
    },
    "msg_select_provider_first": {
        "zh": "请先选择一个 Provider",
        "en": "Please select a provider first.",
    },
    "msg_select_project_first": {
        "zh": "请选择项目目录",
        "en": "Please select a project directory.",
    },
    "msg_project_not_exist": {
        "zh": "项目目录不存在：{}",
        "en": "Project directory does not exist: {}",
    },
    "msg_export_success": {
        "zh": "配置已导出到：\n{}",
        "en": "Config exported to:\n{}",
    },
    "msg_import_confirm": {
        "zh": "导入将覆盖当前所有 Provider 配置，是否继续？",
        "en": "Import will overwrite all current providers. Continue?",
    },
    "msg_import_success": {
        "zh": "配置已导入：\n{}",
        "en": "Config imported:\n{}",

    },
    "msg_name_required": {
        "zh": "Provider 名称不能为空",
        "en": "Provider name is required.",
    },
    "msg_url_required": {
        "zh": "API Base URL 不能为空",
        "en": "API Base URL is required.",
    },
    "msg_model_required": {
        "zh": "模型名称不能为空",
        "en": "Model name is required.",
    },
    "msg_name_exists": {
        "zh": "已存在名为 '{}' 的 Provider",
        "en": "A provider named '{}' already exists.",
    },

    # === v2.3 安全快速启动 ===
    "app_subtitle_safe": {
        "zh": "安全切换 API，一键启动 Claude（不修改全局配置）",
        "en": "Switch APIs and launch Claude safely without changing global settings",
    },
    "quick_launch": {
        "zh": "▶  快速启动 Claude",
        "en": "▶  Quick Launch Claude",
    },
    "quick_launch_testing": {"zh": "正在检测 API…", "en": "Testing API…"},
    "quick_launch_starting": {"zh": "正在启动 Claude…", "en": "Starting Claude…"},
    "project_source_auto": {"zh": "自动检测", "en": "Auto"},
    "project_source_manual": {"zh": "手动选择", "en": "Manual"},
    "session_only_note": {
        "zh": "仅对新打开的 Claude 窗口生效，不会覆盖 ~/.claude/settings.json",
        "en": "Only affects the new Claude window; global settings stay unchanged",
    },
    "selected_badge": {"zh": "当前选择", "en": "Selected"},
    "test_and_use": {"zh": "测试并使用", "en": "Test & Use"},
    "status_not_tested": {"zh": "未测试", "en": "Not tested"},
    "status_testing": {"zh": "检测中…", "en": "Testing…"},
    "status_available": {"zh": "可用", "en": "Available"},
    "status_unavailable": {"zh": "不可用", "en": "Unavailable"},
    "status_disabled": {"zh": "已禁用", "en": "Disabled"},
    "field_auth_mode": {"zh": "认证方式", "en": "Authentication"},
    "tooltip_auth_mode": {
        "zh": "第三方 API 通常使用 Bearer Token；Anthropic 官方 API 通常使用 x-api-key。",
        "en": "Third-party APIs usually use Bearer Token; Anthropic commonly uses x-api-key.",
    },
    "notice": {"zh": "提示", "en": "Notice"},
    "error": {"zh": "错误", "en": "Error"},
    "test_failed": {"zh": "API 检测失败", "en": "API Test Failed"},
    "launch_failed": {"zh": "启动失败", "en": "Launch Failed"},
    "save_failed": {"zh": "保存失败", "en": "Save Failed"},
    "select_project_dir": {"zh": "选择项目目录", "en": "Select Project Directory"},
    "confirm_import": {
        "zh": "导入会替换当前 Provider 列表，且所有 API Key 都需要重新填写。是否继续？",
        "en": "Import replaces the provider list and requires re-entering all API keys. Continue?",
    },
    "confirm_delete_title": {"zh": "确认删除", "en": "Confirm Delete"},
    "confirm_delete": {
        "zh": "确定删除 Provider“{}”吗？其 API Key 也会从凭据管理器中删除。",
        "en": "Delete provider '{}'? Its API key will also be removed.",
    },
    "field_enabled": {"zh": "启用这个 Provider", "en": "Enable this provider"},
    "msg_no_provider_key": {
        "zh": "没有找到已启用且已填写 API Key 的 Provider，请先配置一个 API。",
        "en": "No enabled provider with an API key was found. Configure one first.",
    },
    "msg_no_project_dir": {
        "zh": "无法识别可用项目目录，请检查用户目录权限。",
        "en": "No usable project directory was found. Check your home directory permissions.",
    },
    "msg_claude_not_found": {
        "zh": "找不到 Claude Code；已检查 PATH、npm 和 ~/.local/bin。",
        "en": "Claude Code was not found in PATH, npm, or ~/.local/bin.",
    },
    "msg_launch_prerequisite_missing": {
        "zh": "启动前目录或 Claude 命令失效，请重试。",
        "en": "The project directory or Claude command became unavailable. Try again.",
    },

    # === 启动检查 ===
    "startup_check": {
        "zh": "启动检查",
        "en": "Startup Check",
    },
    "check_pass": {
        "zh": "✓ {}",
        "en": "✓ {}",
    },
    "check_warn": {
        "zh": "⚠ {}",
        "en": "⚠ {}",
    },
    "check_fail": {
        "zh": "✗ {}",
        "en": "✗ {}",
    },
    "check_claude_found": {
        "zh": "已找到 claude 命令",
        "en": "claude command found",
    },
    "check_claude_missing": {
        "zh": "未找到 claude 命令，请确保 Claude Code 已安装",
        "en": "claude command not found. Please install Claude Code.",
    },
    "check_keyring_ok": {
        "zh": "凭据管理器正常",
        "en": "Credential Manager OK",
    },
    "check_keyring_fail": {
        "zh": "凭据管理器不可用，API Key 可能无法保存",
        "en": "Credential Manager unavailable. API keys may not be saved.",
    },
    "check_config_ok": {
        "zh": "配置目录正常",
        "en": "Config directory OK",
    },
    "check_config_fail": {
        "zh": "无法创建配置目录：{}",
        "en": "Cannot create config directory: {}",
    },

    # === V1 AI Gateway ===
    "gateway_tab": {"zh": "AI 网关", "en": "AI Gateway"},
    "v2_dashboard_tab": {"zh": "V2 智能", "en": "V2 Smart"},
    "dashboard_tab": {"zh": "仪表板", "en": "Dashboard"},
    "models_tab": {"zh": "模型管理", "en": "Models"},
    "logs_tab": {"zh": "请求日志", "en": "Logs"},
    "providers_tab": {"zh": "供应商", "en": "Providers"},
    "settings_tab": {"zh": "设置", "en": "Settings"},

    # === 仪表板 ===
    "today_requests": {"zh": "今日请求", "en": "Today Requests"},
    "today_tokens": {"zh": "今日 Token", "en": "Today Tokens"},
    "model_count": {"zh": "模型数量", "en": "Models"},
    "api_status": {"zh": "API 状态", "en": "API Status"},
    "gateway_status": {"zh": "网关状态", "en": "Gateway Status"},
    "gateway_running": {"zh": "运行中", "en": "Running"},
    "gateway_stopped": {"zh": "已停止", "en": "Stopped"},
    "start_gateway": {"zh": "启动网关", "en": "Start Gateway"},
    "stop_gateway": {"zh": "停止网关", "en": "Stop Gateway"},
    "gateway_url": {"zh": "网关地址", "en": "Gateway URL"},
    "copy_url": {"zh": "复制地址", "en": "Copy URL"},
    "copied": {"zh": "已复制", "en": "Copied"},
    "quick_stats": {"zh": "快速统计", "en": "Quick Stats"},
    "total_requests": {"zh": "总请求数", "en": "Total Requests"},
    "success_rate": {"zh": "成功率", "en": "Success Rate"},
    "avg_response_time": {"zh": "平均响应", "en": "Avg Response"},
    "recent_activity": {"zh": "最近活动", "en": "Recent Activity"},
    "no_data": {"zh": "暂无数据", "en": "No data"},
    "ms_unit": {"zh": "ms", "en": "ms"},

    # === 模型管理 ===
    "add_model": {"zh": "+ 添加模型", "en": "+ Add Model"},
    "edit_model": {"zh": "编辑模型", "en": "Edit Model"},
    "model_name": {"zh": "模型名称", "en": "Model Name"},
    "display_name": {"zh": "显示名称", "en": "Display Name"},
    "provider": {"zh": "供应商", "en": "Provider"},
    "input_price": {"zh": "输入价格", "en": "Input Price"},
    "output_price": {"zh": "输出价格", "en": "Output Price"},
    "context_length": {"zh": "上下文长度", "en": "Context Length"},
    "status": {"zh": "状态", "en": "Status"},
    "enabled": {"zh": "已启用", "en": "Enabled"},
    "disabled": {"zh": "已禁用", "en": "Disabled"},
    "actions": {"zh": "操作", "en": "Actions"},
    "price_unit": {"zh": "元/1M tokens", "en": "/1M tokens"},
    "search_model": {"zh": "搜索模型...", "en": "Search models..."},
    "filter_provider": {"zh": "筛选供应商", "en": "Filter Provider"},
    "all_providers": {"zh": "全部供应商", "en": "All Providers"},
    "toggle_status": {"zh": "切换状态", "en": "Toggle"},
    "confirm_delete_model": {"zh": "确定删除模型 '{}' 吗？", "en": "Delete model '{}'?"},

    # === 供应商管理 (Gateway) ===
    "add_provider_title": {"zh": "添加供应商", "en": "Add Provider"},
    "edit_provider_title": {"zh": "编辑供应商", "en": "Edit Provider"},
    "provider_type": {"zh": "供应商类型", "en": "Provider Type"},
    "api_key": {"zh": "API Key", "en": "API Key"},
    "test_key": {"zh": "测试 Key", "en": "Test Key"},
    "key_valid": {"zh": "Key 有效", "en": "Key Valid"},
    "key_invalid": {"zh": "Key 无效", "en": "Key Invalid"},
    "save_provider": {"zh": "保存供应商", "en": "Save Provider"},
    "provider_added": {"zh": "供应商添加成功", "en": "Provider added"},
    "provider_updated": {"zh": "供应商更新成功", "en": "Provider updated"},
    "provider_deleted": {"zh": "供应商已删除", "en": "Provider deleted"},
    "confirm_delete_provider": {"zh": "确定删除供应商 '{}' 吗？相关模型也会被删除。", "en": "Delete provider '{}'? Related models will also be deleted."},
    "api_key_encrypted": {"zh": "API Key 仅保存在本机网关数据库，请勿上传数据目录", "en": "API Key stays in the local gateway database; never upload the data directory"},
    "custom_provider": {"zh": "自定义", "en": "Custom"},

    # === 请求日志 ===
    "request_time": {"zh": "请求时间", "en": "Time"},
    "model": {"zh": "模型", "en": "Model"},
    "input_tokens": {"zh": "输入 Token", "en": "Input Tokens"},
    "output_tokens": {"zh": "输出 Token", "en": "Output Tokens"},
    "total_tokens": {"zh": "总 Token", "en": "Total Tokens"},
    "response_time": {"zh": "响应时间", "en": "Response Time"},
    "success": {"zh": "成功", "en": "Success"},
    "failed": {"zh": "失败", "en": "Failed"},
    "error_reason": {"zh": "错误原因", "en": "Error Reason"},
    "clear_logs": {"zh": "清空日志", "en": "Clear Logs"},
    "export_logs": {"zh": "导出日志", "en": "Export Logs"},
    "filter_status": {"zh": "筛选状态", "en": "Filter Status"},
    "all_status": {"zh": "全部状态", "en": "All"},
    "clear_logs_confirm": {"zh": "确定清空所有日志吗？此操作不可撤销。", "en": "Clear all logs? This cannot be undone."},
    "refresh_logs": {"zh": "刷新", "en": "Refresh"},

    # === 网关说明 ===
    "gateway_info_title": {"zh": "如何使用本地网关", "en": "How to Use Local Gateway"},
    "gateway_info_1": {"zh": "1. 启动网关后，任何支持 OpenAI API 的客户端都可以连接。", "en": "1. Once started, any OpenAI-compatible client can connect."},
    "gateway_info_2": {"zh": "2. 在客户端中设置 API Base URL 为：", "en": "2. Set API Base URL in your client to:"},
    "gateway_info_3": {"zh": "3. API Key 可以填写任意值（网关会使用供应商的真实 Key）。", "en": "3. API Key can be any value (gateway uses real provider keys)."},
    "gateway_info_4": {"zh": "4. 支持的客户端：OpenCode、Claude Code、Continue.dev 等", "en": "4. Supported clients: OpenCode, Claude Code, Continue.dev, etc."},
}


def t(key: str, lang: str = "zh", *args) -> str:
    """
    获取翻译文本
    :param key: 文本键名
    :param lang: 语言代码 ("zh" 或 "en")
    :param args: 格式化参数（用于包含 {} 的字符串）
    :return: 翻译后的文本
    """
    entry = TEXTS.get(key)
    if not entry:
        return key  # 找不到就返回键名本身，方便排查
    text = entry.get(lang, entry.get("zh", key))
    if args:
        try:
            text = text.format(*args)
        except (IndexError, KeyError):
            pass
    return text
