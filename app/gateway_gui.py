"""
AI Gateway 管理面板 GUI
包含：仪表板、模型管理、供应商管理、请求日志

扩展现有 GUI，新增 Tab 页面
"""
import threading
from datetime import datetime
from typing import Optional

import customtkinter as ctk
from tkinter import messagebox

from .i18n import t
from .model_manager import ModelManager
from .gateway_server import GatewayServer, SUPPORTED_PROVIDERS
from .theme import LIGHT, DARK

# 复用主窗口的设计 token
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
FONT_FAMILY = "Microsoft YaHei UI"
FONT_MONO = "Consolas"
PAD_XS, PAD_SM, PAD_MD, PAD_LG, PAD_XL = 4, 8, 12, 16, 24


class GatewayPanel:
    """AI Gateway 管理面板"""

    def __init__(self, parent_frame, model_manager: ModelManager,
                 gateway: GatewayServer, lang: str, logger=None):
        self.parent = parent_frame
        self.model_manager = model_manager
        self.gateway = gateway
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
        """构建 Gateway 面板"""
        self.main_frame = ctk.CTkScrollableFrame(self.parent, fg_color=BG_PRIMARY)
        self.main_frame.pack(fill="both", expand=True)

        # 网关控制区
        self._build_gateway_control()

        # 统计卡片
        self._build_stats_cards()

        # 模型列表
        self._build_model_section()

        # 日志区
        self._build_log_section()

        self._refresh_all()

    def _build_gateway_control(self):
        """网关控制区"""
        card = ctk.CTkFrame(self.main_frame, fg_color=BG_SURFACE, corner_radius=12,
                            border_width=1, border_color=BORDER)
        card.pack(fill="x", pady=(0, PAD_LG))

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=PAD_LG, pady=(PAD_MD, PAD_SM))

        self.gw_title = self._bind_text(ctk.CTkLabel(
            head, text="", font=ctk.CTkFont(size=14, weight="bold"),
            text_color=TEXT_PRIMARY), "gateway_tab")
        self.gw_title.pack(side="left")

        self.gw_indicator = ctk.CTkLabel(head, text="○", text_color=TEXT_MUTED,
                                          font=ctk.CTkFont(size=15))
        self.gw_indicator.pack(side="right")

        # 状态行
        status_row = ctk.CTkFrame(card, fg_color="transparent")
        status_row.pack(fill="x", padx=PAD_LG, pady=PAD_XS)
        self.gw_status_label = ctk.CTkLabel(status_row, text=t("gateway_stopped", self.lang),
                                             text_color=TEXT_MUTED)
        self.gw_status_label.pack(side="left")

        # URL 行
        url_row = ctk.CTkFrame(card, fg_color="transparent")
        url_row.pack(fill="x", padx=PAD_LG, pady=PAD_XS)
        self.gw_url_label = ctk.CTkLabel(url_row, text="",
                                          text_color=INFO, font=ctk.CTkFont(family=FONT_MONO, size=11))
        self.gw_url_label.pack(side="left")

        self.copy_btn = ctk.CTkButton(url_row, text=t("copy_url", self.lang), width=70, height=26,
                                       fg_color=BG_ELEVATED, hover_color=BORDER,
                                       text_color=TEXT_PRIMARY,
                                       font=ctk.CTkFont(size=10),
                                       command=self._copy_url)
        self.copy_btn.pack(side="right")

        # 控制按钮
        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=PAD_LG, pady=(PAD_SM, PAD_MD))

        self.toggle_btn = ctk.CTkButton(
            btn_row, text=t("start_gateway", self.lang), height=36,
            fg_color=SUCCESS, hover_color=SUCCESS_DARK,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._toggle_gateway)
        self.toggle_btn.pack(side="left", padx=(0, PAD_SM))

        # 使用说明
        info_btn = ctk.CTkButton(
            btn_row, text="ℹ", width=36, height=36,
            fg_color=BG_ELEVATED, hover_color=BORDER, text_color=TEXT_PRIMARY,
            command=self._show_info)
        info_btn.pack(side="left")

    def _build_stats_cards(self):
        """统计卡片区"""
        cards_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        cards_frame.pack(fill="x", pady=(0, PAD_LG))
        for i in range(4):
            cards_frame.grid_columnconfigure(i, weight=1)

        # 今日请求
        self.card_requests = self._stat_card(cards_frame, 0, "today_requests", "0", ACCENT)
        # 今日 Token
        self.card_tokens = self._stat_card(cards_frame, 1, "today_tokens", "0", INFO)
        # 模型数量
        self.card_models = self._stat_card(cards_frame, 2, "model_count", "0", SUCCESS)
        # 网关状态
        self.card_status = self._stat_card(cards_frame, 3, "api_status", "—", TEXT_MUTED)

    def _stat_card(self, parent, col: int, title_key: str, value: str, color: str):
        """创建统计卡片"""
        card = ctk.CTkFrame(parent, fg_color=BG_SURFACE, corner_radius=10,
                            border_width=1, border_color=BORDER)
        card.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else PAD_XS, PAD_XS if col < 3 else 0))

        title = ctk.CTkLabel(card, text=t(title_key, self.lang),
                              text_color=TEXT_MUTED, font=ctk.CTkFont(size=10))
        title.pack(anchor="w", padx=PAD_MD, pady=(PAD_MD, 0))

        value_label = ctk.CTkLabel(card, text=value, text_color=color,
                                    font=ctk.CTkFont(size=20, weight="bold"))
        value_label.pack(anchor="w", padx=PAD_MD, pady=(PAD_XS, PAD_MD))

        return value_label

    def _build_model_section(self):
        """模型管理区"""
        section = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        section.pack(fill="x", pady=(0, PAD_LG))

        head = ctk.CTkFrame(section, fg_color="transparent")
        head.pack(fill="x", pady=(0, PAD_SM))

        self.models_title = self._bind_text(ctk.CTkLabel(
            head, text="", font=ctk.CTkFont(size=14, weight="bold"),
            text_color=TEXT_PRIMARY), "models_tab")
        self.models_title.pack(side="left")

        # 搜索框
        self.search_var = ctk.StringVar()
        self.search_entry = ctk.CTkEntry(
            head, textvariable=self.search_var, width=180, height=30,
            fg_color=BG_INPUT, border_color=BORDER, placeholder_text=t("search_model", self.lang))
        self.search_entry.pack(side="right", padx=(PAD_SM, 0))
        self.search_var.trace_add("write", lambda *_: self._refresh_model_list())

        self.add_model_btn = self._bind_text(ctk.CTkButton(
            head, text="", width=110, height=30, fg_color=ACCENT,
            hover_color=ACCENT_HOVER, command=self._show_add_model_dialog), "add_model")
        self.add_model_btn.pack(side="right")

        # 模型列表容器
        self.model_list_frame = ctk.CTkFrame(section, fg_color="transparent")
        self.model_list_frame.pack(fill="x")

    def _refresh_model_list(self):
        """刷新模型列表"""
        for widget in self.model_list_frame.winfo_children():
            widget.destroy()

        models = self.model_manager.get_all_models()
        search = self.search_var.get().strip().lower()

        if search:
            models = [m for m in models if search in m.get("model_name", "").lower()
                      or search in m.get("display_name", "").lower()
                      or search in m.get("provider_name", "").lower()]

        if not models:
            ctk.CTkLabel(self.model_list_frame, text=t("no_data", self.lang),
                         text_color=TEXT_MUTED).pack(pady=PAD_XL)
            return

        # 表头
        header = ctk.CTkFrame(self.model_list_frame, fg_color=BG_ELEVATED, corner_radius=6)
        header.pack(fill="x", pady=(0, PAD_XS))
        for col, text_key, weight in [("model_name", "model_name", 3), ("provider_name", "provider", 2),
                                       ("context_length", "context_length", 1), ("status", "status", 1),
                                       ("actions", "actions", 1)]:
            lbl = ctk.CTkLabel(header, text=t(text_key, self.lang),
                               text_color=TEXT_MUTED, font=ctk.CTkFont(size=10))
            lbl.pack(side="left", padx=PAD_MD, pady=PAD_XS)

        # 模型行
        for m in models:
            self._add_model_row(m)

    def _add_model_row(self, model: dict):
        """添加模型行"""
        row = ctk.CTkFrame(self.model_list_frame, fg_color=BG_SURFACE, corner_radius=6,
                           border_width=1, border_color=BORDER)
        row.pack(fill="x", pady=PAD_XS)

        # 模型名称
        name_text = model.get("display_name") or model.get("model_name", "—")
        ctk.CTkLabel(row, text=name_text, text_color=TEXT_PRIMARY,
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=PAD_MD, pady=PAD_SM)

        # 供应商
        ctk.CTkLabel(row, text=model.get("provider_name", "—"), text_color=TEXT_SECONDARY,
                     font=ctk.CTkFont(size=10)).pack(side="left", padx=PAD_MD, pady=PAD_SM)

        # 上下文长度
        ctx = model.get("context_length", 0)
        ctx_text = f"{ctx // 1000}K" if ctx >= 1000 else str(ctx)
        ctk.CTkLabel(row, text=ctx_text, text_color=TEXT_MUTED,
                     font=ctk.CTkFont(size=10)).pack(side="left", padx=PAD_MD, pady=PAD_SM)

        # 状态
        is_enabled = model.get("status") == "enabled"
        status_color = SUCCESS if is_enabled else TEXT_MUTED
        status_text = t("enabled", self.lang) if is_enabled else t("disabled", self.lang)
        ctk.CTkLabel(row, text=status_text, text_color=status_color,
                     font=ctk.CTkFont(size=10)).pack(side="left", padx=PAD_MD, pady=PAD_SM)

        # 操作按钮
        actions = ctk.CTkFrame(row, fg_color="transparent")
        actions.pack(side="right", padx=PAD_MD)

        toggle_text = t("disabled", self.lang) if is_enabled else t("enabled", self.lang)
        ctk.CTkButton(actions, text=toggle_text, width=50, height=24,
                      fg_color=BG_ELEVATED, hover_color=BORDER, text_color=TEXT_PRIMARY,
                      font=ctk.CTkFont(size=9),
                      command=lambda m=model: self._toggle_model(m)).pack(side="left", padx=PAD_XS)
        ctk.CTkButton(actions, text=t("delete", self.lang), width=40, height=24,
                      fg_color="transparent", hover_color=("#fde7e9", "#3f1d27"), text_color=DANGER,
                      font=ctk.CTkFont(size=9),
                      command=lambda m=model: self._delete_model(m)).pack(side="left")

    def _build_log_section(self):
        """日志区"""
        frame = ctk.CTkFrame(self.main_frame, fg_color=BG_SURFACE, corner_radius=10,
                             border_width=1, border_color=BORDER)
        frame.pack(fill="x", pady=(0, PAD_SM))

        head = ctk.CTkFrame(frame, fg_color="transparent")
        head.pack(fill="x", padx=PAD_LG, pady=(PAD_SM, PAD_XS))

        self.log_title = self._bind_text(ctk.CTkLabel(
            head, text="", text_color=TEXT_SECONDARY,
            font=ctk.CTkFont(size=11, weight="bold")), "logs_tab")
        self.log_title.pack(side="left")

        self.refresh_log_btn = ctk.CTkButton(
            head, text=t("refresh_logs", self.lang), width=60, height=24,
            fg_color=BG_ELEVATED, hover_color=BORDER, text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(size=10), command=self._refresh_logs)
        self.refresh_log_btn.pack(side="right", padx=PAD_XS)

        self.clear_log_btn = self._bind_text(ctk.CTkButton(
            head, text="", width=60, height=24, fg_color="transparent",
            hover_color=BORDER, font=ctk.CTkFont(size=10),
            command=self._clear_logs), "clear_logs")
        self.clear_log_btn.pack(side="right")

        self.log_text = ctk.CTkTextbox(frame, height=150, fg_color=BG_INPUT,
                                        font=ctk.CTkFont(family=FONT_MONO, size=10), state="disabled")
        self.log_text.pack(fill="x", padx=PAD_LG, pady=(0, PAD_MD))

    def _refresh_logs(self):
        """刷新日志"""
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")

        logs = self.model_manager.get_recent_logs(50)
        if not logs:
            self.log_text.insert("end", t("no_data", self.lang) + "\n")
        else:
            for log in logs:
                ts = datetime.fromtimestamp(log.get("request_time", 0)).strftime("%H:%M:%S")
                status_icon = "✓" if log.get("status") == "success" else "✗"
                line = (f"{ts}  {status_icon} {log.get('model', 'unknown'):20s}  "
                       f"In:{log.get('input_tokens', 0):6d}  Out:{log.get('output_tokens', 0):6d}  "
                       f"Total:{log.get('total_tokens', 0):6d}  {log.get('response_time_ms', 0)}ms")
                if log.get("error"):
                    line += f"  [{log['error'][:50]}]"
                self.log_text.insert("end", line + "\n")

        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _clear_logs(self):
        """清空日志显示"""
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _refresh_all(self):
        """刷新所有数据"""
        self._refresh_gateway_status()
        self._refresh_stats()
        self._refresh_model_list()
        self._refresh_logs()

    def _refresh_gateway_status(self):
        """刷新网关状态"""
        if self.gateway.is_running():
            self.gw_indicator.configure(text="●", text_color=SUCCESS)
            self.gw_status_label.configure(text=t("gateway_running", self.lang), text_color=SUCCESS)
            self.gw_url_label.configure(text=self.gateway.get_base_url())
            self.toggle_btn.configure(text=t("stop_gateway", self.lang), fg_color=DANGER)
        else:
            self.gw_indicator.configure(text="○", text_color=TEXT_MUTED)
            self.gw_status_label.configure(text=t("gateway_stopped", self.lang), text_color=TEXT_MUTED)
            self.gw_url_label.configure(text="")
            self.toggle_btn.configure(text=t("start_gateway", self.lang), fg_color=SUCCESS)

    def _refresh_stats(self):
        """刷新统计数据"""
        stats = self.model_manager.get_dashboard_stats()
        self.card_requests.configure(text=str(stats.get("today_requests", 0)))
        self.card_tokens.configure(text=str(stats.get("today_tokens", 0)))
        self.card_models.configure(text=str(stats.get("model_count", 0)))

        api_text = t("gateway_running", self.lang) if self.gateway.is_running() else t("gateway_stopped", self.lang)
        api_color = SUCCESS if self.gateway.is_running() else TEXT_MUTED
        self.card_status.configure(text=api_text, text_color=api_color)

    def _toggle_gateway(self):
        """启动/停止网关"""
        if self.gateway.is_running():
            ok, msg = self.gateway.stop()
        else:
            ok, msg = self.gateway.start()

        self._refresh_gateway_status()
        self._refresh_stats()
        if self.logger:
            self.logger.info(msg)

    def _copy_url(self):
        """复制网关地址到剪贴板"""
        url = self.gateway.get_base_url()
        try:
            self.parent.clipboard_clear()
            self.parent.clipboard_append(url)
            self.copy_btn.configure(text=t("copied", self.lang))
            self.parent.after(1500, lambda: self.copy_btn.configure(text=t("copy_url", self.lang)))
        except Exception:
            pass

    def _show_info(self):
        """显示使用说明"""
        info_lines = [
            t("gateway_info_title", self.lang),
            "",
            t("gateway_info_1", self.lang),
            t("gateway_info_2", self.lang),
            f"  {self.gateway.get_base_url()}",
            t("gateway_info_3", self.lang),
            t("gateway_info_4", self.lang),
        ]
        messagebox.showinfo(t("gateway_tab", self.lang), "\n".join(info_lines))

    def _toggle_model(self, model: dict):
        """切换模型状态"""
        ok, msg = self.model_manager.toggle_model(model.get("id", ""))
        if ok:
            self._refresh_model_list()
            self._refresh_stats()
        else:
            messagebox.showerror(t("error", self.lang), msg)

    def _delete_model(self, model: dict):
        """删除模型"""
        name = model.get("model_name", "")
        if not messagebox.askyesno(t("confirm_delete_title", self.lang),
                                   t("confirm_delete_model", self.lang, name)):
            return
        ok, msg = self.model_manager.delete_model(model.get("id", ""))
        if ok:
            self._refresh_model_list()
            self._refresh_stats()
        else:
            messagebox.showerror(t("error", self.lang), msg)

    def _show_add_model_dialog(self):
        """显示添加模型对话框"""
        ModelDialog(self.parent, self.lang, self.model_manager, None, self._refresh_model_list).grab_set()


