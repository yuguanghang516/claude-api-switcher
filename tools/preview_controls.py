"""Isolated visual QA; no credentials, network requests or app configuration."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import customtkinter as ctk
from app.smooth_widgets import SmoothFrame, SmoothButton, SmoothComboBox
from app.theme import LIGHT, DARK, apply_widget_defaults

apply_widget_defaults()
ctk.set_appearance_mode("light")
root = ctk.CTk()
root.title("Switcher — isolated control QA")
root.geometry("880x500")
root.configure(fg_color=(LIGHT.bg_primary, DARK.bg_primary))
bar = ctk.CTkFrame(root, fg_color="transparent")
bar.pack(fill="x", padx=24, pady=18)
ctk.CTkButton(bar, text="浅色 / 深色", command=lambda: ctk.set_appearance_mode(
    "dark" if ctk.get_appearance_mode() == "Light" else "light")).pack(side="left", padx=8)
for scale in (1, 1.25, 1.5, 2):
    ctk.CTkButton(bar, text=f"{scale:.0%}", width=65,
                  command=lambda s=scale: ctk.set_widget_scaling(s)).pack(side="left", padx=4)
ctk.CTkButton(bar, text="关闭", width=65, command=root.destroy).pack(side="right")

for smooth in (False, True):
    panel = ctk.CTkFrame(root, fg_color="transparent")
    panel.pack(side="left", fill="both", expand=True, padx=18, pady=10)
    ctk.CTkLabel(panel, text="修改后 · 抗锯齿绘制" if smooth else "修改前 · 原控件",
                 font=ctk.CTkFont(size=18, weight="bold")).pack(anchor="w", pady=10)
    frame_type, button_type, combo_type = ((SmoothFrame, SmoothButton, SmoothComboBox) if smooth
                                           else (ctk.CTkFrame, ctk.CTkButton, ctk.CTkComboBox))
    combo_type(panel, values=["中文", "English"], width=105, height=34).pack(anchor="w", pady=10)
    for name, active in (("LongCat", True), ("Gemini 反代", False)):
        card = frame_type(panel, fg_color=(LIGHT.bg_surface, DARK.bg_surface), corner_radius=10,
                          border_width=1, border_color=(LIGHT.accent, DARK.accent) if active
                          else (LIGHT.border, DARK.border))
        card.pack(fill="x", pady=6)
        ctk.CTkLabel(card, text=name + ("  · 当前使用" if active else ""),
                     font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=18, pady=10)
        ctk.CTkLabel(card, text="演示配置 · 不连接任何 API").pack(anchor="w", padx=18)
        button_type(card, text="?", width=32, height=32, corner_radius=16, border_width=1,
                     border_color=(LIGHT.border_strong, DARK.border_strong), fg_color="transparent",
                     text_color=(LIGHT.text_secondary, DARK.text_secondary)).pack(anchor="e", padx=18, pady=10)
root.mainloop()
