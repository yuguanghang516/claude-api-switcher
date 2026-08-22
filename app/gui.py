"""Claude API Switcher V4：Claude Code 环境、API 切换与本地网关。"""
import os
import queue
import threading
import webbrowser
from datetime import datetime
from typing import Optional
import customtkinter as ctk
from tkinter import filedialog, messagebox

from .claude_launcher import ClaudeLauncher
from .config_manager import ConfigManager
from .i18n import LANGUAGES, t
from .logger import AppLogger
from .path_resolver import ClaudeCommandResolver, ProjectDirectoryResolver
from .provider_manager import ProviderManager
from .tooltip import TooltipButton
from .db_manager import DatabaseManager
from .gateway_server import GatewayServer, SUPPORTED_PROVIDERS
from .model_manager import ModelManager
from .gateway_gui import GatewayPanel
from .v2_dashboard import V2DashboardPanel
from .v2_config import V2ConfigManager
from .gateway_server_v2 import GatewayServerV2
from .claude_environment import ClaudeEnvironmentManager
from .gcli2api_manager import Gcli2ApiManager, Gcli2ApiStatus, DEFAULT_BASE_URL
from .theme import LIGHT, DARK, theme
from .version import APP_VERSION_NAME, app_title


ctk.set_default_color_theme("blue")

# CustomTkinter 的双色值会随 light/dark 自动切换，所有页面共用同一套语义色。
ACCENT = (LIGHT.accent, DARK.accent)
ACCENT_HOVER = (LIGHT.accent_hover, DARK.accent_hover)
ACCENT_TEXT = (LIGHT.accent_text, DARK.accent_text)
SUCCESS = (LIGHT.success, DARK.success)
SUCCESS_DARK = (LIGHT.success_dark, DARK.success_dark)
DANGER = (LIGHT.danger, DARK.danger)
INFO = (LIGHT.info, DARK.info)
INFO_DARK = (LIGHT.info_dark, DARK.info_dark)
BG_PRIMARY = (LIGHT.bg_primary, DARK.bg_primary)
BG_SURFACE = (LIGHT.bg_surface, DARK.bg_surface)
BG_ELEVATED = (LIGHT.bg_elevated, DARK.bg_elevated)
BG_INPUT = (LIGHT.bg_input, DARK.bg_input)
TEXT_PRIMARY = (LIGHT.text_primary, DARK.text_primary)
TEXT_SECONDARY = (LIGHT.text_secondary, DARK.text_secondary)
TEXT_MUTED = (LIGHT.text_muted, DARK.text_muted)
BORDER = (LIGHT.border, DARK.border)
GEMINI_ACCENT = ("#6D4AFF", "#A78BFA")
GEMINI_HOVER = ("#5936E8", "#8B5CF6")
FONT_FAMILY = "Microsoft YaHei UI"
FONT_MONO = "Consolas"
PAD_XS, PAD_SM, PAD_MD, PAD_LG, PAD_XL = 4, 8, 12, 16, 24


