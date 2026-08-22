"""
AI Gateway 用量监控仪表板 GUI
页面内容：
- 用量与余额
- 路由规则
- 通知中心
"""
import math
import threading
import tkinter as tk
import webbrowser
from datetime import datetime
from typing import Optional, List, Dict

import customtkinter as ctk
from tkinter import messagebox

from .i18n import t
from .claude_usage import ClaudeUsageScanner
from .theme import LIGHT, DARK, theme

# 设计 token (与 gateway_gui.py 保持一致)
BG_PRIMARY = (LIGHT.bg_primary, DARK.bg_primary)
BG_SURFACE = (LIGHT.bg_surface, DARK.bg_surface)
BG_ELEVATED = (LIGHT.bg_elevated, DARK.bg_elevated)
BG_INPUT = (LIGHT.bg_input, DARK.bg_input)
TEXT_PRIMARY = (LIGHT.text_primary, DARK.text_primary)
TEXT_SECONDARY = (LIGHT.text_secondary, DARK.text_secondary)
TEXT_MUTED = (LIGHT.text_muted, DARK.text_muted)
BORDER = (LIGHT.border, DARK.border)
ACCENT = (LIGHT.accent, DARK.accent)
ACCENT_HOVER = (LIGHT.accent_hover, DARK.accent_hover)
SUCCESS = (LIGHT.success, DARK.success)
SUCCESS_DARK = (LIGHT.success_dark, DARK.success_dark)
DANGER = (LIGHT.danger, DARK.danger)
INFO = (LIGHT.info, DARK.info)
INFO_DARK = (LIGHT.info_dark, DARK.info_dark)
WARNING = (LIGHT.warning, DARK.warning)
FONT_FAMILY = "Microsoft YaHei UI"
FONT_MONO = "Consolas"
PAD_XS, PAD_SM, PAD_MD, PAD_LG, PAD_XL = 4, 8, 12, 16, 24
FONT_PAGE_TITLE = 16
FONT_SECTION_TITLE = 13
FONT_BODY = 11