class ModelDialog:
    """模型添加/编辑对话框"""

    def __init__(self, parent, lang, model_manager: ModelManager,
                 model: Optional[dict], on_save=None):
        self.lang = lang
        self.model_manager = model_manager
        self.model = model
        self.on_save = on_save
        self.dialog = ctk.CTkToplevel(parent)
        self.dialog.title(t("add_model" if not model else "edit_model", lang))
        self.dialog.geometry("480x520")
        self.dialog.resizable(False, False)
        self.dialog.configure(fg_color=BG_PRIMARY)
        self.dialog.transient(parent)
        self._build()

    def _build(self):
        body = ctk.CTkScrollableFrame(self.dialog, fg_color=BG_PRIMARY)
        body.pack(fill="both", expand=True, padx=PAD_XL, pady=PAD_XL)

        model = self.model or {}

        # 选择供应商
        self.provider_var = ctk.StringVar()
        providers = self.model_manager.get_all_providers()
        provider_names = [p.get("name", "") for p in providers]
        self.provider_map = {p.get("name", ""): p.get("id", "") for p in providers}

        if model.get("provider_name"):
            self.provider_var.set(model["provider_name"])
        elif provider_names:
            self.provider_var.set(provider_names[0])

        self._field(body, "provider", self.provider_var, type="combo", values=provider_names)

        # 模型名称
        self.name_var = ctk.StringVar(value=model.get("model_name", ""))
        self._field(body, "model_name", self.name_var)

        # 显示名称
        self.display_var = ctk.StringVar(value=model.get("display_name", ""))
        self._field(body, "display_name", self.display_var)

        # 输入价格
        self.input_price_var = ctk.StringVar(value=str(model.get("input_price", 0)))
        self._field(body, "input_price", self.input_price_var)

        # 输出价格
        self.output_price_var = ctk.StringVar(value=str(model.get("output_price", 0)))
        self._field(body, "output_price", self.output_price_var)

        # 上下文长度
        self.ctx_var = ctk.StringVar(value=str(model.get("context_length", 128000)))
        self._field(body, "context_length", self.ctx_var)

        # 错误标签
        self.error_label = ctk.CTkLabel(body, text="", text_color=DANGER, wraplength=400)
        self.error_label.pack(fill="x", pady=PAD_SM)

        # 按钮
        buttons = ctk.CTkFrame(body, fg_color="transparent")
        buttons.pack(fill="x", pady=PAD_MD)
        ctk.CTkButton(buttons, text=t("cancel", self.lang), fg_color=BG_ELEVATED,
                      hover_color=BORDER, text_color=TEXT_PRIMARY,
                      command=self.dialog.destroy).pack(side="left", expand=True, fill="x", padx=(0, PAD_SM))
        ctk.CTkButton(buttons, text=t("save", self.lang), fg_color=ACCENT,
                      hover_color=ACCENT_HOVER, command=self._save).pack(side="right", expand=True, fill="x", padx=(PAD_SM, 0))

    def _field(self, parent, label_key, variable, type="entry", values=None):
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.pack(fill="x", pady=(PAD_SM, PAD_XS))
        ctk.CTkLabel(header, text=t(label_key, self.lang),
                     text_color=TEXT_SECONDARY).pack(side="left")

        if type == "combo":
            widget = ctk.CTkComboBox(parent, variable=variable, values=values,
                                      height=36, fg_color=BG_INPUT, border_color=BORDER)
        else:
            widget = ctk.CTkEntry(parent, textvariable=variable, height=36,
                                   fg_color=BG_INPUT, border_color=BORDER)
        widget.pack(fill="x")

    def _save(self):
        provider_name = self.provider_var.get()
        provider_id = self.provider_map.get(provider_name, "")

        try:
            input_price = float(self.input_price_var.get() or 0)
            output_price = float(self.output_price_var.get() or 0)
            context_length = int(self.ctx_var.get() or 128000)
        except ValueError:
            self.error_label.configure(text="价格和上下文长度必须是数字")
            return

        data = {
            "provider_id": provider_id,
            "provider_name": provider_name,
            "model_name": self.name_var.get().strip(),
            "display_name": self.display_var.get().strip(),
            "input_price": input_price,
            "output_price": output_price,
            "context_length": context_length,
        }

        if not data["model_name"]:
            self.error_label.configure(text=t("msg_model_required", self.lang))
            return

        if self.model:
            ok, msg = self.model_manager.update_model(self.model.get("id", ""), data)
        else:
            ok, msg = self.model_manager.add_model(**data)

        if ok:
            if self.on_save:
                self.on_save()
            self.dialog.destroy()
        else:
            self.error_label.configure(text=msg)

    def grab_set(self):
        self.dialog.grab_set()
        self.dialog.focus_force()