class MainWindow:
    def __init__(self, data_dir: str, logs_dir: str):
        self.logger = AppLogger(logs_dir)
        self.config = ConfigManager(data_dir)
        theme.apply_mode(self.config.get_theme())
        self.provider_manager = ProviderManager(self.config)
        self.launcher = ClaudeLauncher()
        self.project_resolver = ProjectDirectoryResolver()
        self.claude_command_resolver = ClaudeCommandResolver()
        self.claude_environment = ClaudeEnvironmentManager()
        self.gcli2api = Gcli2ApiManager(data_dir, logger=self.logger)
        self._gcli_status = Gcli2ApiStatus(
            state="unknown", base_url=DEFAULT_BASE_URL,
            install_dir=self.gcli2api.install_dir,
            message="等待检测")
        self._gcli_busy = False
        self._environment_queue = queue.Queue()
        self._environment_busy = False
        self.lang = self.config.get_language() or "zh"
        self._bindings = []
        self._tooltips = []
        self._test_results = {}
        self._testing = set()
        self._pending_test_actions = {}
        self._result_queue = queue.Queue()
        self.provider_status_labels = {}
        self.provider_action_buttons = {}
        self._auto_project_dir = ""
        self._project_source = ""
        self._launch_busy = False

        # === V1 AI Gateway 新增模块 ===
        self.db = DatabaseManager(data_dir)
        self.model_manager = ModelManager(self.db, self.logger)
        self.gateway = GatewayServer(db_manager=self.db, logger=self.logger)
        self.model_manager.init_defaults()

        # === V2 智能网关模块 ===
        self.v2_config = V2ConfigManager(data_dir)
        self.gateway_v2 = GatewayServerV2(
            db_manager=self.db, logger=self.logger, v2_config=self.v2_config)

        self.root = ctk.CTk()
        self.root.title(app_title())
        self.root.geometry("1080x820")
        self.root.minsize(900, 680)
        self.root.configure(fg_color=BG_PRIMARY)
        self._build_ui()
        self._resolve_project_directory()
        self._update_language()
        self.root.after(100, self._poll_test_results)
        self.root.after(150, self._poll_environment_results)
        self.root.after(350, self._detect_claude_environment)
        self.root.after(700, self._detect_gcli2api)

        # 窗口关闭时清理网关
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

        self.logger.info(f"Claude API Switcher {APP_VERSION_NAME} started")

    def _on_closing(self):
        """窗口关闭时清理资源"""
        self.logger.info("正在关闭应用...")
        # 停止 V2 网关
        try:
            if hasattr(self, 'gateway_v2') and self.gateway_v2.is_running():
                self.gateway_v2.stop()
        except Exception:
            pass
        # 停止 V1 网关
        try:
            if hasattr(self, 'gateway') and self.gateway.is_running():
                self.gateway.stop()
        except Exception:
            pass
        try:
            if hasattr(self, 'gcli2api'):
                self.gcli2api.stop_managed()
        except Exception:
            pass
        self.root.destroy()

    def _bind_text(self, widget, key: str):
        self._bindings.append((widget, key))
        widget.configure(text=t(key, self.lang))
        return widget

    def _help(self, parent, key: str, **pack_options):
        tip = TooltipButton(parent, text=t(key, self.lang), lang=self.lang)
        self._tooltips.append((tip, key))
        tip.pack(**pack_options)
        return tip

    def _build_ui(self):
        # === Tab 切换栏 ===
        self.tab_frame = ctk.CTkFrame(self.root, fg_color=BG_SURFACE, corner_radius=0,
                                       border_width=1, border_color=BORDER)
        self.tab_frame.pack(fill="x", padx=0, pady=0)

        self.tab_buttons = {}
        tabs = [("providers_tab", "providers"), ("gateway_tab", "gateway"),
                ("v2_dashboard_tab", "v2_dashboard"),
                ("models_tab", "models"), ("logs_tab", "logs"),
                ("settings_tab", "settings")]
        for i, (key, name) in enumerate(tabs):
            btn = ctk.CTkButton(
                self.tab_frame, text=t(key, self.lang), width=110, height=36,
                fg_color="transparent" if i != 0 else ACCENT,
                hover_color=ACCENT_HOVER if i == 0 else BG_ELEVATED,
                text_color=ACCENT_TEXT if i == 0 else TEXT_PRIMARY,
                corner_radius=8, font=ctk.CTkFont(size=12, weight="bold"),
                command=lambda idx=i: self._switch_tab(idx))
            btn.pack(side="left", padx=PAD_XS, pady=PAD_SM)
            self.tab_buttons[name] = btn

        # === 内容区容器 ===
        self.content_frame = ctk.CTkFrame(self.root, fg_color=BG_PRIMARY)
        self.content_frame.pack(fill="both", expand=True)

        # Tab 0: 原有的 Claude Switcher 主界面
        self.switcher_frame = ctk.CTkFrame(self.content_frame, fg_color=BG_PRIMARY)
        self.switcher_frame.pack(fill="both", expand=True)
        self.main_frame = ctk.CTkScrollableFrame(self.switcher_frame, fg_color=BG_PRIMARY)
        self.main_frame.pack(fill="both", expand=True, padx=PAD_LG, pady=PAD_LG)
        self._build_header()
        self._build_status_and_quick_launch()
        self._build_gcli2api_section()
        self._build_provider_section()
        self._build_log_section()

        # Tab 1: AI Gateway 仪表板
        self.gateway_frame = ctk.CTkFrame(self.content_frame, fg_color=BG_PRIMARY)
        self.gateway_panel = GatewayPanel(
            self.gateway_frame, self.model_manager, self.gateway, self.lang, self.logger)

        # Tab 2: V2 智能网关仪表板（余额/成本/路由/故障转移/通知）
        self.v2_dashboard_frame = ctk.CTkFrame(self.content_frame, fg_color=BG_PRIMARY)
        self.v2_dashboard_panel = V2DashboardPanel(
            self.v2_dashboard_frame, self.gateway_v2, self.lang, self.logger)

        # Tab 3: 模型管理
        self.models_frame = ctk.CTkFrame(self.content_frame, fg_color=BG_PRIMARY)
        self._build_models_tab()

        # Tab 4: 请求日志
        self.logs_frame = ctk.CTkFrame(self.content_frame, fg_color=BG_PRIMARY)
        self._build_logs_tab()

        # Tab 5: Claude Code 环境与外观设置
        self.settings_frame = ctk.CTkFrame(self.content_frame, fg_color=BG_PRIMARY)
        self._build_settings_tab()

        self._current_tab = 0

    def _build_header(self):
        header = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        header.pack(fill="x", pady=(PAD_SM, PAD_LG))
        left = ctk.CTkFrame(header, fg_color="transparent")
        left.pack(side="left")
        self.title_label = self._bind_text(ctk.CTkLabel(
            left, text="", font=ctk.CTkFont(family=FONT_FAMILY, size=22, weight="bold"),
            text_color=TEXT_PRIMARY), "app_title")
        self.title_label.pack(anchor="w")
        self.subtitle_label = self._bind_text(ctk.CTkLabel(
            left, text="", font=ctk.CTkFont(size=11), text_color=TEXT_MUTED), "app_subtitle_safe")
        self.subtitle_label.pack(anchor="w")

        right = ctk.CTkFrame(header, fg_color="transparent")
        right.pack(side="right")
        display_lang = next((name for name, code in LANGUAGES if code == self.lang), "中文")
        self.lang_var = ctk.StringVar(value=display_lang)
        self.lang_combo = ctk.CTkComboBox(
            right, values=[name for name, _ in LANGUAGES], variable=self.lang_var,
            width=82, height=30, command=self._on_language_change,
            fg_color=BG_ELEVATED, border_color=BORDER, button_color=BORDER,
            button_hover_color=ACCENT, dropdown_fg_color=BG_SURFACE)
        self.lang_combo.pack(side="left", padx=(0, PAD_SM))
        self.export_btn = self._bind_text(ctk.CTkButton(
            right, text="", width=64, height=30, fg_color=BG_ELEVATED,
            hover_color=BORDER, border_width=1, border_color=BORDER,
            text_color=TEXT_PRIMARY,
            command=self._export_config), "export")
        self.export_btn.pack(side="left", padx=PAD_XS)
        self.import_btn = self._bind_text(ctk.CTkButton(
            right, text="", width=64, height=30, fg_color=BG_ELEVATED,
            hover_color=BORDER, border_width=1, border_color=BORDER,
            text_color=TEXT_PRIMARY,
            command=self._import_config), "import")
        self.import_btn.pack(side="left", padx=PAD_XS)

    def _build_status_and_quick_launch(self):
        card = ctk.CTkFrame(self.main_frame, fg_color=BG_SURFACE, corner_radius=12,
                            border_width=1, border_color=BORDER)
        card.pack(fill="x", pady=(0, PAD_LG))
        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=PAD_LG, pady=(PAD_MD, PAD_SM))
        self.status_title = self._bind_text(ctk.CTkLabel(
            head, text="", font=ctk.CTkFont(size=14, weight="bold"),
            text_color=TEXT_PRIMARY), "current_status")
        self.status_title.pack(side="left")
        self.status_indicator = ctk.CTkLabel(head, text="○", text_color=TEXT_MUTED,
                                             font=ctk.CTkFont(size=15))
        self.status_indicator.pack(side="right")

        grid = ctk.CTkFrame(card, fg_color="transparent")
        grid.pack(fill="x", padx=PAD_LG, pady=(0, PAD_SM))
        grid.grid_columnconfigure(1, weight=1)
        self.status_provider = self._status_row(grid, 0, "status_provider_label", "tooltip_status_provider")
        self.status_model = self._status_row(grid, 1, "status_model_label", "tooltip_status_model")
        self.status_state = self._status_row(grid, 2, "status_state_label", "tooltip_status_state")

        project_row = ctk.CTkFrame(card, fg_color="transparent")
        project_row.pack(fill="x", padx=PAD_LG, pady=PAD_SM)
        label_frame = ctk.CTkFrame(project_row, fg_color="transparent")
        label_frame.pack(side="left")
        self.project_label = self._bind_text(ctk.CTkLabel(
            label_frame, text="", width=82, anchor="w", text_color=TEXT_SECONDARY), "project_dir")
        self.project_label.pack(side="left")
        self._help(label_frame, "tooltip_project_dir", side="left", padx=(PAD_XS, PAD_SM))
        self.project_dir_var = ctk.StringVar(value=self.config.get_default_project_dir())
        self.project_entry = ctk.CTkEntry(
            project_row, textvariable=self.project_dir_var, height=34,
            fg_color=BG_INPUT, border_color=BORDER, text_color=TEXT_PRIMARY)
        self.browse_btn = self._bind_text(ctk.CTkButton(
            project_row, text="", width=76, height=34, fg_color=BG_ELEVATED,
            hover_color=BORDER, text_color=TEXT_PRIMARY,
            command=self._browse_project_dir), "browse")
        self.browse_btn.pack(side="right")
        self.project_source_label = ctk.CTkLabel(
            project_row, text="", width=82, font=ctk.CTkFont(size=10),
            text_color=INFO)
        self.project_source_label.pack(side="right", padx=(0, PAD_SM))
        self.project_entry.pack(side="left", fill="x", expand=True, padx=(0, PAD_SM))

        self.quick_launch_btn = self._bind_text(ctk.CTkButton(
            card, text="", height=48, font=ctk.CTkFont(size=15, weight="bold"),
            fg_color=SUCCESS, hover_color=SUCCESS_DARK, corner_radius=10,
            command=self._quick_launch), "quick_launch")
        self.quick_launch_btn.pack(fill="x", padx=PAD_LG, pady=(PAD_SM, PAD_SM))
        self.session_note = self._bind_text(ctk.CTkLabel(
            card, text="", font=ctk.CTkFont(size=10), text_color=TEXT_MUTED), "session_only_note")
        self.session_note.pack(pady=(0, PAD_MD))

    def _status_row(self, parent, row: int, key: str, tooltip_key: str):
        label_box = ctk.CTkFrame(parent, fg_color="transparent")
        label_box.grid(row=row, column=0, sticky="w", pady=PAD_XS)
        label = self._bind_text(ctk.CTkLabel(
            label_box, text="", width=82, anchor="w", text_color=TEXT_SECONDARY), key)
        label.pack(side="left")
        self._help(label_box, tooltip_key, side="left", padx=(PAD_XS, PAD_SM))
        value = ctk.CTkLabel(parent, text="—", anchor="w", text_color=TEXT_PRIMARY)
        value.grid(row=row, column=1, sticky="ew", pady=PAD_XS)
        return value

    def _build_gcli2api_section(self):
        """Build the optional Gemini CLI reverse-proxy control card."""
        card = ctk.CTkFrame(
            self.main_frame, fg_color=BG_SURFACE, corner_radius=12,
            border_width=1, border_color=GEMINI_ACCENT)
        card.pack(fill="x", pady=(0, PAD_LG))
        card.grid_columnconfigure(1, weight=1)

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.grid(row=0, column=0, columnspan=4, sticky="ew", padx=PAD_LG,
                  pady=(PAD_LG, PAD_XS))
        self.gcli_title_label = self._bind_text(ctk.CTkLabel(
            head, text="", font=ctk.CTkFont(size=15, weight="bold"),
            text_color=GEMINI_ACCENT), "gcli_title")
        self.gcli_title_label.pack(side="left")
        self.gcli_state_label = ctk.CTkLabel(
            head, text="○ 等待检测", font=ctk.CTkFont(size=11, weight="bold"),
            text_color=TEXT_MUTED)
        self.gcli_state_label.pack(side="right")

        self.gcli_subtitle_label = self._bind_text(ctk.CTkLabel(
            card, text="", anchor="w", justify="left", wraplength=900,
            font=ctk.CTkFont(size=10), text_color=TEXT_MUTED), "gcli_subtitle")
        self.gcli_subtitle_label.grid(row=1, column=0, columnspan=4, sticky="ew",
                                     padx=PAD_LG, pady=(0, PAD_MD))

        credential = ctk.CTkFrame(card, fg_color=BG_ELEVATED, corner_radius=8)
        credential.grid(row=2, column=0, columnspan=4, sticky="ew", padx=PAD_LG,
                        pady=(0, PAD_MD))
        credential.grid_columnconfigure(1, weight=1)
        self.gcli_password_label = self._bind_text(ctk.CTkLabel(
            credential, text="", text_color=TEXT_SECONDARY,
            font=ctk.CTkFont(size=10)), "gcli_password")
        self.gcli_password_label.grid(row=0, column=0, sticky="w", padx=(PAD_MD, PAD_SM), pady=PAD_SM)
        self.gcli_password_var = ctk.StringVar(value="")
        self.gcli_password_entry = ctk.CTkEntry(
            credential, textvariable=self.gcli_password_var, show="•", height=34,
            fg_color=BG_INPUT, border_color=BORDER)
        self.gcli_password_entry.grid(row=0, column=1, sticky="ew", padx=(0, PAD_MD), pady=PAD_SM)
        self.gcli_model_label = self._bind_text(ctk.CTkLabel(
            credential, text="", text_color=TEXT_SECONDARY,
            font=ctk.CTkFont(size=10)), "gcli_model")
        self.gcli_model_label.grid(row=0, column=2, sticky="w", padx=(0, PAD_SM), pady=PAD_SM)
        self.gcli_model_var = ctk.StringVar(value="gemini-2.5-pro")
        self.gcli_model_combo = ctk.CTkComboBox(
            credential, values=["gemini-2.5-pro"], variable=self.gcli_model_var,
            width=230, height=34, fg_color=BG_INPUT, border_color=BORDER)
        self.gcli_model_combo.grid(row=0, column=3, sticky="e", padx=(0, PAD_MD), pady=PAD_SM)

        self.gcli_detail_label = ctk.CTkLabel(
            card, text=f"{DEFAULT_BASE_URL}  ·  {self.gcli2api.install_dir}",
            anchor="w", justify="left", wraplength=900, text_color=TEXT_SECONDARY,
            font=ctk.CTkFont(family=FONT_MONO, size=9))
        self.gcli_detail_label.grid(row=3, column=0, columnspan=4, sticky="ew",
                                   padx=PAD_LG, pady=(0, PAD_SM))

        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.grid(row=4, column=0, columnspan=4, sticky="ew", padx=PAD_LG,
                     pady=(0, PAD_LG))
        for column in range(4):
            actions.grid_columnconfigure(column, weight=1, uniform="gcli-actions")
        self.gcli_action_buttons = []
        button_specs = [
            ("gcli_detect", self._detect_gcli2api, BG_ELEVATED, BORDER),
            ("gcli_install", self._install_gcli2api, GEMINI_ACCENT, GEMINI_HOVER),
            ("gcli_start", self._start_gcli2api, SUCCESS, SUCCESS_DARK),
            ("gcli_panel", self._open_gcli2api_panel, INFO, INFO_DARK),
            ("gcli_add_claude", self._add_gcli2api_to_claude, GEMINI_ACCENT, GEMINI_HOVER),
            ("gcli_add_gateway", self._add_gcli2api_to_gateway, BG_ELEVATED, BORDER),
            ("gcli_examples", self._show_gcli2api_examples, BG_ELEVATED, BORDER),
        ]
        for index, (key, command, color, hover) in enumerate(button_specs):
            button = self._bind_text(ctk.CTkButton(
                actions, text="", height=34, fg_color=color, hover_color=hover,
                text_color=TEXT_PRIMARY if color == BG_ELEVATED else ACCENT_TEXT,
                command=command), key)
            button.grid(
                row=index // 4, column=index % 4, sticky="ew",
                padx=(0 if index % 4 == 0 else PAD_XS, 0), pady=PAD_XS)
            self.gcli_action_buttons.append(button)
        github_button = ctk.CTkButton(
            actions, text="GitHub", width=64, height=34, fg_color="transparent",
            border_width=1, border_color=BORDER, hover_color=BG_ELEVATED,
            text_color=TEXT_PRIMARY,
            command=lambda: webbrowser.open("https://github.com/su-kaka/gcli2api")
        )
        github_button.grid(row=1, column=3, sticky="ew", padx=(PAD_XS, 0), pady=PAD_XS)

    def _set_gcli_busy(self, busy: bool, message: str = ""):
        self._gcli_busy = busy
        for button in getattr(self, "gcli_action_buttons", []):
            button.configure(state="disabled" if busy else "normal")
        if message:
            self.gcli_state_label.configure(text=f"◌ {message}", text_color=INFO)

    def _gcli_password(self) -> str:
        return self.gcli_password_var.get().strip() if hasattr(self, "gcli_password_var") else ""

    def _run_gcli_worker(self, worker, done, busy_text: str):
        if self._gcli_busy:
            return
        self._set_gcli_busy(True, busy_text)

        def run():
            try:
                result = worker()
                self.root.after(0, done, result, None)
            except Exception as exc:
                self.root.after(0, done, None, str(exc)[:200])

        threading.Thread(target=run, daemon=True, name="gcli2api-worker").start()

    def _detect_gcli2api(self):
        def done(status, error):
            self._set_gcli_busy(False)
            if error:
                status = Gcli2ApiStatus(
                    state="error", base_url=self.gcli2api.base_url,
                    install_dir=self.gcli2api.install_dir,
                    error_code="internal", message=f"检测失败：{error}")
            self._gcli_status = status
            self._render_gcli_status(status)

        self._run_gcli_worker(
            lambda: self.gcli2api.detect(self._gcli_password()), done,
            self._ui("正在检测…", "Checking…"))

    def _gcli_display_message(self, status: Gcli2ApiStatus) -> str:
        if self.lang == "zh":
            return status.message
        messages = {
            "connection_refused": "Service is not running or was not detected.",
            "timeout": "Connection timed out. Check the proxy, firewall and service log.",
            "dns": "Server not found. Check the address, network or DNS.",
            "redirect": "The service redirected the request; stopped to protect the password.",
            "auth_failed": "Wrong or missing API password. API_PASSWORD may differ from the panel password.",
            "forbidden": "The Google account, project or credential lacks permission.",
            "not_found": "The API address, endpoint or model does not exist.",
            "rate_limited": "Credential quota is exhausted or rate-limited. Check the panel.",
            "server_error": "gcli2api is temporarily unavailable.",
            "no_models": "The service is running but has no models. Complete Google OAuth in the panel.",
            "invalid_json": "The model endpoint returned invalid JSON.",
            "request_error": "Request failed without exposing credentials.",
        }
        if status.ready:
            return f"Ready · {len(status.models)} models"
        return messages.get(status.error_code, status.message or "Waiting for status")

    def _render_gcli_status(self, status: Gcli2ApiStatus):
        colors = {
            "ready": SUCCESS,
            "stopped": TEXT_MUTED,
            "not_installed": TEXT_MUTED,
            "auth_required": ("#9A6700", "#FBBF24"),
            "oauth_required": ("#9A6700", "#FBBF24"),
            "error": DANGER,
        }
        names = {
            "zh": {
                "ready": "● 可以调用", "stopped": "○ 已安装，未运行",
                "not_installed": "○ 未检测到", "auth_required": "● 需要 API 密码",
                "oauth_required": "● 需要 Google OAuth", "error": "● 检测异常",
            },
            "en": {
                "ready": "● Ready", "stopped": "○ Installed, stopped",
                "not_installed": "○ Not detected", "auth_required": "● API password required",
                "oauth_required": "● Google OAuth required", "error": "● Check failed",
            },
        }
        self.gcli_state_label.configure(
            text=names.get(self.lang, names["en"]).get(status.state, "○ Waiting"),
            text_color=colors.get(status.state, TEXT_MUTED))
        detail = self._gcli_display_message(status)
        version = f" · {status.version}" if status.version else ""
        self.gcli_detail_label.configure(
            text=f"{status.base_url}{version}\n{detail}\n{status.install_dir}")
        if status.models:
            values = list(status.models)
            self.gcli_model_combo.configure(values=values)
            primary, _ = self.gcli2api.select_models(values)
            current = self.gcli_model_var.get()
            if current not in values:
                self.gcli_model_var.set(primary)

    def _install_gcli2api(self):
        message = self._ui(
            "将从 GitHub 安装独立第三方项目 gcli2api。缺少依赖时会通过 WinGet 安装 Git.Git 和 astral-sh.uv。不会执行远程脚本文本、修改 PowerShell 策略或捆绑 OAuth 凭据。gcli2api 使用 CNC-1.0 非商业许可证。是否继续？",
            "This installs the independent third-party gcli2api project from GitHub. Missing Git.Git and astral-sh.uv may be installed with WinGet. No remote script text, PowerShell policy change, or OAuth credential is bundled. gcli2api uses the CNC-1.0 non-commercial license. Continue?")
        if not messagebox.askyesno(t("notice", self.lang), message):
            return

        def progress(text):
            self.root.after(
                0,
                lambda value=text: self.gcli_state_label.configure(
                    text=f"◌ {value}", text_color=INFO),
            )

        def done(result, error):
            self._set_gcli_busy(False)
            ok, message = result if result else (False, error or self._ui("安装失败", "Installation failed"))
            self._append_log(message)
            (messagebox.showinfo if ok else messagebox.showerror)(t("notice", self.lang), message)
            self._detect_gcli2api()

        self._run_gcli_worker(lambda: self.gcli2api.install(progress), done,
                              self._ui("准备安装…", "Preparing installation…"))

    def _start_gcli2api(self):
        password = self._gcli_password()
        if not password:
            messagebox.showerror(t("error", self.lang), self._ui(
                "请先填写 gcli2api API 密码。启动时会同时作为本地面板密码。",
                "Enter the gcli2api API password first. It will also be used as the local panel password."))
            return

        def done(result, error):
            self._set_gcli_busy(False)
            ok, message = result if result else (False, error or "Start failed")
            self._append_log(message)
            if not ok:
                messagebox.showerror(t("error", self.lang), message)
                return
            self.root.after(1500, self._detect_gcli2api)

        self._run_gcli_worker(lambda: self.gcli2api.start(password, password), done,
                              self._ui("正在启动…", "Starting…"))

    def _open_gcli2api_panel(self):
        if not self.gcli2api.open_panel():
            messagebox.showerror(t("error", self.lang), self._ui(
                "无法打开默认浏览器", "Could not open the default browser"))

    def _add_gcli2api_to_claude(self):
        password = self._gcli_password()
        if not password:
            messagebox.showerror(t("error", self.lang), self._ui(
                "请先填写 API 密码", "Enter the API password first"))
            return
        model = self.gcli_model_var.get().strip() or "gemini-2.5-pro"
        _, fast_model = self.gcli2api.select_models(self._gcli_status.models or (model,))
        existing = next((item for item in self.provider_manager.get_all_providers()
                         if item.get("provider_kind") == "gcli2api"), None)
        name = existing.get("name") if existing else "Gemini CLI (gcli2api)"
        ok, message = self.provider_manager.add_or_update_provider(
            name=name, old_name=name if existing else "", base_url=self.gcli2api.base_url,
            model=model, small_fast_model=fast_model, api_key=password,
            enabled=True, priority=10, auth_mode="bearer", provider_kind="gcli2api")
        if ok:
            self._refresh_provider_list()
            self._append_log(message)
        (messagebox.showinfo if ok else messagebox.showerror)(t("notice", self.lang), message)

    def _add_gcli2api_to_gateway(self):
        password = self._gcli_password()
        if not password:
            messagebox.showerror(t("error", self.lang), self._ui(
                "请先填写 API 密码", "Enter the API password first"))
            return
        models = list(self._gcli_status.models) or [self.gcli_model_var.get().strip() or "gemini-2.5-pro"]
        existing = next((item for item in self.model_manager.get_all_providers()
                         if item.get("provider_type") == "gcli2api"), None)
        if existing:
            ok, message = self.model_manager.update_provider(existing["id"], {
                "name": existing.get("name") or "Gemini CLI (gcli2api)",
                "base_url": f"{self.gcli2api.base_url}/v1",
                "api_key": password, "auth_mode": "bearer", "status": "active",
            })
            if ok:
                known = {item.get("model_name") for item in self.model_manager.get_models_by_provider(existing["id"])}
                for model in models:
                    if model not in known:
                        self.model_manager.add_model(existing["id"], model)
        else:
            ok, message = self.model_manager.add_provider(
                name="Gemini CLI (gcli2api)", provider_type="gcli2api",
                base_url=f"{self.gcli2api.base_url}/v1", api_key=password,
                auth_mode="bearer", models=[{"name": model} for model in models])
        if ok:
            self._refresh_models_tab()
            self.gateway_panel._refresh_all()
            self._append_log(message)
        (messagebox.showinfo if ok else messagebox.showerror)(t("notice", self.lang), message)

    def _show_gcli2api_examples(self):
        GcliExamplesDialog(
            self.root, self.lang,
            self.gcli2api.generate_examples(self.gcli_model_var.get().strip() or "gemini-2.5-pro"),
        ).grab_set()

    def _build_provider_section(self):
        section = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        section.pack(fill="x", pady=(0, PAD_LG))
        head = ctk.CTkFrame(section, fg_color="transparent")
        head.pack(fill="x", pady=(0, PAD_SM))
        self.providers_title = self._bind_text(ctk.CTkLabel(
            head, text="", font=ctk.CTkFont(size=14, weight="bold"),
            text_color=TEXT_PRIMARY), "api_providers")
        self.providers_title.pack(side="left")
        self.add_btn = self._bind_text(ctk.CTkButton(
            head, text="", width=125, height=32, fg_color=ACCENT,
            hover_color=ACCENT_HOVER, command=self._show_add_provider_dialog), "add_provider")
        self.add_btn.pack(side="right")
        self.provider_list_frame = ctk.CTkFrame(section, fg_color="transparent")
        self.provider_list_frame.pack(fill="x")

    def _refresh_provider_list(self):
        for widget in self.provider_list_frame.winfo_children():
            widget.destroy()
        self.provider_status_labels.clear()
        self.provider_action_buttons.clear()
        providers = self.provider_manager.get_all_providers()
        if not providers:
            ctk.CTkLabel(self.provider_list_frame, text=t("no_providers_hint", self.lang),
                         text_color=TEXT_MUTED).pack(pady=PAD_XL)
            return
        current = self.config.get_current_provider_name()
        for provider in providers:
            self._add_provider_card(provider, current)

    def _add_provider_card(self, provider, current):
        name = provider.get("name", "")
        enabled = provider.get("enabled", True)
        card = ctk.CTkFrame(self.provider_list_frame, fg_color=BG_SURFACE,
                            corner_radius=10, border_width=1,
                            border_color=ACCENT if name == current else BORDER)
        card.pack(fill="x", pady=PAD_XS)
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=PAD_LG, pady=(PAD_MD, PAD_XS))
        ctk.CTkLabel(top, text=name, font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=TEXT_PRIMARY if enabled else TEXT_MUTED).pack(side="left")
        if name == current:
            ctk.CTkLabel(top, text=t("selected_badge", self.lang), text_color=ACCENT,
                         font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=PAD_SM)
        if not enabled:
            ctk.CTkLabel(top, text=t("status_disabled", self.lang), text_color=TEXT_MUTED).pack(side="right")

        meta = ctk.CTkFrame(card, fg_color="transparent")
        meta.pack(fill="x", padx=PAD_LG)
        ctk.CTkLabel(meta, text=provider.get("base_url") or "—", anchor="w",
                     text_color=TEXT_SECONDARY, font=ctk.CTkFont(family=FONT_MONO, size=10)).pack(fill="x")
        ctk.CTkLabel(meta, text=f"{provider.get('model') or '—'}   ·   {provider.get('masked_key')}",
                     anchor="w", text_color=TEXT_MUTED, font=ctk.CTkFont(size=10)).pack(fill="x")

        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.pack(fill="x", padx=PAD_LG, pady=(PAD_SM, PAD_MD))
        use_btn = ctk.CTkButton(
            actions, text=t("test_and_use", self.lang), width=105, height=30,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            state="normal" if enabled else "disabled",
            command=lambda n=name: self._use_provider(n))
        use_btn.pack(side="left", padx=(0, PAD_XS))
        test_btn = ctk.CTkButton(
            actions, text=t("test", self.lang), width=60, height=30,
            fg_color=INFO, hover_color=INFO_DARK,
            state="normal" if enabled else "disabled",
            command=lambda n=name: self._begin_test(n, "test"))
        test_btn.pack(side="left", padx=PAD_XS)
        status_text, status_color = self._provider_status(name, provider)
        status = ctk.CTkLabel(actions, text=status_text, text_color=status_color,
                              anchor="w", font=ctk.CTkFont(size=10))
        status.pack(side="left", padx=PAD_SM, fill="x", expand=True)
        ctk.CTkButton(actions, text=t("edit", self.lang), width=58, height=30,
                      fg_color=BG_ELEVATED, hover_color=BORDER, text_color=TEXT_PRIMARY,
                      command=lambda n=name: self._show_edit_provider_dialog(n)).pack(side="right", padx=PAD_XS)
        ctk.CTkButton(actions, text=t("delete", self.lang), width=58, height=30,
                      fg_color="transparent", hover_color=("#fde7e9", "#3f1d27"), text_color=DANGER,
                      border_width=1, border_color=("#d13438", "#5f2635"),
                      command=lambda n=name: self._delete_provider(n)).pack(side="right", padx=PAD_XS)
        self.provider_status_labels[name] = status
        self.provider_action_buttons[name] = (use_btn, test_btn)

    def _provider_status(self, name, provider):
        if not provider.get("enabled", True):
            return t("status_disabled", self.lang), TEXT_MUTED
        if name in self._testing:
            return t("status_testing", self.lang), INFO
        if self.provider_manager.is_verified(name):
            return t("status_available", self.lang), SUCCESS
        result = self._test_results.get(name)
        if result and not result[0]:
            return result[1], DANGER
        return t("status_not_tested", self.lang), TEXT_MUTED

    def _build_log_section(self):
        frame = ctk.CTkFrame(self.main_frame, fg_color=BG_SURFACE, corner_radius=10,
                             border_width=1, border_color=BORDER)
        frame.pack(fill="x", pady=(0, PAD_SM))
        head = ctk.CTkFrame(frame, fg_color="transparent")
        head.pack(fill="x", padx=PAD_LG, pady=(PAD_SM, PAD_XS))
        self.log_title = self._bind_text(ctk.CTkLabel(
            head, text="", text_color=TEXT_SECONDARY, font=ctk.CTkFont(size=11)), "run_log")
        self.log_title.pack(side="left")
        self.clear_btn = self._bind_text(ctk.CTkButton(
            head, text="", width=50, height=24, fg_color="transparent",
            hover_color=BORDER, command=self._clear_log), "clear")
        self.clear_btn.pack(side="right")
        self.log_text = ctk.CTkTextbox(frame, height=78, fg_color=BG_INPUT,
                                       font=ctk.CTkFont(family=FONT_MONO, size=10), state="disabled")
        self.log_text.pack(fill="x", padx=PAD_LG, pady=(0, PAD_MD))

    def _on_language_change(self, display_name):
        self.lang = next((code for name, code in LANGUAGES if name == display_name), "zh")
        self.config.set_language(self.lang)
        self._update_language()

    def _update_language(self):
        for widget, key in self._bindings:
            try:
                widget.configure(text=t(key, self.lang))
            except Exception:
                pass
        for tip, key in self._tooltips:
            tip.configure(text=t(key, self.lang), lang=self.lang)
        # 更新 Tab 按钮语言
        tab_keys = ["providers_tab", "gateway_tab", "v2_dashboard_tab",
                    "models_tab", "logs_tab", "settings_tab"]
        for i, (name, btn) in enumerate(self.tab_buttons.items()):
            if i < len(tab_keys):
                btn.configure(text=t(tab_keys[i], self.lang))
        # 更新 Gateway 面板语言
        if hasattr(self, 'gateway_panel'):
            self.gateway_panel.set_lang(self.lang)
        if hasattr(self, "gcli_state_label"):
            self._render_gcli_status(self._gcli_status)
        self._refresh_project_source_label()
        self._refresh_provider_list()
        self._refresh_current_status()

    def _refresh_current_status(self):
        provider = self.provider_manager.get_current_provider()
        if not provider:
            self.status_provider.configure(text="—")
            self.status_model.configure(text="—")
            self.status_state.configure(text=t("status_not_selected", self.lang), text_color=TEXT_MUTED)
            self.status_indicator.configure(text="○", text_color=TEXT_MUTED)
            return
        self.status_provider.configure(text=provider.get("name", "—"))
        self.status_model.configure(text=provider.get("model", "—"))
        state_text, color = self._provider_status(provider["name"], provider)
        self.status_state.configure(text=state_text, text_color=color)
        self.status_indicator.configure(text="●" if color == SUCCESS else "○", text_color=color)

    def _begin_test(self, name: str, action: str):
        if name in self._testing:
            priority = {"test": 0, "select": 1, "launch": 2}
            previous = self._pending_test_actions.get(name, "test")
            if priority.get(action, 0) > priority.get(previous, 0):
                self._pending_test_actions[name] = action
            if action == "launch":
                self._set_quick_launch_state("quick_launch_testing", True)
            return
        self._testing.add(name)
        self._pending_test_actions[name] = action
        self._refresh_provider_list()
        self._refresh_current_status()
        self._append_log(f"正在检测 {name}…")
        if action == "launch":
            self._set_quick_launch_state("quick_launch_testing", True)

        def worker():
            try:
                result = self.provider_manager.test_provider(name)
            except Exception as exc:
                result = (False, f"检测失败：{type(exc).__name__}", 0)
            self._result_queue.put((name, action, result))

        threading.Thread(target=worker, daemon=True, name=f"api-test-{name}").start()

    def _poll_test_results(self):
        try:
            while True:
                name, original_action, result = self._result_queue.get_nowait()
                action = self._pending_test_actions.pop(name, original_action)
                self._testing.discard(name)
                success, message, _ = result
                self._test_results[name] = (success, message)
                self._append_log(f"{'✓' if success else '✕'} {name}: {message}")
                if success and action in {"select", "launch"}:
                    ok, select_message = self.provider_manager.set_current(name)
                    if ok:
                        self._append_log(select_message)
                        if action == "launch":
                            self._launch_now()
                    else:
                        messagebox.showwarning(t("notice", self.lang), select_message)
                        if action == "launch":
                            self._set_quick_launch_state("quick_launch", False)
                elif not success and action == "launch":
                    messagebox.showerror(t("test_failed", self.lang), message)
                    self._set_quick_launch_state("quick_launch", False)
                self._refresh_provider_list()
                self._refresh_current_status()
        except queue.Empty:
            pass
        self.root.after(100, self._poll_test_results)

    def _use_provider(self, name: str):
        if self.provider_manager.is_verified(name):
            ok, message = self.provider_manager.set_current(name)
            if ok:
                self._append_log(message)
                self._refresh_provider_list()
                self._refresh_current_status()
            else:
                messagebox.showwarning(t("notice", self.lang), message)
        else:
            self._begin_test(name, "select")

    def _quick_launch(self):
        if self._launch_busy:
            return
        provider = self._find_launch_provider()
        if not provider:
            messagebox.showwarning(t("notice", self.lang), t("msg_no_provider_key", self.lang))
            return
        project_dir = self._resolve_project_directory(for_launch=True)
        if not project_dir:
            messagebox.showerror(t("launch_failed", self.lang), t("msg_no_project_dir", self.lang))
            return
        claude_path = self.claude_command_resolver.resolve()
        if not claude_path:
            self._switch_tab(5)
            messagebox.showwarning(
                t("launch_failed", self.lang),
                self._ui("未检测到 Claude Code。请点击“一键安装 / 更新”，软件会自动下载、安装并配置 PATH。",
                         "Claude Code was not found. Click Install / Update; the app will download, install and configure PATH."))
            return
        if self.provider_manager.is_verified(provider["name"]):
            if self.config.get_current_provider_name() != provider["name"]:
                ok, message = self.provider_manager.set_current(provider["name"])
                if not ok:
                    messagebox.showwarning(t("notice", self.lang), message)
                    return
            self._launch_now()
        else:
            self._begin_test(provider["name"], "launch")

    def _launch_now(self):
        provider = self.provider_manager.get_current_provider()
        if not provider:
            return
        project_dir = self._resolve_project_directory(for_launch=True)
        claude_path = self.claude_command_resolver.resolve()
        if not project_dir or not claude_path:
            self._set_quick_launch_state("quick_launch", False)
            messagebox.showerror(t("launch_failed", self.lang), t("msg_launch_prerequisite_missing", self.lang))
            return
        self._set_quick_launch_state("quick_launch_starting", True)
        self.root.update_idletasks()
        success, message = self.launcher.launch(
            provider["name"], provider.get("base_url", ""), provider.get("api_key", ""),
            provider.get("model", ""), provider.get("small_fast_model", ""),
            project_dir, claude_path=claude_path,
            auth_mode=provider.get("auth_mode", "bearer"))
        self._append_log(message)
        self._set_quick_launch_state("quick_launch", False)
        if not success:
            messagebox.showerror(t("launch_failed", self.lang), message)

    def _browse_project_dir(self):
        directory = filedialog.askdirectory(
            title=t("select_project_dir", self.lang),
            initialdir=self.project_dir_var.get() or os.path.expanduser("~"))
        if not directory:
            return False
        self.project_dir_var.set(directory)
        self.config.set_default_project_dir(directory)
        self._auto_project_dir = ""
        self._project_source = "manual"
        self._refresh_project_source_label()
        return True

    def _find_launch_provider(self):
        current = self.provider_manager.get_current_provider()
        if current and current.get("enabled", True) and current.get("has_api_key"):
            return current
        for item in self.provider_manager.get_all_providers():
            if item.get("enabled", True) and item.get("has_api_key"):
                return self.provider_manager.get_provider_detail(item["name"])
        return None

    def _resolve_project_directory(self, for_launch: bool = False):
        configured = self.config.get_default_project_dir()
        entry = self.project_dir_var.get().strip() if hasattr(self, "project_dir_var") else ""
        if entry and entry != self._auto_project_dir and os.path.isdir(entry):
            configured = entry
            self.config.set_default_project_dir(entry)
        resolution = self.project_resolver.resolve(configured)
        if not resolution:
            return ""
        self.project_dir_var.set(resolution.path)
        self._project_source = resolution.source
        self._auto_project_dir = "" if resolution.source == "manual" else resolution.path
        self._refresh_project_source_label()
        return resolution.path

    def _refresh_project_source_label(self):
        if not hasattr(self, "project_source_label"):
            return
        key = "project_source_manual" if self._project_source == "manual" else "project_source_auto"
        self.project_source_label.configure(text=t(key, self.lang))

    def _set_quick_launch_state(self, text_key: str, busy: bool):
        self._launch_busy = busy
        self.quick_launch_btn.configure(
            text=t(text_key, self.lang), state="disabled" if busy else "normal")

    def _show_add_provider_dialog(self):
        ProviderDialog(self.root, self.lang, None, self._on_save_provider).grab_set()

    def _show_edit_provider_dialog(self, name: str):
        provider = self.provider_manager.get_provider_detail(name)
        if provider:
            ProviderDialog(self.root, self.lang, provider, self._on_save_provider).grab_set()

    def _on_save_provider(self, data, old_name=""):
        success, message = self.provider_manager.add_or_update_provider(old_name=old_name, **data)
        if success:
            self._test_results.pop(old_name or data["name"], None)
            self._refresh_provider_list()
            self._refresh_current_status()
            self._append_log(f"已保存 {data['name']}")
        else:
            messagebox.showerror(t("save_failed", self.lang), message)
        return success

    def _delete_provider(self, name: str):
        if not messagebox.askyesno(t("confirm_delete_title", self.lang),
                                   t("confirm_delete", self.lang, name)):
            return
        success, message = self.provider_manager.delete_provider(name)
        if success:
            self._test_results.pop(name, None)
            self._refresh_provider_list()
            self._refresh_current_status()
            self._append_log(message)
        else:
            messagebox.showerror(t("error", self.lang), message)

    def _export_config(self):
        path = filedialog.asksaveasfilename(defaultextension=".json",
                                            filetypes=[("JSON", "*.json")])
        if not path:
            return
        success, message = self.provider_manager.export_config(path)
        (messagebox.showinfo if success else messagebox.showerror)(t("notice", self.lang), message)

    def _import_config(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not path:
            return
        if not messagebox.askyesno(t("notice", self.lang), t("confirm_import", self.lang)):
            return
        success, message = self.provider_manager.import_config(path)
        (messagebox.showinfo if success else messagebox.showerror)(t("notice", self.lang), message)
        if success:
            self._test_results.clear()
            self._refresh_provider_list()
            self._refresh_current_status()

    def _append_log(self, message: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
        self.logger.info(message)

    def _clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _ui(self, zh: str, en: str) -> str:
        return zh if self.lang == "zh" else en

    # === V1 AI Gateway Tab 切换 ===

    def _switch_tab(self, index: int):
        """切换 Tab 页面"""
        self._current_tab = index
        frames = [self.switcher_frame, self.gateway_frame, self.v2_dashboard_frame,
                  self.models_frame, self.logs_frame, self.settings_frame]
        for i, frame in enumerate(frames):
            if i == index:
                frame.pack(fill="both", expand=True)
                self.tab_buttons[list(self.tab_buttons.keys())[i]].configure(
                    fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT)
            else:
                frame.pack_forget()
                self.tab_buttons[list(self.tab_buttons.keys())[i]].configure(
                    fg_color="transparent", hover_color=BG_ELEVATED, text_color=TEXT_PRIMARY)

        # 刷新目标 Tab 数据
        if index == 1:
            self.gateway_panel._refresh_all()
        elif index == 2:
            # V2 智能网关仪表板
            if hasattr(self, 'v2_dashboard_panel'):
                self.v2_dashboard_panel._refresh_all()
        elif index == 3:
            self._refresh_models_tab()
        elif index == 4:
            self._refresh_logs_tab()
        elif index == 5:
            self._detect_claude_environment()

    def _build_models_tab(self):
        """构建模型管理 Tab"""
        # 模型管理功能已在 GatewayPanel 中实现，这里显示简化版提示
        frame = ctk.CTkScrollableFrame(self.models_frame, fg_color=BG_PRIMARY)
        frame.pack(fill="both", expand=True, padx=PAD_LG, pady=PAD_LG)

        # 标题
        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", pady=(0, PAD_LG))
        ctk.CTkLabel(header, text=t("models_tab", self.lang),
                     font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=TEXT_PRIMARY).pack(side="left")

        # 添加供应商按钮
        ctk.CTkButton(header, text=t("add_provider_title", self.lang), width=130, height=34,
                      fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      command=self._show_add_gateway_provider_dialog).pack(side="right")

        # 供应商列表
        self.providers_list_frame = ctk.CTkFrame(frame, fg_color="transparent")
        self.providers_list_frame.pack(fill="x")

    def _refresh_models_tab(self):
        """刷新模型管理 Tab"""
        for widget in self.providers_list_frame.winfo_children():
            widget.destroy()

        providers = self.model_manager.get_all_providers()
        if not providers:
            ctk.CTkLabel(self.providers_list_frame, text=t("no_data", self.lang),
                         text_color=TEXT_MUTED).pack(pady=PAD_XL)
            return

        for p in providers:
            self._add_gateway_provider_card(p)

    def _add_gateway_provider_card(self, provider: dict):
        """添加 Gateway 供应商卡片"""
        card = ctk.CTkFrame(self.providers_list_frame, fg_color=BG_SURFACE,
                            corner_radius=10, border_width=1, border_color=BORDER)
        card.pack(fill="x", pady=PAD_XS)

        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=PAD_LG, pady=(PAD_MD, PAD_XS))

        ctk.CTkLabel(top, text=provider.get("name", ""), font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=TEXT_PRIMARY).pack(side="left")

        ptype = provider.get("provider_type", "custom")
        type_text = SUPPORTED_PROVIDERS.get(ptype, {}).get("name", t("custom_provider", self.lang))
        ctk.CTkLabel(top, text=type_text, text_color=TEXT_MUTED,
                     font=ctk.CTkFont(size=10)).pack(side="left", padx=PAD_SM)

        # 操作按钮
        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.pack(fill="x", padx=PAD_LG, pady=(PAD_SM, PAD_MD))

        ctk.CTkButton(actions, text=t("test_key", self.lang), width=70, height=28,
                      fg_color=INFO, hover_color=INFO_DARK, font=ctk.CTkFont(size=10),
                      command=lambda pid=provider.get("id", ""): self._test_provider_key(pid)).pack(side="left", padx=PAD_XS)
        ctk.CTkButton(actions, text=t("edit", self.lang), width=50, height=28,
                      fg_color=BG_ELEVATED, hover_color=BORDER, text_color=TEXT_PRIMARY,
                      font=ctk.CTkFont(size=10),
                      command=lambda p=provider: self._show_edit_gateway_provider_dialog(p)).pack(side="right", padx=PAD_XS)
        ctk.CTkButton(actions, text=t("delete", self.lang), width=50, height=28,
                      fg_color="transparent", hover_color=("#fde7e9", "#3f1d27"), text_color=DANGER,
                      font=ctk.CTkFont(size=10),
                      command=lambda p=provider: self._delete_gateway_provider(p)).pack(side="right")

        # 模型列表
        models = self.model_manager.get_models_by_provider(provider.get("id", ""))
        models_text = ", ".join([m.get("model_name", "") for m in models[:5]]) if models else "—"
        ctk.CTkLabel(card, text=f"{t('model', self.lang)}: {models_text}",
                     text_color=TEXT_MUTED, font=ctk.CTkFont(size=10)).pack(anchor="w", padx=PAD_LG, pady=(0, PAD_SM))

    def _show_add_gateway_provider_dialog(self):
        """显示添加供应商对话框"""
        ProviderGatewayDialog(self.root, self.lang, self.model_manager, None,
                              callback=self._refresh_models_tab)

    def _show_edit_gateway_provider_dialog(self, provider: dict):
        """显示编辑供应商对话框"""
        ProviderGatewayDialog(self.root, self.lang, self.model_manager, provider,
                              callback=self._refresh_models_tab)

    def _delete_gateway_provider(self, provider: dict):
        """删除 Gateway 供应商"""
        name = provider.get("name", "")
        if not messagebox.askyesno(t("confirm_delete_title", self.lang),
                                   t("confirm_delete_provider", self.lang, name)):
            return
        ok, msg = self.model_manager.delete_provider(provider.get("id", ""))
        if ok:
            self._refresh_models_tab()
        else:
            messagebox.showerror(t("error", self.lang), msg)

    def _test_provider_key(self, provider_id: str):
        """测试供应商 API Key"""
        def worker():
            ok, msg, ms = self.model_manager.test_api_key(provider_id)
            # Tkinter 线程安全：通过 after 回到主线程显示对话框
            self.root.after(0, self._show_key_result, ok, msg)
        threading.Thread(target=worker, daemon=True).start()

    def _show_key_result(self, ok: bool, msg: str):
        """在主线程显示 Key 测试结果"""
        if ok:
            messagebox.showinfo(t("key_valid", self.lang), msg)
        else:
            messagebox.showerror(t("key_invalid", self.lang), msg)

    def _build_settings_tab(self):
        """构建外观与 Claude Code 环境管理页面。"""
        frame = ctk.CTkScrollableFrame(self.settings_frame, fg_color=BG_PRIMARY)
        frame.pack(fill="both", expand=True, padx=PAD_XL, pady=PAD_LG)

        heading = ctk.CTkFrame(frame, fg_color="transparent")
        heading.pack(fill="x", pady=(0, PAD_LG))
        ctk.CTkLabel(
            heading, text=self._ui("设置与环境", "Settings & Environment"),
            font=ctk.CTkFont(family=FONT_FAMILY, size=22, weight="bold"),
            text_color=TEXT_PRIMARY).pack(anchor="w")
        ctk.CTkLabel(
            heading,
            text=self._ui("管理界面主题，并自动检测、安装和修复 Claude Code。",
                          "Manage the theme and detect, install or repair Claude Code."),
            font=ctk.CTkFont(size=11), text_color=TEXT_MUTED).pack(anchor="w", pady=(PAD_XS, 0))

        appearance = ctk.CTkFrame(frame, fg_color=BG_SURFACE, corner_radius=12,
                                  border_width=1, border_color=BORDER)
        appearance.pack(fill="x", pady=(0, PAD_LG))
        appearance.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            appearance, text=self._ui("外观", "Appearance"),
            font=ctk.CTkFont(size=15, weight="bold"), text_color=TEXT_PRIMARY
        ).grid(row=0, column=0, sticky="w", padx=PAD_LG, pady=(PAD_LG, PAD_XS))
        ctk.CTkLabel(
            appearance, text=self._ui("跟随系统会自动匹配 Windows 的浅色或深色模式。",
                                      "System mode follows the Windows light or dark setting."),
            text_color=TEXT_MUTED, font=ctk.CTkFont(size=11)
        ).grid(row=1, column=0, sticky="w", padx=PAD_LG, pady=(0, PAD_LG))
        theme_names = {
            "system": self._ui("跟随系统", "System"),
            "light": self._ui("浅色", "Light"),
            "dark": self._ui("深色", "Dark"),
        }
        self._theme_display_to_mode = {label: mode for mode, label in theme_names.items()}
        self.theme_selector = ctk.CTkSegmentedButton(
            appearance, values=list(theme_names.values()), height=34,
            command=self._on_theme_change, selected_color=ACCENT,
            selected_hover_color=ACCENT_HOVER, unselected_color=BG_ELEVATED,
            unselected_hover_color=BORDER)
        self.theme_selector.grid(row=0, column=1, rowspan=2, sticky="e",
                                 padx=PAD_LG, pady=PAD_LG)
        self.theme_selector.set(theme_names[self.config.get_theme()])

        env = ctk.CTkFrame(frame, fg_color=BG_SURFACE, corner_radius=12,
                           border_width=1, border_color=BORDER)
        env.pack(fill="x")
        env.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            env, text="Claude Code",
            font=ctk.CTkFont(size=15, weight="bold"), text_color=TEXT_PRIMARY
        ).grid(row=0, column=0, sticky="w", padx=PAD_LG, pady=(PAD_LG, PAD_XS))
        ctk.CTkLabel(
            env,
            text=self._ui("优先使用 WinGet，失败后自动尝试 Anthropic 官方 Windows 安装器。不会改动你的 API Key。",
                          "Uses WinGet first, then Anthropic's official Windows installer. API keys are never changed."),
            text_color=TEXT_MUTED, font=ctk.CTkFont(size=11), anchor="w",
            justify="left", wraplength=700
        ).grid(row=1, column=0, columnspan=2, sticky="ew", padx=PAD_LG, pady=(0, PAD_MD))

        status_box = ctk.CTkFrame(env, fg_color=BG_ELEVATED, corner_radius=10)
        status_box.grid(row=2, column=0, columnspan=2, sticky="ew", padx=PAD_LG)
        status_box.grid_columnconfigure(0, weight=1)
        self.environment_status_label = ctk.CTkLabel(
            status_box, text=self._ui("正在检测环境…", "Detecting environment…"),
            font=ctk.CTkFont(size=13, weight="bold"), text_color=TEXT_SECONDARY,
            anchor="w")
        self.environment_status_label.grid(row=0, column=0, sticky="ew", padx=PAD_MD,
                                           pady=(PAD_MD, PAD_XS))
        self.environment_detail_label = ctk.CTkLabel(
            status_box, text="", font=ctk.CTkFont(family=FONT_MONO, size=10),
            text_color=TEXT_MUTED, anchor="w", justify="left", wraplength=820)
        self.environment_detail_label.grid(row=1, column=0, sticky="ew", padx=PAD_MD,
                                           pady=(0, PAD_MD))

        self.environment_progress = ctk.CTkProgressBar(env, height=6,
                                                       progress_color=ACCENT)
        self.environment_progress.grid(row=3, column=0, columnspan=2, sticky="ew",
                                       padx=PAD_LG, pady=(PAD_MD, 0))
        self.environment_progress.set(0)

        actions = ctk.CTkFrame(env, fg_color="transparent")
        actions.grid(row=4, column=0, columnspan=2, sticky="ew", padx=PAD_LG,
                     pady=PAD_MD)
        self.environment_buttons = {}
        specs = [
            ("install", self._ui("一键安装 / 更新", "Install / Update"), ACCENT, ACCENT_HOVER, ACCENT_TEXT),
            ("detect", self._ui("重新检测", "Detect"), BG_ELEVATED, BORDER, TEXT_PRIMARY),
            ("repair", self._ui("修复 PATH", "Repair PATH"), BG_ELEVATED, BORDER, TEXT_PRIMARY),
            ("doctor", self._ui("运行诊断", "Run diagnostics"), BG_ELEVATED, BORDER, TEXT_PRIMARY),
        ]
        for action, label, color, hover, text_color in specs:
            button = ctk.CTkButton(
                actions, text=label, height=34, fg_color=color, hover_color=hover,
                text_color=text_color,
                command=lambda value=action: self._run_environment_action(value))
            button.pack(side="left", padx=(0, PAD_SM))
            self.environment_buttons[action] = button

        self.environment_output = ctk.CTkTextbox(
            env, height=135, fg_color=BG_INPUT, border_width=1, border_color=BORDER,
            text_color=TEXT_SECONDARY, font=ctk.CTkFont(family=FONT_MONO, size=10),
            state="disabled")
        self.environment_output.grid(row=5, column=0, columnspan=2, sticky="ew",
                                     padx=PAD_LG, pady=(0, PAD_LG))

    def _on_theme_change(self, display_name: str):
        mode = self._theme_display_to_mode.get(display_name, "system")
        if self.config.set_theme(mode):
            theme.apply_mode(mode)
            self.root.configure(fg_color=BG_PRIMARY)
            self._append_log(self._ui(f"外观已切换为：{display_name}",
                                      f"Theme changed to: {display_name}"))

    def _detect_claude_environment(self):
        self._run_environment_action("detect")

    def _set_environment_busy(self, busy: bool):
        self._environment_busy = busy
        if hasattr(self, "environment_buttons"):
            for button in self.environment_buttons.values():
                button.configure(state="disabled" if busy else "normal")

    def _run_environment_action(self, action: str):
        if self._environment_busy or not hasattr(self, "environment_status_label"):
            return
        self._set_environment_busy(True)
        self.environment_progress.set(0.03)
        self.environment_status_label.configure(
            text=self._ui("正在处理…", "Working…"), text_color=INFO)

        def progress(stage: str, message: str, percent: int):
            self._environment_queue.put(("progress", message, percent))

        def worker():
            try:
                if action == "detect":
                    result = self.claude_environment.detect()
                elif action == "doctor":
                    result = self.claude_environment.doctor()
                elif action == "repair":
                    result = self.claude_environment.repair_path(persist=True)
                else:
                    current = self.claude_environment.detect()
                    result = (self.claude_environment.update(progress) if current.installed
                              else self.claude_environment.install(progress))
                self._environment_queue.put(("done", action, result))
            except Exception as exc:
                self._environment_queue.put(("error", action,
                                             f"{type(exc).__name__}: {exc}"))

        threading.Thread(target=worker, daemon=True,
                         name=f"claude-environment-{action}").start()

    def _poll_environment_results(self):
        try:
            while True:
                kind, value, payload = self._environment_queue.get_nowait()
                if kind == "progress":
                    self.environment_status_label.configure(text=value, text_color=INFO)
                    self.environment_progress.set(max(0, min(100, payload)) / 100)
                    self._write_environment_output(value)
                elif kind == "done":
                    self._set_environment_busy(False)
                    self.environment_progress.set(1)
                    status = payload.status if hasattr(payload, "status") else payload
                    success = payload.success if hasattr(payload, "success") else status.healthy
                    message = payload.message if hasattr(payload, "message") else status.warning
                    self._render_environment_status(status, message, success)
                    if hasattr(payload, "output") and payload.output:
                        self._write_environment_output(payload.output)
                else:
                    self._set_environment_busy(False)
                    self.environment_progress.set(0)
                    self.environment_status_label.configure(
                        text=self._ui("操作失败", "Operation failed"), text_color=DANGER)
                    explanation = self._ui(
                        f"失败原因：{payload}\n请检查网络/代理、权限、Windows Installer 和 WinGet 后重试。",
                        f"Reason: {payload}\nCheck network/proxy, permissions, Windows Installer and WinGet, then retry.")
                    self.environment_detail_label.configure(text=explanation)
                    self._write_environment_output(explanation)
        except queue.Empty:
            pass
        self.root.after(150, self._poll_environment_results)

    def _render_environment_status(self, status, message: str = "", success: bool = True):
        installed = bool(getattr(status, "installed", False))
        healthy = bool(getattr(status, "healthy", False))
        if installed and healthy:
            headline = self._ui("已安装，可正常使用", "Installed and ready")
            color = SUCCESS
        elif installed:
            headline = self._ui("已找到，但环境异常", "Found, but unhealthy")
            color = DANGER
        else:
            headline = self._ui("未安装 Claude Code", "Claude Code is not installed")
            color = TEXT_SECONDARY
        details = [
            getattr(status, "version", "") or self._ui("版本：—", "Version: —"),
            getattr(status, "executable", "") or self._ui("路径：未检测到", "Path: not found"),
        ]
        method = getattr(status, "install_method", "")
        warning = getattr(status, "warning", "")
        diagnostics = getattr(status, "diagnostics", "")
        if method:
            details.append(self._ui(f"安装方式：{method}", f"Install method: {method}"))
        if message:
            details.append(message)
        if warning and warning != message:
            details.append(warning)
        if diagnostics:
            details.append(diagnostics)
        self.environment_status_label.configure(text=headline, text_color=color)
        self.environment_detail_label.configure(text="\n".join(filter(None, details)))
        self._write_environment_output("\n".join(filter(None, details)))

    def _write_environment_output(self, text: str):
        if not text or not hasattr(self, "environment_output"):
            return
        self.environment_output.configure(state="normal")
        self.environment_output.insert("end", f"[{datetime.now():%H:%M:%S}] {text}\n")
        self.environment_output.see("end")
        self.environment_output.configure(state="disabled")

    def _build_logs_tab(self):
        """构建请求日志 Tab"""
        frame = ctk.CTkScrollableFrame(self.logs_frame, fg_color=BG_PRIMARY)
        frame.pack(fill="both", expand=True, padx=PAD_LG, pady=PAD_LG)

        # 标题栏
        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", pady=(0, PAD_LG))

        ctk.CTkLabel(header, text=t("logs_tab", self.lang),
                     font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=TEXT_PRIMARY).pack(side="left")

        ctk.CTkButton(header, text=t("refresh_logs", self.lang), width=70, height=30,
                      fg_color=BG_ELEVATED, hover_color=BORDER, text_color=TEXT_PRIMARY,
                      command=self._refresh_logs_tab).pack(side="right", padx=PAD_XS)
        ctk.CTkButton(header, text=t("clear_logs", self.lang), width=70, height=30,
                      fg_color="transparent", hover_color=BORDER, text_color=DANGER,
                      command=self._clear_all_logs).pack(side="right")

        # 统计摘要
        self.logs_summary_frame = ctk.CTkFrame(frame, fg_color=BG_SURFACE, corner_radius=10,
                                                 border_width=1, border_color=BORDER)
        self.logs_summary_frame.pack(fill="x", pady=(0, PAD_LG))

        # 日志文本区域
        self.logs_text = ctk.CTkTextbox(frame, height=400, fg_color=BG_INPUT,
                                         font=ctk.CTkFont(family=FONT_MONO, size=10), state="disabled")
        self.logs_text.pack(fill="both", expand=True)

    def _refresh_logs_tab(self):
        """刷新日志 Tab"""
        # 更新统计摘要
        for widget in self.logs_summary_frame.winfo_children():
            widget.destroy()

        stats = self.model_manager.get_today_stats()
        summary_items = [
            (t("today_requests", self.lang), str(stats.get("total_requests", 0))),
            (t("today_tokens", self.lang), str(stats.get("total_tokens", 0))),
            (t("success", self.lang), str(stats.get("success_requests", 0))),
            (t("failed", self.lang), str(stats.get("failed_requests", 0))),
        ]
        for i, (label, value) in enumerate(summary_items):
            col = ctk.CTkFrame(self.logs_summary_frame, fg_color="transparent")
            col.pack(side="left", expand=True, padx=PAD_MD, pady=PAD_MD)
            ctk.CTkLabel(col, text=label, text_color=TEXT_MUTED,
                         font=ctk.CTkFont(size=10)).pack()
            ctk.CTkLabel(col, text=value, text_color=TEXT_PRIMARY,
                         font=ctk.CTkFont(size=16, weight="bold")).pack()

        # 更新日志内容
        self.logs_text.configure(state="normal")
        self.logs_text.delete("1.0", "end")

        logs = self.model_manager.get_recent_logs(200)
        if not logs:
            self.logs_text.insert("end", t("no_data", self.lang) + "\n")
        else:
            for log in logs:
                ts = datetime.fromtimestamp(log.get("request_time", 0)).strftime("%Y-%m-%d %H:%M:%S")
                status_icon = "✓" if log.get("status") == "success" else "✗"
                line = (f"{ts}  {status_icon} {log.get('model', 'unknown'):25s}  "
                       f"In:{log.get('input_tokens', 0):6d}  Out:{log.get('output_tokens', 0):6d}  "
                       f"Total:{log.get('total_tokens', 0):6d}  {log.get('response_time_ms', 0)}ms")
                if log.get("error"):
                    line += f"\n    → {log['error'][:100]}"
                self.logs_text.insert("end", line + "\n")

        self.logs_text.see("end")
        self.logs_text.configure(state="disabled")

    def _clear_all_logs(self):
        """清空所有日志"""
        if not messagebox.askyesno(t("confirm_delete_title", self.lang),
                                   t("clear_logs_confirm", self.lang)):
            return
        self.db.clear_old_logs(days=0)
        self._refresh_logs_tab()

    def run(self):
        self.root.mainloop()


