"""
Tooltip 小白提示组件
文字右侧的圆形问号，鼠标悬停或点击弹出解释框
用于给非专业用户解释各字段含义
"""
import customtkinter as ctk

from .theme import DARK, LIGHT


# 与其余页面共用语义色；CustomTkinter 会自动选择 light/dark 分量。
TEXT_SECONDARY = (LIGHT.text_secondary, DARK.text_secondary)
TEXT_MUTED = (LIGHT.text_muted, DARK.text_muted)
BG_ELEVATED = (LIGHT.bg_elevated, DARK.bg_elevated)
BG_SURFACE = (LIGHT.bg_surface, DARK.bg_surface)
BORDER = (LIGHT.border_strong, DARK.border_strong)

# 32×32 点击区：桌面端保持轻量，同时比原 24 px 更容易命中。
BTN_WIDTH = 32
BTN_HEIGHT = 32
SCREEN_MARGIN = 8


def clamp_tooltip_position(x: int, y: int, width: int, height: int,
                           screen_x: int, screen_y: int,
                           screen_width: int, screen_height: int):
    """Clamp a tooltip rectangle to the visible virtual screen bounds."""
    max_x = max(screen_x + SCREEN_MARGIN,
                screen_x + screen_width - width - SCREEN_MARGIN)
    max_y = max(screen_y + SCREEN_MARGIN,
                screen_y + screen_height - height - SCREEN_MARGIN)
    return (
        min(max(x, screen_x + SCREEN_MARGIN), max_x),
        min(max(y, screen_y + SCREEN_MARGIN), max_y),
    )


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
        self._pinned = False

        # 只显示圆圈内问号；说明文字放在弹层中。
        self.btn = ctk.CTkButton(
            parent,
            text="?",
            width=BTN_WIDTH,
            height=BTN_HEIGHT,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="transparent",
            hover_color=BG_ELEVATED,
            text_color=TEXT_SECONDARY,
            border_width=1,
            border_color=TEXT_MUTED,
            corner_radius=16,
            command=self._on_click_toggle,
        )

        # 绑定悬停事件
        self.btn.bind("<Enter>", self._on_enter)
        self.btn.bind("<Leave>", self._on_leave)
        self.btn.bind("<Return>", self._on_click_toggle)
        self.btn.bind("<space>", self._on_click_toggle)
        self.btn.bind("<Escape>", self._hide_tooltip)
        self.btn.bind("<FocusOut>", self._on_focus_out)

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
        if self.tooltip_window is not None:
            return
        self._after_id = self.btn.after(300, self._show_tooltip)

    def _on_leave(self, event=None):
        if self._after_id:
            self.btn.after_cancel(self._after_id)
            self._after_id = None
        if not self._pinned:
            self._hide_tooltip()

    def _on_click_toggle(self, event=None):
        # 点击切换显示/隐藏
        if self.tooltip_window is not None and self._pinned:
            self._hide_tooltip()
        else:
            self._pinned = True
            self._show_tooltip()
            self.btn.focus_set()

    def _on_focus_out(self, event=None):
        if self._pinned:
            self._hide_tooltip()

    def _show_tooltip(self):
        self._after_id = None
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
        self.tooltip_window.bind("<Escape>", self._hide_tooltip)
        self.tooltip_window.bind("<FocusOut>", self._on_focus_out)

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
            font=ctk.CTkFont(size=12),
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
        screen_x = self.tooltip_window.winfo_vrootx()
        screen_y = self.tooltip_window.winfo_vrooty()
        screen_w = self.tooltip_window.winfo_vrootwidth()
        screen_h = self.tooltip_window.winfo_vrootheight()
        win_w = self.tooltip_window.winfo_width()
        win_h = self.tooltip_window.winfo_height()
        if x + win_w + SCREEN_MARGIN > screen_x + screen_w:
            x = self.btn.winfo_rootx() - win_w - 8
        if y + win_h + SCREEN_MARGIN > screen_y + screen_h:
            y = self.btn.winfo_rooty() + self.btn.winfo_height() - win_h
        x, y = clamp_tooltip_position(
            x, y, win_w, win_h, screen_x, screen_y, screen_w, screen_h)
        self.tooltip_window.wm_geometry(f"{x:+d}{y:+d}")

    def _hide_tooltip(self, event=None):
        if self._after_id:
            try:
                self.btn.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        if self.tooltip_window is not None:
            self.tooltip_window.destroy()
            self.tooltip_window = None
        self._pinned = False