class TokenHeatmap:
    """Theme-aware 7-day by 24-hour token activity heatmap."""

    LIGHT_LEVELS = ("#eef3fb", "#dbe8fb", "#b8d0f6", "#79a7ed", "#356fe2")
    DARK_LEVELS = ("#283241", "#2d4261", "#365b88", "#4078ba", "#55a3ff")

    def __init__(self, parent, lang: str = "zh"):
        self.lang = lang
        self.data = []
        self._cells = []
        self._hovered = None
        self.canvas = tk.Canvas(parent, height=230, bd=0, highlightthickness=0,
                                cursor="arrow")
        self.canvas.pack(fill="x", expand=True)
        self.canvas.bind("<Configure>", lambda _event: self.redraw())
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", self._on_leave)
        self.canvas.bind("<Destroy>", self._on_destroy, add="+")
        theme.register(self.redraw)

    @staticmethod
    def _color(value):
        if isinstance(value, (tuple, list)):
            return value[1] if ctk.get_appearance_mode().lower() == "dark" else value[0]
        return value

    @staticmethod
    def _format_tokens(value: int) -> str:
        if value >= 1_000_000_000:
            return f"{value / 1_000_000_000:.1f}B"
        if value >= 1_000_000:
            return f"{value / 1_000_000:.1f}M"
        if value >= 1_000:
            return f"{value / 1_000:.1f}K"
        return f"{value:,}"

    def set_language(self, lang: str):
        self.lang = lang
        self.redraw()

    def set_data(self, rows):
        self.data = list(rows or [])[-7:]
        self._hovered = None
        self.redraw()

    def _weekday(self, value: str) -> str:
        try:
            day = datetime.fromisoformat(value)
        except (TypeError, ValueError):
            return value or "—"
        if self.lang == "zh":
            names = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
        else:
            names = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
        return f"{names[day.weekday()]}  {day.month}/{day.day}"

    def redraw(self):
        if not self.canvas.winfo_exists():
            return
        self.canvas.delete("all")
        self._cells = []
        width = max(720, self.canvas.winfo_width())
        height = max(220, self.canvas.winfo_height())
        bg = self._color(BG_SURFACE)
        self.canvas.configure(bg=bg)

        left, right, top, bottom = 74, 12, 30, 10
        gap_x, gap_y = 4, 5
        grid_width = width - left - right
        cell_width = max(12, (grid_width - gap_x * 23) / 24)
        cell_height = max(16, (height - top - bottom - gap_y * 6) / 7)
        text_color = self._color(TEXT_MUTED)
        font = (FONT_FAMILY, 9)
        rows = self.data or []
        max_value = max((max(row.get("hours", [0]) or [0]) for row in rows), default=0)
        levels = self.DARK_LEVELS if ctk.get_appearance_mode().lower() == "dark" else self.LIGHT_LEVELS

        for hour in (0, 6, 12, 18):
            x = left + hour * (cell_width + gap_x)
            self.canvas.create_text(x, 14, text=f"{hour}:00", anchor="w",
                                    fill=text_color, font=(FONT_FAMILY, 9, "bold"))

        for row_index in range(7):
            row = rows[row_index] if row_index < len(rows) else {"date": "", "hours": [0] * 24}
            values = list(row.get("hours") or [])[:24]
            values.extend([0] * (24 - len(values)))
            y1 = top + row_index * (cell_height + gap_y)
            self.canvas.create_text(left - 8, y1 + cell_height / 2,
                                    text=self._weekday(row.get("date", "")),
                                    anchor="e", fill=text_color, font=font)
            for hour, value in enumerate(values):
                x1 = left + hour * (cell_width + gap_x)
                x2, y2 = x1 + cell_width, y1 + cell_height
                if value <= 0 or max_value <= 0:
                    level = 0
                else:
                    ratio = math.log1p(value) / math.log1p(max_value)
                    level = min(4, max(1, math.ceil(ratio * 4)))
                self.canvas.create_rectangle(
                    x1, y1, x2, y2, fill=levels[level], outline="", tags=("cell",))
                self._cells.append((x1, y1, x2, y2, row, hour, int(value)))

    def _on_motion(self, event):
        cell = next((item for item in self._cells
                     if item[0] <= event.x <= item[2] and item[1] <= event.y <= item[3]), None)
        if cell is None:
            self._on_leave()
            return
        identity = (cell[4].get("date", ""), cell[5])
        if identity == self._hovered:
            return
        self._hovered = identity
        self.canvas.delete("tooltip")
        date_text = self._weekday(cell[4].get("date", ""))
        token_text = self._format_tokens(cell[6])
        text = (f"{date_text} {cell[5]:02d}:00 · {token_text} Token"
                if self.lang == "zh" else
                f"{date_text} {cell[5]:02d}:00 · {token_text} tokens")
        width = self.canvas.winfo_width()
        x = min(max(event.x, 120), max(120, width - 120))
        y = max(24, event.y - 34)
        text_id = self.canvas.create_text(
            x, y, text=text, fill="#ffffff", font=(FONT_FAMILY, 10, "bold"),
            tags=("tooltip",))
        bbox = self.canvas.bbox(text_id)
        if bbox:
            box_id = self.canvas.create_rectangle(
                bbox[0] - 9, bbox[1] - 6, bbox[2] + 9, bbox[3] + 6,
                fill="#172033", outline="#334155", width=1, tags=("tooltip",))
            self.canvas.tag_lower(box_id, text_id)

    def _on_leave(self, _event=None):
        self._hovered = None
        if self.canvas.winfo_exists():
            self.canvas.delete("tooltip")

    def _on_destroy(self, event):
        if event.widget is self.canvas:
            theme.unregister(self.redraw)