class GcliExamplesDialog:
    """Copy-ready gcli2api examples without exposing the user's password."""

    def __init__(self, parent, lang: str, examples: dict):
        self.lang = lang
        self.examples = examples
        self.dialog = ctk.CTkToplevel(parent)
        self.dialog.title("gcli2api " + ("调用示例" if lang == "zh" else "Examples"))
        self.dialog.geometry("760x650")
        self.dialog.minsize(640, 520)
        self.dialog.configure(fg_color=BG_PRIMARY)
        self.dialog.transient(parent)
        self._build()

    def _build(self):
        body = ctk.CTkScrollableFrame(self.dialog, fg_color=BG_PRIMARY)
        body.pack(fill="both", expand=True, padx=PAD_XL, pady=PAD_XL)
        ctk.CTkLabel(
            body,
            text=self._ui(
                "复制后把 YOUR_GCLI2API_PASSWORD 换成你自己的 API 密码。示例不会显示或复制输入框里的真实密码。",
                "Replace YOUR_GCLI2API_PASSWORD with your API password after copying. Your real password is never shown here.",
            ),
            anchor="w", justify="left", wraplength=690,
            text_color=TEXT_SECONDARY,
        ).pack(fill="x", pady=(0, PAD_MD))

        names = {
            "anthropic": "Anthropic / Claude",
            "openai": "OpenAI compatible",
            "gemini": "Gemini native",
        }
        for key in ("anthropic", "openai", "gemini"):
            value = str(self.examples.get(key, ""))
            card = ctk.CTkFrame(
                body, fg_color=BG_SURFACE, corner_radius=10,
                border_width=1, border_color=BORDER)
            card.pack(fill="x", pady=PAD_SM)
            header = ctk.CTkFrame(card, fg_color="transparent")
            header.pack(fill="x", padx=PAD_MD, pady=(PAD_MD, PAD_XS))
            ctk.CTkLabel(
                header, text=names[key], text_color=TEXT_PRIMARY,
                font=ctk.CTkFont(size=12, weight="bold"),
            ).pack(side="left")
            button = ctk.CTkButton(
                header, text=self._ui("复制", "Copy"), width=72, height=28,
                fg_color=GEMINI_ACCENT, hover_color=GEMINI_HOVER)
            button.configure(command=lambda text=value, control=button: self._copy(text, control))
            button.pack(side="right")
            textbox = ctk.CTkTextbox(
                card, height=110, fg_color=BG_INPUT,
                font=ctk.CTkFont(family=FONT_MONO, size=10), wrap="word")
            textbox.pack(fill="x", padx=PAD_MD, pady=(0, PAD_MD))
            textbox.insert("1.0", value)
            textbox.configure(state="disabled")

        ctk.CTkButton(
            body, text=self._ui("关闭", "Close"), fg_color=BG_ELEVATED,
            hover_color=BORDER, text_color=TEXT_PRIMARY, command=self.dialog.destroy,
        ).pack(fill="x", pady=(PAD_MD, 0))

    def _ui(self, zh: str, en: str) -> str:
        return zh if self.lang == "zh" else en

    def _copy(self, value: str, button):
        self.dialog.clipboard_clear()
        self.dialog.clipboard_append(value)
        original = self._ui("复制", "Copy")
        button.configure(text=self._ui("已复制", "Copied"))
        self.dialog.after(1400, lambda: button.configure(text=original))

    def grab_set(self):
        self.dialog.grab_set()
        self.dialog.focus_force()


