import customtkinter as ctk
import pytest

from app.smooth_widgets import SmoothButton, SmoothComboBox, SmoothFrame, surface_image
from app.theme import LIGHT, DARK


@pytest.fixture(scope="module")
def tk_root():
    root = ctk.CTk()
    root.withdraw()
    yield root
    root.destroy()


@pytest.mark.parametrize("palette", [LIGHT, DARK])
@pytest.mark.parametrize("scaling", [1.0, 1.25, 1.5, 2.0])
def test_smooth_widgets_theme_scale_events(palette, scaling, tk_root):
    root = tk_root
    try:
        ctk.set_widget_scaling(scaling)
        ctk.set_appearance_mode("light" if palette is LIGHT else "dark")
        card = SmoothFrame(root, width=400, height=150, corner_radius=10,
                           border_width=1, border_color=palette.accent, fg_color=palette.bg_surface)
        combo = SmoothComboBox(card, values=["中文", "English"], width=100,
                               fg_color=palette.bg_input, text_color=palette.text_primary)
        button = SmoothButton(card, text="?", width=32, height=32, corner_radius=16,
                              border_width=1, fg_color=palette.bg_surface)
        card.pack()
        combo.pack()
        button.pack()
        root.update_idletasks()
        for widget in (combo, button):
            widget._on_enter()
            widget._on_leave()
            widget.configure(state="disabled")
            widget.configure(state="normal")
        combo.set("English")
        assert combo.get() == "English"
        assert combo._canvas.tag_bind("smooth_surface", "<Button-1>")
        assert button.winfo_reqwidth() == button.winfo_reqheight()
        for widget in (card, combo, button):
            assert widget._surface_photo.width() == max(1, round(widget._apply_widget_scaling(widget._current_width)))
            assert len(widget._canvas.find_withtag("smooth_surface")) == 1
    finally:
        for child in root.winfo_children():
            child.destroy()
        ctk.set_widget_scaling(1)


def test_raster_has_antialiased_edges():
    image = surface_image(100, 32, 10, 1, "#ffffff", "#ffffff", "#2563eb",
                          "#eeeeee", 68, (84, 16, "#18283f"))
    assert image.size == (100, 32)
    # Intermediate edge colors prove the border is not a binary jagged mask.
    assert len({image.getpixel((x, y)) for x in range(14) for y in range(14)}) > 20
