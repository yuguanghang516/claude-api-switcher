"""
V2 智能 AI Gateway 仪表板 GUI
新增 Tab 页面：
- 余额监控
- 成本控制
- 路由规则
- 通知中心
"""
import threading
from datetime import datetime
from typing import Optional, List, Dict

import customtkinter as ctk
from tkinter import messagebox

from .i18n import t
from .theme import LIGHT, DARK

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


class V2DashboardPanel:
    """V2 仪表板面板"""

    def __init__(self, parent_frame, gateway_v2, lang: str = "zh", logger=None):
        self.parent = parent_frame
        self.gateway = gateway_v2
        self.lang = lang
        self.logger = logger
        self._bindings = []
        self._build()

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

    def set_lang(self, lang: str):
        self.lang = lang
        self._refresh_language()
        self._refresh_all()

    def _build(self):
        """构建 V2 仪表板"""
        self.main_frame = ctk.CTkScrollableFrame(self.parent, fg_color=BG_PRIMARY)
        self.main_frame.pack(fill="both", expand=True)

        # 余额监控区
        self._build_balance_section()

        # 成本控制区
        self._build_cost_section()

        # 路由规则区
        self._build_routing_section()

        # 故障转移状态
        self._build_failover_section()

        # 通知历史
        self._build_notification_section()

        self._refresh_all()

    def _build_balance_section(self):
        """余额监控区"""
        card = ctk.CTkFrame(self.main_frame, fg_color=BG_SURFACE, corner_radius=12,
                            border_width=1, border_color=BORDER)
        card.pack(fill="x", pady=(0, PAD_LG))

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=PAD_LG, pady=(PAD_MD, PAD_SM))

        self.balance_title = ctk.CTkLabel(
            head, text="💰 余额监控",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=TEXT_PRIMARY)
        self.balance_title.pack(side="left")

        self.refresh_balance_btn = ctk.CTkButton(
            head, text="刷新", width=60, height=28,
            fg_color=BG_ELEVATED, hover_color=BORDER,
            font=ctk.CTkFont(size=10),
            command=self._refresh_balance)
        self.refresh_balance_btn.pack(side="right")

        self.balance_last_update = ctk.CTkLabel(
            head, text="",
            text_color=TEXT_MUTED, font=ctk.CTkFont(size=10))
        self.balance_last_update.pack(side="right", padx=PAD_SM)

        # 余额卡片容器
        self.balance_cards_frame = ctk.CTkFrame(card, fg_color="transparent")
        self.balance_cards_frame.pack(fill="x", padx=PAD_LG, pady=(0, PAD_MD))

    def _build_cost_section(self):
        """成本控制区"""
        card = ctk.CTkFrame(self.main_frame, fg_color=BG_SURFACE, corner_radius=12,
                            border_width=1, border_color=BORDER)
        card.pack(fill="x", pady=(0, PAD_LG))

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=PAD_LG, pady=(PAD_MD, PAD_SM))

        self.cost_title = ctk.CTkLabel(
            head, text="💵 成本控制",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=TEXT_PRIMARY)
        self.cost_title.pack(side="left")

        # 预算进度
        self.budget_frame = ctk.CTkFrame(card, fg_color="transparent")
        self.budget_frame.pack(fill="x", padx=PAD_LG, pady=(0, PAD_MD))

        # 每日预算
        self.daily_budget_label = ctk.CTkLabel(
            self.budget_frame, text="今日: $0 / $0 (0%)",
            text_color=TEXT_SECONDARY, font=ctk.CTkFont(size=11))
        self.daily_budget_label.pack(anchor="w", pady=PAD_XS)

        self.daily_budget_bar = ctk.CTkProgressBar(self.budget_frame, height=8,
                                                     fg_color=BG_INPUT, progress_color=SUCCESS)
        self.daily_budget_bar.pack(fill="x", pady=(0, PAD_SM))
        self.daily_budget_bar.set(0)

        # 每月预算
        self.monthly_budget_label = ctk.CTkLabel(
            self.budget_frame, text="本月: $0 / $0 (0%)",
            text_color=TEXT_SECONDARY, font=ctk.CTkFont(size=11))
        self.monthly_budget_label.pack(anchor="w", pady=PAD_XS)

        self.monthly_budget_bar = ctk.CTkProgressBar(self.budget_frame, height=8,
                                                      fg_color=BG_INPUT, progress_color=INFO)
        self.monthly_budget_bar.pack(fill="x", pady=(0, PAD_SM))
        self.monthly_budget_bar.set(0)

        # 各模型花费
        self.model_cost_frame = ctk.CTkFrame(card, fg_color="transparent")
        self.model_cost_frame.pack(fill="x", padx=PAD_LG, pady=(0, PAD_MD))

    def _build_routing_section(self):
        """路由规则区"""
        card = ctk.CTkFrame(self.main_frame, fg_color=BG_SURFACE, corner_radius=12,
                            border_width=1, border_color=BORDER)
        card.pack(fill="x", pady=(0, PAD_LG))

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=PAD_LG, pady=(PAD_MD, PAD_SM))

        self.routing_title = ctk.CTkLabel(
            head, text="🧭 智能路由",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=TEXT_PRIMARY)
        self.routing_title.pack(side="left")

        # 路由规则开关
        self.routing_switch_var = ctk.BooleanVar(value=True)
        self.routing_switch = ctk.CTkSwitch(
            head, text="启用", variable=self.routing_switch_var,
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
            head, text="🔄 故障转移",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=TEXT_PRIMARY)
        self.failover_title.pack(side="left")

        self.reset_failover_btn = ctk.CTkButton(
            head, text="重置", width=60, height=28,
            fg_color=BG_ELEVATED, hover_color=BORDER,
            font=ctk.CTkFont(size=10),
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
            head, text="🔔 通知",
            text_color=TEXT_SECONDARY,
            font=ctk.CTkFont(size=11, weight="bold"))
        self.notif_title.pack(side="left")

        self.notif_text = ctk.CTkTextbox(card, height=100, fg_color=BG_INPUT,
                                          font=ctk.CTkFont(family=FONT_MONO, size=9),
                                          state="disabled")
        self.notif_text.pack(fill="x", padx=PAD_LG, pady=(0, PAD_MD))

    def _refresh_all(self):
        """刷新所有数据"""
        self._refresh_balance_display()
        self._refresh_cost_display()
        self._refresh_routing_display()
        self._refresh_failover_display()
        self._refresh_notifications()

    def _refresh_balance(self):
        """刷新余额"""
        if hasattr(self.gateway, 'balance_checker'):
            providers = self.gateway._get_all_providers_for_balance()
            if providers:
                threading.Thread(
                    target=lambda: self.gateway.balance_checker.check_all(providers),
                    daemon=True,
                ).start()
        self._refresh_balance_display()

    def _refresh_balance_display(self):
        """刷新余额显示"""
        for widget in self.balance_cards_frame.winfo_children():
            widget.destroy()

        if not hasattr(self.gateway, 'balance_checker'):
            return

        cached = self.gateway.balance_checker.get_all_cached()
        if not cached:
            ctk.CTkLabel(self.balance_cards_frame, text="暂无余额数据，点击刷新检测",
                         text_color=TEXT_MUTED, font=ctk.CTkFont(size=10)).pack(pady=PAD_MD)
            return

        for name, info in cached.items():
            self._add_balance_card(name, info)

        # 更新时间
        now = datetime.now().strftime("%H:%M:%S")
        self.balance_last_update.configure(text=f"更新: {now}")

    def _add_balance_card(self, name: str, info):
        """添加余额卡片"""
        row = ctk.CTkFrame(self.balance_cards_frame, fg_color=BG_ELEVATED, corner_radius=8)
        row.pack(fill="x", pady=PAD_XS)

        # 供应商名称
        ctk.CTkLabel(row, text=name, text_color=TEXT_PRIMARY,
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=PAD_MD, pady=PAD_SM)

        if info.status == "ok":
            # 剩余百分比
            percent_text = f"{info.percent_remaining:.0f}%"
            percent_color = SUCCESS if info.percent_remaining > 30 else (
                WARNING if info.percent_remaining > 10 else DANGER)

            ctk.CTkLabel(row, text=percent_text, text_color=percent_color,
                         font=ctk.CTkFont(size=11, weight="bold")).pack(side="right", padx=PAD_MD)

            # 进度条
            bar = ctk.CTkProgressBar(row, height=6, width=80,
                                      fg_color=BG_INPUT, progress_color=percent_color)
            bar.pack(side="right", padx=PAD_XS)
            bar.set(info.percent_remaining / 100)

            # 余额文本
            balance_text = f"{info.currency} {info.balance:.2f}"
            ctk.CTkLabel(row, text=balance_text, text_color=TEXT_MUTED,
                         font=ctk.CTkFont(size=9)).pack(side="right", padx=PAD_XS)
        elif info.status == "error":
            ctk.CTkLabel(row, text=f"⚠ {info.error[:20]}", text_color=WARNING,
                         font=ctk.CTkFont(size=9)).pack(side="right", padx=PAD_MD)
        else:
            ctk.CTkLabel(row, text="暂不支持", text_color=TEXT_MUTED,
                         font=ctk.CTkFont(size=9)).pack(side="right", padx=PAD_MD)

    def _refresh_cost_display(self):
        """刷新成本显示"""
        if not hasattr(self.gateway, 'cost_controller'):
            return

        status = self.gateway.cost_controller.get_status()

        # 每日预算
        self.daily_budget_label.configure(
            text=f"今日: ${status.daily_used:.2f} / ${status.daily_limit:.2f} ({status.daily_percent:.0f}%)")
        self.daily_budget_bar.set(min(status.daily_percent / 100, 1))
        if status.daily_percent >= 100:
            self.daily_budget_bar.configure(progress_color=DANGER)
        elif status.daily_percent >= 80:
            self.daily_budget_bar.configure(progress_color=WARNING)
        else:
            self.daily_budget_bar.configure(progress_color=SUCCESS)

        # 每月预算
        self.monthly_budget_label.configure(
            text=f"本月: ${status.monthly_used:.2f} / ${status.monthly_limit:.2f} ({status.monthly_percent:.0f}%)")
        self.monthly_budget_bar.set(min(status.monthly_percent / 100, 1))
        if status.monthly_percent >= 100:
            self.monthly_budget_bar.configure(progress_color=DANGER)
        elif status.monthly_percent >= 80:
            self.monthly_budget_bar.configure(progress_color=WARNING)
        else:
            self.monthly_budget_bar.configure(progress_color=INFO)

        # 各模型花费
        for widget in self.model_cost_frame.winfo_children():
            widget.destroy()

        daily_by_model = self.gateway.cost_controller.get_daily_usage_by_model()
        if daily_by_model:
            ctk.CTkLabel(self.model_cost_frame, text="今日各模型花费:",
                         text_color=TEXT_MUTED, font=ctk.CTkFont(size=9)).pack(anchor="w")
            for model, cost in sorted(daily_by_model.items(), key=lambda x: -x[1]):
                ctk.CTkLabel(self.model_cost_frame,
                             text=f"  {model}: ${cost:.4f}",
                             text_color=TEXT_SECONDARY,
                             font=ctk.CTkFont(size=9)).pack(anchor="w")

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
                     font=ctk.CTkFont(size=10)).pack(side="left", padx=PAD_MD, pady=PAD_XS)

        ctk.CTkLabel(row, text=rule.description, text_color=TEXT_SECONDARY,
                     font=ctk.CTkFont(size=10)).pack(side="left", padx=PAD_XS)

        # 优先模型
        models_text = " → ".join(rule.preferred_models[:2])
        ctk.CTkLabel(row, text=models_text, text_color=TEXT_MUTED,
                     font=ctk.CTkFont(family=FONT_MONO, size=9)).pack(side="right", padx=PAD_MD)

    def _refresh_failover_display(self):
        """刷新故障转移状态"""
        for widget in self.failover_targets_frame.winfo_children():
            widget.destroy()

        if not hasattr(self.gateway, 'failover_engine'):
            return

        targets = self.gateway.failover_engine.get_target_status()
        if not targets:
            ctk.CTkLabel(self.failover_targets_frame, text="暂无故障转移目标",
                         text_color=TEXT_MUTED, font=ctk.CTkFont(size=10)).pack(pady=PAD_SM)
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
                     font=ctk.CTkFont(size=10)).pack(side="left", padx=PAD_XS)

        # 健康状态
        is_healthy = target.get("is_healthy", True)
        health_text = "健康" if is_healthy else "异常"
        health_color = SUCCESS if is_healthy else DANGER
        ctk.CTkLabel(row, text=health_text, text_color=health_color,
                     font=ctk.CTkFont(size=9)).pack(side="right", padx=PAD_XS)

        # 连续失败次数
        failures = target.get("consecutive_failures", 0)
        if failures > 0:
            ctk.CTkLabel(row, text=f"失败{failures}次", text_color=WARNING,
                         font=ctk.CTkFont(size=9)).pack(side="right", padx=PAD_XS)

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
                priority_icon = {"low": "○", "medium": "◐", "high": "●", "critical": "🔴"}
                icon = priority_icon.get(notif.priority.value, "○")
                self.notif_text.insert("end", f"{ts} {icon} {notif.title}\n")
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