class ProviderDialog:
    def __init__(self, parent, lang, provider, on_save):
        self.lang = lang
        self.provider = provider
        self.on_save = on_save
        self.old_name = provider.get("name", "") if provider else ""
        self.dialog = ctk.CTkToplevel(parent)
        self.dialog.title(t("dialog_edit_title" if provider else "dialog_add_title", lang,
                            self.old_name) if provider else t("dialog_add_title", lang))
        self.dialog.geometry("560x650")
        self.dialog.resizable(False, False)
        self.dialog.configure(fg_color=BG_PRIMARY)
        self.dialog.transient(parent)
        self._build()

    def _build(self):
        body = ctk.CTkScrollableFrame(self.dialog, fg_color=BG_PRIMARY)
        body.pack(fill="both", expand=True, padx=PAD_XL, pady=PAD_XL)
        provider = self.provider or {}
        self.provider_kind = provider.get("provider_kind", "custom")
        self.name_var = ctk.StringVar(value=provider.get("name", ""))
        self.url_var = ctk.StringVar(value=provider.get("base_url", ""))
        self.model_var = ctk.StringVar(value=provider.get("model", ""))
        self.fast_var = ctk.StringVar(value=provider.get("small_fast_model", ""))
        self.key_var = ctk.StringVar(value="")
        self.enabled_var = ctk.BooleanVar(value=provider.get("enabled", True))
        auth_value = "x-api-key" if provider.get("auth_mode") == "x-api-key" else "Bearer Token"
        self.auth_var = ctk.StringVar(value=auth_value)
        self._field(body, "field_name", self.name_var, "tooltip_name")
        self._field(body, "field_url", self.url_var, "tooltip_url")
        self._field(body, "field_model", self.model_var, "tooltip_model")
        self._field(body, "field_fast_model", self.fast_var, "tooltip_fast_model")
        self._field(body, "field_api_key", self.key_var, "tooltip_key", password=True)

        auth_header = ctk.CTkFrame(body, fg_color="transparent")
        auth_header.pack(fill="x", pady=(PAD_SM, PAD_XS))
        ctk.CTkLabel(auth_header, text=t("field_auth_mode", self.lang),
                     text_color=TEXT_SECONDARY).pack(side="left")
        TooltipButton(auth_header, text=t("tooltip_auth_mode", self.lang), lang=self.lang).pack(side="left", padx=PAD_XS)
        ctk.CTkComboBox(body, values=["Bearer Token", "x-api-key"], variable=self.auth_var,
                        height=36, fg_color=BG_INPUT, border_color=BORDER).pack(fill="x")
        ctk.CTkSwitch(body, text=t("field_enabled", self.lang), variable=self.enabled_var,
                      progress_color=ACCENT).pack(anchor="w", pady=PAD_LG)
        self.error_label = ctk.CTkLabel(body, text="", text_color=DANGER, wraplength=480)
        self.error_label.pack(fill="x", pady=PAD_SM)
        buttons = ctk.CTkFrame(body, fg_color="transparent")
        buttons.pack(fill="x", pady=PAD_MD)
        ctk.CTkButton(buttons, text=t("cancel", self.lang), fg_color=BG_ELEVATED,
                      hover_color=BORDER, text_color=TEXT_PRIMARY,
                      command=self.dialog.destroy).pack(side="left", expand=True, fill="x", padx=(0, PAD_SM))
        ctk.CTkButton(buttons, text=t("save", self.lang), fg_color=ACCENT,
                      hover_color=ACCENT_HOVER, command=self._save).pack(side="right", expand=True, fill="x", padx=(PAD_SM, 0))

    def _field(self, parent, label_key, variable, tooltip_key, password=False):
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.pack(fill="x", pady=(PAD_SM, PAD_XS))
        ctk.CTkLabel(header, text=t(label_key, self.lang), text_color=TEXT_SECONDARY).pack(side="left")
        TooltipButton(header, text=t(tooltip_key, self.lang), lang=self.lang).pack(side="left", padx=PAD_XS)
        ctk.CTkEntry(parent, textvariable=variable, show="•" if password else None,
                     height=36, fg_color=BG_INPUT, border_color=BORDER).pack(fill="x")

    def _save(self):
        data = {
            "name": self.name_var.get().strip(),
            "base_url": self.url_var.get().strip(),
            "model": self.model_var.get().strip(),
            "small_fast_model": self.fast_var.get().strip(),
            "api_key": self.key_var.get().strip(),
            "enabled": self.enabled_var.get(),
            "priority": 99,
            "is_fallback": False,
            "auth_mode": "x-api-key" if self.auth_var.get() == "x-api-key" else "bearer",
            "provider_kind": self.provider_kind,
        }
        if self.on_save(data, self.old_name):
            self.dialog.destroy()

    def grab_set(self):
        self.dialog.grab_set()
        self.dialog.focus_force()


