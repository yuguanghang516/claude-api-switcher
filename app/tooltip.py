"""
Tooltip 小白提示组件
文字右侧的圆形问号，鼠标悬停或点击弹出解释框
用于给非专业用户解释各字段含义
"""
import customtkinter as ctk


# 与 gui.py 保持一致的设计令牌
TEXT_PRIMARY = "#f1f5f9"
TEXT_SECONDARY = "#94a3b8"
TEXT_MUTED = "#64748b"
BG_ELEVATED = "#252532"
BG_SURFACE = "#1a1a24"
BORDER = "#2d2d3d"
ACCENT_LIGHT = "#a78bfa"
INFO = "#06b6d4"

# 24×24 点击区，圆圈视觉保持轻量
BTN_WIDTH = 24
BTN_HEIGHT = 24


class TooltipButton:
    """
    圆形问号 + 悬停/点击弹出提示框
    用法：
        tip = TooltipButton(parent, text="这是解释", lang="zh")
        tip.pack(...)
    """

    def __init__(self, parent, text: str, lang: str = "zh"):
        self.parent = parent
        self.text = text
        self.lang = lang
        self.tooltip_window = None
        self._after_id = None

        # 只显示圆圈内问号；说明文字放在弹层中。
        self.btn = ctk.CTkButton(
            parent,
            text="?",
            width=BTN_WIDTH,
            height=BTN_HEIGHT,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="transparent",
            hover_color=BG_ELEVATED,
            text_color=TEXT_SECONDARY,
            border_width=1,
            border_color=TEXT_MUTED,
            corner_radius=12,
            command=self._on_click_toggle,
        )

        # 绑定悬停事件
        self.btn.bind("<Enter>", self._on_enter)
        self.btn.bind("<Leave>", self._on_leave)
        self.btn.bind("<Return>", self._on_click_toggle)
        self.btn.bind("<space>", self._on_click_toggle)

    def pack(self, **kwargs):
        self.btn.pack(**kwargs)

    def grid(self, **kwargs):
        self.btn.grid(**kwargs)

    def configure(self, **kwargs):
        # 允许更新文本
        if "text" in kwargs:
            self.text = kwargs.pop("text")
        if "lang" in kwargs:
            self.lang = kwargs.pop("lang")
        self.btn.configure(**kwargs)

    def _on_enter(self, event=None):
        # 延迟显示，避免闪烁
        self._after_id = self.btn.after(300, self._show_tooltip)

    def _on_leave(self, event=None):
        if self._after_id:
            self.btn.after_cancel(self._after_id)
            self._after_id = None
        self._hide_tooltip()

    def _on_click_toggle(self, event=None):
        # 点击切换显示/隐藏
        if self.tooltip_window is not None:
            self._hide_tooltip()
        else:
            self._show_tooltip()

    def _show_tooltip(self):
        if self.tooltip_window is not None:
            return

        # 计算位置：按钮右侧
        x = self.btn.winfo_rootx() + self.btn.winfo_width() + 8
        y = self.btn.winfo_rooty()

        # 创建提示窗口
        self.tooltip_window = ctk.CTkToplevel(self.btn)
        self.tooltip_window.wm_overrideredirect(True)  # 无边框
        self.tooltip_window.attributes("-topmost", True)
        self.tooltip_window.configure(fg_color=BG_SURFACE)

        # 提示内容
        frame = ctk.CTkFrame(
            self.tooltip_window,
            fg_color=BG_SURFACE,
            corner_radius=8,
            border_width=1,
            border_color=BORDER,
        )
        frame.pack(padx=2, pady=2)

        label = ctk.CTkLabel(
            frame,
            text=self.text,
            font=ctk.CTkFont(size=11),
            text_color=TEXT_SECONDARY,
            justify="left",
            anchor="w",
            padx=12,
            pady=10,
            wraplength=280,
        )
        label.pack()

        # 确保窗口已渲染后调整位置（不超出屏幕）
        self.tooltip_window.update_idletasks()
        screen_w = self.tooltip_window.winfo_screenwidth()
        win_w = self.tooltip_window.winfo_width()
        if x + win_w > screen_w:
            x = self.btn.winfo_rootx() - win_w - 8
        self.tooltip_window.wm_geometry(f"+{x}+{y}")

    def _hide_tooltip(self):
        if self.tooltip_window is not None:
            self.tooltip_window.destroy()
            self.tooltip_window = None
