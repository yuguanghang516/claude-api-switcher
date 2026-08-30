from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.gui import MainWindow, clamp_dialog_geometry
from app.theme import DARK
from app.tooltip import (
    BTN_HEIGHT,
    BTN_WIDTH,
    SCREEN_MARGIN,
    clamp_tooltip_position,
)
from app.v2_dashboard import FONT_BODY, FONT_HEATMAP_AUX, V2DashboardPanel


def _relative_luminance(hex_color: str) -> float:
    values = []
    for offset in (1, 3, 5):
        channel = int(hex_color[offset:offset + 2], 16) / 255
        values.append(channel / 12.92 if channel <= 0.04045
                      else ((channel + 0.055) / 1.055) ** 2.4)
    return 0.2126 * values[0] + 0.7152 * values[1] + 0.0722 * values[2]


def _contrast(first: str, second: str) -> float:
    high, low = sorted((_relative_luminance(first), _relative_luminance(second)),
                       reverse=True)
    return (high + 0.05) / (low + 0.05)


def test_dark_muted_text_remains_readable_on_all_dark_surfaces():
    for background in (DARK.bg_primary, DARK.bg_surface, DARK.bg_elevated, DARK.bg_input):
        assert _contrast(DARK.text_muted, background) >= 4.5


def test_v2_body_and_heatmap_font_floors():
    assert FONT_BODY >= 13
    assert FONT_HEATMAP_AUX >= 11


def test_tooltip_target_and_position_are_screen_safe():
    assert BTN_WIDTH >= 32
    assert BTN_HEIGHT >= 32
    x, y = clamp_tooltip_position(
        1900, 1060, 280, 120, 0, 0, 1920, 1080)
    assert x + 280 <= 1920 - SCREEN_MARGIN
    assert y + 120 <= 1080 - SCREEN_MARGIN

    x, y = clamp_tooltip_position(
        -2200, -200, 280, 120, -1920, 0, 1920, 1080)
    assert x >= -1920 + SCREEN_MARGIN
    assert y >= SCREEN_MARGIN


def test_dialog_geometry_preserves_normal_size_and_clamps_small_screen():
    normal = clamp_dialog_geometry(560, 650, 1920, 1080, 300, 100, 1080, 820)
    assert normal[:2] == (560, 650)
    width, height, x, y = clamp_dialog_geometry(
        560, 650, 1093, 614, 0, 0, 900, 614)
    assert width <= 1093 - 64
    assert height <= 614 - 112
    assert 0 <= x <= 1093 - width
    assert 0 <= y <= 614 - height


class _RoutingConfig:
    def __init__(self, enabled=False, save_ok=True):
        self.enabled = enabled
        self.save_ok = save_ok

    def is_routing_enabled(self):
        return self.enabled

    def set_routing_enabled(self, enabled):
        if not self.save_ok:
            return False
        self.enabled = bool(enabled)
        return True


class _Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def _routing_panel(config, desired, previous):
    panel = V2DashboardPanel.__new__(V2DashboardPanel)
    panel.gateway = SimpleNamespace(v2_config=config)
    panel.routing_switch_var = _Var(desired)
    panel._routing_switch_last = previous
    panel.lang = "zh"
    panel.parent = Mock()
    return panel


def test_routing_switch_reads_and_persists_real_config_state():
    config = _RoutingConfig(enabled=False)
    panel = _routing_panel(config, desired=True, previous=False)
    assert panel._read_routing_enabled(True) is False
    with patch("app.v2_dashboard.messagebox.showerror") as showerror:
        panel._toggle_routing()
    assert config.enabled is True
    assert panel.routing_switch_var.get() is True
    assert panel._routing_switch_last is True
    showerror.assert_not_called()


def test_routing_switch_rolls_back_when_persistence_fails():
    config = _RoutingConfig(enabled=False, save_ok=False)
    panel = _routing_panel(config, desired=True, previous=False)
    with patch("app.v2_dashboard.messagebox.showerror") as showerror:
        panel._toggle_routing()
    assert panel.routing_switch_var.get() is False
    assert panel._routing_switch_last is False
    showerror.assert_called_once()


def test_gateway_provider_dialog_is_grabbed_from_both_entry_points():
    window = MainWindow.__new__(MainWindow)
    window.root = Mock()
    window.lang = "zh"
    window.model_manager = Mock()
    window._refresh_models_tab = Mock()
    provider = {"id": "provider-1"}
    with patch("app.gui.ProviderGatewayDialog") as dialog:
        MainWindow._show_add_gateway_provider_dialog(window)
        MainWindow._show_edit_gateway_provider_dialog(window, provider)
    assert dialog.return_value.grab_set.call_count == 2


def test_main_language_update_reaches_usage_dashboard():
    window = MainWindow.__new__(MainWindow)
    window.lang = "en"
    window._bindings = []
    window._tooltips = []
    window.main_tabs = []
    window.gateway_subtabs = []
    window.v2_dashboard_panel = Mock()
    window._refresh_project_source_label = Mock()
    window._refresh_provider_list = Mock()
    window._refresh_current_status = Mock()

    MainWindow._update_language(window)

    window.v2_dashboard_panel.set_lang.assert_called_once_with("en")