class ProviderGatewayDialog:
    """Gateway 供应商添加/编辑对话框"""

    def __init__(self, parent, lang, model_manager: ModelManager,
                 provider: Optional[dict], callback=None):
        self.lang = lang
        self.model_manager = model_manager
        self.provider = provider
        self.callback = callback
        self.dialog = ctk.CTkToplevel(parent)
        self.dialog.title(t("add_provider_title" if not provider else "edit_provider_title", lang))
        self.dialog.geometry("520x600")
        self.dialog.resizable(False, False)
        self.dialog.configure(fg_color=BG_PRIMARY)
        self.dialog.transient(parent)
        self._build()

    def _build(self):
        body = ctk.CTkScrollableFrame(self.dialog, fg_color=BG_PRIMARY)
        body.pack(fill="both", expand=True, padx=PAD_XL, pady=PAD_XL)

        provider = self.provider or {}

        # 供应商类型选择
        type_header = ctk.CTkFrame(body, fg_color="transparent")
        type_header.pack(fill="x", pady=(0, PAD_XS))
        ctk.CTkLabel(type_header, text=t("provider_type", self.lang),
                     text_color=TEXT_SECONDARY).pack(side="left")

        self.type_var = ctk.StringVar(value=provider.get("provider_type", "custom"))
        type_names = [v["name"] for v in SUPPORTED_PROVIDERS.values()]
        type_keys = list(SUPPORTED_PROVIDERS.keys())
        self.type_map = {v["name"]: k for k, v in SUPPORTED_PROVIDERS.items()}
        self.type_combo = ctk.CTkComboBox(body, values=type_names, variable=self.type_var,
                                           height=36, fg_color=BG_INPUT, border_color=BORDER,
                                           command=self._on_type_change)
        self.type_combo.pack(fill="x", pady=(0, PAD_SM))

        # 名称
        self.name_var = ctk.StringVar(value=provider.get("name", ""))
        self._field(body, "field_name", self.name_var)

        # Base URL
        self.url_var = ctk.StringVar(value=provider.get("base_url", ""))
        self._field(body, "field_url", self.url_var)

        # API Key
        self.key_var = ctk.StringVar(value="")
        self._field(body, "api_key", self.key_var, password=True)

        # 认证方式
        auth_header = ctk.CTkFrame(body, fg_color="transparent")
        auth_header.pack(fill="x", pady=(PAD_SM, PAD_XS))
        ctk.CTkLabel(auth_header, text=t("field_auth_mode", self.lang),
                     text_color=TEXT_SECONDARY).pack(side="left")
        auth_value = "x-api-key" if provider.get("auth_mode") == "x-api-key" else "Bearer Token"
        self.auth_var = ctk.StringVar(value=auth_value)
        ctk.CTkComboBox(body, values=["Bearer Token", "x-api-key"], variable=self.auth_var,
                        height=36, fg_color=BG_INPUT, border_color=BORDER).pack(fill="x")

        # 提示
        self.note_label = ctk.CTkLabel(body, text=t("api_key_encrypted", self.lang),
                                        text_color=INFO, font=ctk.CTkFont(size=10))
        self.note_label.pack(anchor="w", pady=PAD_SM)

        # 错误标签
        self.error_label = ctk.CTkLabel(body, text="", text_color=DANGER, wraplength=440)
        self.error_label.pack(fill="x", pady=PAD_SM)

        # 按钮
        buttons = ctk.CTkFrame(body, fg_color="transparent")
        buttons.pack(fill="x", pady=PAD_MD)
        ctk.CTkButton(buttons, text=t("cancel", self.lang), fg_color=BG_ELEVATED,
                      hover_color=BORDER, text_color=TEXT_PRIMARY,
                      command=self.dialog.destroy).pack(side="left", expand=True, fill="x", padx=(0, PAD_SM))
        ctk.CTkButton(buttons, text=t("save", self.lang), fg_color=ACCENT,
                      hover_color=ACCENT_HOVER, command=self._save).pack(side="right", expand=True, fill="x", padx=(PAD_SM, 0))

        # 如果是编辑模式，禁用类型选择
        if provider:
            self.type_combo.configure(state="disabled")

    def _field(self, parent, label_key, variable, password=False):
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.pack(fill="x", pady=(PAD_SM, PAD_XS))
        ctk.CTkLabel(header, text=t(label_key, self.lang),
                     text_color=TEXT_SECONDARY).pack(side="left")
        ctk.CTkEntry(parent, textvariable=variable, show="•" if password else None,
                     height=36, fg_color=BG_INPUT, border_color=BORDER).pack(fill="x")

    def _on_type_change(self, display_name: str):
        """供应商类型变化时更新默认 URL"""
        type_key = self.type_map.get(display_name, "custom")
        if type_key in SUPPORTED_PROVIDERS:
            default_url = SUPPORTED_PROVIDERS[type_key].get("base_url", "")
            if default_url and not self.url_var.get():
                self.url_var.set(default_url)

    def _save(self):
        type_display = self.type_var.get()
        type_key = self.type_map.get(type_display, "custom")
        name = self.name_var.get().strip()
        base_url = self.url_var.get().strip()
        api_key = self.key_var.get().strip()
        auth_mode = "x-api-key" if self.auth_var.get() == "x-api-key" else "bearer"

        if not name:
            self.error_label.configure(text=t("msg_name_required", self.lang))
            return
        if not base_url:
            self.error_label.configure(text=t("msg_url_required", self.lang))
            return
        if not api_key and not self.provider:
            self.error_label.configure(text=t("field_key", self.lang) + " *")
            return

        if self.provider:
            # 编辑模式
            provider_id = self.provider.get("id", "")
            data = {"name": name, "base_url": base_url, "auth_mode": auth_mode}
            if api_key:
                data["api_key"] = api_key
            ok, msg = self.model_manager.update_provider(provider_id, data)
        else:
            # 新增模式
            ok, msg = self.model_manager.add_provider(
                name=name, provider_type=type_key, base_url=base_url,
                api_key=api_key, auth_mode=auth_mode)

        if ok:
            if self.callback:
                self.callback()
            self.dialog.destroy()
        else:
            self.error_label.configure(text=msg)

    def grab_set(self):
        self.dialog.grab_set()
        self.dialog.focus_force()