class V2DashboardPanel:
    """用量监控仪表板面板。"""

    def __init__(self, parent_frame, gateway_v2, lang: str = "zh", logger=None,
                 provider_manager=None, claude_usage_root=None):
        self.parent = parent_frame
        self.gateway = gateway_v2
        self.lang = lang
        self.logger = logger
        self.provider_manager = provider_manager
        self.claude_usage_scanner = ClaudeUsageScanner(claude_usage_root)
        self._claude_usage = None
        self._gateway_usage = None
        self._monitor_busy = False
        self._monitor_error = ""
        self._bindings = []
        self._build()

    def _ui(self, zh: str, en: str) -> str:
        return zh if self.lang == "zh" else en

    def _bind_text(self, widget, key: str):
        self._bindings.append((widget, key))
        widget.configure(text=t(key, self.lang))
        return widget

    def _refresh_language(self):
        for widget, key in self._bindings:
            try:
                widget.configure(text=t(key, self.lang))
            except Exception:
                pass
        if hasattr(self, "balance_title"):
            self.balance_title.configure(
                text=self._ui("用量与余额", "Usage & Balance"))
            self.refresh_balance_btn.configure(
                text=self._ui("刷新中…", "Refreshing…") if self._monitor_busy
                else self._ui("刷新全部", "Refresh All"))
            self.balance_scope_note.configure(text=self._ui(
                "数据口径：Claude 本机统计和网关日志不等于供应商账单；只有标注“官方余额”的数值才是账户余额。不会读取聊天内容。",
                "Scope: local Claude usage and gateway logs are not provider bills. Only values marked Official Balance are account balances. Chat content is never read."))
            self.claude_usage_title.configure(
                text=self._ui("Claude Code 本机用量（不含 Codex）", "Local Claude Code Usage (Codex excluded)"))
            self.heatmap_title.configure(
                text=self._ui("近 7 天 Token 热力图", "7-Day Token Heatmap"))
            self.heatmap_note.configure(text=self._ui(
                "仅统计 Claude Code 输入 + 输出 Token；缓存单独展示，不计入热力图。",
                "Claude Code input + output tokens only; cache is shown separately and excluded from the heatmap."))
            self.token_heatmap.set_language(self.lang)
            self.gateway_usage_title.configure(
                text=self._ui("各 API 本地网关用量", "Per-API Local Gateway Usage"))
            self.official_balance_title.configure(
                text=self._ui("供应商账户余额", "Provider Account Balance"))
            self.routing_title.configure(
                text=self._ui("路由策略", "Routing"))
            self.routing_switch.configure(
                text=self._ui("启用", "Enabled"))
            self.failover_title.configure(
                text=self._ui("故障转移", "Failover"))
            self.reset_failover_btn.configure(
                text=self._ui("重置", "Reset"))
            self.notif_title.configure(
                text=self._ui("通知记录", "Notifications"))

    def set_lang(self, lang: str):
        self.lang = lang
        self._refresh_language()
        self._refresh_all()
        self.parent.after(250, self._refresh_balance)

    def _build(self):
        """构建用量监控仪表板。"""
        self.main_frame = ctk.CTkScrollableFrame(self.parent, fg_color=BG_PRIMARY)
        self.main_frame.pack(fill="both", expand=True)

        # 余额监控区
        self._build_balance_section()

        # 路由规则区
        self._build_routing_section()

        # 故障转移状态
        self._build_failover_section()

        # 通知历史
        self._build_notification_section()

        self._refresh_all()
        self.parent.after(250, self._refresh_balance)

    def _build_balance_section(self):
        """余额监控区"""
        card = ctk.CTkFrame(self.main_frame, fg_color=BG_SURFACE, corner_radius=12,
                            border_width=1, border_color=BORDER)
        card.pack(fill="x", pady=(0, PAD_LG))

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=PAD_LG, pady=(PAD_MD, PAD_SM))

        self.balance_title = ctk.CTkLabel(
            head, text=self._ui("用量与余额", "Usage & Balance"),
            font=ctk.CTkFont(family=FONT_FAMILY, size=FONT_PAGE_TITLE, weight="bold"),
            text_color=TEXT_PRIMARY)
        self.balance_title.pack(side="left")

        self.refresh_balance_btn = ctk.CTkButton(
            head, text=self._ui("刷新全部", "Refresh All"), width=76, height=28,
            fg_color=BG_ELEVATED, hover_color=BORDER, text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FONT_BODY),
            command=self._refresh_balance)
        self.refresh_balance_btn.pack(side="right")

        self.balance_last_update = ctk.CTkLabel(
            head, text="",
            text_color=TEXT_MUTED,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FONT_BODY))
        self.balance_last_update.pack(side="right", padx=PAD_SM)

        self.balance_scope_note = ctk.CTkLabel(
            card,
            text=self._ui(
                "数据口径：Claude 本机统计和网关日志不等于供应商账单；只有标注“官方余额”的数值才是账户余额。不会读取聊天内容。",
                "Scope: local Claude usage and gateway logs are not provider bills. Only values marked Official Balance are account balances. Chat content is never read."),
            anchor="w", justify="left", wraplength=860,
            text_color=WARNING,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FONT_BODY))
        self.balance_scope_note.pack(fill="x", padx=PAD_LG, pady=(0, PAD_MD))

        self.claude_usage_title = ctk.CTkLabel(
            card, text=self._ui("Claude Code 本机用量（不含 Codex）", "Local Claude Code Usage (Codex excluded)"),
            anchor="w",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FONT_SECTION_TITLE, weight="bold"),
            text_color=TEXT_PRIMARY)
        self.claude_usage_title.pack(fill="x", padx=PAD_LG)
        self.claude_usage_summary = ctk.CTkLabel(
            card, text=self._ui("正在读取本机 Token 记录…", "Reading local token records…"),
            anchor="w", justify="left", wraplength=860,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FONT_BODY),
            text_color=TEXT_SECONDARY)
        self.claude_usage_summary.pack(fill="x", padx=PAD_LG, pady=(PAD_XS, PAD_SM))

        self.heatmap_title = ctk.CTkLabel(
            card, text=self._ui("近 7 天 Token 热力图", "7-Day Token Heatmap"),
            anchor="w",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FONT_SECTION_TITLE, weight="bold"),
            text_color=TEXT_PRIMARY)
        self.heatmap_title.pack(fill="x", padx=PAD_LG, pady=(PAD_SM, 0))
        self.heatmap_note = ctk.CTkLabel(
            card,
            text=self._ui(
                "仅统计 Claude Code 输入 + 输出 Token；缓存单独展示，不计入热力图。",
                "Claude Code input + output tokens only; cache is shown separately and excluded from the heatmap."),
            anchor="w", text_color=TEXT_MUTED,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FONT_BODY))
        self.heatmap_note.pack(fill="x", padx=PAD_LG, pady=(PAD_XS, PAD_SM))
        heatmap_frame = ctk.CTkFrame(card, fg_color=BG_SURFACE)
        heatmap_frame.pack(fill="x", padx=PAD_LG, pady=(0, PAD_MD))
        self.token_heatmap = TokenHeatmap(heatmap_frame, self.lang)

        self.claude_usage_models_frame = ctk.CTkFrame(card, fg_color="transparent")
        self.claude_usage_models_frame.pack(fill="x", padx=PAD_LG, pady=(0, PAD_MD))

        self.gateway_usage_title = ctk.CTkLabel(
            card, text=self._ui("各 API 本地网关用量", "Per-API Local Gateway Usage"),
            anchor="w",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FONT_SECTION_TITLE, weight="bold"),
            text_color=TEXT_PRIMARY)
        self.gateway_usage_title.pack(fill="x", padx=PAD_LG)
        self.gateway_usage_frame = ctk.CTkFrame(card, fg_color="transparent")
        self.gateway_usage_frame.pack(fill="x", padx=PAD_LG, pady=(PAD_XS, PAD_MD))

        self.official_balance_title = ctk.CTkLabel(
            card, text=self._ui("供应商账户余额", "Provider Account Balance"),
            anchor="w",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FONT_SECTION_TITLE, weight="bold"),
            text_color=TEXT_PRIMARY)
        self.official_balance_title.pack(fill="x", padx=PAD_LG)

        # 余额卡片容器
        self.balance_cards_frame = ctk.CTkFrame(card, fg_color="transparent")
        self.balance_cards_frame.pack(fill="x", padx=PAD_LG, pady=(0, PAD_MD))

    def _build_routing_section(self):
        """路由规则区"""
        card = ctk.CTkFrame(self.main_frame, fg_color=BG_SURFACE, corner_radius=12,
                            border_width=1, border_color=BORDER)
        card.pack(fill="x", pady=(0, PAD_LG))

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=PAD_LG, pady=(PAD_MD, PAD_SM))

        self.routing_title = ctk.CTkLabel(
            head, text=self._ui("路由策略", "Routing"),
            font=ctk.CTkFont(family=FONT_FAMILY, size=FONT_SECTION_TITLE, weight="bold"),
            text_color=TEXT_PRIMARY)
        self.routing_title.pack(side="left")

        # 路由规则开关
        self.routing_switch_var = ctk.BooleanVar(value=True)
        self.routing_switch = ctk.CTkSwitch(
            head, text=self._ui("启用", "Enabled"), variable=self.routing_switch_var,
            command=self._toggle_routing)
        self.routing_switch.pack(side="right")

        # 规则列表
        self.routing_rules_frame = ctk.CTkFrame(card, fg_color="transparent")
        self.routing_rules_frame.pack(fill="x", padx=PAD_LG, pady=(0, PAD_MD))

    def _build_failover_section(self):
        """故障转移状态区"""
        card = ctk.CTkFrame(self.main_frame, fg_color=BG_SURFACE, corner_radius=12,
                            border_width=1, border_color=BORDER)
        card.pack(fill="x", pady=(0, PAD_LG))

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=PAD_LG, pady=(PAD_MD, PAD_SM))

        self.failover_title = ctk.CTkLabel(
            head, text=self._ui("故障转移", "Failover"),
            font=ctk.CTkFont(family=FONT_FAMILY, size=FONT_SECTION_TITLE, weight="bold"),
            text_color=TEXT_PRIMARY)
        self.failover_title.pack(side="left")

        self.reset_failover_btn = ctk.CTkButton(
            head, text=self._ui("重置", "Reset"), width=60, height=28,
            fg_color=BG_ELEVATED, hover_color=BORDER, text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FONT_BODY),
            command=self._reset_failover)
        self.reset_failover_btn.pack(side="right")

        # 目标状态列表
        self.failover_targets_frame = ctk.CTkFrame(card, fg_color="transparent")
        self.failover_targets_frame.pack(fill="x", padx=PAD_LG, pady=(0, PAD_MD))

    def _build_notification_section(self):
        """通知历史区"""
        card = ctk.CTkFrame(self.main_frame, fg_color=BG_SURFACE, corner_radius=12,
                            border_width=1, border_color=BORDER)
        card.pack(fill="x", pady=(0, PAD_SM))

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=PAD_LG, pady=(PAD_SM, PAD_XS))

        self.notif_title = ctk.CTkLabel(
            head, text=self._ui("通知记录", "Notifications"),
            text_color=TEXT_SECONDARY,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FONT_SECTION_TITLE, weight="bold"))
        self.notif_title.pack(side="left")

        self.notif_text = ctk.CTkTextbox(card, height=100, fg_color=BG_INPUT,
                                          font=ctk.CTkFont(family=FONT_FAMILY, size=FONT_BODY),
                                          state="disabled")
        self.notif_text.pack(fill="x", padx=PAD_LG, pady=(0, PAD_MD))

    def _refresh_all(self):
        """刷新所有数据"""
        self._refresh_balance_display()
        self._refresh_routing_display()
        self._refresh_failover_display()
        self._refresh_notifications()

    def _refresh_balance(self):
        """Refresh all monitor sources without blocking the UI thread."""
        if self._monitor_busy:
            return
        self._monitor_busy = True
        self.refresh_balance_btn.configure(
            state="disabled", text=self._ui("刷新中…", "Refreshing…"))
        self.balance_last_update.configure(text=self._ui("正在读取…", "Reading…"))

        def worker():
            claude_usage = None
            gateway_usage = None
            errors = []
            try:
                claude_usage = self.claude_usage_scanner.scan()
            except Exception:
                errors.append(self._ui("Claude 本机记录读取失败", "Failed to read local Claude records"))
            try:
                if getattr(self.gateway, "db", None):
                    gateway_usage = self.gateway.db.get_provider_usage_overview()
            except Exception:
                errors.append(self._ui("网关用量读取失败", "Failed to read gateway usage"))
            try:
                providers = self._get_balance_providers()
                if hasattr(self.gateway, "balance_checker"):
                    self.gateway.balance_checker.check_all(providers)
            except Exception:
                errors.append(self._ui("供应商余额刷新失败", "Failed to refresh provider balances"))
            self.parent.after(0, done, claude_usage, gateway_usage, "；".join(errors))

        def done(claude_usage, gateway_usage, error):
            self._claude_usage = claude_usage
            self._gateway_usage = gateway_usage
            self._monitor_error = error
            self._monitor_busy = False
            self.refresh_balance_btn.configure(
                state="normal", text=self._ui("刷新全部", "Refresh All"))
            self._refresh_balance_display()

        threading.Thread(target=worker, daemon=True, name="usage-balance-refresh").start()

    def _get_balance_providers(self) -> List[Dict]:
        providers = {}
        if self.provider_manager:
            for item in self.provider_manager.get_all_providers():
                detail = self.provider_manager.get_provider_detail(item.get("name", ""))
                if detail:
                    providers[detail.get("name", "unknown")] = {
                        "name": detail.get("name", "unknown"),
                        "type": detail.get("provider_kind", "custom"),
                        "provider_kind": detail.get("provider_kind", "custom"),
                        "api_key": detail.get("api_key", ""),
                        "base_url": detail.get("base_url", ""),
                    }
        if getattr(self.gateway, "db", None):
            for item in self.gateway._get_all_providers_for_balance():
                providers.setdefault(item.get("name", "unknown"), item)
        return list(providers.values())

    def _refresh_balance_display(self):
        """Render local usage, gateway usage and official balances separately."""
        for container in (self.claude_usage_models_frame, self.gateway_usage_frame,
                          self.balance_cards_frame):
            for widget in container.winfo_children():
                widget.destroy()

        if self._claude_usage:
            today = self._claude_usage["today"]
            month = self._claude_usage["month"]
            diagnostics = self._claude_usage["diagnostics"]
            self.claude_usage_summary.configure(text=self._ui(
                f"今日 {today['calls']:,} 次 · 正文 {today['content_tokens']:,} Token "
                f"（输入 {today['input_tokens']:,} + 输出 {today['output_tokens']:,}）· 缓存 {today['cache_tokens']:,}\n"
                f"本月正文 {month['content_tokens']:,} Token · 缓存 {month['cache_tokens']:,} · "
                f"已扫描 Claude Code 的 {diagnostics['files_scanned']:,} 个会话文件（不读取聊天内容，不扫描 Codex）",
                f"Today {today['calls']:,} calls · content {today['content_tokens']:,} tokens "
                f"(input {today['input_tokens']:,} + output {today['output_tokens']:,}) · cache {today['cache_tokens']:,}\n"
                f"This month content {month['content_tokens']:,} tokens · cache {month['cache_tokens']:,} · "
                f"{diagnostics['files_scanned']:,} Claude Code session files scanned (no chat content, no Codex)"))
            self.token_heatmap.set_data(self._claude_usage.get("heatmap", []))
            models = self._claude_usage.get("models", [])
            if models:
                for item in models[:10]:
                    self._add_usage_row(
                        self.claude_usage_models_frame, item["model"],
                        self._ui(
                            f"本月 {item['calls']:,} 次 · 正文 {item['content_tokens']:,} · 缓存 {item['cache_tokens']:,} Token",
                            f"Month {item['calls']:,} calls · content {item['content_tokens']:,} · cache {item['cache_tokens']:,} tokens"))
            else:
                self._empty_row(self.claude_usage_models_frame,
                                self._ui("本月暂无 Claude Token 记录", "No Claude token records this month"))
        else:
            self.claude_usage_summary.configure(
                text=self._monitor_error or self._ui("暂无本机用量数据", "No local usage data"))
            self.token_heatmap.set_data([])

        if self._gateway_usage:
            today_map = {item["provider"]: item for item in self._gateway_usage.get("today", [])}
            month_rows = self._gateway_usage.get("month", [])
            if month_rows:
                for item in month_rows:
                    today = today_map.get(item["provider"], {})
                    self._add_usage_row(
                        self.gateway_usage_frame, item["provider"],
                        self._ui(
                            f"今日 {today.get('total_requests', 0):,} 次 / {today.get('total_tokens', 0):,} Token · "
                            f"本月 {item['total_requests']:,} 次 / {item['total_tokens']:,} Token · 失败 {item['failed_requests']:,}",
                            f"Today {today.get('total_requests', 0):,} / {today.get('total_tokens', 0):,} tokens · "
                            f"Month {item['total_requests']:,} / {item['total_tokens']:,} tokens · failed {item['failed_requests']:,}"))
            else:
                self._empty_row(
                    self.gateway_usage_frame,
                    self._ui("暂无网关调用记录；Claude 直连用量请看上方本机统计",
                             "No gateway calls; see local Claude usage above for direct sessions"))
        else:
            self._empty_row(self.gateway_usage_frame,
                            self._ui("暂无网关用量数据", "No gateway usage data"))

        if not hasattr(self.gateway, 'balance_checker'):
            return

        cached = self.gateway.balance_checker.get_all_cached()
        if not cached:
            self._empty_row(self.balance_cards_frame,
                            self._ui("暂无供应商配置", "No providers configured"))
            return

        for name, info in cached.items():
            self._add_balance_card(name, info)

        # 更新时间
        now = datetime.now().strftime("%H:%M:%S")
        suffix = f" · {self._monitor_error}" if self._monitor_error else ""
        self.balance_last_update.configure(
            text=self._ui(f"更新：{now}{suffix}", f"Updated: {now}{suffix}"))

    def _empty_row(self, parent, message: str):
        ctk.CTkLabel(parent, text=message, text_color=TEXT_MUTED,
                     font=ctk.CTkFont(family=FONT_FAMILY, size=FONT_BODY)).pack(
                         anchor="w", pady=PAD_SM)

    def _add_usage_row(self, parent, name: str, detail: str):
        row = ctk.CTkFrame(parent, fg_color=BG_ELEVATED, corner_radius=7)
        row.pack(fill="x", pady=PAD_XS)
        ctk.CTkLabel(row, text=name, text_color=TEXT_PRIMARY,
                     font=ctk.CTkFont(family=FONT_FAMILY, size=FONT_BODY, weight="bold")).pack(
                         side="left", padx=PAD_MD, pady=PAD_SM)
        ctk.CTkLabel(row, text=detail, text_color=TEXT_SECONDARY,
                     font=ctk.CTkFont(family=FONT_FAMILY, size=FONT_BODY)).pack(
                         side="right", padx=PAD_MD, pady=PAD_SM)

    def _add_balance_card(self, name: str, info):
        """添加余额卡片"""
        row = ctk.CTkFrame(self.balance_cards_frame, fg_color=BG_ELEVATED, corner_radius=8)
        row.pack(fill="x", pady=PAD_XS)

        row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(row, text=name, text_color=TEXT_PRIMARY,
                     font=ctk.CTkFont(family=FONT_FAMILY, size=FONT_BODY, weight="bold")).grid(
                         row=0, column=0, sticky="w", padx=(PAD_MD, PAD_SM), pady=PAD_SM)
        if info.status == "quota":
            detail = self._ui(
                f"模型配额 · {info.error} · {info.source}",
                f"Model quota · {info.error} · {info.source}")
            value = self._ui(
                f"最低剩余 {info.percent_remaining:.0f}%",
                f"Minimum {info.percent_remaining:.0f}% left")
            value_color = WARNING if info.percent_remaining < 20 else SUCCESS
        elif info.status in {"official", "ok"}:
            detail = self._ui(f"官方余额 · {info.source}", f"Official balance · {info.source}")
            value = f"{info.currency} {info.balance:,.2f}"
            value_color = SUCCESS
        elif info.status == "error":
            detail = self._ui(f"查询失败 · {info.error}", f"Check failed · {info.error}")
            value = self._ui("不可用", "Unavailable")
            value_color = WARNING
        else:
            detail = info.error
            value = self._ui("需到平台查看", "View in portal")
            value_color = TEXT_MUTED
        ctk.CTkLabel(row, text=detail, text_color=TEXT_SECONDARY,
                     anchor="w", justify="left", wraplength=560,
                     font=ctk.CTkFont(family=FONT_FAMILY, size=FONT_BODY)).grid(
                         row=0, column=1, sticky="ew", padx=PAD_XS, pady=PAD_SM)
        ctk.CTkLabel(row, text=value, text_color=value_color,
                     font=ctk.CTkFont(family=FONT_FAMILY, size=FONT_BODY, weight="bold")).grid(
                         row=0, column=2, sticky="e", padx=PAD_SM, pady=PAD_SM)
        if info.portal_url:
            ctk.CTkButton(
                row, text=self._ui("打开平台", "Open Portal"), width=74, height=26,
                fg_color=BG_INPUT, hover_color=BORDER, text_color=TEXT_PRIMARY,
                command=lambda url=info.portal_url: webbrowser.open(url)).grid(
                    row=0, column=3, sticky="e", padx=(0, PAD_MD), pady=PAD_SM)

    def _refresh_routing_display(self):
        """刷新路由规则显示"""
        for widget in self.routing_rules_frame.winfo_children():
            widget.destroy()

        if not hasattr(self.gateway, 'smart_router'):
            return

        rules = self.gateway.smart_router.get_all_rules()
        for task_type, rule in rules.items():
            self._add_routing_rule_row(task_type, rule)

    def _add_routing_rule_row(self, task_type: str, rule):
        """添加路由规则行"""
        row = ctk.CTkFrame(self.routing_rules_frame, fg_color=BG_ELEVATED, corner_radius=6)
        row.pack(fill="x", pady=PAD_XS)

        # 规则名称和状态
        status_color = SUCCESS if rule.enabled else TEXT_MUTED
        status_text = "●" if rule.enabled else "○"
        ctk.CTkLabel(row, text=status_text, text_color=status_color,
                     font=ctk.CTkFont(size=12)).pack(side="left", padx=PAD_MD, pady=PAD_XS)

        ctk.CTkLabel(row, text=rule.description, text_color=TEXT_SECONDARY,
                     font=ctk.CTkFont(family=FONT_FAMILY, size=FONT_BODY)).pack(
                         side="left", padx=PAD_XS)

        # 优先模型
        models_text = " → ".join(rule.preferred_models[:2])
        ctk.CTkLabel(row, text=models_text, text_color=TEXT_MUTED,
                     font=ctk.CTkFont(family=FONT_MONO, size=FONT_BODY)).pack(
                         side="right", padx=PAD_MD)

    def _refresh_failover_display(self):
        """刷新故障转移状态"""
        for widget in self.failover_targets_frame.winfo_children():
            widget.destroy()

        if not hasattr(self.gateway, 'failover_engine'):
            return

        targets = self.gateway.failover_engine.get_target_status()
        if not targets:
            ctk.CTkLabel(self.failover_targets_frame, text="暂无故障转移目标",
                         text_color=TEXT_MUTED,
                         font=ctk.CTkFont(family=FONT_FAMILY, size=FONT_BODY)).pack(pady=PAD_SM)
            return

        for target in targets:
            self._add_failover_target_row(target)

    def _add_failover_target_row(self, target: Dict):
        """添加故障转移目标行"""
        row = ctk.CTkFrame(self.failover_targets_frame, fg_color=BG_ELEVATED, corner_radius=6)
        row.pack(fill="x", pady=PAD_XS)

        # 状态指示
        circuit = target.get("circuit_state", "unknown")
        if circuit == "closed":
            status_color = SUCCESS
            status_icon = "●"
        elif circuit == "half_open":
            status_color = WARNING
            status_icon = "◐"
        else:
            status_color = DANGER
            status_icon = "○"

        ctk.CTkLabel(row, text=status_icon, text_color=status_color,
                     font=ctk.CTkFont(size=12)).pack(side="left", padx=PAD_MD, pady=PAD_XS)

        # 模型名称
        ctk.CTkLabel(row, text=target.get("model_name", "unknown"),
                     text_color=TEXT_PRIMARY,
                     font=ctk.CTkFont(family=FONT_FAMILY, size=FONT_BODY)).pack(
                         side="left", padx=PAD_XS)

        # 健康状态
        is_healthy = target.get("is_healthy", True)
        health_text = "健康" if is_healthy else "异常"
        health_color = SUCCESS if is_healthy else DANGER
        ctk.CTkLabel(row, text=health_text, text_color=health_color,
                     font=ctk.CTkFont(family=FONT_FAMILY, size=FONT_BODY)).pack(
                         side="right", padx=PAD_XS)

        # 连续失败次数
        failures = target.get("consecutive_failures", 0)
        if failures > 0:
            ctk.CTkLabel(row, text=f"失败{failures}次", text_color=WARNING,
                         font=ctk.CTkFont(family=FONT_FAMILY, size=FONT_BODY)).pack(
                             side="right", padx=PAD_XS)

    def _refresh_notifications(self):
        """刷新通知历史"""
        if not hasattr(self.gateway, 'notifier'):
            return

        self.notif_text.configure(state="normal")
        self.notif_text.delete("1.0", "end")

        history = self.gateway.notifier.get_history(10)
        if not history:
            self.notif_text.insert("end", "暂无通知\n")
        else:
            for notif in reversed(history):
                ts = datetime.fromtimestamp(notif.timestamp).strftime("%H:%M:%S")
                priority_label = {
                    "low": "[提示]", "medium": "[注意]",
                    "high": "[重要]", "critical": "[严重]",
                }
                label = priority_label.get(notif.priority.value, "[提示]")
                self.notif_text.insert("end", f"{ts} {label} {notif.title}\n")
                if notif.message:
                    msg = notif.message[:80].replace("\n", " ")
                    self.notif_text.insert("end", f"    {msg}\n")

        self.notif_text.see("end")
        self.notif_text.configure(state="disabled")

    def _toggle_routing(self):
        """切换路由开关"""
        enabled = self.routing_switch_var.get()
        if hasattr(self.gateway, 'v2_config'):
            self.gateway.v2_config.set_routing_enabled(enabled)

    def _reset_failover(self):
        """重置故障转移"""
        if hasattr(self.gateway, 'failover_engine'):
            self.gateway.failover_engine.reset_all_circuits()
            self._refresh_failover_display()
